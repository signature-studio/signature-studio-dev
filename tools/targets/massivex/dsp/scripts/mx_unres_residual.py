#!/usr/bin/env python3
"""MX-12 の残件 490 件 (再判定後 0 件 458 / 2 件以上 32) と、MX-10 親 18 件の内訳を数える (MX-15 受入 1・2 の計測)。

残件の定義は mx_unres_orig7498.py と同じ (母集団: MX-10 整合候補 0/2/3 件、再判定は redo)。
  - 0 件の候補ごとの失敗理由: mx10:<理由> / plain_decode_fail / plain_no_boundary / plain_prolog_mismatch / chain_parent_absent
  - 2 件以上の候補ごとの判定: plain_ok / chain_ok / 失敗理由
親 18 件: section hit 1 件 (一意) で CHAININFO、親 RUNTIME_FUNCTION が valid .pdata に完全一致で無いもの。

usage: mx_unres_residual.py <pe> [out.json]
"""
import sys, json, struct, collections
import pefile
import capstone
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from mx_unres_decode import full_decode
from mx_unres_prolog import PUSH_REG


def main(path, outp=None):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, 'rb').read()
    secs = pe.sections
    t = [s for s in secs if s.Characteristics & 0x20000000][0]
    pd = [s for s in secs if s.Name.rstrip(b'\0').decode() == '.pdata'][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    raw = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]
    ents = [struct.unpack_from('<III', raw, i) for i in range(0, len(raw) - 11, 12)]
    valid = [(b, e, u) for (b, e, u) in ents if e > b and b and t_lo <= b < t_hi and e <= t_hi]
    valid_exact = set((b, e) for (b, e, u) in valid)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    hits = lambda u: [s for s in secs if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]
    fo = lambda s, r: s.PointerToRawData + (r - s.VirtualAddress)

    def mx10(ub, b, e):
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if ver not in (1, 2):
            return 'mx10:ver'
        if prolog > e - b:
            return 'mx10:prolog>len'
        if cnt > 255:
            return 'mx10:cnt>255'
        if flags & 4:
            return 'ok'
        return 'ok' if cnt > 0 else 'mx10:cnt0'

    def redo(ub, b, e):
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if flags & 4:
            o = 4 + 2 * (cnt + (cnt & 1))
            pb, pe_, _ = struct.unpack_from('<III', ub, o)
            if (pb, pe_) not in valid_exact:
                return 'chain_parent_absent'
            return 'chain_ok' if full_decode(ub, cnt, prolog, ver) else 'chain_decode_fail'
        if not full_decode(ub, cnt, prolog, ver):
            return 'plain_decode_fail'
        ts = [s2 for s2 in secs if s2.VirtualAddress <= b < s2.VirtualAddress + s2.Misc_VirtualSize][0]
        code = data[fo(ts, b): fo(ts, b) + prolog]
        ends = {ins.address - b + ins.size: ins for ins in md.disasm(code, b)}
        for k in range(cnt):
            cc = struct.unpack_from('<H', ub, 4 + 2 * k)[0]
            off, op, info = cc & 0xFF, (cc >> 8) & 0xF, (cc >> 12) & 0xF
            if op == 6:
                continue
            if off not in ends:
                return 'plain_no_boundary'
            if op == 0 and (ends[off].mnemonic != 'push' or ends[off].op_str != PUSH_REG[info]):
                return 'plain_prolog_mismatch'
        return 'plain_ok'

    stat = collections.Counter()
    pats = collections.Counter()
    pdata_begins = set(b for (b, e, u) in ents)
    parents = []
    for b, e, u in valid:
        hs = hits(u)
        if len(hs) == 1:
            ub = data[fo(hs[0], u): fo(hs[0], u) + 524]
            if ub[0] >> 3 & 4:
                o = 4 + 2 * (ub[2] + (ub[2] & 1))
                pb, pe_, _ = struct.unpack_from('<III', ub, o)
                if (pb, pe_) not in valid_exact:
                    stat['parent18'] += 1
                    parents.append((pb, pe_))
            continue
        ubs = [(s, data[fo(s, u): fo(s, u) + 524]) for s in hs]
        m = [mx10(ub, b, e) for _, ub in ubs]
        if sum(x == 'ok' for x in m) not in (0, 2, 3):
            continue
        stat['population'] += 1
        rs = [redo(ub, b, e) if x == 'ok' else x for (_, ub), x in zip(ubs, m)]
        ok = sum(r in ('plain_ok', 'chain_ok') for r in rs)
        stat['redo_%d' % min(ok, 2)] += 1
        if ok != 1:
            pats[('redo_%d' % min(ok, 2), tuple(sorted(rs)))] += 1
    loc = collections.Counter()
    for pb, pe_ in parents:
        loc['begin_in_pdata' if pb in pdata_begins else 'begin_not_in_pdata'] += 1
        loc['begin_in_text' if t_lo <= pb < t_hi else 'begin_not_in_text'] += 1
        loc['end_in_text' if t_lo <= pe_ <= t_hi else 'end_not_in_text'] += 1
    out = {
        'pe': path,
        'valid_in_text': len(valid),
        'counts': dict(sorted(stat.items())),
        'parent18_location': dict(sorted(loc.items())),
        'residual_patterns': [[k, list(p), n] for (k, p), n in pats.most_common()],
    }
    if outp:
        json.dump(out, open(outp, 'w'), indent=1)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
