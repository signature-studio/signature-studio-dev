#!/usr/bin/env python3
"""set_other 非 imm 台帳の reg 引数のうち分岐先越え (merge 系 34 件 / #3140 / M11-N172) の CFG 到達定義.

m11_setother_nonimm_class.py (M11-N171) は直線区間で後ろ向きに追い、分岐先 (merge) で止まった 34 件を
ここで基本ブロックの predecessor を辿って決める。IR は変更しない (分類のみ)。
  状態 S(i, fam) = 命令 i の直前で fam が持つ到達定義の葉の集合。
    - i が分岐先なら、全 predecessor p の「p の直後の状態」の和集合 (直線部分は 1 本)。
    - 関数入口 (index 0) の葉は entry。間接 jmp が関数内にあれば分岐先は merge_indirect (predecessor が分からない)。
    - 循環 (ループの戻り辺) で同じ (分岐先, 族) に戻る経路は寄与を空にする (葉の最小不動点)。循環を通った途中結果はメモしない。
  葉の定義の読み方は m11_setother_nonimm_class.py と同じ (mov imm・xor・全幅 copy・ext/即値演算の連鎖)。
  call は揮発族 (rax 以外も) を壊す → 葉 call_clobber (復元不能)。rax は戻り値 → 葉 call_ret (未決)。
  区分 (34 件ごと):
    実値化   : 全葉が定数で、値が一つ (cfg_agree)。
    復元不能 : 葉に call_clobber がある (呼出し越えで揮発 reg が壊れ、その経路の値が ABI 上保証されない)。
    未決     : 上記以外。全葉が定数で値が経路で違う (cfg_conflict) または定数でない葉の理由を併記 (merge>理由)。
使い方: python3 m11_setother_nonimm_cfg.py FIXES.json --pe PE
入力: FIXES.json と同じ dir の nonimm_class_rows.json。出力: 区分別件数 (stdout)、全行を nonimm_cfg_rows.json に同じ dir へ書く。
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
a = ap.parse_args()
dirn = os.path.dirname(os.path.abspath(a.fixes))
MERGE = ('merge', 'merge_at_call', 'chain>merge')
targets = [x for x in json.load(open(os.path.join(dirn, 'nonimm_class_rows.json')))
           if x['pos'] < 4 and x['reason'] in MERGE]
mach = ldmach.Machine(a.pe)

M64 = (1 << 64) - 1
VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
GPR = {}
for fam, names in (('rax', ('rax', 'eax', 'ax', 'al', 'ah')), ('rbx', ('rbx', 'ebx', 'bx', 'bl', 'bh')),
                   ('rcx', ('rcx', 'ecx', 'cx', 'cl', 'ch')), ('rdx', ('rdx', 'edx', 'dx', 'dl', 'dh')),
                   ('rsi', ('rsi', 'esi', 'si', 'sil')), ('rdi', ('rdi', 'edi', 'di', 'dil')),
                   ('rbp', ('rbp', 'ebp', 'bp', 'bpl')), ('rsp', ('rsp', 'esp', 'sp', 'spl'))):
    for nm, w in zip(names, (64, 32, 16, 8, 8)):
        GPR[nm] = (fam, w)
for n in range(8, 16):
    for suf, w in (('', 64), ('d', 32), ('w', 16), ('b', 8)):
        GPR['r%d%s' % (n, suf)] = ('r%d' % n, w)
SIZE = {'byte': 8, 'word': 16, 'dword': 32, 'qword': 64}
IMM = re.compile(r'-?(0x[0-9a-fA-F]+|\d+)$')
ARITH = ('add', 'sub', 'imul', 'and', 'or', 'shl', 'shr', 'sar', 'sal', 'inc', 'dec', 'neg', 'not', 'sbb', 'adc')
EXT = ('movzx', 'movsx', 'movsxd', 'cdqe', 'cwde', 'cbw')
MOVS = ('mov', 'movabs', 'movaps', 'movapd', 'movups', 'movdqa', 'movdqu', 'movss', 'movsd', 'movq', 'movd')
ZERO = ('xor', 'pxor', 'xorps', 'xorpd')
NOWRITE = {'bt', 'cmp', 'test', 'push', 'ucomiss', 'ucomisd', 'comiss', 'comisd', 'nop', 'nopw', 'nopl', 'ret'}
CMPX_W = {'cmpxchg': ('rax',), 'cmpxchg8b': ('rax', 'rdx'), 'cmpxchg16b': ('rax', 'rdx')}
FALL_NO = ('jmp', 'ret', 'ud2', 'int3', 'hlt')


def reg_of(name):
    return GPR.get(name)


def split_ops(s):
    p = s.split(',', 1)
    return p[0].strip(), (p[1].strip() if len(p) > 1 else '')


def mem_kind(op):
    inner = op[op.index('[') + 1:op.index(']')]
    if 'rip' in inner:
        return 'global'
    if 'rsp' in inner or 'rbp' in inner:
        return 'stack'
    return 'ptr'


def imm_val(s):
    return int(s, 0)


class Cfg:
    def __init__(self, va):
        self.cf = AR.Fn(mach, va)
        self.ins = self.cf.ins
        self.addr = [x.address for x in self.ins]
        self.idx = {x.address: i for i, x in enumerate(self.ins)}
        self.indirect = any(x.mnemonic.startswith('j') and x.operands and x.operands[0].type != capstone.CS_OP_IMM
                            for x in self.ins)
        self.jsrc = collections.defaultdict(list)
        for i, x in enumerate(self.ins):
            if x.mnemonic.startswith('j') and x.operands and x.operands[0].type == capstone.CS_OP_IMM \
                    and x.operands[0].imm in self.idx:
                self.jsrc[self.idx[x.operands[0].imm]].append(i)
        self.memo = {}
        self.busy = set()
        self.cut = 0

    def is_def(self, i, fam):
        x = self.ins[i]
        mn = x.mnemonic
        if mn.startswith('j') or mn in NOWRITE:
            return False
        dst = split_ops(x.op_str)[0]
        return (fam in self.cf.rw(x)[1] or fam in CMPX_W.get(mn, ())
                or bool(reg_of(dst) and reg_of(dst)[0] == fam))

    def before(self, i, fam, d=0):
        key = (i, fam)
        if key in self.memo:
            return self.memo[key]
        if key in self.busy:
            self.cut += 1
            return []
        if d > 200:
            self.cut += 1
            return [('未決', 'depth', None, None)]
        self.busy.add(key)
        n0 = self.cut
        r = list(dict.fromkeys(self.walk(i, fam, d)))
        self.busy.discard(key)
        if self.cut == n0:
            self.memo[key] = r
        return r

    def walk(self, i, fam, d):
        k = i
        while True:
            if k in self.jsrc:
                if self.indirect:
                    return [('未決', 'merge_indirect', None, hex(self.addr[k]))]
                preds = list(self.jsrc[k])
                out = []
                if k == 0:
                    out.append(('未決', 'entry', None, None))
                if k > 0 and self.ins[k - 1].mnemonic not in FALL_NO:
                    preds = [k - 1] + preds
                for p in preds:
                    out += self.after(p, fam, d + 1)
                return out
            if k == 0:
                return [('未決', 'entry', None, None)]
            prev = k - 1
            if self.ins[prev].mnemonic in FALL_NO:
                return []
            if self.is_def(prev, fam) or self.ins[prev].mnemonic == 'call':
                return self.after(prev, fam, d + 1)
            k = prev

    def after(self, p, fam, d):
        x = self.ins[p]
        at = hex(x.address)
        if x.mnemonic == 'call':
            if fam == 'rax':
                return [('未決', 'call_ret', None, at)]
            if fam in VOLATILE:
                return [('復元不能', 'call_clobber', None, at)]
            return self.before(p, fam, d + 1)
        if not self.is_def(p, fam):
            return self.before(p, fam, d + 1)
        return self.def_leaves(p, fam, d + 1)

    def def_leaves(self, p, fam, d):
        x = self.ins[p]
        mn = x.mnemonic
        at = hex(x.address)
        dst, src = split_ops(x.op_str)
        info = reg_of(dst)
        w = info[1] if info else 0
        mask = (1 << w) - 1 if w else M64
        if mn in ('movzx', 'movsx', 'movsxd') and reg_of(src):
            sfam, sw = reg_of(src)
            out = []
            for c, why, v, da in self.before(p, sfam, d):
                if c == '実値化':
                    v2 = v & ((1 << sw) - 1)
                    if mn != 'movzx' and (v2 >> (sw - 1)) & 1:
                        v2 -= 1 << sw
                    out.append(('実値化', 'ext_' + mn, v2 & mask, at))
                else:
                    out.append((c, 'ext_' + why if c == '復元不能' else 'chain>' + why.split('>')[-1], None, da))
            return out
        if mn in ('add', 'sub', 'and', 'or') and IMM.match(src) and w >= 32:
            cv = imm_val(src)
            out = []
            for c, why, v, da in self.before(p, fam, d):
                if c == '実値化':
                    r = {'add': v + cv, 'sub': v - cv, 'and': v & cv, 'or': v | cv}[mn]
                    out.append(('実値化', 'arith_imm', r & mask, at))
                else:
                    out.append((c, 'arith_' + why if c == '復元不能' else 'chain>' + why.split('>')[-1], None, da))
            return out
        if mn in ARITH:
            return [('未決', 'arith' + ('_load' if '[' in src else ''), None, at)]
        if mn == 'lea':
            return [('未決', 'lea_' + mem_kind(src), None, at)]
        if '[' in src:
            return [('未決', 'load_' + mem_kind(src), None, at)]
        if mn in ZERO and dst == src and w:
            return [('実値化', 'zero_idiom', 0, at)] if w >= 32 else [('未決', 'partial_zero', None, at)]
        if mn in MOVS and IMM.match(src):
            return [('実値化', 'mov_imm', imm_val(src) & mask, at)] if w >= 32 else [('未決', 'partial_imm', None, at)]
        if mn in MOVS and reg_of(src):
            sfam, sw = reg_of(src)
            if w >= 32 and sw >= w and mn == 'mov':
                return [(c, why, (v & mask) if c == '実値化' else None, da)
                        for c, why, v, da in self.before(p, sfam, d)]
            return [('未決', 'partial_copy', None, at)]
        if mn in EXT:
            return [('未決', 'ext', None, at)]
        return [('未決', 'other:' + mn, None, at)]


def decide(leaves):
    if not leaves:
        return '未決', 'unreached', None
    if any(c == '復元不能' for c, w, v, da in leaves):
        return '復元不能', 'call_clobber', None
    if all(c == '実値化' for c, w, v, da in leaves):
        vals = {v for c, w, v, da in leaves}
        if len(vals) == 1:
            return '実値化', 'cfg_agree', vals.pop()
        return '未決', 'cfg_conflict', None
    return '未決', 'merge>' + '+'.join(sorted({w for c, w, v, da in leaves if c != '実値化'})), None


fc = {}
rows = []
cnt = collections.Counter()
xtab = collections.Counter()
for r in targets:
    cva = int(r['caller'].split('_')[1], 16)
    tva = int(r['callee'].split('_')[1], 16)
    if cva not in fc:
        fc[cva] = Cfg(cva)
    C = fc[cva]
    calls = [i for i, x in enumerate(C.ins) if x.mnemonic == 'call' and x.operands
             and x.operands[0].type == capstone.CS_OP_IMM and x.operands[0].imm == tva]
    ci = calls[r['k']]
    fam = AR.REGS[r['pos']]
    leaves = C.before(ci, fam)
    cls, why, val = decide(leaves)
    cnt[cls] += 1
    xtab[(r['reason'], why, cls)] += 1
    rows.append({'caller': r['caller'], 'callee': r['callee'], 'k': r['k'], 'pos': r['pos'], 'kind': r['kind'],
                 'ledger': r['ledger'], 'orig_reason': r['reason'], 'fam': fam, 'class': cls, 'reason': why,
                 'value': (hex(val) if val is not None else None), 'indirect': C.indirect,
                 'leaves': sorted({'%s:%s@%s' % (c, w, da) for c, w, v, da in leaves})})
print('[nonimm-cfg] merge 系 reg 台帳 %d 件' % len(rows))
for k in ('実値化', '復元不能', '未決'):
    print('  %-8s %d' % (k, cnt[k]))
print('[nonimm-cfg] 元の理由 × 区分理由 × 区分')
for (orig, why, cls), v in sorted(xtab.items()):
    print('  %-14s %-28s %-8s %d' % (orig, why, cls, v))
json.dump(rows, open(os.path.join(dirn, 'nonimm_cfg_rows.json'), 'w'), indent=1)
