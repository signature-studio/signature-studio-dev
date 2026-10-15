#!/usr/bin/env python3
"""ID 一致 37 組の process 候補を REPORT_APPENDIX_2739 §1〜§2 の基準で振り分ける (#2739)。
   usage: ks_candidate_triage.py <ident.json> [out.json]
 入力: ks_identity.py の出力 (ident.json)。出力: 振り分け表 (Markdown) を stdout、out.json があれば JSON。
 判定は決定的 (同じ入力で byte 一致)。ハーネスの有無は repo 内のファイル存在だけで見る。
"""
import json, os, sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SNAPINS_JSON = os.path.join(REPO, "tools/targets/kilohearts/snapins/snapins.json")

# C3 の SC 側: 実機機械語で process を実行するハーネス (クラス名 -> repo 相対パス)
SC_HARNESS = {
    "Compressor": "tools/targets/freshair/lift2/native/native_comp.c",
    "Filter": "tools/targets/freshair/lift2/native/native_filter.c",
    "Gain": "tools/targets/freshair/lift/native_gain.c",
}
# C3 の KH 側: snapins.json に登録された key (クラス名 -> key。既定は小文字化)
KH_KEY_OVERRIDE = {"VocalFilter": "formant"}
STUB_MIN_BYTES = 64  # C2


def cls_name(full):
    # '.?AVCompressorDsp@compressor@@' -> 'Compressor'
    return full[4:].split("@")[0][: -len("Dsp")]


def classify(name, pair, kh_keys):
    if min(pair["kh_bytes"], pair["sc_bytes"]) < STUB_MIN_BYTES:
        return "stub", "-"
    sc = name in SC_HARNESS and os.path.exists(os.path.join(REPO, SC_HARNESS[name]))
    kh = KH_KEY_OVERRIDE.get(name, name.lower()) in kh_keys
    if sc and kh:
        return "両側", "-"
    if sc:
        return "SC のみ", "KH (snapins.json に key 無し)"
    if kh:
        return "KH のみ", "SC (実機機械語ハーネス無し)"
    return "なし", "SC と KH の両方"


def main():
    ident = json.load(open(sys.argv[1]))
    kh_keys = set(json.load(open(SNAPINS_JSON)).keys())
    rows = []
    for full in sorted(k for k in ident if k.startswith(".?AV")):
        name = cls_name(full)
        pair = ident[full]["process_pair"]
        cat, missing = classify(name, pair, kh_keys)
        rows.append({
            "class": name, "kh_va": pair["kh_va"], "sc_va": pair["sc_va"],
            "kh_bytes": pair["kh_bytes"], "sc_bytes": pair["sc_bytes"],
            "ratio_M": pair["ratio_M"], "category": cat, "missing": missing,
        })
    counts = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    print("| クラス | KH VA | SC VA | KH B | SC B | ratio_M | 区分 | 欠けている側 |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %s | %d | %d | %.4f | %s | %s |" % (
            r["class"], r["kh_va"], r["sc_va"], r["kh_bytes"], r["sc_bytes"],
            r["ratio_M"], r["category"], r["missing"]))
    print("")
    print("対象 %d: %s" % (len(rows), " / ".join("%s %d" % (k, counts[k]) for k in sorted(counts))))
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w") as f:
            json.dump({"n": len(rows), "counts": counts, "rows": rows}, f, ensure_ascii=False, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
