#!/usr/bin/env python3
"""movnti (閉包内 24 箇所) を含む経路に入る入力を決定的に生成する (T-SH-90 / #3589)。

movnti は memset (f_18001c8f0・8 箇所) の大きいブロック経路にだけある。両 export (fn=0 REXGetCreatorInfo・fn=1 REXGetInfo) は
  memset(dst=a2, 0, count=sext32(a1))  (a1 >= 0x500 / a2 != 0 / 木の検索が成功した後)
を呼ぶ。count >= 0x70000 (= 0x1c00 << 6) で movnti の経路に入る。memcpy (f_18001ca80・16 箇所) は count >= 0x10000 でだけ
movnti に入り、その唯一の呼出し元 (f_18001bde8) は count = 0x40 固定なので入力では到達しない (REPORT_APPENDIX_3589.md)。

case 形式は gen_cases.py と同じ (native_ref.c / run_wasm.mjs が読む)。期待 (reach / info) は OUT と同じ dir の movnti_expect.json に書く。
  reach   : a1 in [0x70000, 0x80000)。wasm は movnti の VA で trap する想定。native は arena 外へ書いて落ちる想定。
  info    : a1 in [0x10000, 0x70000) (閾値未満の対照)。判定に入れず結果だけ表示する。想定 (trap しない) と実測が食い違った (REPORT_APPENDIX_3589.md・未解決)。
reach / info は fn=0 (REXGetCreatorInfo)。木の検索の直後に memset を呼ぶため、入力だけで memset に届く。fn=1 は memset の前の node 参照で落ちるため使わない。
usage: gen_movnti.py OUT
"""
import json, os, random, struct, sys

ARENA = 0x30100000
ARENA_SZ = 0x10000
CTX_OFF = 0x8000
NODE = ARENA + 0xC100
N_REACH = 16
N_CTRL = 4
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


def case(kind, fn, a1):
    a0 = ptr()
    a2 = ptr()
    arena = bytearray(ARENA_SZ)
    for q in range(ARENA_SZ // 8):
        v = ptr() if (CTX_OFF <= 8 * q < CTX_OFF + 0x4000 or rnd.random() >= 0.1) else 0
        struct.pack_into('<Q', arena, 8 * q, v)
    struct.pack_into('<QQQ', arena, NODE - ARENA, 0, 0, key_of(a0))
    struct.pack_into('<Q', arena, CTX_OFF + 0x20, NODE)
    out.append(struct.pack('<IIQQQQQ', fn, 0, a0, a1, a2, 0, ARENA + CTX_OFF) + bytes(arena))
    expect.append({'kind': kind, 'fn': fn, 'a1': a1})


for i in range(N_REACH):
    case('reach', 0, rnd.randrange(0x70000, 0x80000))
for i in range(N_CTRL):
    case('info', 0, rnd.randrange(0x10000, 0x70000))

out[0:0] = [struct.pack('<I', len(out))]
open(sys.argv[1], 'wb').write(b''.join(out))
json.dump(expect, open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), 'movnti_expect.json'), 'w'))
print('[gen_movnti] reach=%d info=%d -> %s' % (N_REACH, N_CTRL, sys.argv[1]))
