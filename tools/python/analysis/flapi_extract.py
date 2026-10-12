#!/usr/bin/env python3
"""FLEngine (mac Mach-O universal / win PE) の rodata から FL 組込 Python モジュール(API面)を抽出する。

  python3 analysis/flapi_extract.py <FLEngine> [--arch x86_64] > flapi_<plat>.json

FL の PyMethodDef 相当は Delphi(Python4Delphi) 側コードで AddMethod(name, func, doc) と登録され、
rodata 上は `name\0 doc\0 name\0 doc\0 ... <module>\0 <fmt>\0.. <kwarg>\0..` の並びで現れる。
モジュール名トークンの直前までの (識別子, 大文字始まり/空白含む説明) 交互列を関数表として回収する。
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from paths import FL_MAC_DIR, FL_WIN64_DIR  # noqa: E402

MODULES = ["transport", "mixer", "channels", "patterns", "playlist", "plugins", "general", "device",
           "arrangement", "launchMapPages", "screen", "ui", "ilmcp", "flpianoroll", "enveditor", "harmonicscale"]
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def slices(b):
    if b[:4] == b"\xca\xfe\xba\xbe":
        n = struct.unpack(">I", b[4:8])[0]
        out = {}
        for i in range(n):
            cpu, sub, off, size, al = struct.unpack(">iiIII", b[8 + 20 * i: 28 + 20 * i])
            out[{0x01000007: "x86_64", 0x0100000C: "arm64"}.get(cpu, hex(cpu))] = b[off:off + size]
        return out
    return {"pe": b}


def is_doc(t):
    return (" " in t) or t[:1].isupper()


def _load_stub_names():
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "fl-stubs", "data", "fl_stubs.json")
    try:
        return {m: set(v) for m, v in json.load(open(p)).items()}
    except OSError:
        return {}


STUB_NAMES = _load_stub_names()


def marker_of(tok):
    """win PE は文字列が .text に直接埋まり、モジュール名に直前コードバイトが連結することがある。"""
    if tok in MODULES:
        return tok
    for m in MODULES:
        if len(m) >= 5 and tok.endswith(m) and len(tok) > len(m) and (ord(tok[-len(m) - 1]) >= 0x80 or ord(tok[-len(m) - 1]) < 0x20):
            return m
    return None


def pair_ok(a, d):
    return (bool(IDENT.match(a)) and len(a) >= 2 and a[0].islower() and len(d) >= 3
            and (" " in d or d[0].isupper()) and not (IDENT.match(d) and d[0].islower()))


def extract(data):
    toks = [t.decode("latin1") for t in re.split(rb"\x00+", data) if t]
    n = len(toks)
    start = next(k for k in range(n - 1) if toks[k] == "getChannelName" and toks[k + 1] == "Get channel name")
    lo, hi = max(0, start - 1500), min(n, start + 4000)
    res = {}
    last_end = lo
    for k in range(lo, hi):
        m = marker_of(toks[k])
        if m is None:
            continue
        # 直前から (name, doc) 交互列を後ろ向きに回収
        fns = []
        j = k
        skip = 0
        while toks[k] != m and j - 2 >= last_end and skip < 8 and not pair_ok(toks[j - 2], toks[j - 1]):
            j -= 1  # win: 最終関数と marker の間にコードバイト列トークンが挟まる
            skip += 1
        while j - 2 >= last_end and pair_ok(toks[j - 2], toks[j - 1]):
            fns.append((toks[j - 2], toks[j - 1]))
            j -= 2
        fns.reverse()
        # 後続 (fmt / kwarg) トークン: 次のモジュール関数列の開始まで
        t = k + 1
        tail = []
        while t < hi and marker_of(toks[t]) is None and not (t + 1 < hi and pair_ok(toks[t], toks[t + 1])):
            tail.append(toks[t])
            t += 1
            if len(tail) > 700:
                break
        # docs の無い name-only 関数 (ui.previous/next 等) は stub 名辞書 + 窓内トークン一致で補完
        window = set(toks[last_end:k])
        extra = sorted(x for x in STUB_NAMES.get(m, ()) if x in window and x not in {a for a, _ in fns})
        if fns or m in ("ilmcp", "flpianoroll"):
            res.setdefault(m, []).append({"functions": fns, "name_only": extra, "tail": tail, "marker_tok": k})
        last_end = k + 1
    return res


def portable(path):
    """入力パスの FL_MAC_DIR / FL_WIN64_DIR 接頭辞を変数名表記に置換 (出力を環境に依存させない)。"""
    for var, base in (("FL_MAC_DIR", FL_MAC_DIR), ("FL_WIN64_DIR", FL_WIN64_DIR)):
        if path == base or path.startswith(base + "/"):
            return "${" + var + "}" + path[len(base):]
    return path


def main():
    path = sys.argv[1]
    arch = None
    if "--arch" in sys.argv:
        arch = sys.argv[sys.argv.index("--arch") + 1]
    b = open(path, "rb").read()
    sl = slices(b)
    key = arch or next(iter(sl))
    out = {"file": portable(path), "slice": key, "modules": extract(sl[key])}
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
