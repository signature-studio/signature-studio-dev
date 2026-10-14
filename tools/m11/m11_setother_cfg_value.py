#!/usr/bin/env python3
"""set_other imm 非定数 55 件 (#1660 / M11-N124) の値を、CFG の到達定義で決める.

m11_setother_ssa_value.py (M11-N112) は直線区間の後ろ向き追跡で止まり、分岐先 (merge) で全件 undecided だった.
本スクリプトは同じ書込規則 (x86-64 の幅・上位ビット) を使い、基本ブロックの predecessor を辿る:
  - 値 V(i, key) = 命令 i の直前で key (レジスタ族 または [rsp+disp] qword) が持つ値.
  - i が分岐先 (jump target) なら、全 predecessor p の「p の直後の値」を集め、全部一致した時だけ決める.
    1 つでも決まらなければ undecided (理由は最初に見つかったもの). 値の不一致は merge_conflict.
  - 関数入口 (index 0) は entry、関数内に間接 jmp (jump table 等) があれば分岐先は merge_indirect (predecessor が完全には分からないため).
  - 戻り辺 (ループ) に入ったら loop で未決. 決まった値は全経路が有限・非循環に定まった場合だけ.
  - call は volatile 族 (rcx/rdx/r8/r9/rax) と [rsp+disp] スロットを壊すとして call_clobber で未決.
  - 書込が上記の規則で扱えない命令 (暗黙書込・未対応形) は opaque / unhandled で未決.
値は 64bit 族の値と、呼び出し先 IR 引数の型幅で切り落とした値 (value_ir) の両方を出す.
使い方: python3 m11_setother_cfg_value.py FIXES.json --pe PE [--imm-class imm_class_rows.json]
出力: 理由別件数 (stdout)、全行を cfg_value_rows.json に FIXES.json と同じ dir へ書く.
"""
import argparse, collections, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
sys.path.insert(0, HERE)
import capstone
import ldmach
import m11_argrecover as AR

ap = argparse.ArgumentParser()
ap.add_argument('fixes'); ap.add_argument('--pe', required=True)
ap.add_argument('--imm-class', default=None)
a = ap.parse_args()
dirn = os.path.dirname(os.path.abspath(a.fixes))
d = json.load(open(a.fixes))
imm_rows = json.load(open(a.imm_class or os.path.join(dirn, 'imm_class_rows.json')))
PTYPE = {(x['caller'], x['callee'], x['k'], x['pos']): x['ptype'] for x in imm_rows if x['class'] != 'full_const'}
mach = ldmach.Machine(a.pe)

M64 = (1 << 64) - 1
W32 = 0xffffffff
def _regtab():
    """レジスタ名 -> (64bit 族, 幅). 高位バイト (ah 等) は含めない (未対応として未決にする)."""
    t = {}
    for b in ['a', 'b', 'c', 'd']:
        fam = 'r' + b + 'x'
        t[fam] = (fam, 64)
        t['e' + b + 'x'] = (fam, 32)
        t[b + 'x'] = (fam, 16)
        t[b + 'l'] = (fam, 8)
    for n in ['si', 'di', 'bp', 'sp']:
        fam = 'r' + n
        t[fam] = (fam, 64)
        t['e' + n] = (fam, 32)
        t[n] = (fam, 16)
        t[n + 'l'] = (fam, 8)
    for i in range(8, 16):
        fam = 'r%d' % i
        t[fam] = (fam, 64)
        t[fam + 'd'] = (fam, 32)
        t[fam + 'w'] = (fam, 16)
        t[fam + 'b'] = (fam, 8)
    return t


REGTAB = _regtab()
ARG_FAM = {k: v[0] for k, v in REGTAB.items()}
WIDTH = {k: v[1] for k, v in REGTAB.items()}
VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
MEMRE = re.compile(r'^(byte|word|dword|qword) ptr \[rsp \+ 0x([0-9a-f]+)\]$')
SIZE = {'byte': 8, 'word': 16, 'dword': 32, 'qword': 64}
FALL_NO = ('jmp', 'ret', 'ud2', 'int3', 'hlt')
OPAQUE = ('div', 'idiv', 'mul', 'imul', 'cqo', 'cdq', 'xchg', 'cmpxchg', 'pop', 'cwde', 'cdqe')


def parse_imm(s):
    s = s.strip()
    if not re.fullmatch(r'-?(0x[0-9a-f]+|\d+)', s):
        return None
    return int(s, 0)


class Fnc:
    """1 関数の CFG. 値は (値 or None, 理由) で返す."""

    def __init__(self, va):
        self.cf = AR.Fn(mach, va)
        self.ins = self.cf.ins
        self.n = len(self.ins)
        self.addr = [x.address for x in self.ins]
        self.idx = {x.address: i for i, x in enumerate(self.ins)}
        self.starts = set()
        self.indirect = False
        for i, x in enumerate(self.ins):
            if x.mnemonic.startswith('j') and x.operands:
                if x.operands[0].type == capstone.CS_OP_IMM:
                    if x.operands[0].imm in self.idx:
                        self.starts.add(self.idx[x.operands[0].imm])
                else:
                    self.indirect = True
        self.preds = {}
        for i in range(self.n):
            p = []
            if i > 0 and self.ins[i - 1].mnemonic not in FALL_NO:
                p.append(i - 1)
            p += [k for k, x in enumerate(self.ins)
                  if x.mnemonic.startswith('j') and x.operands and x.operands[0].type == capstone.CS_OP_IMM
                  and x.operands[0].imm == self.addr[i]]
            self.preds[i] = p
        self.memo = {}
        self.busy = set()

    def writes(self, i, fam):
        return fam in self.cf.rw(self.ins[i])[1]

    def mem_writes(self, i, disp):
        return [m for m in ldmach.memops_of(self.cf.cs, self.ins[i]) if m['write'] and m['base'] == 'rsp'
                and m['disp'] <= disp < m['disp'] + 8]

    def before(self, i, key):
        """命令 i の直前の key の値."""
        if i == 0:
            return None, 'entry'
        if i in self.starts:
            if self.indirect:
                return None, 'merge_indirect'
            return self.join(i, key)
        return self.after(i - 1, key)

    def join(self, i, key):
        mk = (i, key)
        if mk in self.memo:
            return self.memo[mk]
        if mk in self.busy:
            return None, 'loop'
        self.busy.add(mk)
        vals = set(); why = None
        for p in self.preds[i]:
            v, w = self.after(p, key)
            if v is None:
                why = why or ('merge_' + w)
            else:
                vals.add(v)
        self.busy.discard(mk)
        if not self.preds[i]:
            r = (None, 'merge_nopred')
        elif why:
            r = (None, why)
        elif len(vals) == 1:
            r = (vals.pop(), 'merge_agree')
        else:
            r = (None, 'merge_conflict')
        self.memo[mk] = r
        return r

    def after(self, i, key):
        """命令 i の直後の key の値."""
        x = self.ins[i]
        if key[0] == 'reg':
            fam = key[1]
            if x.mnemonic == 'call':
                return (None, 'call_clobber') if fam in VOLATILE else self.before(i, key)
            if not self.writes(i, fam):
                return self.before(i, key)
            return self.write_reg(i, fam)
        disp = key[1]
        if x.mnemonic == 'call':
            return None, 'call_clobber'
        if not self.mem_writes(i, disp):
            return self.before(i, key)
        return self.write_mem(i, disp)

    def write_reg(self, i, fam):
        x = self.ins[i]
        if x.mnemonic in OPAQUE:
            return None, 'opaque'
        ops = x.op_str.split(',', 1)
        dst = ops[0].strip()
        src = ops[1].strip() if len(ops) == 2 else ''
        if ARG_FAM.get(dst) != fam or dst not in WIDTH:
            return None, 'unhandled_dst'
        w = WIDTH[dst]
        if x.mnemonic == 'mov' and re.fullmatch(r'-?(0x[0-9a-f]+|\d+)', src):
            imm = parse_imm(src)
            if w in (32, 64):
                return imm & (W32 if w == 32 else M64), 'mov_full'
            old, why = self.before(i, ('reg', fam))
            if old is None:
                return None, 'partial_old_' + why
            mask = (1 << w) - 1
            return ((old & ~mask) | (imm & mask)) & M64, 'mov_partial'
        if x.mnemonic == 'xor' and src == dst and w in (32, 64):
            return 0, 'xor_zero'
        if x.mnemonic == 'mov' and src in ARG_FAM and w in (32, 64) and WIDTH[src] >= w:
            sv, why = self.before(i, ('reg', ARG_FAM[src]))
            if sv is None:
                return None, 'copy_' + why
            return sv & ((1 << w) - 1), 'copy'
        if x.mnemonic in ('add', 'sub') and w == 32:
            imm = parse_imm(src)
            if imm is None:
                return None, 'arith_nonimm'
            old, why = self.before(i, ('reg', fam))
            if old is None:
                return None, 'arith_old_' + why
            v = (old + imm) if x.mnemonic == 'add' else (old - imm)
            return v & W32, 'arith32'
        return None, 'unhandled:%s %s' % (x.mnemonic, x.op_str)

    def write_mem(self, i, disp):
        x = self.ins[i]
        if x.mnemonic != 'mov':
            return None, 'mem_unhandled_' + x.mnemonic
        m = MEMRE.match(x.op_str.split(',')[0].strip())
        if not m:
            return None, 'mem_fmt'
        size = SIZE[m.group(1)]
        base = int(m.group(2), 16)
        if base != disp:
            return None, 'mem_partial_slot'
        imm = parse_imm(x.op_str.split(',', 1)[1].strip())
        if imm is None:
            return None, 'mem_nonimm'
        if size == 64:
            return imm & M64, 'mem_full'
        if size == 32:
            old, why = self.before(i, ('mem', disp))
            if old is None:
                return None, 'mem_old_' + why
            return ((old & ~W32) | (imm & W32)) & M64, 'mem_dword_partial'
        return None, 'mem_size%d' % size

FN = {}


def fn(va):
    if va not in FN:
        FN[va] = Fnc(va)
    return FN[va]


def trunc(v, ptype):
    m = re.fullmatch(r'i(\d+)', ptype or '')
    if v is None or not m:
        return None
    return v & ((1 << int(m.group(1))) - 1)


rows = []
cnt = collections.Counter()
for r in d['site_detail']:
    if r['status'] != 'matched':
        continue
    cva = int(r['caller'].split('_')[1], 16)
    tva = int(r['callee'].split('_')[1], 16)
    C = fn(cva)
    calls = [i for i, x in enumerate(C.ins) if x.mnemonic == 'call' and x.operands and x.operands[0].type == capstone.CS_OP_IMM and x.operands[0].imm == tva]
    if r['k'] >= len(calls):
        continue
    ci = calls[r['k']]
    for pos_s, src in (r.get('src') or {}).items():
        if src != 'imm':
            continue
        pos = int(pos_s)
        key0 = (r['caller'], r['callee'], r['k'], pos)
        if key0 not in PTYPE:
            continue
        ptype = PTYPE[key0]
        if pos < 4:
            key = ('reg', AR.REGS[pos])
        else:
            key = ('mem', 0x20 + 8 * (pos - 4))
        row = {'caller': r['caller'], 'callee': r['callee'], 'k': r['k'], 'pos': pos, 'ptype': ptype,
               'insn': None, 'value': None, 'value_ir': None, 'why': None}
        wi = None
        for j in range(ci - 1, -1, -1):
            if C.ins[j].mnemonic == 'call':
                break
            hit = C.writes(j, key[1]) if key[0] == 'reg' else bool(C.mem_writes(j, key[1]))
            if hit:
                wi = j
                break
        if wi is not None:
            wx = C.ins[wi]
            row['insn'] = '%s %s' % (wx.mnemonic, wx.op_str)
        v, why = C.before(ci, key)
        if v is None:
            row['why'] = why
            rows.append(row); cnt['undecided:' + why] += 1
            continue
        row['value'] = '0x%x' % v
        row['value_ir'] = None if trunc(v, ptype) is None else '0x%x' % trunc(v, ptype)
        row['why'] = why
        rows.append(row); cnt['decided:' + why] += 1

print('[cfg-value] imm 非定数 対象 %d 件' % len(rows))
for k in sorted(cnt):
    print('  %-44s %d' % (k, cnt[k]))
print('  decided %d / undecided %d' % (sum(v for k, v in cnt.items() if k.startswith('decided')), sum(v for k, v in cnt.items() if k.startswith('undecided'))))
json.dump(rows, open(os.path.join(dirn, 'cfg_value_rows.json'), 'w'), indent=1)
