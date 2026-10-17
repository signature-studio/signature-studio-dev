# #5999 (CI-249): function_f552a0 の呼出し第 1 引数を機械語 `[rbx]` (= *%arg1) に戻す (opt-in・既定 OFF)

親: #5995。判定の根拠は #5995 のコメント 6228635866 (6 件の対応表・原因 A/B)。

## 1. 結論

- 修正 pass `ldfix/fix_f552a0.py` を追加した。機械語どおり、`0xf552a0` のループ内 5 箇所 (f5531d を含む) と脱出後 1 箇所の `call` (計 6 件) の第 1 引数を、呼出しの直前に挿入した `inttoptr %arg1` と `load i64` の値にする。`rcx.0`/`rcx.1` の loop-carry は外す。
- 実 IR (`work-m11` の `boot_final.ll` に pass を適用) で pass が通り、挿入 load 6 件 (参照 12 行) を確認した。変換後 IR は `clang -c -x ir` が通る。
- 修正 ON/OFF の e2e は、同じ条件 (boot5 込みの IR 生成) で測って **数値が完全に一致した** (§3.2)。ただし両方とも既存のゲート (期待値・ptrcheck) で落ちており、修正の効果は本測定では確認できなかった。
- **既定 OFF** (`M11_FIX_F552A0=1` で有効)。既定 ON にする判断は PM に残す。
- 受入条件 1・2 は実 IR で pass 適用と構文検査まで確認。実行結果による確認は §3.2 の通り一致 (効果なし) で、既定 ON の判断材料にはならない。受入条件 3 (引数を照合する判定器) は未着手 (§5)。

## 2. 修正内容と機械語の根拠

機械語 (`block00031_PE.bin`・capstone 実測。#5995 のコメント 6228635866 の表):

| 機械語 | 内容 |
|---|---|
| `f552a7` | `mov rbx, rcx` (`rbx` = 入口の `%arg1`) |
| `f552aa` | `cmp qword ptr [rbx], 0` (`*arg1` の null 判定) |
| `f552b6` / `f552ce` / `f552e8` / `f55318` / `f5531d` / `f5532b` / `f5534b` / `f5536d` | 各 `call 0x12df530` の直前に `mov rcx, qword ptr [rbx]` (第 1 引数は `*arg1`) |
| `f5538d`〜`f55399` | 脱出後 `call 0x12df760` の直前に `mov rcx, qword ptr [rbx]` |
| `0x12df530` | `mov rax, [rcx+8]` / `imul edx, [rcx+0x10]` (第 1 引数は構造体ポインタ) |

IR の差分 (修正 pass による変換):

- 呼出し 6 件の第 1 引数: `%rcx.0.reload` ×4 と `%21` ×1 と `%rcx.1.reload` ×1 → いずれも、直前に挿入した `%fx5999o<N>` (= `load i64, ptr (inttoptr %arg1)`)。
- `%rcx.0.reg2mem` / `%rcx.1.reg2mem` の alloca・store・reload を削除。
- 検査 (pass 内 assert): 適用後に `rcx.0`/`rcx.1` の参照が 0 件、挿入 load が 6 件、二重適用は止まる。
- 実 IR 検証 (`work-m11` 展開後の `tools/m11/work/boot_final.ll`・レビュー r2 の確認を含む): pass 適用 OK、`fx5999o` 参照 12 行。

## 3. 測定

### 3.1 前版の測定 (根拠にしない)

測定 commit: `837082b7baa99ba553343419993e3162e49684b8` (r1 のコード commit)。この commit の IR は `%arg1` を直接渡しており、§2 の修正前の状態に当たる。前版の数値 (`83e4a3fe…` 114 / 875 / 20 / 46) は誤った引数の IR に対するもので、修正後の根拠にならない。

### 3.2 修正 ON/OFF の比較 (実 IR・本 run)

測定 commit: `bebd3e2b32c1114a752638c25d75e65bcea6f1cd` (コード変更の最後の commit。HEAD はこの時点の PR ブランチ)。

素材: `fl-win64` (`block00031_PE.bin`・sha256 `b2c64da4…`) と `work-m11` (`tools/m11/work/` に展開)。RetDec v5.0 で `boot5.lift.ll` を lift (`m11_extra_ranges5.txt`)。emsdk 6.0.12 (`emcc 6.0.12`)。runner 4 vCPU。

手順: `m11_gen_ir2.sh` (`M11_FIX_F552A0` = 0 または 1) → `m11_build.sh` → `m11_run.mjs` (通常起動) → `m11_survey.mjs` → `m11_tolerant.mjs` → 判定。`m11_e2e.sh` は使わなかった (`boot5` の lift と全再生成の時間を避けるため。`lift_pe.sha256` は素材に無く、lift 成果物は `work-m11` 由来)。

| 構成 | IR 指紋 (先頭 8 桁) | `f552a0` | 通常起動 init_count / icall ok / miss | units_run / skipped | survey ok / trap | 寛容起動 ok / skipped | ptrcheck (survey) |
|---|---|---|---|---|---|---|---|
| OFF | `b15e2d23` | not-applied | 99 / 391 / 3 | 98 / 3 | 875 / 20 | 871 / 70 | 71003 (max 71001 で FAIL) |
| ON | `9d4c050c` | applied (fx5999o 12 行) | 99 / 391 / 3 | 98 / 3 | 875 / 20 | 871 / 70 | 71003 (max 71001 で FAIL) |

- 出所: 通常起動は `work/<構成>/run.out` の `M11_RESULT`、survey は `work/<構成>/survey.out` の `"ok":875` と `"trap":20`、寛容起動は `tgate.out` の `M11_TOLERANT gate`。
- OFF と ON で通常起動・survey・寛容起動の結果は一致した (run.out はスタックトレースの wasm 関数番号だけが違い、結果行は同じ)。修正は実行結果に出ない。
- 既存ゲートの状態 (両方共通): `m11_tolerant_gate.py` が「通常起動の完了数 114 != 期待 101」で FAIL、`m11_survey.mjs` の ptrcheck が 71003 > 71001 で FAIL。いずれも修正の有無と無関係に出ている。
- 測定ハーネスの注意: `m11_judge.py` は `work/e2e_full.out` を読むため、本 run の judge 出力 (`units_run=109` 等) は前回 (boot5 無し) の古い結果。今回の数値の根拠にはしない。今回の通常起動の値は `work/<構成>/run.out` の `M11_RESULT` を使う。
- 旧値との比較: survey の 875 / 20 は §3.1 の旧値 (875 / 20 / 46) と一致した。通常起動の完了数は旧値 114 に対し今回 99 (`init_count`) で一致しない。今回の OFF の IR 指紋 `b15e2d23…` も旧値 `e7eade69…` と一致しない。差の原因は未確認 (IR 生成条件の差の可能性。素材の `boot_final.ll` の指紋 `69c774de…` とも異なる)。
- 測定時の wall time・load: 未計測 (本 run の時間制限内で各構成 1 回)。

### 3.3 既定 OFF の IR 指紋

- 既定 OFF (`f552a0=not-applied`) の `boot_final.ll` は `b15e2d23…`。この指紋は REPORT 旧値 `e7eade69…` と一致しない。既定 OFF の IR 生成経路は変えていないので、差は素材条件 (boot5 の有無・RetDec の版) による可能性がある。未確認。

## 4. 製品 KPI

本 PR は起動・GUI の経路を既定で変えない (既定 OFF)。ON の実測も §3.2 のとおり通常起動の数値は OFF と同じ。FLEngine 起動の dispatch 数・最初のウィンドウ: 動かしていない (本 PR の範囲は m11 の lift IR 生成側)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正 ON で効果が出ない理由 (実行経路で `function_f552a0` が呼ばれるか) | 修正の意味が実行結果で確認できない | #5999 (次の run) |
| 既存ゲートの不一致 (通常起動 101 vs 99/114、ptrcheck 71003 > 71001) | e2e が両構成で赤のまま | PM 判断 (期待値・基準の更新は本 PR の範囲外) |
| 受入 3: 引数を照合する判定器 | 修正の正しさを機械で確認できない | #5999 (次の run) |
| 既定 OFF 指紋 `b15e2d23…` と旧値 `e7eade69…` の差 | 過去の数値との比較ができない | #5999 (次の run) |
| 既定 ON にする判断 | 効果が出ないため判断材料なし | PM 判断 |
| 脱出後の `call 0x12df760` (機械語 `[rsi+0x18]`) の callee の意味 | 第 1 引数は `*arg1` に直したが、callee の意味は未確認 | #5995 の未確認項目 |

## 6. コードの測定 commit と差分

- 測定 commit: `bebd3e2b32c1114a752638c25d75e65bcea6f1cd` (§3.2 の全数値はこの commit の IR・コードによる)。
- 前版の測定 commit: `837082b7baa99ba553343419993e3162e49684b8` (§3.1。根拠にしない)。
- `git diff bebd3e2b32c1114a752638c25d75e65bcea6f1cd HEAD -- tools/m11/ldfix/fix_f552a0.py tools/m11/m11_gen_ir2.sh` は空 (測定後のコード差分なし)。
