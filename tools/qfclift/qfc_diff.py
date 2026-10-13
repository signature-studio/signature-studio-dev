#!/usr/bin/env python3
"""qfc_diff.py — QuickFontCache_x64.dll 関数単位 spot 差分: native (実機械語直実行) vs wasm (x64c lift 産物)。

対象 = 本チケットで x64c に新規実装した SSSE3 命令 (pshufb / pmulhrsw / phaddw) を含む 2 関数
(0x57de50 / 0x57e2a0 — 3byte→16bit 画素ブレンド)。比較 = dst バッファ全バイト + rax + xmm0。
判定: 1 case でも不一致 / 片側 fault なら exit 1 (gate は exit code で落ちる)。
usage: qfc_diff.py --cjs work/lift/qfcl.cjs --pe <PE> [--expect-fail]
  --expect-fail: ネガコン用。不一致が検出された (=gate が FAIL した) 時だけ exit 0。"""
import argparse, json, os, random, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC, DST, PRM = 0x20004000, 0x20008000, 0x2000c000
MASK1 = 0x5d9f8c       # .bss: InitDll が実行時に書く pshufb mask (file 上は 0) → 両側へ明示敷設

FUNCS = [(0x57de50, 'blend_57de50'), (0x57e2a0, 'blend_57e2a0')]


def mk_cases(seed=1):
    rnd = random.Random(seed)
    cases = []
    for fn, nm in FUNCS:
        for ci, (w, rows, sstr, dstr) in enumerate([(0, 1, 0x40, 0x40), (1, 1, 0x40, 0x40), (2, 1, 0x40, 0x40),
                                                    (5, 2, 0x40, 0x80), (8, 3, 0x50, 0x80), (13, 2, 0x60, 0x100)]):
            src = bytes(rnd.randrange(256) for _ in range(0x1000))
            dst = bytes(rnd.randrange(256) for _ in range(0x1000))
            mask = bytes([rnd.choice([0x80, 0x80 | rnd.randrange(16)] + [rnd.randrange(16)] * 3) for _ in range(16)]) if ci % 2 else \
                bytes([0, 1, 0x80, 0x80, 4, 5, 0x80, 0x80, 8, 9, 0x80, 0x80, 12, 13, 0x80, 0x80])
            prm = (rnd.getrandbits(64)).to_bytes(8, 'little') + rnd.randrange(1 << 15).to_bytes(4, 'little') + \
                rnd.randrange(1 << 15).to_bytes(4, 'little')
            cases.append({'id': '%s:c%d(w=%d,rows=%d)' % (nm, ci, w, rows), 'fn': fn,
                          'gpr': [SRC, DST, w, rows], 'stk': [sstr, dstr, PRM],
                          'writes': [{'va': '%x' % SRC, 'hex': src.hex()}, {'va': '%x' % DST, 'hex': dst.hex()},
                                     {'va': '%x' % PRM, 'hex': prm.hex()}, {'va': '%x' % MASK1, 'hex': mask.hex()}],
                          'cmp': [{'va': '%x' % DST, 'len': 0x1000}]})
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cjs', default=os.path.join(HERE, 'work', 'lift', 'qfcl.cjs'))
    ap.add_argument('--pe', required=True)
    ap.add_argument('--out', default=os.path.join(HERE, 'work', 'diff'))
    ap.add_argument('--expect-fail', action='store_true')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cases = mk_cases()
    cj = os.path.join(a.out, 'cases.json'); json.dump(cases, open(cj, 'w'))
    with open(os.path.join(a.out, 'nat_cases.txt'), 'w') as fh:
        for c in cases:
            stk = c['stk']
            fh.write('CASE %s %x %s %d %s %d %s %d %s\n' % (
                c['id'].replace(' ', ''), c['fn'], ' '.join(hex(g) for g in c['gpr']), len(stk), ' '.join(hex(s) for s in stk),
                len(c['writes']), ' '.join('%s %s' % (w['va'], w['hex']) for w in c['writes']),
                len(c['cmp']), ' '.join('%s %d' % (r['va'], r['len']) for r in c['cmp'])))
    env = dict(os.environ, QFC_CASES=cj, QFC_CJS=os.path.abspath(a.cjs), QFC_OUT=os.path.join(a.out, 'wasm.json'))
    r = subprocess.run(['node', os.path.join(HERE, 'qfc_wasm_runner.mjs')], env=env, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr[-2000:]); sys.exit('wasm runner failed')
    drv = os.path.join(HERE, 'work', 'qfc_natdrv')
    rn = subprocess.run(['setarch', 'x86_64', '-R', drv, os.path.join(a.out, 'nat_cases.txt'), os.path.join(a.out, 'nat.jsonl'), a.pe],
                        capture_output=True, text=True)
    if rn.returncode != 0:
        print(rn.stdout[-1000:], rn.stderr[-1000:]); sys.exit('native driver failed rc=%d' % rn.returncode)
    wres = {c['id']: c for c in json.load(open(env['QFC_OUT']))}
    nres = {}
    for line in open(os.path.join(a.out, 'nat.jsonl')):
        j = json.loads(line); nres[j['id']] = j
    equal = 0; bad = []
    for c in cases:
        cid = c['id'].replace(' ', '')
        w = wres[c['id']]; n = nres.get(cid)
        ok = n is not None and n['status'] == 'ok' and w['status'] == 'ok' and n['mem'] == w['mem'] and n['rax'] == w['rax'] and n['x0'] == w['x0']
        if ok: equal += 1
        else:
            nd = sum(1 for x, y in zip(bytes.fromhex(n['mem'][0]), bytes.fromhex(w['mem'][0])) if x != y) if n and w['mem'] and n['status'] == 'ok' and w['status'] == 'ok' else -1
            bad.append((c['id'], n and n['status'], w['status'], nd))
    # 非自明性: native が dst を実際に書き換えている (全 case で dst != 初期値) ことを別途確認 (w>0 の case)
    changed = sum(1 for c in cases if c['gpr'][2] > 0 and nres[c['id'].replace(' ', '')]['mem'][0] != c['writes'][1]['hex'])
    need = sum(1 for c in cases if c['gpr'][2] > 0)
    print('[qfc_diff] cases %d equal %d mismatch %d; native dst changed %d/%d (w>0 case)' % (len(cases), equal, len(bad), changed, need))
    for b in bad: print('  MISMATCH', b)
    failed = bool(bad) or changed != need
    if a.expect_fail:
        print('[qfc_diff] negative control: %s' % ('FAIL detected (OK)' if failed else 'NOT detected (BAD)'))
        sys.exit(0 if failed else 1)
    print('[qfc_diff] %s' % ('FAIL' if failed else 'PASS'))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
