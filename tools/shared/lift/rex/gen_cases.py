#!/usr/bin/env python3
"""REX の 2 export (REXGetCreatorInfo / REXGetInfo の wrapper) に与える入力を決定的に生成する (seed 固定)。

case 形式 (little endian, native_ref.c と run_wasm.mjs が同じ規約で読む):
  u32 N (ヘッダ) / 各 case: u32 fn (0=REXGetCreatorInfo, 1=REXGetInfo), u32 0, u64 a0 a1 a2 a3, u64 ctx, arena[ARENA_SZ]
  ctx : REX の ctx 大域 (RVA 0x49e08) に入れる値。0 (NULL) か arena 内の構造体。
  a0  : arena 内ポインタ、または 32 / 64 bit の奇数乱数 (arena 外の値を含む)。
  a1  : 0 / 1 / 0x100-0x7ff の整数。a2 : arena 内ポインタか 0。a3 : 0 か arena 内ポインタ。
  arena: qword 単位で {0, arena 内ポインタ} だけを入れる。整数値は入れない (deref 先の内容が native の仮想アドレスと
         wasm の線形メモリで一致しないため)。arena 内ポインタは両側で同じ内容を指す。arena 内の 0 qword (ctx 領域の外で約 10%)
         を deref すると NULL 参照で native 側は SIGSEGV する (除外の候補。落ちた case の fault アドレスは native_ref の
         stderr に出る。REPORT §7.6)。
成功経路の case (末尾 SUCC 件・REXGetCreatorInfo のみ・seed 2870): 木の根 (ctx+0x20) のノード key = OBJ (アリーナ内)、
  key_of(a0) = OBJ となる a0 (key_of は対合)。OBJ+0x688 = B (0 なら 0x12a50 が偽で戻り値 3)。B の +0x28/+0x50/+0x78 = 0 (SSO の文字列を
  0x12ed0 が読む)。a1 は 0x500 以上 (0x12ed0 の書込に進む)。a2 は N バイトが arena 内に収まる位置。戻り値 1 (書込あり) と 3 を得る。
成功経路の case (末尾 SUCC1 件・REXGetInfo のみ・seed 3587): 0x2080 の O = key_of(a0) = OBJ。O の S = O+0x630・B = O+0x690 を
  dword 1 で埋め、B+0x62c = 0 (0x4500 が 1 を返す)。戻り値 1 (arena 書込あり) を得る。.data への書込は出ない (REPORT_APPENDIX_3587.md)。
usage: gen_cases.py OUT [N]
"""
import random, struct, sys

ARENA = 0x30100000
ARENA_SZ = 0x10000
CTX_OFF = 0x8000
NODE = ARENA + 0xC100
OBJ = ARENA + 0xC200
OBJ_B = ARENA + 0xC300
SUCC = 48
SUCC1 = 48
rnd = random.Random(2733)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 200
out = []


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

rnd2 = random.Random(2870)
for i in range(SUCC):
    a0 = key_of(OBJ)
    arena = bytearray(ARENA_SZ)
    for q in range(ARENA_SZ // 8):
        v = ptr() if (CTX_OFF <= 8 * q < CTX_OFF + 0x4000 or rnd2.random() >= 0.1) else 0
        struct.pack_into('<Q', arena, 8 * q, v)
    struct.pack_into('<Q', arena, OBJ + 0x688 - ARENA, OBJ_B if i % 4 else 0)
    for off in (0x28, 0x50, 0x78):
        struct.pack_into('<Q', arena, OBJ_B + off - ARENA, 0)
    struct.pack_into('<QQQ', arena, NODE - ARENA, 0, 0, key_of(a0))
    struct.pack_into('<Q', arena, CTX_OFF + 0x20, NODE)
    a1 = rnd2.randrange(0x500, 0x800)
    a2 = ARENA + 8 * rnd2.randrange(0, 0xE000 // 8)
    out.append(struct.pack('<IIQQQQQ', 0, 0, a0, a1, a2, 0, ARENA + CTX_OFF) + bytes(arena))

# REXGetInfo (fn=1) の成功経路 (戻り値 1)。木の key = key_of(a0) = OBJ (0x2080 の O)。O の構造 (S = O+0x630, B = O+0x690) は
# dword 1 で埋め、ポインタ項目だけ有効なアドレスへ向ける。B+0x62c = 0 で 0x4500 が 1 を返す。S+4 は 0x21a1 の jump table の値
# (8..0x20)。a1 >= 0x20 (0x2080 の出力長)、a2 は a1 バイトが arena 内に収まる位置。
LK = ARENA + 0xAF00
S_ = ARENA + 0x9000
B_ = ARENA + 0x9800
Z_ = ARENA + 0xA800
SWITCH = (1, 8, 9, 0x10, 0x14, 0x16, 0x18, 0x20)
rnd3 = random.Random(3587)
A0_1 = key_of(OBJ)
for i in range(SUCC1):
    arena = bytearray(ARENA_SZ)
    for base in (OBJ, S_, B_, Z_):
        for k in range(0, 0x700, 4):
            struct.pack_into('<I', arena, base - ARENA + k, 1)
    struct.pack_into('<I', arena, B_ + 0x62c - ARENA, 0)
    struct.pack_into('<I', arena, S_ + 4 - ARENA, rnd3.choice(SWITCH))
    struct.pack_into('<Q', arena, NODE + 0x10 - ARENA, OBJ)
    struct.pack_into('<Q', arena, CTX_OFF + 0x20, NODE)
    struct.pack_into('<Q', arena, CTX_OFF + 8, LK)
    struct.pack_into('<Q', arena, LK - ARENA, 0x10)
    struct.pack_into('<Q', arena, OBJ + 0x630 - ARENA, S_)
    struct.pack_into('<Q', arena, OBJ + 0x690 - ARENA, B_)
    struct.pack_into('<Q', arena, OBJ + 0x20 - ARENA, Z_)
    a1 = rnd3.choice([0x20, 0x23, 0x24, 0x100, 0x7FF])
    a2 = ARENA + 8 * rnd3.randrange(0, (ARENA_SZ - a1) // 8)
    out.append(struct.pack('<IIQQQQQ', 1, 0, A0_1, a1, a2, 0, ARENA + CTX_OFF) + bytes(arena))

out[0:0] = [struct.pack('<I', len(out))]
open(sys.argv[1], 'wb').write(b''.join(out))
print('[gen_cases] N=%d (通常 %d + 成功経路 %d + fn=1 成功経路 %d) -> %s' % (len(out) - 1, N, SUCC, SUCC1, sys.argv[1]))
