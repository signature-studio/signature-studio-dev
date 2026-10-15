"""PE(x64) 読取 + 機械語静的解析 (capstone): 関数ごとの間接呼出し・FP 比較・arity 推定。"""
import struct
import capstone
from capstone import x86_const as X

import pefile


class PE:
    def __init__(self, path):
        self.path = path
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.size = self.pe.OPTIONAL_HEADER.SizeOfImage
        self.sections = []
        for s in self.pe.sections:
            nm = s.Name.rstrip(b'\0').decode('latin1')
            self.sections.append(dict(name=nm, rva=s.VirtualAddress, vsize=s.Misc_VirtualSize, rawsize=s.SizeOfRawData,
                                      flags=s.Characteristics, data=s.get_data()))
        self.imp_lo = self.imp_hi = 0
        d = self.pe.OPTIONAL_HEADER.DATA_DIRECTORY[12]   # IAT
        if d.VirtualAddress:
            self.imp_lo, self.imp_hi = d.VirtualAddress, d.VirtualAddress + d.Size
        else:
            for s in self.sections:
                if s['name'] == '.idata':
                    self.imp_lo, self.imp_hi = s['rva'], s['rva'] + s['vsize']
        self._text = None

    def write_ranges(self):
        """差分比較する writable 範囲 [(rva, len)] (.idata は除外: native は IAT に thunk を書くため)"""
        out = []
        for s in self.sections:
            if (s['flags'] & 0x80000000) and s['name'] not in ('.idata', '.tls', '.rsrc'):
                out.append((s['rva'], max(s['vsize'], s['rawsize'])))
        return out

    def read(self, rva, n):
        for s in self.sections:
            if s['rva'] <= rva < s['rva'] + max(s['vsize'], s['rawsize']):
                off = rva - s['rva']
                return s['data'][off:off + n]
        return b''

    def in_iat(self, rva):
        return self.imp_lo <= rva < self.imp_hi


CALLER_SAVED = {X.X86_REG_RAX, X.X86_REG_RCX, X.X86_REG_RDX, X.X86_REG_R8, X.X86_REG_R9, X.X86_REG_R10, X.X86_REG_R11}
# packed-int (MMX/SSE2 整数) 命令の接頭辞 — clift (x64c) の類型判定用ヒューリスティック
SIMDINT_PRE = ('punpck', 'padd', 'psub', 'pmul', 'pack', 'pcmp', 'pshuf', 'psll', 'psrl', 'psra',
               'pmax', 'pmin', 'pand', 'por', 'pxor', 'palignr', 'pblend', 'phadd', 'phsub', 'psadbw', 'pavgb', 'pavgw')
ARG_GPR = [(X.X86_REG_RCX, X.X86_REG_ECX, X.X86_REG_CX, X.X86_REG_CL), (X.X86_REG_RDX, X.X86_REG_EDX, X.X86_REG_DX, X.X86_REG_DL),
           (X.X86_REG_R8, X.X86_REG_R8D, X.X86_REG_R8W, X.X86_REG_R8B), (X.X86_REG_R9, X.X86_REG_R9D, X.X86_REG_R9W, X.X86_REG_R9B)]
GPR_ALIAS = {}
for i, grp in enumerate(ARG_GPR):
    for r in grp:
        GPR_ALIAS[r] = i
XMM_ARG = {X.X86_REG_XMM0: 0, X.X86_REG_XMM1: 1, X.X86_REG_XMM2: 2, X.X86_REG_XMM3: 3}
FPCMP = {X.X86_INS_COMISD, X.X86_INS_COMISS, X.X86_INS_UCOMISD, X.X86_INS_UCOMISS, X.X86_INS_VCOMISD, X.X86_INS_VCOMISS, X.X86_INS_VUCOMISD, X.X86_INS_VUCOMISS}
ZERO_IDIOM = {'xorps', 'xorpd', 'pxor', 'xor', 'subsd', 'subss', 'subps'}


class Analyzer:
    def __init__(self, pe: PE):
        self.pe = pe
        self.cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.cs.detail = True
        self.text = None
        for s in pe.sections:
            if s['name'] == '.text':
                self.text = s

    def _dis(self, rva, n=15):
        t = self.text
        off = rva - t['rva']
        if off < 0 or off >= len(t['data']):
            return None
        for ins in self.cs.disasm(t['data'][off:off + n], pe_base(self.pe) + rva, 1):
            return ins
        return None

    def analyze(self, va, max_ins=3000, zero_idiom=False):
        """VA の関数を制御フロー追跡し特徴を返す。zero_idiom=True なら xmm の同一レジスタ読みを
        ゼロ化イディオム (xorps r,r 等) とみなし xmm_slots から除く (#2850。既定 False は従来どおり)"""
        base = self.pe.base
        rva0 = va - base
        seen = set()
        work = [rva0]
        icall = ijmp = 0
        fpcmp = 0
        simdint = 0
        calls = []
        packed = 0
        repstr = 0
        n = 0
        rsp_ops = {}
        # arity 用: 順方向データフロー (rva -> defined set)
        defined_in = {rva0: frozenset()}
        used_args = set()
        used_x = set()
        stack_args = set()
        # rsp 追跡 (entry からの相対 off / rbp 相対)
        state = {rva0: (0, None)}   # rva -> (rsp_off, rbp_off)
        order = []
        done = {}   # rva -> 最後に処理したときの defined_in (変わったときだけ再処理する。#3708)
        while work and n < max_ins:
            rva = work.pop()
            if rva in done and done[rva] == defined_in.get(rva, frozenset()):
                continue
            first = rva not in seen
            seen.add(rva)
            done[rva] = defined_in.get(rva, frozenset())
            ins = self._dis(rva)
            if ins is None:
                continue
            if first:
                n += 1
            defs = defined_in.get(rva, frozenset())
            rsp_off, rbp_off = state.get(rva, (0, None))
            mn = ins.mnemonic
            nxt = rva + ins.size
            # --- 特徴 (初回のみ数える) ---
            if first and ins.id in FPCMP:
                fpcmp += 1
            if first and (mn.startswith(SIMDINT_PRE) or mn in ('movq', 'movd')):
                simdint += 1
            if first and mn.startswith('rep'):
                repstr += 1
            if first and (ins.group(capstone.CS_GRP_CALL) or ins.group(capstone.CS_GRP_JUMP)):
                op = ins.operands[0] if ins.operands else None
                is_call = ins.group(capstone.CS_GRP_CALL)
                if op is not None and op.type == capstone.CS_OP_IMM:
                    tgt = op.imm - base
                    if is_call:
                        calls.append(op.imm)
                else:
                    memrip = op is not None and op.type == capstone.CS_OP_MEM and op.mem.base == X.X86_REG_RIP
                    iat = False
                    if memrip:
                        tgt_rva = nxt + op.mem.disp
                        iat = self.pe.in_iat(tgt_rva)
                    if not iat:
                        if is_call:
                            icall += 1
                        elif not ins.group(capstone.CS_GRP_RET):
                            ijmp += 1
            # --- arity データフロー (合流点の定義の交わりが縮んだら再処理する) ---
            try:
                rr, wr = ins.regs_access()
            except Exception:
                rr, wr = [], []
            zero = zero_idiom and mn in ZERO_IDIOM and len(ins.operands) == 2 and ins.operands[0].type == 1 \
                and ins.operands[1].type == 1 and ins.operands[0].reg == ins.operands[1].reg
            for r in rr:
                if r in GPR_ALIAS and GPR_ALIAS[r] not in defs:
                    # xor ecx,ecx のような自己 xor は読みでない
                    if not (mn in ('xor', 'sub') and len(ins.operands) == 2 and ins.operands[0].type == 1 and ins.operands[1].type == 1 and ins.operands[0].reg == ins.operands[1].reg):
                        used_args.add(GPR_ALIAS[r])
                if r in XMM_ARG and ('x', XMM_ARG[r]) not in defs and not zero:
                    used_x.add(XMM_ARG[r])
            nd = set(defs)
            for r in wr:
                if r in GPR_ALIAS:
                    nd.add(GPR_ALIAS[r])
                if r in XMM_ARG:
                    nd.add(('x', XMM_ARG[r]))
            # mov [rsp+8..0x20], rcx 等のホーム保存は「読み」として used に入る (レジスタ read) — 正しい
            # スタック引数: [rsp+disp] / [rbp+disp] (disp 解決後 entry+0x28 以上)
            for op in ins.operands:
                if op.type == capstone.CS_OP_MEM:
                    if op.mem.base == X.X86_REG_RSP and op.mem.index == 0:
                        o = rsp_off + op.mem.disp
                    elif op.mem.base == X.X86_REG_RBP and op.mem.index == 0 and rbp_off is not None:
                        o = rbp_off + op.mem.disp
                    else:
                        continue
                    if o >= 0x28 and o < 0x28 + 8 * 8:
                        stack_args.add((o - 0x28) // 8)
            # rsp/rbp 更新
            if mn == 'push':
                rsp_off -= 8
            elif mn == 'pop':
                rsp_off += 8
            elif mn == 'sub' and ins.operands[0].type == 1 and ins.operands[0].reg == X.X86_REG_RSP and ins.operands[1].type == 2:
                rsp_off -= ins.operands[1].imm
            elif mn == 'add' and ins.operands[0].type == 1 and ins.operands[0].reg == X.X86_REG_RSP and ins.operands[1].type == 2:
                rsp_off += ins.operands[1].imm
            elif mn == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == 1 and ins.operands[0].reg == X.X86_REG_RBP and ins.operands[1].type == 1 and ins.operands[1].reg == X.X86_REG_RSP:
                rbp_off = rsp_off
            elif mn == 'lea' and ins.operands[0].type == 1 and ins.operands[0].reg == X.X86_REG_RBP and ins.operands[1].mem.base == X.X86_REG_RSP:
                rbp_off = rsp_off + ins.operands[1].mem.disp
            if ins.group(capstone.CS_GRP_CALL):
                for r in CALLER_SAVED:
                    pass
                # 呼出し後: 引数レジスタは clobber されたとみなし「定義済」にして誤検出を避ける
                nd |= {0, 1, 2, 3}
                nd |= {('x', i) for i in range(4)}
            fs = frozenset(nd)
            succ = []
            if ins.group(capstone.CS_GRP_RET):
                pass
            elif ins.group(capstone.CS_GRP_JUMP):
                op = ins.operands[0] if ins.operands else None
                if op is not None and op.type == capstone.CS_OP_IMM:
                    t = op.imm - base
                    succ.append(t)
                    if mn != 'jmp':
                        succ.append(nxt)
                elif mn != 'jmp':
                    succ.append(nxt)
            else:
                succ.append(nxt)
            for s in succ:
                if s in defined_in:
                    defined_in[s] = defined_in[s] & fs
                else:
                    defined_in[s] = fs
                    state[s] = (rsp_off, rbp_off)
                if s not in done or done[s] != defined_in[s]:
                    work.append(s)
        arity_gpr = (max(used_args) + 1) if used_args else 0
        return dict(ins=n, icall=icall, ijmp=ijmp, fpcmp=fpcmp, simdint=simdint, calls=sorted(set(calls)), repstr=repstr,
                    arity_gpr=arity_gpr, arity_x=(max(used_x) + 1) if used_x else 0,
                    xmm_slots=sorted(used_x),
                    stack_args=sorted(stack_args), truncated=bool(work))


def pe_base(pe):
    return pe.base
