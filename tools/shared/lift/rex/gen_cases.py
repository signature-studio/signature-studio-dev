#!/usr/bin/env python3
"""REX の 2 export (REXGetCreatorInfo / REXGetInfo の wrapper) に与える入力を決定的に生成する (seed 固定)。

case 形式 (little endian, native_ref.c と run_wasm.mjs が同じ規約で読む):
  u32 N (ヘッダ) / 各 case: u32 fn (0=REXGetCreatorInfo, 1=REXGetInfo), u32 0, u64 a0 a1 a2 a3, u64 ctx, arena[ARENA_SZ]
  ctx : REX の ctx 大域 (RVA 0x49e08) に入れる値。0 (NULL) か arena 内の構造体。
  arena: qword 単位で {0, arena 内ポインタ} だけを入れる。整数値は入れない (REX が値を pointer として deref しても
         native 側で SIGSEGV せず、wasm 側でも線形メモリ内の別データを読まないため)。a0/a2/a3 も同じ規則 (0 か arena 内)。
usage: gen_cases.py OUT [N]
"""
import random, struct, sys

ARENA = 0x30100000
ARENA_SZ = 0x10000
CTX_OFF = 0x8000
rnd = random.Random(2733)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 200
out = [struct.pack('<I', N)]


def ptr():
    return ARENA + 8 * rnd.randrange(0, ARENA_SZ // 8)


def key_of(a):
    """0x180019f0 (REX) の命令列を模倣: rdx=a を一時領域 [rsp+0x10..0x20] に書いてバイトを並べ替え、[rsp+0x18] を返す (木のキー)。"""
    st = bytearray(32)
    st[0x18:0x20] = struct.pack('<Q', a)
    cl = st[0x19]
    st[0x10:0x18] = struct.pack('<Q', a)
    al = st[0x13]
    st[0x1b] = a & 0xff
    st[0x18] = al
    al = st[0x1a]
    st[0x1a] = cl
    st[0x19] = al
    return struct.unpack_from('<Q', st, 0x18)[0]


for i in range(N):
    fn = i % 2
    ctx = 0 if rnd.random() < 0.1 else ARENA + CTX_OFF
    a0 = rnd.choice([ptr(), rnd.getrandbits(32) | 1, rnd.getrandbits(64) | 1])
    a1 = rnd.choice([0, 1, rnd.randrange(0x100, 0x500), rnd.randrange(0x500, 0x800)])
    a2 = rnd.choice([ptr(), ptr(), 0])
    a3 = rnd.choice([0, ptr()])
    arena = bytearray(ARENA_SZ)
    for q in range(ARENA_SZ // 8):
        r = rnd.random()
        v = ptr() if (CTX_OFF <= 8 * q < CTX_OFF + 0x4000 or r >= 0.1) else 0
        struct.pack_into('<Q', arena, 8 * q, v)
    if ctx and rnd.random() < 0.8:
        # 根ノード N (= ctx+0x20 が指す): key = key_of(a0)。左右の子は 0 (木は 1 節点)。
        node = ARENA + 0xC100
        struct.pack_into("<QQQ", arena, node - ARENA, 0, 0, key_of(a0))
        struct.pack_into("<Q", arena, CTX_OFF + 0x20, node)
    out.append(struct.pack('<IIQQQQQ', fn, 0, a0, a1, a2, a3, ctx) + bytes(arena))

open(sys.argv[1], 'wb').write(b''.join(out))
print('[gen_cases] N=%d -> %s' % (N, sys.argv[1]))
