# #734 (LD-12): 消費者形 pure 残の F3c 修復 — ptr 型引数の分 (部分達成)

**判定: 部分達成**。ptr 型引数 (`ptr %argN`) の消費者形を修復対象に入れ、消費者形 pure 残を **30 → 23 関数 (33 → 24 引数)**。残りは entry 外の最初の deref (支配関係が要る) が主因で、子 issue に分けた (§4)。
受入条件「SUSPECT を 0」「到達測定」「ネガコン記録」は未達。

先行: #509 (`REPORT_509.md` §3・§6)。修復は `ldfix.py` `fix_f3c_use` の ptr 分岐 (`ptrarg`)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 30 関数 (33 引数) を修復、または修復不能理由を関数ごとに記録 | **一部**。ptr 型引数を修復 (`f3c_use_ptrarg` = 9 引数。SUSPECT_USE から消えた関数: 44cf40, 4506e0, 46b4d0, 4a27c0, 6ca580, 6ca6c0, ddd4d0, de4120)。残り 23 関数 / 24 引数は §4 の理由で未修復 |
| `reach_509.sh` で survey 到達を測る | **未達**。`m11_build.sh` が `work/ir_conditions.json` の `ldfix=applied` を要求し、work-m11 の snapshot に無い (§3) |
| ネガコン (修復を外すと SUSPECT が復帰) | **一部**。`ldfix_509_e2e.sh` の 5/7 の NC 3 本は実行済 (§2)。ただし今回の修復に対応する個別の NC は未追加 |

## 2. 測定 (実測。`ldfix_509_e2e.sh` の 1〜5/7 を PY=capstone+pefile の venv で実行)

所要 **2 分 55 秒** (exit 0、load average 1 分値 1.01)。

| 入力 | store 形 SUSPECT (関数 / site) | 消費者形 pure (関数 / 引数) | mixed (関数) |
|---|--:|--:|--:|
| 修復前 IR (#509 と同じ) | 8 / 12 | 52 / 56 | 124 |
| #509 の出力 (`009e823`) | 8 / 11 | 49 / 53 | 120 |
| **今回 (ptr 分岐を追加)** | **0 / 0** | **23 / 24** | **118** |

- 旧版/新版の突合: 関数外テキスト一致、F3c 関数 16 → 48 (旧 16 を全て含む)。
- 単独の overlay (`--passes f3c` を `boot_final.ll` へ重ねる): 変わった関数 33、alloca 行を除いて新版と同一 33。
- 残件分類 (`use_residual_509.py`): 修復後 24 引数 / 23 関数。内訳は first-deref-not-entry 13、+ptr-arg 4 (ptr 型だが支配関係も要る)、tracker-no-deref 3、+w32 2、none 1 (5c44b0)、ptr-arg 1。
- 形の確認 (機械語と突合): 4506e0 は機械語 `mov rcx,[rcx]; test rcx,rcx; ... mov eax,[rcx-4]` (rcx = arg1 の値)。修復後 IR は `*arg1` を load して null 判定と `-4` 読みに使う。44cf40 は `mov rax,[rdx]` の後の store (修復後 IR で整合)。
- 検証範囲外: 動的確認 (`dyn_509.mjs`) と survey は未実施 (§3)。SUSPECT 件数だけでは正しさの証明にならない (REPORT_509 §1)。

## 3. 未実施と理由

`ldfix_509_e2e.sh` の 6/7 (wasm 再ビルドと survey) と 7/7 (動的確認) は失敗した。
`m11_build.sh` は `work/ir_conditions.json` に `ldfix=applied` が無いと拒否する (#680)。work-m11 の snapshot にはこの記録が無く、`m11_gen_ir2.sh` の再生成 (fl-win64 の PE が要る) が必要。記録を手で書いて通すことはしない (指紋が一致しない IR を作るため)。
`emcc -c` で修復後 IR (`bf_f3c.ll`) の構文検査は通過 (exit 0)。

## 4. 残件 (子 issue に分割)

| 残件 | 件数 | 起票先 |
|---|--:|---|
| 最初の deref が entry 外 (支配関係が要る) | 13 関数 (+ptr 4 / +w32 2 を含む) | 子 issue (LD-20) |
| tracker-no-deref / none (5c44b0 を含む) | 3 + 1 | 子 issue (LD-20) |
| 再生成 IR での reach・動的確認・個別ネガコン | — | 子 issue (LD-20) |

## 5. 変更

- `tools/m11/ldfix/ldfix.py` `fix_f3c_use`: `ptrarg` (引数が ptr 型) の分岐を追加。`load i64, ptr %argN` の値を `inttoptr` で消費者に渡す。従来の i64 分岐は不変。
- `tools/m11/ldfix/REPORT_734.md` (本ファイル)。
