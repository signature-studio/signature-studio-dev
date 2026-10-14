# 付録: icall #2280 (ICALL-70) — cookie global 0x18125eaa8 の load 幅 i32 の欠陥段の特定と修復

> 親: #2262 (ICALL-69)。前付録: `REPORT_APPENDIX_2262.md`。
> 受入条件 1 (欠陥段の特定) は前 run の IR 差分の記録値 (本 run では未再確認)。受入条件 2・3 (修復の効果と abort 消去) は
> 記録値のみで、本 run では再測定していない (未検証・§2)。受入条件 2・3 は #2302 へ移管 (#2280 本文から除外)。修復の初期値 `COOKIE_INIT` の出所が未確認のため、
> `fa_route_build.sh` の `FA_FIX_COOKIE` は**既定 OFF** に変更した (修復は明示的に `FA_FIX_COOKIE=1` を与えた run だけ有効)。
> 値の一致 (戻り値) は未達のため子 issue へ移管 (§5)。

## 1. 結論

- **欠陥段**: RetDec の `converting global variables` 段 (decode 前段の global 型決定)。RetDec 自身の生出力
  `lift/fa.drc.c` に `int32_t g26 = 0x2ddfa232; // 0x18125eaa8` (i32) として現れ、以後の段 (drc / restore / flatten) は型を引き継ぐ。
  - `before.0.drc.ll` の時点で既に `@global_var_18125eaa8 = ... global i32` と `load i32` (13 箇所)。
  - native `0x181055400` は `mov rbx, qword ptr [rip+0x209693]` (64bit 読込) と `xor rbx, qword ptr [...]` (64bit) で読む。
- **修復**: `tools/icall/ir_fix_cookie.py` (新規)。restore 後 IR で cookie global の宣言型を i64 にし、13 箇所の
  `load i32` を `load i64` + `trunc i64 → i32` (既存の i32 利用の互換) に置換し、`sext i32 → i64` 13 箇所を `add i64 %ck, 0` へ置換。
  `fa_route_build.sh` の step 1 に挿入。既定は OFF (`FA_FIX_COOKIE=1` で有効化)。
- **効果 (記録値・未再確認)**: 前 run の記録では `function_181055400` の cookie 読込が `load i64` になり、
  `FA_ENC_INIT=1` の `fa_cmp.py 1810553d0 --n 2` が OFF `wasm_err=2` → ON `wasm_err=0` (abort 消去)。
  ただし修復の初期値が未確認 (§3) のため、この効果は「修復が正しい」の根拠にならない。本 run では再測定していない。

## 2. 測定 (SlateCore.core_64、closure 131 関数の artifact `work-icall`)

測定 commit: `52bd5e41` (コード変更を含む最後の commit)。コード差分は §6。
**注記 (本 run)**: 下表は前 run の**記録値**であり、本 run では再測定していない (未検証)。
素材 `work-icall`・`plugins-freshair`・`toolchain-*` が無い (`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ。`fl-win64` 内に SlateCore の PE は無い)。
クリーン HEAD (`git worktree add --detach <dir>/work/wt_verify 52bd5e41`) での再測定は未実施。
表の列 "ON (`FA_FIX_COOKIE=1`)" は修復有効時の値。**既定 (`FA_FIX_COOKIE` 未指定 = OFF) の build の測定は存在しない**ため、既定挙動は未検証。
fa_sweep の ON 値は 2 値があり正本が未確定: **未確定 (2 値: 47/64/11/9 と 47/64/9/11)**。どちらが正しいかは本 run で判定できない (未解決 §5)。

| 項目 | OFF (`FA_FIX_COOKIE=0`) | ON (`FA_FIX_COOKIE=1`) |
|---|---|---|
| `fa_route_build.sh` (FA_ENC_INIT=1) | rc=0 | rc=0 (emcc 5.5s) |
| `fa_cmp.py 1810553d0 --n 2` | `wasm_err=2` (`Aborted`) / match 0 | `wasm_err=0` / match 0 / mismatch 2 (戻り値 0x0) |
| `fa_sweep.sh 8 60` (同一 build・同一環境) | 47 / 64 / 11 / 9 (bit一致 / crash・timeout / wasm のみ err / 不一致) | 未確定 (2 値: 47/64/11/9 と 47/64/9/11。REPORT 原記載と PR 初版が不一致) |
| `fa_sweep` 別実行 (ON) | — | 48 / 64 / 9 / 10 (REPORT 原記載。実行ごとの揺れとして記録。本 run では未再現) |
| `slot_trace.sh` (SLOT_ENC_INIT=1) | — | zero-fill VA 10 / 既知 12 hit 3 miss 9 (REPORT と一致) |

- native 側 `1810553d0` の戻り値は `0xc000c5300342457c` (`enc_slots` 後)。wasm ON は `0x0`。
  decode が 0 となり call が skip された経路の戻り値であり、native の戻り値とは別物。値の一致は本 run では判定しない (§5)。
- `fa_sweep` は実行ごとに bit一致が ±1 揺れる (47/48 の記録)。ON/OFF の関数単位比較 (class が変わった関数の一覧) は**未取得**。以前の「分類が変わった関数 0 件」は、同一 build の 2 回実行の関数単位比較に基づかないため撤回する。
- 既定 (`FA_FIX_COOKIE` 未指定) の build は本 PR で既定 OFF に変えたため、修復前と同一のコードパスになる。ただしこの build の `fa_sweep`・`fa_cmp` は未測定。

## 3. 機構の根拠 (数値)

- native `0x181055400`: `mov rbx,[0x18125eaa8]` (8byte) → `xor rbx,[0x1813068f8]` → `ror rbx,cl` (cl = cookie & 0x3f)。
- lifted (修復前): `load i32` → `sext i32 → i64` → `xor` → `urem i32 %1, 64` → `ror`。上位 32bit が落ちる。
- 修復後: `load i64` → `add i64 %ck, 0` (decode 用の 64bit 値)。`urem` の下位 bit 利用は `trunc` 経由で従来どおり。
- **cookie 初期値 `COOKIE_INIT = 0x2b992ddfa232` (`ir_fix_cookie.py`) の出所は未確認**。RetDec 生出力の初期値は `0x2ddfa232` (i32) のみで、上位 32bit `0x2b99` の根拠は無い。PE 上の VA `0x18125eaa8` の 8byte 読み取りは未実施: 素材 `plugins-freshair` の SlateCore.core_64 が無く、`fl-win64` の PE 群にも該当 DLL は無い (`tar --zstd -tf` で確認、installer exe 1 本のみ)。出所が確定するまで修復は既定 OFF。
- `FA_ENC_INIT=1` の `fa_cmp.py` は encoded slot を enc(NULL)=cookie で敷くため、cookie の値そのものは `ir_fix_cookie.py` の初期値に依存する。初期値が誤っていれば `wasm_err=0` の結果も誤りうる。依存の有無は未検証。

## 4. 再現

```
tar --zstd -xf "$HOME/artifacts/work-icall.tar.zst"                # リポジトリ直下 (tools/icall/work/ を含む)
mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$HOME/artifacts/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
bash tools/ott/native/build.sh
FA_ENC_INIT=1 bash tools/icall/fa_route_build.sh                    # 既定 (cookie 修復 OFF)
FA_ENC_INIT=1 python3 tools/icall/diff/fa_cmp.py 1810553d0 --n 2
FA_FIX_COOKIE=1 FA_ENC_INIT=1 bash tools/icall/fa_route_build.sh    # 修復 ON (初期値の出所確定まで検証用)
```

- `plugins-freshair` は tarball のまま `FA_DL` に渡せない (展開が必要)。展開先は `$RUNNER_TEMP/plugins-freshair`。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1810553d0` の wasm 戻り値 (ON=0x0) と native (0xc000c5300342457c) の不一致。call skip 経路の戻り値の仕様と、`enc_slots` 後の native 戻り値の扱いの確認 | 受入条件 (値の一致) 未達 | #2302 (ICALL-71) |
| `fa_sweep` の bit一致が実行ごとに ±1 揺れる原因 | sweep 件数の判定精度 | #2302 (ICALL-71) |
| `fa_sweep` ON 値の正本 (47/64/11/9 か 47/64/9/11 か) と関数単位の class 差分 | 「分類が変わった関数 0 件」の根拠 | #2302 (ICALL-71) |
| cookie 初期値 `0x2b992ddfa232` の出所 (PE 読み取り) と ON 結果の初期値依存 | 修復の正しさ (cookie 値) | #2302 (ICALL-71) |
| クリーン HEAD (`52bd5e41`) での再測定 (素材 `work-icall`・`plugins-freshair`・`toolchain-*` 取得後) | 測定の再現性 | #2302 (ICALL-71) |
| 0x1813068f8 の表への包含判定 | 受入条件 (表への包含判定) | #2224 (ICALL-64)・#2226 (ICALL-66) |

## 6. 測定コードの鮮度

測定 commit は `52bd5e41` (測定対象のコードを含む最後の commit)。以後の commit のうち `fa_route_build.sh` の既定値変更 (`f871b2ae`) は**実行されるコードの変更**であり、測定値 (§2 の表) は既定 OFF の build には当たらない。REPORT・PR 本文の追記 commit (`25716308`・`e7e4e39b`) は測定対象のコードを変えていない。

```
$ git diff 52bd5e41 HEAD -- tools/icall/fa_route_build.sh tools/icall/ir_fix_cookie.py
 tools/icall/fa_route_build.sh | 3 ++-
 1 file changed, 2 insertions(+), 1 deletion(-)
```

差分の中身 (`git diff 52bd5e41 HEAD -- tools/icall/fa_route_build.sh`): `FA_FIX_COOKIE` の既定 `1→0` と注記の追加のみ。`ir_fix_cookie.py` は差分 0。
§2 の数値は `FA_FIX_COOKIE=1` を明示した build (=測定時の既定) の記録値であり、現在の既定 (OFF) の build は未測定。既定 (`FA_FIX_COOKIE` 未指定) は `fa_route_build.sh` の分岐上 `FA_FIX_COOKIE=0` と同一経路 (`SRC_FIX=SRC`) なので、§2 の OFF 列 (`FA_FIX_COOKIE=0`・測定 commit `52bd5e41`) はその経路の記録値として扱える。ただし既定指定での再測定は未実施。

基点 main からのコード差分 (本 run のコード変更の全量):

```
$ git diff 44b68224 52bd5e41 -- tools/icall/fa_route_build.sh tools/icall/ir_fix_cookie.py
 tools/icall/fa_route_build.sh |  8 ++++++-
 tools/icall/ir_fix_cookie.py  | 90 ++++++++++++++++++++++++++++++++++
 2 files changed, 97 insertions(+), 1 deletion(-)
```

## 7. 数値の再現コマンド (WORKFLOW §5)

本 run では素材 `work-icall` が無く、以下は**未実行** (コマンドのみ記録)。実行結果は本節に書かれていない。
受入条件 1・2 の数値は本 run で再確認していない (未検証・前 run の記録値)。

```
grep -c 'load i32, i32\* @global_var_18125eaa8' work/rt_freshair-core/before.0.drc.ll   # 期待: 13 (§1) 【未実行】
python3 tools/icall/ir_fix_cookie.py <入力.ll> <出力.ll>                                # JSON: loads_fixed / sext_fixed 【未実行】
grep -c 'load i64, i64\* @global_var_18125eaa8' work/fa_route/cookie_fixed.ll          # 修復後の load i64 件数 【未実行】
```

- `sext` の 13 件は本 run で再集計していない。`load i32` 13 件も同様に本 run では未再確認。
