#!/usr/bin/env python3
"""FL の ASIO コールバック bufferSwitchTimeInfo (0xc56ae0) から到達する関数集合を静的に数える (AU-8 #194 §4-2・AU-27 #2993)。

worklet 内で FL ミキサを走らせる再設計の見積りで、ミキサ render から到達する関数の中の
CS / 待機 / スレッド API の個数が要る。
  1. .pdata で関数範囲を得て、各関数を capstone で線形逆アセンブルする
  2. 直接 call (e8) と関数範囲外への直接 jmp (tail call) を辺にして BFS で到達集合を作る (下限)
  3. 間接 call/jmp の目標を閉世界の候補で置く (上限)。候補 AT = アドレスを取られた関数:
     (a) 非コード領域 (.data 等) と .text に現れる関数アドレス (vtable・関数ポインタ表を含む。.text 内の表も対象)
     (b) コード中の rip 相対 lea・即値 mov で作られる関数アドレス
     どちらも生バイト走査で求める (偽陽性は候補を広げる側)。
  4. 参考 (slot): 基底がメモリ読込の [R+d] は、非コード領域の関数ポインタ表 (vtable 候補) の d 番目の
     スロットに候補を限る。R が表を指すことは仮定 (未検証)。上限には使わない。
  5. IAT 経由の API 呼出しを thread_api.py の分類で数える
  6. --check-objdump: 上限の到達集合を objdump (全 .text の線形走査) で別実装して突き合わせる (検算)
限界: 上限は AT の閉世界仮定 (関数アドレスは lea・即値・データ表で作られる) に依存する。
  間接箇所の真の目標は特定していない (候補で近似)。
判定 (gate): 入口 VA が .pdata の関数先頭であること、上限の到達集合に既知の辺 (winmm!timeGetTime。REPORT の
  bufferSwitchTimeInfo の systemTime 経路) があること。gate は到達集合の正しさを検査しない (入口の位置のみ)。
  --negctl は入口を関数内部 (先頭+1) に差し替え、gate が FAIL することを確認する (exit 0 = 期待どおり FAIL)。
使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 mixer_reach.py [--json out.json] [--negctl] [--check-objdump]
依存: pefile, capstone (--check-objdump は objdump)"""
import sys, os, re, struct, json, bisect, collections, subprocess
import pefile
import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from thread_api import CLASSES, API2CLASS
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from paths import FL_WIN64_DIR

NEG = "--negctl" in sys.argv
ENTRY_VA = 0xC56AE0   # FL の bufferSwitchTimeInfo 本体 (tools/audio/REPORT.md の ASIO 表)
KNOWN_EDGE = ("winmm.dll", "timeGetTime")
MAIN_PE = os.path.join(FL_WIN64_DIR, "extracted", "block00031_PE.bin")
shown = os.path.relpath(MAIN_PE, FL_WIN64_DIR)

pe = pefile.PE(MAIN_PE)
img = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
t0, t1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
pd = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
pdd = img[pd.VirtualAddress:pd.VirtualAddress + pd.Misc_VirtualSize]
funcs = []
for i in range(0, len(pdd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pdd, i)
    if b == 0:
        break
    funcs.append((b, e))
funcs.sort()
fstarts = [f[0] for f in funcs]
fset = set(fstarts)
NONCODE = [(s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize) for s in pe.sections
           if s.Name.rstrip(b"\0") not in (b".text", b".pdata", b".rsrc", b".reloc", b".idata")]


def func_of(rva):
    k = bisect.bisect_right(fstarts, rva) - 1
    return funcs[k] if k >= 0 and funcs[k][0] <= rva < funcs[k][1] else None


def qv(rva):
    return struct.unpack_from("<Q", img, rva)[0] - base


def in_noncode(a):
    return any(a0 <= a and a + 8 <= a1 for a0, a1 in NONCODE)


def in_text(r):
    return t0 <= r < t1


iat = {}
for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
    for imp in e.imports:
        if imp.name:
            iat[imp.address - base] = (e.dll.decode().lower(), imp.name.decode())
thunks = {}
for m in re.finditer(rb"\xff\x25", img[t0:t1]):
    i = m.start()
    tgt = t0 + i + 6 + struct.unpack_from("<i", img, t0 + i + 2)[0]
    if tgt in iat:
        thunks[t0 + i] = iat[tgt]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
X86_IMM, X86_MEM, X86_REG = capstone.x86.X86_OP_IMM, capstone.x86.X86_OP_MEM, capstone.x86.X86_OP_REG
RIP = capstone.x86.X86_REG_RIP


def addr_refs():
    """コード中で作られるアドレス (RVA): rip 相対 lea (7 バイト) と即値 mov (B8+r imm32 / 48 C7 imm32 / 48 B8+r imm64)。生バイト走査。"""
    tb = bytes(img[t0:t1])
    refs = set()
    for m in re.finditer(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", tb):
        p = m.start()
        refs.add(t0 + p + 7 + struct.unpack_from("<i", tb, p + 3)[0])
    for m in re.finditer(rb"\x48\xb8.{8}|\x48\xc7[\xc0-\xc7].{4}|[\xb8-\xbf].{4}", tb, re.S):
        p = m.start()
        if tb[p] == 0x48 and tb[p + 1] == 0xB8:
            v = struct.unpack_from("<Q", tb, p + 2)[0]
        elif tb[p] == 0x48:
            v = struct.unpack_from("<i", tb, p + 3)[0]
        else:
            v = struct.unpack_from("<I", tb, p + 1)[0]
        refs.add(v - base)
    return refs


REFS = addr_refs()
AT = set(r for r in REFS if r in fset)
for a0, a1 in NONCODE + [(t0, t1)]:
    for a in range(a0, a1 - 7, 8):
        v = qv(a)
        if v in fset:
            AT.add(v)


def table_len(a):
    n = 0
    while in_noncode(a + 8 * n) and in_text(qv(a + 8 * n)) and n < 1024:
        n += 1
    return n


VT = {}   # 参考 (slot): 非コード領域で、コードを指す連続 qword の表の先頭 -> 表の長さ
for a in REFS:
    if in_noncode(a) and in_text(qv(a)):
        VT[a] = table_len(a)
for a0, a1 in NONCODE:
    for a in range(a0, a1 - 7, 8):
        v = qv(a)
        if any(b0 <= v < b1 for b0, b1 in NONCODE) and in_text(qv(v)) and v not in VT:
            VT[v] = table_len(v)
SLOT_CACHE = {}


def slot_cands(d):
    if d not in SLOT_CACHE:
        out = set()
        for V in VT:
            a = V + d
            if in_noncode(a) and qv(a) in AT:
                out.add(qv(a))
        SLOT_CACHE[d] = out
    return SLOT_CACHE[d]


def loaded(L, i, reg):
    """直前 6 命令 (call/jmp/ret を越えない) で reg が mov reg, [mem] により定義されたか。"""
    for p in range(i - 1, max(-1, i - 7), -1):
        pi = L[p]
        if pi.mnemonic in ("call", "jmp", "ret"):
            break
        if pi.operands and pi.operands[0].type == X86_REG and pi.operands[0].reg == reg:
            return pi.mnemonic == "mov" and len(pi.operands) > 1 and pi.operands[1].type == X86_MEM
    return False


def reach(entry_rva, mode):
    """mode: direct (下限: 直接辺のみ) / at (上限: 間接辺は AT 閉世界) / slot (参考: 読込基底の [R+d] は vtable スロット候補)"""
    seen = {}
    q = [entry_rva]
    imps = collections.Counter()
    sites = collections.defaultdict(list)     # (dll,name) -> [call site VA]
    ind = collections.Counter()               # 間接 call/jmp の形ごとの箇所数
    unknown = 0
    insns = 0
    direct = 0                                # 関数宛て直接 call/jmp (tail call を含む。辺になったもの)
    at_pushed = False
    n_slot = n_at = 0
    while q:
        r = q.pop()
        f = func_of(r)
        if f is None:
            unknown += 1
            continue
        if f[0] in seen:
            continue
        seen[f[0]] = f
        L = list(md.disasm(bytes(img[f[0]:f[1]]), base + f[0]))
        for i, ins in enumerate(L):
            insns += 1
            if ins.mnemonic not in ("call", "jmp") or not ins.operands:
                continue
            op = ins.operands[0]
            if op.type == X86_IMM:
                tgt = op.imm - base
                if tgt in thunks:
                    imps[thunks[tgt]] += 1
                    sites[thunks[tgt]].append(ins.address)
                elif ins.mnemonic == "jmp" and f[0] <= tgt < f[1]:
                    continue
                else:
                    direct += 1
                    q.append(tgt)
                continue
            if op.type == X86_MEM and op.mem.base == RIP and op.mem.index == 0:
                tgt = ins.address + ins.size + op.mem.disp - base
                if tgt in iat:
                    imps[iat[tgt]] += 1
                    sites[iat[tgt]].append(ins.address)
                    continue
                ind[f"{ins.mnemonic} [rip-data]"] += 1
            elif op.type == X86_REG:
                ind[f"{ins.mnemonic} reg"] += 1
            else:
                ind[f"{ins.mnemonic} [mem]"] += 1
            if mode == "direct":
                continue
            if (mode == "slot" and op.type == X86_MEM and op.mem.base not in (0, RIP) and op.mem.index == 0
                    and loaded(L, i, op.mem.base)):
                c = slot_cands(op.mem.disp)
                if c:
                    n_slot += 1
                    q.extend(sorted(c))
                    continue
            n_at += 1
            if not at_pushed:
                q.extend(sorted(AT))
                at_pushed = True
    return dict(seen=seen, imps=imps, sites=sites, ind=ind, unknown=unknown, insns=insns, direct=direct,
                n_slot=n_slot, n_at=n_at)


def summarize(R):
    api_calls = sum(R["imps"].values())
    indirect = sum(R["ind"].values())
    total = R["direct"] + api_calls + indirect     # 分母: 到達集合内の call/jmp 箇所 (関数内の無条件 jmp は除く)
    summ = {}
    for cls in CLASSES:
        hit = set()
        n_sites = 0
        for key, ss in R["sites"].items():
            if API2CLASS.get(key[1]) != cls:
                continue
            n_sites += len(ss)
            hit |= {func_of(s - base)[0] for s in ss if func_of(s - base)}
        summ[cls] = {"call_sites": n_sites, "distinct_functions": len(hit)}
    return dict(functions=len(R["seen"]), insns=R["insns"], unknown=R["unknown"], direct=R["direct"],
                api=api_calls, indirect=indirect, total=total,
                indirect_pct=round(100.0 * indirect / total, 1) if total else 0.0,
                ind=dict(R["ind"]), summary=summ, known_hit=R["imps"].get(KNOWN_EDGE, 0),
                apis=[{"dll": k[0], "api": k[1], "class": API2CLASS.get(k[1]), "call_sites": v}
                      for k, v in R["imps"].most_common()])


def objdump_check():
    """objdump (全 .text の線形走査) で上限 (direct + AT 閉世界) を別実装し、関数数・直接・API・間接の箇所数を返す。"""
    out = subprocess.run(["objdump", "-d", "-M", "intel", "--no-show-raw-insn", "-j", ".text", MAIN_PE],
                         capture_output=True, text=True, check=True).stdout
    line_re = re.compile(r"^\s*([0-9a-f]+):\t(\S+)\s*(.*)$")
    addrs, ops = [], {}
    for ln in out.splitlines():
        m = line_re.match(ln)
        if m:
            a = int(m.group(1), 16)
            addrs.append(a)
            ops[a] = (m.group(2), m.group(3))
    addrs.sort()

    def rva_of(va):
        return va - base

    def iat_name_at(va):
        mn, rest = ops.get(va, ("", ""))
        c = re.search(r"# (0x[0-9a-f]+)", rest)
        if mn == "jmp" and "[rip" in rest and c and rva_of(int(c.group(1), 16)) in iat:
            return iat[rva_of(int(c.group(1), 16))]
        return None

    seen, api, ind, direct = set(), collections.Counter(), collections.Counter(), 0
    q, at_pushed = [ENTRY_VA - base], False
    while q:
        r = q.pop()
        f = func_of(r)
        if f is None or f[0] in seen:
            continue
        seen.add(f[0])
        lo, hi = bisect.bisect_left(addrs, base + f[0]), bisect.bisect_left(addrs, base + f[1])
        for a in addrs[lo:hi]:
            mn, rest = ops[a]
            if mn not in ("call", "jmp"):
                continue
            tgt_txt = rest.split()[0] if rest else ""
            if re.fullmatch(r"(0x)?[0-9a-f]+", tgt_txt):
                tgt = rva_of(int(tgt_txt, 16))
                th = iat_name_at(tgt + base)
                if th:
                    api[th] += 1
                elif mn == "jmp" and f[0] <= tgt < f[1]:
                    continue
                else:
                    direct += 1
                    q.append(tgt)
                continue
            c = re.search(r"# (0x[0-9a-f]+)", rest)
            if c and "[rip" in rest and rva_of(int(c.group(1), 16)) in iat:
                api[iat[rva_of(int(c.group(1), 16))]] += 1
                continue
            ind["[mem]" if "[" in rest else "reg"] += 1
            if not at_pushed:
                q.extend(sorted(AT))
                at_pushed = True
    return dict(functions=len(seen), direct=direct, api_sites=sum(api.values()), indirect=sum(ind.values()))


entry_rva = ENTRY_VA - base + (1 if NEG else 0)
is_start = any(s == entry_rva for s in fstarts)
LOW = reach(entry_rva, "direct")
UP = reach(entry_rva, "at")
SLOT = reach(entry_rva, "slot")
low, up, slot = summarize(LOW), summarize(UP), summarize(SLOT)
gate = [
    {"name": "entry_is_pdata_start", "ok": is_start},
    {"name": "known_edge_timeGetTime_reached", "ok": up["known_hit"] >= 1, "got": up["known_hit"]},
]
ok = all(g["ok"] for g in gate)
check = objdump_check() if "--check-objdump" in sys.argv else None

print(f"PE: {shown}  (ImageBase {base:#x}, functions(.pdata)={len(funcs)}, imports={len(iat)}, thunks={len(thunks)})")
print(f"entry: {ENTRY_VA if not NEG else ENTRY_VA + 1:#x} (VA)  pdata 関数先頭: {is_start}")
print(f"候補集合 AT (アドレスを取られた関数): {len(AT)}  (うちコード参照 {len(REFS & fset)})")
print(f"vtable 候補表 (参考 slot 用・非コード領域でコードを指す連続 qword): {len(VT)} 表 / {sum(VT.values())} スロット")
for name, s, R in (("下限 (直接 call + tail jmp の BFS)", low, LOW),
                   ("上限 (間接 call/jmp の目標を AT 閉世界で置く)", up, UP),
                   ("参考 (上限 + 読込基底の [R+d] を vtable 候補スロットに限定)", slot, SLOT)):
    print(f"\n## {name}")
    print(f"到達集合 (関数 / 命令 / 範囲外の目標): {s['functions']} / {s['insns']} / {s['unknown']}")
    print("到達集合内の call/jmp 箇所 (分母。関数内の無条件 jmp は除く):")
    print(f"  {'関数宛て直接':24s} {s['direct']:6d}")
    print(f"  {'API 呼出し':24s} {s['api']:6d}")
    print(f"  {'間接':24s} {s['indirect']:6d}  ({s['indirect_pct']:.1f}% of {s['total']})")
    print(f"  {'合計':24s} {s['total']:6d}")
    if R is not LOW:
        print(f"  間接の目標: AT 候補で近似 {R['n_at']} 箇所 / vtable スロット候補 {R['n_slot']} 箇所 / 候補が空で未解決 0 箇所")
    print("未追跡の間接 call/jmp (形ごと。vtable 呼出しとの対応は推定):")
    for k, v in sorted(s["ind"].items(), key=lambda kv: -kv[1]):
        print(f"  {k:24s} {v:6d}")
    print("## 到達集合内の API 呼出し (分類別: call 箇所 / 呼出し関数の distinct 数)")
    for cls, v in s["summary"].items():
        print(f"  {cls:17s} call_sites={v['call_sites']:5d} distinct_functions={v['distinct_functions']:5d}")
print("\n## 上位 API (上限・到達集合内の call 箇所数)")
for a in up["apis"][:25]:
    print(f"  {a['dll']:16s} {a['api']:30s} {a['call_sites']:5d}")
print("\n## gate")
for g in gate:
    print(f"  {'PASS' if g['ok'] else 'FAIL'} {g['name']}" + (f" got={g['got']}" if "got" in g else ""))
if check is not None:
    print("\n## 検算 (objdump 全 .text 線形走査で上限を別実装)")
    print(f"  objdump : 関数 {check['functions']} / 関数宛て直接 {check['direct']} / API {check['api_sites']} / 間接 {check['indirect']}")
    print(f"  capstone: 関数 {up['functions']} / 関数宛て直接 {up['direct']} / API {up['api']} / 間接 {up['indirect']}")
if "--json" in sys.argv:
    with open(sys.argv[sys.argv.index("--json") + 1], "w") as fh:
        json.dump({"pe": shown, "negctl": NEG, "entry_va": hex(ENTRY_VA), "at_size": len(AT), "vtable_tables": len(VT),
                   "lower": low, "upper": up, "slot_reference": slot, "objdump_check": check,
                   "gate": gate, "ok": ok}, fh, indent=1)
if NEG:
    print(f"\nnegctl: gate {'FAIL (期待どおり)' if not ok else 'PASS (= 検出能力なし)'}")
    sys.exit(0 if not ok else 1)
sys.exit(0 if ok else 1)
