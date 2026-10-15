#!/usr/bin/env python3
"""SR-57 #3626: 0x1800501c0 (show_msg_helper) の呼出元と demo 表示経路の到達性を、patch 前後の機械語で静的に確認する。

入力: 原 PE と patch 済み PE (license/authstub/mpatch.py の出力)。
方法:
  1. .pdata の関数境界で .text を線形走査し、直接 call/jmp (rel32) の宛先を索引化する。
  2. 対象 VA の呼出元 site ごとに、所属関数の内部 CFG (jcc・jmp・ret・fallthrough) で entry から site への到達を判定する。
  3. 関数の上位 (呼出元の連鎖) は逆向き BFS で辿る。根 (root) は、直接の呼出元が無い関数・.rdata に関数ポインタとして
     現れる関数 (間接呼出で到達しうる)。根に届けば「到達可能 (未証明)」、届かなければ「到達不能 (証明)」。
  4. site 直前の lea [rip+disp] を辿り、引数の文字列を読む (ASCII / UTF-16LE)。
usage: demo_dialog_reach.py <pe_orig> <pe_patched> [--target 0x1800501c0]
"""
import struct
import sys
from collections import deque

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM
from capstone.x86 import X86_REG_RIP

ARGS = sys.argv[1:]
TARGET = 0x1800501C0
if '--target' in ARGS:
    k = ARGS.index('--target')
    TARGET = int(ARGS[k + 1], 16)
    del ARGS[k:k + 2]


class Image:
    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.raw = open(path, 'rb').read()
        self.img = self.pe.OPTIONAL_HEADER.ImageBase
        self.secs = {s.Name.rstrip(b'\0').decode(): s for s in self.pe.sections}

    def off(self, va):
        rva = va - self.img
        for s in self.pe.sections:
            span = max(s.Misc_VirtualSize, s.SizeOfRawData)
            if s.VirtualAddress <= rva < s.VirtualAddress + span:
                return s.PointerToRawData + (rva - s.VirtualAddress)
        return None

    def read(self, va, n):
        o = self.off(va)
        return self.raw[o:o + n] if o is not None else b''

    def sec_range(self, name):
        s = self.secs[name]
        lo = self.img + s.VirtualAddress
        return lo, lo + max(s.Misc_VirtualSize, s.SizeOfRawData)

    def functions(self):
        s = self.secs['.pdata']
        pd = self.raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        lo, hi = self.sec_range('.text')
        out = []
        for i in range(0, len(pd) - 11, 12):
            b, e, _ = struct.unpack_from('<III', pd, i)
            b, e = self.img + b, self.img + e
            if lo <= b < hi and b < e:
                out.append((b, e))
        out.sort()
        return out


MD = Cs(CS_ARCH_X86, CS_MODE_64)
MD.detail = True


def disasm(img, b, e):
    return list(MD.disasm(img.read(b, e - b), b))


def succs(ins, lo, hi):
    """(後続 VA のリスト, 間接 jmp か) を返す。関数外への jmp は後続なし (tail jump)。"""
    m = ins.mnemonic
    nxt = ins.address + ins.size
    if m == 'ret' or m in ('ud2', 'hlt', 'int3') or m.startswith('int'):
        return [], False
    if m == 'jmp':
        op = ins.operands[0]
        if op.type == CS_OP_IMM:
            return ([op.imm] if lo <= op.imm < hi else []), False
        return [], True
    if m.startswith('j'):
        op = ins.operands[0]
        t = [op.imm] if op.type == CS_OP_IMM else []
        return t + [nxt], False
    return [nxt], False


def reach_set(insns, lo, hi):
    by = {i.address: i for i in insns}
    seen, q, indirect = {lo}, deque([lo]), 0
    while q:
        a = q.popleft()
        ins = by.get(a)
        if ins is None:
            continue
        s, ind = succs(ins, lo, hi)
        indirect += ind
        for t in s:
            if t in by and t not in seen:
                seen.add(t)
                q.append(t)
    return seen, indirect


def cstr(img, va):
    raw = img.read(va, 200)
    a = raw.split(b'\0')[0]
    u = b''
    for i in range(0, len(raw) - 1, 2):
        if raw[i + 1] != 0 or raw[i] == 0:
            break
        u += bytes([raw[i]])
    cand = []
    if len(a) >= 4 and all(32 <= c < 127 for c in a):
        cand.append(a.decode())
    if len(u) >= 4 and all(32 <= c < 127 for c in u):
        cand.append(u.decode())
    return max(cand, key=len) if cand else ''


def arg_strings(img, insns, idx):
    """call の直前 12 命令から lea reg,[rip+disp] の参照先文字列を拾う。"""
    out = []
    for ins in insns[max(0, idx - 12):idx]:
        if ins.mnemonic == 'lea' and len(ins.operands) == 2 and ins.operands[1].type == CS_OP_MEM:
            m = ins.operands[1].mem
            if m.base == X86_REG_RIP:
                va = ins.address + ins.size + m.disp
                s = cstr(img, va)
                if s:
                    out.append(f'{va:#x}:"{s[:60]}"')
    return out


def main():
    paths = ARGS[:2]
    orig, patched = Image(paths[0]), Image(paths[1])
    funcs_o = orig.functions()
    # 1. 直接 call/jmp の索引 (call 先の索引は patch で変わらない)
    callers = {}
    for b, e in funcs_o:
        for ins in disasm(orig, b, e):
            if ins.mnemonic in ('call', 'jmp') and ins.operands[0].type == CS_OP_IMM:
                callers.setdefault(ins.operands[0].imm, []).append((ins.address, b, e))

    # .rdata の 8 byte 値の集合 (関数ポインタ・vtable 要素。間接呼出で到達しうる)
    rs_ = orig.secs['.rdata']
    rd = orig.raw[rs_.PointerToRawData:rs_.PointerToRawData + rs_.SizeOfRawData]
    rd = rd[:len(rd) // 8 * 8]
    rd_ptr = set(struct.unpack_from('<%dQ' % (len(rd) // 8), rd))

    def intra(img, fn):
        b, e = fn
        insns = disasm(img, b, e)
        rs, ind = reach_set(insns, b, e)
        return insns, rs, ind

    sites = callers.get(TARGET, [])
    print(f'# target {TARGET:#x}: 直接 call/jmp の呼出元 {len(sites)} 件')
    for site, b, e in sorted(sites):
        ins_o, rs_o, ind_o = intra(orig, (b, e))
        ins_p, rs_p, ind_p = intra(patched, (b, e))
        idx_o = next(k for k, i in enumerate(ins_o) if i.address == site)
        idx_p = next((k for k, i in enumerate(ins_p) if i.address == site), None)
        s_args = arg_strings(orig, ins_o, idx_o)
        print(f'- site {site:#x} in fn {b:#x}-{e:#x} (size {e - b})')
        in_p = (site in rs_p) if idx_p is not None else 'decode-miss'
        print(f'  intra-reach orig={site in rs_o} patched={in_p} indirect-jmp(orig/patched)={ind_o}/{ind_p}')
        print(f'  args: {s_args if s_args else "-"}')
        print(f'  fn entry in .rdata as fnptr: {"yes" if b in rd_ptr else "no"}')

    # 2. 上位の到達: 逆向き BFS (patched の intra 到達を使う)
    def root_kind(fn):
        b, e = fn
        if b in rd_ptr:
            return 'vtable/fnptr (間接)'
        if not callers.get(b):
            return 'no direct caller (EH funclet・間接の可能性)'
        return None

    def may_reach(target_fn):
        """target_fn の entry に至る呼出連鎖のうち、根まで届くものを返す (patched)。"""
        prev = {target_fn: None}
        q = deque([target_fn])
        while q:
            f = q.popleft()
            rk = root_kind(f)
            if rk:
                chain = []
                cur = f
                while cur is not None:
                    chain.append(cur)
                    cur = prev[cur]
                return rk, chain
            for site, cb, ce in callers.get(f[0], []):
                g = (cb, ce)
                if g in prev:
                    continue
                ins_p, rs_p, _ = intra(patched, g)
                if site in rs_p:
                    prev[g] = f
                    q.append(g)
        return None, None

    print('\n# 判定 (patched): 関数内 CFG で site に届くか → 届くなら上位連鎖を逆向き BFS で根まで辿る')
    for site, b, e in sorted(sites):
        ins_p, rs_p, ind_p = intra(patched, (b, e))
        if site not in rs_p and ind_p == 0:
            print(f'- {site:#x}: 関数内 CFG で entry から到達不能 (間接 jmp 0) → 到達不能 (証明)')
        elif site not in rs_p:
            print(f'- {site:#x}: 関数内で未到達だが間接 jmp {ind_p} 件あり → 判定保留')
        else:
            rk, chain = may_reach((b, e))
            if rk is None:
                print(f'- {site:#x}: 関数内で到達; 上位は根に届かず → 到達不能 (証明)')
            else:
                print(f'- {site:#x}: 関数内で到達; 根に届く → 到達可能 (未証明) 根={rk}; 連鎖=' +
                      ' <- '.join(f'{c[0]:#x}' for c in chain))


if __name__ == '__main__':
    main()
