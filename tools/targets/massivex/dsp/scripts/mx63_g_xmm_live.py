#!/usr/bin/env python3
"""MX-63 (#5908): 先頭から到達する G (4 件) について、xmm4/5 の入口値が転送経路で G に届くかを判定する。

各 G について次を数える (capstone の regs_read/regs_write を使う)。
  - caller:      G へ直接 call/jmp rel32 する転送 site (全 text を走査し、1 本だけ採る)
  - F_undef:     転送元 F の入口から転送 site まで、xmm4/5 を書かずに到達できる経路がある
                 (= 転送 site での xmm4/5 が F の入口値の可能性がある)
  - G_livein:    G から書き込みより前に xmm4/5 を読む経路がある (= G が入口で値を要求する可能性がある)
  - G_reach:     F_G (G を含む pdata 関数) の先頭から、xmm4/5 を書かずに G へ到達できる経路がある
判定は経路の存在による over/under の混在を含む。間接 jmp・call の飛び先は追わない。
usage: mx63_g_xmm_live.py <pe> <out.json> <G_rva_hex>... (G は RVA)
"""
import json
import sys

import capstone
import pefile

def main(pe_path, out_p):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = text.VirtualAddress
    t_raw = text.PointerToRawData
    t_size = min(text.SizeOfRawData, text.Misc_VirtualSize)
    tbytes = data[t_raw:t_raw + t_size]
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.Misc_VirtualSize]
    funcs = {}
    for i in range(0, len(praw) - 11, 12):
        st = int.from_bytes(praw[i:i + 4], 'little')
        e = int.from_bytes(praw[i + 4:i + 8], 'little')
        if st and e > st:
            funcs[st] = e
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    reg_ids = {'4', '5'}
    gs = [int(x, 16) for x in sys.argv[3:]]

    def fn_of(rva):
        hit = [(e - st, st, e) for st, e in funcs.items() if st <= rva < e]
        if not hit:
            return None
        _, st, e = min(hit)
        return st, e

    def decode(rva):
        off = rva - t_lo
        if off < 0 or off >= len(tbytes):
            return None
        return next(md.disasm(tbytes[off:off + 16], rva + base, 1), None)

    def ins_regs(ins):
        # capstone の regs_read/regs_write は VEX 命令で誤るため、明示オペランドの access で読む。
        # call は呼び先が xmm4/5 を書き得るので書き込み扱い (経路を殺す側に倒す)。
        r, w = set(), set()
        for o in ins.operands:
            if o.type != capstone.x86.X86_OP_REG:
                continue
            name = ins.reg_name(o.reg) or ''
            if name[:3] not in ('xmm', 'ymm', 'zmm') or name[3:] not in ('4', '5'):
                continue
            if o.access & capstone.CS_AC_READ:
                r.add(name[3:])
            if o.access & capstone.CS_AC_WRITE:
                w.add(name[3:])
        if ins.mnemonic == 'call':
            w |= {'4', '5'}
        return r, w

    def succs(ins, lo, hi):
        a = ins.address - base
        m, nxt = ins.mnemonic, a + ins.size
        out = []
        if m == 'ret' or m in ('ud2', 'int3', 'hlt'):
            return out
        tgt = None
        if ins.op_str.startswith('0x') and (m.startswith('j') or m == 'call'):
            tgt = int(ins.op_str, 16) - base
        if m == 'jmp':
            if tgt is not None and lo <= tgt < hi:
                out.append(tgt)
            return out
        if m.startswith('j') and tgt is not None and lo <= tgt < hi:
            out.append(tgt)
        out.append(nxt)
        return [x for x in out if lo <= x < hi]

    def must_undef(start, lo, hi, target):
        """start から target までの全経路で xmm4/5 が未定義か (書き込みを経由する経路が 1 本も無い)。
        状態は (命令, 既に書かれたか)。書かれた状態で target に届く経路があれば False。"""
        seen, stack = set(), [(start, False)]
        while stack:
            a, wrote = stack.pop()
            if a == target and wrote:
                return False
            if (a, wrote) in seen or a == target:
                continue
            seen.add((a, wrote))
            ins = decode(a)
            if ins is None:
                continue
            _, w = ins_regs(ins)
            nw = wrote or bool(w)
            for s in succs(ins, lo, hi):
                stack.append((s, nw))
        return True

    def livein_read(start, lo, hi):
        """start から、書き込みより前に xmm4/5 を読む経路があるか。"""
        seen, stack = set(), [(start, frozenset())]
        while stack:
            a, defd = stack.pop()
            if (a, defd) in seen:
                continue
            seen.add((a, defd))
            ins = decode(a)
            if ins is None:
                continue
            r, w = ins_regs(ins)
            if r - defd:
                return True
            nd = frozenset(defd | w)
            if nd >= reg_ids:
                continue
            for s in succs(ins, lo, hi):
                stack.append((s, nd))
        return False

    # 全 text から E8/E9 rel32 の直接 call/jmp を走査し、G への転送 site を採る
    site_of = {}
    for g in gs:
        site_of[g] = []
    for i in range(len(tbytes) - 5):
        op = tbytes[i]
        if op not in (0xE8, 0xE9):
            continue
        rel = int.from_bytes(tbytes[i + 1:i + 5], 'little', signed=True)
        a = t_lo + i
        tgt = a + 5 + rel
        if tgt in site_of:
            site_of[tgt].append(a)

    rows = []
    for g in gs:
        sites = site_of.get(g, [])
        row = {'G': hex(g + base), 'sites': [hex(s + base) for s in sites]}
        for s in sites:
            fn = fn_of(s)
            if fn is None:
                row.setdefault('caller_no_pdata', []).append(hex(s + base))
                continue
            flo, fhi = fn
            row.setdefault('F_must_undef', []).append(must_undef(flo, flo, fhi, s))
        gfn = fn_of(g)
        if gfn is not None:
            glo, ghi = gfn
            row['F_G'] = hex(glo + base)
            row['G_reach_undef'] = must_undef(glo, glo, ghi, g)
            row['G_livein_read'] = livein_read(g, glo, ghi)
        rows.append(row)
    json.dump(rows, open(out_p, 'w'), indent=1)
    for r in rows:
        print(r)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
