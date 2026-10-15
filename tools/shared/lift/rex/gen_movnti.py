#!/usr/bin/env python3
"""movnti (閉包内 24 箇所) を含む経路に入る入力を決定的に生成する (T-SH-90 / #3589)。

movnti は memset (f_18001c8f0・8 箇所) の大きいブロック経路にだけある。両 export (fn=0 REXGetCreatorInfo・fn=1 REXGetInfo) は
  memset(dst=a2, 0, count=sext32(a1))  (a1 >= 0x500 / a2 != 0 / 木の検索が成功した後)
を呼ぶ。count >= 0x70000 (= 0x1c00 << 6) で movnti の経路に入る。memcpy (f_18001ca80・16 箇所) は count >= 0x10000 でだけ
movnti に入り、その唯一の呼出し元 (f_18001bde8) は count = 0x40 固定なので入力では到達しない (REPORT_APPENDIX_3589.md)。

case 形式は gen_cases.py と同じ (native_ref.c / run_wasm.mjs が読む)。期待 (reach / info) は OUT と同じ dir の movnti_expect.json に書く。
  reach   : a1 in [0x70000, 0x80000)。a2 = arena 先頭。arena は layout.json の arena_sz (movnti モードは 0x80000・#4324)。完了を期待する。
  sweep   : a1 を [0x10000, 0x80000) で振る (a2 = arena 先頭)。movnti に入ったときは movnti の VA で trap する。入らないときは movnti 以外の
            OOB (VA 0) で trap するが、trap 位置は未特定 (wasm の線形メモリは arena より広く、arena 越境の store だけでは説明できない)。判定: movnti に入る ⇔ a1 ≥ 0x70000 (T-SH-94)。
reach / sweep は fn=0 (REXGetCreatorInfo)。木の検索の直後に memset を呼ぶため、入力だけで memset に届く。fn=1 は memset の前の node 参照で落ちるため使わない。
usage: gen_movnti.py OUT
"""
import json, os, random, struct, sys

ARENA = 0x30100000
ARENA_SZ = json.load(open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), 'layout.json')))['arena_sz']
CTX_OFF = 0x8000
NODE = ARENA + 0xC100
N_REACH = 16
SWEEP = sorted(set(list(range(0x10000, 0x80000, 0x2000)) + [0x27878, 0x2d324, 0x3d429, 0x3ffa3, 0x6ffc0, 0x6ffff, 0x70000, 0x70001, 0x70040]))
rnd = random.Random(3589)
out = []
expect = []


def ptr():
    return ARENA + 8 * rnd.randrange(0, ARENA_SZ // 8)


def key_of(a):
    """gen_cases.py と同じ (0x180019f0 の模倣・対合)。"""
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


def case(kind, fn, a1, a2=None):
    a0 = ptr()
    if a2 is None:
        a2 = ptr()
    arena = bytearray(ARENA_SZ)
    for q in range(ARENA_SZ // 8):
        v = ptr() if (CTX_OFF <= 8 * q < CTX_OFF + 0x4000 or rnd.random() >= 0.1) else 0
        struct.pack_into('<Q', arena, 8 * q, v)
    struct.pack_into('<QQQ', arena, NODE - ARENA, 0, 0, key_of(a0))
    struct.pack_into('<Q', arena, CTX_OFF + 0x20, NODE)
    out.append(struct.pack('<IIQQQQQ', fn, 0, a0, a1, a2, 0, ARENA + CTX_OFF) + bytes(arena))
    expect.append({'kind': kind, 'fn': fn, 'a1': a1})


# reach: 木の検索を通すため、gen_cases.py の SUCC1 と同じ構造 (根 key = key_of(a0) = OBJ・OBJ+0x688 = B・B+0x62c = 0) を置く。
# a2 = arena 先頭、a1 = reach 範囲。memset が 0x80000 の arena 内で完了する (#4324)。
OBJ = ARENA + 0xC200
B_ = ARENA + 0x9800
S_ = ARENA + 0x9000
Z_ = ARENA + 0xA800
LK = ARENA + 0xAF00


def reach_case(a1):
    arena = bytearray(ARENA_SZ)
    for base in (OBJ, S_, B_, Z_):
        for k in range(0, 0x700, 4):
            struct.pack_into('<I', arena, base - ARENA + k, 1)
    struct.pack_into('<I', arena, B_ + 0x62c - ARENA, 0)
    struct.pack_into('<QQQ', arena, NODE - ARENA, 0, 0, key_of(OBJ))
    struct.pack_into('<Q', arena, OBJ + 0x630 - ARENA, S_)
    struct.pack_into('<Q', arena, OBJ + 0x690 - ARENA, B_)
    struct.pack_into('<Q', arena, OBJ + 0x20 - ARENA, Z_)
    struct.pack_into('<Q', arena, OBJ + 0x688 - ARENA, 0)
    struct.pack_into('<Q', arena, CTX_OFF + 0x20, NODE)
    struct.pack_into('<Q', arena, CTX_OFF + 8, LK)
    struct.pack_into('<Q', arena, LK - ARENA, 0x10)
    out.append(struct.pack('<IIQQQQQ', 0, 0, key_of(OBJ), a1, ARENA, 0, ARENA + CTX_OFF) + bytes(arena))
    expect.append({'kind': 'reach', 'fn': 0, 'a1': a1})


for i in range(N_REACH):
    reach_case(rnd.randrange(0x70000, 0x80000))
for a1 in SWEEP:
    case('sweep', 0, a1, a2=ARENA)

out[0:0] = [struct.pack('<I', len(out))]
open(sys.argv[1], 'wb').write(b''.join(out))
json.dump(expect, open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), 'movnti_expect.json'), 'w'))
print('[gen_movnti] reach=%d sweep=%d -> %s' % (N_REACH, len(SWEEP), sys.argv[1]))
