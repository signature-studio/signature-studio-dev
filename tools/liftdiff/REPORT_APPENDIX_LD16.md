# liftdiff REPORT 付録: OTT 旧 chain の前回比差分の切り分け (LD-16 / #825)

本書は `REPORT.md` §10 の要約の全文。親 issue #406 / PR #802 の前回比差分 (38/108/66 → 33/110/69) の追跡。

## 結論

- OTT 旧 chain の集計差分は **commit 間の `ldlib/cases.py` の pattern 追加** (`79584ef7` feat(liftdiff): add this/VMT and UTF-16 string case patterns (#235)、9→11 pattern) で説明できる。
- 分類: **main の変更** (採点基準・非決定性ではない)。`cases.py` 単独の差し替えで 33→35 / 110→112 / 69→65 が再現し、他のファイル (`compare.py`・`classify.py`・`pe.py`・`rt/`) は単独では集計を変えない。
- 非決定性: 旧 `59eea5c` も現 HEAD `986e7415` も OTT 集計は 3 回とも同一 (下表)。
- **ログの扱い**: 現 HEAD `986e7415` の 3 回分は `tools/liftdiff/results/liftdiff_e2e_head986e7415_n{1,2,3}.log` として commit 済み。旧 `59eea5c` の 3 回分と §2 の差し替え実行のログは **commit されていない**。再生成には `work-m6-ott` / `work-m11` / `work-liftdiff` / `analysis-ott-binaries` の素材が要り、後続 run の `$HOME/artifacts` には `fl-win64` しか無かったため再実行できていない。よって §1 の旧 `59eea5c` の行と §2 の表の数値は、ログで検証できない報告値として扱う。検証するには素材を揃え、`git worktree add --detach <dir> 59eea5c` で §5 の手順により再実行する必要がある。
- issue 本文の **38/108/66 は今回の素材・commit では再現しなかった**。main 側 `tools/liftdiff/work/ott_old/` (2026-10-12 18:27) の batch は今回の `59eea5c` 再計算と一致せず、関数単位で 16 件が異なる。その由来は未特定 (PR #802 の run 時点の素材・環境差と推定。未確認)。

## 1. 実測 (本 run・Actions runner・4 vCPU)

OTT 旧 chain (`build ott_old` + `batch --set closure --shards 4` + `tests/check_ott.py`)。素材 `fl-win64` `work-m11` `work-liftdiff` `work-m6-ott` `analysis-ott-binaries` を使用した実行の記録 (旧 `59eea5c` 分は報告値)。

ログ区分: 上の表で `986e7415` の行は commit 済みログで検証可能。`59eea5c` の行はログ無し (上記「ログの扱い」参照)。

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
**ログ無し**: 上表の各行 (`cases.py` のみ・全 9 ファイル等) の実行ログは commit していない。この表は検証可能な一次ログではなく報告値。`ldlib/cases.py` 単独差し替えの再現は、素材を揃えて §5 の手順で再実行する必要がある (未実施・未検証)。

## 3. 関数単位の突合 (旧 `59eea5c` 3 回目 vs 現 HEAD 3 回目)

旧 `59eea5c` と現 HEAD の関数単位の差分 (`tests/ott_delta.py`)。変化は 8 件: verdict 変化 4 件 (unexec→match 2 件・unexec→mismatch 2 件) と、tag または unexec 理由のみの変化 4 件。

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
| issue 本文の 38/108/66 の由来 (PR #802 の run 時点の素材・環境) は未特定。今回の素材では再現しない | 前回比の基準値が 2 系統ある | #1069 ([LD-31]) |
| 関数単位の tag 変化の機序 (vm0/u16 pattern がなぜ unexec の native fault を解消するか) は未確認 | pattern 追加の効果の説明が推定止まり | #1070 ([LD-32]) |
| m11 sample:800 の 1 件揺れの関数特定 | 非決定性の出所が未特定 | #1070 ([LD-32]) |
| 素材の展開・python 依存 (`numpy capstone pefile`) は run ごとに必要 | 素の runner で e2e が exit 2 | 既に REPORT_APPENDIX §10 の未解決 (agent-setup) |

## 7. LD-32 (#1070): 8 関数の機序 (パターン単位の観測) と m11 sample:800 の n=3

測定: `c4e93550` (main 取り込み時点の HEAD)・Actions runner (4 vCPU・load 1 分平均 1.5〜6.9)。素材 `fl-win64` `work-m6-ott` `work-m11` `work-liftdiff` `work-liftlib` `analysis-ott-binaries` を展開。`bash tools/liftdiff/liftdiff_e2e.sh` は exit 0・`LIFTDIFF_E2E PASS`・所要 約 3 分 (本 run 1 回目)。OTT 集計 35 / 112 / 65 は §1 の `986e7415` と一致 (D1〜D6 = 4/6/14/20/26)。ログは `results/liftdiff_e2e_ld32_head_c4e93550_n1.log` (commit 済み)。

### 7.1 8 関数のパターン別観測 (観測メモ・未検証・再現不可)

注: 下表は**観測メモであり、受入の根拠に使わない**。元データ (`work/ott_old/batch.jsonl`) は `work/` (gitignore) で残っておらず、本 PR の差分からも再現できない。`results/ott_old_verdicts.tsv` は別時点の集計で、表の match/mismatch/unexec 判定を再現しない (例: 1801ab1d0 は unexec 0/9)。**元データの抜粋 TSV は未 commit**。素材 `work-m6-ott` `analysis-ott-binaries` を揃えた run で抜粋 TSV を commit するまで、以下の値は未検証として扱う。

| 関数 | 判定 | z | s | p0 | vm0 | u16 | 観測 |
|---|---|---|---|---|---|---|---|
| 1801ab1d0 | match | BF(divzero) | NF@1ab1dc | NF@1ab23d | equal | equal | vm0/u16 で初めて両側が正常終了 |
| 1801ab258 | match | NF@1ab25d | NF@1ab25d | NF@1ab2cb | equal | equal | 同上 |
| 1801ab3ec | unexec | NF@1ab41a | NF@1ab41a | NF@1ab420 | NF@1ab437 | NF@1ab420 | vm0/u16 でも native fault のまま。理由が null_deref→fault に変化 (§3) |
| 1801c5e84 | mismatch | equal | NF@1c5eb8 | diff | diff | wasm_trap | vm0 で diff に到達 (tag は wasm_trap が u16 由来) |
| 1801c621c | mismatch | equal | BF | diff | diff | wasm_trap | vm0 で diff に到達 |
| 1801c67a0 | mismatch | BF | BF | BF | wasm_trap | wasm_trap | 全パターンで wasm 側が m8_fail (abort)。vm0/u16 で wasm 側だけ trap |
| 1801c682c | mismatch | BF | BF | BF | diff | diff | vm0/u16 で diff に到達。qall のみ native fault |
| 1801c69cc | mismatch | equal | BF | diff | diff | wasm_trap | vm0 で diff に到達 |

- 機序の観測 (仮説・未確認): 乱数 blob (`r1`〜`r4`) では native 側が blob の値 (0x7e 等) を長さ・添字として使い、NF で止まる関数がある (1ab258 p0: rax=0x7e・r8=0x7e・addr=0x7e)。vm0/u16 は構造を持つ blob (VMT ptr・UnicodeString ヘッダ) なので native が最後まで走り、比較 (equal / diff) に進める。**これは行の値からの推定で、関数内の命令 trace (native と wasm の各 step) は本 run では取っていない**。
- 1801ab3ec: vm0/u16 でも native が 0x1ab41a〜0x1ab458 で fault し続けるため、構造 blob では解消しない。
- 1801c67a0: wasm 側の `m8_fail` (function_1801c721c 経由) が vm0/u16 で trap する。native は全パターンで abort/segv。この型は `wasm_trap` の原因関数 (wasm 側の m8 検査失敗) の特定が次の作業。

### 7.2 m11 sample:800 の n=3 (c4e93550)

| run | 一致 | 不一致 | 実行不能 |
|---|---|---|---|
| 1 (e2e 内 [4/4]) | 360 | 230 | 210 |
| 2 (batch のみ・同一 build) | 360 | 230 | 210 |
| 3 (batch のみ・同一 build) | 360 | 230 | 210 |

- 件数は 3 回とも一致 (360 / 230 / 210)。これは**件数のみの達成**。関数単位の判定が変わったかは**未検証**: 関数ごとの verdict を記録した TSV が無く、件数が同じでも内訳の入れ替わりを排除できない。全 800 件の verdict TSV と比較手順は素材 `work-m11` `work-liftdiff` の再取得後に commit する (未解決の起票先は下表)。§4 の 361 / 360 / 361 の揺れは本 HEAD では件数の再現に留まる。
- 結論: 揺れの原因は**特定不能** (再現せず)。§4 の「native timeout・負荷による揺らぎ」は推定のまま。揺れの再現条件 (負荷・shard 配置) は未確認。
- 測定結果: `results/ld32_m11_sample800_n3_c4e93550.txt` (commit 済み)。

### 7.3 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 8 関数の命令単位 trace (native と wasm の各 step) による機序の確定 | §7.1 は観測と推定の段階 | 本 PR 後に子 issue (LD-32 の残り) |
| m11 sample:800 の 361 ↔ 360 の再現条件 | 本 HEAD では n=3 で再現せず | 同上 |
