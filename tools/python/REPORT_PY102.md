# PY-102 (#2883): playlist.muteTrackLock の value を実装し、flapi 表の引数個数の不一致 (24 件) に根拠を付ける

親: #2027 (PY-62)。引数個数の不一致 (取り込み前 24 件) は main の #2927 ([PY-110]・PR #2956) で解消済み (現 head の不一致 0 件・§8)。PE 追加引数の意味論は子 #2950 ([PY-115])、kwlist 無しの名前と書式は子 #2952 ([PY-116])、準備判定 (-2) の未モデルは子 #2959 ([PY-117])。muteTrackLock の binary 意味論は `tools/python/REPORT_PY61.md` §3。
既知類型との関係: 該当なし (lift 作業ではない。flapi 表の生成器・provider・mock の実装)。

## 結論

- **muteTrackLock**: 表の個数を binary の書式 `i|i` (required 1・max 2) に合わせ、C handler と mock を実装した。2 引数の呼出しは、従来の code 5 (TypeError) から、戻り値 None の差分 0 になった。
- **不一致**: 取り込み前 (before = `b2b052ce`) の `sig_arity_check.py` の不一致は 24 → 23 件 (変わった関数は 1 件 = muteTrackLock)。残り 23 件は全件に根拠 (§3) を付けた。その 23 件は main の #2927 (PR #2956) で解消済みで、現 head の不一致は 0 件 (§8)。PE 追加引数の意味論と kwlist 無しの名前は未確定のまま、子 #2950・#2952 へ付け替えた (§5)。
- **実害 (取り込み前の実測)**: 23 件のうち C 実装済みの 3 関数は、PE が受け付ける個数の呼出しを code 5 で拒否していた (§3-2)。現 head の `sig_arity_probe.mjs` は fails 0 (§8)。
- issue が参照した `tools/python/tests/playlist_diff.mjs` は repo に存在しなかった (`git ls-files` で 0 件)。本 PR で新規作成した。`tools/python/REPORT_PY62.md` も存在しない (issue の参照先の誤り)。#2027 の記録は REPORT_PY61 §3 と REPORT_PY70 §3 にある。

## 測定

- 注記: 本節 (`4ecc1062`) は main の PY-113 (#2955)・PY-115 (#2976) を取り込む前の測定 (`f9666241` で #2927 までの main を取り込んだ後の commit)。PY-113/115 を含む正本は §8 (測定 commit `4f621cad`)。
- 測定 commit (コードを変えた最後の commit): `4ecc1062` (main 取り込み後の修正)。`f9666241` は `origin/main` (`5405a304`) の merge で、競合は `flapi_table.py`・生成物 (`flapi_table.json`・`fl_table.c`)・テスト 2 件。取り込みで、表の 23 件の不一致と未実装 19 件は main の #2927 (PR #2956) で解消済み。`83508efa` (`pe102` コメント修正。挙動は変えていない) の後、`4ecc1062` までのコード差分は main の取り込みと、その解消 (`flapi_table.py` の `EXTRA_PARAMS` に `arity_from: kwsig` を付けた 1 行)。統合前の PY-102 のコードは `445dbf9c`・`63fbd940` にある。
- 差分の証跡: `git diff --stat 4ecc1062 HEAD -- tools/python/analysis/flapi tools/python/analysis/flapi_table.py tools/python/provider tools/python/host tools/python/tests` は 7 files (300 insertions, 13 deletions)。main の PY-113/115 (`5f23cc2f`・`b151dffa`・`4f621cad` の取り込み) の分を含むため 0 行ではない。したがって本節の値は `4ecc1062` 時点の記録で、現 head の正本は §8。
- 検証起点: origin/main `b2b052ce` (着手時)。
- 環境: GitHub Actions runner (4 コア)。測定開始時の `/proc/loadavg` は `0.10 0.36 0.21`、終了時は `0.36 1.01 0.63` (CPython ビルド直後)。並列 1 本。
- 素材: `fl-win64` は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin' '*block24429_DATA.bin' '*block24430_DATA.bin' '*block25159_DATA.bin' '*block24618_DATA.bin'` で展開 (2.31 s)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` を使う。emsdk は `toolchain-emsdk` を展開せず、runner 既定の emsdk を使った (`build_flpy.sh` の `EMSDK_DIR`、`provider/build.sh` の `EMSDK_ENV` の既定値。[EMSDK])。PR 本文の `oc_artifacts` は `fl-win64` のみ。
- 素材の利用: `fetch_inputs.sh` で win64 の DATA block から midi.py・utils.py・MCPTools.pyc・device script を配置。stub は `git clone --depth 1 IL-Group/FL-Studio-API-Stubs` (work/ 配下、gitignore)。CPython wasm は `build_cpython_wasm.sh` で作成 (3 分 20 秒。本測定で作成。CPython 側のソースは変わっていない)。

### 検証の実測 (測定 commit `4ecc1062`。PY-113/115 取り込み前)

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| provider wasm | `bash provider/build.sh` | flprov.wasm 57,199 B | - |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… bash build_flpy.sh` | flpy.wasm 5,924,680 B。再生成 3 ファイル差分 0 (`git status` が空) | 5.5 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 84・unimplemented 351・PASS (`4ecc1062` の test の assert 値。内訳の合計 84 と一致) | - |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425 | - |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・host_calls 37,425 | - |
| playlist 差分 (新規) | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段 PASS | - |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 49・diffs 0・PASS | - |
| channels 差分 | `node tests/channels_diff.mjs` | calls 123・diffs 0・PASS | - |
| device 差分 | `node tests/device_diff.mjs` | calls 8・diffs 0 (rejects 4・midi_out 5)・PASS | - |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・win_pair_verified 388 件・ネガコン 6/6 PASS・fail 0 | 1.96 s |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK (比較 229 件のうち同結果 213・差 11 関数。変更前と同じ) | - |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6,122 ケース・misbind 0・mismatch 0) | - |
| 引数個数 (before/after) | `python3 analysis/flapi/sig_arity_check.py before.json analysis/flapi/flapi_table.json` | before 対象 273・一致 249・不一致 24 / after 一致 273・不一致 0 (main の #2927 / PR #2956 で解消済み) | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | kwsig_targets 24・implemented 5・fails 0 (main 取り込み後。解消前は 3 関数が code 5) | - |

- before は `git show b2b052ce:tools/python/analysis/flapi/flapi_table.json`。

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
| 準備判定 `call [rax+0x98]` が偽なら -2 (文言 "Operation unsafe" = `FL_E_UNSAFE`) | **未モデル** (常に準備済み)。`[rax+0x98]` の呼出し先は未特定。未解決 §5 (子 #2959) |
| 戻り値 None (`0xd82c20` の status 0) | `fl_ret_none` / `return null` |

- 表: `analysis/flapi_table.py` の `EXTRA_PARAMS` で `value:int=-1` を追加した。公開 stub は `index` のみを宣言している (`sig` 1 個)。binary の書式 `i|i` と REPORT_PY61 §3 の `value:int=-1` を根拠にした。生成結果は `flapi_table.json` の 6 行 (3 行削除・3 行追加。引数 `arg1` の name・type・default が `value`・`int`・`-1` に変わる) だけ変わり、`provider/gen/fl_table.c` は `{"playlist", "muteTrackLock", 'n', 2, 1, "ii", ...}` の 1 行だけ変わった。
- lock 状態は C 側で外部に出していない (getter 無し)。そのため差分検査は戻り値と code だけを比べ、状態遷移は mock 単体で 8 段検査した (0 → 1 → 0 → 1 → 反転 0 → 2 → 0 (256) → 254 (-2) → 反転 0)。
- `tests/provider_check.mjs` の実装件数を 77 → 78 (`pe102` 集合を追加)。

## 2. 差分検査 `tests/playlist_diff.mjs` (新規)

- 同じ呼出し列を mock と C (wasm) に流し、戻り値と code を比べる (`mixer_diff.mjs` と同じ形式)。
- 内容: value 指定 (0/1/-1/2/256/-2/true)・value 省略 (None)・範囲外 index (0/501/-1 → code 4)・個数違反 (0 個・3 個 → code 5)・型違い (`"1"`・`"x"`・0.5 → code 5)・隣接 API (`getTrackName`・`setTrackName`)。
- 差分 0 は、C が 2 引数を受理して戻り値 None を返すことと、mock の戻り値が同じであることを意味する。lock 状態そのものは比べていない (§1)。

## 3. 取り込み前 (before = `b2b052ce`) の不一致 23 件の根拠 (`sig_mismatch_evidence.py` の出力)

現 head の `sig_arity_check.py` は不一致 0 件 (main の #2927 / PR #2956 で解消・§8)。以下は解消前の根拠として残す。

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

### 3-2. 実害 (取り込み前の C 実装済み関数の実測。現 head の結果は §8)

`tests/sig_arity_probe.mjs` で実測した (wasm・各関数に PE の max 個の引数を渡す。引数は 1 個目が 0、残りが 1):

| 関数 | 呼出し | 結果 | 意味 |
|---|---|---|---|
| channels.soloChannel | 3 引数 (index, value, useGlobalIndex) | code 5 | PE は受理する個数を拒否する |
| device.midiOutMsg | 5 引数 (PE max) | code 5 | 同上 |
| mixer.getTrackName | 2 引数 (index, maxLen) | code 5 | 同上 (`mixer_diff.mjs` は 2 引数を含まないため差分 0 のまま) |
| plugins.getParamValueString | 4 引数 | ok | 表は 5 個まで受理するが PE は 4 個まで。過大受理 |
| 上記以外の 19 件 | max 個 | code 2 (未実装) | 未実装が先に返り、個数は検査されない |

- 影響の範囲: 表の個数は C dispatch の検査にだけ使う。未実装の関数は handler が NULL のため、個数の不一致は今は表面化しない。実装が入った関数から、正しい呼出しが code 5 になる。
- 推定 (根拠付き・未検証): `kwsig` (PE 書式) を正とすれば、stub を基にした表の個数が誤っている。REPORT_APPENDIX の「バイナリ側を正」方針と同じ向き。現 head では main の #2927 (PR #2956) で表の個数が kwsig に揃い、上の 3 関数の code 5 は解消した (`sig_arity_probe.mjs` fails 0・§8)。追加引数の意味論 (soloChannel.value・getTrackName.maxLen・midiOutMsg 5 個目・getParamValueString) は子 #2950 (PY-115)、kwlist 無しの名前と書式は子 #2952 (PY-116) で確定する。

## 4. 変更ファイル

- `tools/python/provider/fl_engine.c`: `Pl.lock` と `FL_H(playlist, muteTrackLock)` を追加。`fl_engine_reset` で `lock = 0`。
- `tools/python/provider/gen/fl_table.c`: 生成器 (`provider/gen_provider.py`) の出力 1 行。
- `tools/python/analysis/flapi/flapi_table.json`: 生成器 (`FLPY_TABLE_ONLY=1 bash build_flpy.sh`) の出力 (muteTrackLock の sig の 6 行。3 行削除・3 行追加)。
- `tools/python/analysis/flapi_table.py`: `EXTRA_PARAMS` (binary 由来の補正 1 件)。適用順: `EXTRA_PARAMS` (L108) で sig に `value` を足して 2 個にした後、`pe_arity` (L216) は `len(params) != kwsig.max` のときだけ呼ばれる。muteTrackLock は 2 個で max 2 のため `pe_arity` は動かず、二重には補正されない。
- `tools/python/host/fl_mock.mjs`: `playlist.muteTrackLock` と `lock` 状態。
- `tools/python/tests/provider_check.mjs`: 実装件数 77 → 78 (`pe102`)。
- `tools/python/tests/playlist_diff.mjs` (新規)・`tools/python/analysis/flapi/sig_mismatch_evidence.py` (新規・§3-1 の再現)。`tools/python/tests/sig_arity_probe.mjs` は既存 (main の `46f5a007`・#2927 の commit。§3-2 の再現に使う)。

## 5. 未解決 (起票先)

取り込み前の不一致 24 件 (§3)・実装済み 3 関数の個数拒否 (§3-2)・未実装 19 件は、main の #2927 (PR #2956) で解消済み (現 head の不一致 0 件)。open な追跡先は次の 3 件。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| muteTrackLock の準備判定 `call [rax+0x98]` (0xd56535) の呼出し先が未特定。偽のとき -2 (`FL_E_UNSAFE`) を返す経路が C・mock に無い (REPORT_PY61 §3) | 準備前の呼出しで code 3 にならない (実機と差がある) | #2959 |
| `channels.soloChannel` の `value`・`useGlobalIndex`、`mixer.getTrackName` の `maxLen`、`device.midiOutMsg` の 5 個目、`plugins.getParamValueString` の意味論が未確定 (C・mock が読まない) | 追加引数の値を変えても結果が変わらない | #2950 |
| kwlist 無しの名前と書式が未確定 (`screen.*` 10 件・`screen.addTextLine` ほか。名前は `arg{i}` のまま) | 引数名の検査と書式の正しさが未確認 | #2952 |

## 6. DEFECTS.md への行案 (報告のみ。DEFECTS.md は未編集)

- 類型 (候補): 生成器が公開 stub の宣言だけから引数個数を取り、`*args` (0 件として入る) と同名オーバロード (最後の定義だけ) を誤った個数にする。症状: 表の個数が binary の書式と違い、実装後の正しい呼出しが code 5 で拒否される。根本原因: 引数個数の正を stub の宣言に置いた。観測: §3-2 の 3 関数。検出信号: `analysis/flapi/sig_arity_check.py` の不一致数 (取り込み前 23・現 head 0)。修復案: PE 書式の個数を正として生成する (main の #2927 / PR #2956 で実施済み)。

## 7. 事前推定と実測の差

- issue の「`tools/python/tests/playlist_diff.mjs` の 2 個呼出しを code 5 から差分 0 に変える」: 当該ファイルは repo に無かった。新規作成した (§2)。
- issue の「`tools/python/REPORT_PY62.md` §4」: 当該ファイルは存在しなかった。#2027 の記録は REPORT_PY61 §3・REPORT_PY70 §3 にある。
- issue の「`node tests/provider_check.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs` (48/48)」: 実測どおり (§検証)。`tests/provider_check.mjs` の実装件数は PY-102 で 77 → 78、統合後に 84 (`4ecc1062`)、main の PY-115 取り込み後に 85 (`4f621cad`・§8)。
- 推定 (根拠付き): 取り込み前の 24 件の不一致のうち、muteTrackLock 以外は PE 側と stub 側のどちらが正しいかは未確定だった。その後 main の #2927 (PR #2956) で表の個数は kwsig に揃い、残る未確定は意味論と名前 (子 #2950・#2952) になった。

## 8. main 取り込み後の再測定 (測定 commit `4f621cad`)

- 取り込みの経緯: main の #2955 (PY-113・`playlist.setTrackColor` のバイト順) と #2976 (PY-115・mixer の色) が `host/fl_mock.mjs`・`provider/fl_engine.c`・`tests/provider_check.mjs` を変えたため、PR と競合した。`origin/main` (`f82768d9`) を merge して解消した (PR コメントに解消方針)。
  - `setTrackColor`: main の格納式を採用。`muteTrackLock` は残す。
  - `fl_engine.c` の構造体: `Mix.color_set` (main) と `Pl.lock` (本 PR) を両方残す。
  - `provider_check.mjs`: `pe102` と `pe115` を両方の集合に入れる。件数は main の `impl 84` に muteTrackLock の +1 で `impl 85・unimpl 350`。
- 測定 commit: `4f621cad` (コードを変えた最後の commit)。その後 main (`e87eb52a`) を取り込んだ (merge `329a0564`)。`4f621cad` から取り込み後までのコード差分は、main の新規 `tools/python/analysis/flapi/pe_slot_writers.py` (72 行。build と test から参照されない) だけ。`provider`・`host`・`flapi_table.py`・`flapi_table.json` の差分は 0 行 (`git diff 4f621cad HEAD -- tools/python/analysis/flapi_table.py tools/python/analysis/flapi/flapi_table.json tools/python/provider tools/python/host`)。`tests` は round 5 の空行 1 行 (`provider_check.mjs`) だけで、`git diff --ignore-blank-lines 4f621cad HEAD -- tools/python/tests` は 0 行。
- `4ecc1062` からの差分は main 側の変更を含む (`git diff --stat 4ecc1062 4f621cad -- <同範囲>` = 6 files, 229 insertions(+), 13 deletions(-))。そのため §測定の値は再測定し、本節が正本になる。
- round 5 (レビュー指摘 B1・B2・m1〜m4 の修正): 変更は本ファイル・`docs/DOC_MAP.md`・`tests/provider_check.mjs` の空行 1 行。wasm 系 (provider build・flpy・wasm の all_tools・playlist/mixer 差分・provider ABI・`sig_arity_probe.mjs`) は再実行していない (runner に emsdk が無い)。本節の wasm 系の値は `4f621cad` の実測のまま。HEAD の内容で再実行したのは `analysis/flapi/sig_arity_check.py` (before = `b2b052ce`) だけで、対象 273・一致 273・不一致 0 (下表と一致)。`tests/all_tools.mjs` (mock) は、取得済み入力 (`work/` の `fetch_inputs.sh` 出力) を round 5 で取り直していないため再実行していない。
- 環境: GitHub Actions runner (4 コア)。開始時 `/proc/loadavg` は `0.17 0.34 0.18`。素材は `fl-win64` の 5 block を `FL_WIN64_DIR` 配下に展開 (`extracted/`)。emsdk は [EMSDK] の既定パスに 6.0.12 を上流から取得して配置 (`toolchain-emsdk` 素材は本 run に無い)。stubs は `fetch_inputs.sh`。CPython wasm は `build_cpython_wasm.sh` で作成。

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| CPython wasm | `bash build_cpython_wasm.sh` | exit 0 | 3m52s |
| provider wasm | `bash provider/build.sh` | flprov.wasm 57,402 B。fl_table.c 435 関数・ハンドラ 85 | 1.1 s |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… EMSDK_DIR=… bash build_flpy.sh` | flpy.wasm 5,924,680 B。再生成差分 0 (`git status` が空) | 5.6 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 85・unimplemented 350・PASS | - |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425 | 1.8 s |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・host_calls 37,425 | 1.9 s |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段 PASS | - |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 57・diffs 0・PASS (main の PY-115 で件数増) | - |
| channels 差分 | `node tests/channels_diff.mjs` | calls 123・diffs 0・PASS | - |
| device 差分 | `node tests/device_diff.mjs` | calls 8・diffs 0 (rejects 4・midi_out 5)・PASS | - |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・ネガコン PASS・fail 0 | 2.0 s |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK | - |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6,122 ケース・misbind 0・mismatch 0) | 0.1 s |
| 引数個数 (after) | `python3 analysis/flapi/sig_arity_check.py <origin/main の表> analysis/flapi/flapi_table.json` | 対象 273・一致 273・不一致 0 | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | kwsig_targets 24・implemented 5・fails 0・PASS | - |

- NC1 (差分検査): `host/fl_mock.mjs` の `playlist.muteTrackLock` を `arity(a, 1, 1)` に戻すと、`tests/playlist_diff.mjs` は `playlist 差分 12 件` で FAIL (AssertionError)。元に戻すと PASS (calls 23・diffs 0)。
- 製品 KPI: 起動・GUI・ウィンドウに関わらないため、KPI の前後は書かない。

## 9. 取り込み後の再測定の履歴

- 測定 commit `0e42e1ea` (旧 §9) と `14802840` (旧 §10) の全文は `REPORT_PY102_APPENDIX_2883.md` へ分割移動した (250 行上限。内容は削除していない)。値の正本は §10。

## 10. main 取り込み後の再測定 (測定 commit `3aa3a256`)

- 取り込み。`origin/main` `c98d2c99` を merge (`3aa3a256`)。競合は `tests/provider_check.mjs` の 1 箇所だけ。main 側は PY-152 の `pe152` (arrangement 6 関数) を追加し、本 PR 側は `pe102` (`playlist.muteTrackLock`) を追加した。両方を集合に入れ、件数は main の `impl 109・unimpl 326` に `pe102` の +1 を加えて `impl 110・unimpl 325` (合計 435 は不変)。`fl_engine.c`・`fl_mock.mjs`・`flapi_table.json`・`flapi_table.py`・`gen/fl_table.c` は自動マージで衝突なし。
- 測定 commit: `3aa3a256` (コードを変えた最後の commit)。`git diff 3aa3a256 HEAD -- tools/python ':!tools/python/REPORT_PY102.md' ':!tools/python/REPORT_PY102_APPENDIX_2883.md'` は 0 行 (本節の追記だけが差分)。
- 素材: `fl-win64` の 5 block (`block00031_PE`・`block24429_DATA`・`block24430_DATA`・`block25159_DATA`・`block24618_DATA`) を `$RUNNER_TEMP/fl-win64/extracted/` へ展開 (2.911 s)。`FL_WIN64_DIR` でこれを指した。`fetch_inputs.sh` で `work/` を作成 (stubs は git clone)。`toolchain-emsdk` 素材は本 run に無い。
- emsdk: 上流 `emsdk install 6.0.12` を導入して `activate` し、[EMSDK] の既定位置へ symlink した (`build_cpython_wasm.sh` が既定位置を直書きするため)。CPython wasm は本 run で作成 (22:26:30 → 22:31:05、4 分 34.650 秒、exit 0。CPython 側のソースは変えていない)。
- 環境: GitHub Actions runner (4 コア)。`uptime` の load average は 22:25:05 に `0.24 0.17 0.07`、検証の最後 (22:33:01) に `0.56 1.23 0.71`。

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| provider wasm | `EMSDK_ENV=… bash provider/build.sh` | flprov.wasm 59,267 B。fl_table.c 435 関数・ハンドラ 110 | 1.322 s |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… EMSDK_DIR=… bash build_flpy.sh` | flpy.wasm 5,924,680 B。再生成 3 ファイル差分 0 (`git status` が空) | 7.173 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 110・unimplemented 325・mcp_static 60・PASS | 0.387 s |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段・PASS | 1 s 未満 |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 59・diffs 0・PASS | 1 s 未満 |
| channels 差分 | `node tests/channels_diff.mjs` | calls 161・diffs 0・PASS | 1 s 未満 |
| device 差分 | `node tests/device_diff.mjs` | calls 8・diffs 0 (rejects 4・midi_out 5)・PASS | 1 s 未満 |
| general 差分 (main 由来) | `node tests/general_diff.mjs` | calls 25・diffs 0・PASS | 1 s 未満 |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425 | 2 s |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・host_calls 37,425・callback_roundtrip true | 3 s |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・win_pair 388・ネガコン 6/6 PASS・fail 0 | 2 s |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK | - |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6,122 ケース・misbind 0・mismatch 0) | - |
| 引数個数 (before = `origin/main` `c98d2c99` の表 / after = `analysis/flapi/flapi_table.json`) | `python3 analysis/flapi/sig_arity_check.py <main の表> analysis/flapi/flapi_table.json` | before 対象 274・一致 274・不一致 0 / after 対象 274・一致 274・不一致 0。引数個数が変わった関数 0 件 | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | kwsig_targets 24・implemented 8・unimplemented 16・fails 0・PASS | - |

- 件数の差: handler 104 (`14802840`) → 110 は main の PY-152 `pe152` (arrangement 6 件) の取り込み分。
- 未解決 (§5) は不変: 準備判定 (#2959)・追加引数の意味論 (#2950)・kwlist 無しの名前と書式 (#2952)。
