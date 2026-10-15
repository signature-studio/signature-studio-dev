"""LD-181 (#3864): irtool.instrument の entry 記録が IR の i128 引数を下位 64bit で記録すること (旧版は 0 と記録していた)。失敗で非 0 終了。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ldlib import irtool  # noqa: E402

SRC = '''define i64 @function_653c80(i64 %a, i64 %b, i128 %c) {
entry:
  ret i64 0
}
define i64 @function_40c660(i128 %arg0) {
entry:
  ret i64 0
}
'''


def main():
    d = tempfile.mkdtemp()
    src = os.path.join(d, 'in.ll')
    out = os.path.join(d, 'out.ll')
    with open(src, 'w') as f:
        f.write(SRC)
    assert irtool.instrument(src, out) == 2
    text = open(out).read()
    assert 'trunc i128 %c to i64' in text, text
    assert 'trunc i128 %arg0 to i64' in text, text
    lines = [ln for ln in text.splitlines() if 'call void @ld_trace' in ln]
    assert len(lines) == 2, lines
    assert 'i64 %ld.2, i64 0' in lines[0] and 'i64 %a, i64 %b, i64 %ld.2,' in lines[0], lines[0]
    assert 'i64 %ld.0, i64 0' in lines[1], lines[1]
    print('PASS test_ld181_i128_entry')


if __name__ == '__main__':
    main()
