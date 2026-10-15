#!/usr/bin/env python3
"""M11-N3 (#131): sigfix 0 詰め call site の機械語突合・分類・定数復元.

入力: m11_post.py --pads が出す 0 詰め site 一覧 (caller, callee, k=caller 内 callee への k 番目の IR call, have, want).
各 site を capstone の機械語 (.pdata 区間の線型 disasm) と突合し、0 詰めされた引数位置ごとに分類する.
  対応づけ: caller 機械語の「callee VA への直接 call」を命令アドレス順に並べ k 番目を取る.
            IR 側 call 数と機械語側 call 数が一致しない caller は 'unmatched' (復元しない).
  Win64 ABI: 位置 0..3 = rcx/rdx/r8/r9, 位置 4.. = [rsp+0x20+8*(i-4)] (call 直前の rsp 基準).
  分類 (引数位置 1 個ごと):
    callee_unused : reg 引数 = callee 入口の直線部分 (最初の call/分岐まで) で読む前に全幅書込される (保守的: 決まらなければ use 扱い)。
                    stack 引数 = callee 全体に [rbp+0x30+8*(pos-4)] / rsp 相対の読出しが無い。 → 0 詰めは無害
    set_const     : callee が使う + caller の直前窓 (同一基本ブロック内, 直前の call/jmp/ret/分岐先まで) で
                    定数 (mov imm / xor self / lea [rip+x]) が代入 → 定数を復元可能 (--out の fix に載せる).
    set_const_xmm_callee : set_const だが callee が xmm0..3 を引数として読む (IR に xmm 引数が無い) → 部分復元しない (実測: 復元で survey 退行 3 unit)
    set_other     : callee が使う + 窓内で非定数が代入 (レジスタ/メモリ由来) → SSA 値対応が要る (未復元).
    inherit       : callee が使う + 窓内で未代入 (caller 自身の引数 / 遠方 def を素通し) → 未復元.
    stack_*       : 位置>=4 の同分類 (窓内の [rsp+disp] 書込を見る).
使い方: python3 m11_argrecover.py PADS.json --pe PE --out fixes.json [--lb 0x0]
"""
import argparse, array, bisect, collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
sys.path.insert(0, HERE)
import capstone
from capstone import x86_const as X
import ldmach

REGS = ['rcx', 'rdx', 'r8', 'r9']
BASE = 0x400000


def reg_family(cs, rid):
    return ldmach.norm_reg(cs, rid)


class Fn:
    def __init__(self, mach, va):
        self.va = va
        self.ins = mach.disasm_fn(va) or []
        self.cs = mach.cs
        self.addrs = [i.address for i in self.ins]
        self.targets = set()
        for i in self.ins:
            if i.mnemonic.startswith('j') and i.operands and i.operands[0].type == capstone.CS_OP_IMM:
                self.targets.add(i.operands[0].imm)
        self._rw = {}

    def rw(self, ins):
        """(reads, writes) 64bit 親 reg 名の集合. 部分書込 (dl/dx 等) は read+write 扱い (上位保持)."""
        k = ins.address
        if k in self._rw:
            return self._rw[k]
        try:
            rd, wr = ins.regs_access()
        except capstone.CsError:
            rd, wr = [], []
        R = set(); W = set()
        for r in rd:
            f = reg_family(self.cs, r)
            if f: R.add(f)
        for r in wr:
            f = reg_family(self.cs, r)
            if not f:
                continue
            nm = self.cs.reg_name(r)
            if nm in ('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp') or nm.endswith('d') and nm.startswith('r') or nm.startswith('r') and len(nm) <= 3 and nm[1:].isdigit() or nm in ldmach.GPR_SET:
                W.add(f)            # 32bit 以上の書込は全幅を定義
            else:
                W.add(f); R.add(f)  # 8/16bit 部分書込は上位を保持 = 旧値依存
        self._rw[k] = (R, W)
        return R, W

    def callee_uses(self):
        """reg 位置 0..3: callee 入口の直線部分 (最初の call/jmp/jcc/ret まで) で最初に現れるのが read なら 'use',
        write (32bit 以上) なら 'def' (= 引数を使わない). 直線部分で決まらなければ 'maybe' (= 使うかもしれない; 保守的に use 扱い).
        call は rcx..r9 を暗黙に読み得るため、決まる前に call に当たれば 'maybe'."""
        state = {r: None for r in REGS}
        for ins in self.ins:
            R, W = self.rw(ins)
            if ins.mnemonic == 'call' or ins.mnemonic.startswith('j') or ins.mnemonic.startswith('ret'):
                break
            for r in REGS:
                if state[r] is None:
                    if r in R:
                        state[r] = 'use'
                    elif r in W:
                        state[r] = 'def'
        return {i: state[r] != 'def' for i, r in enumerate(REGS)}

    def xmm_args_read(self):
        """入口の直線部分で xmm0..3 を書込前に読むか (= xmm 引数あり; RetDec IR には現れない = 部分復元が無意味)."""
        seen = set()
        for ins in self.ins:
            if ins.mnemonic == 'call' or ins.mnemonic.startswith('j') or ins.mnemonic.startswith('ret'):
                break
            try:
                rd, wr = ins.regs_access()
            except capstone.CsError:
                continue
            for r in rd:
                n = self.cs.reg_name(r)
                if n in ('xmm0', 'xmm1', 'xmm2', 'xmm3') and n not in seen:
                    return True
            for r in wr:
                n = self.cs.reg_name(r)
                if n in ('xmm0', 'xmm1', 'xmm2', 'xmm3'):
                    seen.add(n)
        return False

    def stack_arg_read(self, pos):
        """pos>=4: callee entry 側で受け stack 引数 (return addr 後の 0x28+8*(pos-4) off rsp@entry) を読むか.
        rsp 相対: sub rsp,N 後は [rsp+N+0x8+0x20+...]. rbp 相対: push rbp; mov rbp,rsp 後 [rbp+0x30+8*(pos-4)] (Delphi/MS 双方)."""
        want_rbp = 0x30 + 8 * (pos - 4)
        sub = 0
        for ins in self.ins[:12]:
            if ins.mnemonic == 'sub' and ins.op_str.startswith('rsp, '):
                try:
                    sub += int(ins.op_str.split(', ')[1], 0)
                except ValueError:
                    pass
            if ins.mnemonic == 'push':
                sub += 8
        want_rsp = sub + 8 + 0x20 + 8 * (pos - 4)
        for ins in self.ins:
            for m in ldmach.memops_of(self.cs, ins):
                if m['base'] == 'rbp' and m['disp'] == want_rbp:
                    return True
                if m['base'] == 'rsp' and m['disp'] == want_rsp:
                    return True
        return False


def classify_set(fn, call_idx, pos, lb):
    """call 直前窓で pos 番引数が代入されているか. returns (kind, const|None, why)
    why: none 時は 'entry' (関数入口まで代入なし = caller の live-in を素通し) / 'boundary' (call・jmp・jcc・ret・分岐先で窓が切れる)。
         set 時は代入命令の型 ('load' = メモリ読出し / 'reg' = レジスタ由来 / 'arith' = 演算 / 'other')。"""
    ins_list = fn.ins
    reg = REGS[pos] if pos < 4 else None
    j = call_idx - 1
    while j >= 0:
        ins = ins_list[j]
        if ins.mnemonic in ('call', 'ret', 'jmp') or ins.mnemonic.startswith('j'):
            return 'none', None, 'boundary'
        if reg:
            R, W = fn.rw(ins)
            if reg in W:
                return 'set', const_of(fn, ins, reg, lb), _set_why(fn, ins)
        else:
            for m in ldmach.memops_of(fn.cs, ins):
                if m['write'] and m['base'] == 'rsp' and m['disp'] == 0x20 + 8 * (pos - 4):
                    return 'set', None, _set_why(fn, ins)
        if ins.address in fn.targets:
            return 'none', None, 'boundary'
        j -= 1
    return 'none', None, 'entry'


def src_of(fn, call_idx, pos):
    """set_other の代入元 (classify_set と同じ窓・同じ命令) を台帳用に分類する.
    mem_global (rip 相対) / mem_stack (rsp・rbp 相対) / mem_ptr (その他の基底レジスタ) / reg / lea_<base> / imm / other."""
    ins_list = fn.ins
    reg = REGS[pos] if pos < 4 else None
    j = call_idx - 1
    while j >= 0:
        ins = ins_list[j]
        if ins.mnemonic in ('call', 'ret', 'jmp') or ins.mnemonic.startswith('j'):
            return 'boundary'
        hit = False
        if reg:
            R, W = fn.rw(ins)
            hit = reg in W
        else:
            hit = any(m['write'] and m['base'] == 'rsp' and m['disp'] == 0x20 + 8 * (pos - 4) for m in ldmach.memops_of(fn.cs, ins))
        if hit:
            return _src_class(fn, ins)
        if ins.address in fn.targets:
            return 'boundary'
        j -= 1
    return 'entry'


def _src_class(fn, ins):
    ops = ins.operands
    src = ops[-1] if len(ops) >= 2 else None
    if src is None:
        return 'other'
    if src.type == capstone.CS_OP_MEM:
        base = fn.cs.reg_name(src.mem.base)
        cls = 'global' if base == 'rip' else 'stack' if base in ('rsp', 'rbp') else 'ptr'
        return ('lea_' if ins.mnemonic == 'lea' else 'mem_') + cls
    if src.type == capstone.CS_OP_REG:
        return 'reg'
    if src.type == capstone.CS_OP_IMM:
        return 'imm'
    return 'other'


def _set_why(fn, ins):
    if ins.mnemonic in ('mov', 'movzx', 'movsx', 'movsxd') and len(ins.operands) == 2:
        src = ins.operands[1]
        if src.type == capstone.CS_OP_MEM:
            return 'load'
        if src.type == capstone.CS_OP_REG:
            return 'reg'
    if ins.mnemonic in ('add', 'sub', 'imul', 'shl', 'shr', 'sar', 'and', 'or', 'xor', 'lea', 'neg', 'not'):
        return 'arith'
    return 'other'


def stack_imm_of(fn, call_idx, pos):
    """stack 引数の直前窓の書込が 'mov byte|dword ptr [rsp+disp], imm' なら (値, 書込幅 bit) を返す.
    書込幅が引数の型幅を決めるときだけ採用するため、呼出し側で型と照合する (m11_post.py の fix 適用)."""
    j = call_idx - 1
    while j >= 0:
        ins = fn.ins[j]
        if ins.mnemonic in ('call', 'ret', 'jmp') or ins.mnemonic.startswith('j') or ins.address in fn.targets:
            return None
        for m in ldmach.memops_of(fn.cs, ins):
            if m['write'] and m['base'] == 'rsp' and m['disp'] == 0x20 + 8 * (pos - 4):
                ops = ins.operands
                if ins.mnemonic == 'mov' and len(ops) == 2 and ops[1].type == capstone.CS_OP_IMM and ops[0].type == capstone.CS_OP_MEM:
                    bits = ops[0].size * 8
                    return (ops[1].imm & ((1 << bits) - 1), bits)
                return None
        j -= 1
    return None


def const_of(fn, ins, reg, lb):
    mn, ops = ins.mnemonic, ins.operands
    if mn == 'xor' and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG and ops[1].type == capstone.CS_OP_REG and ops[0].reg == ops[1].reg:
        return {'kind': 'int', 'val': 0}
    if mn == 'mov' and len(ops) == 2 and ops[1].type == capstone.CS_OP_IMM and ops[0].type == capstone.CS_OP_REG:
        nm = fn.cs.reg_name(ops[0].reg)
        if nm in ('rcx', 'rdx', 'r8', 'r9'):
            return None                  # 64bit mov imm (sign-extended 32bit) は別扱い: 未復元
        if nm in ('ecx', 'edx', 'r8d', 'r9d'):
            return {'kind': 'int', 'val': ops[1].imm & 0xffffffff}
        return None                      # cl/dl/cx/dx 等の部分書込: 上位が旧値依存 → 未復元
    if mn == 'lea' and len(ops) == 2 and ops[1].type == capstone.CS_OP_MEM and fn.cs.reg_name(ops[1].mem.base) == 'rip':
        va = ins.address + ins.size + ops[1].mem.disp
        return {'kind': 'ptr', 'val': va - BASE + lb}
    return None


FULL_NAMES = {'rcx': ('rcx', 'ecx'), 'rdx': ('rdx', 'edx'), 'r8': ('r8', 'r8d'), 'r9': ('r9', 'r9d')}
PRIO = ['conflict', 'xmm_callee', 'call_clobber', 'partial_def', 'nonconst_def', 'unknown_pred', 'addr_taken', 'no_caller', 'no_value', 'depth']
MAXD = 8


class Blocks:
    """関数内の基本ブロック (leader = 入口・jump 先・jump/ret の直後). preds は fall-through と直接 jump の逆辺."""

    def __init__(self, fn):
        ins, n = fn.ins, len(fn.ins)
        idx = {a: i for i, a in enumerate(fn.addrs)}
        lead = {0}
        self.indirect = False
        for i, x in enumerate(ins):
            if x.mnemonic.startswith('j') or x.mnemonic.startswith('ret'):
                if i + 1 < n:
                    lead.add(i + 1)
                if x.mnemonic.startswith('j'):
                    if x.operands and x.operands[0].type == capstone.CS_OP_IMM:
                        if x.operands[0].imm in idx:
                            lead.add(idx[x.operands[0].imm])
                    elif x.mnemonic == 'jmp':
                        self.indirect = True
        self.starts = sorted(lead)
        self.ends = self.starts[1:] + [n]
        self.preds = [[] for _ in self.starts]
        for b, e in enumerate(self.ends):
            x = ins[e - 1]
            if x.mnemonic.startswith('j') and x.operands and x.operands[0].type == capstone.CS_OP_IMM and x.operands[0].imm in idx:
                self.preds[self.blk_of(idx[x.operands[0].imm])].append(b)
            if not (x.mnemonic == 'jmp' or x.mnemonic.startswith('ret')) and b + 1 < len(self.starts):
                self.preds[b + 1].append(b)

    def blk_of(self, i):
        return bisect.bisect_right(self.starts, i) - 1


class Defchain:
    """窓の外の live-in (inherit) を呼出元まで追跡して値を決める (M11-N87 / #1373).
    at(f, i, pos): 関数 f の命令 i 直前で reg(pos) の到達定義を後ろ向きに集める (基本ブロック単位・全経路の和).
    entry(f, pos): f 入口の値 = 直接 call / tail jmp の呼出元で at() を取った値の集合 (f のアドレスが取られていれば不明).
    結果は (値の集合 {(kind, val)}, 復元不能の理由の集合)。値が 1 つで理由が空のときは候補 (unsound_cand) として件数だけ残し、fix には載せない。"""

    def __init__(self, mach, F, lb):
        self.m, self.F, self.lb = mach, F, lb
        self.bl, self.memo, self.cuts = {}, {}, 0
        self.callers = None
        self.taken = set()
        self.mod = {}
        self.clob = collections.Counter()

    def blocks(self, va):
        if va not in self.bl:
            fn = self.F(va)
            self.bl[va] = Blocks(fn) if fn.ins else None
        return self.bl[va]

    def build_index(self):
        cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        fns = self.m.fns
        self.callers = collections.defaultdict(list)
        for s in self.m.pef.sections:
            nm = s.Name.rstrip(b'\0').decode('latin1')
            if nm in ('.text', '.pdata'):
                continue
            d = s.get_data()
            q = array.array('Q', d[:len(d) // 8 * 8])
            self.taken |= set(q) & set(fns)
        rip = re.compile(r'\[rip ([+-]) 0x([0-9a-f]+)\]')
        for va, (rva, size) in fns.items():
            for i, x in enumerate(cs.disasm(self.m.read(rva, size), va)):
                mn, op = x.mnemonic, x.op_str
                if mn == 'call' and op.startswith('0x') and int(op, 16) in fns:
                    self.callers[int(op, 16)].append((va, i))
                elif mn.startswith('j') and op.startswith('0x') and int(op, 16) in fns and not (va <= int(op, 16) < va + size):
                    self.callers[int(op, 16)].append((va, i))
                elif mn == 'lea' and '[rip' in op:
                    mm = rip.search(op)
                    if mm:
                        disp = int(mm.group(2), 16) * (1 if mm.group(1) == '+' else -1)
                        t = x.address + x.size + disp
                        if t in fns:
                            self.taken.add(t)
        self.build_mod()

    def build_mod(self):
        """各関数が引数レジスタ (rcx/rdx/r8/r9) を書きうるか (推移閉包・直接 call/tail jmp の辺で伝播).
        opaque = 間接 call / 解決できない直接 call を含む (任意に書きうる)."""
        cs, fns = self.m.cs, self.m.fns
        own, opq, edges = {}, {}, {}
        for va, (rva, size) in fns.items():
            mods, o, es = set(), False, set()
            for x in cs.disasm(self.m.read(rva, size), va):
                mn, op = x.mnemonic, x.op_str
                if mn == 'call' or mn.startswith('j'):
                    if op.startswith('0x'):
                        t = int(op, 16)
                        if mn != 'call' and va <= t < va + size:
                            pass
                        elif t in fns:
                            es.add(t)
                        else:
                            o = True
                    elif mn == 'call':
                        o = True
                try:
                    rd, wr = x.regs_access()
                except capstone.CsError:
                    o = True
                    continue
                for r in wr:
                    f = reg_family(cs, r)
                    if f in FULL_NAMES:
                        mods.add(f)
            own[va], opq[va], edges[va] = mods, o, es
        mod = {va: set(own[va]) for va in fns}
        opaque = dict(opq)
        changed = True
        while changed:
            changed = False
            for va in fns:
                n0, o0 = len(mod[va]), opaque[va]
                for g in edges[va]:
                    mod[va] |= mod[g]
                    opaque[va] = opaque[va] or opaque[g]
                if len(mod[va]) != n0 or opaque[va] != o0:
                    changed = True
        self.mod = {va: (mod[va], opaque[va]) for va in fns}

    def clob_kind(self, x):
        op = x.op_str
        if not op.startswith('0x') or int(op, 16) not in self.mod:
            return 'indirect'
        _, o = self.mod[int(op, 16)]
        return 'opaque' if o else 'writes'

    def passes(self, x, reg):
        """直接 call の callee が reg を書かず (推移的にも)、間接 call を含まないなら、call を跨いで reg は保たれる."""
        op = x.op_str
        if x.mnemonic != 'call' or not op.startswith('0x') or int(op, 16) not in self.mod:
            return False
        mods, o = self.mod[int(op, 16)]
        return not o and reg not in mods

    def reach(self, fn, bl, b, hi, reg):
        out, seen, stack = set(), set(), [(b, hi)]
        fulls = FULL_NAMES[reg]
        while stack:
            blk, top = stack.pop()
            if (blk, top) in seen:
                continue
            seen.add((blk, top))
            killed = False
            for j in range(top - 1, bl.starts[blk] - 1, -1):
                x = fn.ins[j]
                if x.mnemonic == 'call':
                    if self.passes(x, reg):
                        continue
                    self.clob[self.clob_kind(x)] += 1
                    out.add(('clobber', j)); killed = True; break
                try:
                    _, wr = x.regs_access()
                except capstone.CsError:
                    out.add(('unknown', j)); killed = True; break
                hit = [fn.cs.reg_name(r) for r in wr if reg_family(fn.cs, r) == reg]
                if hit:
                    out.add(('def' if all(nm in fulls for nm in hit) else 'partial', j)); killed = True; break
            if killed:
                continue
            if bl.indirect:
                out.add(('unknown',))
            if blk == 0:
                out.add(('entry',))
            if not bl.preds[blk] and blk != 0:
                out.add(('unknown',))
            for p in bl.preds[blk]:
                stack.append((p, bl.ends[p]))
        return out

    def at(self, va, i, pos, depth, path):
        bl = self.blocks(va)
        if bl is None:
            return set(), {'unknown_pred'}
        fn = self.F(va)
        reg = REGS[pos]
        vals, rs = set(), set()
        for s in self.reach(fn, bl, bl.blk_of(i), i, reg):
            if s[0] == 'def':
                c = const_of(fn, fn.ins[s[1]], reg, self.lb)
                if c is None:
                    rs.add('nonconst_def')
                else:
                    vals.add((c['kind'], c['val']))
            elif s[0] == 'entry':
                v2, r2 = self.entry(va, pos, depth, path)
                vals |= v2; rs |= r2
            else:
                rs.add({'clobber': 'call_clobber', 'partial': 'partial_def', 'unknown': 'unknown_pred'}[s[0]])
        return vals, rs

    def entry(self, va, pos, depth, path):
        if (va, pos) in self.memo:
            return self.memo[(va, pos)]
        if va in path:
            self.cuts += 1
            return set(), set()
        if depth > MAXD:
            self.cuts += 1
            return set(), {'depth'}
        if self.callers is None:
            self.build_index()
        before = self.cuts
        vals, rs = set(), set()
        if va in self.taken:
            rs.add('addr_taken')
        cl = self.callers.get(va, [])
        if not cl:
            rs.add('no_caller')
        for d, i in cl:
            v, r = self.at(d, i, pos, depth + 1, path | {va})
            vals |= v; rs |= r
        out = (vals, rs)
        if self.cuts == before:
            self.memo[(va, pos)] = out
        return out

    def resolve(self, va, i, pos):
        if self.callers is None:
            self.build_index()
        vals, rs = self.at(va, i, pos, 0, frozenset())
        if not vals and not rs:
            rs = {'no_value'}
        if rs or len(vals) != 1:
            return None, sorted(rs, key=PRIO.index) if rs else ['conflict']
        kind, val = next(iter(vals))
        return {'kind': kind, 'val': val}, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pads')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--lb', default='0')
    a = ap.parse_args()
    lb = int(a.lb, 0)
    pads = json.load(open(a.pads))
    mach = ldmach.Machine(a.pe)
    fcache = {}

    def F(va):
        if va not in fcache:
            fcache[va] = Fn(mach, va)
        return fcache[va]

    dc = Defchain(mach, F, lb)

    usecache = {}
    stats = collections.Counter()
    sites = []
    fixes = []
    ir_calls = collections.Counter((p['caller'], p['callee']) for p in pads)  # 参照用 (pad のみ)
    for p in pads:
        cva = int(p['caller'].split('_')[1], 16)
        tva = int(p['callee'].split('_')[1], 16)
        cf = F(cva)
        calls = [i for i, ins in enumerate(cf.ins) if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type == capstone.CS_OP_IMM and ins.operands[0].imm == tva]
        rec = {'caller': p['caller'], 'callee': p['callee'], 'k': p['k'], 'have': p['have'], 'want': p['want'], 'args': {}}
        if not cf.ins:
            rec['status'] = 'no_pdata'
        elif p['k'] >= len(calls) or len(calls) != p['n']:
            rec['status'] = 'unmatched'
        else:
            rec['status'] = 'matched'
            ci = calls[p['k']]
            if tva not in usecache:
                tf = F(tva)
                usecache[tva] = (tf, tf.callee_uses() if tf.ins else None, tf.xmm_args_read() if tf.ins else False)
            tf, uses, xmm = usecache[tva]
            for pos in range(p['have'], p['want']):
                if uses is None:
                    kind = 'callee_nopdata'; c = None
                else:
                    if pos < 4:
                        used = uses[pos]
                    else:
                        used = tf.stack_arg_read(pos)
                    if not used:
                        kind = 'callee_unused'; c = None
                    else:
                        s, c, why = classify_set(cf, ci, pos, lb)
                        if xmm and s == 'set' and c is not None:
                            kind = 'set_const_xmm_callee'; c = None
                        elif s == 'none' and pos >= 4:
                            kind = 'stack_inherit'
                        elif s == 'none':
                            c2, why2 = dc.resolve(cva, ci, pos)
                            if c2 is not None and xmm:
                                why2 = ['xmm_callee']
                            elif c2 is not None:
                                why2 = ['unsound_cand']  # 1 値に決まっても fix にしない (defchain の穴。REPORT_N87 §6)
                            kind = 'inherit_unres'
                            stats['dc:%s' % why2[0]] += 1
                            stats['dcx:%s:%s' % (why, why2[0])] += 1
                            rec.setdefault('dc', {})[pos] = why2[0]
                        elif c is not None:
                            kind = 'set_const'
                            fixes.append({'caller': p['caller'], 'callee': p['callee'], 'k': p['k'], 'pos': pos, 'const': c})
                        else:
                            kind = 'set_other' if pos < 4 else 'stack_set_other'
                            if kind == 'set_other' or kind == 'stack_set_other':
                                s_src = src_of(cf, ci, pos)
                                stats['src:%s:%s' % (kind, s_src)] += 1
                                rec.setdefault('src', {})[pos] = s_src
                                sc = stack_imm_of(cf, ci, pos) if pos >= 4 and s_src == 'imm' else None
                                if sc is not None:
                                    fixes.append({'caller': p['caller'], 'callee': p['callee'], 'k': p['k'], 'pos': pos, 'const': {'kind': 'int', 'val': sc[0]}, 'bits': sc[1]})
                                    stats['stack_imm_fix'] += 1
                        stats['why:%s:%s' % (kind, why)] += 1
                rec['args'][pos] = kind
                stats['arg:' + kind] += 1
        stats['site:' + rec['status']] += 1
        sites.append(rec)
    for k, v in dc.clob.items():
        stats['clob:' + k] += v
    # site 単位の最終状態 (全引数が callee_unused / set_const なら「解決」)
    resolved = 0
    for r in sites:
        r['resolved'] = r['status'] == 'matched' and all(k in ('callee_unused', 'set_const') for k in r['args'].values())
        resolved += r['resolved']
    out = {'sites': len(sites), 'resolved_sites': resolved, 'stats': dict(stats), 'fixes': fixes, 'site_detail': sites}
    json.dump(out, open(a.out, 'w'))
    print('[argrecover] 0 詰め site %d / 引数 %d' % (len(sites), sum(len(r['args']) for r in sites)))
    for k, v in sorted(stats.items()):
        print('  %-24s %d' % (k, v))
    print('  resolved_sites(全引数が unused or const)  %d' % resolved)
    print('  const 復元可能 fixes %d' % len(fixes))


if __name__ == '__main__':
    main()
