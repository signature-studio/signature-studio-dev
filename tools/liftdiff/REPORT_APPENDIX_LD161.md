# 付録: liftdiff LD-161 (#3563) — trap helper 0x409730 の abort 経路の return

> **正本**: `tools/liftdiff/REPORT.md`。前段は `REPORT_APPENDIX_LD159.md` (#3505)。本書は LD-161 の実測と未解決を置く。

## 結論

- **受入 1 (trap 入力の status が ok) は部分達成** (`Refs #3563`)。trap に入る 5 件のうち 2 件 ((16,2^60)・(-16,2^60)) が ok になった (前 run は sigfpe)。残り 3 件 ((-16,2)・(-16,3)・(2^31-1,3)) は、戻った後の確保 0x409470 が 0 を返すと推定され、0x417e4a で null 参照する。
- **入れたもの**:
  1. native 専用の `abortret=<VA>` case。trap helper の入口 (0x409730) の状態を trace hit で保存し、noncontinuable な `RaiseException` (flags & 1) で入口の return 状態へ戻す。既定 off。
  2. host の MXCSR の保存と復元 (`run_case`)。ゲストが MXCSR を 0 (全例外 unmask) にしたまま host の計算に入って SIGFPE になっていた (前 run の U8)。
  3. `ab_return` での signal mask の復元 (前 run の U10)。
- **trap 進入**: 5 件とも 0x409730 への進入が trace に残る。
- **判定はしていない**: trap の正しさ・予測式の検証は行わない (受入の範囲外)。

## 実装 (測定 commit `19a314897`)

- `tools/liftdiff/rt/ld_core.h`: case キー `abortret` (hex VA) を追加。wasm 側は読まない値。
- `tools/liftdiff/rt/ld_native.c`:
  - `on_sig` の trace hit で `abortret` の VA に入ったら `ab_save` が ucontext (gregs・fpregs・uc_sigmask) を保存する。
  - `ld_stub_c` で noncontinuable な `RaiseException` を受けたら、`ld_stub` の記録の後に `ab_return` を呼ぶ。`ab_return` は保存状態を `setcontext` で戻す: rsp+8・rip=入口の戻り先・rax=0。callee-saved・xmm・MXCSR・signal mask は入口の値。
  - `run_case`: `ld_ms_call` の前に host の MXCSR を `stmxcsr` で保存し、呼出し直後と fault 経路 (`else`) で `ldmxcsr` により戻す。ゲストの MXCSR (全例外 unmask) が host の `ld_native_ms` 計算 (`/ 1e6`) に効いて SIGFPE になっていた。
  - 保存状態は case ごとに初期化する。0x409730 は abort しか行わない (`0x4096d0` を必ず呼ぶ) ため、通常の return 後に古い保存状態を使うことは起きない。
- `tools/liftdiff/tests/trace_417b70_trap.py`: 各 case に `abortret=409730` を付ける。

## 完走させるために入れた stub (受入 2)

| stub | 変更前 | 変更後 (`abortret` 指定時のみ) |
|---|---|---|
| `RaiseException` (kernel32) | 既定 0 を返す。noreturn の後続を実行してしまう | noncontinuable (flags & 1) は trap helper 入口の return 状態へ戻す。呼出しは `calls` に記録 |
| `LoadLibraryA`・`LocalAlloc`・`GetProcAddress`・`MessageBoxA` | `RaiseException` の後の後続経路で呼ばれていた (MessageBoxA は既定 0) | `abortret` 指定時で、trap 入口の状態を保存した後の noncontinuable な `RaiseException` が戻すとき (`ab_return`) だけ呼ばれなくなる。既定 off では従来どおり。stub の実装は変更なし |

trap の判定は stub に入れていない。stub が決めるのは戻り先だけ。

## 実測 (測定 commit `19a314897`)

測定 commit は、コードを変えた最後の commit。HEAD は同じ commit の上に本付録と結果ファイルだけを積んだもの。

- 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/liftdiff/tests/trace_417b70_trap.py > tools/liftdiff/results/m11_417b70_trap_inputs.md`。rc=0・2 回の出力は一致 (`cmp`)。wall 0.58 s、load 3.98 (実行直前の `/proc/loadavg`)。素材: fl-win64 の `extracted/block00031_PE.bin`、work-liftdiff・work-m11 (worktree の gitignore 対象に展開)。ビルド: `rt/ld_native.c` を `liftdiff_e2e.sh` と同じ gcc コマンドで作り直した。
- 測定 commit 以降のコード差分 (WORKFLOW §6): `git diff 19a314897 HEAD -- tools/liftdiff/rt tools/liftdiff/tests` = 0 行。
- 出力の正本: `results/m11_417b70_trap_inputs.md` (2 行だけ変わった: 2^60 の 2 件が sigfpe → ok)。

| stride | count | 0x409730 進入 | 前 run (74510fd98) | 本 run (19a314897) | 終了位置の所見 |
|---:|---:|:---:|---|---|---|
| 16 | 1 | False | ok | ok | trap に入らない |
| -16 | 1 | False | segv 0x417e4a | segv 0x417e4a | trap に入らない (U6・対象外) |
| 16 | 2 | False | ok | ok | trap に入らない |
| -16 | 2 | True | segv 0x417e4a | segv 0x417e4a | 戻り後の確保 0x409470 が 0 を返すと推定 → 0x417e4a で null 参照 (U6) |
| -16 | 3 | True | segv 0x417e4a | segv 0x417e4a | 同上 |
| 16 | 2^60 | True | sigfpe | **ok** | 戻った後も完走。MXCSR の復元で解消 |
| -16 | 2^60 | True | sigfpe | **ok** | 同上 |
| 2^31-1 | 3 | True (確保内 0x4073c0 から) | segv 0x417e4a | segv 0x417e4a | 戻り後の確保が 0 を返すと推定 → null 参照 (U6) |

- 対照 (`abortret` を外した既定経路・本 run で実施): 2^60 の 2 件は segv (前 run の対照と同じ status。rip は本 run では再確認していない)。他の 3 件の status は前 run と同じ。`abortret` が無い限り ok にならない。
- MXCSR: 復元を入れる前は 2^60 の 2 件が sigfpe で、fault rip は host 側のアドレス空間 (`ld_native`)。復元後は両方 ok。SIGFPE を出した命令は特定していない (復元で消えたことだけ確認)。
- signal mask (`ab_save`・`ab_return`): trap 表は MXCSR の復元だけを入れた試作と同一 (status の変化なし)。現呼出しの状況では影響が見えないことを確認した。

### e2e (`liftdiff_e2e.sh --m11-only`)

- 実行: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/liftdiff/liftdiff_e2e.sh --m11-only` (測定 commit で 1 回)。rc=0・`LIFTDIFF_E2E PASS`・real 3 分 6 秒 (実測)。
- 内訳: [0/4] 単体テスト PASS、[1/4] build PASS、[3/4] `CHECK_INITUNITS PASS`・unit #18 の 3 件 PASS、[4/4] closure sample:800 = 一致 360 / 不一致 234 / 実行不能 206。`REPORT_APPENDIX_3557.md` の 2 回目 (360 / 234 / 206) と同値で、closure への回帰は見えない。
- 未実行: `--full` (closure 全数)、OTT 系 (`work-m6-ott` 素材が無い)。
- 注意: `ld_native` の変更は native 全体に効く (ゲストが MXCSR を変えた case だけ影響する)。`results/ld58_head_sample800_cases.tsv` の sigfpe 行は過去の測定で、再生成していない。

## 未解決

| ID | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U1' | 受入 1 未達: 残り 3 件 ((-16,2)・(-16,3)・(2^31-1,3)) は、戻った後の続きが null 参照で segv する。(a) 確保失敗の経路をモデル化する、(b) abort を call の終端として別 status にする | 受入 1 | #3563 (PM agent の判断待ち: (a)/(b)。既定案: 受入 1 は未達のまま #3563 に残し、(a)/(b) は #1767 の stride ≤ 0 調査の結果を待つ。新しい status は作らない) |
| U6 | `0x409470` が 0 を返して `0x417e4a` で null 参照する経路。終端 4 件 (trap 経由 3 件 + 非 trap の (-16,1)。(-16,1) の機構は未確認) | (a) の前提 | #1767 残 |
| U9 | wasm 側 (`ld_wasm.c`・`fle_ldbridge.c`) は `abortret` を持たない。trap 入力の native と wasm の結果は食い違う | native/wasm 比較で trap 入力を除外する必要がある | #3563 |

## 検証の範囲

- 実行 (測定 commit `19a314897`): trap 表 (8 件) を 2 回、既定 off の対照 (`abortret` 無し・8 件)、e2e `--m11-only`。
- 未実行: `--full`、OTT 系 e2e (素材無し)。wasm 側は変更していない (U9)。
