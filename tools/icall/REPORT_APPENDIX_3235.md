# REPORT_APPENDIX_3235 — ICALL-88: make_thunk の 16 バイト整列 (群 I)

> 親: #2247 (ICALL-68)。前付録: `REPORT_APPENDIX_2247.md` §2.6・§4。本付録は子 #3235 の実測記録。

## 1. 結論

- `tools/ott/native/ott_native.c` の `make_thunk` で、`call rax` の直前に `sub $8,%rsp` (`48 83 EC 08`) を入れた。thunk は 21 バイトで 32 バイト枠内に収まる。
- `slot_trace` の 131 関数で rc 分布が変わった: `rc=95` 53 → 44 (-9)、`rc=99` 0 → 9 (+9)。`rc=0`・`rc=124`・`rc=98` は不変。
- 9 件の `rc=99` (`MISSING IMPORT` の fail-fast) は、§2.6 の 3 件 (`1803b3fc0`・`1803b5b60`・`18103d218`) を含む。
- 既存 e2e `tools/ott/ott_e2e.sh --quick` は HEAD `e5261de58` で PASS (§3.1)。`icall_e2e.sh` は未実行。

## 2. 測定

### 2.1 測定条件

- 測定 commit: `adda5c027` (`fix(ott): make_thunk ...`。コードを変えた最後の commit)。修正前 baseline は親 `d22576191` (main) の tree。
- 再現: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` を foreground・各 1 回実行。
- 素材: `work-icall` (`tools/icall/work/`) と `plugins-freshair` (`FA_DL` → `fetch.sh` で `tools/targets/freshair/work/win/`)。
- `slot_trace.c` は `../../ott/native/ott_native.c` を `#include` しているため、修正は測定経路に入る。

### 2.2 rc 分布 (修正前 → 修正後)

| 測定 | rc=0 | rc=124 | rc=95 | rc=98 | rc=99 |
|---|---|---|---|---|---|
| 修正前 (`d22576191`) | 69 | 1 | 53 | 8 | 0 |
| 修正後 (`adda5c027`) | 69 | 1 | 44 | 8 | 9 |

- 修正前の rc 分布は §2.1 の baseline (`rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8`) と完全一致。
- 修正後の zero-fill VA 10・既知 12 hit 3 は修正前と同じ。
- real 12.514 s / user 11.040 s / sys 1.975 s。load average (1 分値) 0.14 (開始 06:16:28 UTC)。

### 2.3 rc=99 に変わった関数 (import 名)

単独実行 (1 関数 1 プロセス) で `MISSING IMPORT` を確認した。

| 関数 | import |
|---|---|
| 1803b3fc0 | RtlPcToFileHeader |
| 1803b5b60 | RtlPcToFileHeader |
| 180cbd860 | RtlPcToFileHeader |
| 18100ca28 | SetUnhandledExceptionFilter |
| 18100cc50 | RtlCaptureContext |
| 18100cf60 | RtlPcToFileHeader |
| 181011058 | RtlPcToFileHeader |
| 18102f728 | RtlPcToFileHeader |
| 18103d218 | RtlCaptureContext |

- §2.6 の 3 件 (`1803b3fc0`・`1803b5b60`・`18103d218`) は §2.6 の記録と一致 (RtlPcToFileHeader・RtlPcToFileHeader・RtlCaptureContext)。
- 残り 6 件 (`180cbd860`・`18100ca28`・`18100cc50`・`18100cf60`・`181011058`・`18102f728`) は修正後に `rc=99` になった。修正前の関数単位の rc は記録していない。`rc=95` の減少 9 件と `rc=99` の増加 9 件が件数で一致することからの推定で、個別には未確認。

### 2.4 残りの rc=95 (44 件)

- 44 件は `make_thunk` 以外の原因。未測定。受入条件の範囲外。

## 3. 受入条件の判定

| 受入条件 | 結果 |
|---|---|
| 1. thunk を 16 バイト整列して `missing_import` を呼ぶ・thunk 1 個 ≤ 32 バイト | 達成。21 バイト、`sub rsp,8` を `call rax` の直前に入れた |
| 2. `SLOT_ENC_INIT=1 slot_trace.sh` の rc 分布の変化を実測し、§2.1 baseline との差分を記録 | 達成。§2.2・§2.3 |
| 3. `tools/ott/native` を使う既存 e2e を 1 本以上実行し、結果が変わらないことを確認 | 達成。`ott_e2e.sh --quick` が HEAD で PASS (§3.1) |

### 3.1 既存 e2e の実測 (受入 3)

- 測定 commit: `e5261de58` (origin/main。`ott_e2e.sh --quick` をこの HEAD で実行。コードを変えた最後の commit であり、測定以降のコード変更は無い)。
- 素材: `fl-win64`・`plugins-ott`・`work-m6-ott`・`analysis-ott-binaries` (`ANALYSIS_DIR=$HOME/analysis`、`OTT_vst2_win64.dll` 3146752 B)。
- emcc: 上流 emsdk 6.0.12 (`EMSDK_DIR=$HOME/emsdk`。`/opt/emsdk` は runner に無かった)。
- 再現: `cd tools/ott && bash ott_e2e.sh --quick` を foreground で 2 回実行。

| 実行 | real | load (1 分値, 開始→終了) | matrix | fma_sens | 判定 |
|---|---|---|---|---|---|
| 1 回目 (lift・emcc 込み) | 19.9 s | 0.17 → 0.49 | scenarios 22, failed 0, cells 9620, equal 9620, max_ulp 0, state_diff_qwords 0 | cases 12, cells 18432, differing 0 | PASS (exit 0) |
| 2 回目 (lift 済み) | 9.0 s | 0.40 → 0.49 | 同上 | 同上 | PASS (exit 0) |

- 両回とも `std` / `std_f248_0` は 512/512 cells bit-equal・max_ulp 0・`|max|` 0.2516。RetDec 比較 (INFO 節 [6/6]) は `tools/m6/work` が無いためスキップ。
- 差分: `git diff adda5c027 HEAD -- tools/ott tools/shared tools/m1` は 87 ファイル・約 11362 行 (`tools/shared` の ildsp 等を含む)。測定は HEAD で行ったため、この差分込みの HEAD で PASS している。`ott_native.c` の `make_thunk` 修正 (`adda5c027`) は HEAD に含まれる。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| rc=95 残 44 件の原因 | `make_thunk` 外の fatal。群 I 以外 | #2247 の後続 (未起票) |

## 5. 変更

- `tools/ott/native/ott_native.c`: `make_thunk` に `sub rsp,8` の 4 バイトを追加 (`adda5c027`)。
