# tools/audio/asio — #998 負荷下の再現試験 付録 (REPORT §12 から分割移動)

> **正本**: `tools/audio/asio/REPORT.md` §12 (結論・未解決)。本付録は §12-2 の全文 (無変更で移動)。
> 本 run の環境: `nproc=4` (4 コア runner)。`REPORT.md` §11 の「16 コア」は別環境の記録。

### 12-2. 負荷下の再現試験 (2026-10-14・worktree HEAD `80c32a06`・検証コード差分 0)

負荷: `yes > /dev/null` を 4 本 (4 コア runner)。実行前 load 0.28 → 実行中 load 6.0〜9.6。e2e は foreground。

| 実行 | 種別 | exit | 所要 | load (実行後) | underruns (b256_d2 / b1024_d2 / sine / soak) | 備考 |
|---|---|---|---|---|---|---|
| L1 | 完全 (`e2e.sh`) | **1** | 221 s | 6.00 | **1** (silence 512) / 0 / 0 / 0 | `com_ramp_b256_d2` FAIL。ramp 194432/240512 |
| L2 | `--quick` | 0 | 86 s | — | 0 / 0 / 0 (soak なし) | 3/3 PASS |
| L3 | 完全 | 0 | 224 s | 9.60 | 0 / 0 / 0 / 0 | 4/4 PASS |

- 負荷下では `com_ramp_b256_d2` が完全実行 2 回中 1 回 (L1) で underrun 1 を出した。原因は未特定。L1 の silence は 512 で、§11 実行 A (silence 1280) より小さい。
- 通算母集団は §12 の定義に L1〜L3 を加えて **13 回・underrun 2 回** (`b256_d2` のみ)。
- 同一 HEAD・同一負荷での再現は確定的ではない (完全実行 2 回中 1 回)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実行 A・L1 の underrun の原因 (負荷・ring 深さ・worklet スケジューリング) が未特定。負荷下でも完全実行 2 回中 1 回でしか出ない | ゲート (underrun 0) が揺らぐ。merge 判定で再実行が必要になり得る | #998 |
| 負荷下の再現頻度は §12-3 で観測 (N=6, 2 回) のみ。underrun 時の ring 深さ・worklet 側のログ採取が未実施 | 原因の切り分けができない | #998 |

### 12-3. 負荷下の再現頻度 (2026-10-14・HEAD `1be53b3f`・検証コード差分 0)

負荷: `yes > /dev/null` を 4 本 (4 コア runner)。`e2e.sh` 完全実行を foreground で 4 回連続 (A〜D)。各回の負荷は `tools/audio/asio/work/load_run.sh` (work/ 配下・非コミット) で掛け、終了後に PID 指定で停止。

| 実行 | exit | 所要 | load (実行後) | `com_ramp_b256_d2` underruns / silence | min_fill | cb_late (max µs) | T (latency_changes) |
|---|---|---|---|---|---|---|---|
| A | **1** | 211 s | 5.50 | **1 / 2688** | **0** | 1 (165) | 1536 (2) |
| B | 0 | 209 s | 5.82 | 0 / 0 | 384 | 0 (449) | 1024 (0) |
| C | 0 | 209 s | 未記録 | 0 / 0 | 896 | 0 (50) | 1536 (0) |
| D | 0 | 208 s | 未記録 | 0 / 0 | 896 | 0 (99) | 1536 (0) |

- 完全実行 4 回中 1 回 (A) で `com_ramp_b256_d2` が underrun。A の ring は実際に 0 まで枯渇し、他の 3 回の最小充填 (384〜896) と明確に異なる。
- A は `cb_late` が 1 回 (165 µs) 発生し、`latency_changes` が 2 回 (T 変更)。B〜D は `latency_changes` 0。原因との関係は未確認 (相関の観測のみ)。
- 負荷下の母集団 (完全実行のみ): L1・L3 と A〜D の **6 回中 2 回 underrun** (`b256_d2`)。`--quick` の L2 は母集団から除外。
- 負荷下の母集団 (`--quick` 含む): L1〜L3 と A〜D の **7 回中 2 回 underrun**。§12 の負荷なし 5 回 (underrun 0) は別母集団として扱う。
- 負荷は 4 コア runner で実行中 load 6.0 以上 (§12-2 の記録)。実行後 load は A 5.50・B 5.82 のみ記録 (C・D は未記録)。負荷を掛けない状態の 5 回 (§12) では再現しなかった。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| A の ring 枯渇の直接原因 (producer 側の遅延か consumer 側の遅延か) が未特定。`cb_late` との対応は 1 件のみで未確定 | 原因と対処 (受入条件 2) が未達 | #998 |
| underrun 時の ring 深さ・worklet 側ログの採取は本節では未実施 (snapshot の min_fill のみ) | 枯渇の時刻と経路が分からない | #998 → §12-4 で一部採取 |

### 12-4. underrun 直前の ring 充填 trace (2026-10-14・測定 commit `b09073d9` + harness 出力追加)

harness (`harness/chunk_verify.mjs`) の結果 JSON に `underrun_trace` (初回 underrun 直前 64 quantum の `cap.fill` 推移) と `callback_gap` (worklet 呼出間隔ヒストグラム, `hdr[8..14]`) を追加した。worklet 本体・判定基準・ゲートは無変更。負荷は `yes` 4 本 (4 コア runner)、実行は worktree の絶対パスで foreground。

| 実行 | exit | 所要 | `com_ramp_b256_d2` underruns / silence | min_fill | worklet 呼出間隔 最大 (ms) | producer cb_max (µs) | cb_late / wait_timeouts |
|---|---|---|---|---|---|---|---|
| T1 | **1** | 215 s | **1 / 256** | 0 (※・trace 上) | 14 | 23,839 | 0 / 0 |
| T2 | 0 | 207 s | 0 / 0 | 未記録 | 16 | 未記録 | 未記録 |
| T3 | 0 | 211 s | 0 / 0 | 未記録 | 16 | 未記録 | 未記録 |

- **T1 の trace**: `fill_before_first` は underrun 直前の 64 quantum。直近 11 点は `…1024, 896, 768, 640, 512, 640, 512, 384, 256, 128, 0`。隣接差分は −128 が 9 回、+128 が 1 回 (512 → 640) で、残りの quantum は消費 (128 frames/quantum ≒ 2.67 ms) のみ分減っている。つまり約 9〜10 quantum (≒ 24〜27 ms) の間 producer がほぼ書き込まず、その後 1 回だけ部分的に復帰して underrun に至った形。「段階的な追従不足」ではなく「producer の書き込み停止」が実測に近い。
- T1 の `cb_max` 23.8 ms (単発の producer 側 bufferSwitch) は、上記の停止時間 (≒ 24〜27 ms) と時間的に整合する。ただし因果は推定で、停止の原因 (どの wake / JS 往復か) は未特定。
- (※) `min_fill` は旧版の表で 256 としていたが、trace と矛盾していた (256 は同行の silence 値の取り違えの可能性が高い)。harness の `device_fill` は `k = 8 .. qEnd` の全 quantum を走査し、underrun 最初の quantum の充填は trace 末尾の `0` と同じ `cap.fill` 配列の値なので、`device_fill.min` は 0 になるはず。T1 の結果 JSON は `work/` ごと未保存のため、`device_fill.min` の直接確認は未了。
- T1 の `cb_late` 0・`wait_timeouts` 0 で、worklet 側の呼出間隔も最大 14 ms。worklet が止まったのではなく、producer が充填を追えなくなった可能性が高い。ただしこれは trace からの推定で、producer 側の時系列 (どの wake で遅れたか) は未採取。
- T2・T3 は underrun 0 で、`callback_gap` は T1 と同程度 (最大 16 ms)。

**判定**: 負荷下の underrun は、producer が約 24〜27 ms 書き込みを止めたあと 1 回だけ部分復帰して ring が枯渇する形で再現する (1 回の bufferSwitch 停止と時間的に整合)。`cb_late` や worklet 停止では説明できない。直接原因 (producer のどの待ちで遅れたか) は未特定のため、受入条件 2 は**部分達成のまま**。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| producer 側の遅延点の特定 (wake 待ち・bufferSwitch 内の JS 往復のどれか) | 原因と対処 (受入条件 2) が未達 | #998 |
| 同一条件での underrun 頻度の確定 (T1〜T3 は 1/3 のみ) | 頻度の母集団が小さい | #998 |

注: 本付録の検証は worktree `998-underrun-diag` の絶対パスで行った。途中、誤って main の共有ワークツリーで 1 回 e2e を走らせた (exit 0・4/4 PASS・trace なし)。その成果物 (`tools/audio/asio/work/`) は削除済みで、本節の表には含めない。

### 12-5. producer 側 wake 遅延の計測 (2026-10-14・測定 commit `68270216`・コード差分は下記のみ)

`com_test.c` の結果 JSON に既存の `wake_hist` (futex 起床の遅延ヒストグラム `<1,<2,<4,<8,<16,>=16` ms) を追加した。flasio・worklet・判定基準・ゲートは無変更。負荷は `yes` 4 本 (4 コア runner)・e2e は worktree の絶対パスで foreground・実行後に PID 指定で停止。

| 実行 | exit | 所要 | 実行後 load | `com_ramp_b256_d2` underruns / silence | min_fill | cb_late | wait_timeouts | wake_hist (b256_d2) |
|---|---|---|---|---|---|---|---|---|
| W1 | 0 | 219 s | 6.48 | 0 / 0 | 384 | 0 | 0 | [765,13,2,1,0,0] |
| W2 | 0 | 215 s | 7.67 | 0 / 0 | 384 | 0 | 0 | [569,16,1,0,0,0] |
| W3 | 0 | 218 s | 7.86 | 0 / 0 | 896 | 0 | 0 | [749,7,7,0,0,0] |

- W1・W2 は同じ計測コードで、W3 は測定 commit `68270216` の HEAD。3 回とも 4 シナリオ PASS。W1・W2 の時点のコードは W3 と同じ (コミット前に build 済み)。
- W1〜W3 の b256_d2 では wake の 8 ms 以上の起床は 0 回 (`>=16` も 0)。`wait_timeouts` も 0。
- 本計測の母集団は負荷下 3 回で underrun 0。§12-3・§12-4 の underrun 2 回 (A・T1) を再現していない。ゲートを緩めた根拠にはならない。
- 結論: producer の futex 起床遅延は underrun の原因として確認されなかった。§12-4 の「bufferSwitch 内の停止」仮説は、wake 側の遅延ではなく bufferSwitch (JS 往復) 側に残る。未検証。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| underrun の直接原因 (wake 遅延は計測上なし。bufferSwitch 内の JS 往復が候補) | 受入条件 2 が未達 | #998 |
| 同一条件で underrun を再現する手段 (負荷 4 本では 6 回中 2 回 → 本 run は 0/3) | 頻度と原因の切り分けができない | #998 |
