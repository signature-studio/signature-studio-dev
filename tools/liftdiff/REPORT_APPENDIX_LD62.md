# 付録: liftdiff LD-62 (#1767) — 0x417b70 の除算 trap 入力の動的確認

> **正本**: `tools/liftdiff/REPORT.md`。前段の静的確認は `REPORT_APPENDIX_LD41.md`。本書は LD-62 の実測と未解決を置く。

## 結論

- harness の商計算は整数の 0 方向切り捨てに直した (旧 `int(p / cnt)` は `cnt ≈ 2^60` で誤る)。
- 0x417b70 を native (`work/ld_native`, `setarch -R`) で走らせた 8 入力のうち、trap helper 0x409730 に入ったのは 5 件、そのうち FN 直後に入ったのは 4 件。
- **全 8 件が segv する。** 確認した 2 件 (stride -16 count 2 / stride 2147483647 count 3) は fault 位置が `rip_rva=0x1d15a` (fault addr `0x810470ff8`) で同じ。原因は未特定 (未解決 U1)。
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

- 手順: `boot_final3.ll` の 125366 行 `%29 = udiv i64 %28, %arg4` だけを `sdiv` に変えた IR (`tools/m11/work/boot_final3_sdiv.ll`) から wasm を作り (`work/m11_sdiv`、ビルド 8.1 秒・rc 0)、udiv 版 (`work/m11`) と同じ 8 入力で native と比べる。
- 再現: `FL_WIN64_DIR=<展開先> python3 tools/liftdiff/tests/trace_417b70_sdiv_rerun.py > tools/liftdiff/results/m11_417b70_sdiv_rerun.md` (rc 0・所要 11.9 秒・load 0.78 (起動直後))。
- 結果: [`results/m11_417b70_sdiv_rerun.md`](results/m11_417b70_sdiv_rerun.md)。
  - native は 8 件すべて `segv` (除算より前。stride 16 count 1 は `rip_rva=0x7a97`、stride -16 count 1 は `0x17e4a` で fault 位置が入力ごとに違う)。
  - udiv 版・sdiv 版 wasm は 8 件すべて `trap`。比較は全件 `both_fault` で、**sdiv 化で食い違いが消えたかは判定できない** (U4 未達)。
  - wasm の trace 先頭は udiv / sdiv で差がある (例: stride 16 count 1 は sdiv 版が `0x409410 → 0x407a50 → 0x407770 → 0x409730` と trap へ入る)。ただし native が先に segv するため、この差が正しいかは判定できない。
- 未達の原因: native 側が 8 入力すべて除算に到達しない。入力の struct 配置 (U1・U3) が未解決のため、比較の基準が無い。
