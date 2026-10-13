"""fl_rt — flpy ランタイム補助 (wasm 上の CPython 内で動く純 Python)。

役割:
  * call_json(target, args_json): ホスト(JS)から "module:func" を JSON 引数で呼ぶ (MCP tools/call, MIDI callback 等の共通口)
  * load_pyc(path, name): FL 同梱 .pyc (MCPTools.pyc 等) を指定名の module namespace で実行
  * flmidimsg: MIDI scripting の event オブジェクト (FL の `__main__.flmidimsg` 相当)
  * dispatch_midi(cb, fields_json): FL の OnMidiMsg/OnNoteOn... 経路の模擬ディスパッチ
  * install_flapi(): fl_api.install() への薄い委譲
"""
import importlib.util
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
    """FL の flmidimsg 相当 (フィールド一覧は FLEngine rodata: handled timestamp status data1 data2 port ...)。"""

    __slots__ = ("handled", "timestamp", "status", "data1", "data2", "port", "note", "velocity", "pressure",
                 "progNum", "controlNum", "controlVal", "pitchBend", "sysex", "isIncrement", "res", "inEv", "outEv",
                 "midiId", "midiChan", "midiChanEx", "senderId", "pmeFlags")

    def __init__(self, status=0, data1=0, data2=0, port=0, pmeFlags=0b101110, sysex=None):
        self.handled = False
        self.timestamp = 0
        self.status = status
        self.data1 = data1
        self.data2 = data2
        self.port = port
        self.sysex = sysex
        self.isIncrement = False
        self.res = 0.0
        self.inEv = 0
        self.outEv = 0
        self.midiId = 0
        self.midiChan = status & 0x0F
        self.midiChanEx = 0
        self.senderId = 0
        self.pmeFlags = pmeFlags
        self.pitchBend = 0
        self.note = self.velocity = self.pressure = self.progNum = self.controlNum = self.controlVal = 0
        self._derive()

    def _derive(self):
        s = self.status & 0xF0
        if s in (0x80, 0x90):
            self.note, self.velocity = self.data1, self.data2
        elif s == 0xA0:
            self.note, self.pressure = self.data1, self.data2
        elif s == 0xB0:
            self.controlNum, self.controlVal = self.data1, self.data2
        elif s == 0xC0:
            self.progNum = self.data1
        elif s == 0xD0:
            self.pressure = self.data1
        elif s == 0xE0:
            self.pitchBend = self.data1 | (self.data2 << 7)

    def asdict(self):
        return {k: getattr(self, k) for k in self.__slots__ if k != "sysex" or self.sysex is not None}


_CB_BY_STATUS = {0x80: "OnNoteOff", 0x90: "OnNoteOn", 0xA0: "OnKeyPressure", 0xB0: "OnControlChange",
                 0xC0: "OnProgramChange", 0xD0: "OnChannelPressure", 0xE0: "OnPitchBend"}


def dispatch_midi(fields_json, module="__main__"):
    """FL の MIDI scripting 経路: OnMidiIn → (未 handled なら) OnMidiMsg → OnNoteOn 等。FL と同じ順序/条件で呼ぶ。"""
    f = json.loads(fields_json)
    msg = flmidimsg(f.get("status", 0), f.get("data1", 0), f.get("data2", 0), f.get("port", 0),
                    f.get("pmeFlags", 0b101110), f.get("sysex"))
    m = sys.modules[module]
    called = []
    for cb in ("OnMidiIn", "OnMidiMsg"):
        fn = getattr(m, cb, None)
        if fn:
            fn(msg)
            called.append(cb)
    if not msg.handled:
        cb = _CB_BY_STATUS.get(msg.status & 0xF0)
        fn = getattr(m, cb, None) if cb else None
        if fn:
            fn(msg)
            called.append(cb)
    return json.dumps({"called": called, "msg": msg.asdict()})


def install_flapi(table_path="/fl/Lib/flapi_table.json"):
    import fl_api
    return fl_api.install(table_path)
