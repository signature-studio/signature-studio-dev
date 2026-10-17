# #1064 (LD-29): 旧 F3c-block の誤修復 12 関数 (門で除外) の wasm・liftdiff による動的確認

**判定: 部分達成**。受入条件 2・3 は達成。受入条件 1 は unit 単位の survey 差分の記録まで (12 関数への対応付けは未了・§4)。

## 1. 測定条件

- 測定 commit: `cb3a89a6` (origin/main。本 run のコード変更は 0。追加は本 REPORT のみ)。
  `git diff cb3a89a6 HEAD -- tools/m11 tools/liftdiff` = 0 行 (本 REPORT のコミット前後で実行コードに差分なし)。
- 素材: fl-win64 (`block00031_PE.bin`)・toolchain-emsdk ([EMSDK])・work-m11 (`tools/m11/work/`)・work-liftdiff (`tools/liftdiff/work/`)。toolchain-retdec は未使用。
- 比較の両側 (同一 HEAD・同一 PE・同一 image):
  - 旧版 = `ldfix.py` 009e823 の出力 (`prev.ll`)。12 関数の誤修復を含む。
  - 新版 = HEAD の `ldfix.py` の出力 (`new.ll`)。12 関数の修復を門で外した版。

## 2. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 1. 12 関数の修復前後 wasm の survey (unit ごとの trap / halt0 差) を記録 | **部分**。unit 単位の差分は実測 (§3.1)。unit → 12 関数の対応付けは未実施 (§4) |
| 2. 到達する関数の liftdiff 突合 (min–max、n≥3) | **達成** (§3.2。3 回反復・両側とも一致) |
| 3. 修復の有無で結果が変わる関数の一致判定 | **達成** (§3.2。該当 0 件。判定は両側で同一) |

## 3. 実測

### 3.1 e2e (`ldfix_509_e2e.sh`、foreground 1 回、rc=0)

- 所要 5 分 18.8 秒 (real 318.8 s)。load average 0.74 (開始) / 1.44 (終了)。`nproc` = 4。
- 旧版/新版で本体が異なる関数: 838 / 7421。F3c 関数: 旧 16 → 新 36 (旧の全てを含まない)。
- survey (942 unit): 修復前 wasm と修復後 wasm で `ok` 退行 unit 0。kind 含む差分 unit 12 件 `[144, 158, 280, 291, 296, 302, 304, 314, 493, 659, 888, 895]`。
  判定分布 A (修復前) `ok 868 / miss 47 / halt0 8 / oob 17 / other 1 / noproc 1`、B (修復後) `ok 870 / miss 47 / halt0 7 / oob 16 / other 1 / noproc 1`。
- dyn_509 (7/7): 修復前 FAIL 5/5、修復後 PASS 5/5 (`DYN_SUMMARY after_fail=0/5`)。
- reach_509: 計装 26 関数のうち実行されたのは 4 関数 (41a670・409c80・40ffe0・447ee0)。12 関数のうち到達したものは無し。
- ネガティブコントロール (step 5): NC:nc_store で 806740 が SUSPECT に戻る。NC:nc_use で 1063090 が use 形に戻る。

### 3.2 liftdiff (12 関数、target = `$RUNNER_TEMP/t_{new,base}.json`)

target は `tools/m11/ldfix/targets/m11_ldfix.json` を、`ir` だけ旧版 / 新版の IR に差し替えて作った (`initial_memory` 671088640 は `tools/liftdiff/targets/m11.json` に合わせた)。
build は両側 OK (`wasm_size` 3942491 / 3942318、`sig_mismatch` 0)。`liftdiff.py run --fn <12 関数>` を 3 回反復。

| 関数 | 旧版 (3 回) | 新版 (3 回) | 修復の有無で変化 |
|---|---|---|---|
| 5c1030 | unexec (native_fault_all_patterns) | unexec | なし |
| 607b90 | match | match | なし |
| 6088a0 | mismatch (`icall_drop`・native rax 0x5 / wasm 0x6088a0) | mismatch | なし |
| 60f010 | match | match | なし |
| 6214a0 | match | match | なし |
| 737d10 | unexec | unexec | なし |
| 73b300 | match | match | なし |
| 7cbc20 | match | match | なし |
| 7ff6e0 | unexec | unexec | なし |
| 840720 | match | match | なし |
| d243c0 | unexec | unexec | なし |
| e404e0 | match | match | なし |

- 3 回とも同一判定 (min–max: 各関数で変動なし)。両側の case 行も判定行と同一 (差分は build の出力パスとサイズのみ)。
- 6088a0 の mismatch は旧版・新版とも同一で、タグは `icall_drop` (機械語の間接 call/jmp=1 に対し IR の間接 call=0)。修復の有無とは独立。原因の詳細分類は未実施。
- unexec 4 件 (5c1030・737d10・7ff6e0・d243c0) は native が全パターンで segv。native 側が実行不能のため、wasm との突合はできない。

### 3.3 再測定 (#1594・計装 FNS に修復 12 関数を追加・測定 commit `f99878d09`)

- 測定 commit: `f99878d09` (`ldfix_509_e2e.sh` の `FNS` に 12 関数を追加。他は不変)。`git diff f99878d09 HEAD -- tools/m11 tools/liftdiff` は 0 行。
- `ldfix_509_e2e.sh` を foreground 1 回: rc=0、load 1.27 (終了時)。計装は 26 → 38 関数。
- DYN_SUMMARY after_fail=0/9。survey の差分 unit は、正規化後で `[17 114 144 158 280 291 296 302 304 314 492 493 659 880 888 895]` の 16 件。REPORT §3.1 の 12 件とは一致しない (`144 158 280 291 296 302 304 314 493 659 888 895` は再現、`17 114 492 880` は新規、`base → new` の kind 変化を含む)。
- 12 関数の入口通過: 5c1030 のみ 1 unit (114、3 回)。残り 11 関数は 0 unit。計装 38 関数のうち実行されたのは 41a670・409c80・40ffe0・447ee0 と 5c1030 の 5 関数。
- 差分 unit と hit の突合: 差分 unit のうち 12 関数の hit を持つのは unit 114 (`halt0`→`halt0`、kind 不変) のみ。他の差分 unit (144・158・280・291 等) は 12 関数に一切到達しない。よって「修復 12 関数 → 差分 unit」の対応は、この測定では確立できない。
- 結論: 受入条件 1 は未達。12 関数の修復が差分 unit を生んだという証拠は無い。差分の原因は未確定 (修復で本体が変わった 857 関数の経由などが候補だが、本測定では確認していない)。

## 4. 未解決・限界

| 未解決 | 影響 | 起票先 |
|---|---|---|
| survey の unit 差分 12 件 (`144 158 280 291 296 302 304 314 493 659 888 895`) を 12 関数へ対応付けていない | 受入条件 1 の「12 関数ごとの」記録が未完 | #1594 [LD-56] |
| unexec 4 件 (5c1030 / 737d10 / 7ff6e0 / d243c0) の native 実行環境 | wasm との突合ができない | #1594 [LD-56] |

追記 (#3088): 上の unexec 4 件 (5c1030 / 737d10 / 7ff6e0 / d243c0) は、native 実行条件を整えて突合済み (`REPORT_3088.md` §3.3)。本表の値は cb3a89a6 時点のまま。

## 5. 再現

```sh
EMSDK_ENV=<[EMSDK] の emsdk_env.sh> FL_WIN64_DIR=<fl-win64 展開先> M11_WORK=<tools/m11/work> \
  bash tools/m11/ldfix/ldfix_509_e2e.sh
# liftdiff: t_new.json / t_base.json (ir のみ差し替え) で
python3 tools/liftdiff/liftdiff.py build <t>.json
python3 tools/liftdiff/liftdiff.py run <t>.json --fn 5c1030,607b90,6088a0,60f010,6214a0,737d10,73b300,7cbc20,7ff6e0,840720,d243c0,e404e0
```

成果物: `$RUNNER_TEMP/ldfix_509_e2e/` (`sv_base.json` / `sv_new.json` / `reach.json` / `build_*.log`)、`$RUNNER_TEMP/{n,b}{1,2,3}.log` (liftdiff 反復)。
