#!/usr/bin/env python3
"""chain_chunk_negctl.py [WORK_DIR] — chain_chunk_check.py のネガティブコントロール (#2708 / ICALL-83)。
Image 読込後に pdata_chained を壊し、chained_at_E が変わることを示す。検査本体は変えない。
none: 無加工 (期待 12) / empty: pdata_chained を空にする (期待 0) / drop1: 断片 0x180da4081 を外す (期待 11・0x180da4030 が消える)。"""
import sys, os, io, json, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chain_chunk_check as C
A = C.A


def run(mode, d):
    base = A.Image

    class Broken(base):
        def __init__(self, path):
            super().__init__(path)
            if mode == 'empty':
                self.pdata_chained = set()
            elif mode == 'drop1':
                self.pdata_chained.discard(0x180da4081)

    A.Image = Broken
    saved = sys.argv
    sys.argv = [saved[0], d]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            C.main()
    finally:
        A.Image = base
        sys.argv = saved
    return json.loads(buf.getvalue())


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'work', 'rt_freshair-core')
    for mode in ('none', 'empty', 'drop1'):
        r = run(mode, d)
        vas = [f['va'] for f in r['funcs']]
        print(f"{mode}\tclosure {r['closure']}\tchained_at_E {r['chained_at_E']}\t0x180da4030 {'in' if '0x180da4030' in vas else 'absent'}")


if __name__ == '__main__':
    main()
