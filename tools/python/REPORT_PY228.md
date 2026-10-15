# PY-228 (#3656): plugins.getParamValueString の index・slotIndex を PE で確定し C・mock に実装する

親: #2950 (PY-115)。子: #3684 (PY-232・`useGlobalIndex` の表 A/B の実値。本 issue の本文から外した受入条件)。既知類型との関係: 該当なし (lift 作業ではない。PE の静的読みと provider の実装のみ。`docs/DEFECTS.md` の D1a〜D25 のいずれにも当たらない)。

## 結論

1. **PE の確定**: `plugins.getParamValueString` (`0xd7f940`) の `slotIndex != -1` 経路 (`0xd7fb34`〜) を読み、戻り値の組立てと範囲検査を確定した (§2・§3)。同じ解決の並びは `getParamValue` (`0xd7fda0`) と `setParamValue` (`0xd80160`) にもある (§2・§5)。
2. **C・mock**: 値を **channel ごと・mixer track の insert slot ごと** に持つ。`setParamValue` が書き、`getParamValue` と `getParamValueString` が読む (読み書きを揃えた。読出し側だけを変えると MCP の set→get が壊れるため)。範囲外は code 4、空 slot は code 8 (`Plugin not valid`)、挿入で既定値に戻る。
3. **差分検査**: `tests/plugins_diff.mjs` を追加。46 呼出し・差分 0・PASS。ネガティブコントロールで空 slot の判定を外すと **4 件の差分で FAIL** (§4)。
4. **未実行**: `provider_check.mjs` と `all_tools.mjs` (FL_ENGINE=wasm) は `dist/flpy.js` (CPython wasm) を要するため、このランでは実行していない (§6)。親 #2950 の受入の一部。

## 1. 測定

| 項目 | 値 |
|---|---|
| 測定 commit (コードを最後に変えた commit) | `a84a424ad` (`feat(python): plugins の値 API に index・slotIndex の解決を入れる (PY-228)`) |
| 素材 | `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (real 6.681 s)。`toolchain-emsdk.tar.zst` を `$RUNNER_TEMP/opt` に展開 (real 7.638 s) |
| 入力 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/python/fetch_inputs.sh` (midi.py・utils.py・fl-stubs を取得) |
| build | `EMSDK_ENV=$RUNNER_TEMP/opt/emsdk/emsdk_env.sh bash tools/python/provider/build.sh`。rc 0。emcc の cache 温存後は real 1.203 s (初回は sysroot 生成で real 12.264 s)。警告 0 |
| PE 解析 | `FL_WIN64_DIR=… python3 analysis/flapi/plugins_paramvalue_facts.py`。PASS 20 / FAIL 0 / rc 0。real 0.083 s |
| 差分 (新規) | `node tests/plugins_diff.mjs` → `{"calls":46,"diffs":0,"PASS":true}`。real 0.045 s |
| 差分 (既存・回帰) | `node tests/mixer_diff.mjs` → calls 62・diffs 0。real 0.044 s / `node tests/channels_diff.mjs` → calls 214・grid_calls 1200・diffs 0。real 0.054 s / `node tests/device_diff.mjs` → calls 8・diffs 0。real 0.050 s / `node tests/ilmcp_diff.mjs` → calls 32・diffs 0。real 0.048 s |
| arity 検査 | `node tests/sig_arity_probe.mjs` → fails 0・PASS (実装済み 8 関数に `plugins.getParamValueString` を含む)。real 0.051 s |
| load | 測定の直前 `load average 0.05 0.17 0.16` (4 core) |

測定は worktree `ws-3656` (`origin/main` b04f3c024 から作成) で行った。

## 2. PE の逆アセンブル (根拠)

`block00031_PE.bin` を capstone で読んだ。VA は ImageBase 基準。`analysis/flapi/plugins_paramvalue_facts.py` が下表の主要な行を assert する。

| 対象 | VA | 逆アセンブルの事実 |
|---|---|---|
| 引数 | `0xd7f940`・`flapi_kwargs.json` | fmt `ii\|ii`、kwlist `paramIndex, index, slotIndex, useGlobalIndex`。`index` と `paramIndex` は必須、`slotIndex` の既定 `-1` (`[rbp+0xa8]` へ `mov dword ptr [rbp+0xa8], 0xffffffff`)、`useGlobalIndex` の既定 `0` |
| slot 判定 | `0xd7fa02`〜`0xd7fa09` | `cmp dword ptr [rbp+0xa8], -1` → `jne 0xd7fb34` (slot ≠ -1 は別経路) |
| channel 解決 | `0xd7fa16`〜`0xd7fa2d` | `ecx = index`、`dl = (useGlobalIndex > 0)`、`call 0x1005730(index, dl, &obj)`。偽なら code -4 |
| 0x1005730 | `0x1005730`〜`0x10057b7` | `test dl, dl` で分岐。`dl != 0` は表 A (`[rip+0x5dcad3]`)、`dl == 0` は表 B (`[rip+0x5da9a8]`)。範囲は `0 ≤ index ≤ [tbl+0x10]-1`。要素は `call 0xfe8bb0`。表 A・B は `.bss` で実行時に初期化される (未確定) |
| 有効性 | `0x132f780` (`d7fa41`・`d7fbaf`) | `cmp dword ptr [rcx+0x64], 0; setge al`。偽なら code -8 (`d7fb28`・`d7fc87`) |
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

## 3. 解決順と戻り値 (確定)

PE の順に従う (C・mock も同じ順)。

| 順 | 判定 | 失敗時 (code) |
|---|---|---|
| 1 | `slotIndex == -1`: `index` を channel として解決 / `slotIndex != -1`: `index` を mixer track として `[0, 127)` で検査 | -4 → 4 (`Index out of range`) |
| 2 | `slotIndex != -1` のとき `slotIndex ∈ [0, 9]` | -4 → 4 |
| 3 | 有効性: channel は常に有効 / slot は中身があること (`mx[i].slots[s][0] != 0`) | -8 → 8 (`Plugin not valid`) |
| 4 | `paramIndex ∈ [0, 3)` | -4 → 4 |
| 5 | 値の所在: channel は `ch[index].pv[paramIndex]` / slot は `mx[index].spv[slot][paramIndex]` | — |

- 文字列は `"%.1f %%"` で値 × 100 を整形する (既存の書式を維持)。PE 側の書式 (`0x104d2b0`) は**未読**。
- `useGlobalIndex` は `dl` として解決に渡すだけで、group 配列の実値が無いため結果は変えない (identity)。子 #3684 で扱う。

## 4. C・mock の変更

| ファイル | 変更 |
|---|---|
| `provider/fl_engine.c` | `Chan.pv[NPARAM]`・`Mix.spv[NSLOT][NPARAM]` を追加。既定値は `params[].v` (0.5・0.2・0.8)。`pinst()` が §3 の順で解決し、`getParamValue`・`getParamValueString`・`setParamValue` が共有。`pvals` 全体と `PP` マクロは削除。`addEffect` は挿入する slot の値を既定に戻す |
| `host/fl_mock.mjs` | `PARAM_DEFAULT` と `plugPV()` (C の `pinst` と同じ順)。channel に `pv`、mixer に `spv`。3 関数を `arity` 検査付きで置換 (`getParam*` は 2〜4、`setParamValue` は 3〜6 = PE の必須・最大と一致) |
| `host/ilmcp.mjs` | `addEffect` が slot の値を既定に戻す |
| `tests/plugins_diff.mjs` | 新規。46 呼出し + 期待値の直接検査 |
| `analysis/flapi/plugins_paramvalue_facts.py` | 新規。PE の根拠 20 件を assert |

MCP の呼出し形は `analysis/mcp/tool_coverage.json` の実測で `getParamValue/4`・`getParamValueString/4`・`setParamValue/6` (個数は新しい arity 検査の範囲内)。`get_plugin_parameter_value` は `String Value: '50.0 %'` (既定値)、`set_plugin_parameter_value` は `0.9` を書く。既定値の経路は従来と同じ値を返す。

## 5. 差分検査の内容と期待値

`tests/plugins_diff.mjs` の 46 呼出しは次を含む (mock と C の戻り値・code が一致することを確認)。

- channel: 既定値 (`50.0 %`・`20.0 %`・`80.0 %`)、set 後の値 (`25.0 %`)、他 channel への非波及 (`50.0 %`)、`useGlobalIndex=1` の identity、6 引数の set (`12.5 %`)。
- 範囲外: paramIndex 3・-1、channel index 3・-1 → code 4。slot 10・-2、track 127 → code 4。
- 空 slot: get・getValue・set → code 8。挿入 (`ilmcp.addEffect`) で有効化、set 後 `75.0 %`、channel は `25.0 %` のまま、削除で code 8、再挿入で既定値 `50.0 %`。
- channel の追加 (`ilmcp.addChannel("BassDrum")`) と削除 (`removeChannel`) 後の範囲。
- 個数・型: 引数 1 個・2 個 (set)・文字列の index → code 5。

期待値の直接検査 (差分 0 だけでは両方が同じに誤る場合を防ぐ): mock と C の両方で `25.0 %`・`50.0 %`・`12.5 %`・`75.0 %` 等を assert し PASS。

**ネガティブコントロール**: `pinst()` の空 slot 判定 (`mx[index].slots[slot][0]` の検査) を一時的に外して再ビルドし、`node tests/plugins_diff.mjs` → `plugins 差分 4 件` で FAIL。元に戻して再ビルドし PASS を確認 (`{"calls":46,"diffs":0,"PASS":true}`)。

## 6. 差分の確認と未実行

- `git diff a84a424ad HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis` は本 REPORT の commit 後も**差分 0** (本 REPORT と `docs/DOC_MAP.md` の登録だけが後の commit)。
- **未実行**: `node tests/provider_check.mjs` と `FL_ENGINE=wasm node tests/all_tools.mjs` (48/48)。`dist/flpy.js` (CPython wasm) が無く、`provider_check.mjs` は起動時に読み込んで落ちる。親 #2950 の受入 (3 本目) はこのランでは未確認。起票先: #2950 へのコメント (再測定の範囲のため新規子は起票しない)。
- 本番経路 (MCP → flpy → provider) の結果 (`String Value: '50.0 %'`) は、mock の `tool_coverage.json` の既存値と一致する見込みだが、C 経路の実測は未取得。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `useGlobalIndex` (0x1005730 の表 A/B) の実値。group 無しの identity で扱う | `useGlobalIndex` の 0/非 0 で結果が変わる経路の確定が無い | #3684 (PY-232) |
| `setParamValue` の書込み前検査 (`0xf81ce0`・`0x40c660`・`0x3fd`・`0x1051d20`) | 検査の意味は未読。unsafe 系の code (3) を返す可能性があるが、model は返さない | #2950 へコメント (親の残り) |
| `getParamValue` の値の核 (`0x1331340` の vtable `+0x20`・`+0x30`・`0xd7fd40`) | 値の型 (float 丸め) と plugin 実体の値の出所は未確定。mock の `F` タグで代用 | #2950 へコメント |
| 文字列の書式 `0x104d2b0` | `%.1f %%` は既存値の維持で、FL の表示書式は未確認 | #2950 へコメント |
| `provider_check.mjs` と `all_tools.mjs` の flpy 経由の実行 (§6) | 親 #2950 の受入の一部が未確認 | #2950 へコメント |
