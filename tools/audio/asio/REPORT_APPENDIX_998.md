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
| 負荷下の再現頻度の確定 (N 回の連続試行) と、underrun 時の ring 深さ・worklet 側のログ採取が未実施 | 原因の切り分けができない | #998 |

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
- 負荷は 4 コア runner で load 5〜6 に達しているが、負荷を掛けない状態の 5 回 (§12) では再現しなかった。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| A の ring 枯渇の直接原因 (producer 側の遅延か consumer 側の遅延か) が未特定。`cb_late` との対応は 1 件のみで未確定 | 原因と対処 (受入条件 2) が未達 | #998 |
| underrun 時の ring 深さ・worklet 側ログの採取は本節では未実施 (snapshot の min_fill のみ) | 枯渇の時刻と経路が分からない | #998 |
