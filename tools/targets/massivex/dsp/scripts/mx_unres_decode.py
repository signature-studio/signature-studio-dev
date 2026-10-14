#!/usr/bin/env python3
"""解決不能 entry の UNWIND_INFO 候補を UNWIND_CODE 列の完全復号で再判定する (MX-12 受入 1・2)。

mx_unres_probe.py の候補 (section hit ごと) に対し、次を全て満たすものを「完全整合」とする:
  - Version ∈ {1, 2}・Flags は EHANDLER|UHANDLER|CHAININFO (0..7) のみ
  - UNWIND_CODE 列を先頭から復号し、スロット数の合計が CountOfCodes と一致する
  - opcode ∈ UWOP_PUSH_NONVOL..UWOP_PUSH_MACHFRAME (0..10, 7 は予約で不可)・EPILOG (6) は Version 2 のみ
  - 非 EPILOG の CodeOffset は SizeOfProlog 以下で、先頭から単調非増加
  - CHAININFO なら親 RUNTIME_FUNCTION が valid .pdata に完全一致で在る

usage: mx_unres_decode.py <pe> [out.json]
"""
import sys, json, struct, collections
import pefile


def node_slots(op, info):
    if op == 0 or op == 2 or op == 3 or op == 6 or op == 10:
        return 1 if op != 10 or info in (0, 1) else None
    if op == 1:
        return 2 if info == 0 else 3
    if op in (4, 8):
        return 2
    if op in (5, 9):
        return 3
    return None


def full_decode(ub, cnt, prolog, ver):
    codes = [struct.unpack_from('<H', ub, 4 + 2 * k)[0] for k in range(cnt)]
    i = 0
    last_off = 256
    while i < cnt:
        c = codes[i]
        off, op, info = c & 0xFF, (c >> 8) & 0xF, (c >> 12) & 0xF
        if op == 6 and ver != 2:
            return False
        if op != 6:
            if off > prolog or off > last_off:
                return False
            last_off = off
        n = node_slots(op, info)
        if n is None or i + n > cnt:
            return False
        i += n
    return i == cnt


def main(path, outp=None):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, 'rb').read()
    t = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    raw = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]
    ents = [struct.unpack_from('<III', raw, i) for i in range(0, len(raw) - 11, 12)]
    valid = [(b, e, u) for (b, e, u) in ents if e > b and b and t_lo <= b < t_hi and e <= t_hi]
    valid_exact = set((b, e) for (b, e, u) in valid)

    def hits(u):
        return [s for s in pe.sections if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]

    def verdict(s, u, b, e):
        off = s.PointerToRawData + (u - s.VirtualAddress)
        ub = data[off: off + 4 + 2 * 256 + 12]
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if ver not in (1, 2) or prolog > e - b or cnt > 255 or flags > 7:
            return 'bad'
        if flags & 4:
            o = 4 + 2 * (cnt + (cnt & 1))
            pb, pe_, _ = struct.unpack_from('<III', ub, o)
            if (pb, pe_) not in valid_exact:
                return 'bad'
            return 'chain_ok' if full_decode(ub, cnt, prolog, ver) else 'bad'
        if cnt == 0:
            return 'bad'
        return 'plain_ok' if full_decode(ub, cnt, prolog, ver) else 'bad'

    unres = [(b, e, u) for (b, e, u) in valid if len(hits(u)) != 1]
    summary = collections.Counter()
    ok_hist = collections.Counter()
    ambiguous = []
    for b, e, u in unres:
        hs = hits(u)
        summary['hits_%d' % len(hs)] += 1
        vs = [verdict(s, u, b, e) for s in hs]
        ok = [(s, v) for s, v in zip(hs, vs) if v != 'bad']
        ok_hist['ok_%d' % len(ok)] += 1
        if len(ok) == 1:
            summary['unique_' + ok[0][1]] += 1
        elif len(ok) == 0:
            summary['none'] += 1
        else:
            summary['multi'] += 1
            ambiguous.append({'b': hex(b), 'e': hex(e), 'u': hex(u),
                              'cands': [s.Name.rstrip(b'\0').decode() for s, _ in ok]})
    out = {
        'pe': path,
        'unresolved': len(unres),
        'summary': dict(sorted(summary.items())),
        'ok_candidate_hist': dict(sorted(ok_hist.items())),
    }
    if outp:
        json.dump(dict(out, ambiguous=ambiguous), open(outp, 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
