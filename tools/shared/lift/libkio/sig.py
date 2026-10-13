#!/usr/bin/env python3
"""libkio 関数の引数種別。マングル名を c++filt で復号し、引数ごとの kind を返す。
  i64 = long / ref64 = long const& / f32 = float / f64 = double / f64ref = double const&
  buf = unsigned char* / str16 = unsigned short const* / str32 = wchar_t* / str8 = char const*
戻り値型は復号名に現れないため funcs.txt の 4 列目に置く (diff_test.py が読む)。"""
import subprocess
KIND = {"long": "i64", "long const&": "ref64", "float": "f32", "double": "f64", "double const&": "f64ref",
        "unsigned char*": "buf", "unsigned short const*": "str16", "wchar_t*": "str32", "wchar_t const*": "str32",
        "char const*": "str8"}
POINTER = ("buf", "str16", "str32", "str8")
def params(mangled):
    """mangled (__Z... 形式、先頭 _ は 1 つでも 2 つでもよい) → kind のリスト。復号できない名前は None。"""
    m = mangled[1:] if mangled.startswith("__Z") else mangled
    d = subprocess.run(["c++filt", m], capture_output=True, text=True, check=True).stdout.strip()
    if "(" not in d: return None
    inner = d[d.index("(") + 1: d.rindex(")")].strip()
    if not inner: return []
    try: return [KIND[p.strip()] for p in inner.split(",")]
    except KeyError: return None
def idiv_fns(dsm):
    """DSM (objdump 形式) で idiv を含む関数名の集合。"""
    import re
    out = set(); cur = None
    for line in open(dsm, errors="replace"):
        m = re.match(r"; function: (\S+) at ", line)
        if m: cur = m.group(1); continue
        if cur and re.match(r"0x[0-9a-f]+:", line) and re.search(r"\tidiv\b", line): out.add(cur)
    return out
