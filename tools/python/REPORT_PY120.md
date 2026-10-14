# tools/python REPORT: PY-120 launchMapPages 12 件の PE 確定 — `launchMapPages.length` 1 件のみ確定 (#2984, 親 #2832)

> 正本: `tools/python/REPORT_PY87.md` (PE 確定の手順・4 件の確定)。本付録は PY-120 の実測のみ。

既知類型との関係: 該当なし (PE の読取りのみ。lift・IR の変換は行っていない。`docs/DEFECTS.md`・`tools/icall/REPORT.md` の類型とは照合していない)

## 結論

- 12 件のうち **1 件 (`launchMapPages.length`) だけ** を PE の根拠で確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/launchmap_diff.mjs` 3 呼出し)。
- `length` の戻り値は「`obj.+0x50` の配列の件数」を int で返す (VA 0xd791b0)。件数そのものは実行時の状態で、PE からは決まらない。mock・C の初期値 0 は**仮置き**。
- 残り **11 件は未確定**。読んだ範囲・確定に必要な情報・未確定の理由を下の表 (§保留) に書き、子 issue 3 件に分けた (#3027・#3029・#3030)。
- issue の範囲を縮めた (受入条件のうち 1 件分を完了単位とし、残りは子へ移した。`Closes #2984`)。

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

## 確定: `launchMapPages.length` (VA 0xd791b0, NOARGS, 戻り int)

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

子 issue の分け方: 索引付き読出し 4 件 (getMapCount・getMapItemColor・getMapItemChannel・getMapItemAftertouch) は #3027 (PY-137)。init・状態変更 4 件と `length` の未確定 2 点は #3029 (PY-138)。イベント処理 3 件 (processMapItem・releaseMapItem・checkMapForHiddenItem) は #3030 (PY-139)。`0xd843d0` は #3029・#3030 と #3001 (PY-125) に共通して現れる (同一関数かは未確認)。

## 実装

- `host/fl_mock.mjs`: `st.launchPages = 0` (仮置き) と `"launchMapPages.length"` (引数 0 個のみ・件数を返す)。
- `provider/fl_engine.c`: `static int lm_pages` (`fl_engine_reset` で 0)、`FL_H(launchMapPages, length) { NARGS(0, 0); return fl_ret_i(c, lm_pages); }`。
- `tests/provider_check.mjs`: `pe120` 集合を追加し、実装数 83→84・未実装数 352→351。
- `tests/launchmap_diff.mjs` (新規): `general_diff.mjs` と同形式。呼出し 3 件 (`length()` と引数個数違い 2 件)。
- `analysis/flapi/pe_launchmap_entries.py` (新規): 12 件の PyMethodDef の抽出と flags 照合・`--disasm`。

## 検証

測定 commit: `eba7e821` (コードを変えた最後の commit。`feat(flapi): confirm launchMapPages.length from PE 0xd791b0 (PY-120, #2984)`)。ベース `eec639a3` (main 取り込み済み)。

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
- コード差分 (測定 commit から HEAD まで、テスト・mock・C に効く範囲):

```
$ git diff eba7e821 HEAD -- tools/python/host tools/python/provider tools/python/tests
(空)
```

  この REPORT と解析スクリプト (`analysis/flapi/pe_launchmap_entries.py`) は測定 commit の後に加えた。どちらもテスト・provider のビルドに入らない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 11 件の PE 確定 (索引付き読出し 4・状態変更 4・イベント処理 3) | `launchMapPages` の 11/12 が未実装 (provider の未実装扱い) | #3027 (PY-137)・#3029 (PY-138)・#3030 (PY-139) |
| `length` の件数ヘッダ `[arr-8]` の意味と、未初期化経路 (code -7 の例外化の述語) | 件数の意味は推定。未初期化時の挙動は未モデル | #3029 (PY-138) |
| `length` の件数の実行時初期値 (0 は仮置き) | mock・C の値が実機と違う可能性 | #3029 (PY-138) |
| 0xd843d0 の同一性 (本件と #3001 PY-125 の dispatch) | 共通の下位関数の確定が二重になる可能性 | #3029・#3030 の本文で確認 (未確認) |
