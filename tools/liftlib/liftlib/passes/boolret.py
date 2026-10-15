"""liftlib.passes.boolret — Win32 BOOL を返す import の `i1` 戻り値の `sext` を `zext` にする (LD-147 / #3180, D25)。

規則 (これだけ): `%V = call i1 @F(...)` で定義された同一関数内の `%V` について、
`%W = sext i1 %V to i64` の行を `%W = zext i1 %V to i64` に変える。
BOOL の TRUE (1) を rax に入れるとき、sext は 0xffffffffffffffff になり native (rax=1) と食い違う。

icmp・select・phi 等の i1 は対象外。入力は RetDec 産の .ll テキストで、変換は行単位の置換だけ。
RetDec chain (tools/ott/ott_build.sh・tools/m*) は変更しない。本番 chain への組込みは PM 判断 (D5) で、本 pass は測定用の IR を作る段で当てる。
"""
import re

CALL_I1 = re.compile(r'^\s*(%[\w.\-]+) = call i1 @')
SEXT_I1 = re.compile(r'^(\s*%[\w.\-]+ = )sext i1 (%[\w.\-]+) to i64(.*)$')


def apply(text):
    lines = text.split('\n')
    bool_vals = set()
    n = 0
    for i, line in enumerate(lines):
        if line.startswith('define '):
            bool_vals = set()
            continue
        if line.startswith('}'):
            bool_vals = set()
            continue
        m = CALL_I1.match(line)
        if m:
            bool_vals.add(m.group(1))
            continue
        m = SEXT_I1.match(line)
        if m and m.group(2) in bool_vals:
            lines[i] = m.group(1) + 'zext i1 ' + m.group(2) + ' to i64' + m.group(3)
            n += 1
    return '\n'.join(lines), n
