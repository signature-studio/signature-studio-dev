#!/usr/bin/env python3
"""audit_icall.py — PE x86-64 の間接 call/jmp を capstone で静的に数え、RetDec IR と突合する監査ツール.

  python3 audit_icall.py --pe X.dll --ir A.drc.ll [--ir B.drc.ll ...] [--funcs funcs.txt] [--dsm A.drc.dsm]
                         [--json out.json] [--sites sites.json] [--label NAME]

関数集合 (優先順): --funcs (VA 1 行 1 個, 0x可) > IR の `define @function_<va>` 全部 > --all-pdata (.pdata 全関数).
関数範囲は .pdata (RUNTIME_FUNCTION, chain 先頭) を使い、無ければ dsm の `; function: X at A -- B`.
命令列は recursive descent (jcc/jmp/fallthrough + jump table 解決) で取る。到達しない gap は clean に decode できる分だけ
'gap' 命令として別集計 (RetDec dsm が見ていた gap 命令のみ主表に含める。残りは gap_sites として件数のみ別掲)。

分類 kind (mnemonic ごと):
  iat        call/jmp [rip+disp]  で disp 先が import/delay-import の IAT slot
  rip_data   call/jmp [rip+disp]  で IAT 以外 (静的関数ポインタ変数: Delphi RandomPtr 等)
  vtable     call/jmp [reg+disp]  (index 無し; C++ vptr / Delphi VMT / 構造体内 fn ptr)
  indexed    call/jmp [base+idx*scale+disp] (関数ポインタ表)
  abs_mem    call/jmp [disp]  (base 無し)
  reg        call reg / jmp reg (jmp reg で jump table と判定できたものは jmptable)
  jmptable   switch 分岐: jmp reg (表引き後) / jmp [idx*scale+disp]
IR 突合 (insn.addr のある raw RetDec IR のみ per-site): 各 site VA について IR が
  kept_indirect (call で callee が @name 以外) / resolved_direct (call だが @name; RetDec が静的に解決) /
  other_insn (call 以外の IR 命令だけ有る: jmp→br/ret 等) / dropped (その VA の IR 命令が 0)
jmptable は jt_present / jt_dropped / jt_folded。jt_folded は jt 比較列が RetDec で switch に畳まれた site
  (--map 指定時のみ判定: 新区間の終端が switch の default 先で、case 数 = targets-1)。addr は復元しない。
insn.addr の無い IR (パス鎖後) は per-function の indirect call 件数だけで総数比較する (--ir-counts-only 相当, 自動).
"""
import argparse, bisect, collections, json, re, struct, sys, os

import capstone
from capstone import x86
import pefile

KINDS = ['iat', 'rip_data', 'vtable', 'indexed', 'abs_mem', 'reg', 'jmptable']


class Image:
    def __init__(self, path):
        self.path = path
        self.pe = pefile.PE(path, fast_load=True)
        self.pe.parse_data_directories()
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.secs = []
        for s in self.pe.sections:
            data = s.get_data()
            self.secs.append((self.base + s.VirtualAddress, s.VirtualAddress, data, s.Name.rstrip(b'\0').decode('latin1'),
                              s.Characteristics))
        self.iat = set()
        for attr in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT'):
            for d in getattr(self.pe, attr, []) or []:
                for imp in d.imports:
                    if imp.address:
                        self.iat.add(imp.address)
        self.iat_ranges = []
        self.pdata = {}
        self.pdata_chained = set()
        for e in getattr(self.pe, 'DIRECTORY_ENTRY_EXCEPTION', []) or []:
            st = e.struct
            if st.BeginAddress and st.EndAddress > st.BeginAddress:
                self.pdata[self.base + st.BeginAddress] = self.base + st.EndAddress
                ub = self.read(self.base + (st.UnwindData & ~1), 1)
                if ub and ((ub[0] >> 3) & 4):          # UNW_FLAG_CHAININFO: 親関数の断片 (hot/cold split chunk)
                    self.pdata_chained.add(self.base + st.BeginAddress)
        self.pdata_starts = sorted(self.pdata)

    def read(self, va, n):
        for lo, rva, data, name, ch in self.secs:
            if lo <= va and va + n <= lo + len(data):
                return data[va - lo: va - lo + n]
        return None

    def is_exec(self, va):
        for lo, rva, data, name, ch in self.secs:
            if lo <= va < lo + len(data):
                return bool(ch & 0x20000000)
        return False

    def set_extra_starts(self, starts):
        self.bounds = sorted(set(self.pdata_starts) | set(starts))

    def func_range(self, va):
        if va in self.pdata:
            return va, self.pdata[va]
        i = bisect.bisect_right(self.pdata_starts, va) - 1
        if i >= 0 and self.pdata_starts[i] <= va < self.pdata[self.pdata_starts[i]]:
            s = self.pdata_starts[i]
            return va, self.pdata[s]
        b = getattr(self, 'bounds', None)
        if b and self.is_exec(va):
            j = bisect.bisect_right(b, va)
            end = b[j] if j < len(b) else va + 0x1000
            if end - va > 0x4000:
                end = va + 0x4000
            return va, end
        return None


def parse_dsm_ranges(path):
    r = {}
    pat = re.compile(r'^; function: \S+ at 0x([0-9a-f]+) -- 0x([0-9a-f]+)')
    with open(path, 'r', errors='replace') as f:
        for l in f:
            if l.startswith('; function:'):
                m = pat.match(l)
                if m:
                    r[int(m.group(1), 16)] = int(m.group(2), 16)
    return r


class Site:
    __slots__ = ('va', 'fn', 'mn', 'kind', 'text', 'size', 'base', 'index', 'scale', 'disp', 'reg', 'gap', 'targets', 'raw', 'ir', 'jt')

    def to_dict(self):
        return {k: getattr(self, k, None) for k in self.__slots__ if k != 'raw'} | {'bytes': self.raw.hex() if self.raw else ''}


def op_desc(cs, ins):
    op = ins.operands[0]
    d = {}
    if op.type == x86.X86_OP_REG:
        d['reg'] = ins.reg_name(op.reg)
    elif op.type == x86.X86_OP_MEM:
        m = op.mem
        d['base'] = ins.reg_name(m.base) if m.base else None
        d['index'] = ins.reg_name(m.index) if m.index else None
        d['scale'] = m.scale
        d['disp'] = m.disp
        d['size'] = op.size
        d['seg'] = ins.reg_name(m.segment) if m.segment else None
    return d


ODD_MN = {'in', 'out', 'ins', 'outs', 'insb', 'insw', 'insd', 'outsb', 'outsw', 'outsd', 'hlt', 'iret', 'iretq', 'iretd', 'loop', 'loope', 'loopne', 'jrcxz', 'jecxz',
          'int', 'into', 'sysret', 'syscall', 'cli', 'sti', 'ud2', 'lret', 'retf', 'enter', 'leave'.replace('leave', 'bound'), 'bound', 'arpl', 'salc', 'aam', 'aad', 'daa', 'das', 'aaa', 'aas'}


class Disasm:
    def __init__(self, img):
        self.img = img
        self.cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.cs.detail = True
        self.cs.skipdata = False
        self.data_ranges = []

    def decode_one(self, va):
        b = self.img.read(va, 16) or self.img.read(va, 1)
        if not b:
            return None
        for ins in self.cs.disasm(b, va, 1):
            return ins
        return None

    def resolve_jumptable(self, insns_before, jmp_ins, fstart, fend):
        """jmp reg / jmp [..idx*s..] の switch 表を解決し ターゲット VA 列 を返す (失敗 None).
        対応: (1) MSVC: lea B,[rip+..](=imagebase); mov/movsxd r,[B+idx*4+RVA]; add r,B; jmp r
              (2) 絶対表: jmp [idx*8+VA] / mov r,[idx*8+VA]; jmp r
              (3) Delphi/code 内表: lea B,[rip+X]; jmp [B+idx*8+d] (エントリ=絶対 VA 8B)"""
        img = self.img
        win = insns_before[-16:]
        lea = {}
        for ins in win:
            if ins.mnemonic == 'lea' and len(ins.operands) == 2 and ins.operands[1].type == x86.X86_OP_MEM:
                m = ins.operands[1].mem
                if m.base == x86.X86_REG_RIP and not m.index:
                    lea[ins.reg_name(ins.operands[0].reg)] = ins.address + ins.size + m.disp
        n = None
        for ins in reversed(win):
            if ins.mnemonic == 'cmp' and len(ins.operands) == 2 and ins.operands[1].type == x86.X86_OP_IMM:
                n = ins.operands[1].imm + 1
                break
        if n is not None and not (1 <= n <= 4096):
            n = None
        cand = []  # (table_va, scale, rel_base or None, lea_based)
        def from_mem(ins_op):
            m = ins_op.mem
            if not m.index or m.scale not in (4, 8):
                return None
            bn = ins_op.mem and (jmp_ins.reg_name(m.base) if m.base else None)
            if m.base and m.base != x86.X86_REG_RIP:
                bv = lea.get(bn)
                if bv is None:
                    return None
                return (bv + m.disp, m.scale, bv if m.scale == 4 else None, True)
            if not m.base:
                return ((m.disp & 0xFFFFFFFFFFFFFFFF), m.scale, img.base if m.scale == 4 else None, False)
            return None
        op = jmp_ins.operands[0]
        if op.type == x86.X86_OP_MEM:
            r = from_mem(op)
            if r:
                cand.append(r)
        elif op.type == x86.X86_OP_REG:
            for ins in reversed(win):
                if ins.mnemonic in ('mov', 'movsxd', 'movzx') and len(ins.operands) == 2 and ins.operands[1].type == x86.X86_OP_MEM:
                    r = from_mem(ins.operands[1])
                    if r:
                        cand.append(r)
                        break
        for taddr, scale, relb, lea_based in cand:
            lim = n if n else 256
            tl = []
            # Delphi の `sub idx,8; jmp [B+idx*8+d]` 形 (B は lea 基点) は index が負側 (基点より前) に伸びる。
            # lea 基点の絶対 8 byte 表に限り、基点から後退して関数内 target が続く間だけ先頭を延ばす。
            back = 0
            if lea_based and relb is None and scale == 8:
                while back < 256:
                    raw = img.read(taddr - (back + 1) * scale, scale)
                    if raw is None:
                        break
                    t = struct.unpack('<Q', raw)[0]
                    if not (fstart <= t < fend):
                        break
                    back += 1
                taddr -= back * scale
            for i in range(back + lim):
                raw = img.read(taddr + i * scale, scale)
                if raw is None:
                    break
                v = struct.unpack('<I' if scale == 4 else '<Q', raw)[0]
                t = (relb + v) if relb is not None else v
                if scale == 4 and relb is not None and t > 0xFFFFFFFFFFFF:
                    break
                if not (fstart <= t < fend):
                    if n is None and i >= back:
                        break
                    continue
                tl.append(t)
            if tl:
                self.last_jt = (taddr, scale, relb, len(tl))
                self.data_ranges.append((taddr, taddr + (max(len(tl), n or 0) + back) * scale))
                return tl
        return None

    def scan_function(self, fstart, fend, sites_out):
        """recursive descent. sites_out: dict va -> Site. 戻り (ninsn, reached_va_set)."""
        img = self.img
        seen = {}
        work = [fstart]
        terminal = {'ret', 'retf', 'iret', 'ud2', 'hlt', 'int3'}
        jt_targets = {}
        while work:
            va = work.pop()
            hist = []
            while fstart <= va < fend and va not in seen:
                ins = self.decode_one(va)
                if ins is None or ins.id == 0:
                    break
                seen[va] = ins
                hist.append(ins)
                mn = ins.mnemonic
                if mn.startswith('rep') or mn.startswith('lock') or mn.startswith('bnd') or mn.startswith('notrack') or mn.startswith('xacq'):
                    pass
                grp = set(ins.groups)
                is_call = x86.X86_GRP_CALL in grp or mn == 'call'
                is_jmp = x86.X86_GRP_JUMP in grp or mn.startswith('j')
                if mn in terminal:
                    break
                if (is_call or is_jmp) and ins.operands:
                    op = ins.operands[0]
                    if op.type == x86.X86_OP_IMM:
                        if is_jmp:
                            t = op.imm
                            if mn == 'jmp':
                                if fstart <= t < fend:
                                    work.append(t)
                                break
                            if fstart <= t < fend:
                                work.append(t)
                    else:
                        self._record(sites_out, ins, fstart, fend, hist, is_call)
                        if is_jmp and mn == 'jmp':
                            s = sites_out[ins.address]
                            if s.targets:
                                work.extend(s.targets)
                            break
                va += ins.size
        return seen


    def gap_sweep(self, fs, fe, seen, sites, want_insns=None):
        """recursive descent が到達しなかった範囲のうち、全体が clean に decode できる塊だけ拾う (Delphi の unwind landing pad 等).
        拾った間接 call/jmp は gap=True で sites に追加。want_insns(dict) を渡すとその命令も格納する。"""
        img = self.img
        cov = set()
        for va, ins in seen.items():
            for i in range(ins.size):
                cov.add(va + i)
        for lo, hi in self.data_ranges:
            for x in range(max(lo, fs), min(hi, fe)):
                cov.add(x)
        va = fs
        while va < fe:
            if va in cov:
                va += 1
                continue
            g0 = va
            while va < fe and va not in cov:
                va += 1
            g1 = va
            gb = img.read(g0, g1 - g0)
            if not gb or all(x in (0xcc, 0x90, 0x00) for x in gb):
                continue
            insl = []
            p = g0
            ok = True
            while p < g1:
                ins = self.decode_one(p)
                if ins is None or ins.id == 0 or p + ins.size > g1:
                    ok = False
                    break
                insl.append(ins)
                p += ins.size
            if not ok:
                continue
            odd = sum(1 for i in insl if i.mnemonic in ODD_MN)
            zeros = sum(1 for i in insl if i.mnemonic == 'add' and i.bytes == b'\x00\x00')
            if odd or zeros >= 2:
                continue
            tmp = {}
            for k, ins in enumerate(insl):
                grp = set(ins.groups)
                is_call = x86.X86_GRP_CALL in grp or ins.mnemonic == 'call'
                is_jmp = ins.mnemonic.startswith('j')
                if (is_call or is_jmp) and ins.operands and ins.operands[0].type != x86.X86_OP_IMM:
                    self._record(tmp, ins, fs, fe, insl[:k + 1], is_call)
            for v, st in tmp.items():
                if v not in sites:
                    st.gap = True
                    sites[v] = st
            if want_insns is not None:
                for ins in insl:
                    want_insns[ins.address] = ins

    def _record(self, sites, ins, fstart, fend, hist, is_call):
        s = Site()
        s.va = ins.address
        s.fn = fstart
        s.mn = 'call' if is_call else 'jmp'
        s.text = '%s %s' % (ins.mnemonic, ins.op_str)
        s.size = ins.size
        s.raw = bytes(ins.bytes)
        s.gap = False
        s.targets = None
        s.jt = None
        s.ir = None
        d = op_desc(self.cs, ins)
        s.reg = d.get('reg'); s.base = d.get('base'); s.index = d.get('index'); s.scale = d.get('scale'); s.disp = d.get('disp')
        op = ins.operands[0]
        if op.type == x86.X86_OP_REG:
            k = 'reg'
            if not is_call:
                tl = self.resolve_jumptable(hist[:-1], ins, fstart, fend)
                if tl:
                    k = 'jmptable'
                    s.targets = sorted(set(tl))
                    s.jt = self.last_jt
        else:
            if s.base == 'rip':
                slot = ins.address + ins.size + s.disp
                k = 'iat' if slot in self.img.iat else 'rip_data'
                s.disp = slot  # 絶対 slot VA
            elif s.index and not is_call:
                tl = self.resolve_jumptable(hist[:-1], ins, fstart, fend)
                if tl:
                    k = 'jmptable'
                    s.targets = sorted(set(tl))
                    s.jt = self.last_jt
                else:
                    k = 'indexed'
            elif s.index:
                k = 'indexed'
            elif not s.base:
                k = 'abs_mem'
            else:
                k = 'vtable'
        s.kind = k
        sites[s.va] = s


# ---------------------------------------------------------------- IR
CALL_RE = re.compile(r'\bcall\b')
CALLEE_RE = re.compile(r'[@%][\w.$"\-]+\(')
OP_RE = re.compile(r'^\s+(?:%[\w.]+ = )?([a-z_]+)')
FN_DEF_RE = re.compile(r'^define [^\n]*?@function_([0-9a-f]+)\(')


def scan_ir(path):
    """returns dict(fn_defs=set(va), has_addr=bool, addr_kind={va: set(kinds)}, per_fn_ind={fnva: n}, per_fn_calls)"""
    meta = {}
    lines = []
    with open(path, 'r', errors='replace') as f:
        data = f.read()
    for m in re.finditer(r'^!(\d+) = !\{i64 (\d+)\}$', data, re.M):
        meta[m.group(1)] = int(m.group(2))
    fn_defs = []
    addr_kind = collections.defaultdict(set)
    per_fn_ind = collections.Counter()
    per_fn_dir = collections.Counter()
    switch_ncase = collections.Counter()
    cur = None
    n_with_addr = 0
    asm_re = re.compile(r'insn\.addr !(\d+)')
    for line in data.split('\n'):
        if line.startswith('define '):
            m = FN_DEF_RE.match(line)
            cur = int(m.group(1), 16) if m else None
            if cur is not None:
                fn_defs.append(cur)
            continue
        if line.startswith('}'):
            cur = None
            continue
        if cur is None or not line.startswith(' '):
            continue
        am = asm_re.search(line)
        a = meta.get(am.group(1)) if am else None
        if a is not None:
            n_with_addr += 1
        kind = 'other'
        om = OP_RE.match(line)
        opname = om.group(1) if om else '?'
        if CALL_RE.search(line) and '= alloca' not in line and 'declare' not in line[:10]:
            ls = line.split(', !insn.addr')[0]
            idx = ls.find('call ')
            body = ls[idx:] if idx >= 0 else ls
            if ' asm ' in body or body.startswith('call void asm') or ' asm sideeffect' in body:
                kind = 'asm'
            else:
                mm = CALLEE_RE.search(body)
                if mm and mm.group(0).startswith('@'):
                    nm = mm.group(0)[:-1]
                    if nm.startswith('@__asm_') or nm.startswith('@llvm.'):
                        kind = 'intrinsic'
                    elif nm.startswith('@__icall_dispatch'):
                        kind = 'call_ind'
                    else:
                        kind = 'call_dir'
                else:
                    kind = 'call_ind'
        if kind == 'call_ind':
            per_fn_ind[cur] += 1
        elif kind == 'call_dir':
            per_fn_dir[cur] += 1
        if a is not None:
            addr_kind[a].add(kind)
            if kind == 'other':
                addr_kind[a].add('op:' + opname)
    for m in re.finditer(r'switch i\d+ %[\w.]+, label %dec_label_pc_([0-9a-f]+) \[(.*?)\n  \]', data, re.S):
        switch_ncase[int(m.group(1), 16)] = len(re.findall(r'label %dec_label_pc_[0-9a-f]+', m.group(2)))
    return dict(fn_defs=fn_defs, has_addr=n_with_addr > 0, n_with_addr=n_with_addr, addr_kind=addr_kind,
                per_fn_ind=per_fn_ind, per_fn_dir=per_fn_dir, switch_ncase=switch_ncase)


def dsm_icall_vas(path):
    """RetDec dsm 内の間接 call/jmp 命令 VA 集合 (RetDec 自身の disasm が見た間接形)"""
    pat = re.compile(r'^0x([0-9a-f]+):\s+(?:[0-9a-f]{2} )+\s*\t(call|jmp)\s+(.*)$')
    out = {}
    with open(path, 'r', errors='replace') as f:
        for l in f:
            if not l.startswith('0x'):
                continue
            m = pat.match(l)
            if not m:
                continue
            op = m.group(3).strip()
            if re.match(r'^(0x[0-9a-f]+|\w+_[0-9a-f]+)\b', op) and '[' not in op:
                continue  # 直接
            if '<function_' in op:
                continue
            out[int(m.group(1), 16)] = (m.group(2), op)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--ir', action='append', default=[])
    ap.add_argument('--funcs')
    ap.add_argument('--all-pdata', action='store_true')
    ap.add_argument('--dsm', action='append', default=[])
    ap.add_argument('--json')
    ap.add_argument('--sites')
    ap.add_argument('--map', help='icall_rewrite の map.json (jt 比較列の new 区間を引く。switch 畳み込み判定用)')
    ap.add_argument('--label', default='')
    ap.add_argument('--max-fn-size', type=int, default=0x40000)
    a = ap.parse_args()

    img = Image(a.pe)
    dsm_ranges = {}
    dsm_ic = {}
    for d in a.dsm:
        dsm_ranges.update(parse_dsm_ranges(d))
        dsm_ic.update(dsm_icall_vas(d))

    irs = [scan_ir(p) for p in a.ir]
    ir_fns = set()
    for r in irs:
        ir_fns.update(r['fn_defs'])

    if a.funcs:
        fns = []
        for t in open(a.funcs).read().replace(',', '\n').split():
            if t.startswith('#'):
                continue
            lo = t.split('-')[0]
            if '-' in t:
                dsm_ranges[int(lo, 16)] = int(t.split('-')[1], 16)
            fns.append(int(lo, 16))
        fns = sorted(set(fns))
    elif ir_fns:
        fns = sorted(ir_fns)
    elif a.all_pdata:
        fns = sorted(img.pdata)
    else:
        fns = sorted(img.pdata)

    img.set_extra_starts(list(fns) + list(dsm_ranges))
    dis = Disasm(img)
    sites = {}
    norange = []
    ninsn = 0
    for f in fns:
        rg = img.func_range(f)
        if rg:
            fs, fe = rg
        elif f in dsm_ranges:
            fs, fe = f, dsm_ranges[f]
        else:
            norange.append(f)
            continue
        if fe - fs > a.max_fn_size:
            fe = fs + a.max_fn_size
        seen = dis.scan_function(fs, fe, sites)
        ninsn += len(seen)
        dis.gap_sweep(fs, fe, seen, sites)

    # --- 突合
    res = {'label': a.label, 'pe': a.pe, 'nfuncs': len(fns), 'nfuncs_norange': len(norange), 'ninsn': ninsn,
           'ir': a.ir, 'ir_has_insn_addr': [r['has_addr'] for r in irs]}
    addr_kind = collections.defaultdict(set)
    per_fn_ind = collections.Counter()
    per_fn_dir = collections.Counter()
    any_addr = False
    switch_ncase = {}
    for r in irs:
        any_addr |= r['has_addr']
        for k, v in r['addr_kind'].items():
            addr_kind[k] |= v
        per_fn_ind.update(r['per_fn_ind'])
        per_fn_dir.update(r['per_fn_dir'])
        switch_ncase.update(r['switch_ncase'])
    jt_new = {}
    if a.map:
        jt_vas = jt_targets_of(sites)
        for n, l, o in json.load(open(a.map))['insn_ranges']:
            if o in jt_vas:
                jt_new[o] = (n, l)
    status_cnt = collections.defaultdict(collections.Counter)
    gap_sites = [s for s in sites.values() if s.gap]
    res['gap_sites'] = len(gap_sites)
    res['gap_sites_in_retdec_dsm'] = sum(1 for s in gap_sites if s.va in dsm_ic)
    # 主集計は到達可能 site (recursive descent) のみ。gap site は別掲 (RetDec dsm が見ていれば実コードとして主集計に含める)
    sites = {v: s for v, s in sites.items() if not s.gap or v in dsm_ic}
    for va, s in sorted(sites.items()):
        if any_addr:
            ks = addr_kind.get(va, set())
            if 'call_ind' in ks or 'asm' in ks:
                st = 'kept_indirect'
            elif 'call_dir' in ks:
                st = 'resolved_direct'
            elif ks:
                st = 'other_insn:' + ','.join(sorted(k[3:] for k in ks if k.startswith('op:')))
            else:
                st = 'dropped'
            if s.kind == 'jmptable':
                st = 'jt_' + ('present' if ks else 'dropped')
                if not ks and s.va in jt_new and jt_folded(s, jt_new[s.va], switch_ncase):
                    st = 'jt_folded'
        else:
            st = 'n/a'
        s.ir = st
        status_cnt[(s.mn, s.kind)][st] += 1
    res['sites_total'] = len(sites)
    res['rows'] = []
    tot = collections.Counter()
    for (mn, kind), c in sorted(status_cnt.items()):
        row = {'mn': mn, 'kind': kind, 'n': sum(c.values()), 'status': dict(c)}
        res['rows'].append(row)
    call_sites = [s for s in sites.values() if s.mn == 'call']
    res['call_total'] = len(call_sites)
    res['call_non_iat'] = sum(1 for s in call_sites if s.kind != 'iat')
    res['ir_call_ind_total'] = sum(per_fn_ind.values())
    res['ir_call_dir_total'] = sum(per_fn_dir.values())
    if any_addr:
        def lost(x):
            return x.ir == 'dropped' or x.ir.startswith('other_insn')
        res['call_dropped'] = sum(1 for s in call_sites if s.ir == 'dropped')
        res['call_kept'] = sum(1 for s in call_sites if s.ir == 'kept_indirect')
        res['call_resolved_direct'] = sum(1 for s in call_sites if s.ir == 'resolved_direct')
        res['call_other'] = sum(1 for s in call_sites if s.ir.startswith('other_insn'))
        res['call_lost'] = sum(1 for s in call_sites if lost(s))
        res['call_lost_non_iat'] = sum(1 for s in call_sites if lost(s) and s.kind != 'iat')
        tails = [s for s in sites.values() if s.mn == 'jmp' and s.kind not in ('jmptable', 'iat', 'rip_data')]
        res['jmp_tail_sites'] = len(tails)
        res['jmp_tail_lost'] = sum(1 for s in tails if lost(s))
        jts = [s for s in sites.values() if s.kind == 'jmptable']
        res['jmptable_sites'] = len(jts)
        res['jmptable_dropped'] = sum(1 for s in jts if s.ir == 'jt_dropped')
        res['jmptable_folded'] = sum(1 for s in jts if s.ir == 'jt_folded')
    res['fns_with_indirect_call'] = len({s.fn for s in call_sites})
    if dsm_ic:
        res['retdec_dsm_indirect'] = len(dsm_ic)
        res['capstone_in_retdec_dsm'] = sum(1 for v in sites if v in dsm_ic)
    # per-function(IR 総数比較: insn.addr 無し IR 用)
    res['per_fn_cmp'] = [{'fn': hex(f), 'static_call_ind': sum(1 for s in call_sites if s.fn == f and s.kind != 'iat'),
                           'ir_call_ind': per_fn_ind.get(f, 0)} for f in sorted({s.fn for s in call_sites})
                          ][:2000]
    if a.json:
        json.dump({k: v for k, v in res.items()}, open(a.json, 'w'), indent=1, ensure_ascii=False)
    if a.sites:
        json.dump([s.to_dict() for s in sorted(sites.values(), key=lambda s: s.va)],
                  open(a.sites, 'w'), indent=0)
    print_table(res)


def jt_targets_of(sites):
    return {v for v, s in sites.items() if s.kind == 'jmptable'}


def jt_folded(s, new_rg, switch_ncase):
    """jt 比較列が RetDec で switch に畳まれたか: 新区間の終端が switch の default 先で、case 数 = targets-1"""
    n, l = new_rg
    end = n + l
    ncase = switch_ncase.get(end)
    return ncase is not None and s.targets is not None and ncase == len(s.targets) - 1


def print_table(res):
    print('== %s: funcs=%d (range無し %d) insn=%d sites=%d (gap-only %d, うち RetDec dsm 内 %d)' % (res['label'], res['nfuncs'], res['nfuncs_norange'],
                                                                      res['ninsn'], res['sites_total'], res['gap_sites'], res['gap_sites_in_retdec_dsm']))
    print('%-5s %-9s %6s  %s' % ('mn', 'kind', 'n', 'IR status'))
    for r in res['rows']:
        print('%-5s %-9s %6d  %s' % (r['mn'], r['kind'], r['n'], ' '.join('%s=%d' % kv for kv in sorted(r['status'].items()))))
    print('call total=%d (非IAT %d) / fns_with_indirect_call=%d / IR indirect call=%d direct=%d' % (
        res['call_total'], res['call_non_iat'], res['fns_with_indirect_call'], res['ir_call_ind_total'], res['ir_call_dir_total']))
    if 'call_dropped' in res:
        print('call: kept_indirect=%d resolved_direct=%d other_insn=%d dropped=%d  => lost %d (非IAT %d) | tail-jmp %d (lost %d) | jmptable %d (dropped %d, folded %d)' % (
            res['call_kept'], res['call_resolved_direct'], res['call_other'], res['call_dropped'], res['call_lost'], res['call_lost_non_iat'],
            res['jmp_tail_sites'], res['jmp_tail_lost'], res['jmptable_sites'], res['jmptable_dropped'], res['jmptable_folded']))
    if 'retdec_dsm_indirect' in res:
        print('RetDec dsm 内の間接 call/jmp=%d / うち capstone と一致=%d' % (res['retdec_dsm_indirect'], res['capstone_in_retdec_dsm']))


if __name__ == '__main__':
    main()
