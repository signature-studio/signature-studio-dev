#!/usr/bin/env python3
"""SR-85 #5934: 閉包内のレジスタ経由 間接 call (indirect_sr85_all_vt.py の標準出力) と、receiver_this_trace.py --all-disps の TSV を突き合わせる。

入力: all_vt.out (indirect_sr85_all_vt.py の標準出力)・recv_all.tsv (receiver_this_trace.py --all-disps --tsv の出力)
出力: 標準出力に 1 行 1 サイト の TSV (site / in_func / operand / recv_cat_strict / recv_cat_loose / 突き合わせ可否)。
      recv_all.tsv に無いサイトは recv 列を "-" とし、件数を最後に出す。
usage: indirect_sr85_join_recv.py <all_vt.out> <recv_all.tsv>
"""
import sys

all_vt_path, recv_path = sys.argv[1], sys.argv[2]

recv = {}
with open(recv_path) as f:
    next(f)
    for line in f:
        cols = line.rstrip("\n").split("\t")
        call_va = cols[0].removeprefix("0x")
        recv.setdefault(call_va, cols)

sites = []
with open(all_vt_path) as f:
    for line in f:
        cols = line.rstrip("\n").split("\t")
        if len(cols) >= 3 and cols[0] != "in_func" and cols[2].startswith("[R"):
            sites.append((cols[0], cols[1], cols[2]))

seen = set()
matched = 0
print("site\tin_func\toperand\trecv_strict\trecv_loose\tmatched")
for in_func, site, operand in sites:
    if site in seen:
        continue
    seen.add(site)
    r = recv.get(site)
    if r:
        matched += 1
        print(f"{site}\t{in_func}\t{operand}\t{r[4]}\t{r[5]}\tyes")
    else:
        print(f"{site}\t{in_func}\t{operand}\t-\t-\tno")
print(f"# sites={len(seen)} matched={matched} unmatched={len(seen) - matched}", file=sys.stderr)
