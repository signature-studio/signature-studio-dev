# REPORT 付録 — #5934 (SR-85): vptr:THIS の受信を所属関数の class の vtable に絞る

> **正本**: `tools/targets/serum2/gui/REPORT_APPENDIX_5005.md` §5.8〜§5.11 (#5934 の前段)。本付録はその続き (#5934 run 6)。

- 親: #5934 (SR-85 の受入) / 前段: REPORT_APPENDIX_5005.md §5.10・§5.11 (突き合わせ 46/46 一致・測定 commit `41a9499ba`)。
- 入力: `Serum2_win64.vst3` (sha256 `501e7bb3…4e5283`・19,236,864 B)。素材 `plugins-serum2` の installer から取り出し。
- 測定 commit (コード): 本付録を含む commit の直前の HEAD (`bcd2435ac`・origin/main)。新規のコードは `gui/indirect_sr85_this_slot.py` のみ。

### 6.1 手順

1. Ghidra 12.1.4 (公式 release・sha256 `ddac49f9…d4db` を検査済み) で `analyzeHeadless ... -import` (`ghidra_fn_size.java`)。import **18 分 54 秒** (wall clock 15:33:23→15:52:17・rc 0)。
2. 閉包 `-process` (root = `xferonoff_upper2_fns.tsv`・sha256 `fcafc8df…82f9`) **7 秒** (wall clock 15:52:20→15:52:27・rc 0)。
3. 間接 call 列挙 `-process ghidra_xferonoff_indirect.java` (`FN_ADDRS_TSV`・`OUT_DIR` を渡す): **SITE 107 行** (§5.6 と一致)。
4. `indirect_sr85_all_vt.py` (全 vtable 3,633・構築 3,622) → `all_vt.out` (閉包内のレジスタ経由 46 サイト)。
5. `receiver_this_trace.py --all-disps --tsv recv_all.tsv` (26,793 行)。
6. `indirect_sr85_join_recv.py all_vt.out recv_all.tsv > join.tsv`: **46/46 一致** (§5.11 と一致)。
7. `indirect_sr85_this_slot.py Serum2_win64.vst3 join.tsv > this_slot.tsv` (新規): `vptr:THIS` (strict) の 14 サイトについて、所属関数 (`in_func`) を slot に持つ vtable の class 集合 C を求め、構築済み vtable のうち class が C に入るものの slot k の関数を候補にする。

### 6.2 実測 (`this_slot.tsv`)

`vptr:THIS` (strict) は join.tsv の 46 サイトのうち 14 件。`owners` は所属関数を slot に持つ vtable の数 (class 集合の大きさ)、`all` は構築済み全 vtable の slot k の関数数、`restricted` は owners の class に限った slot k の関数数。

| site | operand | owners (vtable 数) | all | restricted |
|---|---|---:|---:|---:|
| 180136d45 | [RAX+0x188] | 161 | 8 | 5 |
| 180136d53 | [RAX+0x190] | 161 | 4 | 1 |
| 1801387e3 | [RAX+0x48] | 178 | 79 | 9 |
| 1801389a3 | [RAX+0x48] | 185 | 79 | 9 |
| 180142566 | [RAX+0x220] | 141 | 5 | 2 |
| 180142575 | [RAX+0x210] | 141 | 5 | 2 |
| 18014258f | [RAX+0x220] | 141 | 5 | 2 |
| 18014259e | [RAX+0x210] | 141 | 5 | 2 |
| 1806227d0 | [RAX+0x200] | 1 | 3 | 1 |
| 180622831 | [RAX+0x48] | 1 | 79 | 1 |
| 180117c75 | [RAX+0x58] | 42 | 61 | 1 |
| 180117caa | [RAX+0x48] | 42 | 79 | 2 |
| 180118168 | [RAX+0x220] | 37 | 5 | 1 |
| 180118177 | [RAX+0x210] | 37 | 5 | 1 |

- 絞れた例: `1806227d0`・`180622831` は所属関数が `XferOnOffButton` の slot 関数 (owner は 1 class)。候補は各 1 関数 (restricted 1)。
- 絞れない例: `1801387e3`・`1801389a3` 等は所属関数が多くの class の slot に現れる (owners 178・185)。`restricted` も 9 件残る。
- `owners` が多い場合、所属関数は汎用の基底 (`CControl` 等の共有 slot 関数) とみなせ、this の class を一意にできない。

### 6.3 判定

- 受入 (同じ slot を持つ別クラス vtable の候補を型で絞る) は**未達**。
- 絞り込みは 14 サイトのうち、所属関数が XferOnOffButton 固有の slot に属する 2 件 (`1806227d0`・`180622831`) で成立する。残り 12 件は所属関数が共有の基底 slot に属し、this の class が一意に決まらない。
- 制約: 所属関数の class 集合が広い (owners が 100 を超えるものがある) ため、`restricted` は「所属関数を持つ全 class の slot」の和で、呼出先の型の証明ではない。

### 6.4 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 共有基底 slot に属する `vptr:THIS` 12 件の this class の一意化 (受信オブジェクトの生成元を関数間で追う) | 別クラス候補の絞りが 12 サイトで未完 (受入未達) | #5934 (open のまま) |
| `R-index` 10 件 (`[rax+8]` 等の rax の由来) | 型追跡の対象が未確定 | #5934 (open のまま) |
