# 付録: liftdiff LD-159 (#3505) — 0x417b70 の呼出し元・呼出し規約と harness の修復

> **正本**: `tools/liftdiff/REPORT.md`。前段は `REPORT_APPENDIX_LD62.md` (親 #1767)。本書は LD-159 の実測と未解決を置く。

## 結論

- **前段の訂正**: 0x417b70 は『0x417b00 の prologue の途中』ではなく、`.pdata` に登録された関数の先頭 (RVA `0x17b70`〜`0x17fa3`)。前段の逆アセンブルは PE の raw offset を無視して平坦に読んだ誤りで、RVA → file offset は `.text` で `RVA - 0xc00`。正しく読むと `push rbp; push rbx; sub rsp,0x98; mov rbp,rsp` で始まる。
- **呼出し元**: PE 内の直接 call は 12 箇所 (E8/E9 rel32 の生走査と、`.pdata` 全 57,816 関数の capstone 走査で一致)。下表。
- **間接経路**: 8 バイトの絶対アドレスで 0x417b70 を持つ箇所は PE に無い。RIP 相対・即値での参照も call 以外に無い。IR 側は `m11_tr_function_417b70` (間接 call 用の trampoline) と、`function_417b70` の IR 内で `function_40d210` に渡す ptrtoint (`boot_final3.ll` 125420 行) がある。後者は対応する PE 側の参照を見つけられず、未判定 (U7)。
- **呼出し規約** (直接呼出し元 11 箇所で同一):
  - `rcx` = 配列 cell の番地 (`[rcx]` は配列データのポインタ、空なら 0)
  - `rdx` = record `R` (`R = rdx + byte[rdx+1]`、stride = `int32[R+2]`、ポインタ = `[R+6]`)
  - `r8` = 1 (全呼出し元で定数 1)
  - `r9` = count の番地 (`count = qword[r9]`)
- **rbp・r13・r14**: 0x417b70 は `rbp` を自分で設定し、先頭から 255 命令 (`0x417b70`〜`0x417fa2`) に `r13`・`r14` の参照は無い。呼出し時のこれらの値は入力に影響しない。記録の対象から外す。
- **segv の原因 (U1 の一部)**: 前段の 8 件 segv のうち、`(16,1)` と `(16,2)` は、harness が FL の起動時初期化を通していないことが原因だった。小サイズ用アロケータの大域ビン (`0x407a50` の `[rip+...]` 表) が 0 のままで、`0x407a97` の `mov 0x18(%rdx)` で落ちる。boot 状態 (`work/m11/boot_state.json`) を読み込むと両方とも `ok` になる。
- **残り 6 件**: count ≤ 0 と積の overflow の入力は trap helper `0x409730` に入る (trace に直接記録される)。しかし `0x409730` は abort 経路 (`0x4096d0` → `RaiseException`・`MessageBoxA`) で、harness の stub では戻らず、後段の `0x41d15a` で segv する。進入は記録できるが、run は完走しない (受入 2 は未達。子 issue へ移す)。

## 直接呼出し元 (PE, VA)

| call 箇所 | 所属関数 (pdata 先頭) | 引数の組み立て (要点) |
|---|---|---|
| `0x417f14` | `0x417b70` | 自己再帰 |
| `0x417fec` | `0x417fc0` | 第 1〜4 引数を素通し (`r8` = 第 3 引数) |
| `0x41834d` | `0x418280` | `r9 = &[rbp+0x48]` (count = `rsi`) |
| `0x4184e4` | `0x4183d0` | `rcx = &[rbp+0x50]` (cell は 0 で初期化) |
| `0x4186e0` | `0x4185a0` | `r9 = &[rbp+0x48]` (count = 外側の size) |
| `0x4187a0` | `0x418700` | count = `rsi+1` (負なら `0x40f560` へ) |
| `0x4663ff` | `0x4662c0` | `r9 = [rbp+0x98]` (呼出し元のポインタ) |
| `0x47c172` | `0x47c090` | count (`[rbp+0x450]`) が 0x80 より大きいときだけ呼ぶ |
| `0x47d47e` | `0x47d460` | `r9 = &[rsp+0x38]` (= 第 2 引数) |
| `0x47d701` | `0x47d6d0` | count = `[arg1+8]` 系 |
| `0x47d771` | `0x47d740` | count = `[arg1+8]` 系 |
| `0x95a7c7` | `0x95a5d0` | count = `int32` フィールド |

## 0x417b70 の内部 (harness に必要な読み出し)

- 最初に読むのは `[rcx]`・`[rdx+1]`・`[R+2]`・`[R+6]`・`[r9]` のみ。`[rcx] != 0` のとき `V = [rcx] - 0x10` の `[V+8]` を読む (配列の先頭要素の長さ)。
- `count > 0`: `product = count*stride` (`imul`)、`idiv count` の結果が stride と違えば `0x409730` (site1 = `0x417c62`)。`product+0x10 < 0` なら `0x409730` (site2 = `0x417c75`)。
- `count < 0`: `0x409730` (`0x417bc8`) の後、`0x418190` を呼んで戻る。
- `count == 0`: `0x418190` を呼んで戻る (trap に入らない)。
- 以降は `0x409410` (確保) と `0x409470` (大域ビンを使う小サイズ確保) を呼ぶ。確保が 0 を返すと `0x417e4a` の `mov dword [rax+4],1` で落ちる。

## 実測 (native, 8 入力)

測定 commit: `3a0f3f563` (`fix(liftdiff): call 0x417b70 with the caller convention and boot state`)。

- 再現コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/liftdiff/tests/trace_417b70_trap.py > tools/liftdiff/results/m11_417b70_trap_inputs.md` (rc=0・所要 0.64 秒 (シェル実測)・load 0.00 (起動直後の `/proc/loadavg`))。素材: `fl-win64` の `extracted/block00031_PE.bin`、`work-m11`・`work-liftdiff` (worktree に展開)。
- 同じ commit で 2 回実行し、出力は一致 (`results/m11_417b70_trap_inputs.md` と同一)。
- 出力の正本: [`results/m11_417b70_trap_inputs.md`](results/m11_417b70_trap_inputs.md)。

| stride | count | 前段 (LD-62) status | 本 PR status | 0x409730 進入 | FN 直後 | 本 PR の所見 |
|---:|---:|---|---|:---:|:---:|---|
| 16 | 1 | segv | **ok** | False | False | 確保は通る (boot 状態で解消) |
| -16 | 1 | segv | segv (`0x417e4a`, `rax=0`) | False | False | 確保 (`0x409470`) が 0 を返す。stride 負の入力の意味は未判定 (U6) |
| 16 | 2 | segv | **ok** | False | False | 同上 |
| -16 | 2 | segv | segv (`0x41d15a`) | True | True | trap → abort 経路で segv (U5) |
| -16 | 3 | segv | segv (`0x41d15a`) | True | True | 同上 |
| 16 | 2^60 | segv | segv (`0x41d15a`) | True | True | 同上 (site1 予測と一致) |
| -16 | 2^60 | segv | segv (`0x41d15a`) | True | True | 同上 |
| 2^31-1 | 3 | segv | segv (`0x41d15a`) | True | False | 途中 (`0x409470`→`0x407a50`→`0x407770`→`0x4073c0`→`0x409730`) で trap |

- 判定 (trap の正しさ・予測式の検証) はしていない。進入の有無は trace の記録のみ。
- 今回、0x409730 への進入は 5 件で、前段と同じ。`(16,1)`・`(16,2)` は trap に入らず完走する。

## 未解決

| ID | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U5 | trap 0x409730 の abort 経路 (`RaiseException`・`MessageBoxA` の stub) で戻らず segv する。進入を segv なしで完走させる方法が無い | 受入 2 (LD-159 元) | 子 issue LD-161 (#3563) |
| U6 | stride ≤ 0 の入力で確保が 0 を返す経路 (`0x417e4a` の segv)。呼出し元の契約 (stride > 0) との関係 | 入力の妥当性。判定しない | #1767 残 |
| U7 | IR の `function_40d210` への関数ポインタ渡し (`boot_final3.ll` 125420 行) の PE 側の対応 | 間接経路の完全性 | #1767 残 |
| U4 | sdiv 再実行での食い違い (判定基準の native が完走しない) | 受入 2 (LD-62 元) | #1767 残 (U5 完了後に再投入) |
</content>
