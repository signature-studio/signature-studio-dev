# liftdiff LD-179 (#3862) — %tagPOINT 値渡し 4256c0 の m11_tr_ 生成

> 親: #1528 (LD-52)。対象: `4256c0` (`ptr (%tagPOINT)`・import thunk・本体は user32 `WindowFromPoint`)。
> 測定 commit: `edd566a96` (コードを変えた最後の commit)。`edd566a96` から HEAD までのコード差分は §4。
> 素材: `fl-win64` (`[WIN64]` の `extracted/block00031_PE.bin`)・`work-m11`・`work-liftdiff`・`toolchain-emsdk` (`[EMSDK]` 6.0.12)。

## 1. 変更

- `tools/m11/m11_post.py`: `m11_tr_` 生成に `%tagPOINT` の分岐を足した。a0 の下位 32bit を x、上位 32bit を y とし、`insertvalue` で POINT を組んで callee に渡す。他の型の分岐は変えない。
- `tools/liftdiff/ldlib/cases.py`: `MACHINE_ENTRY` に `0x4256c0: ['i64']` を追加。
- 単体テスト: `tools/liftdiff/tests/test_ld179_tagpoint_tr.py` (合成 IR で m11_post を実行し、生成 IR の trunc/lshr/insertvalue/call を検査)。e2e `[0/4]` に追加。

## 2. 生成 IR の差分 (boot_final.ll 全量)

- 変更前: `; unsupported param %tagPOINT` + `call ptr @function_4256c0(%tagPOINT zeroinitializer)`
- 変更後: `trunc i64 %a0 to i32` / `lshr i64 %a0, 32` / `trunc` / `insertvalue` ×2 / `call ... (%tagPOINT %c0)`
- `unsupported param` の件数: 1 → 0。他の m11_tr_ は差分 0 (差分は 8 行のみ)。

## 3. 実測

| 項目 | 結果 |
|---|---|
| `bash tools/liftdiff/liftdiff_e2e.sh --m11-only` (HEAD `edd566a96`) | exit 0・`LIFTDIFF_E2E PASS`・所要 3m10s (load 開始前 0.98)・`test_ld52_machine_sig` と `test_ld179_tagpoint_tr` が PASS |
| sample:800 (HEAD) | 一致 360 / 不一致 234 / 実行不能 206 |
| sample:800 (前 run・同コード) | 一致 361 / 不一致 233 / 実行不能 206。REPORT_APPENDIX_LD52 §3 の run 間の揺れの範囲 (1 関数) |
| 11 関数 batch (`file:targets/ld52_11.txt`・HEAD) | 一致 2 / 不一致 1 / 実行不能 8 |
| `4256c0` 判定 | **mismatch (`wasm_trap`)**。native は ok、wasm は `Aborted(missing function: WindowFromPoint)`。入口引数は届くようになった (従来は `unsupported_sig` で実行に入らず) |

- 11 関数 batch の内訳: `40c660` `40c750` は match (equal)。`653c80` `691dd0` は native_fault (従来どおり)。残りは unsupported_sig 6。

## 4. 差分

- 測定 commit `edd566a96` から HEAD までのコード差分: `git diff edd566a96 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/tests tools/liftdiff/liftdiff_e2e.sh` は 0 行。
- 製品 KPI (FLEngine 起動・最初のウィンドウ): 本 PR は起動・GUI に関わらないため書かない。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側に user32 `WindowFromPoint` の実装が無く、`4256c0` は `wasm_trap` (missing function) で止まる。入口型は正しいが判定は match にならない | `4256c0` の一致判定 1 件 | #4184 ([LD-200]) |
| 残り 6 件 (`442a50` `442b90` `664890` `6649b0` `6649c0` `664a80`) の入口型 | 実行不能 6 | #3863 ([LD-180]) |
| `653c80` `691dd0` の native segv | 実行不能 2 | #3864 ([LD-181]) |
