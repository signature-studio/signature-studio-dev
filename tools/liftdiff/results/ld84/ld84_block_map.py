#!/usr/bin/env python3
"""LD-84 (#2193): 1801ab1d0・1ab258・1c621c・1c682c・1c69cc (+1c5e84 の参照) の native 命令と wasm block 列の対応付け。

入力 (repo 内の再生成物。素材は work-m6-ott / work-liftdiff / analysis-ott-binaries):
  - tools/ott/work/ott.ll                      IR。`dec_label_pc_<VA>:` が IR basic block の入口
  - tools/liftdiff/results/ld57/insn_<fn>_<pat>.txt   native 実行トレース (1 行 1 命令: rva と rax..r9 の 16 進)
  - tools/liftdiff/work/ld84/blk_all.json      wasm 側の IR block 入口列 (raw.wasm.blk)。liftdiff.py run -v で取得
  - PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll  末尾命令の逆アセンブル用 (capstone)

対応の定義:
  - native 側の block 入口 = 実行トレース中で VA が IR label と一致した命令 (label 一致法)。
  - 検算 (別アルゴリズム): 各命令の block = VA 以下で最大の label (区間法)。区間法で block が変わる箇所が
    すべて label 一致の入口と一致するかを見る (非 label への遷移の件数)。
  - wasm 側と native 側の block 入口列を先頭から比較し、共通接頭辞長と最初の不一致を出す。

出力: tools/liftdiff/results/ld84/block_map_<fn>_<pat>.tsv と stdout の要約。
再現: cd tools/liftdiff && python3 results/ld84/ld84_block_map.py
"""
import bisect
import json
import os
import re
import sys
from pathlib import Path

import capstone
import pefile

HERE = Path(__file__).resolve().parent
LIFTDIFF = HERE.parent.parent
REPO = LIFTDIFF.parent.parent
IMAGE_BASE = 0x180000000
FNS = ['1801ab1d0', '1801ab258', '1801c5e84', '1801c621c', '1801c682c', '1801c69cc']
PATS = ['vm0', 'u16']


def load_labels(ll_path):
    labels = set()
    pat = re.compile(r'^dec_label_pc_([0-9a-f]+):')
    for line in open(ll_path):
        m = pat.match(line)
        if m:
            labels.add(int(m.group(1), 16))
    return labels


def load_trace(fn, pat):
    rows = []
    for line in open(LIFTDIFF / 'results' / 'ld57' / f'insn_{fn}_{pat}.txt'):
        f = line.split()
        if not f:
            continue
        rows.append(dict(rva=int(f[0], 16), regs=f[1:11]))
    return rows


def disasm_at(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    data = text.get_data()
    base_rva = text.VirtualAddress
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def dis(rva):
        off = rva - base_rva
        for ins in cs.disasm(data[off:off + 15], IMAGE_BASE + rva, 1):
            return f'{ins.mnemonic} {ins.op_str}'.strip()
        return '?'
    return dis


def main():
    labels = load_labels(REPO / 'tools' / 'ott' / 'work' / 'ott.ll')
    label_list = sorted(labels)
    blk = json.load(open(LIFTDIFF / 'work' / 'ld84' / 'blk_all.json'))
    wasm = {}
    for rec in blk:
        fn = rec['function']['va'][2:]
        for c in rec['cases']:
            wasm[(fn, c['pattern'])] = dict(outcome=c['outcome'],
                                            blk=[int(s, 16) for s in c['raw']['wasm']['blk']],
                                            wasm_status=c['wasm_status'])
    pe_path = Path(os.environ.get('PLUGINS_DIR', str(Path.home() / 'analysis' / 'plugins'))) / 'ott' / 'binaries' / 'OTT_vst2_win64.dll'
    dis = disasm_at(str(pe_path))
    outdir = HERE
    print(f'labels={len(labels)} pe={pe_path.name}')
    for fn in FNS:
        for pat in PATS:
            tr = load_trace(fn, pat)
            # 区間法: VA 以下で最大の label
            ent = []   # label 一致の入口 (native)
            prev_id = None
            prev_ins = ''
            nonlabel_switch = 0
            anomaly = 0
            anomaly_at = set()
            per = []   # (va, block_id, is_entry)
            for r in tr:
                va = IMAGE_BASE + r['rva']
                i = bisect.bisect_right(label_list, va) - 1
                bid = label_list[i] if i >= 0 else None
                is_entry = va in labels
                if is_entry:
                    ent.append(va)
                if prev_id is not None and bid != prev_id and not is_entry:
                    nonlabel_switch += 1
                    if not (prev_ins.startswith('call') or prev_ins.startswith('ret')):
                        anomaly += 1
                        anomaly_at.add((prev_ins, va))
                prev_id = bid
                prev_ins = dis(r['rva'])
                per.append((va, bid, is_entry))
            w = wasm[(fn, pat)]
            wb = w['blk']
            k = 0
            while k < min(len(wb), len(ent)) and wb[k] == ent[k]:
                k += 1
            ident = (len(wb) == len(ent)) and k == len(wb)
            # 最初の不一致 (wasm 側の打ち切り (trap) も含む)
            div = ''
            if not ident:
                wv = f'0x{wb[k]:x}' if k < len(wb) else '(wasm 終端)'
                nv = f'0x{ent[k]:x}' if k < len(ent) else '(native 終端)'
                div = f'k={k} wasm={wv} native={nv}'
            # 1 入口ごとの対応表 (native 側の入口・実行命令数・末尾命令)
            starts = [j for j, (va, bid, is_entry) in enumerate(per) if is_entry]
            entries = []
            for si, j0 in enumerate(starts):
                j1 = starts[si + 1] if si + 1 < len(starts) else len(per)
                own = [j for j in range(j0, j1) if per[j][1] == per[j0][0]]
                entries.append(dict(va=per[j0][0], first=own[0], n=len(own), last=own[-1]))
            with open(outdir / f'block_map_{fn}_{pat}.tsv', 'w') as f:
                f.write('k\twasm_block\tnative_block\tmatch\tnative_insn_n\tnative_first_rva\tnative_last_rva\tlast_insn\tlast_rax\tlast_rcx\n')
                for kk in range(max(len(wb), len(entries))):
                    wv = f'{wb[kk]:x}' if kk < len(wb) else '-'
                    if kk < len(entries):
                        e = entries[kk]
                        nv = f'{e["va"]:x}'
                        lr = tr[e['last']]
                        ins = dis(lr['rva'])
                        row = f'{kk}\t{wv}\t{nv}\t{"=" if kk < len(wb) and wb[kk] == e["va"] else "!"}\t{e["n"]}\t{tr[e["first"]]["rva"]:x}\t{lr["rva"]:x}\t{ins}\t{lr["regs"][0]}\t{lr["regs"][1]}\n'
                    else:
                        row = f'{kk}\t{wv}\t-\t!\t0\t-\t-\t-\t-\t-\n'
                    f.write(row)
            print(f'{fn} {pat} outcome={w["outcome"]} wasm={w["wasm_status"]} wasm_n={len(wb)} native_entry_n={len(ent)} '
                  f'prefix={k} identical={ident} nonlabel_switch={nonlabel_switch} anomaly={anomaly} {div}')
            for pi, va in sorted(anomaly_at, key=lambda x: x[1]):
                print(f'    anomaly_target {va:#x} after "{pi}"')
    # ネガティブコントロール: 一致している case (1801ab1d0 vm0) の wasm 列の 1 件を壊すと、一致判定が崩れることを示す
    wb = list(wasm[('1801ab1d0', 'vm0')]['blk'])
    tr = load_trace('1801ab1d0', 'vm0')
    ent = [IMAGE_BASE + r['rva'] for r in tr if IMAGE_BASE + r['rva'] in labels]
    bad = list(wb)
    bad[1] = bad[0]
    k = 0
    while k < min(len(bad), len(ent)) and bad[k] == ent[k]:
        k += 1
    print(f'NEG-CONTROL 1801ab1d0 vm0: wasm_n={len(wb)} wasm[1] を wasm[0] に置換 -> prefix={k} (期待: 1 で不一致)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
