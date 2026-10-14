#!/usr/bin/env python3
# #3052: FLEngine_x64.dll 内の `WFBox`・`DitherBox`・レジストリ読取り API の参照を静的に数える (受入 1 の経路調査)。
# 使い方: uv run --with pefile --with capstone python3 tools/flp/s3_regread_xref.py <block00031_PE.bin>
#   (素材 $RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin。repo には書かない)
# 出力は REPORT_APPENDIX_3052.md §18 の数値の根拠。関数境界は .pdata、逆アセンブルは capstone (関数単位)。
# 陰性対照: 環境変数 S3_DROP_CALL=<call 命令の VA> を与えると、その 1 件を数えない (件数が 1 減ることを確かめる)。
import bisect
import collections
import os
import struct
import sys

import capstone
import pefile

P = sys.argv[1]
DROP = int(os.environ.get("S3_DROP_CALL", "0"), 16)
pe = pefile.PE(P, fast_load=False)
pe.parse_data_directories()
base = pe.OPTIONAL_HEADER.ImageBase
sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
text = sec[b".text"]
tva = base + text.VirtualAddress
tdata = text.get_data()
data = pe.__data__


def va_of(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return s.Name.rstrip(b"\0").decode(), base + s.VirtualAddress + off - s.PointerToRawData
    return "-", 0


# 1) 文字列参照: ASCII (DFM / RTTI) と UTF-16 (Delphi の文字列リテラル)。ヒットは VA (セクション内) と前後のバイトを出す
ascii_names = [b"WFBox", b"DitherBox", b"QualityBox", b"FormatBox", b"WAVRenderForm"]
listed = {b"WFBox", b"DitherBox", b"WAVRenderForm"}
for nm in ascii_names:
    hits = []
    i = data.find(nm)
    while i != -1:
        hits.append(i)
        i = data.find(nm, i + 1)
    u16 = data.find(nm.decode().encode("utf-16-le"))
    print(f"string {nm.decode():14s} ascii_hits={len(hits)} utf16_hits={0 if u16 == -1 else 1}")
    if nm in listed:
        for off in hits:
            sname, va = va_of(off)
            print(f"  hit {nm.decode():13s} va={hex(va)} sec={sname} off={hex(off)} pre={data[off - 4:off]!r} post={data[off + len(nm):off + len(nm) + 24]!r}")

# 2) レジストリ API の IAT スロットと、それを jmp/call で呼ぶ thunk
reg_slots = {}
for e in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in e.imports:
        if imp.name and imp.name.decode().startswith("Reg"):
            reg_slots[imp.address] = imp.name.decode()
thunk = {}
for pat in (b"\xff\x25", b"\xff\x15"):
    i = tdata.find(pat)
    while i != -1:
        disp = struct.unpack_from("<i", tdata, i + 2)[0]
        tgt = tva + i + 6 + disp
        if tgt in reg_slots:
            thunk[tva + i] = reg_slots[tgt]
        i = tdata.find(pat, i + 1)
for va, nm in sorted(thunk.items()):
    if nm in ("RegQueryValueExW", "RegOpenKeyExW"):
        print(f"thunk {hex(va)} -> {nm}")
rq = {va for va, nm in thunk.items() if nm in ("RegQueryValueExW", "RegOpenKeyExW")}

# 3) 関数境界 (.pdata) と関数単位の逆アセンブル
pd = sec[b".pdata"].get_data()
funcs = set()
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b:
        funcs.add((base + b, base + e))
funcs = sorted(funcs)
fstart = [f[0] for f in funcs]


def fn_of(va):
    k = bisect.bisect_right(fstart, va) - 1
    if k >= 0 and funcs[k][0] <= va < funcs[k][1]:
        return funcs[k][0]
    return None


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
calls = collections.defaultdict(list)   # 直接 call/jmp の先 -> 呼出し箇所
lea_refs = collections.defaultdict(list)  # 関数 -> RIP 相対 lea の先
ninsn = 0
for fs, fe in funcs:
    o1, o2 = fs - tva, fe - tva
    if o1 < 0 or o2 > len(tdata):
        continue
    for ins in md.disasm(tdata[o1:o2], fs):
        ninsn += 1
        if ins.address == DROP:
            continue
        if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
            calls[int(ins.op_str, 16)].append(ins.address)
        elif ins.mnemonic == "lea" and "rip" in ins.op_str:
            seg = ins.op_str.split("rip")[1].split("]")[0].replace(" ", "")
            disp = int(seg.lstrip("+-"), 16) * (-1 if seg.startswith("-") else 1)
            lea_refs[fs].append(ins.address + ins.size + disp)
print(f"functions={len(funcs)} insns={ninsn}")

# 4) レジストリ読取り (RegQueryValueExW / RegOpenKeyExW) を直接呼ぶ関数
sites = [(t, c) for t in rq for c in calls.get(t, [])]
direct = collections.defaultdict(list)
for t, c in sites:
    direct[fn_of(c)].append(c)
print(f"direct call sites to Reg{{Query,Open}} thunks={len(sites)} functions={len(direct)} dropped={hex(DROP) if DROP else 'none'}")
for f in sorted(direct, key=lambda x: x or 0):
    print(f"  fn {hex(f)} sites={len(direct[f])} at={[hex(c) for c in direct[f]]}")

# 5) RegQueryValueExW を直接呼ぶ関数 (読取り層) と、その呼出し元の数
q_thunks = {va for va, nm in thunk.items() if nm == "RegQueryValueExW"}
q_funcs = sorted({fn_of(c) for t in q_thunks for c in calls.get(t, []) if fn_of(c)})
print(f"functions calling RegQueryValueExW thunk={len(q_funcs)}")
size_of = dict(funcs)
for f in q_funcs:
    callers = {fn_of(c) for c in calls.get(f, [])} - {None}
    print(f"  rd {hex(f)} size={hex(size_of[f] - f)} callers={len(callers)}")

# 6) 文字列リテラル (UTF-16 'General\\' 系) を lea で参照する関数
def utf16_at(va):
    o = va - tva
    if o < 0 or o + 2 > len(tdata):
        return None
    s = []
    for i in range(0, 200, 2):
        if o + i + 2 > len(tdata):
            break
        c = int.from_bytes(tdata[o + i:o + i + 2], "little")
        if c == 0 or c < 0x20 or c > 0x7E:
            break
        s.append(chr(c))
    return "".join(s)


key_fns = collections.defaultdict(set)
for f, tgts in lea_refs.items():
    for tg in tgts:
        s = utf16_at(tg)
        if s and s.startswith("Software\\Image-Line\\FL Studio 26\\General"):
            key_fns[s].add(f)
for s, fs in sorted(key_fns.items()):
    print(f"key literal {s!r} referenced by functions={sorted(hex(x) for x in fs)}")
