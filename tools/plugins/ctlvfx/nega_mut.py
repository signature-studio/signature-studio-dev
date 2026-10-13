#!/usr/bin/env python3
"""ctlvfx_nega.sh 用: 実測の status.csv / facts.json / PLUGIN_MATRIX.json を 1 箇所だけ壊したコピーを作る。
  csv-pass   IN OUT                     全行を合格値にそろえる (対照用の基準。 実測が不合格を含んでいても NC の基準にできる)
  csv-set    IN OUT BLOCK FIELD VALUE   status.csv の BLOCK 行の FIELD を VALUE にする
  csv-drop   IN OUT BLOCK               BLOCK 行を消す
  csv-append IN OUT 'a,b,...'           行を追記する
  csv-header IN OUT                     header の先頭列名を壊す
  csv-late-fix IN OUT BLOCK             BLOCK 行の直前に不合格行 (emcc_c_rc=1) を足す (最後の行が合格 = 再実行で直った形)
  facts-bump IN OUT NAME KEY            facts[NAME][KEY] を +1 (KEY は closure_funcs 等)
  facts-bump-id IN OUT                  最初に即値 ID を持つ plugin の host.ids の最初の即値 ID の件数を +1 (stdout: その plugin 名)
  facts-drop IN OUT NAME                facts から NAME を消す
  matrix-tier IN OUT NAME               PLUGIN_MATRIX.json の NAME の tier を別の値にする
  ll-rename  IN OUT                     final.ll の最初の `define @function_<VA>` を別名にする (関数の脱落を模す)
  ll-outside IN OUT                     final.ll に閉包外の `define @function_deadbeef` を足す (混入を模す)
"""
import csv, json, re, sys

op, src, dst = sys.argv[1:4]
a = sys.argv[4:]
if op.startswith('csv-'):
    rows = list(csv.reader(open(src)))
    hdr = rows[0]
    if op == 'csv-pass':
        for r in rows[1:]:
            for k in ('lift_rc', 'emcc_c_rc', 'f80_funcs', 'declares_unimpl'):
                r[hdr.index(k)] = '0'
            r[hdr.index('defines')] = str(max(int(r[hdr.index('defines')]), int(r[hdr.index('closure_funcs')])))
    elif op == 'csv-set':
        for r in rows[1:]:
            if r[0] == a[0]:
                r[hdr.index(a[1])] = a[2]
    elif op == 'csv-drop':
        rows = [rows[0]] + [r for r in rows[1:] if r[0] != a[0]]
    elif op == 'csv-append':
        rows.append(a[0].split(','))
    elif op == 'csv-header':
        rows[0][0] = 'blk'
    elif op == 'csv-late-fix':
        i = next(i for i, r in enumerate(rows) if i and r[0] == a[0])
        bad = list(rows[i]); bad[hdr.index('emcc_c_rc')] = '1'
        rows.insert(i, bad)
    csv.writer(open(dst, 'w')).writerows(rows)
elif op.startswith('ll-'):
    t = open(src).read()
    if op == 'll-rename':
        t = re.sub(r'^(define [^@]*@)function_([0-9a-f]+)\b', r'\1renamed_\2', t, count=1, flags=re.M)
    else:
        t += '\ndefine void @function_deadbeef() {\n  ret void\n}\n'
    open(dst, 'w').write(t)
else:
    d = json.load(open(src))
    if op == 'facts-bump':
        d[a[0]][a[1]] += 1
    elif op == 'facts-bump-id':
        for name, f in d.items():
            ks = [k for k in f['host']['ids'] if k != 'dyn']
            if ks:
                f['host']['ids'][ks[0]] += 1
                print(name, 'ID', ks[0])
                break
    elif op == 'facts-drop':
        del d[a[0]]
    elif op == 'matrix-tier':
        for p in d['plugins']:
            if p['name'] == a[0]:
                p['tier'] = 'T9'
    json.dump(d, open(dst, 'w'))
