#!/usr/bin/env python3
"""元の機械語 (native_ref) が落ちた case の原因を入力から切り分ける (T-SH-46 受入 3)。
native_ref の stderr (`[native] crash case=C fn=F sig=S addr=A`) と cases.bin を突き合わせ、入力から予測される原因に分類する。
分類 (上から順に当てはまるもの 1 つ):
  timeout     : SIGALRM (300 ms 超過)
  ctx-null    : ctx 大域 (RVA 0x49e08) が 0 → 0x1de0 が [ctx+8] を読む (addr 0x8)
  key-deref   : 0x12a50 が key = 0x180019f0(a0) を指すオブジェクトの [key+0x688] を読む (addr = key+0x688)
  out-overrun : 出力先 a2 + a1 が arena 外へ出る (0x1c8f0 の memset / 0x12ed0 の書込)
  other       : 上のどれでもない
usage: crash_class.py WORKDIR STDERR_FILE
"""
import re, struct, sys, collections

W, ERR = sys.argv[1], sys.argv[2]
ARENA = 0x30100000
ARENA_SZ = 0x10000
CASE_HDR = 48


def key_of(a):
    """0x180019f0 の変換 (gen_cases.py と同じ)。"""
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


cases = open(W + '/cases.bin', 'rb').read()
n = struct.unpack_from('<I', cases, 0)[0]
info = []
p = 4
for _ in range(n):
    fn, _pad, a0, a1, a2, a3, ctx = struct.unpack_from('<IIQQQQQ', cases, p)
    info.append((fn, a0, a1, a2, ctx))
    p += CASE_HDR + ARENA_SZ

pat = re.compile(r'\[native\] crash case=(\d+) fn=(\d+) sig=(\S+?)(?: addr=0x([0-9a-f]+))?$')
cnt = collections.Counter()
rows = []
for line in open(ERR):
    m = pat.search(line.strip())
    if not m:
        continue
    c, fn, sig, addr = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    fn_, a0, a1, a2, ctx = info[c]
    ad = int(addr, 16) if addr else None
    k = key_of(a0)
    if sig == 'ALRM':
        cls = 'timeout'
    elif ctx == 0:
        cls = 'ctx-null'
    elif ad is not None and ad == (k + 0x688) & 0xFFFFFFFFFFFFFFFF:
        cls = 'key-deref'
    elif a2 + a1 > ARENA + ARENA_SZ and ARENA <= a2 < ARENA + ARENA_SZ:
        cls = 'out-overrun'
    else:
        cls = 'other'
    cnt[cls] += 1
    rows.append((c, fn, cls, hex(ad) if ad is not None else '-'))

print('[crash] 落ちた case %d 件の分類 (入力から予測。native の fault アドレスと照合): %s' % (len(rows), dict(cnt)))
print('[crash] 分類ごとの case 例 (case, fn, 分類, addr): %s' % [r for r in rows if r[2] == 'other'][:8])
