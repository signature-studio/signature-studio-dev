# PY-102 (#2883): playlist.muteTrackLock の value を実装し、flapi 表の引数個数の不一致 (24 件) に根拠を付ける

親: #2027 (PY-62)。残り 23 件の解消は子 #2927 ([PY-110])。muteTrackLock の binary 意味論は `tools/python/REPORT_PY61.md` §3。
既知類型との関係: 該当なし (lift 作業ではない。flapi 表の生成器・provider・mock の実装)。

## 結論

- **muteTrackLock**: 表の個数を binary の書式 `i|i` (required 1・max 2) に合わせ、C handler と mock を実装した。2 引数の呼出しは、従来の code 5 (TypeError) から、戻り値 None の差分 0 になった。
- **不一致**: `sig_arity_check.py` の不一致は 24 → 23 件 (変わった関数は 1 件 = muteTrackLock)。残り 23 件は全件に根拠 (§3) を付けた。どちらが正か (stub か PE か) は関数ごとには確定していない。修正は子 #2927 へ。
- **実害 (実測)**: 23 件のうち C 実装済みの 3 関数は、PE が受け付ける個数の呼出しを code 5 で拒否する (§3-2)。
- issue が参照した `tools/python/tests/playlist_diff.mjs` は repo に存在しなかった (`git ls-files` で 0 件)。本 PR で新規作成した。`tools/python/REPORT_PY62.md` も存在しない (issue の参照先の誤り)。#2027 の記録は REPORT_PY61 §3 と REPORT_PY70 §3 にある。

## 測定

- 測定 commit (コードを変えた最後の commit): `63fbd940` (`test(python): add sig arity probe for wasm dispatch codes (PY-102)`)。
- 表の所要と件数は、直前のコード commit `445dbf9c` (`feat(python): implement playlist.muteTrackLock value arg (PY-102)`) で取得した。`63fbd940` は `tests/sig_arity_probe.mjs` を足しただけで、主要検証を `63fbd940` で再実行し、件数と PASS が同じことを確認した (provider_check 435/78・all_tools 48/48 (mock と wasm)・playlist_diff 23/0・probe の code 5 は 3 件・flapi_table_check fail=0)。
- 差分 0 の証跡: `git diff 63fbd940 HEAD -- tools/python/analysis/flapi tools/python/analysis/flapi_table.py tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。本 REPORT の commit で増えたのは `tools/python/REPORT_PY102.md` と `docs/DOC_MAP.md` だけ。
- 検証起点: origin/main `b2b052ce`。
- 環境: GitHub Actions runner (4 コア)。測定前の `/proc/loadavg` は `0.28 1.14 0.74`、検証の途中は `0.45`〜`0.49` (1 分値)。並列 1 本。
- 素材: `fl-win64` は `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin' '*block24429_DATA.bin' '*block24430_DATA.bin' '*block25159_DATA.bin' '*block24618_DATA.bin'` で展開 (2.86 s)。emsdk は runner に入っている既定値 (`EMSDK_DIR` の既定、emcc 6.0.12) を使った。`toolchain-emsdk` の展開はしていない。
- 素材の利用: `fetch_inputs.sh` で win64 の DATA block から midi.py・utils.py・MCPTools.pyc・device script を配置。stub は `git clone --depth 1 IL-Group/FL-Studio-API-Stubs` (work/ 配下、gitignore)。CPython wasm は `build_cpython_wasm.sh` で作成 (4 分 13 秒)。

### 検証の実測 (コード commit `445dbf9c`。件数は `63fbd940` で再確認済み)

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| provider wasm | `bash provider/build.sh` | `flprov.wasm` 56,850 B | 0.92 s |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… bash build_flpy.sh` | `flpy.wasm` 5,924,680 B。再生成 3 ファイルは差分 0 | 7.00 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 78・unimplemented 357・PASS | 0.37 s |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0 | 1.92 s |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・host_calls 37,425 | 2.23 s |
| playlist 差分 (新規) | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段 PASS | 計 0.2 s (下 4 本と合算) |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 48・diffs 0 | (同上) |
| channels 差分 | `node tests/channels_diff.mjs` | calls 107・diffs 0 | (同上) |
| device 差分 | `node tests/device_diff.mjs` | calls 7・diffs 0 | (同上) |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・win_pair_verified 388 件・ネガコン 6/6 PASS | 2.27 s |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK (比較 229 件のうち同結果 213・差 11 関数。変更前と同じ) | 0.05 s |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6,122 ケース・misbind 0・mismatch 0) | 0.10 s |
| 引数個数 (before/after) | `python3 analysis/flapi/sig_arity_check.py before.json analysis/flapi/flapi_table.json` | before 対象 273・一致 249・不一致 24 / after 一致 250・不一致 23。変わった関数 1 件 (`playlist.muteTrackLock` 1→2) | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | 表の個数の呼出しが code 5 になる関数 3 件 (`channels.soloChannel`・`device.midiOutMsg`・`mixer.getTrackName`) | - |

- before は `git show origin/main:tools/python/analysis/flapi/flapi_table.json`。
- 引数個数の不一致の根拠: `FL_STUBS_DIR=work/fl-stubs python3 analysis/flapi/sig_mismatch_evidence.py` (§3 の表の出典)。

### ネガティブコントロール

- **NC1 (差分検査)**: `host/fl_mock.mjs` の `playlist.muteTrackLock` を 2 引数拒否 (`arity(a, 1, 1)`) に戻すと、`tests/playlist_diff.mjs` は差分 **12 件**を検出して FAIL。元に戻すと PASS (calls 23・diffs 0)。これは 2 引数呼出しの従来の symptom (mock と C の code の食い違い) と同じ形。
- **NC2 (表の再生成)**: `tests/flapi_table_check.sh` の既存ネガコン 6/6 (win PE 無し・空・別物・stubs 無し・emsdk 無し・引き継ぎ元無し) が PASS。

## 1. muteTrackLock の実装

binary (コア `0xd56510`・REPORT_PY61 §3) と実装の対応:

| binary | 実装 (`provider/fl_engine.c` と `host/fl_mock.mjs`) |
|---|---|
| `1 <= index <= 0x1f4 (500)` の外は -4 (文言 "Index out of range" = `FL_E_RANGE`) | `PL(0)` が index 1..500 の外で RANGE (code 4) |
| `value == -1` なら `track+0xd5` の byte を反転 | `value == -1` (既定) なら `lock = !lock` |
| それ以外は同じ byte へ `value` の下位 1 byte を書く | `lock = (uint8_t)value` (mock は `v & 0xff`) |
| 準備判定 `call [rax+0x98]` が偽なら -2 (文言 "Operation unsafe" = `FL_E_UNSAFE`) | **未モデル** (常に準備済み)。`[rax+0x98]` の呼出し先は未特定。未解決 §5 |
| 戻り値 None (`0xd82c20` の status 0) | `fl_ret_none` / `return null` |

- 表: `analysis/flapi_table.py` の `EXTRA_PARAMS` で `value:int=-1` を追加した。公開 stub は `index` のみを宣言している (`sig` 1 個)。binary の書式 `i|i` と REPORT_PY61 §3 の `value:int=-1` を根拠にした。生成結果は `flapi_table.json` の 5 行だけ変わり、`provider/gen/fl_table.c` は `{"playlist", "muteTrackLock", 'n', 2, 1, "ii", ...}` の 1 行だけ変わった。
- lock 状態は C 側で外部に出していない (getter 無し)。そのため差分検査は戻り値と code だけを比べ、状態遷移は mock 単体で 8 段検査した (0 → 1 → 0 → 1 → 反転 0 → 2 → 0 (256) → 254 (-2) → 反転 0)。
- `tests/provider_check.mjs` の実装件数を 77 → 78 (`pe102` 集合を追加)。

## 2. 差分検査 `tests/playlist_diff.mjs` (新規)

- 同じ呼出し列を mock と C (wasm) に流し、戻り値と code を比べる (`mixer_diff.mjs` と同じ形式)。
- 内容: value 指定 (0/1/-1/2/256/-2/true)・value 省略 (None)・範囲外 index (0/501/-1 → code 4)・個数違反 (0 個・3 個 → code 5)・型違い (`"1"`・`"x"`・0.5 → code 5)・隣接 API (`getTrackName`・`setTrackName`)。
- 差分 0 は、C が 2 引数を受理して戻り値 None を返すことと、mock の戻り値が同じであることを意味する。lock 状態そのものは比べていない (§1)。

## 3. 不一致 23 件の根拠 (`sig_mismatch_evidence.py` の出力)

### 3-1. 分類と一覧

分類は機械的な規則だけで付けた (PE と stub のどちらが正かは判定していない)。

- **可変長**: stub が `*args` で個数を宣言していない (表の個数は 0)。
- **オーバロード**: 同名の `def` が複数あり、生成器 (`analysis/flapi_table.py` の `sigs[node.name] = …`) は最後の定義だけを採る。
- **stub 少 / stub 多**: stub の引数個数が PE の書式の max と異なる。

| 関数 | 表の個数/PE max | 分類 | stub 宣言 (`tools/python/work/fl-stubs/src/midi_controller_scripting/` 配下) | PE kwlist (先頭 6) |
|---|---|---|---|---|
| playlist.muteTrack | 2/3 | stub 少 | `playlist/__tracks.py:116` | index,value,inGroup |
| playlist.selectTrack | 1/2 | stub 少 | `playlist/__tracks.py:226` | (kwlist 無し) |
| channels.getStepParam | 6/5 | stub 多 | `channels/__sequencer.py:154` | step,param,offset,startPos,padsStride |
| channels.soloChannel | 2/3 | stub 少 | `channels/__properties.py:282` | index,value,useGlobalIndex |
| mixer.armTrack | 1/2 | stub 少 | `mixer/__tracks.py:134` | index,value |
| mixer.enableTrack | 1/2 | stub 少 | `mixer/__tracks.py:227` | index,value |
| mixer.getTrackName | 1/2 | stub 少 | `mixer/__tracks.py:9` | index,maxLen |
| mixer.selectTrack | 1/2 | stub 少 | `mixer/__selection.py:68` | index,value |
| patterns.clonePattern | 1/2 | stub 少 | `patterns/__properties.py:300` | (kwlist 無し) |
| device.midiOutMsg | 4/5 | オーバロード (3 定義) | `device/__device.py:107` (最後の定義) | (kwlist 無し) |
| plugins.getColor | 4/5 | stub 少 | `plugins/__init__.py:312` | index,slotIndex,flag,paramIndex,useGlobalIndex |
| plugins.getParamValueString | 5/4 | stub 多 | `plugins/__init__.py:272` | paramIndex,index,slotIndex,useGlobalIndex |
| screen.addTextLine | 2/5 | stub 少 | `screen/__init__.py:108` `(text, line, /)` | (kwlist 無し) |
| screen.addMeter | 0/5 | 可変長 | `screen/__init__.py:104` | (kwlist 無し) |
| screen.animateText | 0/1 | 可変長 | `screen/__init__.py:121` | (kwlist 無し) |
| screen.blank | 0/2 | 可変長 | `screen/__init__.py:125` | (kwlist 無し) |
| screen.drawRect | 0/5 | 可変長 | `screen/__init__.py:209` | (kwlist 無し) |
| screen.drawText | 0/6 | 可変長 | `screen/__init__.py:213` | (kwlist 無し) |
| screen.eraseRect | 0/4 | 可変長 | `screen/__init__.py:217` | (kwlist 無し) |
| screen.findTextLine | 0/4 | 可変長 | `screen/__init__.py:249` | (kwlist 無し) |
| screen.removeTextLine | 0/2 | 可変長 | `screen/__init__.py:289` | (kwlist 無し) |
| screen.setScreenActiveCounter | 0/1 | 可変長 | `screen/__init__.py:293` | (kwlist 無し) |
| screen.unBlank | 0/1 | 可変長 | `screen/__init__.py:297` | (kwlist 無し) |

- 個別の根拠 (stub と PE の食い違い): `playlist.muteTrack` は stub に `inGroup` が無い。`channels.soloChannel` は stub の 2 番目が `useGlobalIndex`、PE の 2 番目は `value`。`mixer.getTrackName` は stub の 2 番目が無く、PE は `maxLen`。`plugins.getColor` は stub に `paramIndex` が無い。`plugins.getParamValueString` は stub の `pickupMode` が PE の書式に無い。`channels.getStepParam` は stub の 3 番目 `index` が PE では `offset`、stub の `useGlobalIndex` が PE の書式 (max 5) に無い。`screen.addTextLine` は stub 2 引数・PE 書式 `siiii` (5 引数)。REPORT_PY70 §3 と同じ件。

### 3-2. 実害 (C 実装済みの関数の実測)

`tests/sig_arity_probe.mjs` で実測した (wasm・各関数に PE の max 個の引数を渡す。引数は 1 個目が 0、残りが 1):

| 関数 | 呼出し | 結果 | 意味 |
|---|---|---|---|
| channels.soloChannel | 3 引数 (index, value, useGlobalIndex) | code 5 | PE は受理する個数を拒否する |
| device.midiOutMsg | 5 引数 (PE max) | code 5 | 同上 |
| mixer.getTrackName | 2 引数 (index, maxLen) | code 5 | 同上 (`mixer_diff.mjs` は 2 引数を含まないため差分 0 のまま) |
| plugins.getParamValueString | 4 引数 | ok | 表は 5 個まで受理するが PE は 4 個まで。過大受理 |
| 上記以外の 19 件 | max 個 | code 2 (未実装) | 未実装が先に返り、個数は検査されない |

- 影響の範囲: 表の個数は C dispatch の検査にだけ使う。未実装の関数は handler が NULL のため、個数の不一致は今は表面化しない。実装が入った関数から、正しい呼出しが code 5 になる。
- 推定 (根拠付き・未検証): `kwsig` (PE 書式) を正とすれば、stub を基にした表の個数が誤っている。REPORT_APPENDIX の「バイナリ側を正」方針と同じ向き。関数ごとの確定は子 #2927。

## 4. 変更ファイル

- `tools/python/provider/fl_engine.c`: `Pl.lock` と `FL_H(playlist, muteTrackLock)` を追加。`fl_engine_reset` で `lock = 0`。
- `tools/python/provider/gen/fl_table.c`: 生成器 (`provider/gen_provider.py`) の出力 1 行。
- `tools/python/analysis/flapi/flapi_table.json`: 生成器 (`FLPY_TABLE_ONLY=1 bash build_flpy.sh`) の出力 (muteTrackLock の sig 5 行)。
- `tools/python/analysis/flapi_table.py`: `EXTRA_PARAMS` (binary 由来の補正 1 件)。
- `tools/python/host/fl_mock.mjs`: `playlist.muteTrackLock` と `lock` 状態。
- `tools/python/tests/provider_check.mjs`: 実装件数 77 → 78 (`pe102`)。
- `tools/python/tests/playlist_diff.mjs` (新規)・`tools/python/tests/sig_arity_probe.mjs` (新規・§3-2 の再現)・`tools/python/analysis/flapi/sig_mismatch_evidence.py` (新規・§3-1 の再現)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| muteTrackLock の準備判定 `call [rax+0x98]` の呼出し先が未特定。偽のとき -2 (`FL_E_UNSAFE`) を返す経路が C・mock に無い | 準備前の呼出しで code 3 にならない (実機と差がある) | #2809 (PY-91: 残りのコアと helper の意味。REPORT_PY61 §3 の記載) |
| 不一致 23 件 (§3-1) の表の個数・名前の修正 | 実装済みの 3 関数が PE の個数の呼出しを code 5 で拒否する (§3-2) | 子 #2927 ([PY-110]) |
| 差分検査 `mixer_diff.mjs` は 2 引数の `getTrackName` を含まない | §3-2 の差が差分検査で検出されない | 子 #2927 (受入条件に差分検査の呼出し列の追加を含める) |
| 表の個数が PE と違う未実装の関数 (19 件) は code 2 のまま | 実装が入るまで個数の不一致は表面化しない | #2809 (PY-91)・REPORT_PY57 の未読 26 件 |

## 6. DEFECTS.md への行案 (報告のみ。DEFECTS.md は未編集)

- 類型 (候補): 生成器が公開 stub の宣言だけから引数個数を取り、`*args` (0 件として入る) と同名オーバロード (最後の定義だけ) を誤った個数にする。症状: 表の個数が binary の書式と違い、実装後の正しい呼出しが code 5 で拒否される。根本原因: 引数個数の正を stub の宣言に置いた。観測: §3-2 の 3 関数。検出信号: `analysis/flapi/sig_arity_check.py` の不一致数 (現在 23)。修復案: PE 書式の個数を正として生成する (子 #2927)。

## 7. 事前推定と実測の差

- issue の「`tools/python/tests/playlist_diff.mjs` の 2 個呼出しを code 5 から差分 0 に変える」: 当該ファイルは repo に無かった。新規作成した (§2)。
- issue の「`tools/python/REPORT_PY62.md` §4」: 当該ファイルは存在しなかった。#2027 の記録は REPORT_PY61 §3・REPORT_PY70 §3 にある。
- issue の「`node tests/provider_check.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs` (48/48)」: 実測どおり (§検証)。`tests/provider_check.mjs` の実装件数は 77 → 78 に変わった。
- 推定 (根拠付き): 24 件の不一致のうち、muteTrackLock 以外は PE 側の正しさも stub 側の正しさも未確定。関数ごとの binary 検証は子 #2927。
