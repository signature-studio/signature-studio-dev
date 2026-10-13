#!/usr/bin/env python3
"""kwargs シグネチャ復元 (PY-9 b) の検証。wasm 不要 (偽 _flhost で fl_api.bind を直接検証)。
  python3 tests/kwsig_check.py
  1. flapi_table.json の kwsig が FLEngine 由来の書式/kwlist と整合 (kwlist 長 == 書式の最大引数数)
  2. fl_api の bind: kwlist 名での呼出し・VARARGS のみ関数の kwargs 拒否・省略任意引数
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
for m, fs in t["modules"].items():
    for n, e in fs.items():
        n_fn += 1
        ks = e.get("kwsig")
        assert ks is not None, f"{m}.{n}: kwsig 無し"
        if ks.get("kwlist") is not None:
            n_kw += 1
            assert ks["flags"] & 2 and len(ks["kwlist"]) == ks["max"], (m, n, ks)
        if ks.get("fmt") is not None:
            n_fmt += 1
print(f"functions={n_fn} with_fmt={n_fmt} with_kwlist={n_kw}")
assert n_fn == 435 and n_kw >= 100

fl_api.install(os.path.join(ROOT, "analysis/flapi/flapi_table.json"))
ch, mx, pl, ilm = (sys.modules[x] for x in ("channels", "mixer", "playlist", "ilmcp"))

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
print("kwsig_check: OK")
