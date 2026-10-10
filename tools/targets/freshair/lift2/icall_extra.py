#!/usr/bin/env python3
"""icall_extra.py <core> <report.json> — mlift report の closure (`funcs`) を走査し
closure 内の `lea r64,[rip+disp32]` が指す .text VA (closure 外) を icall seed として列挙する。

vtable スロットは vtable を実データとして敷設するので解決できるが、「関数ポインタを引数で受け回す」
経路 (例: モデル基本 ctor 0x180c96ad0 が r9 に lea で載せて 0x18100c7e0 に渡す) は mlift の BFS
(direct call) に入らず、実行時に未 lift → fa_host_icall の fail-fast に落ちる。

あわせて「FreshAirDsp 制御層/モデル領域 (rva 0x3c000..0x3f000) の全関数」も seed する
(harness グラフの vtable slot として .rdata の製品記述テーブルから参照されるため)。

関数範囲は mlift と同じ pe_image.func_extent を使う (pdata 無しは線形走査)。stdout に `--icall VA`。"""
import sys, json, struct, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mlift'))
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from pe_image import Image

core, rep = sys.argv[1], sys.argv[2]
img = Image(core)
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
r = json.load(open(rep))
clo = set(int(k, 16) for k in r['funcs'])
TEXT_LO, TEXT_HI = img.text_lo, img.text_hi
extra = {}
for va in sorted(clo):
    ext = img.func_extent(va, md)
    if not ext: continue
    b, e = ext
    s = img.read(b, e - b)
    for j in range(len(s) - 7):
        if s[j + 1] == 0x8D and s[j] in (0x48, 0x4C) and (s[j + 2] & 0xC7) == 0x05:
            rel = struct.unpack_from('<i', s, j + 3)[0]
            t = b + j + 7 + rel
            if TEXT_LO <= t < TEXT_HI and t not in clo:
                extra[t] = extra.get(t, 0) + 1

# 追加: FreshAirDsp 制御層/モデル領域 (rva 0x3c000..0x3f000) の全関数も seed 対象に。
# pdata 非登録の小関数 (0x1803de6e0 / 0x1803de9b0 等) は「関数 end + int3 パディング飛ばし」で
# 機械的に復元する (harness グラフの vtable slot として参照される)。
RLO, RHI = img.base + 0x3d0000, img.base + 0x3f0000   # RVA 0x3d0000..0x3f0000 (FreshAirDsp 制御層/モデル)
starts = set(f[0] for f in img.funcs)
for va in sorted(starts):
    if not (RLO <= va < RHI):
        continue
    if va not in clo:
        extra[va] = extra.get(va, 0) + 1
    cur = va
    guard = 0
    while guard < 400:
        guard += 1
        ext = img.func_extent(cur, md)
        if not ext:
            break
        b, e = ext
        if e <= cur:
            break
        nxt = e
        while nxt < RHI and img.read(nxt, 1) == b'\xcc':
            nxt += 1
        if nxt <= cur or nxt >= RHI:
            break
        if nxt not in starts:
            starts.add(nxt)
            if nxt not in clo:
                extra[nxt] = extra.get(nxt, 0) + 1
        cur = nxt
print(' '.join('--icall %x' % t for t in sorted(extra)))
