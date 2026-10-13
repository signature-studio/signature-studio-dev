# #930 (LD-20): 消費者形 pure 残 23 関数 (24 引数) の残件測定 — 部分達成

**判定: 部分達成**。修復の追加はせず、残件の分類 (§3)・ネガコン (§4)・survey 到達の再測定 (§2) を取った。支配関係つきの修復 (entry 外 deref の 18 関数 = 素 13・ptr 4・w32 1) は未着手で、子 issue #1134 に分けた (§5)。

先行: #734 (`REPORT_734.md`)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 残 23 関数 (24 引数) のうち entry 外 deref の 18 関数 (19 引数。素 13・ptr 4・w32 1) を支配関係つきで修復、または不能理由を関数ごとに記録 | **一部**。関数ごとの最初の deref 位置を §3 に前回記録として載せた (本 PR では未再現)。支配関係つきの修復は未着手 (§5 の子 issue #1134) |
| tracker-no-deref (3 関数) と none (5c44b0) の理由を記録 | **一部**。tracker-no-deref (3 関数) は「記号実行が deref を見ない」という現象のみを記録 (理由は未特定)。5c44b0 は理由未特定。理由の特定は #1134 |
| `ir_conditions.json` を作り直した IR で `reach_509.sh` を実行し、survey 到達を記録 | **達成**。23 関数・942 unit で実測 (§2)。到達 (kind=ok) は 44f040・47ad70 の 2 関数、残 21 関数は 0 |
| ネガコン (修復を外すと SUSPECT_USE が復帰) | **REPORT_734 の既存測定と一致 (再実行なし)**。§4 (ptr 分岐の直前版 30 関数 / 33 引数 → 現行 23 / 24) |

## 2. survey 到達の実測 (`reach_509.sh`)

- 測定 commit: `92cfb784` (main 作業ツリーのコード。IR 生成・build・計装はこの commit の `tools/m11`)。
- 手順: `m11_gen_ir2.sh` (rc 0・ldfix=applied) → `m11_build.sh` (rc 0・wasm-ld signature mismatch 0 / undefined symbol 0) → `ldfix/reach_509.sh` (23 関数を計装)。
- 出力 JSON: `results/reach_930.json` (942 unit)。
- 所要 (実測): gen_ir2 44.6 s / build 25.5 s / reach 22.3 s。load average 1.2 前後。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-m11` → `tools/m11/work/`、`toolchain-emsdk` → `[EMSDK]` (emcc 6.0.12)。

### 2.1 kind 別の集計

kind 分布 (942 unit): ok 870 / miss 47 / oob 16 / halt0 7 / other 1 / noproc 1。

「到達」の定義: **kind=ok の unit で、その関数の入口計装が 1 回以上 hit した**。halt0・oob・miss で hit した unit は到達に含めない。

| 関数 | kind=ok で hit した unit | 入口通過 (ok のみ) | 参考: 他 kind で hit した unit |
|---|--:|--:|---|
| 44f040 | 1 | 1 | oob 2 |
| 47ad70 | 5 | 10 | halt0 1・oob 1 |
| 40fe90 | 0 | 0 | oob 1・halt0 1 |
| 上記以外の 20 関数 | 0 | 0 | — |

- 到達あり 2 関数 (44f040・47ad70)、0 件 21 関数。
- 前回 REPORT の「40fe90 2 unit / 44f040 3 unit / 47ad70 7 unit」は kind を区別しない数字で、到達の定義に合わない。撤回し、上の表で置き換える。
- 前回 #509 の `results/reach_509.json` の kind 分布 (ok 852) と今回 (ok 870) は一致しない。計装 VA と IR の生成条件の差が原因と思われるが、切り分けは未実施。survey の退行判定にはこの差を使わない。

## 3. 関数ごとの残件 (use_residual_509.py の門 + 最初の deref 位置)

最初の deref 位置は前回 run の記録 (`f3c_track` の記号実行による機械語の VA)。本 PR では再現していない (deref 位置は今回の測定対象外)。`ptr` は IR のヘッダ型。分類の件数 (18 / 23 関数) は今回の `use_residual_509.py` の門による分類。survey 到達は §2.1 の実測。

| 関数 | 引数 | 分類 | 最初の deref (前回記録・未検証) | IR ヘッダ型 | survey 到達 (kind=ok) |
|---|---|---|---|---|---|
| 101d180 | arg3 | first-deref-not-entry | 101d477 | i64 | 0 |
| 1050f90 | arg2 | first-deref-not-entry+w32 | 1051098 | i64 | 0 |
| 1050f90 | arg3 | first-deref-not-entry+w32 | 105114c | i64 | 0 |
| 10626e0 | arg3 | first-deref-not-entry+ptr-arg | 1062752 | ptr | 0 |
| 10628d0 | arg1 | first-deref-not-entry | 10628d8 | i64 | 0 |
| 12f9730 | arg3 | first-deref-not-entry | 12f9872 | i64 | 0 |
| 40fe90 | arg1 | first-deref-not-entry | 40fe99 | i64 | 0 (oob・halt0 のみ) |
| 41b8d0 | arg1 | first-deref-not-entry | 41b8de | i64 | 0 |
| 41b970 | arg1 | first-deref-not-entry | 41b97e | i64 | 0 |
| 449550 | arg4 | first-deref-not-entry | 44957e | i64 | 0 |
| 44f040 | arg1 | first-deref-not-entry | 44f069 | i64 | 1 |
| 44fb40 | arg1 | first-deref-not-entry | 44fb71 | i64 | 0 |
| 47ad70 | arg2 | first-deref-not-entry | 47ad82 | i64 | 5 |
| 5c44b0 | arg2 | none | 5c44bf | i64 | 0 |
| 6905f0 | arg2 | first-deref-not-entry | 69072a | i64 | 0 |
| 75a180 | arg4 | tracker-no-deref | (deref 無し) | i64 | 0 |
| 784ed0 | arg1 | first-deref-not-entry+ptr-arg | 784f36 | ptr | 0 |
| 786d50 | arg3 | first-deref-not-entry+ptr-arg | 787019 | ptr | 0 |
| 787380 | arg3 | first-deref-not-entry+ptr-arg | 78753f | ptr | 0 |
| c40420 | arg4 | first-deref-not-entry | c4065b | i64 | 0 |
| db6480 | arg4 | tracker-no-deref | (deref 無し) | i64 | 0 |
| dc27c0 | arg2 | tracker-no-deref | (deref 無し) | i64 | 0 |
| ddd4d0 | arg2 | ptr-arg | ddd4e9 | ptr | 0 |
| f552a0 | arg1 | first-deref-not-entry | f552b6 | i64 | 0 |

- **first-deref-not-entry 18 関数 (素 13・ptr 4・w32 1)**: 最初の deref が entry ブロック外。修復には IR のブロック支配関係が要る。ptr 付きは 10626e0・784ed0・786d50・787380 (4 関数)、w32 付きは 1050f90 (1 関数、2 引数)。到達は 44f040・47ad70 の 2 関数のみ (kind=ok)。
- **tracker-no-deref 3 関数 (75a180・db6480・dc27c0)**: audit は機械語の deref を見るが、ldfix の記号実行は deref を見ない (現象。理由は未特定)。到達は 0 件のため、survey 上では修復の効果を測れない。
- **none (5c44b0)**: どの門にも掛からないが、`fix_f3c_use` の置換対象になっていない理由は未特定。最初の deref (5c44bf) は entry ブロック内。到達は 0 件。
- **ptr-arg 1 (ddd4d0)**: ptr 型引数だが、最初の deref は entry 内。REPORT_734 の PR 版 SUSPECT_USE に残る既知の関数。到達は 0 件。

分類語の定義 (`use_residual_509.py` の門): `first-deref-not-entry` = 最初の deref のブロックが entry 外 / `ptr-arg` = 引数の IR 型が ptr / `w32` = 32bit deref を含む / `tracker-no-deref` = 機械語には deref があるが記号実行の tracker が見つけない / `none` = どの門にも掛からない。

## 4. ネガコン (修復の有無で SUSPECT_USE が変わること)

数値の出所は REPORT_734 §(NC 行、表 Line 14・23〜26)。今回の PR では再実行していない。

| ldfix.py | suspect_use 関数 / 引数 |
|---|--:|
| `7db8953b^` (ptr 分岐の直前) | 30 / 33 |
| 現行 `origin/main` (ptr 分岐あり) | 23 / 24 |

ptr 分岐を外すと SUSPECT_USE が 7 関数 / 9 引数だけ戻る。REPORT_734 の数値と一致する。

## 5. 未実施と残件

| 残件 | 件数 | 起票先 |
|---|--:|---|
| entry 外 deref の支配関係つき修復 (first-deref-not-entry 18 関数 = 素 13・ptr 4・w32 1) | 18 関数 (19 引数) | 子 issue #1134 (LD-34) |
| tracker-no-deref (75a180・db6480・dc27c0) の記号実行の修正 | 3 関数 | 子 issue #1134 (LD-34) |
| 5c44b0 (none) の理由特定 | 1 関数 | 子 issue #1134 (LD-34) |
| 7/7 動的確認 (修復の wasm 比較) | — | 子 issue #1134 (LD-34) |

survey の ok 退行は、修復を入れていないため今回の範囲では測っていない。SUSPECT 件数だけでは修復の正しさは示せない (REPORT_509 §1)。
