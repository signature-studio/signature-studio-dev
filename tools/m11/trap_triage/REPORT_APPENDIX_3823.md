# #3823 付録: 923 (function_410b10) の obj 0x10bd3960 への書込み元 (2026-10-15, n=1)

正本は `REPORT_714.md`。本付録は #3823 (#1426 の子 `[M11-N193]`) の測定の全文。

## 1. 結論

- 923 の `function_410b10` 入口の `obj` は `0x10bd3960` (線形メモリ内)。trap 時の `*(obj)` (先頭 4 B) は 0 で、`*(obj)-0x80` が範囲外になる (inspector 実測、§3)。
- 全 unit の実行中に `[obj, obj+32)` への書込みを採ると 66 件。`*(obj)` の 0 化は、**unit 830 の `function_10c7cd0` (site 4015)** と **unit 880 の `function_125da90` (site 6778)** による、バイト単位のループ書込みである (§2)。
- 両関数は、呼出し元の引数で宛先が決まる汎用の「バイト単位コピー」。このため、0 を書いた**呼出し元** (obj を宛先にした側) は、IR の静的追跡だけでは確定できていない。**推定**: 呼出し鎖は `function_1263540`・`function_1264050`・`function_10d50d0` のいずれか。確定は未了。

判定: 受入 1 (`*(obj)` に 0 を書く命令・関数の実測特定) は**部分達成 (推定)**: 同じ番地への 0 書込みの命令は site 4015・6778 (IR 行 33552・57572) まで特定。ただし、その書込みが 923 の obj と同一オブジェクトへの書込みかは未確認。受入 2 (書込みの呼出し鎖と値の由来) は**未達**。受入 3 (回帰 0) は**未達** (基点 JSON との unit 突合を実施していない。§4)。

## 2. 書込み (測定 commit `68d5cb3c4`)

測定 commit `68d5cb3c4` (origin/main、本 PR の作業ベース。コード変更なし)。素材 fl-win64・toolchain-retdec・toolchain-emsdk・work-m11 を展開 (`FL_WIN64_DIR=$RUNNER_TEMP/ws3823/fl-win64`、`RETDEC_ROOT=$RUNNER_TEMP/ws3823/retdec`)。work-liftdiff は本 run では未使用。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` | rc=0 (`boot_final.ll` 490761 行) | 33.2 秒 |
| `m11_build.sh` | rc=0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`) | 18.8 秒 |
| `m11_survey.mjs` (既定) | rc=0 / ok 873 / trap 21 / noproc 1 / miss 47 / units 942 | 8.6 秒 |

load average は工程中 0.09〜1.38。

書込み採取 (`trap_triage/watch_obj_3823.sh`、全関数 store 計装、unit 0..923 を順に実行、監視 W = `0x10bd3960`、`[aw]` 66 件):

| unit | site | IR 関数 (IR 行) | 書込み | 範囲 |
|---|---|---|---|---|
| 45 | 20387 | `function_4fa990` (181413) | `[obj+8]` = `0x10bcc0a0` (8 B) | `obj+8` |
| 101 | 20376 | `function_4fa8f0` (181322) | `[obj+16]` = `0x1fa8d8` (8 B) | `obj+16` |
| 830 | 4015 | `function_10c7cd0` (33552) | `store i8` 1 B ずつ、val = 0 | `[obj, obj+32)` の 32 B |
| 880 | 6778 | `function_125da90` (57572) | `store i8` 1 B ずつ、val = 0 | `[obj, obj+32)` の 32 B |

- unit 830 と 880 の書込みは、いずれも同じ `[obj, obj+32)` を 1 バイトずつ 0 にする (各 32 件)。`*(obj)` を 0 にした書込みはこれに当たる。ただし unit 830・880 の `obj` が 923 の `obj` と同一オブジェクトかは未確認 (下の注)。
- unit 45 と 101 の書込みは `obj+8`・`obj+16` を設定する。`obj+0` は触らない。
- 923 の trap は unit 830・880 より後で起きる。

**unit の対応**: 監視を全 unit で ON にしたため、同じ番地が unit 830・880 で別のオブジェクトを指す可能性がある。`obj` の同一性は、trap 時点の `obj` (923) と unit 830・880 の時点の `obj` を突き合わせて確認する必要がある (未了)。

## 3. 923 の trap 時点 (inspector 実測、同一 build)

`node --wasm-enforce-bounds-checks --import ./trap_triage/inspect_trap.mjs m11_survey.mjs` (`M11_SURVEY_UNITS` で 942 unit の JSON を採取)。`wasm-function` の番号は build ごとに変わるため、`function_410b10` は名前で引いた。

| 項目 | 値 |
|---|---|
| trap 関数 | `function_410b10` (wasm 14906、OOB 命令 0x355476) |
| `obj` (local `$var0`) | `0x10bd3960` (線形メモリ内) |
| `*(obj)` (addr = obj, 先頭 8 B) | 0 |
| `*(obj+8)` | `0x10bd3330` |
| 呼出し鎖 | `function_410730` (local0 = 同じ obj) ← `function_4fb910` (local0 = 0xf6b900, local1 = 0x1fa8d8) ← `function_136c660` ← `m11_icall` ← `m11_call_unit` (unit 923) |

- `function_4fb910` の local1 = `0x1fa8d8` は、IR 定数 `2074840` と一致する (REPORT_APPENDIX_2785 §2-2 の `0x1faa18` は本 build では出ない)。
- 注: `M11_SURVEY_STACK=923` の先頭フレームは wasm 14906。REPORT_1602 §16 の 14900 とは番号が違う (build 差)。

## 4. 回帰 (受入 3)

本 PR はコードを変えない (`git diff 68d5cb3c4 HEAD -- tools/m11` は本付録と `trap_triage/watch_obj_3823.sh` の追加のみ)。既定 survey の unit 別 JSON は同じ HEAD で 1 回取得した (`ok 873 / trap 21`)。**別 run の JSON との unit 突合は未実施**のため、回帰 0 の確認にはなっていない。計測 build (全 store 計装) は既定と挙動が違うので、突合の対象にしない。この run の既定値 (873 / 21) は REPORT_714 §12 (870 / 24) と一致しない。差の由来は未特定 (REPORT_APPENDIX_2785 §1 と同じ差)。

**注 (unit 対応)**: 監視は unit 0 から ON のまま全 unit を回したので、同じ番地 0x10bd3960 が unit ごとに別オブジェクトを指す可能性がある。923 の `obj` と同一かは、unit 830・880 の時点の `obj` 値を採らないと確定しない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 830・880 の `function_10c7cd0`・`function_125da90` を呼ぶ呼出し元の特定。obj を宛先にする側 (0 を書く由来) | 923 の OOB の除去 | 子 issue (本 PR の完了後に起票) |
| 監視の unit 対応 (同じ番地が unit 830・880 で同じオブジェクトか) | 同上 | 同上 |
| 既定 survey の差 (873/21 と 870/24) の由来 | 受入 3 の基準値 | #1426 (継続) |
