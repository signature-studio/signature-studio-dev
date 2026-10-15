#!/usr/bin/env python3
"""[engine-local] x86_fp80 を含む関数の定義を宣言 (declare) に置換し、部分集合の IR を作る (到達性の測定専用)。
除外は関数単位。 判定は本体 (define 行から対応する } 行まで) に限る (後続の declare の x86_fp80 では除外しない)。
本体は捨てるため、出力 IR の挙動は元の関数に対して無効 (正しさは示さない)。
除外した関数は TSV (name / VA / reason) に記録する。
usage: engine_f80_stub.py IN.ll OUT.ll EXCL.tsv   (stderr: 除外件数)
"""
import re, sys
src = open(sys.argv[1]).read()
REASON = 'x86_fp80 を含む (f80 の libcall 不足 / 共有鎖 f80_lower 未決のため除外)'
rows = []
pieces = []
for chunk in re.split(r'\n(?=define )', src):
    if chunk.startswith('define'):
        lines = chunk.split('\n')
        end = lines.index('}')
        if 'x86_fp80' in '\n'.join(lines[:end + 1]):
            head = lines[0]
            assert head.endswith(' {'), head[:120]
            decl = re.sub(r'^define ', 'declare ', head[:-2]).replace(' dso_local', '')
            nm = re.search(r'@("[^"]*"|[\w.$]+)\(', decl)
            if not nm:
                sys.exit('engine_f80_stub: 関数名を解釈できない: %s' % decl[:120])
            name = nm.group(1)
            m = re.match(r'function_([0-9a-f]+)$', name)
            va = '0x%s' % m.group(1) if m else 'NA'
            rows.append((name, va))
            pieces.append('\n'.join([decl] + lines[end + 1:]))
            continue
    pieces.append(chunk)
open(sys.argv[2], 'w').write('\n'.join(pieces))
with open(sys.argv[3], 'w') as f:
    f.write('name\tva\treason\n')
    for name, va in rows:
        f.write('%s\t%s\t%s\n' % (name, va, REASON))
print('engine_f80_stub: excluded =', len(rows), file=sys.stderr)
