#!/usr/bin/env python3
"""MX-63 (#5908): 非境界 G の判定を、線形復号でなく制御フローの再帰降下で行う。

各非境界 G について次を数える。
  - cf_from_fn: pdata 関数先頭から直接制御フロー (fallthrough・直接 jmp/jcc/call の飛び先) で G に到達する
                (= G は関数内の命令境界として実行経路に現れる)。
  - self_ret:   G から同じ規則で復号したとき、(bad) に当たらず ret に到達する (G 単独の復号が閉じる)。
  - bad_on_path: G 起点の復号で (bad) に当たった経路が残る (G が埋め込みデータ・復号誤りの可能性)。
間接 jmp/call・関数外への飛び先は追わない (未確認として数える)。
usage: mx63_g_recdesc.py <pe> <contain.json> <out.json>
"""
import json
import sys

import capstone
import pefile


def main(pe_path, contain_p, out_p):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = text.VirtualAddress
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.Misc_VirtualSize]
    funcs = {}
    for i in range(0, len(praw) - 11, 12):
        st = int.from_bytes(praw[i:i + 4], 'little')
        e = int.from_bytes(praw[i + 4:i + 8], 'little')
        if st and e > st:
            funcs[st] = e
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    d = json.load(open(contain_p))

    def code_at(rva):
        off = text.PointerToRawData + (rva - t_lo)
        return data[off:off + 16]

    def walk(roots, lo, hi):
        seen, bad, indirect, ret = set(), set(), 0, 0
        stack = list(roots)
        while stack:
            a = stack.pop()
            if a in seen or a in bad or not (lo <= a < hi):
                continue
            ins = next(md.disasm(code_at(a), a + base, 1), None)
            if ins is None:
                bad.add(a)
                continue
            seen.add(a)
            m, nxt = ins.mnemonic, a + ins.size
            tgt = None
            if ins.op_str.startswith('0x') and (m.startswith('j') or m == 'call'):
                tgt = int(ins.op_str, 16) - base
            if m == 'ret' or m in ('ud2', 'int3', 'hlt'):
                ret += 1
            elif m == 'jmp':
                if tgt is None:
                    indirect += 1
                else:
                    stack.append(tgt)
            elif m == 'call':
                stack.append(nxt)
            elif m.startswith('j'):
                if tgt is None:
                    indirect += 1
                else:
                    stack.append(tgt)
                stack.append(nxt)
            else:
                stack.append(nxt)
        return seen, bad, indirect, ret

    rows = []
    for s in d['sites']:
        if s['class'] != 'mid_function_not_boundary':
            continue
        g, fs = int(s['G'], 16), int(s['G_fn'], 16)
        fe = funcs[fs]
        fseen, fbad, find, _ = walk([fs], fs, fe)
        g_from_fn = g in fseen
        gseen, gbad, gind, gret = walk([g], fs, fe)
        rows.append({'site': s['site'], 'G': hex(g), 'G_fn': hex(fs),
                     'fn_end': hex(fe), 'cf_from_fn': g_from_fn,
                     'fn_bad_on_path': len(fbad), 'fn_indirect': find,
                     'self_ret': gret > 0, 'self_bad': len(gbad), 'self_indirect': gind})
    cat = {}
    for r in rows:
        if r['cf_from_fn']:
            k = 'reached_from_fn_start'
        elif r['self_ret'] and r['self_bad'] == 0:
            k = 'self_closed_no_bad'
        elif r['self_ret']:
            k = 'self_ret_with_bad'
        else:
            k = 'undetermined'
        r['class'] = k
        cat[k] = cat.get(k, 0) + 1
    print('MX-63 recdesc (non-boundary G): n=%d %s' % (len(rows), json.dumps(cat)))
    json.dump({'summary': cat, 'rows': rows}, open(out_p, 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
