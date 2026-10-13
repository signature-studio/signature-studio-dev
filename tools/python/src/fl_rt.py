"""fl_rt — flpy ランタイム補助 (wasm 上の CPython 内で動く純 Python)。

役割:
  * call_json(target, args_json): ホスト(JS)から "module:func" を JSON 引数で呼ぶ (MCP tools/call, MIDI callback 等の共通口)
  * load_pyc(path, name): FL 同梱 .pyc (MCPTools.pyc 等) を指定名の module namespace で実行
  * flmidimsg: MIDI scripting の event オブジェクト (FL の `__main__.flmidimsg` 相当)
  * dispatch_midi(fields_json, module): 単一 module への受信 MIDI 配送 (OnMidiIn → OnMidiMsg → 型別。handled で停止)
  * CALLBACKS / load_device_script / init_scripts / dispatch_callback / dispatch_script_midi (PY-6 #76):
    device script (.py) ローダと 27 callback の配送表
  * install_flapi(): fl_api.install() への薄い委譲
"""
import importlib.util
import itertools
import json
import marshal
import sys
import traceback
import types


def _resolve(target):
    mod, _, attr = target.rpartition(":")
    m = sys.modules.get(mod or "__main__")
    if m is None:
        m = __import__(mod, fromlist=["_"])
    obj = m
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def call_json(target, args_json):
    try:
        fn = _resolve(target)
        a = json.loads(args_json) if args_json else {}
        r = fn(**a) if isinstance(a, dict) else fn(*a)
        return json.dumps({"ok": r}, default=str)
    except BaseException as e:  # noqa: BLE001 — ホスト境界で全例外を JSON 化
        return json.dumps({"err": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()})


def invoke_cb(id, args=None, release=True):
    """ホスト(FLEngine)が保持する {__cb:id} 経由で Python callable を呼び戻す (例: ilmcp.showHighlight の whenDone)。"""
    import _flhost
    fn = _flhost._cbs.pop(id) if release else _flhost._cbs[id]
    return fn(*(args or []))


def load_pyc(path, name="__main__"):
    """.pyc を読み、module `name` の namespace で実行。MCP は FL 側で `__main__` として実行される (get_mcp_tools_json が sys.modules['__main__'] を走査)。"""
    data = open(path, "rb").read()
    if data[:4] != importlib.util.MAGIC_NUMBER:
        raise ImportError(f"pyc magic mismatch: {data[:4]!r} != {importlib.util.MAGIC_NUMBER!r}")
    code = marshal.loads(data[16:])
    if name == "__main__":
        mod = sys.modules["__main__"]
    else:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    mod.__file__ = code.co_filename
    exec(code, mod.__dict__)
    return mod


_PYSCRIPTS = {}  # name -> module (読み込み済み .pyscript)
_FLAPI_GLOBALS = ("channels", "mixer", "patterns", "playlist", "transport", "general", "ui", "device", "arrangement",
                  "plugins", "screen", "launchMapPages")


def load_pyscript(path, name=None):
    """.pyscript を専用 module namespace で実行する。FL のピアノロールスクリプトは通常の Python ソース。
    トップレベルで実行される (createDialog/apply を持たない旧形式はこの時点で処理が走る)。
    戻り値: 公開エントリの有無 {"name", "createDialog", "apply"}。"""
    import flpianoroll
    name = name or "pyscript_" + str(len(_PYSCRIPTS))
    src = open(path, "rb").read().decode("utf-8-sig")
    mod = types.ModuleType(name)
    mod.__file__ = path
    # Remote Scripts (filleach 等) は import 無しで `channels.xxx` を参照する → インストール済みの flapi module を
    # グローバルに見せる (ASSUMPTION: FL 実機が同じ名前を注入していると推定。同梱 5 本の参照名から逆算)
    for fm in _FLAPI_GLOBALS:
        if fm in sys.modules:
            mod.__dict__[fm] = sys.modules[fm]
    sys.modules[name] = mod
    _PYSCRIPTS[name] = mod
    exec(compile(src, path, "exec"), mod.__dict__)
    return {"name": name, "createDialog": callable(getattr(mod, "createDialog", None)),
            "apply": callable(getattr(mod, "apply", None))}


def run_pyscript(name, score=None, values=None):
    """1 回分の実行: score(dict) を注入 → createDialog() → フォーム値(dict)を注入 → apply(form) → 結果 dict。
    call_json("fl_rt:run_pyscript", {"name":..,"score":..,"values":..}) の共通口からも呼べる (例外は call_json が {"err"} 化)。
    values は {"コントロール名": 値}。無指定のコントロールは createDialog の既定値のまま。"""
    import flpianoroll
    mod = _PYSCRIPTS[name]
    flpianoroll.reset(score)
    form = None
    dialog = None
    if callable(getattr(mod, "createDialog", None)):
        form = mod.createDialog()
        form.set_values(values or {})
        dialog = form.describe()
    if callable(getattr(mod, "apply", None)):
        mod.apply(form)
    return {"dialog": dialog, "score": flpianoroll.score.dump(),
            "utils": list(flpianoroll.Utils.messages), "warnings": list(flpianoroll.warnings)}


class flmidimsg:
    """FL の flmidimsg (FlMidiMsg) 相当。23 フィールドは FLEngine rodata (handled timestamp status data1 data2 port ...)。
    note/velocity/pressure/progNum/controlNum/controlVal は data1/data2 の別名 (公開 stubs 文書: 「Modifications to this will affect
    all data1 derived properties」)。midiId / midiChan / port / timestamp は文書上「常に 0」。"""

    __slots__ = ("handled", "timestamp", "status", "data1", "data2", "port", "sysex", "isIncrement", "res", "inEv",
                 "outEv", "midiId", "midiChan", "midiChanEx", "senderId", "pmeFlags")
    FIELDS = ("handled", "timestamp", "status", "data1", "data2", "port", "note", "velocity", "pressure", "progNum",
              "controlNum", "controlVal", "pitchBend", "sysex", "isIncrement", "res", "inEv", "outEv", "midiId",
              "midiChan", "midiChanEx", "senderId", "pmeFlags")

    def __init__(self, status=0, data1=0, data2=0, port=0, pmeFlags=0b101110, sysex=None, timestamp=0):
        if isinstance(status, (list, tuple, bytes, bytearray)):  # FlMidiMsg([0xF0, ...]) 形式 (sysex)
            sysex, status, data1, data2 = bytes(status), 0xF0, 0, 0
        self.handled = False
        self.timestamp = timestamp
        self.status = status
        self.data1 = data1
        self.data2 = data2
        self.port = port
        self.sysex = None if sysex is None else bytes(sysex)
        self.isIncrement = False
        self.res = 0.0
        self.inEv = 0
        self.outEv = 0
        self.midiId = 0
        self.midiChan = 0
        self.midiChanEx = 0
        self.senderId = 0
        self.pmeFlags = pmeFlags

    note = property(lambda s: s.data1, lambda s, v: setattr(s, "data1", v))
    pressure = property(lambda s: s.data1, lambda s, v: setattr(s, "data1", v))
    progNum = property(lambda s: s.data1, lambda s, v: setattr(s, "data1", v))
    controlNum = property(lambda s: s.data1, lambda s, v: setattr(s, "data1", v))
    velocity = property(lambda s: s.data2, lambda s, v: setattr(s, "data2", v))
    controlVal = property(lambda s: s.data2, lambda s, v: setattr(s, "data2", v))
    pitchBend = property(lambda s: s.data1 | (s.data2 << 7))

    def asdict(self):
        d = {k: getattr(self, k) for k in self.FIELDS if k != "sysex"}
        if self.sysex is not None:
            d["sysex"] = list(self.sysex)
        return d


# --- MIDI scripting callback 配送表 (FLEngine rodata の pycb* 27 個。引数名は公開 stubs の署名、OnInitAll のみ新規で引数なし) ---
# kind: lifecycle=スクリプト寿命 / midi=受信 MIDI (flmidimsg を渡す。OnMidiIn → OnMidiMsg → 型別の順) /
#       midi_out=MIDI Out プラグインからの送信 (flmidimsg) / host=FL 状態通知 (位置引数)
CALLBACKS = {
    "OnInit": ((), "lifecycle"), "OnInitAll": ((), "lifecycle"), "OnDeInit": ((), "lifecycle"),
    "OnMidiIn": (("msg",), "midi"), "OnMidiMsg": (("msg",), "midi"), "OnSysEx": (("msg",), "midi"),
    "OnNoteOn": (("msg",), "midi"), "OnNoteOff": (("msg",), "midi"), "OnControlChange": (("msg",), "midi"),
    "OnProgramChange": (("msg",), "midi"), "OnPitchBend": (("msg",), "midi"), "OnKeyPressure": (("msg",), "midi"),
    "OnChannelPressure": (("msg",), "midi"), "OnMidiOutMsg": (("msg",), "midi_out"),
    "OnIdle": ((), "host"), "OnProjectLoad": (("status",), "host"), "OnRefresh": (("flags",), "host"),
    "OnDoFullRefresh": ((), "host"), "OnUpdateBeatIndicator": (("value",), "host"), "OnDisplayZone": ((), "host"),
    "OnUpdateLiveMode": (("lastTrack",), "host"), "OnDirtyMixerTrack": (("index",), "host"),
    "OnDirtyChannel": (("index",), "host"), "OnFirstConnect": ((), "host"), "OnUpdateMeters": ((), "host"),
    "OnWaitingForInput": ((), "host"), "OnSendTempMsg": (("message", "duration"), "host"),
}
# 受信 MIDI の型別 callback (status の上位ニブル。sysex は status==0xF0)
_CB_BY_STATUS = {0x80: "OnNoteOff", 0x90: "OnNoteOn", 0xA0: "OnKeyPressure", 0xB0: "OnControlChange",
                 0xC0: "OnProgramChange", 0xD0: "OnChannelPressure", 0xE0: "OnPitchBend", 0xF0: "OnSysEx"}


def _call_cb(m, cb, args, called, errors):
    """module m の callback cb を呼ぶ。未定義なら何もしない。例外は FL と同じく Script output (stderr) へ出して続行、errors に記録。"""
    fn = getattr(m, cb, None)
    if not callable(fn):
        return False
    called.append(cb)
    try:
        fn(*args)
    except BaseException as e:  # noqa: BLE001 — スクリプトの例外でホストを落とさない
        errors.append({"cb": cb, "err": f"{type(e).__name__}: {e}"})
        traceback.print_exc()
    return True


def _midi_order(msg, m, called, errors):
    """FL の MIDI 受信配送: OnMidiIn (先頭・handled=True で全停止) → OnMidiMsg → 型別 (OnNoteOn 等)。
    各 callback が返った時点で msg.handled が True なら以降は呼ばない (公開 stubs 文書の callbacks / FlMidiMsg.handled)。"""
    for cb in ("OnMidiIn", "OnMidiMsg"):
        _call_cb(m, cb, (msg,), called, errors)
        if msg.handled:
            return
    cb = _CB_BY_STATUS.get(msg.status & 0xF0) if msg.status <= 0xF0 else None  # 0xF1〜0xFF (実時間/システム共通) は型別 callback なし
    if cb:
        _call_cb(m, cb, (msg,), called, errors)


def _mk_msg(f):
    return flmidimsg(f.get("status", 0), f.get("data1", 0), f.get("data2", 0), f.get("port", 0),
                     f.get("pmeFlags", 0b101110), f.get("sysex"), f.get("timestamp", 0))


def dispatch_midi(fields_json, module="__main__"):
    """単一 module (既定 __main__) への MIDI 配送 (PoC 互換)。順序と handled の扱いは _midi_order。"""
    msg = _mk_msg(json.loads(fields_json))
    called, errors = [], []
    _midi_order(msg, sys.modules[module], called, errors)
    return json.dumps({"called": called, "errors": errors, "msg": msg.asdict()})


# --- device script ローダ (FL の device_*.py。スクリプトごとに独立した module namespace) ---
_scripts = {}   # name -> {"module", "port", "meta", "path", "key"}
_script_seq = itertools.count(1)


def callback_table():
    return json.dumps({k: {"args": list(a), "kind": kind} for k, (a, kind) in CALLBACKS.items()})


def parse_meta(source):
    """先頭のコメント `# key=value` を読む (name / supportedDevices / receiveFrom 等。公開 stubs 文書の Script metadata)。"""
    meta = {}
    for line in source.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("#"):
            break
        k, sep, v = line[1:].partition("=")
        if sep and k.strip():
            meta[k.strip()] = v.strip()
    return meta


def load_device_script(name, source=None, path=None, port=None):
    """device script (.py) を読み込む。source (文字列) か path (wasm FS 上) のどちらか。OnInit は呼ばない (init_scripts)。
    port: この script が受ける MIDI 入力ポート番号 (None=全ポート)。同名の再読込は module を作り直す。
    exec が例外で失敗したら登録しない (sys.modules も戻す)。同名の既存 script は先に unload 済みで復元しない。"""
    if source is None:
        with open(path, "rb") as fh:
            source = fh.read().decode("utf-8")
    meta = parse_meta(source)
    if name in _scripts:
        unload_device_script(name)
    key = "fl_device_%d" % next(_script_seq)
    mod = types.ModuleType(key)
    mod.__file__ = path or f"<device:{name}>"
    code = compile(source, mod.__file__, "exec")
    sys.modules[key] = mod
    try:
        exec(code, mod.__dict__)
    except BaseException:
        sys.modules.pop(key, None)
        raise
    _scripts[name] = {"module": mod, "port": port, "meta": meta, "path": path, "key": key}
    return json.dumps({"name": name, "module": key, "meta": meta, "port": port,
                       "callbacks": sorted(cb for cb in CALLBACKS if callable(getattr(mod, cb, None)))})


def unload_device_script(name):
    s = _scripts.pop(name)
    sys.modules.pop(s["key"], None)
    return json.dumps(True)


def list_device_scripts():
    return json.dumps({n: {"module": s["key"], "port": s["port"], "meta": s["meta"],
                           "callbacks": sorted(cb for cb in CALLBACKS if callable(getattr(s["module"], cb, None)))}
                       for n, s in _scripts.items()})


def _targets(script, port=None):
    if script is not None:
        return [(script, _scripts[script])]
    return [(n, s) for n, s in _scripts.items() if port is None or s["port"] is None or s["port"] == port]


def dispatch_callback(cb, args_json="[]", script=None):
    """非 MIDI callback (lifecycle / host / midi_out) を全 script (script 指定時はその 1 本) に配送する。
    引数個数は CALLBACKS の定義と一致が必須 (不一致は ValueError = ホスト側のバグ)。midi_out は args=[fields] で flmidimsg を渡す。"""
    if cb not in CALLBACKS:
        raise ValueError(f"unknown callback: {cb}")
    names, kind = CALLBACKS[cb]
    a = json.loads(args_json) if args_json else []
    if kind == "midi":
        raise ValueError(f"{cb} は受信 MIDI 用: dispatch_script_midi を使う")
    if len(a) != len(names):
        raise ValueError(f"{cb} takes {len(names)} argument(s) {names}, got {len(a)}")
    out = []
    for n, s in _targets(script):
        called, errors = [], []
        args = (_mk_msg(a[0]),) if kind == "midi_out" else tuple(a)
        _call_cb(s["module"], cb, args, called, errors)
        out.append({"script": n, "called": called, "errors": errors})
    return json.dumps({"cb": cb, "results": out})


def init_scripts(script=None):
    """全 script に OnInit、その後に OnInitAll を 1 回ずつ (OnInitAll の意味は名前からの推定: 全 script の OnInit 後)。"""
    r = [json.loads(dispatch_callback("OnInit", "[]", script))]
    r.append(json.loads(dispatch_callback("OnInitAll", "[]", script)))
    return json.dumps(r)


def dispatch_script_midi(fields_json):
    """受信 MIDI を port が一致する device script (port=None は全ポート受け) に配送する。script ごとに独立した flmidimsg。"""
    f = json.loads(fields_json)
    out = []
    for n, s in _targets(None, f.get("port", 0)):
        msg = _mk_msg(f)
        called, errors = [], []
        _midi_order(msg, s["module"], called, errors)
        out.append({"script": n, "called": called, "errors": errors, "msg": msg.asdict()})
    return json.dumps({"results": out})


def install_flapi(table_path="/fl/Lib/flapi_table.json"):
    import fl_api
    return fl_api.install(table_path)
