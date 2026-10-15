#!/usr/bin/env python3
"""MX-38 (#3775) U4c: .pdata 1 本目の IAT 外 (direct) handler 6,354 件の構造を測る。

- mx6_pdata_eh.py の handler_name は `ff 25` の thunk だけを IAT に引き、それ以外を 'direct' とする。
  本スクリプトは direct の entry を集め、(a) 相異なる handler 番地の数、(b) 同じ番地を共有する件数、
  (c) 番地ごとの先頭の直接 call 先、(d) その call 先が関数の入口 (.pdata 始点) か、含む関数の命令境界か、を出す。
- 同定 (handler の正体) は行わない。本スクリプトの出力は構造の測定だけ。

usage: mx38_direct_handler.py <pe> <out.json>
"""
import bisect
import collections
import json
import re
import struct
import sys

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))

import pefile  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402

from mx6_pdata_eh import EHANDLER, UHANDLER, make_rva_reader, walk_imports  # noqa: E402

CALL_RIP = re.compile(r'\[rip \+ 0x([0-9a-f]+)\]')
CALL_DIRECT = re.compile(r'^0x([0-9a-f]+)$')


def main(pe_path, out_p):
    pe = pefile.PE(pe_path, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    rd = make_rva_reader(pe, data)
    iat = walk_imports(rd, pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].VirtualAddress)
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = pdata.get_data()
    ent = {}
    for i in range(0, len(praw) - 11, 12):
        st, e, ui = struct.unpack('<III', praw[i:i + 12])
        if st and e > st:
            ent[st] = (e, ui)
    starts = sorted(ent)
    md = Cs(CS_ARCH_X86, CS_MODE_64)

    def uinfo(ui):
        b = rd(ui, 4)
        if b is None or b == b'\0\0\0\0':
            return None
        return b[0] >> 3, b[2], 4 + 2 * ((b[2] + 1) & ~1)

    def is_thunk(h):
        c = rd(h, 6) or b''
        return c[:2] == b'\xff\x25'

    direct = collections.Counter()
    for st, (e, ui) in ent.items():
        u = uinfo(ui)
        if u is None or not u[0] & (EHANDLER | UHANDLER):
            continue
        h = struct.unpack('<I', rd(ui + u[2], 4) or b'\0' * 4)[0]
        if is_thunk(h):
            continue
        direct[h] += 1

    def call_targets(h):
        out = []
        for ins in md.disasm(rd(h, 260) or b'', h + base):
            if ins.mnemonic == 'call':
                m = CALL_DIRECT.match(ins.op_str)
                if m:
                    out.append(('direct', int(m.group(1), 16) - base))
                    continue
                m = CALL_RIP.search(ins.op_str)
                if m:
                    slot = ins.address + ins.size + int(m.group(1), 16) - base
                    out.append(('iat', iat.get(slot, 'slot:%x' % slot)))
            if len(out) >= 1:
                break
        return out

    def contain(x):
        j = bisect.bisect_right(starts, x) - 1
        if j < 0 or x >= ent[starts[j]][0]:
            return None
        return starts[j]

    def on_boundary(f, x):
        e = ent[f][0]
        code = rd(f, e - f) or b''
        return x in {ins.address - base for ins in md.disasm(code, f + base)}

    groups = collections.Counter()
    rows = []
    for h, n in direct.most_common():
        ct = call_targets(h)
        kind = ct[0] if ct else ('none', '')
        if kind[0] == 'direct':
            t = kind[1]
            f = contain(t)
            info = {
                'call_target': hex(t),
                'target_is_pdata_begin': t in ent,
                'containing_func': hex(f) if f is not None else None,
                'on_instruction_boundary': on_boundary(f, t) if f is not None else None,
            }
            key = 'direct:begin' if t in ent else ('direct:inside_func' if f is not None else 'direct:outside_pdata')
        else:
            info = {'call_target': kind[1]}
            key = 'iat:' + str(kind[1]) if kind[0] == 'iat' else 'none'
        groups[key] += 1
        rows.append({'handler': hex(h), 'entries': n, **info})

    res = {
        'direct_entries': sum(direct.values()),
        'distinct_handlers': len(direct),
        'handlers_shared_by_2plus': sum(1 for v in direct.values() if v >= 2),
        'entries_in_top2_handlers': sum(n for _, n in direct.most_common(2)),
        'first_call_kind': dict(groups.most_common()),
        'top_handlers': rows[:12],
    }
    with open(out_p, 'w') as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in res.items() if k != 'top_handlers'}, indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
