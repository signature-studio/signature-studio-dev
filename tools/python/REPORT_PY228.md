# PY-228 (#3656): plugins.getParamValueString の index・slotIndex を PE で確定し C・mock に実装する

親: #2950 (PY-115)。子: #3684 (PY-232・`useGlobalIndex` の表 A/B の実値。本 issue の本文から外した受入条件)。既知類型との関係: 該当なし (lift 作業ではない。PE の静的読みと provider の実装のみ。`docs/DEFECTS.md` の D1a〜D25 のいずれにも当たらない)。

## 結論

1. **PE の確定**: `plugins.getParamValueString` (`0xd7f940`) の `slotIndex != -1` 経路 (`0xd7fb34`〜) を読み、戻り値の組立てと範囲検査を確定した (§2・§3)。同じ解決の並びは `getParamValue` (`0xd7fda0`) と `setParamValue` (`0xd80160`) にもある (§2・§5)。
2. **C・mock**: 値を **channel ごと・mixer track の insert slot ごと** に持つ。`setParamValue` が書き、`getParamValue` と `getParamValueString` が読む (読み書きを揃えた。読出し側だけを変えると MCP の set→get が壊れるため)。範囲外は code 4、空 slot は code 8 (`Plugin not valid`)、挿入で既定値に戻る。
3. **差分検査**: `tests/plugins_diff.mjs` を追加。56 呼出し・差分 0・PASS (review round 1 で型検査 10 件を追加)。空 slot の判定を外すと **4 件の差分で FAIL**、戻すと 56/0 PASS (56 呼出し版で再測定。§5)。
4. **flpy 経由**: round 1 で `tests/poc_mcp.mjs` の値の検査を channel の `pv` に直し、`get_plugin_parameter_value` の set→get (`90.0 %`) も検査した。flpy (CPython wasm) を作って実行し PASS (§1・§6)。`provider_check.mjs` と `all_tools.mjs` (FL_ENGINE=wasm) も PASS。親 #2950 の受入の一部はこれで確認した。

## 1. 測定

| 項目 | 値 |
|---|---|
| 測定 commit (コードを最後に変えた commit) | `656d01e7d` (`Merge remote-tracking branch 'origin/main' into 3656-plugins-getparamvaluestring`。main `1ccf20c6a` を取り込んだ merge)。取り込みで `tools/python/host/fl_mock.mjs` が衝突 (§6)。取り込み後に全項目を再測定。前回の測定 commit は `6ee6d1401` (main `dadf1884b` の取り込み。round 2 の前) |
| 素材 | `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (real 5.570 s)。emsdk は runner 同梱のもの (`EMSDK_DIR` の既定値) を使い、`toolchain-emsdk` は展開していない |
| 入力 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/python/fetch_inputs.sh` (midi.py・utils.py・fl-stubs を取得。real 0.417 s)。`build_flpy.sh` は stubs を要するため、これを先に実行する |
| flpy | `bash tools/python/build_cpython_wasm.sh` (native + wasm の CPython 3.12.1。rc 0・real 4 m 08 s)、`FL_WIN64_DIR=… bash tools/python/build_flpy.sh` (rc 0・real 7.092 s。`dist/flpy.{js,wasm,data}`)。`analysis/flapi` の追跡物は再生成後も差分なし |
| build (provider) | `bash tools/python/provider/build.sh`。rc 0。警告 0 |
| flpy 経由 (MCP) | `node tests/poc_mcp.mjs` → `POC OK` (rc 0・real 1.28 s)。tools 48・host_calls 20563・roundtrip 37 µs/call (init 161 ms)。`set_plugin_parameter_value` → `Set 'Cutoff' … to 0.9000`、続く `get_plugin_parameter_value` → `Normalized Value: 0.9000, String Value: '90.0 %'`。channel 2 の `pv[0]` = 0.9、channel 0 の `pv[0]` = 0.5 |
| 修正前 (参考) | 同じ flpy で `poc_mcp.mjs` を `7608e7950` の状態 (旧 assert) で実行 → `AssertionError` (`tests/poc_mcp.mjs:69`・`params[0].v` が 0.5 のまま)。指摘どおり |
| provider 経由 | `node tests/provider_check.mjs` → `{"functions":435,"implemented":165,"unimplemented":270,"mcp_static":60,"PASS":true}` (real 0.37 s。main 取り込みで実装数 162 → 165)。`FL_ENGINE=wasm node tests/all_tools.mjs` → total 48・ok 48・soft_error 0・raised 0・host_calls 37425 (real 2.09 s。既存 REPORT_APPENDIX の 37,425 と一致) |
| 差分 (新規) | `node tests/plugins_diff.mjs` → `{"calls":56,"diffs":0,"PASS":true}` (real 0.05 s。初版は 46 呼出し) |
| PE 解析 | `FL_WIN64_DIR=… python3 analysis/flapi/plugins_paramvalue_facts.py`。PASS 20 / FAIL 0 / rc 0。経路別の VA 絞り込み版 (§2)。real 0.088 s |
| 差分 (既存・回帰) | `mixer_diff` 69・diffs 0 (0.05 s) / `channels_diff` 238・grid_calls 1200・diffs 0 (0.07 s) / `device_diff` 11・diffs 0 (0.05 s) / `ilmcp_diff` 32・diffs 0 (0.06 s) / `ilmcp_e2e` PASS (0.47 s)。mock の `all_tools.mjs` は 48/48・host_calls 37425 (2.00 s) |
| arity 検査 | `node tests/sig_arity_probe.mjs` → fails 0・PASS (実装済み関数に `plugins.getParamValueString` を含む)。real 0.05 s |
| load | 測定の直前 `load average 0.39 1.27 0.77` (4 core・uptime 04:03)。ビルド開始時は `0.24 0.29 0.14` |

測定は worktree `ws-3656` (PR 枝 `3656-plugins-getparamvaluestring`) で行った。`git diff 656d01e7d HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis` の出力は 0 行 (測定 commit の後は REPORT と `docs/DOC_MAP.md` の commit だけ)。

## 2. PE の逆アセンブル (根拠)

`block00031_PE.bin` を capstone で読んだ。VA は ImageBase 基準。`analysis/flapi/plugins_paramvalue_facts.py` が下表の行を assert する。経路の所属は VA で絞る (round 1): slot -1 の行は `0xd7fb34` より前の命令、slot ≥ 0 の行は `0xd7fb34` 以降の命令だけを見る。値の参照 (`0xd84740`)・文字列化・getParamValue (`0xd7fda0`)・setParamValue (`0xd80160`) の行は関数単位の窓で見る (経路の所属は見ない)。

| 対象 | VA | 逆アセンブルの事実 |
|---|---|---|
| 引数 | `0xd7f940`・`flapi_kwargs.json` | fmt `ii\|ii`、kwlist `paramIndex, index, slotIndex, useGlobalIndex`。`index` と `paramIndex` は必須、`slotIndex` の既定 `-1` (`[rbp+0xa8]` へ `mov dword ptr [rbp+0xa8], 0xffffffff`)、`useGlobalIndex` の既定 `0` |
| slot 判定 | `0xd7fa02`〜`0xd7fa09` | `cmp dword ptr [rbp+0xa8], -1` → `jne 0xd7fb34` (slot ≠ -1 は別経路) |
| channel 解決 | `0xd7fa16`〜`0xd7fa2d` | `ecx = index`、`dl = (useGlobalIndex > 0)`、`call 0x1005730(index, dl, &obj)`。偽なら code -4 |
| 0x1005730 | `0x1005730`〜`0x10057b7` | `test dl, dl` で分岐。`dl != 0` は表 A (`[rip+0x5dcad3]`)、`dl == 0` は表 B (`[rip+0x5da9a8]`)。範囲は `0 ≤ index ≤ [tbl+0x10]-1`。要素は `call 0xfe8bb0`。表 A・B は `.bss` で実行時に初期化される (未確定) |
| 有効性 | `0x132f780` (`d7fa41`・`d7fbaf`) | `cmp dword ptr [rcx+0x64], 0; setge al`。偽なら code -8 (`d7fb28`・`d7fc87`)。channel 経路 (`d7fa41`) でも検査される (§3 の注) |
| paramIndex 範囲 | `0xd7fa55`〜`0xd7fa95`、`0xd7fbb5`〜`0xd7fbf5` | 件数 `[obj+0x68]` の `-1` を `rax` に取り、`0 ≤ paramIndex ≤ rax` を検査 (件数 1 以下の分岐は `rax ≤ 0` で別に書かれている。NPARAM = 3 の model では到達しない) |
| 値 (channel) | `0xd7fa9b`〜`0xd7fac9` | `call 0xd84740(rsi, &out, id, 0, 2)`、`id = [obj+0x9c] + paramIndex + 0x8000` (`add r8d, [rbp+0xa4]`・`add r8d, 0x8000`)。`out` の先頭 qword ≠ 0 なら error |
| 文字列 (channel) | `0xd7fadb`〜`0xd7fb17` | `call 0x104d2b0(&s, edx=id, r8d=[out+8])` → `call 0xc3cfa0` → 戻り値 `[rbp+0x58]` |
| slot の index 範囲 | `0xd7fb3b`〜`0xd7fb5d` | `index < 0` または `index > [0x15e2198]-1` (mixer 件数 dword) で code -4 |
| slot の上限 | `0xd7fb63`〜`0xd7fb77` | `slot < 0` または `slot > 9` で code -4 (`cmp rax, 9; jg`) |
| slot の obj | `0xd7fb7d`〜`0xd7fb9d` | `rax = [0x15e06a0] + index*0x28f*8`、`rbx = [rax + slot*8 + 0x134c]` (要素 stride 0x1478) |
| slot の id | `0xd7fc01`〜`0xd7fc24` | `0x12be250(index, slot)` を基底にし、`id = base + paramIndex + 0x70008000`。`0x12be250` は `((index<<6) + slot) << 16` (`mov eax,ecx; shl eax,6; add eax,edx; shl eax,0x10; ret`) |
| エラー文言 | `0xd82c20` の分岐 | code -4 → 文字列 `0xd82e8c` = `Index out of range`。code -8 → `0xd82f3c` = `Plugin not valid` (ASCII で確認) |
| getParamValue | `0xd7fda0` | 同じ解決の並び (`call 0x1005730`・`call 0x132f780`・件数の `sub eax,1`・`cmp rax, 9`)。値の取得は `0x1331340` 経由の vtable 呼出し (`call [rax+0x20]`・`call [rax+0x30]`)・`0xd7fd40` で、**値の核は未読** |
| setParamValue | `0xd80160` | `call 0x1005730`・`call 0x132f780`・`call 0x12be250` の並び。書込み前に `call 0xf81ce0`・`call 0x40c660`・`mov r8d, 0x3fd`・`call 0x1051d20` の検査があり、**その意味は未読** |

## 3. 解決順と戻り値 (PE で確定した部分と、未確認のモデルの置き)

PE の順に従う (C・mock も同じ順)。置き (未確認) の行は表の後の注と §7 に分けた。

| 順 | 判定 | 失敗時 (code) |
|---|---|---|
| 1 | `slotIndex == -1`: `index` を channel として解決 / `slotIndex != -1`: `index` を mixer track として検査 (PE は `[0, [0x15e2198])`。モデルは `[0, 127)` と置く) | -4 → 4 (`Index out of range`) |
| 2 | `slotIndex != -1` のとき `slotIndex ∈ [0, 9]` | -4 → 4 |
| 3 | 有効性 (`0x132f780` = `[obj+0x64] >= 0`): PE は channel 経路 (`d7fa41`) と slot 経路 (`d7fbaf`) の両方で検査する。モデルは channel を常に有効、slot は `mx[i].slots[s][0] != 0` で代用 (置き) | -8 → 8 (`Plugin not valid`) |
| 4 | `paramIndex ∈ [0, 3)` | -4 → 4 |
| 5 | 値の所在: channel は `ch[index].pv[paramIndex]` / slot は `mx[index].spv[slot][paramIndex]` | — |

- 文字列は `"%.1f %%"` で値 × 100 を整形する (既存の書式を維持)。PE 側の書式 (`0x104d2b0`) は**未読**。
- `useGlobalIndex` は `dl` として解決に渡すだけで、group 配列の実値が無いため結果は変えない (identity)。子 #3684 で扱う。
- **有効性と範囲の置き (未確認)**: 
  - channel: PE は slot -1 経路でも `0x132f780` (`[obj+0x64] >= 0`) を検査し、偽なら code -8 を返す。モデルは「`index` が範囲内の channel は常に有効」と置く。この根拠 (channel の plugin obj で `[obj+0x64] >= 0` が常に成り立つこと) は**未確認**。モデルの channel は追加・削除で列挙が変わるだけで、偽になる状態は作れない。
  - slot: `0xd7fbaf` の `0x132f780` が偽のとき code -8 を返すこと (`0xd7fbaf` → `0xd7fc87`) までを PE で確かめた。空 slot の obj が `[obj+0x64] < 0` を取ることは読んでいない。モデルの `slots[s][0] != 0` は置き。C の `pinst()` は `slots[s][0]` の 0 判定だけで、`[obj+0x64]` は読まない。
  - track の範囲: PE は `[0x15e2198]-1` (mixer 件数) の実行時比較で、`127` はモデルの置き。
  - いずれも §7 の未解決表に入れる。

## 4. C・mock の変更

| ファイル | 変更 |
|---|---|
| `provider/fl_engine.c` | `Chan.pv[NPARAM]`・`Mix.spv[NSLOT][NPARAM]` を追加。既定値は `params[].v` (0.5・0.2・0.8)。`pinst()` が §3 の順で解決し、`getParamValue`・`getParamValueString`・`setParamValue` が共有。`pvals` 全体と `PP` マクロは削除。`addEffect` は挿入する slot の値を既定に戻す |
| `host/fl_mock.mjs` | `PARAM_DEFAULT` と `plugPV()` (C の `pinst` と同じ順)。channel に `pv`、mixer に `spv`。3 関数を `arity` 検査付きで置換 (`getParam*` は 2〜4、`setParamValue` は 3〜6 = PE の必須・最大と一致)。round 1 で引数の型検査を追加: `argI` (fl_a_int 相当)・`argD` (fl_a_dbl 相当)。検査順は C の handler と同じ (`getParam*`: paramIndex・index・slotIndex・useGlobalIndex / `setParamValue`: 値 → paramIndex・index・slotIndex → 4 番目・5 番目 (pickupMode・useGlobalIndex)、型だけ見て捨てる) |
| `host/ilmcp.mjs` | `addEffect` が slot の値を既定に戻す |
| `tests/plugins_diff.mjs` | 新規。56 呼出し + 期待値の直接検査 (初版 46 + round 1 の型検査 10) |
| `tests/poc_mcp.mjs` | round 1: 値の検査を `channels[2].pv[0]` に直す (`params[]` は変えない)。`get_plugin_parameter_value` の set→get 一致 (`90.0 %`) を検査 |
| `analysis/flapi/plugins_paramvalue_facts.py` | 新規。PE の根拠 20 件を assert。round 1 で経路所属を VA で絞る (§2) |

MCP の呼出し形は `analysis/mcp/tool_coverage.json` の実測で `getParamValue/4`・`getParamValueString/4`・`setParamValue/6` (個数は新しい arity 検査の範囲内)。`get_plugin_parameter_value` は `String Value: '50.0 %'` (既定値)、`set_plugin_parameter_value` は `0.9` を書く。既定値の経路は従来と同じ値を返す。

## 5. 差分検査の内容と期待値

`tests/plugins_diff.mjs` の 56 呼出し (初版 46 + round 1 の型検査 10) は次を含む (mock と C の戻り値・code が一致することを確認)。

- channel: 既定値 (`50.0 %`・`20.0 %`・`80.0 %`)、set 後の値 (`25.0 %`)、他 channel への非波及 (`50.0 %`)、`useGlobalIndex=1` の identity、6 引数の set (`12.5 %`)。
- 範囲外: paramIndex 3・-1、channel index 3・-1 → code 4。slot 10・-2、track 127 → code 4。
- 空 slot: get・getValue・set → code 8。挿入 (`ilmcp.addEffect`) で有効化、set 後 `75.0 %`、channel は `25.0 %` のまま、削除で code 8、再挿入で既定値 `50.0 %`。
- channel の追加 (`ilmcp.addChannel("BassDrum")`) と削除 (`removeChannel`) 後の範囲。
- 個数・型: 引数 1 個・2 個 (set)・文字列の index → code 5。round 1 で追加: 文字列の useGlobalIndex (`getParamValueString`)・pickupMode (`setParamValue` の 5 番目)・値 (`setParamValue`) → code 5 (C と mock の両方を直接検査)。`None` は既定値、`true` は 1.0 として通る (channel 1 の Gain に書いて 0.5 で書き直す)。

期待値の直接検査 (差分 0 だけでは両方が同じに誤る場合を防ぐ): mock と C の両方で `25.0 %`・`50.0 %`・`12.5 %`・`75.0 %` 等を assert し PASS。

**ネガティブコントロール** (56 呼出し版・測定 commit `656d01e7d` で取り直し): `pinst()` の空 slot 判定 (`if (!mx[index].slots[slot][0]) return fl_err(… "Plugin not valid")`) を一時的に外して `bash tools/python/provider/build.sh` (rc 0・警告 0) で再ビルドし、`node tests/plugins_diff.mjs` → `plugins 差分 4 件` で FAIL (rc 1)。判定を元に戻して再ビルド (rc 0・警告 0) し、`{"calls":56,"diffs":0,"PASS":true}` (rc 0) を確認。戻した後の `git diff 656d01e7d -- tools/python/provider` は 0 行。初版 (46 呼出し・測定 commit `a84a424ad`) の PASS 46/0 は参考値。

## 6. 差分の確認と未実行

- `git diff 656d01e7d HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis` は本 REPORT の commit 後も**差分 0** (本 REPORT と `docs/DOC_MAP.md` の登録だけが後の commit)。
- main (`1ccf20c6a`) の取り込み (`656d01e7d`): `tools/python/host/fl_mock.mjs` の衝突は step 定義の行 (`STEP_DEF`・`stepParam`) だけ。main 側 (PY-111: `prm` は 8 まで・`prm === 7` は `pos * STEP_V`) を採り、本 PR の `PARAM_DEFAULT` を残した。`provider/fl_engine.c` は自動マージ。取り込み後に `fetch_inputs.sh`・`build_cpython_wasm.sh`・`build_flpy.sh`・`provider/build.sh` を再実行し、§1 の全項目を再測定した。
- 前回の取り込み (`6ee6d1401`、main `dadf1884b`): `provider/fl_engine.c` の衝突は `Pl` 構造体だけ。main 側の `Pl` を採り、`Chan`・`Mix` は本 PR の `pv`・`spv` を残した。
- round 1 (review) で「未実行」だった `provider_check.mjs`・`all_tools.mjs` (FL_ENGINE=wasm)・`poc_mcp.mjs` を、flpy (§1) を作って実行した。いずれも PASS。`ilmcp_e2e.mjs` も PASS。
- `poc_mcp.mjs` は flpy (CPython wasm) と **mock** の flapi を使う (C provider は通らない)。C provider の値 API は `plugins_diff.mjs` (C と mock の差分 0) と `FL_ENGINE=wasm all_tools.mjs` (48/48・host_calls 37425。既存の追跡値と一致) で確認した。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `useGlobalIndex` (0x1005730 の表 A/B) の実値。group 無しの identity で扱う | `useGlobalIndex` の 0/非 0 で結果が変わる経路の確定が無い | #3684 (PY-232) |
| `setParamValue` の書込み前検査 (`0xf81ce0`・`0x40c660`・`0x3fd`・`0x1051d20`) | 検査の意味は未読。unsafe 系の code (3) を返す可能性があるが、model は返さない | #2950 へコメント (親の残り) |
| `getParamValue` の値の核 (`0x1331340` の vtable `+0x20`・`+0x30`・`0xd7fd40`) | 値の型 (float 丸め) と plugin 実体の値の出所は未確定。mock の `F` タグで代用 | #2950 へコメント |
| 文字列の書式 `0x104d2b0` | `%.1f %%` は既存値の維持で、FL の表示書式は未確認 | #2950 へコメント |
| `setParamValue` の pickupMode (kwlist 5 番目・`fii\|iii`) | C・mock は型検査だけで値を読んで捨てる (効果は未読)。useGlobalIndex は 6 番目 | #2950 へコメント |
| `setParamValue` の paramValue の書式 `f` (float32) | C・mock は double のまま (`A_DBL`)。PE の float32 丸めの差は未確認。`%.1f` 表示では差が出ない | #2950 へコメント |
| channel の有効性 `[obj+0x64] >= 0` (`0x132f780`) の根拠 | モデルは範囲内の channel を常に有効と置く (§3)。偽になる channel 状態は作れない | #2950 へコメント |
| slot の有効性 (空 slot の obj が `[obj+0x64] < 0` を取る条件) と track 範囲の件数 `[0x15e2198]` | モデルは slot の空判定を `slots[s][0] != 0`、track の範囲を 127 と置く (§3)。偽になる条件と件数の出所は未読 | #2950 へコメント |
