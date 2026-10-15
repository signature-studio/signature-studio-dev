"""#4184 (LD-200): by-value の 2 要素 scalar struct (%tagPOINT) を含む import (WindowFromPoint) が stub skip されず、要素ごとの引数に展開されることの単体テスト。失敗で非 0 終了。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ldlib import irtool  # noqa: E402

IR = """%tagPOINT = type { i32, i32 }
%tagRECT = type { i32, i32, i32, i32 }
%tagMSG = type { ptr, i32, i32, i32, i32, %tagPOINT }
declare ptr @WindowFromPoint(%tagPOINT) local_unnamed_addr
declare i32 @ScrollThing(ptr, %tagRECT) local_unnamed_addr
declare void @Defined(i64) local_unnamed_addr
define weak ptr @function_4256c0(%tagPOINT %Point) local_unnamed_addr {
  %0 = call ptr @WindowFromPoint(%tagPOINT %Point)
  ret ptr %0
}
"""


def main():
    with tempfile.NamedTemporaryFile('w', suffix='.ll', delete=False) as f:
        f.write(IR)
        path = f.name
    try:
        assert irtool.struct_table(path) == {'%tagPOINT': ['i32', 'i32']}, irtool.struct_table(path)
        src, names, skipped = irtool.gen_stubs(path, {'Defined'})
        assert 'WindowFromPoint' in names and 'WindowFromPoint' not in skipped, (names, skipped)
        line = [ln for ln in src.splitlines() if ln.startswith('void* WindowFromPoint(')]
        assert line and '(unsigned a0, unsigned a1)' in line[0] and '(u64)a0, (u64)a1' in line[0], line
        assert irtool.gen_stubs.widths['WindowFromPoint'] == [32, 32], irtool.gen_stubs.widths
        assert 'ScrollThing' in skipped, skipped
        assert 'Defined' not in names, names
    finally:
        os.unlink(path)
    print('test_ld200_struct_stub: OK')


if __name__ == '__main__':
    main()
