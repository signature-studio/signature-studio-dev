#!/usr/bin/env python3
"""shell (batch_lift.sh の work/batch/status.csv) と cpp (cpp_lift.sh の summary.csv) を 1 つの判定用 CSV に統合する。
列: block,name,role,units,lift_rc,defines,declares_unimpl,i256_trap,f80_funcs,emcc_c_rc,missing_define,seconds
  units = 固有閉包の関数数 (shell) / .pdata 関数数 (cpp)。 missing_define は engine_defs.py の監査 (ranges と final.ll の突合)。
行が欠けたブロックは出力せず exit 1 (judge に任せず、ここで止める)。 usage: mk_status.py <out.csv>
"""
import csv, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
import targets  # noqa: E402

HDR = 'block,name,role,units,lift_rc,defines,declares_unimpl,i256_trap,f80_funcs,emcc_c_rc,missing_define,seconds'.split(',')
rows, missing = [], []
batch = {}
bp = os.path.join(P, 'work', 'batch', 'status.csv')
if os.path.exists(bp):
    for r in list(csv.reader(open(bp)))[1:]:
        batch[r[0]] = r   # 再実行時は最後の行を採用


def run(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout.split()


for t in targets.load():
    b = t['block']
    if t['role'] == 'shell':
        r = batch.get(str(b))
        d = os.path.join(P, 'work', 'batch', str(b))
        if not r:
            missing.append(b)
            continue
        uni, i256 = run('python3', os.path.join(HERE, 'simd_stats.py'), os.path.join(d, 'p.simd.log'))
        rng = os.path.join(P, 'work', 'closure', 'block%05d.ranges.txt' % b)
        miss = subprocess.run(['python3', os.path.join(HERE, 'engine_defs.py'), rng, os.path.join(d, 'p.final.ll')],
                              capture_output=True, text=True).stdout.strip().split(',')[0]
        # r = block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds
        rows.append([b, t['name'], 'shell', r[2], r[4], r[5], uni, i256, r[7], r[8], miss, r[9]])
    elif t['role'] == 'cpp':
        sp = os.path.join(P, 'work', 'synth', 'cpp%d' % b, 'summary.csv')
        if not os.path.exists(sp):
            missing.append(b)
            continue
        s = open(sp).read().strip().split(',')
        # s = block,pdata_funcs,lift_rc,defines,f80,unimpl,i256,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,...
        rows.append([b, t['name'], 'cpp-' + t['kind'], s[1], s[2], s[3], s[5], s[6], s[4], s[7], s[11], s[10]])
if missing:
    print('mk_status: 結果行が無いブロック:', missing, file=sys.stderr)
    sys.exit(1)
csv.writer(open(sys.argv[1], 'w', newline='')).writerows([HDR] + rows)
print('mk_status: %d rows -> %s' % (len(rows), sys.argv[1]))
