# flp #5302: FLEX 書き出しの停止点 (wine thread 状態)

親: #5302 (受入 1: Render tests 4 本の WAV 未出力の原因記録)。前提: #6088 (S2 の進行観測)・停止報告 (`c8866d829` 測定)。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| 4 本の WAV 未出力の原因を記録する | **未達** (FLEX 1 本で「書き出し前の起動段階で CPU を使い続ける thread がある」まで。原因は未特定) | §3・§4 |

## 2. 測定

- 測定 commit: `bc4d4586a` (`tools/flp/s2_render_probe.sh` のコメントだけを直した commit。測定はこの HEAD のまま、コードを変えずに実行)。base は `b900bf5ad` (origin/main)。
- 差分 (測定 commit から HEAD まで): `git diff bc4d4586a HEAD -- tools/flp/s2_render_probe.sh` は空 (差分 0)。
- 素材 `fl-win64`: `$HOME/artifacts/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (5.4 s)。wine は apt の wine64 9.0 (`/usr/lib/wine/wine64`) + xvfb-run。
- S1 `tools/flp/s1_wine_probe.sh`: rc=124 (GUI 継続)・MSGBOX_OnInit=0・native-load=0 (前回と同じ)。
- S2 `S2_TIMEOUT=150 S2_THREAD_AT="60 90" bash tools/flp/s2_render_probe.sh FLEX.flp 1` (48000 Hz・WFBox=2・DitherBox=0 は既定のまま): rc=124・WAV なし・150 s。
- 採取: `s2_threads_1.tsv` (列: 経過秒・pid・tid・comm・state・utime・stime・wchan・syscall)。
- **syscall 列は全行 `-` (空)。** このランナーでは `/proc/<pid>/task/<tid>/syscall` の読み出しが EPERM になる (自分のプロセスの同ファイルも `Operation not permitted`・`ptrace_scope=1`)。syscall の値は取得できなかった。前回の採取 (`30d973d95`・tid 5048) の生 TSV も残っておらず、値は確認できない。
- 前回 (`30d973d95`) の付録にあった「syscall は 0 (ユーザー空間で実行中)」は誤読で、撤回する。`0` は syscall 番号 (x86_64 の read) であり、ユーザー空間の実行を示さない。

## 3. thread の状態 (FL64.exe pid 4973)

生の `s2_threads_1.tsv` の 60 s / 90 s の行 (pid 5125 の thread のうち関係する行。syscall 列は全て `-`):

```
60	5125	5199	FL64.exe	R 5464 56	0	-
90	5125	5199	FL64.exe	R 8305 87	0	-
60	5125	5125	FL64.exe	R 1727 1549	0	-
90	5125	5125	FL64.exe	R 2506 2396	0	-
```

| tid | comm | 60 s: state utime stime | 90 s: state utime stime | wchan |
|---|---|---|---|---|
| 5199 | FL64.exe | R 5464 56 | R 8305 87 | 0 |
| 5125 | FL64.exe (main) | R 1727 1549 | R 2506 2396 | 0 |
| 5196 | FL64.exe | S 267 1241 | S 267 1241 | anon_pipe_read |
| 他 (20 本強) | 各種 | S (utime 増分 0) | S (増分 0) | futex_do_wait・anon_pipe_read |

- tid 5199 は 60 s→90 s で utime が 2841 ticks (28.41 s) 増え、30 s の実時間の約 0.95 コア。両時点で state は R。
- main thread (5125) は utime +779・stime +847 ticks。
- 他の thread は待ち (anon_pipe_read・futex) で増分 0。
- **判定に使えるのは、utime 増分と state R だけ。** 「spin か長い計算か」は、この採取からは言えない (前回の判定は syscall 値の誤読に依存していたため撤回)。wchan が 0 なのは、カーネルの待ち関数を示さないという意味で、ユーザー空間の計算を証明しない。
- 前回の tid 5048 (`30d973d95` の採取) と今回の tid 5199 は別 run の thread。同一 thread かは確認していない。

## 4. 判定と未解決

- 判定 (utime 増分と state R だけで言える範囲): 書き出し前の段階で、1 本の thread (tid 5199) が 60 s→90 s の間に約 0.95 コアの CPU 時間を使い、state は R のまま。待ち (S) ではない。`s2_progress_1.tsv` の WAV 0・ログ増分 0 と整合する (同じ期間に WAV は出ていない)。
- 言えないこと: その CPU が spin か長い計算か、何の関数か。syscall 値が取れないため、ユーザー空間で計算中かの確認にもならない。
- 未解決:
  - tid 5199 (と前回の 5048) が何をしているか: 関数・RIP の特定。gdb の attach (`tools/flp/s3_gdb_attach_probe.sh` 系の流用) か、RIP の複数時点採取が必要 (本 PR では未採取)。
  - 他 3 本 (Fruity Convolver・Fruity Parametric EQ 2・Fruity Center) は今回未再測定。
