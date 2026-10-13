#!/usr/bin/env python3
"""judge の識別力を、実測 status.csv を 1 箇所だけ壊した合成 CSV で確認する (synth_e2e.sh --judge-only 経由 = 配線ごと)。
各ケースで「終了コード」と「`[synth_e2e] OK` が出ないこと」を検査する。 期待と食い違えば exit 1。
前提: synth_e2e.sh を実行済み (work/synth/status.csv)。 usage: nega_judge.py
"""
import csv, json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
import judge as J  # noqa: E402

rows = list(csv.DictReader(open(os.path.join(P, 'work', 'synth', 'status.csv'))))
hdr = list(rows[0].keys())
known = json.load(open(os.path.join(HERE, 'known.json')))
want = [r['block'] for r in rows]
verdict = {b: k for b, _, k, _ in J.judge(rows, known, want)[0]}
passrow = next(r for r in rows if verdict[r['block']] == 'PASS')
knownrow = next((r for r in rows if verdict[r['block']] == 'KNOWN'), None)
T = tempfile.mkdtemp(dir=os.environ.get('RUNNER_TEMP', None))
fails = 0


def run(label, mut, expect_rc, kind, kn=None, extra=None):
    """mut: rows -> rows。 kn: known.json 相当の dict (既定は実物)。"""
    global fails
    rs = mut([dict(r) for r in rows])
    cp = os.path.join(T, 'status.csv')
    with open(cp, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=hdr)
        w.writeheader()
        w.writerows(rs)
    kp = os.path.join(T, 'known.json')
    with open(kp, 'w') as fh:
        json.dump(known if kn is None else kn, fh)
    p = subprocess.run(['bash', os.path.join(HERE, 'synth_e2e.sh'), '--judge-only', cp] if not extra else extra(cp),
                       capture_output=True, text=True, env=dict(os.environ, SYNTH_KNOWN=kp))
    ok_line = '[synth_e2e] OK' in p.stdout
    last = [l for l in p.stdout.splitlines() if l.startswith('judge')][-1:]
    # 終了コードだけでなく、judge の集計行に期待した種別が立っていること (別の理由で落ちた偽陽性を排除)
    m = re.search(r'%s (\d+)' % re.escape(kind), last[0]) if (last and kind) else None
    kind_ok = (m is not None and int(m.group(1)) > 0) if kind else (last != [] and not re.search(r'(NEW-FAIL|FIXED|MISSING) [1-9]', last[0]))
    good = p.returncode == expect_rc and ok_line == (expect_rc == 0) and kind_ok
    fails += not good
    print('%-4s %-52s rc=%d (期待 %d) OKline=%s  %s' % ('ok' if good else 'NG', label, p.returncode, expect_rc, ok_line, last[0] if last else ''))


def setcol(b, **kv):
    def f(rs):
        for r in rs:
            if r['block'] == b:
                r.update({k: str(v) for k, v in kv.items()})
        return rs
    return f


pb = passrow['block']
print('対象: PASS 行 = %s %s / KNOWN 行 = %s' % (pb, passrow['name'], knownrow and (knownrow['block'], knownrow['name'])))
run('control: 実測 status.csv + 実 known.json', lambda rs: rs, 0, None)
run('PASS 行の emcc_c_rc=1', setcol(pb, emcc_c_rc=1), 1, 'NEW-FAIL')
run('PASS 行の lift_rc=1 かつ f80_funcs=3', setcol(pb, lift_rc=1, f80_funcs=3), 1, 'NEW-FAIL')
run('PASS 行の declares_unimpl=5', setcol(pb, declares_unimpl=5), 1, 'NEW-FAIL')
run('PASS 行の i256_trap=2', setcol(pb, i256_trap=2), 1, 'NEW-FAIL')
run('PASS 行の missing_define=1', setcol(pb, missing_define=1), 1, 'NEW-FAIL')
run('PASS 行の defines=0', setcol(pb, defines=0), 1, 'NEW-FAIL')
run('PASS 行の declares_unimpl=-1 (ログ欠落の印)', setcol(pb, declares_unimpl=-1), 1, 'NEW-FAIL')
run('PASS 行を削除 (行欠落)', lambda rs: [r for r in rs if r['block'] != pb], 1, 'MISSING')
run('PASS 行を複製 (重複)', lambda rs: rs + [dict(passrow)], 1, 'MISSING')
run('PASS 行の値が数値でない', setcol(pb, emcc_c_rc='x'), 1, 'MISSING')
k2 = dict(known)
k2[pb] = {'fails': ['declares_unimpl'], 'ref': '#0'}
run('FIXED: known にあるのに解消している行 (PASS 行に疑似登録)', lambda rs: rs, 1, 'FIXED', kn=k2)
k3 = {b: dict(v) for b, v in known.items()}
if knownrow:
    k3[knownrow['block']].pop('ref')
else:
    k3[pb] = {'fails': ['declares_unimpl']}
run('known.json の KNOWN 行から ref を欠落させる', lambda rs: rs, 1, None, kn=k3)
if knownrow:
    kb = knownrow['block']
    run('KNOWN 行に未登録の不合格 (f80_funcs=9) を追加', lambda rs: setcol(kb, f80_funcs=9)(rs), 1, 'NEW-FAIL')
    k4 = {b: v for b, v in known.items() if b != kb}
    run('KNOWN 行の登録を known.json から外す', lambda rs: rs, 1, 'NEW-FAIL', kn=k4)
    run('judge.py --strict (KNOWN があれば不合格)', lambda rs: rs, 1, 'NEW-FAIL',
        extra=lambda cp: ['python3', os.path.join(HERE, 'judge.py'), cp, '--strict', '--want'] + want)
else:
    print('NG   KNOWN 行が無いため KNOWN 系のケースを実行できない')
    fails += 1
print('nega_judge: %s' % ('全ケース期待通り' if not fails else '%d ケースが期待と不一致' % fails))
sys.exit(1 if fails else 0)
