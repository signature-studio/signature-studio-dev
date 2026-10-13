# #1188: RetDec が先頭 cmp/jg を落とす段の切り分け (8c5eb0 と同型の最小再現)

判定: 受入 1 (最小再現で jcc の条件辺が落ちることを確認) **達成**。受入 2 (落ちる段の切り分け) **達成 (default オプションのみ)**: 脱落は CFG 復元段ではなく、default オプションの LLVM 最適化段 `Simplify the CFG` で起きる。`--backend-no-opts` 構成での pass 単位の切り分けは未実施 (§3・§4)。受入 3 (RetDec 本体・`m11_ov.c` 非変更) **達成**。
検証 HEAD: 本 PR の commit (ブランチ `1188-retdec-jcc-cut`)。RetDec は `toolchain-retdec` の v5.0 (commit `53e55b4b`)。

## 1. 既存の生 lift での確認 (8c5eb0 実物)

- `work-m11` の `boot2.drc.dsm` (RetDec 逆アセンブル段) には `0x8c5f15 cmp dword ptr [rbp+0x4c], ebx` と `0x8c5f18 jg 0x8c6066` が残っている。
- 同じ `boot2.drc.ll` (RetDec 出力・後処理前) では `dec_label_pc_8c5ef5` が無条件 `br` で `8c5f23` へ進み、`cmp`/`jg` が無い。
- `8c5eb0` 単独 (`--select-ranges 0x8c5eb0-0x8c60ed`) でも同じ。`--backend-no-opts` でも消える。よって脱落は `--backend-no-opts` で無効化されない段で起きる (段の特定は §3 の default オプションの trace による)。

## 2. 最小再現 (`tools/m11/trap_triage/1188_min/`)

ELF (x86-64, `_start`) を `as`+`gcc -nostdlib -static` で作り、`retdec-decompiler <elf>` で lift する。3 variant:

| variant | 比較の左辺 | 最終 IR の `br` 数 | 判定 |
|---|---|---|---|
| vA (`xor eax,eax; cmp eax,ebx; jg`) | 即値由来の 0 | 0 | jcc 脱落 |
| vB (`mov eax,[rcx+0x18]; cmp eax,ebx; jg`) | メモリ読み出し (未知値) | 2 | 残る |
| vC (`mov eax,0; cmp eax,ebx; jg`) | 即値 0 | 0 | jcc 脱落 |
| g2 (`8c5eb0` 同型: `cmp [rbp+0x4c],ebx; jg` 先頭ガード + 後方 back-edge `jle` のループ) | スタック読み出し・ループ版 | エントリ終端が無条件 `br` | jcc 脱落 |

ループ版 g2 は受入 1 の形 (先頭 cmp/jg + back-edge ループ) に当たる。エントリブロックの終端を見ると、先頭ガードの `jg` が無条件 `br` に変わっている。

再現: `RETDEC=<retdec-decompiler> bash tools/m11/trap_triage/retdec_jcc_cut_1188.sh` (出力は `tools/m11/work/trap1188/`、gitignore)。実測 (本 run, 2026-10-13 21:54 UTC): `vA: entry guard DROPPED`・`vB: entry guard kept`・`vC: entry guard DROPPED`・`g2: entry guard DROPPED`。

raw モード (`-m raw -a x86-64`) は 32 ビットとして逆アセンブルされるため (REX 前置が `dec eax` になる)、再現には使えない。ELF で行う。

## 3. 段の切り分け (pass 単位)

`retdec-decompiler --print-before-all` で LLVM パスごとの IR を取り、`br` 数を数えた。**すべて default オプションでの trace**。`--backend-no-opts` 構成では `--print-before-all` を取っていないため、以下の段の特定は no-opts 構成には当てはまらない (未検証)。

- **Input binary → LLVM IR decoding → Module Verifier**: 翻訳直後の IR で `jg` は `sf==of && !zf` の `br` として正しく生成されている (`8c5eb0` の `8c5f18` で `br i1 %155`、vA の `br i1 %15` の `icmp sgt`)。**命令翻訳は正しい**。
- **CFG 復元 (`jcc` の終端化)**: 翻訳段で既に `br` として存在するため、CFG 復元で条件辺が落ちているのではない。
- **`8c5eb0` 本体**: `icmp sgt` (`8c5f18`) は段 40 (`Combine redundant instructions`) の入力まで残り、段 41 (`Simplify the CFG`) の入力で `br i1 false, label %dec_label_pc_8c6066` に変わっている。直前の `store i32 0, i32* %stack_var_-44` (ループカウンタ初期化) を経て、比較の左辺が定数 0 と見なされたと推定する (左辺の既知化の経路は未追跡)。
- **vC**: pass 25 の時点で既に `icmp sgt i64 0, %x` (左辺が定数 0)。`Simplify the CFG` で分岐ごと消える。
- **vA**: pass 25 では左辺が `xor(rax, rax)` (同一値の xor) で、0 に畳まれるのは後段。`Simplify the CFG` で消える点は vC と同じ。
- **vB**: 左辺が未知 (メモリ読み出し) なので `icmp` は残り、分岐も残る。

## 4. 結論

- default オプションの pass trace では、脱落の段は **LLVM 最適化の `Simplify the CFG`**。`--backend-no-opts` 構成では pass trace を取っていないため、この段が no-opts でも動くかは未検証 (§1 の「no-opts でも消える」と両立するかは未確認)。命令翻訳 (フラグ計算) と CFG 復元 (`jcc` の終端化) は、いずれも正しく jcc を保持している (翻訳直後の IR で `br` あり)。
- 引き金は「比較の左辺が定数 0 と見なされる」こと。vC (即値 0) で実測。`8c5eb0` では直前の `store i32 0` (ループカウンタ初期化) 経由と推定 (経路は未追跡)。vB (未知値) では残る。
- 既存 REPORT_699 §2 の「生 lift で既に脱落」は、生 lift (RetDec 出力・後処理前) の段での観測として正しい。ただし脱落は RetDec 内の `Simplify the CFG` で起きるため、「CFG 復元か翻訳か」の未切り分けはこれで解消する。
- DEFECTS 類型との関係: D1b (フラグが定数に畳まれる) と機構が近いが、畳み込み対象が「フラグ」ではなく「比較の左辺が既知 0 の `icmp`」である点は未確認。同一視はしない (PM 判断)。

## 5. 範囲と未解決

- `m11_ov.c`・RetDec 本体は変更していない。
- 未解決 (a): 「既知 0」以外の既知値 (定数 1, -1 等) で同じ畳み込みが起きるか。本 run では 0 のみ確認。受入条件の外。起票要否は PM 判断。
- 未解決 (b): `Simplify the CFG` の畳み込み規則の正確な条件 (RetDec ソース未確認)。RetDec 本体は変更しないため、ソース確認は本件では行わない。
- 未解決 (c): 修正方針 (lift 前処理で `cmp` 左辺を既知定数から切り離すか、後処理で jcc を復元するか) は PM 判断。DEFECTS.md 行案は本 REPORT では確定しない。
- 20 MiB 超の blob: 追加なし。
