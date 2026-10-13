# liftdiff REPORT 付録: OTT 旧 chain の前回比差分の切り分け (LD-16 / #825・LD-31 / #1069)

本書は `REPORT.md` §10 の要約の全文。親 issue #406 / PR #802 の前回比差分の追跡。

## 結論

- 前回比の基準は、同一 HEAD で n=3 採点した値 (min–max)。過去の報告値 (38/108/66・33/110/69) は基準にしない。`59eea5c` の 38/108/66 は旧基準・報告値で、比較の参照点にとどめる (生ログ commit 済み・下記)。
- 参考: 旧基準 `59eea5c` (38/108/66) から、`origin/main` c4e93550 = 35/112/65 (38→35)。このうち `ldlib/cases.py` だけで 38→40 が再現する (main 全体では 40 でなく 35)。
- 基準の決定 (PM 判断 #1069, 2026-10-14): 『同一 HEAD で n=3 回採点した値 (集計 min–max)』。
- 訂正 (LD-31): 旧版 LD-16 付録の基準値 (訂正前の報告値) と、それに基づく切り分け (ld_native.c 計時の寄与・関数単位の表) は再現せず無効。本書から削除した (旧版は git 履歴に残る)。
- 生ログ: 本節末尾の「生ログの根拠」を参照。

## 1. 実測値

| commit | 回 | 集計 (一致 / 不一致 / 実行不能) | D1 / D2 / D3 / D4_D5 / D6 | 根拠 |
|---|---|---|---|---|
| `59eea5c` (前回比の基準) | 3 | 38 / 108 / 66 (3 回同一) | 4 / 6 / 14 / 18 / 26 | 生ログ `results/ott_ld31_n3_c59eea5c_n{1,2,3}.log` |
| `origin/main` c4e93550 | 3 | 35 / 112 / 65 (3 回同一) | 4 / 6 / 14 / 20 / 26 | 生ログ `results/ott_ld31_n3_cmain_n{1,2,3}.log` |
| HEAD 4716440c (`ldlib/`・`rt/` は main と差分 0) | 3 | 35 / 112 / 65 (3 回同一) | 4 / 6 / 14 / 20 / 26 | 生ログ `results/ott_ld31_n3_head_n{1,2,3}.log`。`986e7415` の既存ログ `results/liftdiff_e2e_head986e7415_n{1,2,3}.log` も 35/112/65 |
| `59eea5c` + main の `ldlib/cases.py` のみ | 3 | 40 / 110 / 62 (3 回同一) | — | 生ログ `results/ott_ld31_n3_cases59_n{1,2,3}.log` |

測定方法 (全行共通): wasm は素材 `work-liftdiff` 同梱の凍結 snapshot (`work/ott_old/ld_wasm.wasm`) を使い、`ld_native` は各 commit の `rt/` から再ビルド。`batch --set closure` (212 関数) → `check_ott.py`。wasm 側は 3 commit で同一のため、差はすべて liftdiff 側 (`ldlib/`・`rt/`) の違いに由来する。wasm を各 commit で再 build した測定ではない (emsdk の runner 未導入)。

- 前回比は、同一 run で測った基準側 n=3 と変更側 n=3 の組で行う (PM 判断 #1069)。旧基準 59eea5c (38/108/66) は参照点のみ。
- 検証の途中で、`work/` の展開直後の `liftdiff.py build` が `sigs.json` (212→178 関数) を書き換えた事故があった。素材 tar から `sigs.json`・`batch.jsonl` を戻し直した後の測定のみ採用する。

## 2. ファイル単位の差し替え (未実施)

- `ldlib/cases.py` 単独 (main 版) で 38→40 が n=3 で再現 (生ログ commit 済み)。main 全体 (35) は cases.py 以外の変更 (`ldlib/compare.py`・`classify.py`・`pe.py`・`session.py`・`rt/` 等) を含み、その寄与は未切り分け。

## 3. 関数単位の突合 (未実施)

- 関数単位の差分 (`tests/ott_delta.py`) は、再計算した `batch.jsonl` が揃った後に行う。本 run では未実施。

## 4. n=3 の非決定性

- OTT 集計 (`check_ott.py`): `59eea5c`・main・HEAD・`cases.py` 単独版は各 3 回同一 (生ログ commit 済み)。`986e7415` は 3 回同一 (既存ログ)。
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
- 前回比の運用 (PM 判断 #1069): 基準側 (main の HEAD) と変更側を同じ run で n=3 採点し、生の `OTT_SUMMARY` 行を `results/` に commit して REPORT から参照する。生ログの無い数値は「報告値」と明記する。

## 6. 検証の範囲・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| main 全体 (match 35) と `cases.py` 単独 (match 40) の差の原因 (cases.py 以外の main 側変更) の切り分け未実施 | 38→35 の機序が未特定 | #1069 ([LD-31]) |
| wasm を各 commit で再 build していない (凍結 snapshot 使用・emsdk 未導入) | 3 commit の wasm 側差分は未測定 (liftdiff 側差分のみ) | #1069 ([LD-31]) |
| 関数単位の tag 変化の機序 (vm0/u16 pattern の効果) は未確認 | pattern 追加の効果の説明が推定止まり | #1070 ([LD-32]) |
| m11 sample:800 の 1 件揺れの関数特定 | 非決定性の出所が未特定 | #1070 ([LD-32]) |
| 素材の展開・python 依存 (`numpy capstone pefile`) は run ごとに必要 | 素の runner で e2e が exit 2 | 既に REPORT_APPENDIX §10 の未解決 (agent-setup) |

## 生ログの根拠

すべて `results/` に commit 済みの生ログ (`OTT_SUMMARY` 行を含む)。

- `results/ott_ld31_n3_c59eea5c_n{1,2,3}.log`: 59eea5c の n=3
- `results/ott_ld31_n3_cmain_n{1,2,3}.log`: origin/main (c4e93550) の n=3
- `results/ott_ld31_n3_head_n{1,2,3}.log`: HEAD 4716440c の n=3
- `results/ott_ld31_n3_cases59_n{1,2,3}.log`: 59eea5c + main の `cases.py` の n=3
- `results/liftdiff_e2e_head986e7415_n{1,2,3}.log`: 986e7415 の n=3 (LD-16 時の既存ログ)

## 7. LD-32 (#1070): 8 関数の機序 (パターン単位の観測) と m11 sample:800 の n=3

測定: `c4e93550` (main 取り込み時点の HEAD)・Actions runner (4 vCPU・load 1 分平均 1.5〜6.9)。`bash tools/liftdiff/liftdiff_e2e.sh` は exit 0・`LIFTDIFF_E2E PASS`・所要 約 3 分 (本 run 1 回目)。素材の根拠: 測定 run のログ `results/liftdiff_e2e_ld32_head_c4e93550_n1.log` の 118〜123 行に `[4/4] M11 closure 差分バッチ (sample:800)` の実行と 800 件の集計 (360/230/210) が出ており、m11 chain はこの run で実行された。**素材の一覧はこの測定 run では記録していない**。後続の fix run (`ed2b5cd2`〜) の `$ARTIFACTS_DIR` には `fl-win64` のみあり、`work-m11` `work-liftdiff` `work-m6-ott` `analysis-ott-binaries` は無い (PR 本文の「素材」行と一致)。OTT 集計 35 / 112 / 65 は §1 の `986e7415` と一致 (D1〜D6 = 4/6/14/20/26)。ログは `results/liftdiff_e2e_ld32_head_c4e93550_n1.log` (commit 済み)。

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
| 1 (e2e 内 [4/4]) | 360 | 230 | 210 | ログあり (`liftdiff_e2e_ld32_head_c4e93550_n1.log` 123 行) |
| 2 (batch のみ・同一 build) | 360 | 230 | 210 | **報告値・ログ無し** (commit されたログも verdict も無い) |
| 3 (batch のみ・同一 build) | 360 | 230 | 210 | **報告値・ログ無し** (同上) |

- run2・run3 は一次ログが commit されておらず、件数は報告値として扱う。確認できるのは run1 (e2e ログ) のみ。
- 件数は 3 回とも一致 (360 / 230 / 210)。これは**件数のみの達成**。関数単位の判定が変わったかは**未検証**: 関数ごとの verdict を記録した TSV が無く、件数が同じでも内訳の入れ替わりを排除できない。全 800 件の verdict TSV と比較手順は素材 `work-m11` `work-liftdiff` の再取得後に commit する (未解決の起票先は下表)。§4 の 361 / 360 / 361 の揺れは本 HEAD では件数の再現に留まる。
- 結論: 揺れの原因は**特定不能** (再現せず)。§4 の「native timeout・負荷による揺らぎ」は推定のまま。揺れの再現条件 (負荷・shard 配置) は未確認。
- 測定結果: `results/ld32_m11_sample800_n3_c4e93550.txt` (commit 済み)。

### 7.3 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 8 関数の命令単位 trace (native と wasm の各 step) による機序の確定 | §7.1 は観測と推定の段階 | 本 PR 後に子 issue (LD-32 の残り) |
| m11 sample:800 の 361 ↔ 360 の再現条件 | 本 HEAD では n=3 で再現せず | 同上 |

## 8. LD-32 (#1070) 追補: 揺れの特定と 8 関数の trace (測定 commit 604e900f)

既知類型との関係: 該当なし (揺れは wasm 側の vm timeout 境界の分類差で、`docs/DEFECTS.md` の D1a〜D20 のいずれにも当たらない。8 関数の欠陥は既存類型 D1・D3・D4_D5・D6 (`check_ott.py` の集計) と `wasm_trap` / `m8_fail` の原因特定に分かれ、後者は未特定)。

測定: `604e900f` (origin/main)・Actions runner (4 vCPU・load 1 分平均 0.9〜5.9)。素材は `fl-win64` `work-m6-ott` `work-m11` `work-liftdiff` `work-liftlib` `analysis-ott-binaries` `toolchain-emsdk` を展開 (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`ANALYSIS_DIR=$HOME/analysis`)。

### 8.1 e2e

- `bash tools/liftdiff/liftdiff_e2e.sh` 2 回目 (本測定): exit 0・`LIFTDIFF_E2E PASS`・所要 203.99 s (3 分 24 秒)。ログ `results/liftdiff_e2e_ld32b_604e900f_n1.log`。
- OTT 集計 35 / 112 / 65 (D1〜D6 = 4 / 6 / 14 / 20 / 26)。§1 の `986e7415`・`c4e93550` の値と一致。
- m11 sample:800 集計 360 / 230 / 210 (`[4/4]`)。
- 1 回目 (`results/liftdiff_e2e_ld32a_604e900f_failed_fl_path.log`) は `FL_WIN64_DIR` に `extracted` を含めた誤設定で [3/4] が `FileNotFoundError` で失敗。環境設定の誤りで、リポジトリの不具合ではない。

### 8.2 m11 sample:800 の n=3 (関数単位)

- batch 3 回 (r1 = e2e 内 [4/4]、r2・r3 = `liftdiff.py batch --set sample:800 --shards 12`)。件数は 3 回とも 360 / 230 / 210。
- 関数単位の突合: `tests/ld32_verdict_cmp.py`。verdict が変わった関数は **0 件**。case outcome だけが変わった関数は 3 件。結果は `results/ld32_m11_sample800_verdict_n3_604e900f.tsv`。

| 関数 | verdict (r1/r2/r3) | 揺れた pattern (r1 \| r2 \| r3) | 揺れの型 |
|---|---|---|---|
| 0x5c5500 | unexec ×3 | fvm: hang \| both_fault \| both_fault、p01・p1・qall・u16 も同様 | wasm 1000 ms 打切り (`timeout`) と wasm の完走 (`trap`) の境界 |
| 0x67e2b0 | mismatch ×3 | s: both_fault \| hang \| hang | 同上 |
| 0x903d50 | match ×3 | s: hang \| native_fault \| native_fault | 同上 (r1 のみ wasm 打切り) |

- 揺れの分類: **wasm 側の vm timeout (`wasm_timeout_ms` 既定 1000 ms) の境界**。同じ case が、ある run では `wasm=timeout`、別の run では `wasm=trap` か `wasm=ok` になる。判定への影響は `hang` と `both_fault` / `native_fault` の入れ替わりだけで、match・mismatch・unexec の区分は変わらない。
- 根拠: 揺れた case はすべて `wasm_status=timeout` を含む `hang` と、同じ case の別 run の `trap` / `ok` の組。native 側の `timeout` (SIGALRM) は揺れ 3 関数では出ていない (0x903d50 p0 は 3 回とも native timeout で固定)。
- 推定 (未検証): 打切りの境界に乗るのは負荷 (並列 shard 数 12 と runner の load 1 分平均 0.9〜5.9) による wasm 実行時間の揺れ。wasm の実行時間は本 run の batch 出力では測っておらず、直接の確認は未実施。
- 限界: 揺れの原因の確定 (wasm の実行時間の実測) は #1313 の範囲。

### 8.3 8 関数の pattern 単位の trace

- `liftdiff.py run targets/ott_old.json --fn <8 関数> --pattern z,s,p0,p1,p01,pall,u16,vm0,qall --nobuild` (`results/ld32_ott8_pattern_604e900f.log`)。`--verbose` で entry 単位の trace を取った結果は `results/ld32_ott8_trace_604e900f.log`。
- 機序の要点 (entry 単位の trace で確認した範囲):
  - 1801ab1d0・1801ab258: p0・p1 で native が segv (rdi/rax に 0x7e 等の乱数値)。vm0・u16 では両側が正常終了し equal。
  - 1801ab3ec: vm0・u16 でも native segv が続く (rip 0x1ab420・0x1ab437)。構造 blob では解消しない。
  - 1801c5e84・1801c621c・1801c69cc: 3 関数で `HeapFree` を呼ぶ call 順序が分岐。wasm 側は `function_1801baef8` (未解決 callee) を呼び、`ret` が `0x1` と `0x0` で不一致。u16 では wasm 側で `HeapFree` 内の OOB trap。
  - 1801c67a0: wasm 側の `m8_fail` → `abort` が vm0・u16 で trap。native は `ok` (vm0・u16)。p0 では native segv と wasm trap の両方。
  - 1801c682c: vm0・u16 で `callsite_arg_drop` (`HeapFree` の第 1 引数 0x5 が wasm で 0x0)。
- **命令単位 trace (native と wasm の各 step) は未取得**。entry・call の単位まで。よって受入条件 1 は未達。残りは #1313 (LD-44)。

### 8.4 受入条件の判定

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| 1. 8 関数の機序を関数単位の trace で示す | **未達** (entry・call 単位まで) | §8.3。命令単位 trace は #1313 |
| 2. sample:800 の揺れ 1 件の関数特定と分類 | 達成 (件数揺れは無し・case 揺れ 3 関数を特定、分類は wasm timeout 境界) | §8.2・`results/ld32_m11_sample800_verdict_n3_604e900f.tsv` |
| 3. n=3 の結果と分類を REPORT に記録 | 達成 | §8.1・8.2。r2・r3 のログを `results/` に commit |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 8 関数の命令単位 trace による機序の確定 | §8.3 は entry・call 単位 | #1313 ([LD-44]) |
| wasm 1000 ms 打切り境界の揺れの原因 (wasm の実行 ms の実測) | §8.2 の分類は推定 | #1313 ([LD-44]) |
