#!/usr/bin/env python3
"""RTL 帯 (0x401000 <= VA < 0x456e98) の x64c liftdiff 不一致を主因タグで集計する (#410 受入 2)。

入力: liftdiff batch の jsonl (flelift)。例: work-liftdiff の flelift/batch_closure_hybrid.jsonl
主因 = tags の先頭 (liftdiff が出力した順)。tags 無しは (none)。
出力: 件数表 (主因 / 全タグ出現 / 一致→不一致の退行の内訳)。
"""
import json
import sys
from collections import Counter

RTL_LO, RTL_HI = 0x401000, 0x456E98


def main(path, regress_path=None):
    rows = [json.loads(line) for line in open(path)]
    band = [r for r in rows if RTL_LO <= int(r["function"]["va"], 16) < RTL_HI]
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

    if regress_path:
        by_va = {r["function"]["va"]: r for r in rows}
        print("\n## 一致→不一致の退行 (TSV 由来 VA 一覧)")
        for line in open(regress_path):
            va = line.strip()
            if not va:
                continue
            r = by_va.get(va)
            if r is None:
                print(f"{va}\t(not in jsonl)")
                continue
            tags = [t["tag"] for t in r.get("tags", [])]
            print(f"{va}\t{r['verdict']}\t{','.join(tags) or '(none)'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
