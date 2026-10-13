# #930 (LD-20): 消費者形 pure 残 23 関数 (24 引数) の残件測定 — 部分達成

**判定: 部分達成**。修復の追加はせず、残件の分類 (§3) とネガコン (§4) を取った。支配関係つきの修復 (entry 外 deref の 18 関数 = 素 13・ptr 4・w32 1) は未着手で、子 issue #1134 に分けた (§5)。§2 の到達数は再現未了 (§2.1)。

先行: #734 (`REPORT_734.md`)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 残 23 関数 (24 引数) のうち entry 外 deref の 18 関数 (19 引数。素 13・ptr 4・w32 1) を支配関係つきで修復、または不能理由を関数ごとに記録 | **一部**。関数ごとの最初の deref 位置を §3 に記録。支配関係つきの修復は未着手 (§5 の子 issue #1134) |
| tracker-no-deref (3 関数) と none (5c44b0) の理由を記録 | **一部**。tracker-no-deref (3 関数) は「記号実行が deref を見ない」という現象のみを記録 (理由は未特定)。5c44b0 は理由未特定。理由の特定は #1134 |
| `ir_conditions.json` を作り直した IR で `reach_509.sh` を実行し、survey 到達を記録 | **未検証**。§2 の到達数は、この PR の run の VA 列・出力 JSON が無く再現できない (§2.1)。再測定は #1134 |
| ネガコン (修復を外すと SUSPECT_USE が復帰) | **達成**。§4 (ptr 分岐の直前版 30 関数 / 33 引数 → 現行 23 / 24) |

## 2. 測定 (実測)

検証 HEAD: `b4dac086` (origin/main) の worktree。素材: `fl-win64` (PE 1 本)・`toolchain-emsdk` (emcc 6.0.12)・`work-m11`。Python は capstone・pefile 導入済み。

| 手順 | 結果 | 所要 (実測) |
|---|---|---|
| `m11_gen_ir2.sh` (ir_conditions 再生成) | rc 0、`ldfix=applied`、`ir_sha256` f5b27a237fd487253daef4af9d8f6aaea30cb49fbbb1e03c62b27b4baa1daec4 | 38.6 s |
| `m11_build.sh` (wasm 再ビルド) | rc 0、`OK: work/m11_boot.cjs(+.wasm)` | 20.9 s |
| `audit_lsf.py` (現行 IR) | suspect_use 23 関数 / 24 引数、suspect_mixed 119 関数 | 11.3 s |
| `use_residual_509.py` | 合計 24 (関数, 引数) / 23 関数。内訳は §3 | 1.4 s |
| `reach_509.sh` (23 関数を計装、survey 942 unit) | 未検証 (VA 列・出力 JSON を保存せず、§2.1 の値は再現できない) | — |
| ネガコン (`7db8953b^` の ldfix.py を修復前 IR に流す) | suspect_use 30 関数 / 33 引数 (現行は 23 / 24) | — |

実行時の load average は 0.35〜0.5 (4 vCPU)。

### 2.1 到達 (survey 942 unit、関数入口の計装) — 未検証

**この表は現時点で再現できない。撤回扱いとし、再測定は #1134 で行う。**

- 計装に渡した VA 列 (順番) と出力 JSON を、本 PR の run では保存していなかった。index と関数の対応は確定できない。
- 同じ `reach_509.sh` 系の既存 `results/reach_509.json` (942 unit、#509 の run) の内訳は次の通り (`kind` = `reach_survey.mjs` の unit 判定)。
  - kind 別: ok 852 / oob 26 / halt0 17 / miss 46 / noproc 1 (計 942)
  - hit のある unit: index 1 = 17 unit、index 7 = 44 unit、index 14 = 1 unit、index 15 = 1 unit
  - kind=ok で hit のある unit: index 7 の 26 unit のみ
- 「到達」の定義: 本 REPORT では「kind=ok の unit で、その関数の入口計装が 1 回以上 hit した」を指す。halt0・oob・miss で hit した unit は到達数に含めない。

本 PR の表 (40fe90 2 unit / 44f040 3 unit / 47ad70 7 unit) は、既存 JSON の内訳とも対応しない。対応する VA 列の記録が見つからないため、この数値は根拠なし。

## 3. 関数ごとの残件 (use_residual_509.py の門 + 最初の deref 位置)

最初の deref 位置は `f3c_track` の記号実行による機械語の VA。`ptr` は IR のヘッダ型。

| 関数 | 引数 | 分類 | 最初の deref | IR ヘッダ型 | survey 到達 |
|---|---|---|---|---|---|
| 101d180 | arg3 | first-deref-not-entry | 101d477 | i64 | 0 |
| 1050f90 | arg2 | first-deref-not-entry+w32 | 1051098 | i64 | 0 |
| 1050f90 | arg3 | first-deref-not-entry+w32 | 105114c | i64 | 0 |
| 10626e0 | arg3 | first-deref-not-entry+ptr-arg | 1062752 | ptr | 0 |
| 10628d0 | arg1 | first-deref-not-entry | 10628d8 | i64 | 0 |
| 12f9730 | arg3 | first-deref-not-entry | 12f9872 | i64 | 0 |
| 40fe90 | arg1 | first-deref-not-entry | 40fe99 | i64 | 2 unit / 6 回 |
| 41b8d0 | arg1 | first-deref-not-entry | 41b8de | i64 | 0 |
| 41b970 | arg1 | first-deref-not-entry | 41b97e | i64 | 0 |
| 449550 | arg4 | first-deref-not-entry | 44957e | i64 | 0 |
| 44f040 | arg1 | first-deref-not-entry | 44f069 | i64 | 3 unit / 3 回 |
| 44fb40 | arg1 | first-deref-not-entry | 44fb71 | i64 | 0 |
| 47ad70 | arg2 | first-deref-not-entry | 47ad82 | i64 | 7 unit / 15 回 |
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

- **first-deref-not-entry 18 関数 (素 13・ptr 4・w32 1)**: 最初の deref が entry ブロック外。修復には IR のブロック支配関係が要る。ptr 付きは 10626e0・784ed0・786d50・787380 (4 関数)、w32 付きは 1050f90 (1 関数、2 引数)。survey 到達の欄は §2.1 の通り未検証。
- **tracker-no-deref 3 関数 (75a180・db6480・dc27c0)**: audit は機械語の deref を見るが、ldfix の記号実行は deref を見ない (現象。理由は未特定)。survey 到達の欄は未検証のため、修復の効果も未測定。
- **none (5c44b0)**: どの門にも掛からないが、`fix_f3c_use` の置換対象になっていない理由は未特定。最初の deref (5c44bf) は entry ブロック内。
- **ptr-arg 1 (ddd4d0)**: ptr 型引数だが、最初の deref は entry 内。REPORT_734 の PR 版 SUSPECT_USE に残る既知の関数。

分類語の定義 (`use_residual_509.py` の門): `first-deref-not-entry` = 最初の deref のブロックが entry 外 / `ptr-arg` = 引数の IR 型が ptr / `w32` = 32bit deref を含む / `tracker-no-deref` = 機械語には deref があるが記号実行の tracker が見つけない / `none` = どの門にも掛からない。

## 4. ネガコン (修復の有無で SUSPECT_USE が変わること)

同じ修復前 IR (`M11_LDFIX=0` で再生成) に対して:

| ldfix.py | suspect_use 関数 / 引数 |
|---|--:|
| `7db8953b^` (ptr 分岐の直前) | 30 / 33 |
| 現行 `origin/main` (ptr 分岐あり) | 23 / 24 |

ptr 分岐を外すと SUSPECT_USE が 7 関数 / 9 引数だけ戻る。REPORT_734 の数値と一致する。ネガコン後は `ir_conditions.json` を `ldfix=applied` に戻した (指紋 `f5b27a23…`)。

## 5. 未実施と残件

| 残件 | 件数 | 起票先 |
|---|--:|---|
| entry 外 deref の支配関係つき修復 (first-deref-not-entry 18 関数 = 素 13・ptr 4・w32 1) | 18 関数 (19 引数) | 子 issue #1134 (LD-34) |
| tracker-no-deref (75a180・db6480・dc27c0) の記号実行の修正 | 3 関数 | 子 issue #1134 (LD-34) |
| 5c44b0 (none) の理由特定 | 1 関数 | 子 issue #1134 (LD-34) |
| 7/7 動的確認 (修復の wasm 比較) | — | 子 issue #1134 (LD-34) |

survey の ok 退行は、到達数が再現できていないため今回の範囲では測っていない。SUSPECT 件数だけでは修復の正しさは示せない (REPORT_509 §1)。
