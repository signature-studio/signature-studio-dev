#!/usr/bin/env python3
"""MX-47 (#4192): .text 外を指す FH3 funclet 候補 211 件の由来・FH3 棄却 355 件の内訳・U4g/U4h/U4i の確認。

入力: PE, mx39 の reach.json (mx39_e2e.sh 実行済み)。出力: JSON (stdout と MX47_WORK/origin.json)。
由来の帰属は mx39_funclet_reach.fh3_funclets_capped と同じ読み方で、どの FuncInfo の
どの欄 (unwind action / try の catch handler 配列の何番目) から値が出たかを記録する。
"""
import collections
import json
import os
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mx6_pdata_eh as P  # noqa: E402
from mx39_funclet_reach import FH3, fh3_funclets_capped  # noqa: E402
from mx43_funclet_roots import universe  # noqa: E402

FI_MAGIC = (0x19930520, 0x19930521, 0x19930522)
CAP_STATE, CAP_TRY, CAP_CATCH = 0x1000, 0x1000, 0x100


def main(pe_path, reach_json, out_json):
    pe = pefile.PE(pe_path, fast_load=False)
    data = open(pe_path, 'rb').read()
    rd = P.make_rva_reader(pe, data)
    iat = P.walk_imports(rd, pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].VirtualAddress)
    tx = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    lo = tx.VirtualAddress
    hi = lo + max(tx.Misc_VirtualSize, tx.SizeOfRawData)
    secs = [(s.Name.rstrip(b'\0').decode('ascii', 'replace'), s.VirtualAddress,
             s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)) for s in pe.sections]

    def sec_of(v):
        for n, a, b in secs:
            if a <= v < b:
                return n
        return None

    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    entries = {}
    for i in range(0, len(pdata) - 11, 12):
        st, e, ui = (int.from_bytes(pdata[i + j:i + j + 4], 'little') for j in (0, 4, 8))
        if st and e > st:
            entries[st] = (e, ui)

    def handler_is_fh3(h):
        code = rd(h, 6) or b''
        if code[:2] == b'\xff\x25':
            return iat.get(h + 6 + int.from_bytes(code[2:6], 'little', signed=True)) == FH3
        return False

    # FuncInfo ごとに 1 回だけ読む (同じ FI を指す pdata が複数あるため)
    fi_seen = {}
    reject = collections.Counter()
    for st, (e, ui) in entries.items():
        b = rd(ui, 4)
        if b is None or b == b'\0\0\0\0' or not (b[0] >> 3) & (P.EHANDLER | P.UHANDLER):
            continue
        hdr = 4 + 2 * ((b[2] + 1) & ~1)
        hb = rd(ui + hdr, 8)
        if hb is None or not handler_is_fh3(int.from_bytes(hb[:4], 'little')):
            continue
        fi = int.from_bytes(hb[4:8], 'little')
        if fi in fi_seen:
            continue
        fi_seen[fi] = st
        got = fh3_funclets_capped(rd, fi)
        if got is not None:
            continue
        b36 = rd(fi, 36)
        if b36 is None:
            reject['fi_unreadable'] += 1
            continue
        magic = int.from_bytes(b36[:4], 'little')
        mx, _, nt, _ = (int.from_bytes(b36[4 + 4 * k:8 + 4 * k], 'little') for k in range(4))
        if magic not in FI_MAGIC:
            reject['bad_magic'] += 1
        elif mx > CAP_STATE:
            reject['maxState>0x1000'] += 1
        elif nt > CAP_TRY:
            reject['nTry>0x1000'] += 1
        else:
            reject['nCatch>0x100'] += 1

    # 由来の帰属: 成功した FI の候補を欄ごとに記録
    attrib = collections.defaultdict(list)
    for fi in fi_seen:
        got = fh3_funclets_capped(rd, fi)
        if not got:
            continue
        b36 = rd(fi, 36)
        mx, du, nt, dt = (int.from_bytes(b36[4 + 4 * k:8 + 4 * k], 'little') for k in range(4))
        for s in range(mx):
            e8 = rd(du + 8 * s, 8) or b'\0' * 8
            act = int.from_bytes(e8[4:8], 'little')
            if act:
                attrib[act].append(('unwind', fi, s))
        for t in range(nt):
            tb = rd(dt + 20 * t, 20) or b'\0' * 20
            nc = int.from_bytes(tb[12:16], 'little')
            if nc > CAP_CATCH:
                continue
            ha = int.from_bytes(tb[16:20], 'little')
            for h in range(nc):
                hb2 = rd(ha + 16 * h, 16) or b'\0' * 16
                hv = int.from_bytes(hb2[12:16], 'little')
                attrib[hv].append(('handler', fi, '%d/%d' % (h, nc)))

    out = sorted(f for f in attrib if not (lo <= f < hi))
    uni = universe(pe_path)
    assert set(out) == set(f for f in uni if not (lo <= f < hi)), 'attribution と universe の 範囲外候補が一致しない'

    kinds = collections.Counter()
    where = collections.Counter()
    for f in out:
        src = attrib[f]
        kinds['unwind' if all(k[0] == 'unwind' for k in src) else 'handler'] += 1
        for k in src:
            if k[0] == 'handler':
                idx, cnt = (int(x) for x in k[2].split('/'))
                where['handler slot %s' % ('last' if idx == cnt - 1 else 'non-last')] += 1
        where['value in ' + (sec_of(f) or 'outside_image')] += 1
    small = sorted(hex(f) for f in out if f < 0x1000)

    reach = json.load(open(reach_json))
    flow = {int(x['funclet'], 16) for x in reach['modes']['flow']['reached_funclets']}
    u4 = []
    for r in reach['candidates']:
        if not r.get('target_parent_in_round1'):
            continue
        t = int(r['target_funclet'], 16)
        u4.append({
            'site': r['site_rva'], 'target': r['target_funclet'], 'target_flow_reached': t in flow,
            'container': r['container'], 'container_is_fh3_parent': r['container_is_fh3_parent'],
            'container_is_funclet': r['container_is_funclet'],
            'site_reached_by_flow_in_container': r['site_reached_by_flow_in_container'],
            'site_is_insn_boundary': r['site_is_insn_boundary_linear'],
        })

    roots = sorted(f for f in uni if lo <= f < hi and f not in flow)
    pro = collections.Counter()
    for f in roots:
        b = rd(f, 5) or b''
        if b[:4] == bytes.fromhex('48895424'):
            pro['mov [rsp+x],rdx'] += 1
        elif b[:1] in (b'\x55', b'\x40', b'\x53'):
            pro['push'] += 1
        else:
            pro['other'] += 1
    flow_pro = collections.Counter(
        'mov [rsp+x],rdx' if (rd(f, 4) or b'')[:4] == bytes.fromhex('48895424') else 'other' for f in flow)

    res = {
        'out_of_text_candidates': len(out),
        'out_kind': dict(kinds), 'out_where': dict(where), 'out_below_0x1000': small,
        'fh3_funcinfo_success': len(fi_seen) - sum(reject.values()),
        'fh3_funcinfo_rejected': dict(reject), 'fh3_funcinfo_rejected_total': sum(reject.values()),
        'u4g_u4h_rows': u4,
        'u4i_root_prologue': dict(pro), 'u4i_flow_prologue': dict(flow_pro),
        'u4i_roots': len(roots), 'u4i_flow': len(flow),
    }
    os.makedirs(os.path.dirname(out_json) or '.', exist_ok=True)
    json.dump(res, open(out_json, 'w'), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
