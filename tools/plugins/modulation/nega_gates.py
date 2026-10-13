#!/usr/bin/env python3
"""判定 (gate) 群の識別力を確認するネガティブコントロール。 実測の入力 (work/modulation/{status8.csv,facts.json}, work/batch) を
1 箇所だけ壊した合成入力を作り、 judge.py / matrix_check.py / ids_crosscheck.py / modulation_e2e.sh --judge-only が期待どおりの終了コードを返すかを見る。
  各ケース: 対照 (無改変) は exit 0、壊したものは期待コード (多くは 1、入力不正は 2) であること。 1 つでも外れたら exit 1。
前提: modulation_e2e.sh 実行済み。 usage: nega_gates.py   (modulation_nega.sh から呼ぶ)
"""
import csv, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
W = os.path.join(P, 'work', 'modulation')
N = os.path.join(W, 'nega')
shutil.rmtree(N, ignore_errors=True)
os.makedirs(N)
BLOCKS = '18978,18989,19007,19009,19066,19144,19265,19267'
B = '19007'   # Fruity Flanger (judge の対象 block; 最小の閉包)
C = '18989'   # Fruity Chorus (PLUGIN_MATRIX に batch 欄がある)
fails = []


def run(cmd, env=None):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(cmd, capture_output=True, text=True, env=e, cwd=P)
    return r.returncode, r.stdout + r.stderr


def case(tag, desc, cmd, want, env=None, absent=None, must=None):
    """must = 失敗の理由として出力に含まれるべき文字列 (狙った検査で落ちたことの確認)。 absent = 出力に含まれてはならない文字列。"""
    rc, out = run(cmd, env)
    ok = rc == want and (absent is None or absent not in out) and (must is None or must in out)
    if absent is not None:
        desc += ' (出力に %r を含まない)' % absent
    print('%-6s %-62s exit=%d (期待 %d)%s  %s' % (tag, desc, rc, want, '' if must is None else ' 理由=%r' % must, 'OK' if ok else 'NG'))
    if not ok:
        fails.append(tag)
        print(out[-600:])


hdr, *rows = list(csv.reader(open(os.path.join(W, 'status8.csv'))))
col = {h: i for i, h in enumerate(hdr)}


def write(name, hdr_, rows_):
    p = os.path.join(N, name)
    csv.writer(open(p, 'w')).writerows([hdr_] + rows_)
    return p


def mut(block, **kv):
    out = []
    for r in rows:
        r = list(r)
        if r[0] == block:
            for k, v in kv.items():
                r[col[k]] = str(v)
        out.append(r)
    return out


J = [sys.executable, os.path.join(HERE, 'judge.py')]
BD = os.path.join(P, 'work', 'batch')
base = ['--blocks', BLOCKS, '--batch-dir', BD]

print('--- NC3: judge.py (対象 block %s = Fruity Flanger を 1 箇所だけ壊す)' % B)
case('NC3-0', '対照: 無改変 status8.csv', J + [os.path.join(W, 'status8.csv')] + base, 0)
cf = int(next(r for r in rows if r[0] == B)[col['closure_funcs']])
nob = ['--blocks', BLOCKS]   # --batch-dir 無し (行の値だけで落ちることを見る)
for tag, desc, kv, why in [
    ('NC3-1', 'lift_rc=1', {'lift_rc': 1}, 'lift_rc=1'),
    ('NC3-2', 'f80_funcs=3', {'f80_funcs': 3}, 'f80_funcs=3'),
    ('NC3-3', 'emcc_c_rc=1', {'emcc_c_rc': 1}, 'emcc_c_rc=1'),
    ('NC3-4', 'declares_unimpl=5', {'declares_unimpl': 5}, 'declares_unimpl=5'),
    ('NC3-5', 'declares_unimpl=-1 (集計行なし)', {'declares_unimpl': -1}, 'declares_unimpl=-1'),
    ('NC3-6', 'defines=closure_funcs-1 (%d)' % (cf - 1), {'defines': cf - 1}, 'defines=%d != closure_funcs' % (cf - 1)),
    ('NC3-7', 'lift_rc が整数でない ("x")', {'lift_rc': 'x'}, '整数でない'),
]:
    case(tag, desc, J + [write(tag + '.csv', hdr, mut(B, **kv))] + nob, 1, must=why)
case('NC3-8', 'その block の行が無い', J + [write('nc3_8.csv', hdr, [r for r in rows if r[0] != B])] + nob, 1, must='行が無い')
case('NC3-9', '9 列に短縮された行', J + [write('nc3_9.csv', hdr, [r[:9] if r[0] == B else r for r in rows])] + nob, 1, must='列数が 10 でない')
case('NC3-10', '良い行の後ろに不合格行を追記 (最終行が採用される)',
     J + [write('nc3_10.csv', hdr, rows + [mut(B, emcc_c_rc=1)[[r[0] for r in rows].index(B)]])] + nob, 1, must='emcc_c_rc=1')
case('NC3-11', 'ヘッダ列名の改変 (入力不正 = 2)', J + [write('nc3_11.csv', hdr[:4] + ['LIFT_RC'] + hdr[5:], rows)] + nob, 2, must='ヘッダ')
case('NC3-12', 'status.csv が無い (入力不正 = 2)', J + [os.path.join(N, 'none.csv')] + nob, 2, must='No such file')
# 成果物側: batch-dir の p.o 欠落 / p.final.ll の define 数不一致 (対象 block だけ symlink + 欠落/改変にした複製)
for tag, desc in [('NC3-13', 'p.o が無い'), ('NC3-14', 'p.final.ll の define 数が行と違う')]:
    bd = os.path.join(N, 'batch_' + tag)
    for b in BLOCKS.split(','):
        os.makedirs(os.path.join(bd, b))
        for f in ('p.final.ll', 'p.o'):
            src = os.path.join(BD, b, f)
            if os.path.exists(src):
                os.symlink(src, os.path.join(bd, b, f))
    d = os.path.join(bd, B)
    if tag == 'NC3-13':
        os.remove(os.path.join(d, 'p.o'))
    else:
        os.remove(os.path.join(d, 'p.final.ll'))
        s = open(os.path.join(BD, B, 'p.final.ll'), errors='replace').read()
        i = s.index('\ndefine ')
        open(os.path.join(d, 'p.final.ll'), 'w').write(s[:i] + '\ndeclare ' + s[i + len('\ndefine '):])
    case(tag, desc, J + [os.path.join(W, 'status8.csv'), '--blocks', BLOCKS, '--batch-dir', bd], 1,
         must='p.o が無い' if tag == 'NC3-13' else 'p.final.ll の define 数')

print('--- NC4: matrix_check.py')
F = json.load(open(os.path.join(W, 'facts.json')))
MC = [sys.executable, os.path.join(HERE, 'matrix_check.py')]
st = os.path.join(W, 'status8.csv')
case('NC4-0', '対照: 無改変 facts.json / status8.csv', MC + ['--facts', os.path.join(W, 'facts.json'), '--status', st], 0)
f2 = json.loads(json.dumps(F)); f2['Fruity Flanger']['closure_funcs'] += 1
json.dump(f2, open(os.path.join(N, 'facts_funcs.json'), 'w'))
case('NC4-1', 'Fruity Flanger の closure_funcs を +1', MC + ['--facts', os.path.join(N, 'facts_funcs.json'), '--status', st], 1, must='MISMATCH Fruity Flanger closure_funcs')
f3 = json.loads(json.dumps(F)); f3['Hyper Chorus']['vcall'] += 1
json.dump(f3, open(os.path.join(N, 'facts_vcall.json'), 'w'))
case('NC4-2', 'Hyper Chorus の vcall を +1', MC + ['--facts', os.path.join(N, 'facts_vcall.json'), '--status', st], 1, must='MISMATCH Hyper Chorus vcalls')
case('NC4-3', 'Fruity Chorus (matrix に batch 欄あり) の lift_rc を 1 に',
     MC + ['--facts', os.path.join(W, 'facts.json'), '--status', write('nc4_3.csv', hdr, mut(C, lift_rc=1))], 1, must='MISMATCH Fruity Chorus batch.lift_rc')
f4 = json.loads(json.dumps(F)); del f4['Vintage Phaser']
json.dump(f4, open(os.path.join(N, 'facts_n7.json'), 'w'))
case('NC4-4', 'プラグインを 1 本落とす (7 本; 入力不正 = 2)', MC + ['--facts', os.path.join(N, 'facts_n7.json'), '--status', st], 2, must='7 != 8')

print('--- NC5: ids_crosscheck.py')
IC = [sys.executable, os.path.join(HERE, 'ids_crosscheck.py')]
case('NC5-0', '対照: 無改変 facts.json', IC + [os.path.join(W, 'facts.json')], 0)
f5 = json.loads(json.dumps(F))
nm = next(n for n, f in f5.items() if any(k != 'dyn' for k in f['host']['ids']))
k = next(k for k in f5[nm]['host']['ids'] if k != 'dyn')
f5[nm]['host']['ids'][k] += 1
json.dump(f5, open(os.path.join(N, 'facts_ids.json'), 'w'))
case('NC5-1', '%s の taint 側 ID %s の件数を +1' % (nm, k), IC + [os.path.join(N, 'facts_ids.json')], 1, must='NG')

print('--- NC6: modulation_e2e.sh --judge-only (実スクリプトの終了コードが judge に従うか)')
E = ['bash', os.path.join(HERE, 'modulation_e2e.sh'), '--judge-only']
real = os.path.join(P, 'work', 'batch', 'status.csv')
bh, *brows = list(csv.reader(open(real)))
poison = [r for r in brows if r[0] != B] + [mut(B, emcc_c_rc=1)[[r[0] for r in rows].index(B)]]
case('NC6-0', '対照: 実 status.csv', E, 0, env={'STATUS_CSV': real}, must='judge-only: PASS')
case('NC6-1', '不合格行 (Fruity Flanger emcc_c_rc=1) を最終行に持つ status.csv', E, 1,
     env={'STATUS_CSV': write('nc6.csv', bh, poison)}, absent='[modulation_e2e] OK', must='judge: FAIL 7/8')

print('nega_gates: %s (%d 件不一致)' % ('FAIL' if fails else 'OK', len(fails)))
sys.exit(1 if fails else 0)
