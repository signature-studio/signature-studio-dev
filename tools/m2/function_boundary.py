#!/usr/bin/env python3
# M2-2: 関数境界合意検証 (Ghidra headless × RetDec × 静的 Table (ground truth))。
#
#   win64 FLEEngine_x64.dll : ground = PE .pdata (RUNTIME_FUNCTION, pescan.py)
#   mac FLEEngine slice     : ground = Mach-O LC_FUNCTION_STARTS (llvm-objdump)
#
# 入力:
#   --ghidra-csv   : ghidra_scripts/DumpFunctions.java の出力 (name,entry,size)
#   --retdec-json  : retdec-decompiler が残す <out>.config.json の functions 部分
#                    (startAddr / endAddr を含む)
#   --ground       : ground truth ファイル。win = pescan json, mac = 行ごとに
#                    16進アドレスの function-starts テキスト
#   --va-base      : 入力の VA→RVA キャスト値 (win DLL: 0x400000, mac slice: 0)
#   --out-json     : 出力
#
# 出す指標:
#   counts (3者) と 件数差 (±5% 条件),
#   entry 集合の一致率 (Ghidra∩RetDec / Ghidra, / RetDec, Jaccard),
#   それぞれ ground truth との同率,
#   matched pair (entry 一致) における境界の size 合致率 (取捨差 ±16B 内を同値とする)

import argparse
import csv
import json
import re
import sys


def die(msg):
    print(f"[boundary] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def json_compilable(path):
    try:
        json.load(open(path))
        return True
    except Exception:
        return False


def load_ghidra(path):
    out = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            e = (row.get("entry") or "").strip()
            if e.startswith("ram:"):
                e = e[4:]
            try:
                ent = int(e, 16)
            except (ValueError, KeyError):
                continue
            out[ent] = int(row.get("size", 0) or 0)
    return out


def load_retdec(path):
    """retdec config.json → {start_rva: end_rva}"""
    data = json.load(open(path))
    fns = data.get("functions", [])
    out = {}
    for f in fns:
        s = f.get("startAddr")
        e = f.get("endAddr")
        if s is None or e is None:
            continue
        try:
            s = int(s, 16)
            e = int(e, 16)
        except ValueError:
            continue
        if e >= s:
            out[s] = e
    return out


def load_retdec_dsm(path, shift):
    """retdec dsm の '; function: ... at 0x.. -- 0x..' ラベルから境界集合を取る。

    shift: VA→RVA 変換 (win DLL は 0x400000 減算, mac slice は 0)。
    """
    if shift is None:
        shift = -0x400000
    pat = re.compile(r"; function: (\S+) at (0x[0-9a-f]+) -- (0x[0-9a-f]+)")
    out = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            m = pat.match(line)
            if m:
                s = int(m.group(2), 16) + shift
                e = int(m.group(3), 16) + shift
                if s in out:
                    continue
                out[s] = e
    return out


def load_ground(path, kind):
    out = {}
    if kind == "win":
        data = json.load(open(path))
        for e in data.get("pdata", []):
            out[e["begin"]] = e["end"]
    else:
        with open(path) as fh:
            for line in fh:
                t = line.strip()
                if t.startswith("0x") or t.isdigit() or (t and all(
                        c in "0123456789abcdefABCDEF" for c in t) and len(t) >= 6):
                    try:
                        out[int(t, 16)] = None
                    except ValueError:
                        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--ghidra-csv", required=True)
    ap.add_argument("--retdec-json", default=None)
    ap.add_argument("--retdec-dsm", default=None,
                    help="retdec .dsm の '; function: <name> at <start> -- <end>' 行から"
                         "関数境界集合を取る (--retdec-json 代替。FLEEngine 規模では"
                         "後段の全 phase 完了前に dsm が確定するためこちらが実用)")
    ap.add_argument("--dsm-shift", type=lambda s: int(s, 0), default=None,
                    help="dsm アドレスの RVA 変換差 (既定: -0x400000=win VA→RVA, mac=0)")
    ap.add_argument("--ground", required=True)
    ap.add_argument("--ground-kind", choices=["win", "mac"], required=True)
    ap.add_argument("--va-base", type=lambda s: int(s, 0), default=0x400000)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args()

    gh = {e - args.va_base: s for e, s in load_ghidra(args.ghidra_csv).items()}
    rd = {}
    if args.retdec_json and json_compilable(args.retdec_json):
        rd = {s - args.va_base: e - args.va_base for s, e in
              load_retdec(args.retdec_json).items()}
    elif args.retdec_dsm:
        rd = load_retdec_dsm(args.retdec_dsm, args.dsm_shift)
    gr = load_ground(args.ground, args.ground_kind)

    gs = set(gh)
    rs = set(rd)
    grs = set(gr)

    def rate(a, b):
        return (len(a & b) / len(a) if a else 0.0, len(a & b) / len(b) if b else 0.0,
                len(a & b) / len(a | b) if a | b else 0.0)

    gh_rd = rate(gs, rs)
    gh_gr = rate(gs, grs)
    rd_gr = rate(rs, grs)

    # borderline size agreement for matched pairs (entry 一致 & 両方 end を持つ)
    size_tot = size_ok = 0
    for e in gs & rs:
        if e in rd and e in gh:
            size_tot += 1
            if abs(rd[e] - e - gh[e]) <= 16:
                size_ok += 1

    diffs = {
        "ghidra_vs_retdec_count_delta": (abs(len(gs) - len(rs)) / max(len(gs), 1)
                                         ) if rs else None,
        "ghidra_vs_ground_count_delta": abs(len(gs) - len(grs)) / max(len(gs), 1),
        "retdec_vs_ground_count_delta": (abs(len(rs) - len(grs)) / max(len(rs), 1)
                                         ) if rs else None,
    }

    out = {
        "label": args.label,
        "counts": {
            "ghidra": len(gs), "retdec": len(rs), "ground": len(grs),
        },
        "count_deltas": diffs,
        "within_5pct": all(v is not None and v <= 0.05 for v in diffs.values()),
        "entry_agreement": {
            "ghidra_retdec": {"ghidra_coverage": gh_rd[0], "retdec_coverage": gh_rd[1],
                              "jaccard": gh_rd[2]},
            "ghidra_ground": {"ghidra_coverage": gh_gr[0], "ground_coverage": gh_gr[1],
                              "jaccard": gh_gr[2]},
            "retdec_ground": {"retdec_coverage": rd_gr[0], "ground_coverage": rd_gr[1],
                              "jaccard": rd_gr[2]},
        },
        "matched_pairs": size_tot,
        "matched_size_agreement": (size_ok / size_tot) if size_tot else None,
    }
    with open(args.out_json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"[boundary] {args.label}: ghidra={len(gs)} retdec={len(rs)} "
          f"ground={len(grs)}")
    print("[boundary] ±5% 条件: " +
          ", ".join(f"{k}={v:.1%}" if v is not None else f"{k}=n/a"
                    for k, v in diffs.items()))
    if rs:
        print(f"[boundary] jaccard ghidra-retdec={gh_rd[2]:.1%} "
              f"ghidra-ground={gh_gr[2]:.1%} retdec-ground={rd_gr[2]:.1%}")
    else:
        print(f"[boundary] jaccard ghidra-ground={gh_gr[2]:.1%} (retdec n/a)")
    if size_tot:
        print(f"[boundary] matched size agreement: {size_ok}/{size_tot} "
              f"({out['matched_size_agreement'] * 100:.1f}%)")


if __name__ == "__main__":
    main()
