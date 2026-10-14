# 付録: liftdiff LD-28 (#1035) — 型 C・D の原因候補・0x417b70 の idiv/udiv 仮説

> **正本**: `tools/liftdiff/REPORT.md` (結論・§7 未解決)。本書は LD-28 (#1035) の節を `REPORT_APPENDIX.md` §9 から分割移動したもの (250 行上限のため)。`REPORT_APPENDIX.md` §9 には参照 1 行のみ残す。

#### 型 C・D の原因候補 (LD-28 / #1035)
集計 = `tests/trace_diverge_cd.py` → `results/m11_unreachable_cd.md` (件数の正本)。型 A・B (#864 の D15 候補・leaf) を除いた型 C・D の食い違いを対象にする。
- 結論: 型 C・D の食い違いは原因候補 (P1・P2・P3) に分類した。P2 は L が F の直接 call 先であることを条件に含む。内訳は results 参照。
- P2 の代表例 0x418be0 (呼出元 0x41c820) は P2 候補に分類した。IR 側 (`call 0x407030` の欠落) は再確認していない。call site と IR block の対応づけは未実施。
- P2 の全 20 件で F→L の直接 call 辺 (`L ∈ direct_calls(F)`) が成立することを PE 実測で確認した。
- **測定 commit = `200cc2b4`** (PR #1434 の検証 run: `trace_diverge_cd.py` 15.6 s・`results/m11_unreachable_cd.md` と diff 0 行)。同じ 3 ファイルは `516a2b07` (前回 run の記録: 16.56 s・diff 0 行) でも同一内容。`results/m11_unreachable_cd.md` の再実行は、この fix run では素材が無く行っていない。3 ファイルを最後に変えた commit は `8119565c`。
- **鮮度 (#1268・`docs/WORKFLOW.md` §6)**: 測定 commit からの、測定に使う 3 ファイルの差分。
  ```
  $ git diff 200cc2b4 HEAD -- tools/liftdiff/ldlib/pe.py tools/liftdiff/tests/trace_diverge_cd.py tools/liftdiff/results/m11_unreachable_cd.md
  (出力 0 行)
  ```
  以後の commit は REPORT_APPENDIX の文書のみ。
- P2 の全 20 件で `L ∈ direct_calls(F)` が成立 (同一 PE・同一入力で 20/20 を確認)。
- 候補判定は call 先の集合差分のみ。P1・P2 は候補であり確定ではない。
- **0x417b70 (LD-28 受入条件 1・静的確認のみ、動的未確認)**: 食い違い 32 件の次 entry は native 側 0x409470 (18)・0x409410 (11)・0x418190 (3)、wasm 側 0x409730 (17)・0x409410 (15)。
  L の機械語は `417c56: idiv qword ptr [rbp+0x60]` (符号付き除算、直前の `cqo` で符号拡張)。機械語は `block00031_PE.bin` (RVA `0x17c56`, ImageBase `0x400000`) で確認。
  IR は `%29 = udiv i64 %28, %arg4` (符号なし) と前回 run で記録したが、**`boot_final3.ll` の行番号は未確認** (素材 `work-m11` が無く、本 fix run では再照合していない)。
  その直後の `icmp eq %29, %27` が偽のとき `call 0x409730; unreachable` へ進む。stride×count が負で count ≥ 2 なら、符号付き除算は stride を返すが符号なし除算は一致しない。count = 1 では一致する (下記)。
  数値例 (積の符号のみ・64bit 整数で計算): −16×2 (count 2)、−32×4、−8×3、−16×3 で udiv は stride を返さず、idiv は返す。反例: count = 1 では udiv も idiv も stride を返し一致する (−16×1 で両方 −16)。
  仮説: 32 件の一部は、この udiv が trap 経路 (0x409730) を誤って取ることで生じる。**未確認**: 32 件の stride 符号・経路の実測、および sdiv への修正後に食い違いが消えるかの再実行。
  `417c7a`〜`417c81` の `dword [rax+4]==1` 判定と 0x409410/0x409470 の分岐も未確認。
  子 issue: #1238 (LD-41) に追記 (動的確認の受入条件を持つ)。

#### 0x418be0 (P2 20 件) の IR 側確認 (LD-28 受入条件 1・本 run の実測)
- 機械語 (`block00031_PE.bin`): 呼出元 `0x41c820` は `0x41c875: call 0x418be0` の後、`0x41c88a: call 0x407030` を持つ。`0x407030` は IAT の `LoadStringW` への `jmp qword ptr [rip+...]` thunk (IAT RVA 0x1970c78)。
- IR (`boot_final3.ll`): `function_41c820` は `%14 = call i32 @LoadStringW(...)` を**直接**呼ぶ (`function_407030` を経由しない)。`function_407030` 自体は `@LoadStringW` を呼ぶ定義として存在する (L105921)。したがって P2 の「`call 0x407030` の欠落」は、IR に thunk 呼出しが無いという表現の差で、呼出し脱落そのものとは言えない。
- batch 実測 (`work-liftdiff` の `batch_closure.jsonl`・20 件・wasm_trap かつ unreachable・食い違い L = 0x418be0): native trace は全 20 件で `0x418be0 → 0x407030 → 0x413060`、wasm は `0x418be0 → 0x413060`。全 batch (17,324 case) で wasm trace に `0x407030` が現れるのは 0 件、native に現れるのは 317 件。
- thunk `0x407030` を native trace から除いて比べると、20 件中 4 件は trace_head 内で一致、16 件は食い違いが残る (次の不一致 entry: `0x409410` vs `0x4133f0` 9 件・`0x4233b0` vs `0x413060` 3 件・`0x467910` vs `0x4133f0` 2 件・`0x409410` vs `0x43dd60` 1 件・`0x412c20` vs `0x412d60` 1 件)。
- 結論: 0x418be0 系の食い違いは「thunk の脱落」だけでは説明できない。`0x407030` は表現差として扱い、残る分岐 (`0x41c820` 以後の `0x413060` 呼出し後の経路) は未特定。P2 の件数 (20) は results の分類どおりで、その原因ラベルは「thunk 脱落」から「未特定 (IR の thunk 呼出し無し・後続 trace で食い違い)」に読み替える。受入条件 1 の 0x418be0 は、この読替えで静的確認済み・原因は未達 → #1035 に残す。
- 再現 (本 run の一回限りの解析・スクリプト未 commit): `batch_closure.jsonl` を読み、`wasm_trap` かつ detail が `unreachable` の case で、trace_head の最後の共通 entry が 0x418be0 のものを抽出。native 側から `0x407030` を除いた列と wasm 列を比較。PE は `LD_M11_PE=work/fl-win64/extracted/block00031_PE.bin`。
