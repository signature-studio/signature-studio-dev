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

- 測定 commit: `666a5d4c8` (RIP 採取 `S2_RIP_AT` を入れた script。§5.1・§5.2 の run はすべてこの script)。前回 (§3) の測定 commit `a1e14e07a` からの差分は `git diff a1e14e07a 666a5d4c8 -- tools/flp/s2_render_probe.sh` の RIP 採取 (`S2_RIP_AT`) 追加のみ。
- 再現コマンド: `S2_TIMEOUT=300 S2_THREAD_AT="60 150 240" S2_RIP_AT="60 150 240" bash tools/flp/s2_render_probe.sh "Fruity Convolver.flp" 1` (`kernel.yama.ptrace_scope=0` を事前に設定)。
- 注: 既定の `S2_THREAD_AT="60 90"`・`S2_TIMEOUT=120` では、300 s 時点の値は出ない。§5.1 の値は下の採取時刻の指定で得たもの。
- 素材 `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開。wine64 9.0・gdb (apt)。`kernel.yama.ptrace_scope=0` を runner で設定 (gdb attach に必要)。
- S1 (120 s): rc=124・MSGBOX_OnInit=0・native-load=0 (前回と同じ)。

### 5.1 4 本の再測定 (48000 Hz・WFBox=2・DitherBox=0 は既定のまま・S2_TIMEOUT=300・S2_THREAD_AT="60 150 240")

| 本 | rc | WAV | ログ (バイト) | 計算 thread (R・wchan 0) の utime (ticks) |
|---|---|---|---|---|
| Fruity Convolver (RIP 採取あり・HEAD `7493d05f8` の run) | 124 | なし | 1434 | tid 14479: 60 s 5488 → 150 s 13915 → 240 s 22401 |
| Fruity Parametric EQ 2 | 124 | なし | 1562 | tid 10383: 60 s 5484 → 150 s 13903 → 240 s 22435 |
| Fruity Center | 124 | なし | 1498 | tid 12187: 60 s 5647 → 150 s 14366 → 240 s 23184 |
| FLEX | 未再測 | なし | 1434 | 前回 §3 の 150 s のみ (600 s の記録は無い) |

- 採取は 4 点 (60/150/240 s) で同じ形: 計算 thread が 1 本だけ R のまま utime が増え続け、他の thread は pipe 読み・futex の待ち。
- 3 本の run は `S2_RIP_AT` を空にして行った (RIP 採取の影響を除く)。Convolver のみ RIP 採取あり。Parametric EQ 2・Fruity Center の run は `S2_RIP_AT=""` で `S2_TIMEOUT=300 S2_THREAD_AT="60 150 240"` (script は `666a5d4c8` と同じ実行経路)。
- 表の Convolver 行は HEAD `7493d05f8` の run (RIP 採取あり・`S2_RIP_AT` 指定時のみ gdb の存在確認が走る)。Parametric EQ 2・Fruity Center の 2 行は `S2_RIP_AT=""` のため gdb 確認は走らない。前回の run の値は採らない (上記)。
- 生データ (`s2_threads_*.tsv`・`s2_render_probe` のログ) は、測定に使ったランナーにのみ残っていた。本ランナーの checkout には無いため、run の時刻と保存先は、この REPORT には書けない (照合は未了)。
- 前回 (旧 §5.1) の値は、tid と値の生データが本ランナーに残っていないため採用しない。
- 前提: `kernel.yama.ptrace_scope=0` (既定 1 では gdb が `Could not attach to process` で、RIP 採取は空になる)。

### 5.2 RIP 採取 (Fruity Convolver・S2_TIMEOUT=300・S2_RIP_AT="60 150 240")

- 再現コマンド: `S2_TIMEOUT=300 S2_THREAD_AT="60 150 240" S2_RIP_AT="60 150 240" bash tools/flp/s2_render_probe.sh "Fruity Convolver.flp" 1`。
- 測定 commit: `7493d05f8` (HEAD・検証用の再測定)。script の実行経路は `666a5d4c8` と同じ。
- 計算 thread (`s2_threads_1.tsv` の R 1 本・60 s の tid 14479) の RIP。`QuickFontCache_x64.dll` のロード先は run ごとに変わる (ASLR)。RVA = RIP − ロード先 (この run のロード先は `r-xp` 領域 0x7a0f5000 付近):
  - 60 s: `0x7a0f5b72` (RVA 0x185b72)
  - 150 s: `0x7a0f5bf4` (RVA 0x185bf4)
  - 240 s: `0x7a0f5bbf` (RVA 0x185bbf)
- 前回 (旧 §5.2) の `0x185c0d` とは一致しない。`0x185c0d` が今回の run で再現しなかった理由は未確認。
- 逆アセンブル (素材 `fl-win64` の `block24350_PE.bin`・ImageBase 0x400000・`objdump -d -M intel`)。前回の `0x585c0d` の `cmp BYTE PTR [rax+0x1a],0x0` → `je 0x585bf0` は REPORT の記述どおり。今回の 3 点は次のとおり:

  | RVA | VA | 位置 | 命令 |
  |---|---|---|---|
  | 0x185b72 | 0x585b72 | helper 0x585b70 の本体 (prologue の直後) | `sub rsp,0x28` |
  | 0x185bbf | 0x585bbf | helper 0x585b70 の epilogue | `pop rbp` (直後の `ret` は 0x585bc0) |
  | 0x185bf4 | 0x585bf4 | ループ本体 (0x585bf0〜0x585c0d) | `mov rcx,QWORD PTR [rax+0x48]` |

- 判定: 3 点のうち 2 点 (0x185b72・0x185bbf) は、ループ本体ではなく helper 0x585b70 の中にある。helper は `[rbx+0x70]` を見て `call 0x4f1db0`・`call 0x548ad0` を行い、ループから `call 0x585b70` (0x585be9・0x585c00) で呼ばれる。ループ本体の中にあるのは 0x185bf4 の 1 点だけ。よって RIP の 3 点から「ループ内で計算が続いている」とは言えない。ループの終了条件 `[obj+0x1a]` の値・関数名は未確認。spin か polling かは、3 点の採取からは言えない。
- 注: gdb の attach は各採取で FL64.exe を止めるため、RIP 採取の run の時間は採取なしの run と比べられない。

### 5.3 未解決 (起票先: #5302 のまま `Refs`)

- 計算 thread の呼び出し元 (ループ本体) の特定。RIP を 0.1 s 間隔で多数採る、または `QuickFontCache_x64.dll` の `0x585b70` を呼ぶ呼び出し元を gdb の breakpoint (hit count) で数える。
- helper 0x585b70 と、その callee 0x4f1db0・0x548ad0 の確認 (ループ本体から呼ばれる 0x585b70 が、計算 thread の RIP 2 点を含むため)。
- 受入 1 (4 本の原因記録): 4 本とも「WAV なし・1 thread が CPU を使い続ける」まで。「遅い」と「固まっている」の区別は未達。
- FLEX の 300 s 再測定は未実施 (前回 §3 の 150 s のみ)。
- wine の ptrace 経由の backtrace: 今回は未試行。
