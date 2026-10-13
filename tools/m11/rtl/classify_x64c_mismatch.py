#!/usr/bin/env python3
"""RTL 帯 (0x401000 <= VA < 0x456e98) の x64c liftdiff 不一致を主因タグで集計する (#410 受入 2)。

usage: classify_x64c_mismatch.py <batch.jsonl> <rtl_verdicts.tsv>
入力:
  batch.jsonl       liftdiff batch の jsonl (flelift)。例: work-liftdiff の flelift/batch_closure_hybrid.jsonl
  rtl_verdicts.tsv  rtl_compare.py の出力 (tools/m11/rtl/results/rtl_verdicts.tsv)。列: va, unit, m11, x64c
主因 = tags の先頭 (liftdiff が出力した順)。tags 無しは (none)。
出力:
  1. batch 側の帯内件数と主因・全タグ表
  2. rtl_verdicts.tsv の x64c 列の帯内件数 (REPORT §2 の 535/125/512 の出所)
  3. TSV の x64c 列 と batch 判定のクロス表
  4. 一致→不一致の退行候補: 定義 = rtl_verdicts.tsv で m11=match かつ x64c=mismatch (rtl_compare.py の遷移と同じ)。
     status 列は batch 側の判定 (TSV 側は全件 mismatch)
"""
import json
import sys
from collections import Counter

RTL_LO, RTL_HI = 0x401000, 0x456E98


def main(path, tsv_path):
    rows = [json.loads(line) for line in open(path)]
    band = [r for r in rows if RTL_LO <= int(r["function"]["va"], 16) < RTL_HI]
    by_va = {r["function"]["va"]: r for r in rows}
    mm = [r for r in band if r["verdict"] == "mismatch"]
    print(f"band={len(band)} verdict={dict(Counter(r['verdict'] for r in band))}")
    print(f"mismatch={len(mm)}")

    first = Counter()
    anytag = Counter()
    for r in mm:
        tags = [t["tag"] for t in r.get("tags", [])]
        first[tags[0] if tags else "(none)"] += 1
        anytag.update(set(tags))
    print("\n## 主因 (先頭タグ)")
    for k, v in first.most_common():
        print(f"{k}\t{v}")
    print("\n## 全タグ出現 (1 関数に複数タグあり)")
    for k, v in anytag.most_common():
        print(f"{k}\t{v}")

    tsv = {}
    for line in open(tsv_path):
        if line.startswith("#") or not line.strip():
            continue
        p = line.rstrip("\n").split("\t")
        if RTL_LO <= int(p[0], 16) < RTL_HI:
            tsv[p[0]] = (p[2], p[3])
    print(f"\n## rtl_verdicts.tsv の x64c 列 (帯内 {len(tsv)} 件)")
    print(f"match/mismatch/unexec = {'/'.join(str(Counter(v[1] for v in tsv.values())[k]) for k in ('match', 'mismatch', 'unexec'))}")
    cross = Counter((tsv[va][1], by_va[va]["verdict"] if va in by_va else "(not in jsonl)") for va in tsv)
    print("\n## TSV x64c 列 (行) × batch 判定 (列)")
    print("TSV\\batch\tmatch\tmismatch\tunexec")
    for t in ("match", "mismatch", "unexec"):
        print(f"{t}\t" + "\t".join(str(cross[(t, b)]) for b in ("match", "mismatch", "unexec")))

    regress = [va for va in tsv if tsv[va] == ("match", "mismatch")]
    print(f"\n## 一致→不一致の退行候補 ({len(regress)} 件; 定義: rtl_verdicts.tsv で m11=match かつ x64c=mismatch。status は batch 側)")
    print("va\tbatch_verdict\tbatch_tags")
    for va in sorted(regress):
        r = by_va.get(va)
        if r is None:
            print(f"{va}\t(not in jsonl)\t-")
            continue
        tags = [t["tag"] for t in r.get("tags", [])]
        print(f"{va}\t{r['verdict']}\t{','.join(tags) or '(none)'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
