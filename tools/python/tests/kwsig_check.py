#!/usr/bin/env python3
"""kwargs シグネチャ復元 (PY-9 b) の検証。wasm 不要 (偽 _flhost で fl_api.bind を直接検証)。
  python3 tests/kwsig_check.py
  1. flapi_table.json の kwsig が FLEngine 由来の書式/kwlist と整合 (kwlist 長 == 書式の最大引数数、NOARGS は書式無し)
  2. fl_api の bind: kwlist 名での呼出し・VARARGS のみ関数の kwargs 拒否・省略任意引数
  3. stubs の既定値を持つ引数の kw 呼出しが PR 前 (stubs 署名のみ) の bind と同じ結果になる (既知の差だけ許可)
  4. kwlist の重複名 (arrangement.selectionSet) の扱い
"""
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
calls = []
fake = types.ModuleType("_flhost")
fake.HostError = type("HostError", (Exception,), {})
fake.call = lambda fid, a: calls.append((fid, a)) or 0
sys.modules["_flhost"] = fake
sys.path.insert(0, os.path.join(ROOT, "src"))
import fl_api  # noqa: E402

t = json.load(open(os.path.join(ROOT, "analysis/flapi/flapi_table.json")))
n_fn = n_kw = n_fmt = 0
fmt_by_flags = {}
dup_kwlists = []
for m, fs in t["modules"].items():
    for n, e in fs.items():
        n_fn += 1
        ks = e.get("kwsig")
        assert ks is not None, f"{m}.{n}: kwsig 無し"
        if ks["flags"] & 4:  # METH_NOARGS は PyArg_Parse* を呼ばないので書式は無い (隣の関数の lea の誤検出を防ぐ)
            assert ks["fmt"] is None and "max" not in ks and "required" not in ks, (m, n, ks)
        if ks.get("kwlist") is not None:
            n_kw += 1
            assert ks["flags"] & 2 and len(ks["kwlist"]) == ks["max"], (m, n, ks)
            if len(set(ks["kwlist"])) != len(ks["kwlist"]):
                dup_kwlists.append(f"{m}.{n}")
        if ks.get("fmt") is not None:
            n_fmt += 1
            fmt_by_flags[ks["flags"]] = fmt_by_flags.get(ks["flags"], 0) + 1
print(f"functions={n_fn} with_fmt={n_fmt} {sorted(fmt_by_flags.items())} with_kwlist={n_kw} dup_kwlist={dup_kwlists}")
assert n_fn == 435 and n_kw == 103
assert fmt_by_flags == {1: 200, 3: 103} and n_fmt == 303
assert dup_kwlists == ["arrangement.selectionSet"]

fl_api.install(os.path.join(ROOT, "analysis/flapi/flapi_table.json"))
ch, mx, pl, ilm, gen, arr = (sys.modules[x] for x in ("channels", "mixer", "playlist", "ilmcp", "general", "arrangement"))
dv = sys.modules["device"]


def expect(exc, f, *a, **k):
    try:
        f(*a, **k)
    except exc:
        return
    raise AssertionError(f"{f.__qualname__}{a}{k}: {exc.__name__} 期待")


def last():
    return calls[-1][1]


# (1) kwlist 名 (バイナリ由来) で呼べる。stubs と名前が違う関数はバイナリ名が優先
mx.getTrackName(index=2, maxLen=9)
assert last() == (2, 9), last()
ch.setChannelPitch(1, value=5, pitchUnit=1, pickupMode=0, useGlobalIndex=False)
assert last() == (1, 5, 1, 0, False), last()
ch.getChannelName(value=4)  # バイナリの kwlist 先頭は 'value' (stubs は 'index')
assert last()[0] == 4, last()
# (2) stubs に署名が無かった新規関数も kwargs で呼べる
ch.rerollLoopStarterLoop(index=1)
assert last() == (1,), last()
# (3) 既定値不明の任意引数を飛ばして後ろだけ指定は不可 (C 側既定値が静的に不明)
expect(TypeError, ch.fillEachNSteps, 0, 4, velocity=100)
# (4) 未知 kwarg / 必須欠落
expect(TypeError, mx.getTrackName, 1, bogus=1)
expect(TypeError, mx.getTrackName, maxLen=3)
# (5) kwlist 無し (flags=1) は stubs 署名のまま: MCPTools が使う channelCount(globalCount=) は通る
ch.channelCount(globalCount=1)
assert last() == (1,), last()
expect(TypeError, ilm.runPRScript, s="x")  # 署名不明 (stubs 無し・kwlist 無し) は従来どおり拒否
pl.getTrackName(index=1)
assert last() == (1,), last()
# (6) 位置引数だけなら従来どおり
mx.getTrackName(7)
assert last() == (7,), last()

# (7) 既定値は stubs の同名引数のものだけ。名前が違う同位置 (stubs mode → kwlist useDb/flag) の既定値は引き継がない
expect(TypeError, ch.getChannelVolume, 1, useGlobalIndex=True)  # useDb は既定値不明 (途中の省略) → 拒否
ch.getChannelVolume(index=3)  # 末尾の useDb・useGlobalIndex は省略 → C 側の既定値
assert last() == (3,), last()
ch.getChannelVolume(1, True, useGlobalIndex=True)
assert last() == (1, True, True), last()
mx.getTrackVolume(index=2)  # stubs mode=0 は kwlist flag へ引き継がない → 省略
assert last() == (2,), last()
mx.getTrackVolume(2, flag=1)
assert last() == (2, 1), last()
gen.saveUndo("u", 1)  # 位置のみ
gen.saveUndo("u", 1, updateHistory=False)  # stubs update=True (別名) は引き継がない。明示指定は通る
assert last() == ("u", 1, False), last()
gen.saveUndo("u", 1)
assert last() == ("u", 1), last()
expect(TypeError, ch.getChannelVolume, 1, mode=1)  # バイナリに無い名前 (stubs の旧名) は拒否
expect(TypeError, mx.getTrackVolume, 1, mode=1)
# 位置がずれた引数 (stubs に無い引数がバイナリで挿入されている) は、別の引数の既定値を流用せず拒否
expect(TypeError, ch.soloChannel, 1, useGlobalIndex=True)
ch.soloChannel(1, 1, useGlobalIndex=True)
assert last() == (1, 1, True), last()
# gap (既定値不明の省略引数) より後ろの未指定引数には stubs 既定値を足さない (足すと位置がずれる)
ch.getGridBit(index=1)  # position が gap。後続 useGlobalIndex (stubs 既定 False) は省略
assert last() == (1,), last()
pl.triggerLiveClip(index=1, blockNum=2)  # flags が gap。後続 velocity (stubs 既定 -1) は省略
assert last() == (1, 2), last()
expect(TypeError, ch.getGridBit, index=1, useGlobalIndex=True)  # gap を越えた明示指定は従来どおり TypeError
expect(TypeError, pl.triggerLiveClip, index=1, blockNum=2, velocity=5)
# 未知の kwarg は既定値の評価 (stubs 由来の midi.* は eval できない) より先に TypeError
expect(TypeError, dv.linkToLastTweaked, 1, 2, eventId=3)

# (8) PR 前の bind (stubs 署名のみ。fl_api._make の旧実装と同一ロジック) との新旧比較。
#     stubs 署名と kwlist の両方がある 94 関数の全てで、位置引数 k 個 + kw 1 個 (kwlist の名前) の呼出しを比べる。
#     差は次の 3 種だけ (PY-15 #653 で既定値の引き継ぎを同名のみに変えた結果。期待を固定):
#       a. 名前だけ違う同位置の既定値を引き継がない → 末尾は省略 (C 側の既定値)、途中は TypeError
#          (channels.getChannelVolume/soloChannel/setChannelPitch, mixer.getTrackVolume/getEventIDName/automateEvent,
#           general.saveUndo, device.forwardMIDICC)
#       b. 旧が位置をずらして誤束縛していた (新は束縛しない・TypeError):
#          plugins.getColor (useGlobalIndex を paramIndex の位置へ) / plugins.getParamValueString (5 引数目を渡す)
#       c. バイナリは 5 引数なので旧の 6 つ目 (useGlobalIndex の stubs 既定値) を渡さない: channels.getStepParam
def legacy_bind(sig, args, kw):
    names = [p["name"] for p in sig["params"]]
    defaults = {p["name"]: p["default"] for p in sig["params"] if p["default"] is not None}
    if not kw:
        return args
    out = list(args)
    for n in names[len(args):]:
        if n in kw:
            out.append(kw.pop(n))
        elif n in defaults:
            out.append(eval(defaults[n], {}))
        else:
            raise TypeError(n)
    if kw:
        raise TypeError(sorted(kw))
    return tuple(out)


def outcome(fn):
    try:
        return ("ok", fn())
    except Exception as ex:  # noqa: BLE001
        return (type(ex).__name__, None)


n_cmp = n_same = 0
known = set()
for m, fs in t["modules"].items():
    for n, e in fs.items():
        kl = e["kwsig"].get("kwlist")
        if kl is None or not e.get("sig"):
            continue
        f = getattr(sys.modules[m], n)
        for k in range(len(kl) + 1):
            args = tuple(1000 + i for i in range(k))
            for kwn in dict.fromkeys(kl):
                old = outcome(lambda: legacy_bind(e["sig"], args, {kwn: 7777}))
                if old[0] != "ok":
                    continue
                n_cmp += 1
                new = outcome(lambda: (f(*args, **{kwn: 7777}), last())[1])
                if new == old:
                    n_same += 1
                else:
                    known.add(f"{m}.{n}")
print(f"legacy bind が通った kw 呼出し {n_cmp} 件のうち新も同結果 {n_same}、差 {sorted(known)}")
assert known == {"channels.getChannelVolume", "channels.getStepParam", "channels.setChannelPitch", "channels.soloChannel",
                 "device.forwardMIDICC", "general.saveUndo", "mixer.automateEvent", "mixer.getEventIDName",
                 "mixer.getTrackVolume", "plugins.getColor", "plugins.getParamValueString"}, known
assert (n_cmp, n_same) == (224, 208), (n_cmp, n_same)

# (9) kwlist の重複名 (arrangement.selectionSet は ['selStart','selStart','selectNotes',...]; バイナリ由来)
#     最初の出現だけを kw で束縛し、2 つ目以降は位置専用 (kw では埋まらない)
assert t["modules"]["arrangement"]["selectionSet"]["kwsig"]["kwlist"][:3] == ["selStart", "selStart", "selectNotes"]
arr.selectionSet(1, 2)
assert last() == (1, 2), last()
arr.selectionSet(1, 2, selectNotes=1)
assert last() == (1, 2, 1), last()
expect(TypeError, arr.selectionSet, selStart=5)  # 2 つ目の selStart が埋まらない (必須)
expect(TypeError, arr.selectionSet, 1, selStart=5)  # kw は最初の出現にしか束縛されない
expect(TypeError, arr.selectionSet, 1, 2, selStart=5)
print("kwsig_check: OK")
