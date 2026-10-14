# tools/python REPORT: PY-120 launchMapPages 12 件の PE 確定 — `launchMapPages.length` 1 件のみ確定 (#2984・題名 [PY-153]・親 #2832)

> 正本: `tools/python/REPORT_PY87.md` (PE 確定の手順・4 件の確定)。本付録は PY-120 の実測のみ。

既知類型との関係: 該当なし (PE の読取りのみ。lift・IR の変換は行っていない。`docs/DEFECTS.md`・`tools/icall/REPORT.md` の類型とは照合していない)

## 結論

- 12 件のうち **1 件 (`launchMapPages.length`) だけ** を PE の根拠で確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/launchmap_diff.mjs` 3 呼出し)。
- `length` の戻り値は「`obj.+0x50` の配列の件数」を int で返す (VA 0xd791b0)。件数そのものは実行時の状態で、PE からは決まらない。mock・C の初期値 0 は**仮置き**。
- `provider_check` の「実装」に数える 1 件 (`launchMapPages.length`) は、PE の例外経路 (`obj.+0x50 == 0` で code -7) を持たない**仮置きの値** (mock・C とも常に 0 を返す)。確定したのは呼出し経路と戻り型までで、値そのものは確定していない。
- 残り **11 件は未確定**。読んだ範囲・確定に必要な情報・未確定の理由を下の表 (§保留) に書き、子 issue 3 件に分けた (#3027・#3029・#3030)。
- issue の範囲を縮めた (受入条件のうち 1 件分を完了単位とし、残りは子へ移した。`Closes #2984`)。
- 再測定 (HEAD `a0b6f97f`・§再取り込み後の再測定 (2)): 全 e2e を HEAD で実行した。FAIL は 1 件のみ (`static_subinterp_browser` の flpy_static64 で反復時に wasm メモリが増える。既知の #2918・本 PR の前から同値)。wasm32 の静的版は 12/12 PASS。

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

### 履歴: 初回測定 (測定 commit `eba7e821`・main 取り込み前。当時の HEAD の結果)

測定 commit: `eba7e821` (当時のコードを変えた最後の commit。`feat(flapi): confirm launchMapPages.length from PE 0xd791b0 (PY-120, #2984)`)。ベース `eec639a3` (main 取り込み済み)。

環境: runner (4 core)。開始時の load average 0.51 (`uptime`)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。前提の生成物 (gitignore・work/ と dist/): `fetch_inputs.sh` rc 0 (初回は DATA block が無く rc 1。`block24429`・`block24430`・`block25159`・`block24618*` を展開して再実行し rc 0)、`build_cpython_wasm.sh` rc 0 (初回 chain 全体 4 分 14 秒、cpython 込み)、`FLPY_SKIP_TABLE=1 build_flpy.sh` rc 0、`provider/build.sh` rc 0。

| コマンド | 結果 | wall |
|---|---|---|
| `node tests/provider_check.mjs` | PASS (435 / 実装 84 / 未実装 351 / MCP 静的 60) | 0.37 秒 |
| `node tests/launchmap_diff.mjs` | calls 3、diffs 0、PASS | 0.05 秒 |
| `node tests/general_diff.mjs` (回帰) | calls 9、diffs 0、PASS | 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 2.11 秒 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12 件、全て OK (flags 照合) | — |

- ベース (変更前、同じ環境): `provider_check` は実装 83 / 未実装 352 で PASS、`all_tools` 48/48、`general_diff` PASS。
- ネガティブコントロール: `host/fl_mock.mjs` の `launchPages` を 0 から 1 にすると、`node tests/launchmap_diff.mjs` は `AssertionError [ERR_ASSERTION]: launchMapPages 差分 1 件` で rc 1 (FAIL)。0 に戻すと PASS (rc 0)。
- 当時 (HEAD `eba7e821`) のコード差分 (テスト・mock・C に効く範囲): 空 (0 行)。現 HEAD では空ではない (後続の main 取り込みによる差分。§再取り込み後の再測定 を参照)。

  この REPORT と解析スクリプト (`analysis/flapi/pe_launchmap_entries.py`) は測定 commit の後に加えた。どちらもテスト・provider のビルドに入らない。

### 履歴: main 取り込み後の再測定 (merge `53835669`・main `00ca9f1b`。当時の HEAD の結果)

main (`00ca9f1b`) を取り込んだ merge `53835669` で、競合は 2 件だった。(1) `tests/provider_check.mjs` の集合定義と条件式: main の `pe119` (ui ゲッター 6 件) と本件の `pe120` の両方を残した。(2) `docs/DOC_MAP.md` の表末尾: main の `REPORT_PY119.md` 行と本件の `REPORT_PY120_2984.md` 行の両方を残した。期待値は実装 93 / 未実装 342 (main の 92 / 343 に本件の 1 件を加えた値)。

測定 commit: `53835669` (当時のコードを変えた最後の commit)。環境: runner (load average 0.4〜3.0)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` は fl-win64 から DATA block 4 件 (block24429・block24430・block25159・block24618) だけを展開した先。emsdk は `[EMSDK]` (docs/REFERENCES.md)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 (fl_table.c: 435 関数・ハンドラ 93) | 1.5 秒 |
| `bash build_cpython_wasm.sh` | rc 0 (前提。CPython 3.12.1 wasm) | 249 秒 |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` | rc 0 | 6 秒 |
| `FLPY_SKIP_TABLE=1 build_flpy_static.sh` | rc 0 | 6 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 93 / 未実装 342 / MCP 静的 60) | 0.36 秒 |
| `node tests/launchmap_diff.mjs` | calls 3、diffs 0、PASS | 0.05 秒 |
| `node tests/general_diff.mjs` (回帰) | calls 9、diffs 0、PASS | 0.05 秒 |
| `node tests/ui_state_diff.mjs` (回帰・pe119) | calls 12、diffs 0、PASS | 0.05 秒 |
| `channels` / `device` / `ilmcp` / `midi_path` / `mixer` / `transport` / `ui` の `*_diff.mjs` | 全て diffs 0、PASS (calls 161 / 8 / 32 / 30 cases / 59 / 7 / 17) | 各 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback_roundtrip true | 2.1 秒 |
| `node tests/browser_check.mjs` | BROWSER OK (tools 48) | 8.9 秒 |
| `node tests/mcp_ui_check.mjs` / `node tests/midi_ui_check.mjs` | MCP UI OK / MIDI UI OK | 2.2 秒 / 2.8 秒 |
| `node tests/static_check.mjs` | STATIC CHECK OK | 0.4 秒 |
| `node tests/static_browser_check.mjs` | STATIC BROWSER OK (sab_host_calls 37,425・static_host_calls 37,425・static_in_worker true) | 4.5 秒 |
| `node tests/static_mt_check.mjs` | **未再測定**。pthread 版 (`CPY_PTHREADS=1` の CPython wasm) の再ビルドが要り、この run の時間枠に入らなかった。`236a8106` 時点の結果は本 HEAD の値ではない | — |
| `python3 analysis/flapi/pe_launchmap_entries.py` | **未再実行**。`block00031_PE.bin` (PE 本体) を展開していない。`tools/python/analysis/flapi` は main 取り込みで変わっていない (下の diff) | — |

- 前提の順序: `provider_check` は `dist/flpy.js` (CPython wasm) と `work/midi.py` 等 (`fetch_inputs.sh`) を要するため、上の build を先に行った。
- 当時 (HEAD `53835669`) のコード差分: 空 (0 行)。現 HEAD では空ではない (後続の取り込みによる差分)。

- 測定 commit 以前の main 側差分 (参考): `git diff --stat 236a8106 53835669 -- tools/python/analysis/flapi` は空。`tools/python/host`・`provider`・`tests` は取り込みで 8 files 変わった (main の `pe119`・`ui_state_diff` と、競合解消の `provider_check.mjs` を含む)。

### 再取り込み後の再測定 (merge `a2a56bf8`・main `5191cf9f`・HEAD `0549e22b` で測り直し)

測定 commit: `a2a56bf8` (コードを変えた最後の commit。merge)。測定時の HEAD: `0549e22b` (差し戻し対応の測定。以後の commit は本 REPORT と PR 本文のみ)。環境: runner (4 core)。`FL_WIN64_DIR` は fl-win64 から DATA block 4 件と PE 本体 (`block00031_PE.bin`) だけを展開した先。emsdk は [EMSDK] (6.0.12)。vite は本体 checkout の `node_modules` を symlink して解決した (コミットしない)。

CPython wasm は HEAD で再ビルドした (流用なし): `fetch_inputs.sh` → `build_cpython_wasm.sh` (rc 0)、`build_cpython_wasm64.sh` (rc 0。`EMSDK_ENV` に [EMSDK] の `emsdk_env.sh` を指定する。未指定では rc 1)、`CPY_PTHREADS=1 build_cpython_wasm.sh` (rc 0)。

| コマンド | 結果 | wall (s) |
|---|---|---|
| `provider/build.sh` / `FLPY_SKIP_TABLE=1 build_flpy.sh` / `FLPY_SKIP_TABLE=1 build_flpy_static.sh` | 全て rc 0 (fl_table.c: 435 関数・ハンドラ 110) | — |
| `FLPY_MEMORY64=1 CPY_BUILD=… STATIC_OUT=flpy_static64 FLPY_SKIP_TABLE=1 build_flpy_static.sh` / `CPY_PTHREADS=1 FLPY_SKIP_TABLE=1 build_flpy_static.sh` | 全て rc 0 (flpy_static64・flpy_static_pthread) | — |
| `node tests/provider_check.mjs` | PASS (435 / 実装 110 / 未実装 325 / MCP 静的 60) | 0 |
| `node tests/launchmap_diff.mjs` | calls 3、diffs 0、PASS | 0 |
| `node tests/general_diff.mjs` (回帰) | calls 25、diffs 0、PASS | 0 |
| `node tests/ui_state_diff.mjs` / `screen_diff.mjs` / `arrangement_diff.mjs` (main 由来) | calls 12 / 32 / 25、diffs 0、PASS | 0 |
| `channels` / `device` / `ilmcp` / `midi_path` / `mixer` / `transport` / `ui` の `*_diff.mjs` | 全て diffs 0、PASS (calls 161 / 8 (rejects 4・midi_out 5) / 32 (state_checks 9) / 30 cases / 59 / 7 / 17) | 0〜1 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 1 |
| `node tests/browser_check.mjs` | BROWSER OK (tools 48) | 1 |
| `node tests/static_check.mjs` | STATIC CHECK OK。ただし 12 回実行のうち 1 回目 (ループ内) だけ rc 1 (`STATIC CHECK FAIL (1)`)。FAIL 行は採取していない。残り 11 回は全て OK | 1 |
| `node tests/static_browser_check.mjs` | STATIC BROWSER OK (sab_host_calls 37,425・static_host_calls 37,425・static_in_worker true) | 2 |
| `node tests/static_subinterp_browser.mjs` (既定 flpy_static64・MEMORY64=1) | **FAIL (12 check 中 11 PASS)**。失敗は「150 回 (50×3) の作成/実行/破棄で wasm メモリが増えない」: 33,554,432 → 48,365,568 B (+14,811,136 B)。`REPORT_PY109.md` の記録と同値。既知 (#2918) | 20 |
| `STATIC_WASM=flpy_static STATIC_MEM64=0 node tests/static_subinterp_browser.mjs` (wasm32 静的版) | STATIC SUBINTERP OK (12/12 PASS) | 17 |
| `STATIC_WASM=flpy_static_pthread node tests/static_mt_check.mjs` | STATIC MT CHECK OK (runs 50、threads_2_tools 48、threads_4_tools 2、thread_mismatch 0) | 1 |
| `node tests/mcp_ui_check.mjs` | MCP UI OK (tools/list = 48) | 2 |
| `node tests/midi_ui_check.mjs` | MIDI UI OK | 2 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12/12 OK (PE 本体を展開して再実行) | 0 |

- static_mt の host_calls (37,424) と all_tools・static_browser_check (37,425) の 1 差は計数元の違い。原因は未調査 (各 check の判定条件どおりで FAIL ではない)。
- 負のコントロール: 前節の結果を引き継ぐ。`fl_mock.mjs` の `launchPages` の既定値は 0 のまま。
- コード差分 (測定 commit `a2a56bf8` から HEAD まで、テスト・mock・C・解析に効く範囲): 下の出力を HEAD で取った。

```
$ git diff a2a56bf8 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```

### 再取り込み後の再測定 (2) (merge `a0b6f97f`・main `f81c46bb`・HEAD で測り直し)

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
| `static_subinterp_browser` (flpy_static64・MEMORY64=1) | **FAIL (12 check 中 11 PASS)**。前節と同じ失敗 (150 回の作成/実行/破棄で wasm メモリが増える: 33,554,432 → 48,365,568 B、+14,811,136 B)。#2918 (既知) | 27 |
| `STATIC_WASM=flpy_static_pthread static_mt_check` | STATIC MT CHECK OK (runs 50・threads_2_tools 48・threads_4_tools 2・thread_mismatch 0) | 1 |
| `mcp_ui_check` / `midi_ui_check` | MCP UI OK (tools/list = 48) / MIDI UI OK | 3 / 2 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12/12 OK | 0 |

- 負のコントロール (`launchPages` を 1 にすると `launchmap_diff` が FAIL する確認) は今回は再実行していない。前節の結果を引き継ぐ。mock の `launchPages` の既定値は 0 のまま。
- コード差分 (測定 commit `a0b6f97f` から HEAD まで、テスト・mock・C・解析に効く範囲): 下の出力を HEAD で取った。

```
$ git diff a0b6f97f HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 11 件の PE 確定 (索引付き読出し 4・状態変更 4・イベント処理 3) | `launchMapPages` の 11/12 が未実装 (provider の未実装扱い) | #3027 (PY-156)・#3029 (PY-138)・#3030 (PY-139) |
| `length` の件数ヘッダ `[arr-8]` の意味 (件数か容量か)・未初期化経路 (code -7 の例外化の述語)・実行時初期値 (mock・C の 0 は仮置き。provider_check の実装 1 件はこの仮置き値) | 件数の意味は推定。未初期化時の挙動は未モデル。mock・C の値が実機と違う可能性 | #3029 (PY-138) |
| `0xd843d0` の同一性 (本件と #3001 PY-125 の dispatch) | 下位関数の二重確定の可能性 | #3029・#3030 (未確認) |
| `static_subinterp_browser` (flpy_static64・MEMORY64=1) の FAIL 1 件 (150 回の反復で wasm メモリが +14.8 MB 増える) | 長時間の反復で wasm メモリが増える。本 PR の前から同値 (`REPORT_PY109.md`) | #2918 (既存・PY-108) |
| `static_check` の単発 FAIL (前節の 12 回中 1 回・FAIL 行は未採取)。今回の 1 回は OK | 原因未特定。再発時に比べられる一次情報が無い | 未起票 (単発・未再現。再発時に FAIL 行を採取して起票) |
