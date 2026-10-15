#!/usr/bin/env python3
"""ld270_bfs_frame.py — #5435 (LD-270) spill 宛 `128f9e0` 12 site の到達経路 (BFS 親) と frame F の照合。

1. 機械語 CFG (ldmach_img の逆アセンブル) を入口 128f9e0 から BFS し、12 site の BFS 親経路を出す。
   経路上の機械 leader のうち、lift 段 IR (boot3.lift.ll) に label が無いものを数える。
2. 同じ BFS を IR CFG (boot3.lift.ll の br / switch 先) で行い、12 site の含まれる IR block に到達するかを見る。
3. frame F を prologue (push 数 * 8 + sub rsp, imm) から独立に算出し、ld120 の F=2088 と照合する。
   各 site の stack_var_-(F-d) が IR の alloca / 本体に在るかも出す。
出力: results/ld270_bfs_128f9e0.tsv
使い方: python3 ld270_bfs_frame.py     環境変数: M11_WORK (既定 tools/m11/work)
"""
import os
import re
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402

FN, FN_END = 0x128f9e0, 0x1294ab8
NAME = 'function_128f9e0'
SITES = ['12906d1', '1291ac3', '1291b14', '1291b5f', '1291c20', '1293012',
         '1293063', '12930ae', '129312c', '129450c', '129455d', '12945a8']
GAP_START = 0x1290645


def ir_body(path):
    ll = open(path).read().splitlines()
    s = next(i for i, l in enumerate(ll) if re.match(r'define .*@%s\(' % NAME, l))
    e = next(i for i in range(s, len(ll)) if ll[i] == '}')
    return ll[s:e]


def ir_cfg(body):
    blocks, cur, succ = {}, None, {}
    for l in body:
        m = re.match(r'dec_label_pc_([0-9a-f]+):', l)
        if m:
            cur = int(m.group(1), 16)
            blocks[cur] = []
            continue
        if cur is not None:
            blocks[cur].append(l)
    for a, ls in blocks.items():
        t = set()
        for l in ls:
            for m in re.finditer(r'label %dec_label_pc_([0-9a-f]+)', l):
                t.add(int(m.group(1), 16))
        succ[a] = sorted(t)
    return blocks, succ


def bfs(entry, succ):
    par = {entry: None}
    q = deque([entry])
    while q:
        a = q.popleft()
        for b in succ.get(a, []):
            if b not in par:
                par[b] = a
                q.append(b)
    return par


def path_of(par, x):
    p = []
    while x is not None:
        p.append(x)
        x = par[x]
    return list(reversed(p))


def prologue_frame(ins):
    push = sum(1 for x in ins[:40] if x.mnemonic == 'push')
    sub = [x for x in ins[:60] if x.mnemonic == 'sub' and x.op_str.startswith('rsp, ')]
    imm = int(sub[0].op_str.split(', ')[1], 0) if sub else 0
    return push, imm, push * 8 + imm


def main():
    w = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
    mach = ImageMachine(os.path.join(w, 'm11_image.bin'), os.path.join(w, 'boot*.drc.config.json'))
    ins = [x for x in mach.cs.disasm(mach.read(FN - mach.base, FN_END - FN + 0x10), FN, FN_END - FN + 0x10)
           if x.address < FN_END]
    by = {x.address: x for x in ins}
    leaders = {FN}
    for x in ins:
        if x.mnemonic.startswith('j') and x.op_str.startswith('0x'):
            leaders.add(int(x.op_str, 16))
            leaders.add(x.address + x.size)
    leaders = sorted(t for t in leaders if FN <= t < FN_END and t in by)

    # 機械 CFG: block = leader から次の leader 直前まで。末尾命令で後続を決める
    msucc = {}
    for i, a in enumerate(leaders):
        nxt = leaders[i + 1] if i + 1 < len(leaders) else FN_END
        last = None
        addr = a
        while addr < nxt and addr in by:
            last = by[addr]
            addr += last.size
        s = set()
        if last is not None:
            if last.mnemonic == 'jmp' and last.op_str.startswith('0x'):
                s.add(int(last.op_str, 16))
            elif last.mnemonic.startswith('j') and last.mnemonic != 'jmp' and last.op_str.startswith('0x'):
                s.add(int(last.op_str, 16))
                s.add(last.address + last.size)
            elif last.mnemonic in ('ret', 'jmp'):
                pass
            else:
                s.add(addr)
        msucc[a] = sorted(t for t in s if t in leaders)
    mpar = bfs(FN, msucc)

    lift_b, lift_s = ir_cfg(ir_body(os.path.join(w, 'boot3.lift.ll')))
    ipar = bfs(FN, lift_s)
    lift_labels = set(lift_b)

    push, sub, F = prologue_frame(ins)
    ir_final = ir_body(os.path.join(w, 'boot_final3.ll'))
    alloca = {int(m.group(1)) for l in ir_final for m in [re.match(r'\s+%stack_var_(-\d+) = alloca', l)] if m}

    rows = ['site\tmachine_reached\tmachine_path_len\tgap_on_path\tir_block_reached\tsite_at_ir_label\tir_path_len\tstack_var\tframe_F\tprologue_push_sub\tir_alloca\tir_mentions\tmachine_path']
    print('[ld270] 機械 leader %d / 機械 BFS 到達 %d / IR label %d / IR BFS 到達 %d'
          % (len(leaders), len(mpar), len(lift_labels), len(ipar)))
    print('[ld270] prologue: push %d 本 + sub rsp %d = F=%d (0x%x)' % (push, sub, F, F))
    for s in SITES:
        d = int(s, 16)
        # site を含む機械 leader (最大の leader <= site)
        blk = max(a for a in leaders if a <= d)
        mp = path_of(mpar, blk) if blk in mpar else []
        gap_on = [hex(a) for a in mp if a >= GAP_START and a < FN_END and a not in lift_labels]
        # site の IR 所在: lift label の最大 <= d が BFS 到達するか
        lb = max((a for a in lift_labels if a <= d), default=None)
        ip = path_of(ipar, lb) if lb in ipar else []
        mm = re.search(r'\[rbp \+ (0x[0-9a-f]+)\]', by[d].op_str)
        disp = int(mm.group(1), 16)
        name = 'stack_var_-%d' % (F - disp)
        ments = sum(1 for l in ir_final if re.search(re.escape(name) + r'(?![\d])', l))
        off = -(F - disp)
        at_label = blk in lift_labels
        rows.append('\t'.join([s, 'yes' if blk in mpar else 'no', str(len(mp)), ' '.join(gap_on) or '-',
                               'yes' if lb in ipar else 'no', 'yes' if at_label else 'no', str(len(ip)), name, str(F),
                               '%d/%d' % (push, sub), 'yes' if off in alloca else 'no', str(ments),
                               ' -> '.join('%x' % a for a in mp)]))
        print('[ld270] %s: 機械 leader %x 到達=%s (経路 %d 点, 欠落区間の leader=%s) / IR 含む block %x 到達=%s / site 番地に IR label=%s / %s alloca=%s 言及=%d'
              % (s, blk, blk in mpar, len(mp), gap_on or '-', lb, lb in ipar, at_label, name,
                 'yes' if off in alloca else 'no', ments))
        if mp:
            print('[ld270]   機械経路: ' + ' -> '.join('%x' % a for a in mp))
    out = os.path.join(HERE, 'results/ld270_bfs_128f9e0.tsv')
    with open(out, 'w') as fh:
        fh.write('\n'.join(rows) + '\n')
    print('[ld270] -> %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
