#!/usr/bin/env python3
# SR-85 #5034 上限の反復: root 集合の閉包 -> 閉包内の間接 call の候補化 -> 候補を root に加える。新規候補が 0 になるまで回す。
import os, re, subprocess, sys

G = os.environ["GHIDRA_HOME"]
GUI = "../gui"
IB = 0x180000000
roots = {}
for l in open("xferonoff_upper_fns.tsv"):
    if l.startswith("0x"):
        roots[int(l.split("\t")[0], 16)] = 1  # RVA
it = 0
while True:
    it += 1
    tsv = f"iter{it}_fns.tsv"
    with open(tsv, "w") as f:
        for rva in sorted(roots):
            f.write(f"0x{rva:x}\titer\t0\t0\n")
    env = dict(os.environ, FN_ADDRS_TSV=os.path.abspath(tsv), OUT_DIR=os.path.abspath(f"closure_iter{it}"))
    base = [f"{G}/support/analyzeHeadless", "ghproj", "xo", "-process", "Serum2_win64.vst3", "-noanalysis", "-readOnly", "-scriptPath", GUI]
    subprocess.run(base + ["-postScript", "ghidra_xferonoff_closure.java"], env=env, stdout=open(f"closure_iter{it}.log", "w"), stderr=subprocess.STDOUT, check=True, timeout=300)
    subprocess.run(base + ["-postScript", "ghidra_xferonoff_indirect.java"], env=env, stdout=open(f"indirect_iter{it}.log", "w"), stderr=subprocess.STDOUT, check=True, timeout=300)
    summ = [l for l in open(f"closure_iter{it}.log") if "SUMMARY" in l]
    subprocess.run([sys.executable, f"{GUI}/indirect_sr85_own_vt.py", "Serum2_win64.vst3", f"indirect_iter{it}.log", "aa9750,aa96b0,aa9770"], stdout=open(f"own_vt_iter{it}.tsv", "w"), stderr=subprocess.DEVNULL, check=True, timeout=120)
    cands = set()
    unres = 0
    for r in [l.rstrip("\n").split("\t") for l in open(f"own_vt_iter{it}.tsv")][1:]:
        if len(r) < 4:
            continue
        m = re.search(r"((?:0x[0-9a-fA-F]+)(?:,0x[0-9a-fA-F]+)*)\s*$", r[3])
        if m:
            cands.update(int(c, 16) - IB for c in m.group(1).split(","))
        else:
            unres += 1
    new = sorted(c for c in cands if c not in roots)
    print(f"iter={it} roots={len(roots)} {summ[-1].split('SUMMARY')[1].strip() if summ else 'NO SUMMARY'} cand_fns={len(cands)} new_cand={len(new)} unresolved_rows={unres}", flush=True)
    if not new or it >= 6:
        break
    for c in new:
        roots[c] = 1
