#!/usr/bin/env python3
"""ld120_controls.py — #2679 (LD-120) の 0 件の主張の対照と frame F の根拠の数値。

標準出力のみ (results/ は作らない)。素材 `work-m11` (tools/m11/work) が要る。
  [prologue]  関数先頭の命令と F (push * 8 + sub rsp, imm。`mov rbp, rsp` まで)
  [cfg]       config の function_128f9e0 の locals (本数・stack_var の最小値・最大値)
  [F-scan]    F ∈ [1328, 8192] のうち、12 site の stack_var 名 (-(F-d)) が全て config の locals に一致する F
  [pos-slot]  既知の alloca `stack_var_-2032` の言及 (function_128f9e0 本体・IR / lift / drc の 3 ファイル)
  [neg-slot]  本体の先頭へ `load ... stack_var_-760` を 1 行挿入 (メモリ上・ファイルは書かない) → 言及数 (3 ファイル)
  [pos-K]     K=18746032 を含む IR 行 (ファイル全体・関数別) と、同じ検索を function_10c7cd0 本体へ当てた件数 (IR のみ)
  [neg-K]     本体の先頭へ K の load を 1 行挿入 → K の行数 (IR のみ)
使い方: python3 ld120_controls.py     環境変数: M11_WORK (既定 tools/m11/work)
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
FN_NAME = 'function_128f9e0'
CTRL_FN = 'function_10c7cd0'
K_VALUE = '18746032'
POS_SLOT = -2032
NEG_SLOT = -760


def span(lines, name):
    s = next(i for i, l in enumerate(lines) if re.match(r'define .*@%s\(' % name, l))
    e = next(i for i in range(s, len(lines)) if lines[i] == '}')
    return s, e


def mentions(body, name):
    return sum(1 for l in body if re.search(re.escape(name) + r'(?![\d])', l))


def main():
    w = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
    mach = ImageMachine(os.path.join(w, 'm11_image.bin'), os.path.join(w, 'boot*.drc.config.json'))
    ins = list(mach.cs.disasm(mach.read(FN - mach.base, 0x40), FN, 0x40))
    k = next(i for i, x in enumerate(ins) if x.mnemonic == 'mov' and x.op_str == 'rbp, rsp')
    F = L.frame_size(ins)
    print('[prologue] %s' % ' ; '.join('0x%x %s %s' % (x.address, x.mnemonic, x.op_str) for x in ins[:k + 1]))
    print('[F] F=%d (0x%x)。rbp の位置 = エントリ rsp - %d' % (F, F, F))

    cfg = json.load(open(os.path.join(w, 'boot3.drc.config.json')))
    locs = next(f for f in cfg['functions'] if f.get('name') == FN_NAME)['locals']
    names = {v['name'] for v in locs}
    stack = [int(m.group(1)) for n in names for m in [re.fullmatch(r'stack_var_(-?\d+)', n)] if m]
    print('[cfg] locals %d 本 (stack_var %d 本)・最小 %d・最大 %d' % (len(names), len(stack), min(stack), max(stack)))

    tsv = open(os.path.join(HERE, 'results/ld120_frame_128f9e0.tsv')).read().splitlines()[1:]
    disp = [int(r.split('\t')[1], 16) for r in tsv]
    cands = [c for c in range(1328, 8193) if all('stack_var_-%d' % (c - d) in names for d in disp)]
    print('[F-scan] 12 名が全て config locals に一致する F: %d 通り (F=%d を含む %s): %s'
          % (len(cands), F, F in cands, ' '.join(map(str, cands))))

    for fname in ['boot_final3.ll', 'boot3.lift.ll', 'boot3.drc.ll']:
        ll = open(os.path.join(w, fname)).read().splitlines()
        s, e = span(ll, FN_NAME)
        body = ll[s:e]
        alloca = sorted({int(m.group(1)) for l in body for m in [re.match(r'\s+%stack_var_(-\d+) = alloca', l)] if m})
        print('[%s] %s 本体 %d〜%d 行: alloca %d 本 (範囲 %d〜%d)'
              % (fname, FN_NAME, s + 1, e + 1, len(alloca), alloca[0], alloca[-1]))
        print('  [pos-slot] stack_var_%d (alloca %s) の言及: %d 件 (期待 1 以上)'
              % (POS_SLOT, 'あり' if POS_SLOT in alloca else 'なし', mentions(body, 'stack_var_%d' % POS_SLOT)))
        slot_line = '  %%neg = load i64, ptr %%stack_var_%d' % NEG_SLOT
        mod = body[:1] + [slot_line] + body[1:]
        print('  [neg-slot] stack_var_%d の言及: 原本 %d 件 → 本体先頭に 1 行挿入 %d 件 (期待 0 → 1)'
              % (NEG_SLOT, mentions(body, 'stack_var_%d' % NEG_SLOT), mentions(mod, 'stack_var_%d' % NEG_SLOT)))
        if fname != 'boot_final3.ll':
            continue
        cur, per_fn = None, {}
        for l in ll:
            m = re.match(r'define .*@(\w+)\(', l)
            if m:
                cur = m.group(1)
            if K_VALUE in l:
                per_fn[cur] = per_fn.get(cur, 0) + 1
            if l == '}':
                cur = None
        cs, ce = span(ll, CTRL_FN)
        print('  [pos-K] %s を含む行: ファイル全体 %d 行 (関数別 %s)。同じ検索を %s 本体 %d〜%d 行に当てると %d 件 (期待 1 以上)'
              % (K_VALUE, sum(per_fn.values()), per_fn, CTRL_FN, cs + 1, ce + 1,
                 sum(1 for l in ll[cs:ce] if K_VALUE in l)))
        k_line = '  %%kneg = load i64, ptr inttoptr (i64 %s to ptr)' % K_VALUE
        mod = body[:1] + [k_line] + body[1:]
        print('  [neg-K] %s を含む行: 原本 %d 件 → 本体先頭に 1 行挿入 %d 件 (期待 0 → 1)'
              % (K_VALUE, sum(K_VALUE in l for l in body), sum(K_VALUE in l for l in mod)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
