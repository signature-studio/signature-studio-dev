# liftdiff REPORT 付録: OTT 旧 chain の前回比差分の切り分け (LD-16 / #825)

本書は `REPORT.md` §10 の要約の全文。親 issue #406 / PR #802 の前回比差分 (38/108/66 → 33/110/69) の追跡。

## 結論

- OTT 旧 chain の集計差分は **commit 間の `ldlib/cases.py` の pattern 追加** (`79584ef7` feat(liftdiff): add this/VMT and UTF-16 string case patterns (#235)、9→11 pattern) で説明できる。
- 分類: **main の変更** (採点基準・非決定性ではない)。`cases.py` 単独の差し替えで 33→35 / 110→112 / 69→65 が再現し、他のファイル (`compare.py`・`classify.py`・`pe.py`・`rt/`) は単独では集計を変えない。
- 非決定性: 旧 `59eea5c` も現 HEAD `986e7415` も OTT 集計は 3 回とも同一 (下表)。
- issue 本文の **38/108/66 は今回の素材・commit では再現しなかった**。main 側 `tools/liftdiff/work/ott_old/` (2026-10-12 18:27) の batch は今回の `59eea5c` 再計算と一致せず、関数単位で 16 件が異なる。その由来は未特定 (PR #802 の run 時点の素材・環境差と推定。未確認)。

## 1. 実測 (本 run・Actions runner・4 vCPU)

OTT 旧 chain (`build ott_old` + `batch --set closure --shards 4` + `tests/check_ott.py`)。素材 `fl-win64` `work-m11` `work-liftdiff` `work-m6-ott` `analysis-ott-binaries` (`$HOME/artifacts` の実在を確認して展開)。

| commit | 回 | 集計 (一致 / 不一致 / 実行不能) | D1 / D2 / D3 / D4_D5 / D6 |
|---|---|---|---|
| `59eea5c` (旧) | 1 | 33 / 110 / 69 | 4 / 6 / 13 / 19 / 26 |
| `59eea5c` (旧) | 2 | 33 / 110 / 69 | 4 / 6 / 13 / 19 / 26 |
| `59eea5c` (旧) | 3 | 33 / 110 / 69 | 4 / 6 / 13 / 19 / 26 |
| `986e7415` (現 HEAD) | 1 | 35 / 112 / 65 | 4 / 6 / 14 / 20 / 26 |
| `986e7415` (現 HEAD) | 2 | 35 / 112 / 65 | 4 / 6 / 14 / 20 / 26 |
| `986e7415` (現 HEAD) | 3 | 35 / 112 / 65 | 4 / 6 / 14 / 20 / 26 |

- 旧 `59eea5c` の 1 回目は build 時に `tools/m6/work` が無く失敗した状態から、素材を入れ直して再実行した結果 (失敗時の batch は採用していない)。

## 2. 原因の切り分け (ファイル単位の差し替え)

旧 `59eea5c` の worktree に、現 HEAD の該当ファイルを 1 組ずつ入れて `build` + `batch` + `check_ott.py` を実行した (毎回 build)。

| 差し替え (現 HEAD のファイル) | 集計 |
|---|---|
| なし (旧そのまま) | 33 / 110 / 69 |
| `rt/` (fle_runner.mjs・ld_core.h・ld_native.c・ld_runner.mjs) | 33 / 110 / 69 |
| `ldlib/compare.py` `classify.py` `pe.py` | 33 / 110 / 69 |
| `ldlib/compare.py` のみ | 33 / 110 / 69 |
| `ldlib/cases.py` のみ | **35 / 112 / 65** |
| 全 9 ファイル | 35 / 112 / 65 |
| 現 HEAD の `ldlib` のみ (rt 旧) | 35 / 112 / 65 |

注: build を省いた途中の実行は無効として採用しない。結論は build を毎回入れた再実行で確定した。

## 3. 関数単位の突合 (旧 `59eea5c` 3 回目 vs 現 HEAD 3 回目)

判定が変わった関数 (`tests/ott_delta.py`):

| 関数 | 旧 | 新 | 変化 |
|---|---|---|---|
| 1801ab1d0 | unexec (native_fault) | match | unexec 解消 |
| 1801ab258 | unexec (native_fault) | match | unexec 解消 |
| 1801ab3ec | unexec (native_null_deref) | unexec (native_fault) | 理由のみ変化 |
| 1801c5e84 | mismatch | mismatch | wasm_trap 追加 |
| 1801c621c | mismatch | mismatch | wasm_trap 追加 |
| 1801c67a0 | unexec (native_null_deref) | mismatch | wasm_trap 追加 (C 定義) |
| 1801c682c | unexec (native_null_deref) | mismatch | callee_divergence・callsite_arg_drop・import_call_seq・unresolved_callee 追加 |
| 1801c69cc | mismatch | mismatch | wasm_trap 追加 |

- 追加 pattern (vm0/u16) が、既存の unexec 関数に対する native fault の見え方を変え、さらに深部の比較を可能にした、と読める。ただし個別の機序は**未確認** (本 run は関数単位の trace を見ていない)。
- D1 / D2 / D6 は両 commit で同数。D3 (+1) と D4_D5 (+1) の差が集計の差分の全部。
- 件数の増減の方向 (unexec 4 件減・mismatch 2 件増) は `cases.py` の pattern 追加と整合する。

## 4. n=3 の非決定性

- OTT 集計 (`check_ott.py`): 旧・現とも 3 回同一。非決定性なし。
- m11 sample:800 (`liftdiff_e2e.sh` [4/4]): 現 HEAD 3 回 = 一致 361 / 360 / 361、不一致 229 / 230 / 229、実行不能 210 / 210 / 210。1 件の揺れ (run 依存)。
  - 揺れの原因は推定 (native timeout・負荷による case outcome の揺らぎ、REPORT_APPENDIX §11 と同類)。関数単位の特定は未実施。
- e2e 全体: 3 回とも exit 0・`LIFTDIFF_E2E PASS`・所要 184.9 / 185.5 / 183.4 s (load avg は 1 分平均で 4.8〜6.4 の間で変動)。

## 5. 数え方の定義と再計算

- 対象: `targets/ott_old.json` の closure 212 関数 (`batch --set closure`)。
- 集計: 関数ごとの `verdict` (`match` / `mismatch` / `unexec`) の件数。
- D1〜D6 (`tests/check_ott.py`): D1 = tag `icall_drop` の関数数、D2 = `short_global`、D3 = `callsite_arg_drop` ∪ `arg_drop`、D4_D5 = C 定義 (`sig.c`) かつ mismatch、D6 = `xmm_arg_drop` ∪ `zero_init_drop` ∪ `fp_flag_unreflected` ∪ `spill_slot_deref`。tag は複数重複あり。
- 再計算:
  ```
  python3 liftdiff.py batch targets/ott_old.json --set closure --shards 4 --nobuild --out work/ott_old/batch.jsonl
  python3 tests/check_ott.py                     # OTT_SUMMARY を出力
  python3 tests/ott_delta.py <旧 batch.jsonl> <新 batch.jsonl>   # 関数単位の差分
  ```
- 旧 commit の再現: `git worktree add --detach <dir> 59eea5c`、`tools/{ott,m6,m11,liftdiff}/work/` を素材から入れる。

## 6. 検証の範囲・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| issue 本文の 38/108/66 の由来 (PR #802 の run 時点の素材・環境) は未特定。今回の素材では再現しない | 前回比の基準値が 2 系統ある | 本 issue #825 にコメント済み。PM 判断 |
| 関数単位の tag 変化の機序 (vm0/u16 pattern がなぜ unexec の native fault を解消するか) は未確認 | pattern 追加の効果の説明が推定止まり | 起票先未定 (次の LD 子 issue 候補) |
| m11 sample:800 の 1 件揺れの関数特定 | 非決定性の出所が未特定 | 同上 |
| 素材の展開・python 依存 (`numpy capstone pefile`) は run ごとに必要 | 素の runner で e2e が exit 2 | 既に REPORT_APPENDIX §10 の未解決 (agent-setup) |
