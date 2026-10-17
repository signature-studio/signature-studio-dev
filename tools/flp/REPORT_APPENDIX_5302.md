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

## 5. 残作業 (a)(b) の測定 (本 PR)

- 測定 commit: 本 PR の `s2_render_probe.sh` を commit した HEAD (下の §5.3 で再現)。前回の測定 commit `a1e14e07a` からの差分は `s2_render_probe.sh` の RIP 採取 (`S2_RIP_AT`) 追加のみ。
- 素材 `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開。wine64 9.0・gdb (apt)。`kernel.yama.ptrace_scope=0` を runner で設定 (gdb attach に必要)。
- S1 (120 s): rc=124・MSGBOX_OnInit=0・native-load=0 (前回と同じ)。

### 5.1 4 本の結果 (48000 Hz・WFBox=2・DitherBox=0 は既定のまま・各 300 s)

| 本 | rc | WAV | ログ (バイト) | 300 s 時点の wine 系 CPU (R の thread) |
|---|---|---|---|---|
| FLEX | 未再測 (前回 §3: 150 s・600 s で WAV なし) | なし | 1434 | 前回 §3 |
| Fruity Convolver | 124 | なし | 1434 (不変) | 約 1 コア (tid 5263: 60→150→240 s で utime 5494→14028→22464 ticks) |
| Fruity Parametric EQ 2 | 124 | なし | 1562 | 約 1 コア (tid 11475: 5501→13947→22489 ticks) |
| Fruity Center | 124 | なし | 1498 | 約 1 コア (tid 13275: 5668→14377→23184 ticks) |

- 4 本とも、ログは ALSA 警告と `X connection broken` で止まり、書き出しの進行は見えない。
- 注: 表の 3 本は同じ 300 s 上限の run。FLEX は今回の run に含めていない (表の値は前回 §3 の値)。
- 4 本とも、wine 系の thread で utime が増え続けて R のままの thread が 1 本ある。他の thread は pipe 読み (`anon_pipe_read`)・futex の待ち。
- Fruity Center の 240 s 時点では main thread (13200) が `poll_schedule_timeout` (待ち) にいる。計算 thread (13275) は R のまま。

### 5.2 RIP 採取 (Fruity Convolver・S2_RIP_AT="60 150 240"・gdb attach)

- 採取: `s2_rip_1.tsv` (列: 経過秒・LWP・rip)。`gdb -p` の `thread apply all info registers rip`。
- ほとんどの thread の RIP は `libc read` (pipe 待ち) で、3 時点で変わらない。
- 採取は第 1 run (`S2_RIP_AT="60 150 240"`・Fruity Convolver) で 60 / 150 / 240 s の 3 点、第 2 run (`S2_RIP_AT="60 90"`・同じ本) で 60 / 90 s の 2 点。
- 計算 thread は両 run とも 1 本 (第 1 run tid 7368・第 2 run tid 9883)。残りの thread の RIP は libc `read` (pipe 待ち) で変化なし。
- 計算 thread の RIP (`QuickFontCache_x64.dll` の `r-xp` 領域。ロード先 0x79f70000・RVA = RIP − 0x79f70000):
  - 第 1 run: 60 s `0x7a0f5b81` (RVA 0x185b81) → 150 s・240 s `0x7a0f5c0d` (RVA 0x185c0d)。
  - 第 2 run: 60 s `0x7a0f5b95` (RVA 0x185b95) → 90 s `0x7a0f5c0d`。
- 逆アセンブル (`objdump -d -M intel`・ImageBase 0x400000 の VA で表示。RVA 0x185c0d = VA 0x585c0d):
  - `0x585c05`〜`0x585c0d`: `cmp BYTE PTR [rax+0x1a],0` → `je 0x585bf0`。`0x585bf0`〜`0x585c00` は `call 0x5860a0` と `call 0x585b70` を繰り返す。
  - つまり `[obj+0x1a]` が 0 になるまで回るループの末尾。`0x585c0d` で止まる採取が 150・240 s・第 2 run の 90 s で一致しており、ループの末尾を繰り返し通っている。
- 判定: **ループは特定できた (`0x585bf0`〜`0x585c0d`)。** ただし `[obj+0x1a]` の値・`call 0x5860a0` の中身・終了条件は未確認。spin か、待ちの代わりの polling かは、この採取からは言えない。関数名は stripped で不明。

### 5.3 未解決 (起票先: #5302 のまま `Refs`)

- 高 CPU thread の呼び出し元 (ループ本体) の特定。次の一手: RIP を 0.1 s 間隔で多数採るか、`QuickFontCache_x64.dll` の `0x585b70` を呼ぶ呼び出し元を gdb の breakpoint (hit count) で数える。1 run に収まる。
- 受入 1 (4 本の原因記録): 4 本とも「WAV なし・1 thread が計算を続けている」までで、「遅い」と「固まっている」の区別は未達。
- wine の `ptrace` 経由の backtrace は PE 側で取れなかった (未試行)。
