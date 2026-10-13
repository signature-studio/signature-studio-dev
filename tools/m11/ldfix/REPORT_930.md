# #930 (LD-20): 消費者形 pure 残 23 関数 (24 引数) の残件測定 — 部分達成

**判定: 部分達成**。修復の追加はせず、残件の実測 (再生成 IR での到達・不能理由・ネガコン) を取った。支配関係つきの修復 (entry 外 deref の 13 + 4 + 2 関数) は未着手で、子 issue に分けた (§4)。

先行: #734 (`REPORT_734.md`)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 残 23 関数 (24 引数) のうち entry 外 deref の 13 関数 (+ptr 4 / +w32 2 を含む) を支配関係つきで修復、または不能理由を関数ごとに記録 | **一部**。関数ごとの最初の deref 位置を §3 に記録。支配関係つきの修復は未着手 (§4 の子 issue) |
| tracker-no-deref (3 関数) と none (5c44b0) の理由を記録 | **記録**。理由は §3 (tracker-no-deref は到達 0 で、修復の効果を測れない。5c44b0 は理由未特定) |
| `ir_conditions.json` を作り直した IR で `reach_509.sh` を実行し、survey 到達を記録 | **達成**。§2 (ir_conditions `ldfix=applied`・ir_sha256 `f5b27a23…`) |
| ネガコン (修復を外すと SUSPECT_USE が復帰) | **達成**。§2 (ptr 分岐の直前版 30 関数 / 33 引数 → 現行 23 / 24) |

## 2. 測定 (実測)

検証 HEAD: `b4dac086` (origin/main) の worktree。素材: `fl-win64` (PE 1 本)・`toolchain-emsdk` (emcc 6.0.12)・`work-m11`。Python は capstone・pefile 導入済み。

| 手順 | 結果 | 所要 (実測) |
|---|---|---|
| `m11_gen_ir2.sh` (ir_conditions 再生成) | rc 0、`ldfix=applied`、`ir_sha256` f5b27a237fd487253daef4af9d8f6aaea30cb49fbbb1e03c62b27b4baa1daec4 | 38.6 s |
| `m11_build.sh` (wasm 再ビルド) | rc 0、`OK: work/m11_boot.cjs(+.wasm)` | 20.9 s |
| `audit_lsf.py` (現行 IR) | suspect_use 23 関数 / 24 引数、suspect_mixed 119 関数 | 11.3 s |
| `use_residual_509.py` | 合計 24 (関数, 引数) / 23 関数。内訳は §3 | 1.4 s |
| `reach_509.sh` (23 関数を計装、survey 942 unit) | rc 0。§2.1 | 17.3 s |
| ネガコン (`7db8953b^` の ldfix.py を修復前 IR に流す) | suspect_use 30 関数 / 33 引数 (現行は 23 / 24) | — |

実行時の load average は 0.35〜0.5 (4 vCPU)。

### 2.1 到達 (survey 942 unit、関数入口の計装)

| 関数 | 実行 unit 数 | 入口通過 総回数 |
|---|--:|--:|
| 40fe90 | 2 | 6 |
| 44f040 | 3 | 3 |
| 47ad70 | 7 | 15 |
| 上記以外の 20 関数 (41b8d0, 41b970, 449550, 44fb40, 5c44b0, 6905f0, 75a180, 784ed0, 786d50, 787380, c40420, db6480, dc27c0, ddd4d0, f552a0, 101d180, 1050f90, 10626e0, 10628d0, 12f9730) | 0 | 0 |

survey で実行されたのは 3 関数のみ。残り 20 関数は、942 unit のどれでも入口を通らなかった。

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

- **first-deref-not-entry 13 関数 (+ptr 4 / +w32 2 を含む)**: 最初の deref が entry ブロック外。修復には IR のブロック支配関係が要る。survey で到達するのは 40fe90・44f040・47ad70 の 3 関数のみ。
- **tracker-no-deref 3 関数 (75a180・db6480・dc27c0)**: audit は機械語の deref を見るが、ldfix の記号実行は見ない。3 関数とも survey 到達 0 で、修復の効果は測れない。
- **none (5c44b0)**: どの門にも掛からないが、`fix_f3c_use` の置換対象になっていない理由は未特定。最初の deref (5c44bf) は entry ブロック内。
- **ptr-arg 1 (ddd4d0)**: ptr 型引数だが、最初の deref は entry 内。REPORT_734 の PR 版 SUSPECT_USE に残る既知の関数。survey 到達 0。

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
| entry 外 deref の支配関係つき修復 (first-deref-not-entry 13 関数、+ptr 4・+w32 2 を含む) | 13 関数 | 子 issue #1134 (LD-34) |
| tracker-no-deref (75a180・db6480・dc27c0) の記号実行の修正 | 3 関数 | 子 issue #1134 (LD-34) |
| 5c44b0 (none) の理由特定 | 1 関数 | 子 issue #1134 (LD-34) |
| 7/7 動的確認 (修復の wasm 比較) | — | 子 issue #1134 (LD-34) |

survey で到達したのは 3 関数のみのため、survey の ok 退行は今回の範囲では測っていない。SUSPECT 件数だけでは修復の正しさは示せない (REPORT_509 §1)。
