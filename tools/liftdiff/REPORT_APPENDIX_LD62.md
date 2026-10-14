# 付録: liftdiff LD-62 (#1767) — 0x417b70 の除算 trap 入力の動的確認

> **正本**: `tools/liftdiff/REPORT.md`。前段の静的確認は `REPORT_APPENDIX_LD41.md`。本書は LD-62 の実測と未解決を置く。

## 結論

- harness の商計算は整数の 0 方向切り捨てに直した (旧 `int(p / cnt)` は `cnt ≈ 2^60` で誤る)。
- 0x417b70 を native (`work/ld_native`, `setarch -R`) で走らせた 8 入力のうち、trap helper 0x409730 に入ったのは 5 件、そのうち FN 直後に入ったのは 4 件。
- **全 8 件が segv する。** 確認した 2 件 (stride -16 count 2 / stride 2147483647 count 3) は fault 位置が `rip_rva=0x1d15a` (fault addr `0x810470ff8`) で同じ。原因は未特定 (未解決 U1)。fault 位置と除算命令 (`0x417c56`) の対応は下の sdiv 節の表にある。
- 予測と不一致の行が 1 件ある (`stride 2147483647, count 3`。未解決 U2)。

## 測定

- trap 側の測定 commit: `1e4d805e` (LD-62 の predict 整数化)。`git diff 1e4d805e HEAD -- tools/liftdiff/tests/trace_417b70_trap.py` は 0 行。
- 境界値側 (`trace_417b70_boundary.py`) は重複 cnt の削除で変更した。測定 commit はその修正 commit (PR 本文に記載)。
- 再現コマンド (rc=0, 所要 1.21 秒 (シェル実測), load 未計測。素材: `fl-win64` は `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`、`work-liftdiff` と `work-m11` を worktree の `tools/liftdiff/work/` と `tools/m11/work/` に展開):

  ```sh
  FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/liftdiff/tests/trace_417b70_trap.py > tools/liftdiff/results/m11_417b70_trap_inputs.md
  ```

- 出力の正本: [`results/m11_417b70_trap_inputs.md`](results/m11_417b70_trap_inputs.md) (生成物)。
- 境界値の計算: `python3 tools/liftdiff/tests/trace_417b70_boundary.py > tools/liftdiff/results/m11_417b70_div_boundary.md` (素材不要)。
  - 出力: [`results/m11_417b70_div_boundary.md`](results/m11_417b70_div_boundary.md)。
  - p = k·cnt + r (k ∈ {1,2,3,5,7,16,1000,2^31−1}, r ∈ {−1,0,1}) の 4 種の cnt (計 96 件) を exact (Fraction) と比べると、旧式は 31 件不一致、新式は 0 件。
  - cnt の重複 (`(1<<60)+1` と `1152921504606846977` は同値) は除いてある。旧式で `cnt = 2^60+1` の 1 行だけ見ると 8 件不一致。

## 実測 (native, 8 入力)

| stride | count | 予測 site1 | 予測 site2 | native status | 0x409730 進入 | FN 直後 |
|---:|---:|:---:|:---:|---|:---:|:---:|
| 16 | 1 | False | False | segv | False | False |
| -16 | 1 | False | False | segv | False | False |
| 16 | 2 | False | False | segv | False | False |
| -16 | 2 | False | True | segv | True | True |
| -16 | 3 | False | True | segv | True | True |
| 16 | 2^60 | True | False | segv | True | True |
| -16 | 2^60 | True | False | segv | True | True |
| 2147483647 | 3 | False | False | segv | True | False |

trace 先頭 (`t[0]` は hex 文字列。全文は results 側):

- stride 16 count 1: `0x417b70, 0x409470, 0x407a50` … (trap へ入らない)
- stride -16 count 2: `0x417b70, 0x409730, 0x4096d0, 0x4096b0, …` (FN 直後に trap)
- stride 2147483647 count 3: `0x417b70, 0x409470, 0x407a50, 0x407770, 0x4073c0, 0x409730, …` (FN 直後ではなく途中で trap)

## 未解決

| ID | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U1 | 8 件すべて segv。確認した 2 件 (stride -16 count 2 / stride 2147483647 count 3) は fault 位置 `rip_rva=0x1d15a` (`0x810470ff8`) が同じで、calls に `MessageBoxA` が出ている。segv の原因と、segv 前の trace で trap 進入を観測してよいかは未判定 | trap 進入の判定の信用度。受入条件 1 の確定 | #1767 残 |
| U2 | 予測と不一致: `stride 2147483647, count 3` は site1/site2 とも予測 False だが `0x409730` に入る (trace 6 件目で入り、FN 直後ではない)。予測式の前提 (どの経路で trap に入るか) がこの入力で成り立たない理由は未判定 | 予測式の妥当性。判定結果そのものは未確定 | #1767 残 |
| U3 | 正の stride (16) の入力が trap に入らない原因 (struct 配置) | 受入条件 1 の一部 | #1767 残 |
| U4 | sdiv (符号付き) 再実行で食い違いが消えるか | 受入条件 2 未達 | #1767 残 |

## sdiv 再実行 (受入条件 2・U4)

### 手順 (commit 済み・work/ の生成物に依存しない)

1. `python3 tools/m11/m11_sdiv_variant.py`: 素材 `work-m11` の `tools/m11/work/boot_final3.ll` を読む。行 125366 が `  %29 = udiv i64 %28, %arg4` と一致するのを確かめてから、その 1 行だけ `sdiv` に変えた `tools/m11/work/boot_final3_sdiv.ll` を書く。`tools/liftdiff/targets/m11.json` の `name` を `m11_sdiv`、`ir` を上の IR に差し替えて `tools/liftdiff/work/m11_sdiv/target.json` を書く。
2. harness `trace_417b70_sdiv_rerun.py` が 1 を呼び、`m11_sdiv` を `build_wasm.build` でビルドしてから、udiv 版 (`work/m11`) と sdiv 版を同じ 8 入力で流す。

### 再実行の実測 (測定 commit: `dfab4e7f`。以後 HEAD `018993a7` までのコード差分は 0 行、main 取り込みのみ)

- 素材: `fl-win64` は `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`、`work-m11` と `work-liftdiff` は worktree の `tools/m11/work/`・`tools/liftdiff/work/` に展開。
- 再現コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/liftdiff/tests/trace_417b70_sdiv_rerun.py > tools/liftdiff/results/m11_417b70_sdiv_rerun.md` (rc=0・所要 19.7 秒・load 0.22 (起動 8 分後の 1 分値))。
- sdiv 版 wasm のビルド: `[build] OK ... 'sig_mismatch': 0, 'undefined': 1` (link 3.2 秒)。

### 結果

[`results/m11_417b70_sdiv_rerun.md`](results/m11_417b70_sdiv_rerun.md) の 8 行。

- native は 8 件すべて `segv`。udiv 版・sdiv 版 wasm は 8 件すべて `trap`。比較は全件 `both_fault`。
- **sdiv 化で食い違いが消えたかは判定できない** (U4 未達)。native が 8 件とも segv するため、比較の基準が無い。

### native の fault 位置と除算命令 (指摘 2 への回答)

除算命令は 0x417b70 の中に `idivq` 1 件だけ (`0x417c56`・`idiv qword ptr [rbp+0x60]`・`objdump -D -b binary` で確認。RVA は PE の `0x400000` 基準)。`0x17b70` から fall-through / 直接 jump だけで辿った関数内 230 命令の CFG (`capstone`) で、idiv を経由せずに到達できる命令は 56 件だった。

| stride | count | native status | `rip_rva` | fault 命令 | trace (0x417b70 の次の関数入口) | その入口を呼ぶ call 箇所 (0x417b70 内) |
|---:|---:|---|---|---|---|---|
| 16 | 1 | segv | `0x7a97` | `mov 0x18(%rdx),%rax` (0x407a50 内) | `0x409470` → `0x407a50` | `0x417d8a` / `0x417d99` (idiv の後) |
| -16 | 1 | segv | `0x17e4a` | `movl $1,0x4(%rax)` (0x417b70 内) | `0x409470` | `0x417d8a` / `0x417d99` (idiv の後) |
| 16 | 2 | segv | `0x7a97` | 同上 (0x407a50 内) | `0x409470` → `0x407a50` | `0x417d8a` / `0x417d99` (idiv の後) |
| -16 | 2 | segv | `0x1d15a` | `mov (%rax,%rcx,8),%rax` (0x41d110 内) | `0x409730` → … → `0x41d110` | `0x417c62` / `0x417c75` (idiv の後) |
| -16 | 3 | segv | `0x1d15a` | 同上 | 同上 | 同上 |
| 16 | 2^60 | segv | `0x1d15a` | 同上 | 同上 | 同上 |
| -16 | 2^60 | segv | `0x1d15a` | 同上 | 同上 | 同上 |
| 2147483647 | 3 | segv | `0x1d15a` | 同上 | `0x409470` → `0x407770` → `0x4073c0` → `0x409730` → … | `0x417d8a` / `0x417d99` (idiv の後) |

読み方:

- 8 件とも、0x417b70 から最初に出る関数 call は idiv の後の call 箇所から呼ばれている (`0x417d8a`・`0x417d99`・`0x417c62`・`0x417c75`)。idiv を通らずに届く call は `0x417bc8` と `0x417bdb` だけで、どちらも count ≤ 0 の枝にある。入力の count は全件正なので、この枝は通らない。したがって 8 件とも idiv を実行した後の経路に入っている (trace 上の関数入口の呼び出し元による推論)。
- `-16` count 1 だけは fault 命令 `0x417e4a` が 0x417b70 内にあり、idiv `0x417c56` より後の分岐にある (CFG で確認。idiv を経由せずに到達できない)。
- 残り 7 件の fault 命令は 0x417b70 の外 (`0x407a97`・`0x41d15a`) にある。fault が idiv の後かは、呼び出し経路 (上の表の右端) が idiv の後であることから言える。
- 除算結果が正しい値だったかは未判定。

**結論**: 「8 件すべて除算より前に segv」は誤り。8 件とも、0x417b70 から除算を経由する call 経路の先で fault している (`-16` count 1 は fault 命令自体が除算の後)。残り 7 件は fault 命令が 0x417b70 の外にあり、「除算の後」は呼び出し経路からの推論。除算結果の正しさは未判定。U4 の『判定不能』の結論は維持する (native 基準が無いため、sdiv 化の効果は比べられない)。

### 未達の原因

native 側が 8 入力すべて segv するため、sdiv 化の効果を比べる基準が無い。入力の struct 配置 (U1・U3) が未解決のため、比較の基準は作れていない。
