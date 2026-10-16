#!/usr/bin/env python3
"""MX-63 (#5908): 先頭から到達する G (4 件) について、xmm4/5 の入口値が転送経路で G に届くかを判定する。

各 G について次を数える (明示オペランドの access で読む。capstone の regs_read/regs_write は VEX 命令で誤るため使わない)。
  - caller:      G へ直接 call/jmp rel32 する転送 site (全 text を走査し、その site の pdata 関数を線形復号して
                 命令先頭と一致するものだけを採る。命令境界でない E8/E9 バイトは site に数えない)
  - F_reach:     転送元 F の入口から転送 site まで、intra-function の経路が存在する (書き込みは問わない)
  - F_undef:     F_reach かつ、その経路のどれも xmm4/5 を書かない (= site での xmm4/5 が F の入口値の可能性がある)
                 F_reach=False の site は「未判定」として別に数える (未定義の証拠にしない)
  - G_livein:    G から書き込みより前に xmm4/5 を読む経路がある (= G が入口で値を要求する可能性がある)
  - G_reach:     F_G (G を含む pdata 関数) の先頭から、xmm4/5 を書かずに G へ到達できる経路がある (出力キーは G_reach_undef)
判定は経路の存在による over/under の混在を含む。間接 jmp・call の飛び先は追わない。.text 外へ広がる pdata 範囲は関数として採らない。
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
        # .text 外へ広がる不正な pdata 範囲 (最大 4 GB・100 件) は関数として採らない。
        # 採ると insn_starts が範囲全体を復号してメモリを使い切る (実測: G 0x1a11e00 で kill)。
        if st and e > st and t_lo <= st and e <= t_lo + t_size:
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

    def insn_starts(lo, hi):
        """[lo, hi) を先頭から線形に復号し、命令先頭 (RVA) の集合を返す。復号できないバイトは 1 byte 進める。"""
        starts = {}
        a = lo
        while a < hi:
            ins = decode(a)
            if ins is None:
                a += 1
                continue
            starts[a] = ins
            a += ins.size
        return starts

    def ins_regs(ins):
        # 明示オペランドの access で xmm4/5 の読み書きを見る。
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

    def reachable(start, lo, hi, target):
        """start から target へ intra-function の経路があるか (書き込みは問わない)。"""
        seen, stack = set(), [start]
        while stack:
            a = stack.pop()
            if a == target:
                return True
            if a in seen:
                continue
            seen.add(a)
            ins = decode(a)
            if ins is None:
                continue
            stack.extend(succs(ins, lo, hi))
        return False

    def must_undef(start, lo, hi, target):
        """start から target までの全経路で xmm4/5 が未定義か (書き込みを経由する経路が 1 本も無い)。
        状態は (命令, 既に書かれたか)。書かれた状態で target に届く経路があれば False。
        target に届かない場合は呼び出し側で reachable を見ること (この関数は True を返し得る)。"""
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

    # 全 text から E8/E9 rel32 の直接 call/jmp の候補を走査し、G への候補を採る (命令境界は後で確かめる)
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
        cands = site_of.get(g, [])
        row = {'G': hex(g + base), 'candidates': [hex(s + base) for s in cands],
               'sites': [], 'not_insn_boundary': [], 'caller_no_pdata': [],
               'F_reach_no': [], 'F_undef': [], 'F_defined': []}
        starts_cache = {}
        for s in cands:
            fn = fn_of(s)
            if fn is None:
                row['caller_no_pdata'].append(hex(s + base))
                continue
            flo, fhi = fn
            if flo not in starts_cache:
                starts_cache[flo] = insn_starts(flo, fhi)
            ins = starts_cache[flo].get(s)
            if ins is None or ins.mnemonic not in ('call', 'jmp'):
                row['not_insn_boundary'].append(hex(s + base))
                continue
            row['sites'].append(hex(s + base))
            if not reachable(flo, flo, fhi, s):
                row['F_reach_no'].append(hex(s + base))
            elif must_undef(flo, flo, fhi, s):
                row['F_undef'].append(hex(s + base))
            else:
                row['F_defined'].append(hex(s + base))
        gfn = fn_of(g)
        if gfn is not None:
            glo, ghi = gfn
            row['F_G'] = hex(glo + base)
            g_reach = reachable(glo, glo, ghi, g)
            row['G_reach_no'] = not g_reach
            row['G_reach_undef'] = g_reach and must_undef(glo, glo, ghi, g)
            row['G_livein_read'] = livein_read(g, glo, ghi)
        row['counts'] = {
            'candidates': len(cands),
            'sites_insn': len(row['sites']),
            'not_insn_boundary': len(row['not_insn_boundary']),
            'caller_no_pdata': len(row['caller_no_pdata']),
            'F_reach_no': len(row['F_reach_no']),
            'F_undef': len(row['F_undef']),
            'F_defined': len(row['F_defined']),
        }
        rows.append(row)
    json.dump(rows, open(out_p, 'w'), indent=1)
    for r in rows:
        print(r)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
