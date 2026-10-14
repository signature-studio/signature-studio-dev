# liftlib REPORT 付録 (#1560 CI-28) — raw `drc.ll` の扱いの決定

> 親: [`REPORT_APPENDIX_D.md`](REPORT_APPENDIX_D.md) §22・§23 (LIFTLIB-9 #668・LIFTLIB-10/11 #695・#887)。
> 本付録は CI-28 (#1560) の決定と実測。`REPORT_APPENDIX_D.md` は 250 行上限のため分割して別置き。
> 検証 HEAD: `d16d7f5d` (origin/main)。担当 dir: `tools/liftlib/`。

## 1. 決定

**(b) を採る。比較は必ず正規化後 (`run_base` + `canon_alloca_order`) の `base.ll` で行い、raw `drc.ll` の sha256 は比較・受入に使わない。**

理由:
- raw の差は `uselistorder` 行の有無・並びと alloca 並びで、RetDec 内部 (LLVM use-list 順) に起因する。RetDec のソースは repo に無く、決定化は上流の修正になる (`REPORT_APPENDIX_D.md` §22.5: 箇所未特定)。(a) の実装は RetDec 本体の改変を伴い、この issue のスコープ外。
- 正規化後の `base.ll` は既に全 run 一致が実測済み (`REPORT_APPENDIX_D.md` §23.4・下記 §2)。判定に必要な決定性はこれで足りる。
- raw の sha256 を一致させても、比較手順の決定性 (`REPORT_APPENDIX_D.md` §22.6) への寄与がない。

定義の明記先: `tools/liftlib/lift_determinism_e2e.sh` の冒頭コメント・`lift_determinism_check.py` の docstring (既存)、本付録。p0c REPORT の受入 2' は「決定により対象外」とする。

## 2. 実測 (k80・raw 差の確認)

| 項目 | 値 |
|---|---|
| HEAD | `d16d7f5d` (origin/main) |
| 入力 | `block18983_PE.bin` (sha256 `a399cbe060ec…`、`fl-win64`) / `tools/plugins/lift/kernel_ranges_balance.txt` (80 ranges) |
| 素材 | `fl-win64`・`toolchain-retdec` (RetDec v5.0、`/opt/retdec`) |
| コマンド | `DET_PE=… DET_RANGES=… DET_OUT=… DET_RUNS=4 bash tools/liftlib/lift_determinism_e2e.sh` |
| 結果 | PASS、negctrl detected、negctrl 3 OK (`canon-same/nocanon-DIFF`)、rc=0 |
| 所要 | 総 6 s (RetDec 並列 4 本 3 s)、load 1.01 → 1.01 |

| run | raw sha256 (情報のみ) | base sha256 (判定) | base 行数 |
|---|---|---|---|
| r1 | `dea06288b922` | `4bfa6e1003a5` | 10932 |
| r2 | `9dfaa0f8587f` | `4bfa6e1003a5` | 10932 |
| r3 | `dea06288b922` | `4bfa6e1003a5` | 10932 |
| r4 | `9dfaa0f8587f` | `4bfa6e1003a5` | 10932 |

raw は 2 種に割れ、base は 4/4 同一。今回の raw の 2 種は偶数 run (ASLR 無効) と奇数 run (ASLR 有効) で分かれたが、`REPORT_APPENDIX_D.md` §22.3 のとおりこの対応は常には成立しないため、判定の根拠にしない。(a) を採らない根拠として、raw 不一致が実在することを本 run で再確認した。

## 3. 残り

- 上流 (RetDec) の use-list 決定化: 箇所未特定のため起票しない (`REPORT_APPENDIX_D.md` §22.10 と同じ扱い)。
- p0c REPORT の受入 2' は「決定により対象外」とし、raw 一致は受入に使わない (`tools/plugins/p0c/REPORT.md` の表を更新済み)。
