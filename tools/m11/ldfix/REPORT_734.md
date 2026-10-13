# #734 (LD-12): 消費者形 pure 残の F3c 修復 — ptr 型引数の分 (部分達成)

**判定: 部分達成**。ptr 型引数 (`ptr %argN`) の消費者形を修復対象に入れ、消費者形 pure 残を **30 → 23 関数 (33 → 24 引数)**。残りは entry 外の最初の deref (支配関係が要る) が主因で、子 issue に分けた (§4)。
6/7 (wasm 再ビルド・survey) と 7/7 (動的確認) は未実施 (`/opt/emsdk` が無い。`ir_conditions.json` も無い)。受入条件「SUSPECT を 0」「到達測定」は未達。

先行: #509 (`REPORT_509.md` §3・§6)。修復は `ldfix.py` `fix_f3c_use` の ptr 分岐 (`ptrarg`)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 30 関数 (33 引数) を修復、または修復不能理由を関数ごとに記録 | **一部**。ptr 型引数を修復 (`f3c_use_ptrarg` = 9 引数 = 33 → 24)。残り 23 関数 / 24 引数は §4 の理由で未修復 |
| `reach_509.sh` で survey 到達を測る | **未達**。`m11_build.sh` が `work/ir_conditions.json` の `ldfix=applied` を要求し、work-m11 の snapshot に無い (§3) |
| ネガコン (ptr 分岐を外すと SUSPECT が復帰) | **実測済み** (§2 の NC 行)。同じ修復前 IR に対し `origin/main` の ldfix.py (ptr 分岐なし) を流すと消費者形 pure は 30 関数 / 33 引数、PR 版は 23 / 24。PR で消えたのは **7 関数** (44cf40, 4506e0, 46b4d0, 4a27c0, 6ca580, 6ca6c0, de4120)。PR 版で新たに pure 入りした関数は **0 件**。ddd4d0 は PR 版の SUSPECT_USE に残る |

## 2. 測定 (実測。`ldfix_509_e2e.sh` の 1〜5/7 を PY=capstone+pefile の venv で実行)

検証 HEAD: `637c13cc` の上に本 fix commit を積んだ版 (ldfix.py は `7db8953b` と同一)。所要 **194 秒** (exit 0、load average 1 分値 0.99)。入力は work-m11 (`M11_WORK`)。

| 入力 | store 形 SUSPECT (関数 / site) | 消費者形 pure (関数 / 引数) | mixed (関数) |
|---|--:|--:|--:|
| 修復前 IR (`M11_LDFIX=0` で再生成) | 8 / 12 | 52 / 56 | 124 |
| `origin/main` の ldfix.py (ptr 分岐なし。NC 基準) | 0 / 0 | 30 / 33 | 118 |
| **今回 (ptr 分岐を追加)** | **0 / 0** | **23 / 24** | **118** |

- 基準は同じ修復前 IR に `origin/main` の ldfix.py を流した出力 (NC:prev)。REPORT_509 §3 の「新 ldfix 出力」行 (0 / 0・30 / 33・118) と一致する。旧 `009e823` の行 (8 / 11, 49 / 53, 120) は #484 の出力で別基準のため本表から外した。
- store 形 SUSPECT の 0 / 0 は本 PR の変更によるものではない。本 PR の差分 (`fix_f3c_use` の ptr 分岐) は消費者形だけを触り、store 形の経路 (`fix_f3c_fn`) を変えていない。修復前 (8 / 12) → 0 / 0 は #509 で既に成立。消えた store 形 8 関数 (5c0270・41a670・66e080・7e5240・806740・c62780・409c80・417b70) は、本 PR の 7 関数 (消費者形 pure) とは別の集合。
- 旧版/新版の突合 (`main` 版 vs PR 版): 関数外テキスト一致、本体が異なる関数 18 (うち F3c 関数 41 → 48、旧の全てを含む)。SUSPECT_USE の差は上記 7 関数の除去のみ、新規 0。
- 単独の overlay (`--passes f3c` を `boot_final.ll` へ重ねる): 変わった関数 33、alloca 行を除いて新版と同一 33。
- NC の個別 (5/7、#509 から流用した 2 本): 806740 の store を `%arg3` に戻すと store 形 SUSPECT 1 / 1 (復帰)。1063090 の消費者置換を戻すと消費者形 pure 24 関数、1063090 は pure に入る (復帰)。いずれも #509 時点の NC で、本 PR の ptr 分岐の NC ではない。
- 残件分類 (`use_residual_509.py`): 修復後 24 引数 / 23 関数。内訳は first-deref-not-entry 13、+ptr-arg 4 (ptr 型だが支配関係も要る)、tracker-no-deref 3、+w32 2、none 1 (5c44b0)、ptr-arg 1。
- 形の確認 (機械語と突合): 4506e0 は機械語 `mov rcx,[rcx]; test rcx,rcx; ... mov eax,[rcx-4]` (rcx = arg1 の値)。修復後 IR は `*arg1` を load して null 判定と `-4` 読みに使う。44cf40 は `mov rax,[rdx]` の後の store (修復後 IR で整合)。
- 構文検査: 修復後 IR (`new.ll` と `bf_f3c.ll`) を `llvm-as-18` で検査 (exit 0)。`emcc -c` は使っていない (`/opt/emsdk` が無い)。
- 検証範囲外: 動的確認 (`dyn_509.mjs`) と survey は未実施 (§3)。SUSPECT 件数だけでは正しさの証明にならない (REPORT_509 §1)。

## 3. 未実施と理由

素材: `$HOME/artifacts` には `fl-win64.tar.zst` と `work-m11.tar.zst` の両方がある (2026-10-13 確認)。`work-m11` は `tools/m11/work/` へ展開して使った (`boot0-4.lift.ll`・`boot*.drc.config.json`・`m11_image.bin`・`boot_final.ll`・`boot_final3.ll` が揃う)。`ldfix_509_e2e.sh` の 1〜5/7 は work-m11 で exit 0 で完走した (§2)。

- 再現可能: 1〜5/7 (修復前 IR 再生成・旧版/新版の突合・audit・overlay・NC)。
- 未達: 6/7 (wasm 再ビルドと survey) と 7/7 (動的確認)。`m11_build.sh` は `work/ir_conditions.json` に `ldfix=applied` が無いと拒否する (#680)。work-m11 の snapshot には `ir_conditions.json` が無いため、6/7 の reach は測れない。`m11_gen_ir2.sh` の再生成には fl-win64 の PE が要るが、この環境には emsdk (`/opt/emsdk`) も無い。記録を手で書いて通すことはしない (指紋が一致しない IR を作るため)。

## 4. 残件 (子 issue に分割)

| 残件 | 件数 | 起票先 |
|---|--:|---|
| 最初の deref が entry 外 (支配関係が要る) | 13 関数 (+ptr 4 / +w32 2 を含む) | 子 issue (LD-20) |
| tracker-no-deref / none (5c44b0 を含む) | 3 + 1 | 子 issue (LD-20) |
| 再生成 IR での reach・動的確認・個別ネガコン | — | 子 issue (LD-20) |

## 5. 変更

- `tools/m11/ldfix/ldfix.py` `fix_f3c_use`: `ptrarg` (引数が ptr 型) の分岐を追加。`load i64, ptr %argN` の値を `inttoptr` で消費者に渡す。従来の i64 分岐は不変。
- `tools/m11/ldfix/REPORT_734.md` (本ファイル)。
