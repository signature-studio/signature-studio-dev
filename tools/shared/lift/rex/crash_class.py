#!/usr/bin/env python3
"""元の機械語 (native_ref) が落ちた case の原因を入力と fault 時のレジスタから切り分ける (T-SH-46 受入 3 / T-SH-89 #3588)。
native_ref の stderr (`[native] crash case=C fn=F sig=S addr=A rip=P reg=V ...`) と cases.bin を突き合わせ、分類する。
分類 (上から順に当てはまるもの 1 つ。key = key_of(a0) = 木の根のノードの key):
  timeout      : SIGALRM (300 ms 超過)
  ctx-null     : ctx 大域 (RVA 0x49e08) が 0 → 0x1de0 が [ctx+8] を読む (addr 0x8)
  key-deref    : 木の根の key を this として、0x12a50 (cmp [this+0x688],0) か 0x12b70 (mov rax,[this+0x690]) が読む。
                 rcx = key で、addr = key+0x688 か key+0x690 (key は canonical で、アリーナ外の番地)
  key-noncanon : 同じ読みで key が非 canonical (bit 47..63 が揃わない)。CPU は GP 例外にし、SIGSEGV の si_addr は 0
  succ-null-src: 成功経路の 0x12ed0 が B (= [key+0x688]) の文字列を 0x1f260 でコピーするとき、
                 cap (B+cap) >= 0x10 のヒープ経路でコピー元 [B+buf] が 0 (rdx = 0 で 0x1f298 が読む)
  out-overrun  : 出力先 a2 + a1 が arena 外へ出る (0x1c8f0 の memset / 0x12ed0 の書込)
  other        : 上のどれでもない
usage: crash_class.py WORKDIR STDERR_FILE
"""
import re, struct, sys, collections

W, ERR = sys.argv[1], sys.argv[2]
ARENA = 0x30100000
ARENA_SZ = 0x10000
CASE_HDR = 48
ACC_KEY_688 = 0x30012a50   # cmp qword ptr [rcx+0x688], 0
ACC_KEY_690 = 0x30012b70   # mov rax, qword ptr [rcx+0x690]
COPY_LOAD = 0x3001f298     # 0x1f260 (文字列コピー) の qword 読込 mov rax, qword ptr [rdx]
B_FIELDS = [(0x28, 0x10), (0x50, 0x38), (0x78, 0x60), (0xa0, 0x88), (0xc8, 0xb0)]  # 0x12ed0 の 5 本: (cap, buf)
B_OFF = 0xC300   # B = ARENA+0xC300 (gen_cases.py の OBJ_B)
M64 = (1 << 64) - 1


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


def canonical(x):
    return x < (1 << 47) or x >= (M64 + 1 - (1 << 47))


cases = open(W + '/cases.bin', 'rb').read()
n = struct.unpack_from('<I', cases, 0)[0]
info = []
p = 4
for _ in range(n):
    fn, _pad, a0, a1, a2, a3, ctx = struct.unpack_from('<IIQQQQQ', cases, p)
    info.append((fn, a0, a1, a2, ctx, p + CASE_HDR))
    p += CASE_HDR + ARENA_SZ

pat = re.compile(r'\[native\] crash case=(\d+) fn=(\d+) sig=(\S+)(?: addr=0x([0-9a-f]+) rip=0x([0-9a-f]+)((?: \w+=0x[0-9a-f]+)*))?$')
cnt = collections.Counter()
rip_cnt = collections.Counter()
rows = []
for line in open(ERR):
    m = pat.search(line.strip())
    if not m:
        continue
    c, fn, sig, addr, rip = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)
    regs = {k: int(v, 16) for k, v in re.findall(r'(\w+)=0x([0-9a-f]+)', m.group(6) or '')}
    fn_, a0, a1, a2, ctx, aoff = info[c]
    ad = int(addr, 16) if addr else None
    rp = int(rip, 16) if rip else None
    k = key_of(a0)
    if sig == 'ALRM':
        cls = 'timeout'
    elif ctx == 0:
        cls = 'ctx-null'
    elif rp in (ACC_KEY_688, ACC_KEY_690) and regs.get('rcx') == k and ad == 0 and not canonical(k):
        cls = 'key-noncanon'
    elif rp in (ACC_KEY_688, ACC_KEY_690) and regs.get('rcx') == k and ad is not None \
            and ad in ((k + 0x688) & M64, (k + 0x690) & M64):
        cls = 'key-deref'
    elif rp == COPY_LOAD and regs.get('rdx') == 0 and 0 <= (regs.get('r11', 0) - a2) // 0x100 < len(B_FIELDS):
        arena = cases[aoff:aoff + ARENA_SZ]
        capo, bufo = B_FIELDS[(regs['r11'] - a2) // 0x100]
        q = lambda o: struct.unpack_from('<Q', arena, B_OFF + o)[0]
        cls = 'succ-null-src' if (q(capo) >= 0x10 and q(bufo) == 0) else 'other'
    elif a2 + a1 > ARENA + ARENA_SZ and ARENA <= a2 < ARENA + ARENA_SZ:
        cls = 'out-overrun'
    else:
        cls = 'other'
    cnt[cls] += 1
    rip_cnt[(hex(rp) if rp else '-', cls)] += 1
    rows.append((c, fn, cls, hex(ad) if ad is not None else '-', hex(rp) if rp else '-'))

print('[crash] 落ちた case %d 件の分類 (入力と fault 時のレジスタから切り分け): %s' % (len(rows), dict(cnt)))
print('[crash] fault 命令 (rip, 分類): %s' % sorted(((k_[0], k_[1], v) for k_, v in rip_cnt.items())))
print('[crash] fn 別の分類 (fn, 分類, 件数): %s' % sorted((f, c_, v) for (f, c_), v in collections.Counter((r[1], r[2]) for r in rows).items()))
print('[crash] other の case (case, fn, 分類, addr, rip): %s' % [r for r in rows if r[2] == 'other'][:8])
