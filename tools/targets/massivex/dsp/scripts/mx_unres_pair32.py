#!/usr/bin/env python3
"""MX-49 受入 2: 再判定後 2 件以上の 32 件 (候補がすべて plain_ok) を区別できるかを実測する。

各 pair について候補ごとの UNWIND_INFO 欄 (ver / flags / prolog / cnt / 先頭 cnt 個の CodeOffset) と
親 RUNTIME_FUNCTION の (begin, end) を並べ、どの欄も候補間で一致しないかを数える。
区別規則の候補は「候補間で値が異なる欄」のうち既存の規則 (mx10 / plain) に無いものだけ。

usage: mx_unres_pair32.py <pe> [out.json]
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
    hits = lambda u: [s for s in secs if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]
    fo = lambda s, r: s.PointerToRawData + (r - s.VirtualAddress)

    def mx10_ok(ub, b, e):
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if ver not in (1, 2) or prolog > e - b or cnt > 255:
            return False
        return bool(flags & 4) or cnt > 0

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def plain_ok(ub, b, e, ts_sec):
        # redo() の plain 分岐と同じ判定 (復号 → 境界 → prolog の push 照合)
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if flags & 4:
            return False
        if not full_decode(ub, cnt, prolog, ver):
            return False
        code = data[fo(ts_sec, b): fo(ts_sec, b) + prolog]
        ends = {ins.address - b + ins.size: ins for ins in md.disasm(code, b)}
        for k in range(cnt):
            cc = struct.unpack_from('<H', ub, 4 + 2 * k)[0]
            off, op, info = cc & 0xFF, (cc >> 8) & 0xF, (cc >> 12) & 0xF
            if op == 6:
                continue
            if off not in ends:
                return False
            if op == 0 and (ends[off].mnemonic != 'push' or ends[off].op_str != PUSH_REG[info]):
                return False
        return True

    fields = collections.Counter()
    pairs = []
    for b, e, u in valid:
        hs = hits(u)
        if len(hs) == 1:
            continue
        ubs = [(s, data[fo(s, u): fo(s, u) + 524]) for s in hs]
        m = [mx10_ok(ub, b, e) for _, ub in ubs]
        if sum(m) not in (0, 2, 3):
            continue
        ts = [s2 for s2 in secs if s2.VirtualAddress <= b < s2.VirtualAddress + s2.Misc_VirtualSize][0]
        # redo() と同じ判定で ok (plain_ok / chain_ok) の候補を集める
        ok_c = []
        for (s, ub), x in zip(ubs, m):
            if not x:
                continue
            ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
            if flags & 4:
                o = 4 + 2 * (cnt + (cnt & 1))
                pb, pe_, _ = struct.unpack_from('<III', ub, o)
                if (pb, pe_) not in valid_exact or not full_decode(ub, cnt, prolog, ver):
                    continue
                kind = 'chain_ok'
            else:
                if not plain_ok(ub, b, e, ts):
                    continue
                kind = 'plain_ok'
            offs = tuple(struct.unpack_from('<H', ub, 4 + 2 * k)[0] for k in range(cnt))
            ok_c.append({
                'sec': s.Name.rstrip(b'\0').decode(), 'kind': kind, 'ver': ver, 'flags': flags,
                'prolog': prolog, 'cnt': cnt, 'codes': offs,
                'uwind_hex': ub[:4 + 2 * cnt + 4].hex(),
            })
        if len(ok_c) < 2:
            continue
        fields['n%d' % len(ok_c)] += 1
        pairs.append({'begin': b, 'end': e, 'cands': ok_c})
        a, c = ok_c[0], ok_c[1]
        for k in ('ver', 'flags', 'prolog', 'cnt', 'codes', 'sec'):
            fields['same_' + k if a[k] == c[k] else 'diff_' + k] += 1
        fields['same_uwind' if a['uwind_hex'] == c['uwind_hex'] else 'diff_uwind'] += 1

    out = {'pe': path, 'pairs': len(pairs), 'field_compare': dict(sorted(fields.items())),
           'samples': pairs}
    if outp:
        json.dump(out, open(outp, 'w'), indent=1)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
