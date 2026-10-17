# flp #5302: FLEX 書き出しの停止点 (wine thread 状態)

親: #5302 (受入 1: Render tests 4 本の WAV 未出力の原因記録)。前提: #6088 (S2 の進行観測)・停止報告 (`c8866d829` 測定)。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| 4 本の WAV 未出力の原因を記録する | **未達** (FLEX 1 本で「書き出し前の起動段階で CPU を使い続ける thread がある」まで。原因は未特定) | §3・§4 |

## 2. 測定

- 測定 commit: `a1e14e07a` (本 PR の HEAD。`tools/flp/s2_render_probe.sh` は `bc4d4586a` から変更なし)。
- 差分 (測定 commit から HEAD まで): `git diff a1e14e07a HEAD -- tools/flp/s2_render_probe.sh` は空 (差分 0)。
- 素材 `fl-win64`: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (9.3 s)。wine は apt の wine64 9.0 (`/usr/lib/wine/wine64`) + xvfb-run。
- S1 `tools/flp/s1_wine_probe.sh` (120 s): rc=124 (GUI 継続)・MSGBOX_OnInit=0・native-load=0 (前回と同じ)。
- S2 `S2_TIMEOUT=150 S2_THREAD_AT="60 90" bash tools/flp/s2_render_probe.sh FLEX.flp 1` (48000 Hz・WFBox=2・DitherBox=0 は既定のまま): rc=124・WAV なし・150 s (実測 2 分 33 秒)。
- 採取: `$RUNNER_TEMP/s2/s2_threads_1.tsv` (列: 経過秒・pid・tid・comm・state・utime・stime・wchan・syscall)。
- **syscall 列は全行 `-`。** スクリプトは `set -euo pipefail` のため、`cat` の EPERM で `cut` が失敗し `|| echo -` が効いて `-` になる。同じ式を pipefail 無しで実行すると空欄になる (実測)。
- `/proc/<pid>/task/<tid>/syscall` は本ランナーで、スクリプト外の兄弟プロセスの値は EPERM。`/proc/self/syscall` は読める (値あり)。`ptrace_scope=1` で、読み手が対象の祖先でないためと考えられる (未確認)。`0` などの値は、この採取では得られない。
- 前回 (`30d973d95`) の付録にあった「syscall は 0 (ユーザー空間で実行中)」は誤読で、撤回する。`0` は syscall 番号 (x86_64 の read) であり、ユーザー空間の実行を示さない。

## 3. thread の状態 (今回の採取: FL64.exe pid 4875)

生の `s2_threads_1.tsv` の 60 s / 90 s の行 (関係する行。他は下表):

```
60	4875	4875	FL64.exe	R 1212 2162	0	-
90	4875	4875	FL64.exe	R 1759 3248	0	-
60	4875	4947	FL64.exe	R 5482 113	0	-
90	4875	4947	FL64.exe	R 8237 160	0	-
```

| tid | comm | 60 s: state utime stime | 90 s: state utime stime | wchan |
|---|---|---|---|---|
| 4947 | FL64.exe | R 5482 113 | R 8237 160 | 0 |
| 4875 | FL64.exe (main) | R 1212 2162 | R 1759 3248 | 0 |
| 4946 | FL64.exe | S 187 959 | S 187 959 | anon_pipe_read |
| 他 (10 本) | 各種 | S (utime 増分 0) | S (増分 0) | futex_do_wait・anon_pipe_read |

- tid 4947 は 60 s→90 s で utime が 2755 ticks (27.55 s) 増え、30 s の実時間の約 0.92 コア。両時点で state は R。
- main thread (4875) は utime +547・stime +1086 ticks。
- 他の thread は待ち (anon_pipe_read・futex) で増分 0。
- `s2_progress_1.tsv` で、0〜141 s の全サンプルのログ バイト数が 1434 のまま増えない (ログ増分 0)。WAV は出ていない。
- **判定に使えるのは、utime 増分と state R だけ。** 「spin か長い計算か」は、この採取からは言えない。wchan が 0 なのは、カーネルの待ち関数を示さないという意味で、ユーザー空間の計算を証明しない。
- 参考: 前回 round の採取 (`bc4d4586a`・pid 5125・tid 5199) でも同じ形 (60→90 s で utime +2841 ticks・state R) だった。その生の TSV は本ランナーに残っていない。tid は run ごとに変わり、30d973d95 の tid 5048 とは別 run。

## 4. 判定と未解決

- 判定 (utime 増分と state R だけで言える範囲): 書き出し前の段階で、1 本の thread (今回 tid 4947) が 60 s→90 s の間に約 0.92 コアの CPU 時間を使い、state は R のまま。待ち (S) ではない。
- 言えないこと: その CPU が spin か長い計算か、何の関数か。syscall 値が取れないため、ユーザー空間で計算中かの確認にもならない。
- 未解決:
  - tid 4947 (と前回の 5199) が何をしているか: 関数・RIP の特定。gdb の attach (`tools/flp/s3_gdb_attach_probe.sh` 系の流用) か、RIP の複数時点採取が必要 (本 PR では未採取)。
  - 他 3 本 (Fruity Convolver・Fruity Parametric EQ 2・Fruity Center) は今回未再測定。
