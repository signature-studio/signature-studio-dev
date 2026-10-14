# M11 shimx_link 付録 (#179 SHX-T6): 旧 main の link 失敗の修正と `--midi` の winstubs 結線の実測

REPORT.md §11 の全文 (250 行上限のため分割移動。本体からは削除し、ここへ移した)。

## 11. 旧 main の link 失敗の修正と `--midi` の winstubs 結線 (#179 SHX-T6)

- 測定 commit: `397c4161` (コードを変えた最後の commit。以後は本節のみ)。修正前: `46c92356` (main)。
- 差分: `git diff 46c92356 397c4161 -- tools/m11/shimx_link` は `build.sh` のみ (EXPORTS の sxt_* 分離と usage 注記)。
- main 取り込み: 同じ EXPORTS 修正は #2732 (`e7491b4f`、§10.3) で main に入り済み。main 取り込みの競合では測定済みの本節の `build.sh` を残した (意味は同じ。書式は `if ...; fi` と `[ $TRACE = 1 ] &&` の違いのみ)。
- 差分確認 (測定 commit から取り込み merge 後の HEAD まで・コード範囲): `git diff 397c4161 HEAD -- tools/m11/shimx_link ':!*.md'` の出力は 0 行 (再測定は不要)。

### 11.1 旧 main で全 variant の link が失敗していた原因

SHX-T9f (`7e9940ac`) で基底の EXPORTS に `_sxt_*` を入れたが、`sxt_*` の定義は `trace_rt.c` (`--trace` でだけリンク) にしか無い。emcc 6.0.12 は未定義の exported symbol を error (`-Werror`) にするため、plain を含む全 variant が `emcc: error: undefined exported symbol: "_sxt_count"` で rc 1 になっていた。
修正: `sxt_*` の export を `TRACE=1` のときだけ付ける (trace 側の export 集合は従来と同一)。

| variant | 修正前 (46c92356) | 修正後 (397c4161) |
|---|---|---|
| 既定 `build.sh` | rc 1 (`_sxt_count`) | rc 0 / 3 s / mismatch 1 / undefined 0 / dup 0 |
| `--midi` | rc 1 | rc 0 / 3 s / mismatch 1 / undefined 0 / dup 0 |
| `--ws --midi` | rc 1 | rc 0 / 2 s / mismatch 1 / undefined 0 / dup 0 |
| `--soft --fix --ws` | 未計測 (基底 EXPORTS 行が同一のため同じ原因) | rc 0 / 3 s / mismatch 1 / undefined 0 / dup 0 |
| `--soft --fix --ws --midi` | 未計測 (同上) | rc 0 / 3 s / mismatch 1 / undefined 0 / dup 0 |
| `--trace --soft --fix` | 未計測 (export 集合は同一) | rc 0 / 4 s / mismatch 1 / undefined 0 / dup 0 |

mismatch 1 は `midiOutShortMsg` (i64 呼出 vs i32 定義) で、既定 variant と同数。本変更由来ではない (§19.9 と同じ既知項目)。

### 11.2 e2e (HEAD `397c4161` で foreground 実行、load 0.24→0.49)

| 検証 | コマンド | 結果 |
|---|---|---|
| midi 結線 (plain, fix 無し) | `node midi_e2e.mjs m11_sx_plain_failfast_midi.cjs` | ALL PASS (3/3。`sx_midi_probe_numdevs(3)` = 3、n_out=0 で 0) |
| midi 結線 (winstubs 結線あり) | `node midi_e2e.mjs m11_sx_plain_failfast_ws_midi.cjs` | ALL PASS (3/3) |
| midi 結線 (winstubs + fix + soft) | `node midi_e2e.mjs m11_sx_plain_soft_fix_ws_midi.cjs` | ALL PASS (3/3) |
| winstubs gate (fix + soft、`--midi` 無し) | `node ws_e2e.mjs m11_sx_plain_soft_fix_ws.cjs` | PASS 19 / FAIL 0。BOOT init_count 18 / units_run 17/942 / threw=memory access out of bounds |
| winstubs gate (fix + soft、`--midi` 有り) | `node ws_e2e.mjs m11_sx_plain_soft_fix_ws_midi.cjs` | PASS 19 / FAIL 0。BOOT は上と同一 (18 / 17/942) |
| trace 実行 | `node run_trace.mjs m11_sx_trace_soft_fix.cjs` | rc 0。`SXL_RESULT` に init 18 / units_run 17 / trace wrappers 356 |

- `ws_e2e.mjs` の BOOT 基準 (18 / 17) は `--fix` 系で測る (§10.1)。fix 無しの `--ws` / `--ws --midi` は unit 15 で abort する (alloca 縮退の既知問題。両者同一)。
- boot 統計 (`BOOT_WS_STATS`, `--midi` 有無で同一): cpuid 8、find_window 0、createprocess 0、loadlib_miss 0。**最初のウィンドウは作られていない** (find_window 0)。

### 11.3 起動 KPI の前後 (PR 本文用)

- 修正前: 当該 closure は link 不能 (boot 到達点は測れない)。修正後: `--soft --fix --ws` / `--soft --fix --ws --midi` とも units_run 17/942、init_count 18、最初のウィンドウ無し。
- flelift boot の dispatch 数 / unit 数 (`tools/flelift/boot/REPORT.md`) は本変更の対象外で、動かしていない。

### 11.4 残件

- 本番 FL 経路 (FL 実機・headless Chrome の `midiOutGetNumDevs` 結線・`midiOutShortMsg` の引数幅) は未検証。#37 (AU-14)。
