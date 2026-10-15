# 付録: liftdiff LD-161 (#3563) — trap helper 0x409730 の abort 経路の return

> **正本**: `tools/liftdiff/REPORT.md`。前段は `REPORT_APPENDIX_LD159.md` (#3505)。本書は LD-161 の実測と未解決を置く。

## 結論

- **受入 1 (trap 入力の status が ok) は未達**。部分達成 (`Refs #3563`)。
- **入れたもの**: native 専用の `abortret=<VA>` case。trap helper の入口 (0x409730) の状態を trace hit で保存し、noncontinuable な `RaiseException` (flags & 1) で入口の return 状態へ戻す。既定 off。
- **変更前の失敗点**: `RaiseException` (既定 stub は 0 を返す) の後も、ゲストが abort の後続 (`LoadLibraryA`・`LocalAlloc`・`GetProcAddress`・`MessageBoxA`) を実行し、0x41d15a の TLS 読み (`gs:[0x58]` + TLS index `0xffffffff`) で segv した。
- **変更後**: 5 件の trap 入力で 0x409730 は戻り、0x417b70 の続きを実行する。ただし続きが完走しない (下表)。trap 進入の trace (0x409730 の entry) は全件に残る。
- **判定はしていない**: trap の正しさ・予測式の検証は行わない (受入の範囲外)。

## 実装 (測定 commit `74510fd98`)

- `tools/liftdiff/rt/ld_core.h`: case キー `abortret` (hex VA) を追加。wasm 側は読まない値。
- `tools/liftdiff/rt/ld_native.c`:
  - `on_sig` の trace hit で `abortret` の VA に入ったら `ab_save` が ucontext (gregs と fpregs) を保存する。
  - `ld_stub_c` で noncontinuable な `RaiseException` を受けたら、`ld_stub` の記録の後に `ab_return` を呼ぶ。`ab_return` は保存状態を `setcontext` で戻す: rsp+8・rip=入口の戻り先・rax=0。callee-saved・xmm・MXCSR は入口の値。
  - 保存状態は case ごとに初期化する。0x409730 は abort しか行わない (`0x4096d0` を必ず呼ぶ) ため、通常の return 後に古い保存状態を使うことは起きない。
- `tools/liftdiff/tests/trace_417b70_trap.py`: 各 case に `abortret=409730` を付ける。

## 完走させるために入れた stub (受入 2)

| stub | 変更前 | 変更後 (`abortret` 指定時のみ) |
|---|---|---|
| `RaiseException` (kernel32) | 既定 0 を返す。noreturn の後続を実行してしまう | noncontinuable (flags & 1) は trap helper 入口の return 状態へ戻す。呼出しは `calls` に記録 |
| `LoadLibraryA`・`LocalAlloc`・`GetProcAddress`・`MessageBoxA` | `RaiseException` の後の後続経路で呼ばれていた (MessageBoxA は既定 0) | `abortret` 指定時で、trap 入口の状態を保存した後の noncontinuable な `RaiseException` が戻すとき (`ab_return`) だけ呼ばれなくなる。既定 off では従来どおり。stub の実装は変更なし |

trap の判定は stub に入れていない。stub が決めるのは戻り先だけ。

## 実測

測定 commit `74510fd98` (コードを変えた最後の commit)。HEAD は同じ commit から本付録 (docs のみ) を積んだもの。

再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/liftdiff/tests/trace_417b70_trap.py > tools/liftdiff/results/m11_417b70_trap_inputs.md`。rc=0、2 回の出力は一致 (`cmp`)。所要 0.48 s (wall)、load 0.15 (実行直前の `/proc/loadavg`)。素材: fl-win64 の `extracted/block00031_PE.bin`、work-liftdiff・work-m11 (worktree の gitignore 対象に展開)。出力の正本: `results/m11_417b70_trap_inputs.md`。

測定 commit 以降のコード差分 (WORKFLOW §6): `git diff 74510fd98 HEAD -- tools/liftdiff/rt tools/liftdiff/tests` の出力は空 (0 行)。本付録と PR 本文の docs のみの commit はこの範囲の外。

| stride | count | 0x409730 進入 | 変更前 (`e80effec4`) | 変更後 (`74510fd98`) | 終了位置の所見 |
|---:|---:|:---:|---|---|---|
| 16 | 1 | False | ok | ok | trap に入らない (対象外) |
| -16 | 1 | False | segv 0x417e4a | segv 0x417e4a | trap に入らない (U6・対象外) |
| 16 | 2 | False | ok | ok | trap に入らない |
| -16 | 2 | True | segv 0x41d15a | segv 0x417e4a | 戻り後の確保 0x409470 が size ≤ 0 で 0 を返し、0x417e4a で null 参照 |
| -16 | 3 | True | segv 0x41d15a | segv 0x417e4a | 同上 |
| 16 | 2^60 | True | segv 0x41d15a | sigfpe | 戻り後のゲストが MXCSR を 0 (全例外非マスク) にする。下の U8 |
| -16 | 2^60 | True | segv 0x41d15a | sigfpe | 同上 |
| 2^31-1 | 3 | True (確保内 0x4073c0 から) | segv 0x41d15a | segv 0x417e4a | VirtualAlloc の後、戻り後の確保が 0 を返し null 参照 |

- 変更前の 0x41d15a: `RaiseException` (0xeedfade・flags 1) の後の経路。`0x41d14b`〜`0x41d15a` は `gs:[0x58]` の TLS 配列を `[rax + rcx*8]` で読み、`rcx` (TLS index) は `0xffffffff` のまま。
- 変更後の 0x417e4a: `mov dword [rax+4],1` の `rax` が 0。trap 経由の 3 件 ((-16,2)・(-16,3)・(2^31-1,3)) は、戻り後の確保 0x409470 が 0 を返すと推定する (確保 0x409470 は size ≤ 0 の分岐 0x40949e と確保失敗 0x409495 から再び 0x409730 を呼ぶ・逆アセンブル)。非 trap の (-16,1) は trace が 0x409470 で止まり 0x409730 に入らないため、この機構では説明できない (機構は未確認。U6)。
- MXCSR (ld_native の一時計測。計測後に元へ戻した): `ld_ms_call` 復帰直後は、(16,1)・(16,2) で `0x00001f80`、(16,2^60) で `0x00000000`。segv の入力は復帰しないため計測できない。sigfpe は `ld_native.c` の `ld_native_ms` 計算 (ホスト側の `divsd`) で起きると推定 (未確認。SIGFPE の発生命令は特定していない)。
- 対照 (`abortret` を付けない): (-16,2) は変更前と同一の segv 0x41d15a で、呼出し列も同一 (`RaiseException`→`LoadLibraryA`→`LocalAlloc`→`GetProcAddress`→`MessageBoxA`)。(16,2) は ok。既定 off で挙動は変わらない。

## 未解決

| ID | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U1' | 受入 1 (trap 入力の ok) 未達。戻った後の続きの扱いを決める必要がある。(a) 確保失敗の経路 (0x409470 が 0 を返す → 0x417e4a の null 参照) をモデル化する、(b) abort を call の終端として別 status にする | 受入 1 | #3563 (PM agent の判断待ち: (a)/(b)・既定案: 受入 1 は未達のまま #3563 に残し、(a)/(b) は #1767 の stride ≤ 0 調査の結果を待つ。新しい status は作らない) |
| U6 | `0x409470` が 0 を返して `0x417e4a` で null 参照する経路。終端は 4 件。trap 経由は (-16,2)・(-16,3)・(2^31-1,3) の 3 件、非 trap は (-16,1) (機構は未確認) | (a) の前提。終端 4 件 | #1767 残 |
| U8 | ホスト側の浮動小数点環境: `run_case` は `ld_ms_call` の復帰後に MXCSR を既定へ戻さない。ゲストの MXCSR=0 が host の `divsd` で SIGFPE になる (推定) | (16,2^60)・(-16,2^60) の sigfpe。harness 側の不具合の疑い | #3563 |
| U9 | wasm 側 (`ld_wasm.c`・`fle_ldbridge.c`) は `abortret` を持たない。trap 入力の native と wasm の結果は食い違う | native/wasm の比較で trap 入力を除外する必要がある | #3563 |
| U10 | `ab_return` は memset した `ucontext_t` で `setcontext` するため、復帰後の signal mask が空になる。入口の `uc_sigmask` を `ab_save` で保存して渡すと安全 (未適用) | 現呼出しへの影響は未確認。適用は rt を変えるため、測定 commit を更新して再測定する必要がある (本 run は work-m11 が無く再測定できない) | #3563 (次の測定 run で適用) |

## 検証の範囲

- 実行 (測定 commit `74510fd98` で実施): trap 表 (上の 8 件) の再現 (2 回)、既定 off の対照 2 件。
- 未実行: `tools/liftdiff/liftdiff_e2e.sh` (wasm 経路を含む)。変更は native の gated 経路だけで、wasm のビルドは変えていない。
- 未実行 (本 run の fix モード): 再測定。`work-m11`・`work-liftdiff` が本 run の素材に無く、`trace_417b70_trap.py` を再現できない。付録の差分 (ld_native.c・U10) を入れる場合は再測定が要る。
