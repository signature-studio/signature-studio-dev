# #1231: M11_FIX_652500=1 時の unit 888 退行の再測定 (測定 commit 2b2faf52)

既知類型との関係: 該当なし (IR・build・harness の再測定で、`docs/DEFECTS.md` の類型は新規確定しない)。

**判定: 退行は再現しなかった。** 受入条件 1 (VA 上限か論理差か) と 2 (survey 2 系統の食い違いの理由) は、比較対象の退行が存在しないため判定できない。**Refs #1231** (Closes しない)。

親: #1019 (M11-N58) / 前提: PR #1018 (gate `M11_FIX_652500`)。REPORT_1019 §1 の退行 (888: ok → halt0) を、測定 commit `2b2faf52` で再測定した結果。

## 0. 測定環境

- 測定 commit: `2b2faf52` (本 PR head のコードが測った commit。PR head `26a1c481` までの `git diff 2b2faf52 HEAD -- tools/m11` はこの REPORT のみ = 差分 0 の証跡)。
- 素材: `fl-win64` は `$RUNNER_TEMP/fl-win64` に展開。`work-m11` / `work-liftdiff` は `tools/m11/work/`・`tools/liftdiff/work/` に展開。`toolchain-retdec` / `toolchain-emsdk` は [OPT-TOOLS] 配下の [RETDEC]・[EMSDK] を使用 (PATH・[RETDEC] の bin・[EMSDK] で確認)。
- `m11_gen_ir2.sh`: rc=0, 43 s, `ldfix=applied`, `ir_sha256=2c68ceae…` (2 回実行で同一)。
- build (`m11_build.sh`): OFF rc=0 24.5 s / ON rc=0 18.5 s。load 1 分値 0.8 前後。
- **注意**: `m11_build.sh` は build 時に qstore 後処理で `boot_final.ll` を書き換える (`qstore=applied`, `ir_sha256=16d1bae6…`)。REPORT_1019 の `ir_sha256=f5b27a23…` とは IR が一致しない。以下は qstore 適用版 (既定) と qstore 無効版 (`M11_QSTORE=0`) の両方で測った。

## 1. survey_units.mjs (既定 build = qstore 適用)

| 構成 | ok | oob | halt0 | miss | other | noproc | 計 | 実行 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| OFF (gate=0) | 870 | 16 | 7 | 47 | 1 | 1 | 942 | n=2 (同一) |
| ON (gate=1) | 870 | 17 | 6 | 47 | 1 | 1 | 942 | n=2 (同一) |

- 888 は OFF/ON とも `ok` (ret=1, va_mb=74.8)。退行なし。
- OFF と ON の unit 別 kind の差は unit 895 のみ (`halt0` → `oob`)。REPORT_1019 の 368 / 659 / 888 の遷移はいずれも再現せず。
- 888 の grow 失敗 (`Maximum memory size exceeded`) は OFF/ON とも 0 件。`live` は ON で 775.7 MB。

## 2. m11_survey.mjs (`M11_SURVEY_STACK=149,888`, 既定 build)

- 888: OFF/ON とも `returned 1` (ok)。
- 149: OFF/ON とも `memory access out of bounds` (REPORT_1019 と一致)。
- 集計: OFF `va_live=1355 MB`, ON `va_live=850 MB` (ON が小さい)。`va_oom=0`, `trap_oom=0`。

## 3. qstore 無効 (`M11_QSTORE=0`) の再測定

| 構成 | survey_units ok / oob / halt0 | m11_survey unit 別 kind |
|---|---|---|
| OFF | 868 / 18 / 7 | OFF = ON (差 0) |
| ON | 868 / 19 / 6 | |

- m11_survey の unit 別 kind は OFF/ON で完全一致 (差 0 件)。888 は両 build とも ok、368 は ok、659 は trap。
- survey_units の OFF→ON 差は halt0 → oob が 1 件 (件数は qstore 適用版と違うが、遷移の向きは同じ)。

## 4. 結論

- REPORT_1019 §1 の「888: ok → halt0 (ON)」は、測定 commit `2b2faf52` (測定時点の main) では再現しない (4 構成のいずれでも 888 は ok)。
- REPORT_1019 §2 の「survey 2 系統で 888 の判定が食い違う」も再現しない。両 survey とも 888 は ok。
- 退行の原因が IR の差 (REPORT_1019 は `f5b27a23…`) か、その後の main の変更 (qstore・#1046 など) かは未確認。切り分けには REPORT_1019 時点の commit での再測定が要る。
- 受入条件 1・2 は判定不能 (対象の退行が無い)。受入条件 3 (本 REPORT の記録) は本 PR で満たす。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| REPORT_1019 時点の commit で 888 退行を再現し、測定 commit `2b2faf52` との差分 (IR・qstore・#1046) を切り分ける | 退行の有無と原因の確定 | 本 issue #1231 のコメントで PM 判断 |
| survey_units.mjs の OFF→ON 差 (unit 895 halt0→oob、qstore 有無で件数が変わる) | survey 数値の信頼性 | 本 issue の続きとして PM 判断 |
| REPORT_1019 の受入条件 1・2 (unit 149 の原因特定、gate 既定 ON 化) | #1019 の残り | #1230 (M11-N75) |
