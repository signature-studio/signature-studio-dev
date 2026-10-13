# liftlib REPORT 付録 D — §22 LIFTLIB-9 (#668): RetDec raw lift 出力の非決定性

> 本体: [`REPORT.md`](REPORT.md) §22 (要約)。本付録は §22 の全文 (250 行上限のため分割移動・内容は削除していない)。
> 検証起点 commit: `8d883c3` (origin/main)。実装 commit: `5dc0117` (gate + probe)。担当 dir: `tools/liftlib/`。
> 既知類型との関係: `docs/DEFECTS.md` の D1〜D16 に **該当なし** (非決定性であり miscompile ではない。A7 段で吸収済み)。

## 22.1 結論

- 同一 PE・同一 ranges で RetDec を実行すると、**raw `*.drc.ll` は実行ごとに変わり得る**。差分は `uselistorder` 指示 (LLVM の use-list 順の指示) の行で、行の有無と並びが変わる。値の種類数は実行群により異なり、ASLR 有効の実行群 (n=2〜6) で 1〜6 種だった (§22.3 の分布表)。
- `uselistorder` 行を除くと、raw も `.drc.c` も全 run で一致する (probe の 8 本: ASLR 有効 4 本・無効 4 本で除去後 raw は 1 種、`.drc.c` も 1 種)。既存の A7 段 (`run_base` / `ir5_patch`) がこの行を除去するため、**liftlib base 段・m6 chain の出力は決定的**。
- ASLR (アドレス空間配置のランダム化) を無効にしても raw が一致しない事例がある (§22.4)。契機は未分離のため、決定性の手段にはしない。`setarch -R` は採らない。
- 対策は **比較手順の固定** (raw は比較しない・A7 後の成果物で判定) と **回帰 gate** (`lift_determinism_e2e.sh`)。新しい正規化 pass は不要。
- **未解決**: k80 (block18983_PE.bin, p0c REPORT §15.4) の alloca 並び差は OTT では再現せず、A7 後に残るかは未検証 (fl-win64 が必要)。→ 下記 §22.6 の起票先。

## 22.2 入力と条件

| 項目 | 値 |
|---|---|
| PE | `$ANALYSIS_DIR/plugins/ott/binaries/OTT_vst2_win64.dll` (3146752 B、`analysis-ott-binaries` 展開) |
| ranges | `tools/m6/work/ott_ranges.txt` (166 関数、`work-m6-ott` 展開) |
| RetDec | v5.0 (commit `53e55b4b26e9`。[RETDEC] `docs/REFERENCES.md`)。`--select-ranges` + `--select-decode-only --timeout 2400` |
| runner | nproc=4、`randomize_va_space=2` (ASLR 有効)、GitHub Actions runner |
| 1 run の所要 | 8.2〜9.0 秒 (probe の実測、load 0.6〜1.4) |

## 22.3 実測 1: raw は実行ごとに変わる (ASLR 有効 / 無効)

`bash tools/liftlib/lift_determinism_probe.sh 4` (HEAD `5dc0117`)。sha256 は先頭 12 桁。

| mode | run | ms | raw sha256 | uselistorder 除去後 | `.drc.c` | uselistorder 行数 |
|---|---|---|---|---|---|---|
| on (既定) | r1 | 8879 | 5bac875d2e33 | eb5685d8592b | 1945bf8a4a45 | 2548 |
| on | r2 | 8879 | 465ac159db7e | eb5685d8592b | 1945bf8a4a45 | 2550 |
| on | r3 | 8522 | 6d79bb6f829a | eb5685d8592b | 1945bf8a4a45 | 2547 |
| on | r4 | 8356 | 256e2e70e4f7 | eb5685d8592b | 1945bf8a4a45 | 2547 |
| off (`setarch x86_64 -R`) | r1〜r4 | 8305〜8744 | 279d6ee60f7d (4/4 同一) | eb5685d8592b | 1945bf8a4a45 | 2546 |

distinct (値の種類数): ASLR 有効 raw = **4/4**、uselistorder 除去後 = **1**、`.drc.c` = **1**。ASLR 無効 raw = 1 (この環境条件内)。

補足の実測 (前段で取得、同じ入力・同じ手順): ASLR 有効 6 本 (a1,a2,b1〜b4) の raw sha256 は全て別値。ASLR 無効 4 本 (n1〜n4) は 4/4 同一 `f2c8f229fd95`。a1 と a2 の raw 差分 26 行は全て `uselistorder` 行で、それを除くと両者は同一。

実行群ごとの分布 (ASLR 有効の raw。distinct = 値の種類数。全 PR 内実測の集計):

| 実行群 | 由来 | n | raw distinct |
|---|---|---|---|
| probe (`5dc0117`) | 本節の表 | 4 | 4 |
| 補足 a1,a2,b1〜b4 | 本節の補足 | 6 | 6 |
| gate N=2 (`5dc0117`) | §22.7 | 2 | 2 |
| gate N=4 (`5dc0117`) | §22.7 | 4 | 2 (`5bac875d2e33` ×3・`a782ad770357` ×1) |
| probe (`ae16a2f`、レビュー再実行) | PR review | 4 | 2 (`5bac875d2e33` ×3・`6d79bb6f829a` ×1) |
| gate N=2 (`ae16a2f`、レビュー再実行) | PR review | 2 | 1 (r1 = r2 = `5bac875d2e33`) |
| gate N=2 (`116cbb3`、修正後) | §22.12 | 2 | 2 |
| gate N=4 (`116cbb3`、修正後) | §22.12 | 4 | 3 |
| probe (`116cbb3`、修正後) ASLR 有効 | §22.12 | 4 | 4 |

→ 同じ条件でも一致する回と一致しない回がある。ASLR 有効の実行群では n=2〜6 で distinct は 1〜6 (min–max)。ASLR 無効 (`setarch -R`) の probe は 2 回 (`5dc0117` と `116cbb3`、計 8 本) とも 4/4 が `279d6ee60f7d` で同一。ただし 2 回とも同じ出力パス (`tools/liftlib/work/probe/off/r1/tmp` 等) を使っており、§22.4 のとおり条件で値が変わり得るため、決定性の根拠にはしない。

## 22.4 実測 2: ASLR 無効でも raw が一致しない事例 (契機は未分離)

同じ `setarch x86_64 -R` で、出力パスと TMPDIR のパスを変えた (1 行目と 3 行目)。レビュー再実行では TMPDIR の長さだけを変えた比較も行われた (4 行目)。

| 条件 | raw sha256 |
|---|---|
| 前段の n1〜n4 (TMPDIR = `$RUNNER_TEMP/det/n1/tmp`) | f2c8f229fd95 (4/4 同一) |
| 同じ条件で再実行 (`run1.sh $RUNNER_TEMP/det/n1 setarch x86_64 -R`) | f2c8f229fd95 (再現) |
| probe (TMPDIR = `tools/liftlib/work/probe/off/r1/tmp`、より長いパス) | 279d6ee60f7d (4/4 同一) |
| レビュー再実行: TMPDIR の長さだけを変えた 2 本 | 1c5f5c6a47bb (2 本同一) |

→ 同じ条件内では再現する (1・2 行目) が、出力パス・TMPDIR が変わると値が変わる事例がある (f2c8f229fd95 と 279d6ee60f7d は別値)。ただし TMPDIR の長さだけを変えた比較では 2 本とも同一 (1c5f5c6a47bb) で、「TMPDIR の絶対パス長で値が変わる」とは言えない。契機は**未分離**。`setarch -R` は決定性の手段として採らない (A7 後の判定で足りる)。

## 22.5 原因 (推定を含む)

- **実測で言えること**: 差分は LLVM の `uselistorder` 指示の行のみ (行の有無と並びが実行ごとに変わる。例: レビュー再実行の r1 と r4 の比較で `%1930` の追加、`%1795` と `i128 %186` の削除)。ASLR 有効時に値が変わることは §22.3 で実測。ASLR 無効時の変化の契機は未分離 (§22.4)。
- **推定**: RetDec / LLVM 内部で use-list を組むときに、ポインタ値に依存した順序 (ポインタを鍵にした集合・写像の走査) が使われている可能性がある。RetDec のソースが repo に無く、該当箇所は**未特定**。
- 除外した仮説: Python の hash seed (`PYTHONHASHSEED=1/2` で liftlib base 出力が同一、§22.7)、`.drc.c` の差 (0 件)、alloca 並びの差 (OTT の 8 本で 0 件: uselistorder 除去後が全て同一のため)。

## 22.6 対策と比較手順 (決定)

1. **比較対象は A7 後の成果物のみ**。raw `*.drc.ll` と中間物 (`*.norm0.ll` 等) は sha256 比較に使わない (`uselistorder` の順序で変わるため)。
2. 既存の A7 段 (`tools/liftlib/liftlib/passes/base.py:321-335`・`tools/m5/ir5_patch.py:260-271`、`tools/plugins/lift/passes/ir5_patch.py` も同系) が `uselistorder` 行を除去する。新しい正規化 pass は追加しない。
3. `setarch -R` は採らない (§22.4)。
4. 回帰 gate: `tools/liftlib/lift_determinism_e2e.sh` (§22.8)。

## 22.7 A7 後の一致 (決定性の実測)

| 対象 | 入力 | 結果 |
|---|---|---|
| liftlib `run_base` (A7 含む) | §22.3 の ASLR 有効 + 無効の raw 6 本 (a1,a2,b1,b2,n1,n2) | 6/6 同一 `c8fb37be3a24` |
| 同上、`PYTHONHASHSEED=1` / `=2` | a1 の raw | 両方 `c8fb37be3a24` (hash seed 非依存) |
| m6 chain (`m2/ir_normalize.py` → `m5/ir5_patch.py`) | raw a1, b2, n1 | 3/3 同一 `09b1b8128a88` |
| gate (`lift_determinism_e2e.sh`、N=2) | 新規 2 run | raw `b771dd2dab2c` / `efaddaf414a0` (不一致) → base 2/2 `c8fb37be3a24` PASS |
| gate N=4 (`DET_RUNS=4`) | 新規 4 run | raw は 2 種 (`5bac875d2e33` ×3、`a782ad770357`) → base 4/4 `c8fb37be3a24` PASS |

## 22.8 回帰 gate と probe (1 コマンド再現)

- `bash tools/liftlib/lift_determinism_e2e.sh` (既定 N=2、`DET_RUNS=N` で変更。N は 2 以上で、N<2 は比較 0 組で PASS させないため rc=2): RetDec を並列 N 回 → `run_base` → base.ll の sha256 が全て一致で PASS。不一致・ネガコン失敗・RetDec 失敗は全て非 0 で終了。前提欠落 (`ANALYSIS_DIR` 不在) は rc=2。
- 実測 (HEAD `5dc0117`、load は実行前後):

| 実行 | 結果 | 所要 | load |
|---|---|---|---|
| N=2 (既定) | PASS、`negctrl detected`、rc=0 | 総 20 s (RetDec 9 s) | 0.75 → 0.85 |
| N=4 (`DET_RUNS=4`) | PASS、`negctrl detected`、rc=0 | 総 28 s (RetDec 14 s) | 0.28 → 1.16 |
| ネガコン 2: `DET_NEGCTRL_NO_BASE=1` (A7 を外し raw を比較) | `determinism FAIL`、rc=1 | RetDec 8 s | 0.80 → 0.99 |
| 前提欠落 `ANALYSIS_DIR=/nonexistent` | rc=2 | — | — |

- ネガコン 1 (`negctrl`): base.ll に 1 行を足した複製が、同じ比較関数で不一致と判定される (比較器の盲点を検出)。
- ネガコン 2 は確率的: raw の全 run が偶然一致すると PASS (exit 0) する。本 HEAD の実測では raw は 2 本とも不一致 (`5bac875d2e33` / `2d296a991f9b`)、probe では 4 本中 4 種。

- `bash tools/liftlib/lift_determinism_probe.sh [N]`: §22.3 の表を出力 (既定 N=4。所要は §22.12 の実測)。

## 22.9 受入条件の達成状況 (Issue #668)

| 受入条件 | 状況 |
|---|---|
| 非決定の原因を特定し REPORT に実測を残す | **達成 (推定部分あり)**: 差分は uselistorder のみ、ASLR 依存。RetDec 内の箇所は未特定 (§22.5) |
| lift 成果物を決定的にする手段 / 比較手順を docs に定める | **OTT で達成**: A7 後 + 比較手順 (§22.6)。k80 は未 (下表) |
| 決定性の回帰検出 (sha256 比較、不一致で非 0) を e2e に入れる | **達成**: `lift_determinism_e2e.sh` (§22.8) |

PR は `Refs #668` (Closes は使わない)。k80 の実測が残るため。

## 22.10 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| k80 (block18983_PE.bin) の alloca 並び差 (`%0 = alloca i3` と `i64` の入替) と `k80.lift.ll` の 58 行差 (p0c §15.4)。OTT では再現せず、A7 後に残るかは未検証 | p0c の k80 系 before/after 比較は lift 段を揃えないと成立しない | 子 issue `[LIFTLIB-10]` #695 (fl-win64 が必要。`oc_artifacts` に `fl-win64` を追加して再実行を依頼) |
| RetDec 内部の use-list 順序を決める箇所 (ソース位置) が未特定 | 原因は推定のまま。A7 で運用上は吸収済み | 本件では上流報告しない (箇所未特定)。`[LIFTLIB-10]` の結果を見て判断 |
| 他 chain (`tools/plugins/lift/` の `lift_ranges.sh` など) の A7 後一致は未測定 | 同じ A7 系コードだが実測していない | 範囲外として明記。必要なら `[LIFTLIB-10]` で併せて測定 |
| `setarch -R` で決定的にできるか (環境条件を固定すれば足りるか) | 採らない方針 (§22.4) | 不要 (A7 で足りる) |

## 22.11 範囲外

- `tools/liftlib/liftlib_e2e.sh` (FreshAir・KH の素材を要する) は今回の `oc_artifacts` に無いため未実行。本 gate は OTT のみを使う。
- block18983_PE.bin / k80 は未使用 (fl-win64 不在)。k80 の数値は p0c REPORT §15.4 の既存記録のみ。

## 22.12 レビュー指摘への対応と修正後の再検証

PR #696 の oc-reviewer review (`ae16a2f`、CHANGES_REQUESTED) への対応。修正 commit `116cbb3` (`tools/liftlib/` のみ)。検証は `116cbb3` の HEAD で実施。

| 指摘 | 対応 |
|---|---|
| 1 repo 外絶対パス (§22.1 の RetDec・runner 行) | RetDec の実体は `[RETDEC]` (`docs/REFERENCES.md`) 参照に統一し、runner の作業 dir の記述は削除 |
| 2 §22.4 の機構 (TMPDIR 長で値が変わる) | 断定を撤回し、契機は未分離と明記。レビュー再実行 (TMPDIR 長のみ変更、1c5f5c6a47bb 同一) を §22.4 に併記 |
| 3 「毎回変わる」の過大 | 「実行ごとに変わり得る」に変更し、実行群ごとの分布表を §22.3 に追加 |
| 4 `lift_determinism_check.py` の docstring | 「必ず exit 1」を訂正 (raw が偶然一致すれば exit 0) |
| 5 `DET_RUNS=1` で比較 0 組のまま PASS | N<2 は rc=2 (`lift_determinism_e2e.sh` と `lift_determinism_check.py` の両方) |
| 6 「use-list 順」の不正確さ | 「`uselistorder` 指示の行 (行の有無と並び)」に統一 (§22.1・§22.5) |
| Copilot | `copilot-pull-request-reviewer` の review と inline コメントは 0 件 (2026-10-13 取得時点) |

検証 (HEAD `116cbb3`、runner nproc=4):

| 検証 | 結果 | 所要 | load (開始 → 終了) |
|---|---|---|---|
| `lift_determinism_e2e.sh` (N=2、既定) | PASS、negctrl detected、rc=0。raw `5bac875d2e33` / `35847e5a3fc2`、base 2/2 `c8fb37be3a24` | 総 17 s (RetDec 9 s) | 0.10 → 0.45 |
| `DET_RUNS=4 lift_determinism_e2e.sh` | PASS、negctrl detected、rc=0。raw 3 種 (`5bac875d2e33` ×2・`279d6ee60f7d`・`ef2320ee025b`)、base 4/4 `c8fb37be3a24` | 総 35 s (RetDec 20 s) | 0.50 → 2.31 |
| ネガコン 2: `DET_NEGCTRL_NO_BASE=1` (A7 を外す) | `determinism FAIL`、rc=1 (期待どおり) | RetDec 19 s | 0.50 → 2.69 |
| 前提・ガード: `DET_RUNS=1` / `DET_RUNS=abc` | rc=2 (RetDec 未起動) | — | — |
| `lift_determinism_check.py /nonexistent 1` | rc=2 | — | — |
| `lift_determinism_probe.sh 4` (ASLR 有効 / 無効 各 4) | raw: 有効 4 種 / 無効 1 種 (`279d6ee60f7d` 4/4)。除去後 raw・`.drc.c` は 8 本とも各 1 種 | 総 33 s | 2.13 → 2.08 |

静的確認: `bash -n` と `python3 -m py_compile` が通過。`find tools/liftlib docs -size +20M` は 0 件。`git diff --check` は clean。変更は `tools/liftlib/` と `docs/DOC_MAP.md` (付録 D の行数欄) のみ。

未解決は §22.10 のとおり (変更なし)。k80 の実測は `[LIFTLIB-10]` #695 で行う。

## 23. LIFTLIB-10 (#695): k80 (block18983_PE.bin) の alloca 並び非決定の実測

検証 HEAD: 本 PR 基点 (origin/main `67172db8`) + probe 入力差し替え。素材: `fl-win64` (`block18983_PE.bin` sha256 a399cbe060ec…)・`toolchain-retdec` (RetDec v5.0)・`work-liftlib`。
入力: `tools/plugins/lift/kernel_ranges_balance.txt` (80 ranges、1440 bytes、sha256 `2215d32093306b0c3d55e7552b6e0ff569afc5d8dab366b74b3ef834080dbb10`、`PROBE_PE` / `PROBE_RANGES` で指定)。runner は `pefile`・`capstone` が無いため `kernel_table.py` は実行せず、同梱の ranges を使った。初版の「136 ranges」は誤記で、ファイルは 80 件 (`0x…-0x…` の区間 80 件、カンマ区切り 1 行)。
実行: `PROBE_PE=… PROBE_RANGES=… PROBE_OUT=… bash tools/liftlib/lift_determinism_probe.sh 4`。RetDec 1 回 2.3 s、probe 全体 10 s、load 0.53 (開始 1 分値)。

### 23.1 probe 実測 (N=4)

| mode | run | rc | raw sha256 | no_uselist sha256 | c sha256 |
|---|---|---|---|---|---|
| ASLR on | r1 / r2 / r3 | 0 | 30ee3dbce31f | 5297dcfbd19d | 0e15e718a2e6 |
| ASLR on | r4 | 0 | b568d8f539cc | 5297dcfbd19d | 0e15e718a2e6 |
| ASLR off | r1〜r4 | 0 | 53942ce274fa (4 run 同一) | 07ad6a3a4ff9 | 0e15e718a2e6 |

distinct: ASLR on = raw 2 / no_uselist 1 / c 1。ASLR off = raw 1 / no_uselist 1 / c 1。

### 23.2 A7 後 (`lift_determinism_check.py`、N=4)

| mode | base.ll sha256 (4 run) | 判定 | negctrl |
|---|---|---|---|
| ASLR on | 48f92e937c00 (4 run 同一) | PASS | detected |
| ASLR off | 08f018fba946 (4 run 同一) | PASS | detected |

- **同一 ASLR 設定の中では A7 後に全 run 一致する。**
- **ASLR on と off の間では base.ll が一致しない** (48f9… ≠ 08f0…)。差は 58 行で、すべて `alloca` 行の入替 (`alloca i3`/`i64`/`i128`)。`alloca` 以外の行は差 0 件。p0c REPORT_APPENDIX_E §15.4 の 58 行差と同一の現象。
- A7 (`run_base`) は alloca の並びを正規化していない。ASLR 依存の順序は RetDec 内で決まり、A7 では消えない。

### 23.3 未達 (起票先: 子 issue)

- 受入条件のうち「alloca 並びの原因 (RetDec 内の順序か) の特定」と「決定化手段 (正規化 pass) の実装と回帰 gate 組込み」は本 run では未了。alloca 単位のソートによる正規化を試したが、`%N` 参照の付け替えが必要で単純ソートでは一致しなかった (36 行差が残る)。
- p0c REPORT §15.4 の注記更新は、ASLR 固定 (`setarch -R`) で lift する運用にするか、正規化を入れるかの決定後に行う。

### 23.4 LIFTLIB-11 (#887): alloca 正規化 pass と gate 組込み

HEAD `57cfa758` (canon 修正後の計測。修正前 `e8bf48e8` の計測は base sha `4bfa6e1003a5` が一致しており結論は変わらない)。素材: `fl-win64` (`block18983_PE.bin` sha256 `a399cbe060ec…`)・`toolchain-retdec` (RetDec v5.0)・`work-liftlib`。入力は 23.1 と同じ (`kernel_ranges_balance.txt`、80 ranges)。

**原因 (実測で言えること)**: 差分は `uselistorder` を除いた後も alloca 行の並びと、それに伴う `%N` 参照の付け替えだけ。関数内の alloca 連続 run は型が全て異なり (型の重複 0 件、8 本で確認)、型名順に並べ替えて参照を付け替えると ASLR on/off・run の差が全て消える (8 本の canon 後 sha256 が 1 種)。RetDec 内部の並びを決める箇所は未特定のまま (§22.5 の推定と同じ)。

**決定化**: `base.canon_alloca_order` (`tools/liftlib/liftlib/passes/base.py`) を追加。A7 (`run_base`) の後段で、関数ごとの連続 alloca run を型全体 (`align N` を除く) の文字列順に並べ、スロット名 `%N` は番号の昇順に振り直して `%N` 参照を付け替える。型キーを先頭トークンだけにすると `{ i32, i8 }` と `{ i64, i64 }` が同順 (tie) になり入力順に依存するため、型全体を使う。`run_base` の既定出力は変えていない (gate と呼び出し側のみ適用)。

**gate**: `lift_determinism_e2e.sh` は奇数 run を ASLR 有効、偶数 run を `setarch -R` (ASLR 無効) で混ぜる。入力は `DET_PE` / `DET_RANGES` / `DET_OUT` で差し替え可能 (既定は従来どおり OTT)。`lift_determinism_check.py` は base.ll に canon を適用して比較し、ネガコン 3 として「raw の alloca 並びを逆順にした複製」を使う。canon 後は一致、canon 無し (A7 のみ) では不一致になることを判定に含める (`canon-same/nocanon-DIFF`)。

| 検証 (HEAD `57cfa758`、runner nproc=4、RetDec v5.0 Linux 版を `/opt/retdec` へ symlink) | 結果 | 所要 | load (開始 → 終了) |
|---|---|---|---|
| `DET_RUNS=8 lift_determinism_e2e.sh` (k80, ASLR 混在) | PASS、negctrl detected、negctrl 3 OK (`canon-same/nocanon-DIFF`)、rc=0。base 8/8 `4bfa6e1003a5`、base_lines 10932。raw は 2 種 (`3c71a7a21caf`・`c2e915be5e2d`、情報のみ) | 総 12 s (RetDec 6 s) | 0.35 → 1.18 |
| `DET_NEGCTRL_NO_BASE=1` (A7 を外し raw を比較) | `determinism FAIL`、rc=1 (期待どおり) | 3 s | 1.08 → 1.08 |
| 既定 (`DET_RUNS` 未指定、N=2) | PASS、negctrl 3 OK、rc=0 | 4 s | 1.25 → 1.31 |

**raw 値の扱い**: raw sha256 は TMPDIR・出力パスの影響を受け得るため比較・記録の対象にしない (§22.6)。判定は base.ll (`4bfa6e1003a5`、全 run 一致) のみ。`tests/test_unit.py` T23 (合成入力・素材不要) は旧版 `e8bf48e8` で AssertionError、修正版 `75e332c8` で PASS を確認した。

**p0c 注記**: p0c REPORT_APPENDIX_B §15.4 に「lift 段を揃える手順」を 1 行追記した (本 run で更新)。OTT の `run_base` 既定出力は変えていない。`tools/plugins/lift/` の他 chain の canon 適用は未測定。
