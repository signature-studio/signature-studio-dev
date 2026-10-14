# 付録: icall #2280 (ICALL-70) — cookie global 0x18125eaa8 の load 幅 i32 の欠陥段の特定と修復

> 親: #2262 (ICALL-69)。前付録: `REPORT_APPENDIX_2262.md`。
> 本 run は受入条件 1 (欠陥段の特定) と 2 (修復と cookie 読込の i64 化) と 3 のうち abort 消去を達成。
> 値の一致 (戻り値) は未達のため子 issue へ移管 (§5)。

## 1. 結論

- **欠陥段**: RetDec の `converting global variables` 段 (decode 前段の global 型決定)。RetDec 自身の生出力
  `lift/fa.drc.c` に `int32_t g26 = 0x2ddfa232; // 0x18125eaa8` (i32) として現れ、以後の段 (drc / restore / flatten) は型を引き継ぐ。
  - `before.0.drc.ll` の時点で既に `@global_var_18125eaa8 = ... global i32` と `load i32` (13 箇所)。
  - native `0x181055400` は `mov rbx, qword ptr [rip+0x209693]` (64bit 読込) と `xor rbx, qword ptr [...]` (64bit) で読む。
- **修復**: `tools/icall/ir_fix_cookie.py` (新規)。restore 後 IR で cookie global の宣言型を i64 にし、13 箇所の
  `load i32` を `load i64` + `trunc i64 → i32` (既存の i32 利用の互換) に置換し、`sext i32 → i64` 13 箇所を `add i64 %ck, 0` へ置換。
  `fa_route_build.sh` の step 1 に挿入 (`FA_FIX_COOKIE=0` で無効化)。
- **効果 (実測)**: `function_181055400` の cookie 読込は `load i64` になった (`work/fa_route/cookie_fixed.ll`)。
  `FA_ENC_INIT=1` の `fa_cmp.py 1810553d0 --n 2` は OFF で `wasm_err=2` (abort)、ON で `wasm_err=0` (abort 消去)。

## 2. 測定 (SlateCore.core_64、closure 131 関数の artifact `work-icall`)

測定 commit: `44b68224` (origin/main 基点の 2280 ブランチ)。コード変更は §6 の差分。

| 項目 | OFF (`FA_FIX_COOKIE=0`) | ON (既定) |
|---|---|---|
| `fa_route_build.sh` (FA_ENC_INIT=1) | rc=0 | rc=0 (emcc 5.5s) |
| `fa_cmp.py 1810553d0 --n 2` | `wasm_err=2` (`Aborted`) / match 0 | `wasm_err=0` / match 0 / mismatch 2 (戻り値 0x0) |
| `fa_sweep.sh 8 60` (同一 build・同一環境) | funcs 131 / bit一致 47 / crash・timeout 64 / wasm のみ err 11 / 不一致 9 | 同左 (分類が変わった関数 0 件) |
| `fa_sweep` 別実行 (ON) | — | funcs 131 / bit一致 48 / crash・timeout 64 / wasm のみ err 9 / 不一致 10 (実行ごとの揺れ) |
| `slot_trace.sh` (SLOT_ENC_INIT=1) | — | zero-fill VA 10 / 既知 12 hit 3 miss 9 (REPORT と一致) |

- native 側 `1810553d0` の戻り値は `0xc000c5300342457c` (`enc_slots` 後)。wasm ON は `0x0`。
  decode が 0 となり call が skip された経路の戻り値であり、native の戻り値とは別物。値の一致は本 run では判定しない (§5)。
- `fa_sweep` は実行ごとに bit一致が ±1 揺れる (47/48)。ON/OFF の関数単位比較 (同一 build の 2 回実行) で分類が変わった関数は 0 件。

## 3. 機構の根拠 (数値)

- native `0x181055400`: `mov rbx,[0x18125eaa8]` (8byte) → `xor rbx,[0x1813068f8]` → `ror rbx,cl` (cl = cookie & 0x3f)。
- lifted (修復前): `load i32` → `sext i32 → i64` → `xor` → `urem i32 %1, 64` → `ror`。上位 32bit が落ちる。
- 修復後: `load i64` → `add i64 %ck, 0` (decode 用の 64bit 値)。`urem` の下位 bit 利用は `trunc` 経由で従来どおり。

## 4. 再現

```
tar --zstd -xf "$HOME/artifacts/work-icall.tar.zst"                # リポジトリ直下 (tools/icall/work/ を含む)
mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$HOME/artifacts/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
bash tools/ott/native/build.sh
FA_ENC_INIT=1 bash tools/icall/fa_route_build.sh                    # 既定 (cookie 修復 ON)
FA_ENC_INIT=1 python3 tools/icall/diff/fa_cmp.py 1810553d0 --n 2
FA_FIX_COOKIE=0 FA_ENC_INIT=1 bash tools/icall/fa_route_build.sh     # OFF 比較
```

- `plugins-freshair` は tarball のまま `FA_DL` に渡せない (展開が必要)。展開先は `$RUNNER_TEMP/plugins-freshair`。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1810553d0` の wasm 戻り値 (ON=0x0) と native (0xc000c5300342457c) の不一致。call skip 経路の戻り値の仕様と、`enc_slots` 後の native 戻り値の扱いの確認 | 受入条件 (値の一致) 未達 | #2302 (ICALL-71) |
| `fa_sweep` の bit一致が実行ごとに ±1 揺れる原因 | sweep 件数の判定精度 | #2302 (ICALL-71) |
| 0x1813068f8 の表への包含判定 | 受入条件 (表への包含判定) | #2224 (ICALL-64)・#2226 (ICALL-66) |

## 6. 測定コードの鮮度

測定 commit は `52bd5e41` (コード変更を含む最後の commit。測定は commit 前の同一内容の作業ツリーで実施)。

```
$ git diff 44b68224 52bd5e41 -- tools/icall/fa_route_build.sh tools/icall/ir_fix_cookie.py   # 基点 main からの差分 (本 run のコード変更の全量)
 tools/icall/fa_route_build.sh |  8 ++++++-
 tools/icall/ir_fix_cookie.py  | 90 ++++++++++++++++++++++++++++++++++++
 2 files changed, 97 insertions(+), 1 deletion(-)
```
