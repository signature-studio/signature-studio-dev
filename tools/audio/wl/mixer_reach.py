#!/usr/bin/env python3
"""FL の ASIO コールバック bufferSwitchTimeInfo (0xc56ae0) から到達する関数集合を静的に数える (AU-8 #194 §4)。

worklet 内で FL ミキサを走らせる再設計の見積りで、ミキサ render から到達する関数の中の
CS / 待機 / スレッド API の個数が要る (tools/audio/wl/REPORT.md §4 の未解決項目)。
  1. .pdata で関数範囲を得て、各関数を capstone で線形逆アセンブルする
  2. 直接 call (e8) と関数範囲外への直接 jmp (tail call) を辺にして BFS で到達集合を作る
  3. IAT 経由の API 呼出し (`call [rip+IAT]` と `jmp [rip+IAT]` thunk 経由) を thread_api.py の分類で数える
限界 (下限であることの根拠。REPORT §4-2 に同じ内容):
  - 間接 call (`call reg` / `call [reg+disp]` / vtable 呼出し) と switch の間接 jmp は辺にしない。到達集合は下限。
  - 間接 call の数は到達集合ごとに出す (未追跡の辺の規模)。分母 (到達集合内の call/jmp 箇所) も出す。
判定 (gate): 入口 VA が .pdata の関数先頭であること、到達集合に既知の辺 (winmm!timeGetTime。REPORT の
  bufferSwitchTimeInfo の systemTime 経路) があること。gate は到達集合の正しさを検査しない (入口の位置のみ)。
  --negctl は入口を関数内部 (先頭+1) に差し替え、gate が FAIL することを確認する (exit 0 = 期待どおり FAIL)。
使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 mixer_reach.py [--json out.json] [--negctl]
依存: pefile, capstone"""
import sys, os, re, struct, json, bisect, collections
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


def func_of(rva):
    k = bisect.bisect_right(fstarts, rva) - 1
    return funcs[k] if k >= 0 and funcs[k][0] <= rva < funcs[k][1] else None


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


def reach(entry_rva):
    seen = {}
    q = [entry_rva]
    imps = collections.Counter()
    sites = collections.defaultdict(list)     # (dll,name) -> [call site VA]
    ind = collections.Counter()               # 間接 call/jmp の形ごとの箇所数 (未追跡の辺)
    unknown = 0
    insns = 0
    direct = 0                                # 関数宛て直接 call/jmp (tail call を含む。辺になったもの)
    while q:
        r = q.pop()
        f = func_of(r)
        if f is None:
            unknown += 1
            continue
        if f[0] in seen:
            continue
        seen[f[0]] = f
        for ins in md.disasm(bytes(img[f[0]:f[1]]), base + f[0]):
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
            elif op.type == X86_MEM and op.mem.base == RIP and op.mem.index == 0:
                tgt = ins.address + ins.size + op.mem.disp - base
                if tgt in iat:
                    imps[iat[tgt]] += 1
                    sites[iat[tgt]].append(ins.address)
                else:
                    ind[f"{ins.mnemonic} [rip-data]"] += 1
            elif op.type == X86_REG:
                ind[f"{ins.mnemonic} reg"] += 1
            else:
                ind[f"{ins.mnemonic} [mem]"] += 1
    return seen, imps, sites, ind, unknown, insns, direct


entry_rva = ENTRY_VA - base + (1 if NEG else 0)
is_start = any(s == entry_rva for s in fstarts)
seen, imps, sites, ind, unknown, insns, direct = reach(entry_rva)
fl = list(seen.values())
known_hit = imps.get(KNOWN_EDGE, 0)
api_calls = sum(imps.values())
indirect_calls = sum(ind.values())
edge_total = direct + api_calls + indirect_calls          # 分母: 到達集合内の call/jmp 箇所 (関数内の無条件 jmp は除く)
indirect_pct = 100.0 * indirect_calls / edge_total if edge_total else 0.0

summary = {}
for cls in CLASSES:
    hit_funcs = set()
    n_sites = 0
    for key, ss in sites.items():
        if API2CLASS.get(key[1]) != cls:
            continue
        n_sites += len(ss)
        hit_funcs |= {func_of(s - base)[0] for s in ss if func_of(s - base)}
    summary[cls] = {"call_sites": n_sites, "distinct_functions": len(hit_funcs)}

gate = [
    {"name": "entry_is_pdata_start", "ok": is_start},
    {"name": "known_edge_timeGetTime_reached", "ok": known_hit >= 1, "got": known_hit},
]
ok = all(g["ok"] for g in gate)

print(f"PE: {shown}  (ImageBase {base:#x}, functions(.pdata)={len(funcs)}, imports={len(iat)}, thunks={len(thunks)})")
print(f"entry: {ENTRY_VA if not NEG else ENTRY_VA + 1:#x} (VA)  pdata 関数先頭: {is_start}")
print(f"到達集合 (直接 call + tail jmp の BFS): 関数 {len(fl)} / 命令 {insns} / 範囲外の目標 {unknown}")
print("到達集合内の call/jmp 箇所 (分母。関数内の無条件 jmp は除く):")
print(f"  {'関数宛て直接':24s} {direct:6d}")
print(f"  {'API 呼出し':24s} {api_calls:6d}")
print(f"  {'間接 (下表)':24s} {indirect_calls:6d}  ({indirect_pct:.1f}% of {edge_total})")
print(f"  {'合計':24s} {edge_total:6d}")
print("未追跡の間接 call/jmp (到達集合内の箇所数。命令形の内訳。vtable 呼出しとの対応は推定):")
for k, v in ind.most_common():
    print(f"  {k:24s} {v:6d}")
print(f"  {'合計':24s} {indirect_calls:6d}")
print("\n## 到達集合内の API 呼出し (分類別: call 箇所 / 呼出し関数の distinct 数)")
for cls, s in summary.items():
    print(f"  {cls:17s} call_sites={s['call_sites']:5d} distinct_functions={s['distinct_functions']:5d}")
print("\n## 上位 API (到達集合内の call 箇所数)")
for k, v in imps.most_common(25):
    print(f"  {k[0]:16s} {k[1]:30s} {v:5d}")
print("\n## gate")
for g in gate:
    print(f"  {'PASS' if g['ok'] else 'FAIL'} {g['name']}" + (f" got={g['got']}" if "got" in g else ""))
if "--json" in sys.argv:
    with open(sys.argv[sys.argv.index("--json") + 1], "w") as fh:
        json.dump({"pe": shown, "negctl": NEG, "entry_va": hex(ENTRY_VA), "reachable_functions": len(fl),
                   "instructions": insns, "unknown_targets": unknown, "indirect": dict(ind), "summary": summary,
                   "edges": {"direct": direct, "api": api_calls, "indirect": indirect_calls, "total": edge_total,
                             "indirect_pct": round(indirect_pct, 1)},
                   "apis": [{"dll": k[0], "api": k[1], "class": API2CLASS.get(k[1]), "call_sites": v} for k, v in imps.most_common()],
                   "gate": gate, "ok": ok}, fh, indent=1)
if NEG:
    print(f"\nnegctl: gate {'FAIL (期待どおり)' if not ok else 'PASS (= 検出能力なし)'}")
    sys.exit(0 if not ok else 1)
sys.exit(0 if ok else 1)
