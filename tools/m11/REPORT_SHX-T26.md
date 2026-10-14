# trap stack の wasm-function[1352] 特定と function_8c5eb0 の D19 判定 (SHX-T26 / #1629 / 親 #1493)

既知類型との関係: `function_8c5eb0` は DEFECTS.md の D19 (件数 0 ループ) と同一関数だが、**今回の実 boot の trap とは同一原因ではないと判定** (§3)。

## 1. 結論

- 測定 commit: `9741735f` (main 取り込み済み・本 PR は REPORT のみ)。素材 `work-m11.tar.zst` (`tools/m11/work/` に展開, gitignore)。
- 測定経路の差分 (`git diff 9741735f HEAD -- tools/m11/shimx_link tools/m11/guard699 tools/m11/m11_build.sh tools/shimx`): 出力 0 行。測定に使った run_trace.mjs・build.sh・m11_guard699.py は無変更。
- 範囲を広げた差分 (`git diff 9741735f HEAD -- tools/m11 tools/shimx`): main 取り込みで入ったのは 9 ファイル (+643 −3)。内訳は別 issue 由来の REPORT と `m11_argrecover_verify.py`・`m11_setother_ssa_value.py`・`judge_dump.py`・`ldfix/audit_undefload_dest.py` で、本測定の経路には含まれない。PR 自身の `REPORT_SHX-T26.md` (+49) を含めた `tools/m11 tools/shimx` 全体は 10 ファイル (+692 −3)。素材 `work-m11` が取得できないため、この差分込みの再測定は未実施。
- trap stack 最上段 `wasm-function[1352]` の関数名は **`function_4133f0`** (export 表で特定)。ただし番号 1352 は **D19 ガード適用版の wasm** のみで現れる。素材の snapshot wasm では同じ関数が `[1240]`。関数番号は build ごとに変わるため、番号単体では突き合わせられない。
- `function_8c5eb0` (trace wasm の番号 5100) は **どの stack にも現れない** (snapshot・HEAD 再実行・ガード版の 3 run)。
- D19 ガード (`icmp sle i32 %9, 0`) を当てても実 boot の停止位置は変わらない (`units_run=17`・`threw` 同一)。よって D19 の修復は本 trap の修復要件ではない。
- 受入条件 4 件のうち 1・3・4 は達成。2 は「同一でない」判定まで達成し、DEFECTS.md への正式登録は未実施 (§4)。

## 2. 実測

| 段階 | 入力 | 結果 |
|---|---|---|
| snapshot trace run (展開物) | `tools/m11/work/shimx_link/m11_sx_trace_soft.run.json` | `boot_stage=1` `units_run=17` `dllmain_done=false` `threw="memory access out of bounds"` / stack 最上段 `[1240]` = `function_4133f0` |
| HEAD 再実行 (`9741735f`) | `node shimx_link/run_trace.mjs work/shimx_link/m11_sx_trace_soft.cjs` (snapshot wasm, 再 build なし) | rc=0 / 同値 (`total_calls=94` `icall_ok=19`) / 最上段 `[1240]` (`function_4133f0`) |
| D19 ガード版 build | `build.sh --trace --soft` rc=0 (`signature mismatch=1 undefined symbol=0 duplicate=0`) | 実 boot rc=0 / `units_run=17` `dllmain_done=false` `threw` 同一 / `icall_ok=24` `total_calls=97` `distinct_called=28` / 最上段 `[1352]` = `function_4133f0` |

- 名前特定は `.cjs.wasm` の export 表を直接読んだ (name section は空・`wasm-objdump` は未導入)。
- 関数番号は build ごとに変わる。snapshot wasm では `[1240]` = `function_4133f0`、ガード版では `[1352]` = `function_4133f0`。同じ関数でも番号が一致しないため、番号だけで別 build の stack を突き合わせないこと。
- issue 本文の「`function_8c5eb0` (export 番号 5183)」は build に依存して一致しない。trace wasm で `function_8c5eb0` は番号 5100、番号 5183 は `function_5aee80`。通常 wasm (`m11_boot.cjs.wasm`) では番号 5183 は `function_8675c0`。

## 3. D19 判定 (`function_8c5eb0`)

| 根拠 | 内容 |
|---|---|
| stack に現れない | snapshot・HEAD 再実行・ガード版の全 stack に `function_8c5eb0` は無い |
| 呼出関係 | `function_4133f0` の callees は `409440`・`409c80`・`412c20` と自身のみ。6 段以内の呼出で `function_8c5eb0` へ到達しない (IR `boot_final.ll`) |
| ガードで停止不変 | `m11_guard699` の `--mode on` を当てても `units_run=17`・同じ OOB。D19 の型 (件数 0 ループ) の修復は本 trap を解消しない |

判定: **D19 と同一原因ではない**。`function_8c5eb0` の D19 ガード (`m11_guard699.py`) は本 trap の修復要件から外す。

## 4. 手順と注意

- `m11_guard699.py` は `define weak i64 @function_8c5eb0(` / `define weak i64 @function_8ca670(` を認識しない (`boot_final3.ll` の定義形)。そのため、`weak` を外した**作業コピー**にガードを当てた (diff 28 行, 関数 1 箇所)。`boot_final3.ll` は元の内容に戻して検証済み。
- 作業コピーは `tools/m11/work/t26/` (gitignore)。trace wasm `tools/m11/work/shimx_link/m11_sx_trace_soft.cjs.wasm` は**ガード版で上書き済み**。snapshot の wasm は残っていないため、再現時は `work-m11` を展開し直すこと。
- 関数名は `function_<VA>` の export 名で表す (VA 16 進)。`wasm-function[N]` の N は build ごとに変わるので、比較には `.cjs.wasm` の export 表を引くこと。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_4133f0` の OOB (最上段) の原因。trap 直前に `GetLocaleInfoW` の反復 (unit 18) がある | 受入 (実 boot の file API 件数) の未達が続く | #1630 (SHX-T27) |
| D19 の別類型としての DEFECTS.md 登録 (`function_4133f0` 系) | 欠陥カタログ未更新 | #1630 で切り分け後に起票 |
| `weak` 定義形に対する `m11_guard699.py` の対応 | ガード版は手で作業コピーを作った | 本 issue では扱わない (PM 判断) |
