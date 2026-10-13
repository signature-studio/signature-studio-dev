# REPORT_N55 — #955 [M11-N55]: sigfix 0 詰め site の liftdiff 差分ハーネス検証

親: #131 / 依存: #122 (CLOSED)。対象: `tools/m11/results/sigfix_zeropad_remaining.tsv` (0 詰め site 1,049 行)。
REPORT §9 (#131) の「次の一手」を実施した結果。

**起点**: origin/main `352f4e96` の上で作業 (ブランチ `955-m11-zeropad-liftdiff`)。
環境: 4 vCPU runner, `work-m11` / `work-liftdiff` / `fl-win64` (`block00031_PE.bin`) / `toolchain-emsdk` 展開済み, `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
harness は `liftdiff.py build targets/m11.json` (sig_mismatch 0) → `liftdiff.py batch targets/m11.json --set file:<VA 一覧> --shards 4 --nobuild`。

## 1. 結論 (実測)

| 項目 | 実測 |
|---|---|
| 0 詰め site 1,049 件 | **一致 170** / **不一致 293** / **未到達 586** (site 単位, `m11_zeropad_liftdiff.py` の集計) |
| callee の内訳 | 対象 callee 217 件 → 一致 30 / 不一致 69 / 未到達 118 (重複あり) |
| 再現性 | 同一 HEAD で batch を 2 回実行 (n=2)。batch 集計は 75/173/419 で一致し、site 判定表 (`sigfix_zeropad_liftdiff.tsv`) は **完全一致** (`diff` 0 行) |
| 所要 | batch 1 回 200 秒 (n=1) / 199 秒 (n=2), 667 関数, 4 shards, load 1.7 |
| 不一致 site のうち tag が引数 k を指すもの | 25 site (`callsite_arg_drop` 等の evidence が `arg<k>` を含む) |

受入条件「0 詰め site のうち差分ハーネスで実行されるものを優先順に検証し、結果 (一致 / 不一致 / 未到達) を REPORT に実測値で残す」は、
**全 1,049 site を判定した** (実行される 463 site は一致/不一致、残り 586 site は未到達)。

## 2. 判定の定義

* 対象 callee (`sigfix` が引数を 0 詰めした call の呼出先) の harness 採点 (`function` 単位, 9 pattern) を site に写す。
* **一致** = callee の verdict が `match`。
* **不一致** = callee の verdict が `mismatch`。tag が `arg<k>` を指す場合は `arg` 列に記録 (0 詰めした引数そのものの差分を示すか)。
* **未到達** = callee の verdict が `unexec` (native が fault / null deref / hang / 未対応シグネチャ), または batch 対象外 (`not_in_batch` は 0 件)。
* 優先順: 判定確定 (不一致 → 一致) → 未到達。同順位内は callee の出現数が多い順。

判定表: [results/sigfix_zeropad_liftdiff.tsv](results/sigfix_zeropad_liftdiff.tsv) (1,049 行, 優先順付き)。
再現: `python3 tools/m11/m11_zeropad_liftdiff.py tools/liftdiff/work/m11/batch_zeropad.jsonl` (batch は `liftdiff.py batch` の `--set file:` 指定)。

## 3. 内訳

| 判定 | site | callee 数 | 主な callee (site 数) |
|---|---:|---:|---|
| 不一致 | 293 | 69 | `function_40ae70` (71), `function_40d210` (34), `function_6bed60` (16), `function_65f270` (12), `function_6c3700` (9) |
| 一致 | 170 | 30 | `function_418190` (111), `function_60ae30` (12), `function_63a6d0` (7), `function_6774b0` (6), `function_737f70` (4) |
| 未到達 | 586 | 118 | native null deref 50 / native fault 50 / hang 12 / unsupported_sig 6 (callee 単位) |

不一致 site のうち evidence が引数 k を名指しするもの (25 site): `function_4093f0` arg0, `function_413770` arg0, `function_660cc0` arg4, `function_6613b0` arg0, `function_67db00` arg0, `function_6a09b0` arg0, `function_6be4f0` arg0, `function_6bed60` arg0, `function_6c3700` arg0, `function_6c5930` arg0, `function_6ee1a0` arg0, `function_7f2fe0` arg0, `function_920270` arg0, `function_bb1ad0` arg0, `function_cc33d0` arg0。
(残りの不一致 site は callee 単位の差分で、0 詰め引数そのものとの対応は tag から確定できない。)

## 4. 解釈と制約

* **一致 = 0 詰め引数が意味的に正しいことの証明ではない**。harness は callee 単体の入出力を native と比べるだけで、呼出し元が渡すべき値 (0 詰めで置き換えた値) は検証しない。一致は「callee が 0 詰めされた値を与えられても挙動が native と同じ入力範囲で一致した」ことを示すに留まる。
* 不一致 293 site は 0 詰めの誤りを示し得るが、evidence が arg k を名指しするのは 25 site のみ。残りは callee 本体の lift 欠陥 (`load_dropped` / `callee_divergence` 等) の可能性があり、0 詰め起因とは確定しない。
* 未到達 586 site は native 側で既に実行不能な callee。0 詰めの正否は本 harness では判定できない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未到達 586 site (native fault / null deref / hang / unsupported_sig の callee) | 0 詰めの正否が未判定 | #955 (Refs)。native 側の入力生成を拡充する作業は未起票 (PM へ起票を依頼) |
| 不一致 site のうち 0 詰め起因か callee 本体の欠陥かの切り分け (arg 名指し 25 site 以外) | 不一致 293 site の帰属が未確定 | #955 (Refs)。DEFECTS.md への行案は PM 判断 |
| 一致 site の意味的な正しさ (callee 単体の一致 ≠ 呼出し元の 0 詰め値の正しさ) | §4 の通り | #955 (Refs)。未検証 |
