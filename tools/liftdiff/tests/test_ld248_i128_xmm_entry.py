"""LD-248 (#4975): irtool.instrument は機械語入口型が double の i128 引数の下位 64bit を x 側 (xmm) に記録すること。
entry_types を渡さない既定 (LD-181) は整数側だけに記録する。失敗で非 0 終了。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ldlib import cases, irtool  # noqa: E402

SRC = '''define i64 @function_40c660(i128 %arg0) {
entry:
  ret i64 0
}
define i64 @function_653c80(i64 %a, i64 %b, i128 %c) {
entry:
  ret i64 0
}
'''


def run(entry_types):
    d = tempfile.mkdtemp()
    src = os.path.join(d, 'in.ll')
    out = os.path.join(d, 'out.ll')
    with open(src, 'w') as f:
        f.write(SRC)
    assert irtool.instrument(src, out, entry_types=entry_types) == 2
    return open(out).read()


def trace_line(text, va):
    return [ln for ln in text.splitlines() if 'call void @ld_trace' in ln and ('i64 %d,' % va) in ln][0]


def main():
    assert cases.MACHINE_ENTRY[0x40c660] == ['double']
    text = run(cases.MACHINE_ENTRY)
    line = trace_line(text, 0x40c660)
    assert line.rstrip().endswith('i64 %ld.0, i64 0, i64 0, i64 0)'), line
    line = trace_line(text, 0x653c80)
    assert line.rstrip().endswith('i64 0, i64 0, i64 0, i64 0)'), line
    text = run(None)
    line = trace_line(text, 0x40c660)
    assert line.rstrip().endswith('i64 0, i64 0, i64 0, i64 0)'), line
    print('PASS test_ld248_i128_xmm_entry')


if __name__ == '__main__':
    main()
