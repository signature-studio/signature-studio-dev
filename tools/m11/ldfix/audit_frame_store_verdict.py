#!/usr/bin/env python3
"""audit_frame_store_verdict.py — FRAME_IN_ESCAPED 候補の真偽の機械判定 (#2144 / #1866 残件)。

入力: 旧監査の結果 JSON (audit_undefload_564_full.json 形式) と F4 修復済み関数リスト (f4_564_post.json)。
各 FRAME_IN_ESCAPED site の読み (機械語 !insn.addr の命令) について、同じ関数の線型 disasm で
読みより前に、同じ (base, disp) の frame slot へ書く命令があるかを見る。途中に call / ret / jmp / 条件分岐 が
あれば探索を止める (IR ブロック境界の近似)。

判定 (site 単位。直前の straight-line 区間のみ見る):
  STORE_IN_BLOCK  同一 frame slot への書き込みが、call/ret/jmp/条件分岐を挟まず直前にある
                  → 機械語上は store が有るのに IR で読みが undef になった候補 (真の脱落候補)
  NO_STORE_IN_BLOCK  区間内に書き込みが無い。前のブロックの store は見ていないので、
                  live-in とは断定しない (未判定)

関数判定: STORE_IN_BLOCK が 1 site でもあれば STORE_IN_BLOCK_FN、無ければ UNDETERMINED。
これは機械的な近似であり、確定判定ではない。ブロック境界・エイリアスは厳密に見ない。

使い方: python3 audit_frame_store_verdict.py PE.bin AUDIT.json F4.json OUT.json
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine, memops_of  # noqa: E402

STOP_MN = ('call', 'ret', 'jmp')


def slot_of(mo):
    if mo is None or mo.get('rip_rva') is not None or mo['index']:
        return None
    if mo['base'] not in ('rbp', 'rsp'):
        return None
    return (mo['base'], mo['disp'])


def main():
    pe, audit_path, f4_path, out = sys.argv[1:5]
    mach = Machine(pe)
    audit = json.load(open(audit_path))
    f4 = set(json.load(open(f4_path))['f4_vas'])
    rows = [s for s in audit['frame_in_escaped'] if s['fn'] not in f4]
    fns = collections.defaultdict(list)
    for s in rows:
        fns[s['fn']].append(s)
    verdict = {}
    per_site = []
    for fn, sites in sorted(fns.items()):
        va = int(fn, 16)
        seq = mach.disasm_fn(va) or []
        fn_drop = False
        for s in sites:
            addr = int(s['detail'][0].split()[0], 16) if s.get('detail') else None
            idx = next((i for i, x in enumerate(seq) if x.address == addr), None)
            if idx is None:
                per_site.append(dict(fn=fn, ty=s['ty'], verdict='NOADDR'))
                continue
            ins = seq[idx]
            rd = next((mo for mo in memops_of(mach.cs, ins) if mo['kind'] in ('load', 'rmw', 'other')), None)
            slot = slot_of(rd)
            v = 'NO_STORE_IN_BLOCK'
            if slot is not None:
                for j in range(idx - 1, -1, -1):
                    w = seq[j]
                    if w.mnemonic.startswith(STOP_MN) or w.mnemonic.startswith('j'):
                        break
                    hit = [mo for mo in memops_of(mach.cs, w) if mo['kind'] in ('store', 'rmw') and slot_of(mo) == slot]
                    if hit:
                        v = 'STORE_IN_BLOCK'
                        break
            per_site.append(dict(fn=fn, ty=s['ty'], addr='%x' % addr, mnem='%s %s' % (ins.mnemonic, ins.op_str), verdict=v))
            fn_drop = fn_drop or v == 'STORE_IN_BLOCK'
        verdict[fn] = 'STORE_IN_BLOCK_FN' if fn_drop else 'UNDETERMINED'
    tally = collections.Counter(verdict.values())
    json.dump(dict(functions=len(verdict), by_verdict=dict(tally), verdict=verdict, sites=per_site),
              open(out, 'w'), indent=1)
    print('functions', len(verdict), dict(tally))


if __name__ == '__main__':
    main()
