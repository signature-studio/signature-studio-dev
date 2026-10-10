#!/usr/bin/env python3
"""IPP 実測インベントリの集約 -> data/ipp_inventory.json + data/ipp_inventory.md
 入力: work/raw/{win_pe_catalog,ipp_win_usage,ipp_mac_usage,ipp_static_mac,mac_macho_catalog}.json, work/ipp_validate_flengine.json"""
import sys, os, json, re, collections
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import pefile

def load(n): return json.load(open(f"{RAW}/{n}.json"))
wc = {r["file"]: r for r in load("win_pe_catalog")}
wu = load("ipp_win_usage"); mu = load("ipp_mac_usage"); sm = load("ipp_static_mac")

# ---- dsp_ippv2 exports ----
win_ex = wc["block24356_PE.bin"]["exports"]; win32_ex = wc["block24355_PE.bin"]["exports"]
mac_slice = fat_slice(f"{MAC_SHARED}/dsp_ippv2_x64.dylib")
mac_ex = [l.split()[-1].lstrip("_") for l in run(["llvm-nm", "-gU", mac_slice]).stdout.splitlines() if l.strip()]
def pref(n): return "ipps" if n.startswith("ipps") else "ippi" if n.startswith("ippi") else "agg" if n.startswith("Agg") else "ippcore"
exp_sum = {"win_x64": {"total": len(win_ex), **collections.Counter(map(pref, win_ex))},
           "win_x86": {"total": len(win32_ex)}, "mac_x86_64": {"total": len(mac_ex), **collections.Counter(map(pref, mac_ex))},
           "win_only": sorted(set(win_ex) - set(mac_ex)), "mac_only": sorted(set(mac_ex) - set(win_ex))}

# ---- 機能族 ----
def family(n):
    b = n
    if re.match(r"ipp(Malloc|Free|Get|Set)", b) and not b.startswith(("ippsSet", "ippiSet")): return "core"
    if n.startswith("ippi"): return "image"
    if re.search(r"FFT|FIR|IIR|Conv_|CrossCorr|AutoCorr|FilterMedian|WinKaiser|MulPack|Tone_|Rand(Uniform|Gauss)|Conj|Phase|Magnitude|PowerSpectr", b): return "dsp_filter_fft"
    if re.search(r"_A(11|21|24|26|50|53)\b|Exp|Ln_|Log10|Pow|Sin|Cos|Atan|Tanh|Cbrt|Sqrt|Inv_|Round|Trunc|Expm1", b): return "transcendental"
    if re.search(r"^ipps(Copy|Move|Zero|Set|Compare|Equal)_", b): return "memory"
    if re.search(r"Convert_|SwapBytes|Interleave|Deinterleave|CplxToReal|RealToCplx|Real_|Imag_", b): return "convert_shuffle"
    return "arith_reduce"
DIFF = {"core": "trivial", "memory": "trivial", "convert_shuffle": "trivial (丸め/飽和 Sfs の仕様一致が要点)", "arith_reduce": "easy (SIMD-friendly C)",
        "transcendental": "moderate (A11/A21/A24/A50/A53 精度段; 許容誤差一致, bit-exact は不可能)", "dsp_filter_fft": "moderate-hard (FFT/FIR/IIR/Rand 系はアルゴリズム一致が必要)", "image": "moderate-hard (Resize/Warp/Filter は丸め仕様一致が必要)"}

def pe_label(f):
    r = wc.get(f, {}); lab = r.get("dllname") or ""
    pdb = r.get("pdb") or ""
    if pdb: lab = (lab + " | " if lab else "") + pdb.split("\\")[-1]
    if not lab:
        try:
            pe = pefile.PE(f"{WIN_EXTRACTED}/{f}", fast_load=True); pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
            for fi in getattr(pe, "FileInfo", []) or []:
                for e in fi:
                    for st in getattr(e, "StringTable", []):
                        d = {k.decode(): v.decode(errors="replace") for k, v in st.entries.items()}
                        lab = d.get("OriginalFilename") or d.get("FileDescription") or lab
        except Exception: pass
    return lab or f.replace("_PE.bin", "")

# ---- win 使用 ----
w_used = collections.defaultdict(lambda: {"pes": [], "sites": 0})
for f, v in wu.items():
    for e in v["table"]:
        n = e["call"] + e["mov"] + e["other"]
        if n: w_used[e["name"]]["pes"].append(f); w_used[e["name"]]["sites"] += n
win_pes_with_refs = sorted({f for u in w_used.values() for f in u["pes"]})
win_loader = sorted({e["name"] for v in wu.values() for e in v["table"]})
win_inv = {name: {"family": family(name), "n_pe": len(u["pes"]), "sites": u["sites"], "pes": [pe_label(p) for p in sorted(u["pes"])[:4]]} for name, u in sorted(w_used.items(), key=lambda x: -len(x[1]["pes"]))}
# FLEngine win: wrapper 関数と呼出元数 (capstone 全逆アセンブルの独立検証)
fl = json.load(open(f"{WORK}/ipp_validate_flengine.json"))
fl_wrap = [r for r in fl["refs"] if r["mn"] == "call"]
# ---- mac 使用 ----
m_used = collections.defaultdict(lambda: {"files": [], "sites": 0})
for f, v in mu.items():
    for e in v["table"]:
        n = e["call"] + e["mov"] + e["other"]
        if n: m_used[e["name"]]["files"].append(f); m_used[e["name"]]["sites"] += n
mac_flengine = {e["name"]: e["call"] + e["mov"] + e["other"] for e in mu["Contents/Libs/FLEngine_x64.dylib"]["table"] if e["call"] + e["mov"] + e["other"]}
mac_inv = {name: {"family": family(name), "n_files": len(u["files"]), "sites": u["sites"]} for name, u in sorted(m_used.items(), key=lambda x: -len(x[1]["files"]))}
mac_files_by_n = {f: sum(1 for e in v["table"] if e["call"] + e["mov"] + e["other"]) for f, v in mu.items()}
fam_count = lambda inv: dict(collections.Counter(v["family"] for v in inv.values()))

# ---- 静的 IPP ----
static_win = []
for f, r in wc.items():
    try:
        pe = pefile.PE(f"{WIN_EXTRACTED}/{f}", fast_load=True)
        for s in pe.sections:
            if s.Name.rstrip(b"\0") == b"IPPCODE" and r.get("dllname") not in ("dsp_ippv2.dll", "dsp_ippv2_x64.dll"):
                static_win.append({"pe": pe_label(f), "ippcode_bytes": s.SizeOfRawData})
    except Exception: pass
inv = {
  "ipp_version": "Intel oneAPI IPP 2021.7 (ippCore string '2021.7 (r0xa954907f) Nov 4 2022' in dsp_ippv2_x64.dylib)",
  "exports": exp_sum,
  "loader_table": {"names": len(win_loader), "win_pes_with_table": sum(1 for v in wu.values() if v["entries"]), "mac_files_with_table": sum(1 for v in mu.values() if v["entries"]),
                   "note": "全 Delphi/FPC バイナリが同一 unit を静的リンクし 423 エントリ (重複除き 420 名) を LoadLibrary+GetProcAddress 相当で解決する (win: ローダ関数 FLEngine 0x653f40)"},
  "win": {"distinct_used": len(win_inv), "pes_with_direct_refs": len(win_pes_with_refs), "families": fam_count(win_inv), "functions": win_inv,
          "flengine": {"wrapper_functions": [{"name": r["name"], "wrapper_va": r["func"], "callers": r["callers_of_func"]} for r in fl_wrap]}},
  "mac": {"distinct_used": len(mac_inv), "files_with_direct_refs": sum(1 for v in mac_files_by_n.values() if v), "families": fam_count(mac_inv),
          "flengine_distinct": len(mac_flengine), "flengine_call_sites": sum(mac_flengine.values()), "functions": mac_inv},
  "static_ipp": {"mac_symbols": {k.split("/")[-1] if "oggio" in k else "Multiband Delay engine.vst": {"public": v["public"], "n_own": v["n_own"], "cpu_prefixes": v["cpus"]} for k, v in sm.items()},
                 "win_ippcode_sections": sorted(static_win, key=lambda x: -x["ippcode_bytes"])},
  "difficulty": DIFF,
}
json.dump(inv, open(f"{DATA}/ipp_inventory.json", "w"), indent=1, ensure_ascii=False)

# ---- markdown ----
md = []
md.append(f"dsp_ippv2 export: win x64 {len(win_ex)} (ipps {exp_sum['win_x64']['ipps']} / ippi {exp_sum['win_x64']['ippi']} / core+Agg {exp_sum['win_x64'].get('ippcore',0)+exp_sum['win_x64'].get('agg',0)}), mac {len(mac_ex)}")
md.append(f"win 使用 (直接参照あり): distinct {len(win_inv)} / PE {len(win_pes_with_refs)}  族別 {fam_count(win_inv)}")
md.append(f"mac 使用 (直接参照あり): distinct {len(mac_inv)} / Mach-O {inv['mac']['files_with_direct_refs']}  族別 {fam_count(mac_inv)}; FLEngine mac distinct {len(mac_flengine)} (call site {sum(mac_flengine.values())})")
md.append("win 使用関数: " + ", ".join(f"{n}({v['n_pe']})" for n, v in win_inv.items()))
open(f"{DATA}/ipp_inventory.md", "w").write("\n".join(md) + "\n")
print("\n".join(md))
print("win flengine wrappers:", [(w["name"], w["callers"]) for w in inv["win"]["flengine"]["wrapper_functions"]])
print("static win:", [(s["pe"], s["ippcode_bytes"]) for s in inv["static_ipp"]["win_ippcode_sections"]])
print("mac-only exports", len(exp_sum["mac_only"]), "win-only", len(exp_sum["win_only"]))
