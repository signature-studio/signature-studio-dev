> **正本**: `tools/targets/serum2/license/authstub/REPORT.md` §14。本書は #1009 (SR-12) の受入 2・3 (前後 site 数表・ネガコン・再計算手順) の全文。

## 14f. L1 復元 pass の前後 census の再計算とネガコン (#1009)

- 再計算: `python3 l1_recompute.py <PE> <raw.ll> <outdir>` (`authstub/`)。raw lift を base 修復した IR (pass 無し = 脱落状態 `raw_base.ll`) と、その上に `liftlib.passes.l1_restore.restore_l1` を適用した IR (pass 有り `raw_l1.ll`) を作り、両方に `l1_census.py` を実行する。数え方の定義は §13b。
- 照合 (fail-closed・不一致で SystemExit): pass 無しは `dec_label_pc_1800c2ef4` 無し・被覆 0・直接 call 0・入口 edge 0。pass 有りは block 有り・直接 call 1・入口 edge 1 以上。機械語側 3 指標 (直接 call sites・edx 即値・入口 edge) は PE だけから計算されるため、両者で同値になるのが構造上当然である。`l1_recompute.py` はこの同値のみを照合し、期待値 (sites=1・edx_const=1・into=1) は照合しない。両 IR を `llvm-as-18` で検査する。
- ネガコン: (a) pass 無し (`raw_base.ll`) が脱落状態そのもの。pass を外すと復元された辺・block・被覆が消える。(b) 同じ IR に pass を 2 回適用すると `二重適用` で SystemExit (スクリプト内で確認)。

### 再現

```sh
# 素材: plugins-serum2 の Install_Xfer_Serum2_2.1.5.exe から 7z で VST3 を取り出す (REPORT §11 と同じ手順)
cd tools/targets/serum2/license/authstub
bash e2e.sh                                  # step [1] が work/lift/authstub.drc.ll を作る
python3 l1_recompute.py ../../work/Serum2_win64.vst3 work/lift/authstub.drc.ll work/l1
```

### 実測

- 測定 commit: `054a94b5` (コードを変えた最後の commit = `l1_recompute.py` の追加)。
- 入力: `Serum2_win64.vst3` sha256 `501e7bb3…5283` (19,236,864 B、展開後に一致確認)。raw lift `authstub.drc.ll` 710,975 B・sha256 先頭 16 桁 `5ce6d287d370ef96` (§14c と同じ lift)。
- e2e cold (`work/` 削除後・`TMPDIR=$RUNNER_TEMP`・開始時 load 0.27): rc 0・real **35.3 s**・**23/23 PASS**。pass は e2e チェーンに入っていないため、不変確認である。
- `l1_recompute.py` (同 lift): rc 0・real 2.8 s・`l1_recompute OK`。二重適用は `0x1800c2ef4 ブロックが既に存在する (二重適用)` で SystemExit。
- 出力 IR sha256 先頭 16 桁: `raw_base.ll` `3523d0400d43ec2a`・`raw_l1.ll` `67c9af539303f7f9`。
- 差分 0 の証跡 (WORKFLOW §6): `git diff 054a94b5 HEAD -- tools/targets/serum2/license/authstub/*.py tools/liftlib tools/targets/serum2/license/authstub/e2e.sh` の出力は 0 行 (HEAD = `5ed692f6` 時点で確認。以降の commit は本文書のみ)。

census (`l1_census.py` の 10 指標を再計算した値):

| 指標 | pass 無し (raw_base) | pass 有り (raw_l1) |
|---|---|---|
| machine: 直接 `call [reg+0x30]` sites | 1 | 1 |
| machine: `edx=0x800010` loads | 1 | 1 |
| machine: 入口 edge (edges into site block) | 1 | 1 |
| IR: `insn.addr` 被覆 (site 範囲) | 0 | 4 |
| IR: site 範囲の命令数 | 0 | 15 |
| IR: 直接 call (site 範囲) | 0 | 1 |
| IR: `edx=0x800010` 即値 (site 範囲) | 0 | 1 |
| IR: `0x800010` 即値 (ファイル全体) | 1 | 2 |
| IR: br/switch の入口 edge | 0 | 1 |
| IR: block `dec_label_pc_1800c2ef4` | 不在 | 存在 |

- 機械語側 3 指標は PE 由来のため両列で同値になる (pass は機械語側を変えない。この列の一致は検証の根拠ではない)。pass が変えるのは IR 側の行だけである。
- 注: 本表の pass 有り列は §14e の `raw_l1` 列 (store 込み) と同じ値である。`raw_base` 列は §13b の脱落状態と同じ値である。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 復元 call の実行時 (wasm) の BLK 値の実測 (IR 上の界面一致までは §14e で確認済み) | 実行時の不一致は未検出 | #1228 (SR-16。e2e 組込みと同じ工程で実測) |
| 復元 pass の e2e チェーン組込み (適用順は N2b 優先) | e2e 23/23 は pass 無しの patched 経路の値 | #1228 (SR-16) |
