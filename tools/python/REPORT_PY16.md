# PY-16 (#654): stubs 既定値 `midi.*` の評価 — 全文

> [REPORT.md](REPORT.md) §15 の全文。250 行上限のため分割移動 (本体は要約のみ)。

## stubs 既定値 `midi.*` の評価 (PY-16, #654)

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
- 770 行、先頭行 `# name=FL Studio (midi) parameters`。AST で確認: 代入文 571、一意名 565。重複代入は 6 名 (`EKRes` `CT_Sampler` `CT_GenPlug` `CT_Layer` `CT_AudioClip` `CT_AutoClip`) で、いずれも 2 回の式が同一。
- 定数のみではない: 末尾 (769〜770 行) に関数定義 `EncodeRemoteControlID` が 1 件ある。既定値の解決には関与しない。
- 検算: `midi` を `sys.modules` に入れ、`fl_api._default_value(expr)` と `eval(expr, {"midi": midi})` (検算用。repo には入れない) の型と値を比べた → 21/21 一致、全 20 式一致。
- host 引数: `setChannelPitch(1, value=5, pitchUnit=1, useGlobalIndex=False)`・`transport.rewind(startStop=1)`・`transport.globalTransport(index=1, value=2)`・`mixer.getEventValue(index=1)` の既定値 (`pickupMode`・`flags`・`pmeFlags`・`flags`・`value`) が実物の midi 値で host へ渡る (値は LEGAL 方針により記載しない)。
- 検算スクリプトは repo 外 (`$RUNNER_TEMP/verify/midi_real_check.py`、指示により非コミット)。

**wasm 回帰** (HEAD `4b3cbe2`、`[EMSDK]` 6.0.12、node 22.23.3、直列 1 本。`fl-win64` から `block24429`・`24430`・`25159`・`00031` を `work/` と `$RUNNER_TEMP` へ配置。load average (1 分値) は開始 3.22、終了 2.91。CPython ビルド中は 3.5 前後):

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

**範囲外**: `run_all.sh` 全体 (step 3・4 の固定パス、#630) は未実施。`browser_check.mjs` (headless Chrome)・`mcp_ui_check.mjs`・`midi_ui_check.mjs` (Vite) は未実施。

**範囲外**: 実機 FL での検証は未実施。FL 上で利用者の `midi` が bind 時に import できることは未確認。`midi` が無い環境で既定値を省略した呼出しは `ModuleNotFoundError` になる (旧 `NameError` と同じく呼出し時に失敗する。省略時のみ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実機 FL で `midi.*` 既定値 (21 引数) が解決されることの確認 | 実機で未確認 | #81 (PY-9 b) の実機確認項目 |
| 実物 midi 検算スクリプトを repo に置くか (現状は repo 外) | 再現に FL 素材が要る | PM 判断 (repo 化するなら別 PR) |
| `all_tools.mjs` の summary は、例外を握る tool の結果欠落を検出しない (soft_error 0 のまま) | 今回の欠落は tool_coverage.json の差分でしか見えなかった | 親 #81 に子チケット案 (追跡 JSON 差分の gate 化) を提案。PM 判断 |
| `browser_check`・`mcp_ui_check`・`midi_ui_check`・`run_all.sh` 全体は未実施 | Chrome / Vite 経路の回帰は未確認 | #630 (固定パス解消) の後の run |
