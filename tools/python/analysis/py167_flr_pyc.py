#!/usr/bin/env python3.12
"""同梱 Chord progression の pyc で `flr` と `flrack` の参照を数える (PY-167 #3181 の解析補助)。

  python3.12 analysis/py167_flr_pyc.py <FL-win64 展開先>/extracted

同梱 pyc は magic 3531 (CPython 3.12 の bytecode) のため、Python 3.12 でしか命令を正しく読めない。
出力: (1) `flr` を import する元 (2) `flr = ...` の定義 (3) `flr` に続く属性読取の件数
(4) `flrack` に続く属性読取の件数 (5) `flrack.flr` の属性読取の件数
(6) 全 code object の `LOAD_ATTR flr`・`STORE_ATTR flr` の件数 (属性として flr を読む・書く箇所の総数)。
"""
import collections
import dis
import glob
import marshal
import os
import sys
import types


def walk(code):
    yield code
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield from walk(k)


def main():
    if sys.version_info[:2] != (3, 12):
        sys.exit("python3.12 で実行すること (pyc は 3.12 bytecode)")
    base = sys.argv[1]
    imp_from = collections.Counter()
    flr_def = []
    flr_attr = collections.Counter()
    flrack_attr = collections.Counter()
    pyc_n = 0
    attr_flr = collections.Counter()
    for path in sorted(glob.glob(os.path.join(base, "block*_DATA.bin"))):
        with open(path, "rb") as f:
            head = f.read()
        if head[:4] != b"\xcb\r\r\n":
            continue
        code = marshal.loads(head[16:])
        if not isinstance(code, types.CodeType):
            continue
        pyc_n += 1
        name = os.path.basename(path)
        for c in walk(code):
            ins = list(dis.get_instructions(c))
            for i, x in enumerate(ins):
                nxt = ins[i + 1] if i + 1 < len(ins) else None
                if x.opname in ("LOAD_ATTR", "STORE_ATTR") and x.argval == "flr":
                    attr_flr[x.opname] += 1
                if x.opname == "IMPORT_FROM" and x.argval == "flr":
                    j = i - 1
                    while j >= 0 and ins[j].opname != "IMPORT_NAME":
                        j -= 1
                    src = ins[j].argval if j >= 0 else None
                    imp_from[(name, c.co_filename, src)] += 1
                if x.opname == "STORE_GLOBAL" and x.argval == "flr":
                    flr_def.append((name, c.co_filename, c.co_qualname, x.positions.lineno))
                if x.opname in ("LOAD_GLOBAL", "LOAD_NAME") and x.argval == "flr" and nxt is not None:
                    flr_attr[nxt.argval if nxt.opname == "LOAD_ATTR" else nxt.opname] += 1
                if x.opname in ("LOAD_GLOBAL", "LOAD_NAME") and x.argval == "flrack" and nxt is not None:
                    flrack_attr[nxt.argval if nxt.opname == "LOAD_ATTR" else nxt.opname] += 1
    print("# (1) `from <module> import flr` の元 (ファイル・関数・import 元)")
    for (blk, fn, src), n in sorted(imp_from.items()):
        print(f"  {blk} {fn}: from {src} import flr ({n})")
    print("# (2) `flr = ...` の定義 (STORE_GLOBAL)")
    for blk, fn, qn, line in flr_def:
        print(f"  {blk} {fn}:{line} {qn}")
    print("# (3) LOAD_GLOBAL/LOAD_NAME flr に続く属性読取 (件数)")
    for k, n in flr_attr.most_common():
        print(f"  {k}: {n}")
    print("# (4) LOAD_GLOBAL/LOAD_NAME flrack に続く属性読取 (件数・rack.py では C モジュール、他は import rack as flrack)")
    for k, n in flrack_attr.most_common():
        print(f"  {k}: {n}")
    print(f"# (5) flrack の属性として flr を読む箇所: {flrack_attr.get('flr', 0)} 件")
    print(f"# (6) 全 code object (pyc {pyc_n} 件) の属性 flr: LOAD_ATTR {attr_flr['LOAD_ATTR']} 件・STORE_ATTR {attr_flr['STORE_ATTR']} 件")


if __name__ == "__main__":
    main()
