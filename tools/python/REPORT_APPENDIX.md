# python REPORT 付録

> 正本: `tools/python/REPORT.md`。行数上限 (250 行, `docs/DOC_MAP.md` §1) のため、§PY-13 (#588) と §12・§13 (#81 PY-9 b) の全文をここに無変更で分割移動した。内容は削除していない (Git 履歴に残る)。

## PY-13 (#588): `build_flpy.sh` の flapi_table 再生成を環境変数化

既知類型との関係 (DEFECTS.md): 該当なし (lift ではなくビルド入力の扱い。「入力が無いのに緑」型の gate 欠陥の予防)。

| 入力 | 環境変数 | 既定 (従来どおり) | 欠落時 |
|---|---|---|---|
| win PE | `FL_WIN_PE` または `FL_WIN64_DIR` | `$FL_WIN64_DIR/extracted/block00031_PE.bin` (`tools/shared/env.sh`) | exit 2 (旧: 空 bytes 扱いで `win_pair_verified` 全 false の表を出力) |
| stubs clone | `FL_STUBS_DIR` | `tools/python/work/fl-stubs` (`fetch_inputs.sh` が clone) | exit 2 (旧: 例外) |
| mac dylib | `FL_ENGINE_DYLIB` | `$FL_MAC_DIR/.../FLEngine_x64.dylib` | WARN + 出力先の既存 `flapi_table.json` の `midi_script_callbacks_in_binary` を引き継ぐ。引き継ぎ元も無ければ exit 2 (旧: 空配列で上書き) |
| 出力先 | `FLAPI_OUT_DIR` | `analysis/flapi` | — |
| emsdk | `EMSDK_DIR` | `/opt/emsdk` | exit 2 (link 段のみ) |

- PE 照合が 1 件も一致しない (別ファイル・破損) 場合も exit 2。`FLPY_TABLE_ONLY=1 bash build_flpy.sh` は table / ids / `FLAPI.md` の再生成だけで終了 (emsdk・CPython wasm 不要)。
- 副次: 旧 `flapi_table.py` は `FLAPI.md` 先頭の「自動生成・人手編集禁止」ヘッダを出力せず、再生成で追跡中のファイルが差分になっていた。生成側に移した。
- 検証: `FL_WIN64_DIR=<fl-win64 展開先> bash tests/flapi_table_check.sh` (出力先は一時ディレクトリ。追跡中のファイルは書き換えない)。判定: 再生成 3 ファイルが追跡中とバイト一致 + `win_pair_verified=true` > 0 + ネガコン 6 本が全て exit 非 0 + 理由表示 + 出力不変。前提入力が無ければ exit 3 (NOT VERIFIED)。
- 実測 (Actions runner、oc_artifacts: fl-win64 toolchain-emsdk、直列、n=3): 3 回とも exit 0・wall 2.20 / 2.20 / 2.20 秒・load average 0.13〜0.20。正常系 3 / 3 ファイル一致 (差分 0)、`win_pair_verified=true` 388 件 (REPORT §3 の 388/399 と一致)。ネガコン 6 本 (PE 無し / PE 空 / PE が別物 / stubs 無し / emsdk 無し / dylib も既存 table も無し) は全て exit=2 + 理由表示。
- gate 自体のネガコン: 入力 PE を乱数 1 MB に差し替えると `flapi_table_check.sh` は exit 1、PE 無しは exit 3 (どちらも緑にならない)。範囲外: `build_flpy.sh` の emcc link 段 (CPython wasm の事前ビルド `build_cpython_wasm.sh` が必要で未実施。emsdk の実在 `/opt/emsdk/emsdk_env.sh` のみ確認)、`fetch_inputs.sh` / `run_all.sh` の `/home/ubuntu` 固定パス (run_all.sh の `FL_MAC` / `FL_WIN`)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `run_all.sh` が `FL_MAC` / `FL_WIN` を `/home/ubuntu/...` に固定している | Actions で `run_all.sh` 全体を回せない | #630 (PY-15) |
| mac dylib が無い環境では `midi_script_callbacks_in_binary` を既存値から引き継ぐだけで再抽出できない | 26.1.7 以外の版で更新漏れの恐れ (WARN は出る) | #588 コメントに記載 |

## 12. kwargs シグネチャの静的復元 (PY-9 b, #81)
方式・入力: §7 の kwargs 項目参照。再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi_kwargs.py` (要 capstone, pefile。出力は commit 済み JSON とバイト一致) の後 `python3 tests/kwsig_check.py` (wasm 不要)。

| 項目 | 実測 |
|---|---|
| メソッド表から 435 関数全件に対応付け | 435/435 (13 module)。メソッド表に載るが本 table の module 外の 8 表 (flpianoroll/flcpt/ScriptDialog 等のクラスメソッド) は対象外 |
| 書式文字列を復元 (flags=1/3 + 引数あり) | 303 関数 (flags=1: 200 / flags=3: 103。flags 全体は 1=205, 3=105, 4=125)。flags=4 (NOARGS) 125 件は書式無し。初版の「309 (flags=4: 6)」は `ret` を越えて隣の関数の `lea` を拾った誤検出で、`ret`/`int3` 打切りと NOARGS 除外で修正 (変化は 6 関数のみ。flags=1/3 の 303 件は全て最初の `ret`/`int3` より前に間接 call があり、再生成の前後で不変) |
| **kwlist (引数名) を復元** (flags=3 = VARARGS\|KEYWORDS) | **103 関数**。全件で `len(kwlist) == 書式の最大引数数`。flags=3 で未復元は 2 (`device.flrMidiNote`, `flrMidiCC`: lea の並びが他と異なる) |
| flags=1 (VARARGS のみ、実 FL は kwargs を受けない可能性) | 205 (うち書式あり 200)。**位置引数のみ**。ただし MCPTools が `channels.channelCount(globalCount=)` を kw 呼出しするため kwargs 拒否にはしていない |
| 新規 43 関数のうち | 書式あり 32 / kwlist あり 9 (`fillEachNSteps` `rerollLoopStarter*` `setPluginMixLevel` `setPluginMuteState` `setLoopStarterRootNote` `releaseCC` `selectionSet` 等)。残りは flags=1 (位置引数のみ)/4 (引数なし) |

stubs (LGPL 参照) 署名との照合 (kwlist のある 103 のうち stubs 署名がある関数): 名前一致 66 / **不一致 28** (バイナリ側を正とする)。例: `channels.getChannelName` は stubs の `index` でなくバイナリの kwlist 先頭が `value`、`channels.getChannelVolume` は `mode` でなく `useDb`、`channels.setChannelPitch` は `mode` でなく `pitchUnit`、`mixer.getTrackVolume` は `mode` でなく `flag`、`plugins.setParamValue` は `value` でなく `paramValue`、`transport.globalTransport` は `command` でなく `index`、`device.forwardMIDICC` は `mode` でなく `forwardTo`、`mixer.automateEvent` は `speed` でなく `smoothSpeed`。書式の引数数 (必須/最大) は stubs 署名と 230 件一致 / 49 件不一致 (stubs の引数が欠けている・書式の `|` 位置が異なる等)。
- `fl_api.py`: kwlist があれば stubs 名より優先して kwargs を束縛。省略可能引数の既定値が C 側で静的に不明なとき、それを飛ばして後続だけ指定する呼出しは `TypeError` (推測値で埋めない)。stubs の既定値は、同名の引数のものを引き継ぎ、名前だけ変わった同位置の引数 (`mode`→`useDb` 等) のものも引き継ぐ。stubs 側の名前が kwlist の別位置にある (位置がずれた) 3 関数 `channels.soloChannel` / `plugins.getColor` / `plugins.getParamValueString` は別の引数の既定値になるため引き継がない。未知の kwarg は既定値の評価より先に `TypeError`。
- **kwlist の重複 1 件 (バイナリ由来)**: `arrangement.selectionSet` = `['selStart','selStart','selectNotes','updateSongLoop','scroll']` (kwlist 表 0x151dc00 の先頭 2 エントリが同じ文字列 0xd7890c を指す。2 つ目は `selEnd` の記載ミスと推定)。bind は最初の出現だけを kw で束縛し、2 つ目以降は位置専用 (kw では埋まらない)。実 CPython (3.14, ctypes で `PyArg_ParseTupleAndKeywords` を直接呼出し) は `selStart=5` のみ → 必須欠落 `TypeError` (mock と同じ) だが、位置 1 個 + `selStart=5` は 2 つ目に束縛されて通り、mock はこれを拒否する (誤記を kw で踏まない側に倒した差)。
- 検証 (`tests/kwsig_check.py`): 435 関数に kwsig・kwlist 103・NOARGS 書式無し・bind の 9 区分。区分 8 は PR 前 (stubs 署名のみ) の bind との新旧比較で、94 関数 (stubs 署名と kwlist の両方あり) の「位置 k 個 + kw 1 個 (kwlist の名前)」呼出しのうち旧が通った 224 件が対象、新も同結果 216 件、差 8 件 (4 関数: `getStepParam` はバイナリが 5 引数で 6 つ目を渡さない / 上記のずれた 3 関数。うち 3 件は旧が gap 後の既定値で位置ずれさせていたもの: 新は gap 以降の未指定引数を省略し `getGridBit(index=1)` は `(1,)`、`triggerLiveClip(index=1, blockNum=2)` は `(1, 2)`)。MCPTools.pyc の flapi への kw 呼出し 20 箇所 (重複除き 14 パターン; `KW_NAMES` 付き `CALL` を 3.12 `dis` で抽出。`print(..., file=)` 等は対象外) は新 bind で 14/14 通り、kwlist のある関数では全て kwlist 名と一致 (旧 main の bind は 13/14: `plugins.getParamValueString(slotIndex=, useGlobalIndex=)` が stubs 既定値 `midi.PIM_None` の `eval` で `NameError`)。
- **wasm 回帰** (検証起点 bdd2f7c を別 worktree に展開、`FL_WIN64_DIR` 設定、node 22.23.3、直列 1 本、load average 1.1。`run_all.sh` は step 4 が `/home/ubuntu` 固定 (#588) のため同じ手順を個別実行): `all_tools.mjs` 48/48 (JS mock と `FL_ENGINE=wasm` の両方、host_calls 37,425)・`provider_check.mjs` PASS・`poc_mcp.mjs` POC OK・`browser_check.mjs` (headless Chrome) OK・`midi_script.mjs` 23 check PASS (`--neg` で検出)・`subinterp_probe.mjs` 12 check PASS (各 0〜8 秒)。**`provider_check.mjs:86` が stubs 名で `getChannelName(index=)` を kw 呼出ししており、kwlist (`value`) 採用で `TypeError` になっていた** (ec9813b で FAIL を確認) ため `value=` に修正。未実行: `mcp_ui_check.mjs` / `midi_ui_check.mjs` (Vite が要る)。CPython wasm は ec9813b の run でクリーンビルド 243 秒 (その後 `work/` を別 worktree へ移したため `build_cpython_wasm.sh` の再実行は絶対パスのずれで rc=2、libpython は流用)。`build_flpy.sh` が再生成する `flapi_table.json` は `midi_script_callbacks_in_binary` を失う (§10 の既知問題) ため、`midi_script.mjs` は commit 済みの表で実行。`tests/kwsig_check.py` 0.03〜0.04 秒 (n=3、load 0.44)。`analysis/flapi_kwargs.py` の再生成は両 JSON とも commit 済みとバイト一致。

## 13. 未解決 (#81)
- (a) 実機 FL での `mixer.getCurrentTempo(1)` 等の意味差確認は実機が必要で未着手 (#81 のブロッカーのまま)。`device.flrMidiNote` / `flrMidiCC` の書式・kwlist も未復元 (2 件)。
- stubs 既定値が C 側で不明な引数を飛ばす呼出し (`channels.soloChannel(1, useGlobalIndex=True)` 等 3 関数) は `TypeError`。実 FL は C 側の既定値で通すため意味差。ホストへの「省略」の渡し方 (provider は `None`=handler 既定値、JS mock の `tog` は `undefined` のみ省略扱い) が未統一で、PM 判断待ち (PR #463 コメントに起票依頼)。
- stubs 既定値 `midi.*` 10 種 (21 引数: `PIM_None` 7、`GT_All` 5 ほか) は `eval(…, {})` で `NameError` (main 既存の問題)。本 issue #654 (PY-16) で対応 (`eval` を除き、許可した式だけを評価する。§14)。

## 14. stubs 既定値 `midi.*` の評価 (PY-16, #654)

既知類型との関係: 該当なし (lift / 逆アセではない。PR #463 で入った `fl_api.bind` の既定値評価の不具合)。検証起点 commit: `8d883c3` (origin/main)。修正 commit: `4b3cbe2` (`src/fl_api.py`・`tests/kwsig_check.py` の節 (10))。

**結論**: `bind` の `eval(defaults[n], {})` を削除し、許可した式だけを評価する `_default_value` に置換した。`midi.*` の値は利用者の `midi` モジュールから bind 時に `getattr` で取り、repo には値を書かない (`docs/LEGAL.md`)。修正前は `midi` が globals に無いため、`midi.*` 既定値の 21 引数で `NameError` になっていた。

**全数列挙**: `flapi_table.json` の sig 既定値のうち `midi.` を含むもの = **20 関数・21 引数・名前 10 種** (`_DEFAULT_NAMES` と一致)。解決先は全件 `getattr(利用者の midi, 名前)`。

| 関数 | 引数 (stubs 名) | 既定値式 | 解決先 |
|---|---|---|---|
| playlist.getLiveBlockStatus | mode | `midi.LB_Status_Default` | 実行時 getattr |
| playlist.getLiveStatus | mode | `midi.LB_Status_Default` | 実行時 getattr |
| channels.setChannelPan | pickupMode | `midi.PIM_None` | 実行時 getattr |
| channels.setChannelPitch | pickupMode | `midi.PIM_None` | 実行時 getattr |
| channels.setChannelVolume | pickupMode | `midi.PIM_None` | 実行時 getattr |
| mixer.automateEvent | res | `midi.EKRes` | 実行時 getattr |
| mixer.getEventValue | value | `midi.MaxInt` | 実行時 getattr |
| mixer.getSongTickPos | mode | `midi.ST_Int` | 実行時 getattr |
| mixer.setTrackPan | pickupMode | `midi.PIM_None` | 実行時 getattr |
| mixer.setTrackStereoSep | pickupMode | `midi.PIM_None` | 実行時 getattr |
| mixer.setTrackVolume | pickupMode | `midi.PIM_None` | 実行時 getattr |
| transport.fastForward | flags | `midi.GT_All` | 実行時 getattr |
| transport.globalTransport | pmeflags | `midi.PME_System` | 実行時 getattr |
| transport.globalTransport | flags | `midi.GT_All` | 実行時 getattr |
| transport.markerJumpJog | flags | `midi.GT_All` | 実行時 getattr |
| transport.markerSelJog | flags | `midi.GT_All` | 実行時 getattr |
| transport.rewind | flags | `midi.GT_All` | 実行時 getattr |
| device.linkToLastTweaked | eventId | `midi.REC_None` | 実行時 getattr |
| plugins.getColor | flag | `midi.GC_BackgroundColor` | 実行時 getattr |
| plugins.getName | flag | `midi.FPN_Param` | 実行時 getattr |
| plugins.getParamValueString | pickupMode | `midi.PIM_None` | 実行時 getattr |

既定値式の全種類は 20 (distinct)。うち `midi.` 以外の 10 種 (`False` `-1` `0` `1` `True` `None` `300` `16` `1 / 24` `4`) は旧 `eval` と同じ値になることを検査する (節 (10) (b'))。

**評価器** (`src/fl_api.py` `_default_value`):
- 許可表 `_DEFAULT_NAMES` (10 名): `midi.PIM_None` `midi.GT_All` `midi.LB_Status_Default` `midi.EKRes` `midi.MaxInt` `midi.ST_Int` `midi.PME_System` `midi.REC_None` `midi.GC_BackgroundColor` `midi.FPN_Param`。
- 許可する形: 定数 (`None`・`bool`・`int`・`float`)、単項 `+` `-`、二項 `+` `-` `*` `/` (`operator` で計算)、許可表の `midi.<名>` 属性参照。
- 拒否 (`ValueError`): 文字列・関数呼出し・許可表に無い名前や属性・その他の構文。
- `ast.literal_eval` を使わない理由: `channels.incEventValue` の `res` 既定値 `1 / 24` は二項演算で、`literal_eval` は拒否する (旧 `eval` では通っていた既存挙動)。四則演算を `operator` で計算して `1/24` を得る。

**検証** (HEAD `4b3cbe2`):

| # | 項目 | 手順 | 結果 |
|---|---|---|---|
| 1 | kwsig_check (wasm 不要) | `cd tools/python && python3 tests/kwsig_check.py` ×3 | **PASS** (`kwsig_check: OK`)。wall 44 / 45 / 43 ms。load average (1 分値) 2.37 (CPython wasm ビルドと並行) |
| 2 | ネガコン: 旧 `fl_api.py` + 新テスト | `git archive origin/main tools/python` を `$RUNNER_TEMP/neg_old` に展開し、新 `kwsig_check.py` をコピーして実行 | **FAIL** (exit 1)。(b) の `ch.setChannelPitch` の既定値評価で `NameError` (下) |
| 3 | 実物 midi.py の既定値 | 下記「実物 midi.py」 | **21/21 一致**・20 式中 20/20 一致 (mismatch 0) |
| 4 | wasm 回帰 (下表) | CPython wasm を clean ビルド → `build_flpy.sh` → 各テスト | **PASS** (`all_tools` は wasm・mock とも 48/48)。初回の wasm 実行は provider ビルド前で rc 1 (`dist/flprov.js` 不在) のため、`provider/build.sh` の後に再実行した |

ネガコンの失敗行 (旧 `fl_api.py` 70 行目の `eval` で停止):

```
  File ".../src/fl_api.py", line 78, in f
    a = bind(args, kw)
  File ".../src/fl_api.py", line 70, in bind
    out.append(eval(defaults[n], {}))  # stubs 由来の単純リテラル (True/False/0/-1/None)
  File "<string>", line 1, in <module>
NameError: name 'midi' is not defined
```

(テストの順序: 旧コードで最初に落ちる箇所が (b) の NameError になるよう、非 midi 既定値の eval 一致確認 (b') は (b) の後に置いた。`fl_api._default_value` を先に参照すると旧コードは `AttributeError` で止まるため。)

**実物 midi.py** (commit しない。`fl-win64.tar.zst` から `extracted/block24429_DATA.bin` だけを `--wildcards` で抽出 (2.9 秒) → `tools/python/work/midi.py` = `fetch_inputs.sh` の win64 経路):
- 770 行、先頭行 `# name=FL Studio (midi) parameters`。AST で確認: 代入文 571、一意名 565。重複代入は 6 名 (`EKRes` `CT_Sampler` `CT_GenPlug` `CT_Layer` `CT_AudioClip` `CT_AutoClip`) で、いずれも 2 回の式が同一。`EKRes` は `1 / 24`。
- 定数のみではない: 末尾 (769〜770 行) に関数定義 `EncodeRemoteControlID` が 1 件ある。既定値の解決には関与しない。
- 検算: `midi` を `sys.modules` に入れ、`fl_api._default_value(expr)` と `eval(expr, {"midi": midi})` (検算用。repo には入れない) の型と値を比べた → 21/21 一致、全 20 式一致。
- host 引数: `setChannelPitch(1, value=5, pitchUnit=1, useGlobalIndex=False)`・`transport.rewind(startStop=1)`・`transport.globalTransport(index=1, value=2)`・`mixer.getEventValue(index=1)` の既定値 (`pickupMode`・`flags`・`pmeFlags`・`flags`・`value`) が実物の midi 値で host へ渡る (値は LEGAL 方針により記載しない)。
- 検算スクリプトは repo 外 (`$RUNNER_TEMP/verify/midi_real_check.py`、指示により非コミット)。

**wasm 回帰** (HEAD `4b3cbe2`、`/opt/emsdk` 6.0.12、node 22.23.3、直列 1 本。`fl-win64` から `block24429`・`24430`・`25159`・`00031` を `work/` と `$RUNNER_TEMP` へ配置。load average (1 分値) は開始 3.22、終了 2.91。CPython ビルド中は 3.5 前後):

| 段 | 結果 | wall |
|---|---|---|
| `build_cpython_wasm.sh` (native + wasm、clean) | rc 0。`libpython3.12.a` 9,644,380 B。記録 (`record.mjs`) は `NOTICES_RECORDS_DIR` で一時先へ向け、追跡中の `tools/legal/notices/records/` は更新せず | 4 分 5.5 秒 (実測 `time`) |
| `build_flpy.sh` (table 再生成 → link) | rc 0。flpy.wasm 5,923,823 B / flpy.data 3,261,784 B / flpy.js 120,354 B。table 再生成は追跡中の `analysis/flapi/*.json` と **バイト一致** (出力先は `FLAPI_OUT_DIR` の一時 dir) | 7,060 ms |
| `tests/smoke_direct.mjs` | rc 0 (stdlib 22 module 全 import 可、再帰 900 ok) | 302 ms |
| `FL_ENGINE=wasm node tests/all_tools.mjs` (再実行) | **48/48 ok**、soft_error 0、raised 0、host_calls 37,425、callback 往復 true | 1,883 ms |
| `node tests/all_tools.mjs` (JS mock) | 48/48 ok、host_calls 37,425 | 2,024 ms |
| wasm と mock の tool 別結果 (`tool_coverage.wasm.json` と `tool_coverage.json`) | 48/48 一致 (差 0) | — |
| `provider/build.sh` + `tests/provider_check.mjs` | PASS (関数 435、実装 60、未実装 375) | 341 ms |
| `tests/poc_mcp.mjs` | POC OK | 1,253 ms |
| `tests/midi_script.mjs` | 23 checks PASS | 815 ms |
| `tests/subinterp_probe.mjs` | 12 checks PASS | 6,525 ms |

**追跡 JSON の更新** (`analysis/mcp/tool_coverage.json`、`tests/all_tools.mjs` の mock 実行で生成): origin/main の追跡版との差は **1 tool** のみ。旧版は、パラメータ値を取得する tool が `Normalized Value: 0.5000` だけを返し、`String Value` が欠けていた。旧版では `plugins.getParamValueString` の既定値 `midi.PIM_None` の bind が `NameError` で止まり、host 呼出し (api_calls) に届いていなかった。summary は soft_error 0 のまま ok。新版は `String Value: '50.0 %'`、この tool の host_calls 15→16、総 37,424→37,425。wasm 版も同じ新結果 (上の 48/48 一致)。よって追跡 JSON を新結果で更新し、同じ PR に含める (差分は本修正の効果のみ)。

**範囲外**: `run_all.sh` 全体 (step 3・4 の `/home/ubuntu` 固定パス、#630) は未実施。`browser_check.mjs` (headless Chrome)・`mcp_ui_check.mjs`・`midi_ui_check.mjs` (Vite) は未実施。

**範囲外**: 実機 FL での検証は未実施。FL 上で利用者の `midi` が bind 時に import できることは未確認。`midi` が無い環境で既定値を省略した呼出しは `ModuleNotFoundError` になる (旧 `NameError` と同じく呼出し時に失敗する。省略時のみ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実機 FL で `midi.*` 既定値 (21 引数) が解決されることの確認 | 実機で未確認 | #81 (PY-9 b) の実機確認項目 |
| 実物 midi 検算スクリプトを repo に置くか (現状は repo 外) | 再現に FL 素材が要る | PM 判断 (repo 化するなら別 PR) |
| `all_tools.mjs` の summary は、例外を握る tool の結果欠落を検出しない (soft_error 0 のまま) | 今回の欠落は tool_coverage.json の差分でしか見えなかった | 親 #81 に子チケット案 (追跡 JSON 差分の gate 化) を提案。PM 判断 |
| `browser_check`・`mcp_ui_check`・`midi_ui_check`・`run_all.sh` 全体は未実施 | Chrome / Vite 経路の回帰は未確認 | #630 (固定パス解消) の後の run |
