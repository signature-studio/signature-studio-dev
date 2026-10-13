# #1230: unit 149 の `412e40` 第 1 引数 (stack slot か値か) の判定

**判定: 受入条件 1 は一部達成 (引数の渡し方は機械語・IR 双方で正しいと確認。値の出どころは未判定)。受入条件 2・3 (修復・n≥3 survey・ネガコン) は未着手。Refs #1230 (Closes しない)。**

親: #1019 (M11-N58) / 前提: PR #1018 (gate `M11_FIX_652500`)。

## 0. 検証環境

- 測定 base: `origin/main` `2b2faf52`、branch `1230-m11-unit149-oob-412e40` (worktree `ws-1230`)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR` は末尾 `/` 無しの `$RUNNER_TEMP/fl-win64`)。`work-m11` / `work-liftdiff` は worktree の `tools/` 直下に展開。`[RETDEC]` `[EMSDK]` は runner 既存。
- `m11_gen_ir2.sh`: rc=0, 43.8 s, `ldfix=applied`, `boot_final.ll` 490693 行。
- `M11_FIX_652500={0,1} m11_build.sh`: 両方 rc=0 (OFF 26 s)。
- 注意: `FL_WIN64_DIR` の末尾に `/` を付けると IR の PE パスと不一致で build が拒否される (`m11_build.sh` の fail-closed)。

## 1. 機械語と IR の突合 (`653660` → `412e40` 呼出し)

- `653660` (`disasm_fn.py 653660`) の `0x653944` `lea rcx,[rbp+0x40]` / `mov edx,0xc` / `call 0x412e40`、`0x653952` `lea rcx,[rbp+0xb0]` / `mov edx,2` / `call 0x412e40`。第 1 引数は **`lea` によるスタック slot のアドレス**。
- IR (`boot_final.ll` 216831〜216832): `%__m11c_1299 = ptrtoint ptr %stack_var_-136` → `call @function_412e40(i64 %__m11c_1299, i64 12)`。機械語と一致する。
- `412e40` 本体 (IR 115662): 第 1 引数を `%0 = inttoptr` で指し、`%1 = load i64 %0` (= slot の中身) が 0 なら即 return。非 0 なら `[%1-8]` (32bit カウンタ) を読む。
- 結論: **引数の渡し方 (アドレスか値か) は lift で壊れていない**。「deref 脱落」仮説は棄却。

## 2. oob の発生箇所 (wasm 実行時)

- `M11_SURVEY_STACK=149 node m11_survey.mjs` (OFF/ON とも): `wasm-function[75]:0x6b52f` = `function_412e40`。
- `trap_triage/oob_insn.py work/m11_boot.cjs.wasm 75 0x6b52f`: `i32.load offset=0` (`[%1-8]` の読み)。
- 最上位 frame: `412e40 ← 653660 (3904) ← 6539e0 (3905) ← 664180 (3983) ← 664250 (3985) ← …`。
- OFF/ON で同じ oob 箇所 (gate によって変わらない)。

## 3. 未判定 (次の入口)

- `412e40` の `[%1-8]` の `%1` は `0x40` slot の中身。`653660` 内で slot の中身を変える箇所は、入口の 0 初期化 (`65367b`)、`6536f2`/`653xxx` の `0xb0`/`0xb8` 系、`653914` 直後の `call 0x6525b0` (**`6525b0` の戻り値は `rax=&slot` で、slot の中身は書かない**: 機械語 `6525b0` で確認) の 3 つ。
- `disasm` 上、`653660` 内で `[rbp+0x40]` へ直接 store する命令は `65367b` の 0 初期化のみ (`grep` で確認)。ただし `&slot` (`lea rcx,[rbp+0x40]`) を渡した先が書く可能性は残る。`6525b0` は書かない (上記)。`412e40` は非 0 の時だけ `store i64 0` で slot を書く (IR 115662 の `dec_label_pc_412e53`)。
- よって「0 のはずの slot が非 0 になった経路」は、`&slot` を受ける関数の内部 (未調査の callee) にある。これが判定の次の入口。
- 未検証: wasm 実行時に `412e40` 入口の `%1` を採取し、どの store で非 0 になったかを特定する。

## 4. 未達の受入条件と起票先

| 受入条件 | 状態 | 起票先 |
|---|---|---|
| 1. 第 1 引数 slot/値の判定 (機械語と IR の突合) | 引数の渡し方は正常と確定。slot の中身 (`6525b0` の書込み) は未判定 | #1230 (本 PR で継続) |
| 2. 修復と unit 149 の n≥3 survey (min–max) | 未着手 (判定待ち) | #1230 |
| 3. ネガコン (修復を外すと oob 復帰) | 未着手 (修復待ち) | #1230 |

`412e40` の oob 周辺の別経路は既存の #1274 ([M11-N77]、unit 190 の `412e40` oob・`410360` 経由外) が追っている。本 issue との重複は無いが、`412e40` の入口値の扱いは #1274 と共有される可能性がある。
