# flp #5302: FLEX 書き出しの停止点 (wine thread 状態)

親: #5302 (受入 1: Render tests 4 本の WAV 未出力の原因記録)。前提: #6088 (S2 の進行観測)・停止報告 (`c8866d829` 測定)。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| 4 本の WAV 未出力の原因を記録する | **未達** (FLEX 1 本で「書き出し前の起動段階で CPU を使い続ける thread がある」まで。原因は未特定) | §3・§4 |

## 2. 測定

- 測定 commit: 本 PR の `tools/flp/s2_render_probe.sh` を変えた commit (測定は作業ツリーで行い、コミット後に再現する)。base は `b900bf5ad` (origin/main)。
- 素材 `fl-win64`: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (6.1 s)。wine は apt の wine64 9.0 + xvfb-run。
- S1 `tools/flp/s1_wine_probe.sh`: 2 m 9 s・rc=124 (GUI 継続)・MSGBOX_OnInit=0・native-load=0 (前回と同じ)。
- S2 `S2_TIMEOUT=150 S2_THREAD_AT="60 90" bash tools/flp/s2_render_probe.sh FLEX.flp 1` (48000 Hz・WFBox=2・DitherBox=0 は既定のまま): rc=124・WAV なし・150 s。
- 採取: `s2_threads_1.tsv` (列: 経過秒・pid・tid・comm・state・utime・stime・wchan・syscall)。

## 3. thread の状態 (FL64.exe pid 4973)

| tid | comm | 60 s: state utime stime | 90 s: state utime stime | wchan |
|---|---|---|---|---|
| 5048 | FL64.exe | R 5448 61 | R 8184 96 | 0 (実行中) |
| 4973 | FL64.exe (main) | R 1729 1508 | R 2492 2304 | 0 |
| 5045 | FL64.exe | S 284 1253 | S 284 1253 | anon_pipe_read |
| 他 (20 本強) | 各種 | S (utime 増分 0) | S (増分 0) | futex_do_wait・anon_pipe_read |

- tid 5048 は 60 s→90 s で utime が 2736 ticks (約 27.4 s) 増え、30 s の実時間の約 0.91 コアを使う。state は常に R・syscall は 0 (ユーザー空間で実行中)。
- main thread は utime +763・stime +796 ticks (約 0.26 コアずつ)。
- 他の thread は待ち (anon_pipe_read・futex) で増分 0。

## 4. 判定と未解決

- 判定: 書き出し前の起動段階で、1 本の thread (tid 5048) がユーザー空間で計算を続けている。待ちではなく spin か長い計算。`s2_progress_1.tsv` の WAV 0・ログ増分 0 と一致する。
- 未解決 (起票先: #5302 のまま `Refs`):
  - tid 5048 が何をしているか: 関数の特定に gdb の attach (`tools/flp/s3_gdb_attach_probe.sh` 系の流用) か、`WINEDEBUG=+thread` の起動時刻が必要。
  - 計算か無限ループかの区別は、同じ thread の RIP を 2 時点で採ると可能 (本測定では未採取)。
  - 他 3 本 (Fruity Convolver・Fruity Parametric EQ 2・Fruity Center) は今回未再測定。
