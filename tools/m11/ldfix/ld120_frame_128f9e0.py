#!/usr/bin/env python3
"""ld120_frame_128f9e0.py — #2679 (LD-120) spill 宛 未判定 `128f9e0` 12 site の frame slot 突合。

機械語 (`[rbp+d]`・frame F = push 数 * 8 + `sub rsp, imm` ・ stack_var = -(F - d)) と IR 本体
(`define weak i64 @function_128f9e0`) を site ごとに突き合わせ、TSV と候補判定 (jsonl) の根拠行を出す。
出力:
  results/ld120_frame_128f9e0.tsv   site ごとの機械語連鎖・消費者・IR の言及数・config の locals 宣言
  --verdicts                       results/candidate_verdicts_1161.jsonl に無い site だけ UNDETERMINED を追記
使い方: python3 ld120_frame_128f9e0.py [--verdicts]     環境変数: M11_WORK (既定 tools/m11/work)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
import ld110_reg2mem_link as L  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402

FN = 0x128f9e0
FN_LEN = 0x6000
FN_NAME = 'function_128f9e0'
SITES = ['12906d1', '1291ac3', '1291b14', '1291b5f', '1291c20', '1293012',
         '1293063', '12930ae', '129312c', '129450c', '129455d', '12945a8']
K_VALUE = '18746032'


def main():
    w = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
    mach = ImageMachine(os.path.join(w, 'm11_image.bin'), os.path.join(w, 'boot*.drc.config.json'))
    ins = list(mach.cs.disasm(mach.read(FN - mach.base, FN_LEN), FN, FN_LEN))
    idx = {x.address: i for i, x in enumerate(ins)}
    ll = open(os.path.join(w, 'boot_final3.ll')).read().splitlines()
    start = next(i for i, l in enumerate(ll) if l.startswith('define weak i64 @%s(' % FN_NAME))
    end = next(i for i in range(start, len(ll)) if ll[i] == '}')
    body = ll[start:end]
    F = L.frame_size(ins)
    name_of = lambda d: 'stack_var_-%d' % (F - d)  # noqa: E731
    alloca = {int(m.group(1)) for l in body for m in [re.match(r'\s+%stack_var_(-\d+) = alloca', l)] if m}
    k_loads = sum(1 for l in body if K_VALUE in l)
    cfg = json.load(open(os.path.join(w, 'boot3.drc.config.json')))
    locals_ = {v['name'] for f in cfg['functions'] if f.get('name') == FN_NAME for v in f.get('locals', [])}
    drc = open(os.path.join(w, 'boot3.drc.ll')).read().splitlines()
    ds = next(i for i, l in enumerate(drc) if re.match(r'define .*@%s\(' % FN_NAME, l))
    de = next(i for i in range(ds, len(drc)) if drc[i] == '}')
    drc_body = drc[ds:de]
    print('[ld120] frame F=%d (0x%x) / IR allocas %d 本 (範囲 %d〜%d) / IR 本体 %d 行 / K=%s の load %d 件'
          % (F, F, len(alloca), max(alloca), min(alloca), len(body), K_VALUE, k_loads))

    rows = ['site\tdisp\tstack_var\tmachine_chain\tmachine_consumers\tir_alloca\tir_mentions\tconfig_local\tir_K_loads\tdrc_mentions']
    facts = {}
    for s in SITES:
        ms = L.machine_side(mach, ins, idx, s, lambda x: int(L.MEM_RBP.search(x.op_str).group(1), 16))
        name = name_of(ms['disp'])
        off = -(F - ms['disp'])
        mentions = sum(1 for l in body if re.search(re.escape(name) + r'(?![\d])', l))
        drc_m = sum(1 for l in drc_body if re.search(re.escape(name) + r'(?![\d])', l))
        facts[s] = dict(d=ms['disp'], name=name, chain=ms['chain'], refs=ms['refs'], alloca=off in alloca,
                        mentions=mentions, cfg=name in locals_, k=ms['k'], v=ms['v'], drc=drc_m)
        rows.append('\t'.join([s, hex(ms['disp']), name, ms['chain'], ' | '.join(ms['refs']),
                               'yes' if off in alloca else 'no', str(mentions),
                               'yes' if name in locals_ else 'no', str(k_loads), str(drc_m)]))
        print('[ld120] %s [rbp+%s] -> %s: alloca %s / IR 言及 %d 件 / config locals %s'
              % (s, hex(ms['disp']), name, 'yes' if off in alloca else 'no', mentions,
                 'yes' if name in locals_ else 'no'))
    out = os.path.join(HERE, 'results/ld120_frame_128f9e0.tsv')
    with open(out, 'w') as fh:
        fh.write('\n'.join(rows) + '\n')
    print('[ld120] %d site -> %s' % (len(SITES), out))

    if '--verdicts' in sys.argv:
        vpath = os.path.join(HERE, 'results/candidate_verdicts_1161.jsonl')
        have = {json.loads(l)['site'] for l in open(vpath) if l.strip()}
        add = []
        for s in SITES:
            if s in have:
                continue
            f = facts[s]
            ev = ('機械語 %s (2 段 deref・K=0x%x・V=0x%x)。消費者 %s。'
                  'IR: %s 本体 (76541〜77198 行) に %s の alloca・store・load は %d 件 (alloca %s)。'
                  'K の load は IR 本体に %d 件。RetDec 出力 boot3.drc.ll の同関数 (%d〜%d 行) にも %s の言及は %d 件 '
                  '(m11 後処理より前の段で欠落)。config の locals には %s が宣言済み (%s)。'
                  'IR に store も読みも無く、TRUE_DROP / OK_LOAD / NO_CONSUMER の結線 (IR の store→load) が立たないため判定不能。'
                  '欠落の原因は RetDec 段の未確定 (子 issue)。'
                  % (f['chain'], f['k'], f['v'], f['refs'][0], FN_NAME, f['name'],
                     f['mentions'], 'yes' if f['alloca'] else 'no', k_loads, ds + 1, de,
                     f['name'], f['drc'], f['name'], 'yes' if f['cfg'] else 'no'))
            add.append(json.dumps({'fn': '128f9e0', 'site': s, 'verdict': 'UNDETERMINED', 'evidence': ev},
                                  ensure_ascii=False))
        with open(vpath, 'a') as fh:
            for a in add:
                fh.write(a + '\n')
        print('[ld120] candidate_verdicts_1161.jsonl に UNDETERMINED %d 行を追記' % len(add))
    return 0


if __name__ == '__main__':
    sys.exit(main())
