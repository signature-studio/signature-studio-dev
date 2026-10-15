# tools/audio/asio — AU-47 (#4593) callback 区間の内訳計装 付録

親: [REPORT.md](REPORT.md) §8 / #3757 ([REPORT_APPENDIX_3757.md](REPORT_APPENDIX_3757.md))。

## 1. 計装

`tools/audio/src/flasio.c` の `do_buffer` で 4 区間の最大 µs を記録する (判定は変えない)。

| 区間 | 計測範囲 |
|---|---|
| `in_read` | `fla_in_read` |
| `memset` | 出力バッファの `memset` |
| `bufferswitch` | `t0`〜bufferSwitch 本体終了 (`cb_max_us` と同区間) |
| `out_write` | `fla_out_write` |

- 保持先: `A.seg_max_us[4]` (flasio.c の静的状態)。`flasio_get_stats` で `flasio_stats_t.seg_max_us[4]` に出す。
- 統計リセット (prefill 後) で他の cb 統計と同じく 0 に戻す。
- 結果 JSON: `com_test.c` の `stats` 直下ではなく、`seg_max_us` 名前空間 (`{"in_read","memset","bufferswitch","out_write"}`) で出す。
- **`fla_ctl_t` (共有 SAB 構造体) には入れていない**。`audio-layout.ts` とのオフセット突合 (fail-fast) を避けるため。issue 本文の「`fla_ctl_t` に記録」からの逸脱。

## 2. 測定 (HEAD 604f9d5dd の作業ツリー・計装 commit 前後で実測)

測定コマンド: `node tools/audio/asio/harness/run_com.mjs --only com_ramp_b256_d2`
(build: `bash tools/audio/asio/build.sh`)。判定は `underruns` / `silence_frames` / ramp mismatch の既存基準。

### 2-1. 作業ツリー (計装 commit 前の作業状態) で 20 回

| 回 | underruns | silence | ramp mismatch | in_read | memset | bufferswitch | out_write |
|---|---|---|---|---|---|---|---|
| r01 (初回) | **1** | **4608** | **210560 / 240512** | 90 | **126665** | 64 | 10 |
| r02 | 0 | 0 | 0 | 1520 | 484 | 50 | 15 |
| r03 | 0 | 0 | 0 | 25 | 50 | 479 | 104 |
| r04 | 0 | 0 | 0 | 40 | 1885 | 479 | 10 |
| r05 | 0 | 0 | 0 | 45 | 485 | 104 | 10 |
| r06 | 0 | 0 | 0 | 25 | 104 | 500 | 20 |
| r07 | 0 | 0 | 0 | 34 | 15 | 40 | 10 |
| r08 | 0 | 0 | 0 | 35 | 15 | 40 | 10 |
| r09 | 0 | 0 | 0 | 90 | 20 | 755 | 40 |
| r10 | 0 | 0 | 0 | 10 | 50 | 84 | 14 |
| r11 | 0 | 0 | 0 | 30 | 50 | 9944 | 10 |
| r12 | 0 | 0 | 0 | 475 | 89 | 54 | 49 |
| r13 | 0 | 0 | 0 | 24 | 15 | 44 | 95 |
| r14 | 0 | 0 | 0 | 50 | 14 | 480 | 10 |
| r15 | 0 | 0 | 0 | 24 | 20 | 505 | 20 |
| r16 | 0 | 0 | 0 | 25 | 24 | 44 | 114 |
| r17 | 0 | 0 | 0 | 20 | 20 | 50 | 479 |
| r18 | 0 | 0 | 0 | 14 | 10 | 40 | 10 |
| r19 | 0 | 0 | 0 | 99 | 459 | 50 | 15 |
| r20 | 0 | 0 | 0 | 489 | 20 | 44 | 20 |

単位は µs。`seg_max_us` は区間ごとの最大値 (1 回の run 内での最大)。

- 20 回中 FAIL は **1 回 (r01)**。その他 19 回は underrun 0・ramp 0 mismatch。
- r01 の FAIL 時、区間の最大は `memset` **126,665 µs** (約 127 ms)。`bufferswitch` は 64 µs で本体は犯人ではない。
- 同 run の `cb_max_us` は 64 µs。**`cb_max_us` (bufferSwitch 本体) は FAIL 時の遅延を捕まえていない。**
- `memset` 区間は `A.B * sizeof(float) * nOut` の 0 埋めのみ。通常は数〜数百 µs。FAIL 1 回だけ 127 ms で、他 19 回は最大 1,885 µs。

### 2-2. HEAD 604f9d5dd (計装 commit) での再測定

- r01 (HEAD): underruns 0 / ramp 0 / seg `{in_read 14, memset 475, bufferswitch 54, out_write 10}`。
- h02 (HEAD): underruns 0 / ramp 0 / seg `{in_read 20, memset 15, bufferswitch 54, out_write 20}`。
- h03 (HEAD): underruns 0 / ramp 0 / seg `{in_read 10, memset 14, bufferswitch 459, out_write 14}`。
- **HEAD での連続 20 回は未実施** (時間上限のため 3 回で区切った)。FAIL 再現は HEAD では未確認。

## 3. 解釈 (未確定)

- FAIL 1 回 (20 回中) の遅延は `memset` 区間に載った (126 ms)。
- ただし `memset` は単純な 0 埋めで、127 ms の原因は memset 自体ではなく、**計測区間内でスレッドが停止した** (OS スケジューリング・wasm メモリの初回 touch・ページ割当て等) 可能性が高い。区間内のどの命令かは切り分けていない。
- `fla_in_read` と `fla_out_write` はそれぞれ FAIL run で 90 µs・10 µs。
- 「停止の直接経路の特定」は**未達**。

## 4. 未達・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD 604f9d5dd での連続 20 回 (FAIL 再現の確認) | FAIL の再現率は作業ツリー 20 回で 1/20 のみ。HEAD では未確認 | #4593 (本 PR の残り) |
| `memset` 区間 127 ms の原因 (memset 内の初回 touch か、区間内の OS 停止か) | 停止の直接経路が未特定 | #4593 |
| FAIL 時の区間ごとの内訳を複数回得ること | 1 件では再現性を言えない | #4593 |
