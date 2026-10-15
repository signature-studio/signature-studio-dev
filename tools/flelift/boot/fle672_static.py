#!/usr/bin/env python3
"""FLE-672 (#672) 静的判定の再現: 2^20 面の経路と、その分岐入力 (LoadLibraryW / GetProcAddress の結果) を示す。

  python3 tools/flelift/boot/fle672_static.py [PE]   # PE 既定 = $FL_WIN64_DIR/extracted/block00031_PE.bin

出力は REPORT_APPENDIX_672.md §B の数値の出典。読むだけで、ファイルは変えない。
"""
import bisect, os, re, struct, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PE_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("FL_WIN64_DIR", ""), "extracted", "block00031_PE.bin")
pe = pefile.PE(PE_PATH, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
DATA = pe.__data__
MD = Cs(CS_ARCH_X86, CS_MODE_64)


def off(va):
    return pe.get_offset_from_rva(va - BASE)


def dis(start, end):
    return list(MD.disasm(DATA[off(start):off(end)], start))


def annotate(i):
    """rip 相対の参照先 VA を併記する (1 行 = 1 命令)。"""
    s = f"{i.address:x}: {i.mnemonic} {i.op_str}"
    m = re.search(r"\[rip \+ (0x[0-9a-f]+)\]", i.op_str)
    if m:
        s += f"   ; [VA 0x{i.address + i.size + int(m.group(1), 16):x}]"
    return s


# .pdata と UNWIND_INFO (EH scope table) を読む
ex = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
rows = []
for k in range(ex.SizeOfRawData // 12):
    b, e, u = struct.unpack_from("<III", DATA, ex.PointerToRawData + k * 12)
    if not b:
        continue
    fo = pe.get_offset_from_rva(u)
    flags = DATA[fo] >> 3
    scopes = []
    if flags & 1:
        ncodes = DATA[fo + 2]
        j = fo + 4 + ((ncodes + 1) & ~1) * 2
        cnt, = struct.unpack_from("<I", DATA, j + 4)
        for n in range(min(cnt, 64)):
            bg, en, kind, tg = struct.unpack_from("<IIII", DATA, j + 8 + 16 * n)
            scopes.append((BASE + bg, BASE + en, kind, BASE + tg))
    rows.append((BASE + b, BASE + e, flags, scopes))
rows.sort()
starts = [r[0] for r in rows]


def fn_of(va):
    i = bisect.bisect_right(starts, va) - 1
    return rows[i] if i >= 0 and rows[i][0] <= va < rows[i][1] else None


print("== 1. 関数の EH 属性 (flags: 1=EHANDLER 2=UHANDLER。scope kind 2 = try/except・0 = finally 系)")
for name, va in [("f_815050 (2^20 面を作る)", 0x815050), ("f_815e10 (呼出し・分岐)", 0x815E10),
                 ("f_11c2d80 (f_815e10 の呼出元)", 0x11C2D80), ("f_6b8fa0 (面の確保)", 0x6B8FA0),
                 ("f_6cefb0 (面の取得)", 0x6CEFB0), ("f_6c7610 (fill 呼出し)", 0x6C7610),
                 ("f_4120c0 (System.InitUnits)", 0x4120C0)]:
    f = fn_of(va)
    kinds = [(hex(s[0]), hex(s[1]), s[2]) for s in f[3]] if f else []
    print(f"  {name:32s} entry=0x{f[0]:x} flags={f[2]} scopes={kinds}" if f else f"  {name} no pdata")

print("\n== 2. 2^20 面の経路の分岐点 (f_815e10: 0x815e10〜0x815ece)")
for i in dis(0x815E10, 0x815ECF):
    if i.address in (0x815E1E, 0x815E25, 0x815E33, 0x815E52, 0x815E60, 0x815E6B, 0x815E86, 0x815E8D,
                     0x815E96, 0x815EB5, 0x815EB9, 0x815EBC, 0x815E38, 0x815E3F, 0x815E46):
        print("  " + annotate(i))
print("  flag = (qword [VA 0x15f6f88] != 0): 0x815e60〜0x815e6b の setne で [VA 0x15f6f91] に入る。")
print("  flag == 0 → 0x815eb5 で f_815050 (2^20 面) を呼ぶ。flag != 0 → 0x815e96 の代替経路。")
print("  VA 0x15f6f88 は 0x815e52 で f_4235f0(handle VA 0x15f6f80, L\"CreateCursorFromFont\") の戻り値を入れる。")
print("  VA 0x15f6f80 は 0x815e38 で f_6539e0(L\"ILTools\") の戻り値 (module handle)。")

print("\n== 3. 寸法 2^20 の出所 (f_815050: 0x81571b・0x81572c)")
for i in dis(0x81571B, 0x815729):
    if i.mnemonic == "movabs":
        v = int(i.op_str.split(",")[1].strip(), 16)
        print(f"  {i.address:x}: movabs {i.op_str}  -> double {struct.unpack('<d', struct.pack('<Q', v))[0]:.0f}")
print("  W = f(c1) + SPI + f(2^20 + c2) + 4·SPI (0x815831〜0x815854)。定数 2^20 は stub 値に依らない。")

print("\n== 4. 面の確保 f_6b8fa0: サイズは 32bit imul (0x6b8fbf・0x6b8fdc)。w = h = 2^20 の結果")
for bpp in (1, 4):
    stride = (((1 << 20) * bpp + 31) >> 5) << 2
    print(f"  bpp={bpp}: stride={stride} size32=(stride*h) mod 2^32 = {(stride * (1 << 20)) & 0xFFFFFFFF}")

print("\n== 5. GetMem(size<=0) の native 挙動 (System._GetMem = 0x409410)")
for i in dis(0x409410, 0x40941F):
    print("  " + annotate(i))
print("  size<=0 → 0x40941a で xor ebx,ebx → nil (ホストの fle_ov_getmem も R[1]>0 でなければ nil)")

print("\n== 6. 文字列 (分岐入力の名前)")
for va, n in [(0x815EDC, 9), (0x815EEC, 40)]:
    raw = DATA[off(va):off(va) + n * 2 + 2]
    print(f"  0x{va:x}: {raw.decode('utf-16-le', 'replace').split(chr(0))[0]!r}")
