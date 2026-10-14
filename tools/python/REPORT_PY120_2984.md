# tools/python REPORT: PY-120 launchMapPages 12 件の PE 確定 — `launchMapPages.length` 1 件のみ確定 (#2984・題名 [PY-153]・親 #2832)

> 正本: `tools/python/REPORT_PY87.md` (PE 確定の手順・4 件の確定)。本付録は PY-120 の実測のみ。

既知類型との関係: 該当なし (PE の読取りのみ。lift・IR の変換は行っていない。`docs/DEFECTS.md`・`tools/icall/REPORT.md` の類型とは照合していない)

## 結論

- 12 件のうち **1 件 (`launchMapPages.length`) だけ** を PE の根拠で確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/launchmap_diff.mjs` 3 呼出し)。
- `length` の戻り値は「`obj.+0x50` の配列の件数」を int で返す (VA 0xd791b0)。件数そのものは実行時の状態で、PE からは決まらない。mock・C の初期値 0 は**仮置き**。
- `provider_check` の「実装」に数える 1 件 (`launchMapPages.length`) は、PE の例外経路 (`obj.+0x50 == 0` で code -7) を持たない**仮置きの値** (mock・C とも常に 0 を返す)。確定したのは呼出し経路と戻り型までで、値そのものは確定していない。
- 残り **11 件は未確定**。読んだ範囲・確定に必要な情報・未確定の理由を下の表 (§保留) に書き、子 issue 3 件に分けた (#3027・#3029・#3030)。
- issue の範囲を縮めた (受入条件のうち 1 件分を完了単位とし、残りは子へ移した。`Closes #2984`)。
- 再測定 (測定 commit `71005b39`・§再測定 (4)): 差分の鮮度の指摘に従い、未実行だった項目 (64 bit の static_subinterp・pthread の static_mt・fulltext_parity・負のコントロール) を HEAD で実行した。FAIL は 1 件のみ (`static_subinterp_browser` の flpy_static64 で反復時に wasm メモリが増える。既知の #2918・本 PR の前から同値)。wasm32 の静的版は 12/12 PASS。

## 手段

- PyMethodDef の所在: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_launchmap_entries.py [--disasm]`。entry VA を 0x151e058〜0x151e1b8 で切る (`init`・`length` は他モジュールの PyMethodDef と名前が重なるため。`length` は範囲外に 3 箇所、`init` は範囲外に 1 箇所ある)。
- 逆アセンブル: 同スクリプトの `--disasm` (capstone 5.0.7・pefile 2024.8.26)。`ret` まで。呼出し先の IAT 名は解決していない (RIP 相対の絶対アドレスを注記)。
- 公開 stub の戻り型・kwsig: `analysis/flapi/flapi_table.json` (`launchMapPages`)。
- 解析対象の展開: `fl-win64` の `block00031_PE.bin` (PE 本体)、`block24429_DATA.bin`・`block24430_DATA.bin`・`block25159_DATA.bin`・`block24618*` (fetch_inputs 用)。

## 12 件の PyMethodDef (範囲 0x151e058〜0x151e1b8)

`pe_launchmap_entries.py` の出力そのまま。flags は PyMethodDef の値、flapi_flags は `flapi_table.json` の `kwsig.flags` (4 = METH_NOARGS、1 = METH_VARARGS)。

| 関数 | entry | fn | flags | flapi_flags | 照合 | docstring |
|---|---|---|---|---|---|---|
| init | 0x151e058 | 0xd79020 | 1 | 1 | OK | Init launchmap pages |
| length | 0x151e078 | 0xd791b0 | 4 | 4 | OK | Get launchmap pages length |
| updateMap | 0x151e098 | 0xd79290 | 1 | 1 | OK | Update launchmap page |
| getMapItemColor | 0x151e0b8 | 0xd793d0 | 1 | 1 | OK | Get launchmap item color |
| getMapCount | 0x151e0d8 | 0xd79560 | 1 | 1 | OK | Get launchmap items length |
| getMapItemChannel | 0x151e0f8 | 0xd796b0 | 1 | 1 | OK | Get launchmap item destination channel |
| getMapItemAftertouch | 0x151e118 | 0xd79810 | 1 | 1 | OK | Get launchmap item aftertouch |
| processMapItem | 0x151e138 | 0xd79bc0 | 1 | 1 | OK | Process map item |
| releaseMapItem | 0x151e158 | 0xd79d10 | 1 | 1 | OK | Release map item |
| checkMapForHiddenItem | 0x151e178 | 0xd79fe0 | 4 | 4 | OK | Check for launchpad hidden item |
| createOverlayMap | 0x151e198 | 0xd7a130 | 1 | 1 | OK | Create overlay map |
| setMapItemTarget | 0x151e1b8 | 0xd7a3a0 | 1 | 1 | OK | Set map item destination target |

12 件とも flags は flapi の kwsig と一致し、docstring は flapi の doc と一致する。PyArg 書式を読んだ 4 件 (init `sii`・updateMap `i`・getMapItemColor `ii`・getMapCount `i`) は flapi の kwsig.fmt と一致する。

## PE 根拠の確定: `launchMapPages.length` (VA 0xd791b0, NOARGS, 戻り int・戻り値の意味は推定)

逆アセンブル (`--disasm` の出力):

```
0xd791b0 sub rsp,0x28
0xd791b4 call 0xd7a6d0              ; self → 状態の取得器 (0xd7a6d0 は [0x15e05b8] を呼ぶだけ)
0xd791b9 mov rax,[rax]              ; obj
0xd791bc mov rax,[rax+0x50]         ; 管理オブジェクト (page 群)
0xd791c0 test rax,rax / je 0xd791e2 ; 0 なら code -7 → 0xd82c20 (下の「未確定」)
0xd791c5 mov rax,[rax+0x3c0]        ; 配列
0xd791cc test rax,rax / je 0xd791d5 ; 配列が無ければ件数 0
0xd791d1 mov rax,[rax-8]            ; 件数 (8 バイトのヘッダ)
0xd791d5 mov ecx,eax
0xd791d7 mov rax,[0x15e4280] / call [rax]   ; 変換スロット → Python int
0xd791f0 ret
```

- 変換スロット `[0x15e4280]` は `REPORT_PY87.md` の general 4 件と同じ slot。stub の戻り型 int と一致する。
- 戻り値は配列の件数 (32 bit に切った値)。件数 0 は配列が無い場合。

### 確定できていない点

1. **件数ヘッダ `[arr-8]` の意味**: 件数か容量か。生成側の書き込みを読んでいないため、「件数」は使い方からの推定 (docstring の "length" と戻り型 int からの推定)。
2. **`obj.+0x50 == 0` の経路**: `0xd82c20` に code -7 を渡す。`0xd82c20` の code → 例外の表は下に示した (VA 0xd82c20)。ただし負の code の経路は、先頭で実行時の述語 (`[0x15e4790]→[+8]→vt[+0x88]`) を呼び、偽のときは `0xd82dd0` へ抜ける (未読)。述語は実行時のオブジェクトの vtable なので、静的に同定できない。よって未初期化時に例外になるかは未確定。
3. **件数の実行時の初期値**: 0 は仮置き (mock `st.launchPages`・C `lm_pages`)。

### 参考: `0xd82c20` の code → 戻り (本 run で読んだ範囲)

| code | 文言 (VA の文字列) | 備考 |
|---|---|---|
| -1 | Unspecified error | `cmp`・`sub` の分岐で確認 |
| -2 | Operation unsafe at current time | |
| -3 | Range error | |
| -4 | Index out of range | flapi code 4 と一致 |
| -5 | Wrong number of function parameters or wrong parameter type | flapi code 5 と一致 |
| -6 | Linked device not assigned | |
| -7 | Device not assigned | `length` の `obj.+0x50 == 0` 経路 |
| -8 | Plugin not valid | |
| その他 | Unknown error | |

負の code は「内部 code = -(flapi code)」の対応が 4・5 で成り立つ。code 0 と正の code の経路は一部のみ読んだ (`0xc38bc0` の呼出し先は未読)。

## 保留: 残り 11 件 (未確定・理由付き)

| 関数 | fn | 本 run で読んだ範囲 | 確定に必要な情報 | 未確定の理由 |
|---|---|---|---|---|
| init | 0xd79020 | PyArg 書式 `sii` (0xd791a4)、`0xd7a6d0` 経由で状態、`call 0x41c6e0`・`call 0xd7a6d0` | 引数 deviceName・width・height の使い方と、obj の生成/初期化 | 初期化本体 (0x41c6e0 以降) 未読 |
| updateMap | 0xd79290 | 書式 `i`、`call 0xd843d0` (out・0xd79f80 のコールバック付き) | index の意味、0xd843d0 の意味 | 0xd843d0 と 0xd79f80 未読 |
| getMapItemColor | 0xd793d0 | 書式 `ii` (0xd79550)、`[obj.+0x50]+0x3c0` の 32 バイト要素を `call 0x416750` に渡す。index<0 は `+0x3d4` の固定記録 | 0x416750 の型記述子 (r8) の解釈 | 0x416750 は tag 0x16 等を見る汎用のマーシャリング処理で、本 run では読み切れず |
| getMapCount | 0xd79560 | 書式 `i` (0xd79595)、getMapItemColor と同じ形 (0x416750) | 同上 | 同上 |
| getMapItemChannel | 0xd796b0 | 未読 | 同上 (推定のみ。確認していない) | 未読 |
| getMapItemAftertouch | 0xd79810 | 未読 | 同上 (推定のみ。確認していない) | 未読 |
| processMapItem | 0xd79bc0 | 未読 (引数 eventData (FlMidiMsg)・index・itemIndex・velocity) | FlMidiMsg の読み方、副作用 | 未読 |
| releaseMapItem | 0xd79d10 | 未読 (引数 eventData・index) | 同上 | 未読 |
| checkMapForHiddenItem | 0xd79fe0 | NOARGS。`call 0xd843d0` (0xd79f80 のコールバック付き) の結果 (`[rbp+0x78]`) を `call 0xd82c20` で返す | 0xd843d0・0xd79f80 の意味 | 0xd843d0 と 0xd79f80 未読 |
| createOverlayMap | 0xd7a130 | 未読 (引数 offColor・onColor・width・height) | 描画の意味、副作用 | 未読 |
| setMapItemTarget | 0xd7a3a0 | 未読 (引数 index・itemIndex・target、戻り int) | 戻り値の意味 | 未読 |

子 issue の分け方: 索引付き読出し 4 件 (getMapCount・getMapItemColor・getMapItemChannel・getMapItemAftertouch) は #3027 (PY-156)。init・状態変更 4 件と `length` の未確定 2 点は #3029 (PY-138)。イベント処理 3 件 (processMapItem・releaseMapItem・checkMapForHiddenItem) は #3030 (PY-139)。`0xd843d0` は #3029・#3030 と #3001 (PY-125) に共通して現れる (同一関数かは未確認)。

## 実装

- `host/fl_mock.mjs`: `st.launchPages = 0` (仮置き) と `"launchMapPages.length"` (引数 0 個のみ・件数を返す)。
- `provider/fl_engine.c`: `static int lm_pages` (`fl_engine_reset` で 0)、`FL_H(launchMapPages, length) { NARGS(0, 0); return fl_ret_i(c, lm_pages); }`。
- `tests/provider_check.mjs`: `pe120` 集合を追加し、実装数 83→84・未実装数 352→351。
- `tests/launchmap_diff.mjs` (新規): `general_diff.mjs` と同形式。呼出し 3 件 (`length()` と引数個数違い 2 件)。
- `analysis/flapi/pe_launchmap_entries.py` (新規): 12 件の PyMethodDef の抽出と flags 照合・`--disasm`。

## 検証

### 履歴 (初回〜merge `a2a56bf8` の測定)

`REPORT_APPENDIX_2984.md` に分割移動 (内容は削除していない)。

### 履歴: 再取り込み後の再測定 (2) (merge `a0b6f97f`・main `f81c46bb`。当時の HEAD の結果)

main (`f81c46bb`) を取り込んだ merge `a0b6f97f` の競合は 3 ファイル 7 箇所。`host/fl_mock.mjs`・`provider/fl_engine.c` は、main の PY-96 (選択範囲 4 件) と PY-121 (#2982・表示・メニュー 6 件) の追加と、本件の `launchPages`・`lm_pages`・`launchMapPages.length` を両側残しで解消した。`tests/provider_check.mjs` は集合定義と条件式に main の `pe96`・`pe121_2982` と本件の `pe120` を並べ、期待値を実装 120 / 未実装 315 にした (main の 119 / 316 に本件の 1 件を加えた値)。rebase・force push はしていない。

測定 commit: `a0b6f97f` (コードを変えた最後の commit。merge)。環境: runner (4 core)。素材は `fl-win64` から DATA block 4 件と PE 本体 (`block00031_PE.bin`) を、`toolchain-emsdk` を展開した emsdk ([EMSDK] 6.0.12) で使った。vite は本体 checkout の `node_modules` を symlink して解決した (コミットしない)。CPython wasm (32 bit・64 bit・pthread) は HEAD で再ビルドした (流用なし)。

| コマンド | 結果 | wall (s) |
|---|---|---|
| `fetch_inputs.sh` / `provider/build.sh` | rc 0 (fl_table.c: 435 関数・ハンドラ 120) | 1 / 13 |
| `build_cpython_wasm.sh` / `CPY_PTHREADS=1 build_cpython_wasm.sh` / `build_cpython_wasm64.sh` | 全て rc 0 | 230 / 124 / 173 |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` / `build_flpy_static.sh` / `CPY_PTHREADS=1 … build_flpy_static.sh` / `FLPY_MEMORY64=1 … build_flpy_static.sh` | 全て rc 0 | 10 / 6 / 18 / 7 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 120 / 未実装 315 / MCP 静的 60) | 0 |
| `launchmap_diff` / `general_diff` / `ui_state_diff` / `screen_diff` / `arrangement_diff` / `arrangement_selection_diff` | 全て diffs 0、PASS (calls 3 / 25 / 12 / 32 / 25 / 8) | 0 |
| `ui_display_diff` | PASS (ok 12・bad 11・diffs 0) | 0 |
| `channels` / `device` / `ilmcp` / `midi_path` / `mixer` / `transport` / `ui` の `*_diff.mjs` | 全て diffs 0、PASS (calls 161 / 8 / 32 / 30 cases / 59 / 7 / 17) | 0 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 2 |
| `browser_check` / `static_check` | BROWSER OK (tools 48) / STATIC CHECK OK (1 回) | 10 / 0 |
| `static_browser_check` | STATIC BROWSER OK (sab_host_calls 37,425・static_in_worker true) | 3 |
| `STATIC_WASM=flpy_static STATIC_MEM64=0 static_subinterp_browser` | STATIC SUBINTERP OK (12/12 PASS) | 22 |
| `static_subinterp_browser` (flpy_static64・MEMORY64=1) | **FAIL (12 check 中 11 PASS)**。付録の merge `a2a56bf8` 節と同じ失敗 (150 回の作成/実行/破棄で wasm メモリが増える: 33,554,432 → 48,365,568 B、+14,811,136 B)。#2918 (既知) | 27 |
| `STATIC_WASM=flpy_static_pthread static_mt_check` | STATIC MT CHECK OK (runs 50・threads_2_tools 48・threads_4_tools 2・thread_mismatch 0) | 1 |
| `mcp_ui_check` / `midi_ui_check` | MCP UI OK (tools/list = 48) / MIDI UI OK | 3 / 2 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12/12 OK | 0 |

- 負のコントロール (`launchPages` を 1 にすると `launchmap_diff` が FAIL する確認) は今回は再実行していない。付録の merge `a2a56bf8` 節の結果を引き継ぐ。mock の `launchPages` の既定値は 0 のまま。
- コード差分 (測定 commit `a0b6f97f` から HEAD まで、テスト・mock・C・解析に効く範囲): 下の出力を HEAD で取った。

```
$ git diff a0b6f97f HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```

### 再取り込み後の再測定 (3) (merge `71005b39`・main `150a83fa`・HEAD で測り直し)

main の取り込みは 2 回。`1b37410c` を取り込んだ merge `38927307` (競合 2 ファイル 2 箇所) を push した後、main が `150a83fa` へ進んだため、`150a83fa` を取り込んだ merge `71005b39` (競合 1 ファイル 1 箇所) を作った。解消は両側残し:
- `host/fl_mock.mjs` (`38927307`): 本件の `launchMapPages.length` と main の PY-125 (`general.clearLog`・`general.dumpScoreLog`) を両方残した。
- `tests/provider_check.mjs` (`38927307`・`71005b39`): 判定集合に `pe120`・`pe125` と main の PY-102 (`pe102`・`playlist.muteTrackLock`) を全て入れた。期待値は main `150a83fa` の 122/313 に本件の 1 件を加えた 123/312。
- `provider/fl_engine.c` は自動マージ。`launchMapPages.length`・`general.clearLog`・`playlist.muteTrackLock` の登録が C と mock に各 1 回ずつ残ることを grep で確認した。

測定 commit: `71005b39` (コードを変えた最後の commit。merge)。環境: runner (4 core・load average 約 1)。素材: `fl-win64` から DATA block 4 件と PE 本体 (`block00031_PE.bin`) を展開。emsdk は [EMSDK] (6.0.12・runner 同梱。`toolchain-emsdk` の tarball は展開していない)。ブラウザ系は本体 checkout の `node_modules` を symlink して実行した (commit しない)。CPython wasm (32 bit) は `38927307` の測定で再ビルド (rc 0・255 s) したものを流用した。`71005b39` までの main 差分に `tools/python` の build スクリプト・CPython 取得の変更は無い (`git diff --stat 992d430b 71005b39 -- tools/python` の一覧に `.sh` は無い)。

| コマンド | 結果 | wall (s) |
|---|---|---|
| `fetch_inputs.sh` / `build_cpython_wasm.sh` (32 bit) | `38927307` で rc 0 / rc 0 (`71005b39` では流用) | 1 / 255 |
| `provider/build.sh` / `build_flpy.sh` / `build_flpy_static.sh` | 全て rc 0 (`fl_table.c`: 435 関数・ハンドラ 123) | 1 / 7 / 7 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 123 / 未実装 312 / MCP 静的 60) | 0 |
| `launchmap` / `general` / `ui_state` / `screen` / `arrangement` / `arrangement_selection` / `ui_display` / `channels` / `device` / `ilmcp` / `midi_path` / `mixer` / `transport` / `ui` / `playlist` の `*_diff.mjs` | 全て diffs 0、PASS (calls 3 / 32 / 12 / 32 / 25 / 8 / ok 12・bad 11 / 161 / 8 / 32 / 30 cases / 59 / 7 / 17 / 23) | 0〜1 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 2 |
| `python3 analysis/flapi/pe_launchmap_entries.py` / `static_check.mjs` | 12/12 OK / STATIC CHECK OK | 0 / 0 |
| `browser_check` / `static_browser_check` / `mcp_ui_check` / `midi_ui_check` | BROWSER OK (tools 48) / STATIC BROWSER OK (sab_host_calls 37,425) / MCP UI OK (tools/list = 48) / MIDI UI OK | 1 / 4 / 2 / 2 |
| `STATIC_WASM=flpy_static STATIC_MEM64=0 static_subinterp_browser` | STATIC SUBINTERP OK (12/12 PASS) | 24 |

- 今回は未実行: `static_subinterp_browser` (flpy_static64・MEMORY64=1)・`static_mt_check`・負のコントロール (`launchPages` を 1 にして `launchmap_diff` が FAIL する確認)。いずれも CPython の再ビルド (64 bit・pthread) か再実行が要る。前回の結果は本測定の根拠にしない。
- コード差分 (測定 commit `71005b39` から HEAD まで、テスト・mock・C・解析に効く範囲): 下の出力を HEAD で取った (REPORT のみの commit が HEAD)。

```
$ git diff 71005b39 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```

### 再測定 (4) (測定 commit `71005b39`・HEAD `4f855fde` で実行)

測定 commit は `71005b39` (コードを変えた最後の commit)。`4f855fde` は REPORT のみの commit。(3) の表にあった未実行の項目を、HEAD のコードで実行した。素材は `fl-win64` から `block00031_PE.bin` と DATA block 4 件を `$RUNNER_TEMP` の `fl-win64-3039` へ展開した (`tar --zstd -xf --wildcards`)。emsdk は [EMSDK] (runner 同梱・6.0.12)。`toolchain-emsdk` は展開していない (不使用)。`mcp_ui_check`・`midi_ui_check` は本体 checkout の `node_modules` を symlink して実行した (commit していない)。CPython wasm は 32 bit・pthread・64 bit の 3 種を HEAD で再ビルドした (流用なし)。

| コマンド | 結果 | wall (s) |
|---|---|---|
| `fetch_inputs.sh` / `provider/build.sh` | rc 0 / rc 0 (fl_table.c: 435 関数・ハンドラ 123) | 2 (合計) |
| `build_cpython_wasm.sh` (32 bit・native 込み) / `CPY_PTHREADS=1 build_cpython_wasm.sh` / `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> build_cpython_wasm64.sh` | 全て rc 0 | 254 / 146 / 192 |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` / `build_flpy_static.sh` / `CPY_PTHREADS=1 … build_flpy_static.sh` / `FLPY_MEMORY64=1 CPY_BUILD=… STATIC_OUT=flpy_static64 … build_flpy_static.sh` | 全て rc 0 | 27 (4 本の合計) |
| `node tests/provider_check.mjs` | PASS (435 / 実装 123 / 未実装 312 / MCP 静的 60) | 6 (下の 5 行の合計) |
| `launchmap_diff` / `general_diff` / `ui_state_diff` / `screen_diff` | 全て diffs 0、PASS (calls 3 / 32 / 12 / 32) | 同上 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 同上 |
| `static_check.mjs` | STATIC CHECK OK | 同上 |
| `STATIC_WASM=flpy_static_pthread static_mt_check.mjs` | STATIC MT CHECK OK (runs 50・threads_2_tools 48・threads_4_tools 2・thread_mismatch 0) | 1 |
| `tests/fulltext_parity.mjs` | FULLTEXT PARITY OK (mock/wasm・mock/static・wasm/static の 48 tool 全文 text_diff 0)。ネガコン: 300 字目 (160 字より後ろ) の 1 字変更を全文比較が検出 (1)、先頭 160 字のゲートは検出せず (false) | 8 |
| `STATIC_WASM=flpy_static64 STATIC_MEM64=1 static_subinterp_browser.mjs` | **FAIL** (checks 12 中 failed 1: 150 回の作成/実行/破棄で wasm メモリが増える。mem_before 33,554,432 → mem_after 48,365,568 B)。既知 #2918 と同じ失敗 | 下の 3 行の合計 77 |
| `STATIC_WASM=flpy_static STATIC_MEM64=0 static_subinterp_browser.mjs` | STATIC SUBINTERP OK (12/12 PASS) | 同上 |
| `static_browser_check.mjs` | STATIC BROWSER OK (sab_host_calls 37,425・static_in_worker true・diff_tools 0) | 同上 |
| `browser_check.mjs` | BROWSER OK (tools 48) | 1 |
| `mcp_ui_check.mjs` / `midi_ui_check.mjs` | MCP UI OK (tools/list = 48) / MIDI UI OK | 2 / 3 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12/12 OK | 0 |
| 負のコントロール: `host/fl_mock.mjs` の `launchPages` を 1 にして `launchmap_diff.mjs` | rc 1・`launchMapPages 差分 1 件` (mock ok 1 / wasm ok 0) で検出。確認後に 0 へ戻し、再実行で PASS (calls 3・diffs 0) | 0 |

- コード差分 (測定 commit `71005b39` から HEAD まで): 上の結果はコードが 71005b39 と同じ作業ツリーで得たもの。下の出力を最終 HEAD で取った (REPORT の変更のみ)。

```
$ git diff 71005b39 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 11 件の PE 確定 (索引付き読出し 4・状態変更 4・イベント処理 3) | `launchMapPages` の 11/12 が未実装 (provider の未実装扱い) | #3027 (PY-156)・#3029 (PY-138)・#3030 (PY-139) |
| `length` の件数ヘッダ `[arr-8]` の意味 (件数か容量か)・未初期化経路 (code -7 の例外化の述語)・実行時初期値 (mock・C の 0 は仮置き。provider_check の実装 1 件はこの仮置き値) | 件数の意味は推定。未初期化時の挙動は未モデル。mock・C の値が実機と違う可能性 | #3029 (PY-138) |
| `0xd843d0` の同一性 (本件と #3001 PY-125 の dispatch) | 下位関数の二重確定の可能性 | #3029・#3030 (未確認) |
| `static_subinterp_browser` (flpy_static64・MEMORY64=1) の FAIL 1 件 (150 回の反復で wasm メモリが +14.8 MB 増える) | 長時間の反復で wasm メモリが増える。本 PR の前から同値 (`REPORT_PY109.md`) | #2918 (既存・PY-108) |
| `static_check` の単発 FAIL (過去測定 (付録) の 12 回中 1 回・FAIL 行は未採取)。今回の 1 回は OK | 原因未特定。再発時に比べられる一次情報が無い | 親 #2984 への提案 (既存の該当 issue は無い。再発時に FAIL 行を採取して #2984 にコメントする。新規子は作らない) |
