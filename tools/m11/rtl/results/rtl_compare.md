自動生成: python3 tools/m11/rtl/rtl_compare.py <rtl_units.json> <m11_batch.jsonl> <flelift_batch.jsonl> --md <out.md> --tsv <out.tsv> (引数の実値は tools/m11/rtl/REPORT.md §6)
関数数 1172 (両 route 採点あり)

| 帯 (VMT 先頭基準の近似。unit 境界ではない) | 関数 | m11 match/mismatch/unexec | x64c match/mismatch/unexec |
|---|--:|---|---|
| System 以降 [0x401000〜] | 473 | 152/216/105 | 253/63/157 |
| System.Types 以降 [0x41fd40〜] | 360 | 248/110/2 | 42/14/304 |
| System.SysUtils 以降 [0x42db78〜] | 339 | 86/211/42 | 240/48/51 |
| **計** | 1172 | **486/537/149** | **535/125/512** |

遷移 (m11 → x64c): match→match 207, match→mismatch 7, match→unexec 272, mismatch→match 312, mismatch→mismatch 117, mismatch→unexec 108, unexec→match 16, unexec→mismatch 1, unexec→unexec 132

| m11_ov.c 手転記 | VA | m11 | x64c |
|---|---|---|---|
| InitUnits | 0x4120c0 | match | unexec |
| _InitLib | 0x412160 | unexec | unexec |
| 再配置表適用 | 0x412510 | unexec | unexec |
| Halt 復元 | 0x412770 | unexec | unexec |
| _UStrAsg | 0x4133f0 | mismatch | match |
| _StartLib | 0x41d8f0 | unexec | unexec |
| SysUtils LCMapString 変換 | 0x450560 | mismatch | mismatch |
