#!/usr/bin/env python3
"""fa9_check.py — FA-9 の実測集計と判定 (run_fa9.sh から呼ぶ)。
  mkpert <in.txt> <out.txt> : 各シナリオの初回呼出 (先頭 W ブロック) の M+0x9dc4 (初期 Mid Air) を 0.9 に強制した摂動シナリオを作る
                              (元値はシナリオごとに異なる。先頭 W ブロックに 1 件だけ在ることを assert)
  check  <base.out> <base.err> <alt.out> <alt.err> <pert_base.out> <pert.out>
         exit 0 = 全ゲート通過 / 1 = 不合格 (ゲートは下記 GATE 行)。
  GATE: (a) base: 8 シナリオ完走・ERR 0・ca1480 呼出 72 (=9/シナリオ)・全呼出が map 経路 (eq=1)・map 検索 found=0・da6c00 呼出 0
        (b) ネガコン alt (静的分岐強制): 8/8 が ERR (ERR 0 なら probe は静的分岐を検出できていない)
        (c) ネガコン pert: 摂動が状態ダンプに現れる (差分 >0) — 現れなければ盲点検査が無効
  観測のみ (判定しない): pert の L/R 出力差分 (= 0x157 変化が Filter 出力に届くか)。"""
import re, struct, sys

def mkpert(src, dst):
    # 行形式: sidx ncalls vcap nW {rg off val}*nW ... (rg=1 は M 領域)。先頭 W ブロック = 初回呼出の入力
    new = '%08x' % struct.unpack('<I', struct.pack('<f', 0.9))[0]
    out = []
    for ln in open(src):
        t = ln.split()
        nw = int(t[3])
        hits = [j for j in range(nw) if t[4 + 3 * j] == '1' and t[5 + 3 * j] == '9dc4']
        assert len(hits) == 1, ('先頭 W ブロックの M+0x9dc4 が 1 件でない', t[0], hits)
        t[6 + 3 * hits[0]] = new
        out.append(' '.join(t))
    open(dst, 'w').write('\n'.join(out) + '\n')
    print('pert: 初回呼出の M+0x9dc4 (初期 Mid Air) を 0x%s (0.9f) に強制 (%d scenarios)' % (new, len(out)))

def calls_of(path):
    return [ln for ln in open(path) if ln.startswith('FA9CA')], [ln for ln in open(path) if ln.startswith('FA9DA')]

def lr_tail(seg):
    t = seg.split(' ')
    return t[-2:]

def check(base_out, base_err, alt_out, alt_err, pert_base_out, pert_out):
    fails = []
    bo = open(base_out).read().split('\n')[:8]
    ca, da = calls_of(base_err)
    ca_lines = [l for l in ca]
    nerr = sum(1 for ln in bo if '|ERR' in ln)
    paths = {re.search(r'path=(\S+)', l).group(1) for l in ca_lines}
    eqs = {re.search(r'eq=(\d)', l).group(1) for l in ca_lines}
    founds = {re.search(r'found=(\d)', l).group(1) for l in ca_lines}
    print('(a) base  : scenarios=%d ERR=%d ca1480=%d (per scen %s) path=%s eq=%s found=%s da6c00=%d' % (
        len([l for l in bo if l.startswith('S')]), nerr, len(ca_lines),
        sorted({sum(1 for l in ca_lines if ('FA9CA S%d ' % s) in l) for s in range(900, 908)}), sorted(paths), sorted(eqs), sorted(founds), len(da)))
    if not (len([l for l in bo if l.startswith('S')]) == 8 and nerr == 0 and len(ca_lines) == 72 and paths == {'map'} and eqs == {'1'} and founds == {'0'} and len(da) == 0):
        fails.append('(a) base 不一致')
    ao = open(alt_out).read().split('\n')[:8]
    aca, _ = calls_of(alt_err)
    aerr = sum(1 for ln in ao if '|ERR' in ln)
    apaths = sorted({re.search(r'path=(\S+)', l).group(1) for l in aca})
    print('(b) alt   : ERR=%d/8 ca1480=%d path=%s (静的分岐強制ネガコン)' % (aerr, len(aca), apaths))
    if aerr != 8 or apaths != ['static']:
        fails.append('(b) 静的分岐ネガコンが ERR/static にならない')
    pb = open(pert_base_out).read().split('\n')[:8]
    pp = open(pert_out).read().split('\n')[:8]
    dtok = same_lr = diff_lr = 0
    for b, p in zip(pb, pp):
        for sb, sp in zip(b.split(' |')[1:], p.split(' |')[1:]):
            if lr_tail(sb) == lr_tail(sp): same_lr += 1
            else: diff_lr += 1
        dtok += sum(1 for x, y in zip(b.split(' '), p.split(' ')) if x != y)
    print('(c) pert  : 状態ダンプ差分トークン=%d / L/R 出力 同一 %d 呼出 / 差分 %d 呼出 (観測のみ)' % (dtok, same_lr, diff_lr))
    if dtok == 0:
        fails.append('(c) 摂動が状態に届いていない (盲点検査が無効)')
    print('GATE: %s' % ('PASS' if not fails else 'FAIL: ' + '; '.join(fails)))
    return 0 if not fails else 1

if __name__ == '__main__':
    if sys.argv[1] == 'mkpert':
        mkpert(sys.argv[2], sys.argv[3]); sys.exit(0)
    if sys.argv[1] == 'check':
        sys.exit(check(*sys.argv[2:8]))
    sys.exit(2)
