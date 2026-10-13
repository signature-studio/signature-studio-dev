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
- `fl_api.py`: kwlist があれば stubs 名より優先して kwargs を束縛。省略可能引数の既定値が C 側で静的に不明なとき、それを飛ばして後続だけ指定する呼出しは `TypeError` (推測値で埋めない)。既定値は stubs の**同名**引数の単純リテラルだけを引き継ぐ (名前違いの同位置は別の引数なので引き継がない。PY-15 #653 で変更。規則と影響は §14)。未知の kwarg は既定値の評価より先に `TypeError`。
- **kwlist の重複 1 件 (バイナリ由来)**: `arrangement.selectionSet` = `['selStart','selStart','selectNotes','updateSongLoop','scroll']` (kwlist 表 0x151dc00 の先頭 2 エントリが同じ文字列 0xd7890c を指す。2 つ目は `selEnd` の記載ミスと推定)。bind は最初の出現だけを kw で束縛し、2 つ目以降は位置専用 (kw では埋まらない)。実 CPython (3.14, ctypes で `PyArg_ParseTupleAndKeywords` を直接呼出し) は `selStart=5` のみ → 必須欠落 `TypeError` (mock と同じ) だが、位置 1 個 + `selStart=5` は 2 つ目に束縛されて通り、mock はこれを拒否する (誤記を kw で踏まない側に倒した差)。
- 検証 (`tests/kwsig_check.py`): 435 関数に kwsig・kwlist 103・NOARGS 書式無し・bind の 9 区分。区分 8 は PR 前 (stubs 署名のみ) の bind との比較で、件数と差の規則 (a)〜(c) は §14 に定義した。MCPTools.pyc の flapi への kw 呼出し 20 箇所 (14 パターン) の結果と判定の限界も §14 に記載。
- **wasm 回帰** (旧 HEAD bdd2f7c の計測。本 PR head の再計測は §14。検証起点 bdd2f7c を別 worktree に展開、`FL_WIN64_DIR` 設定、node 22.23.3、直列 1 本、load average 1.1。`run_all.sh` は step 4 が `/home/ubuntu` 固定 (#588) のため同じ手順を個別実行): `all_tools.mjs` 48/48 (JS mock と `FL_ENGINE=wasm` の両方、host_calls 37,425)・`provider_check.mjs` PASS・`poc_mcp.mjs` POC OK・`browser_check.mjs` (headless Chrome) OK・`midi_script.mjs` 23 check PASS (`--neg` で検出)・`subinterp_probe.mjs` 12 check PASS (各 0〜8 秒)。**`provider_check.mjs:86` が stubs 名で `getChannelName(index=)` を kw 呼出ししており、kwlist (`value`) 採用で `TypeError` になっていた** (ec9813b で FAIL を確認) ため `value=` に修正。未実行: `mcp_ui_check.mjs` / `midi_ui_check.mjs` (Vite が要る)。CPython wasm は ec9813b の run でクリーンビルド 243 秒 (その後 `work/` を別 worktree へ移したため `build_cpython_wasm.sh` の再実行は絶対パスのずれで rc=2、libpython は流用)。`build_flpy.sh` が再生成する `flapi_table.json` は `midi_script_callbacks_in_binary` を失う (§10 の既知問題) ため、`midi_script.mjs` は commit 済みの表で実行。`tests/kwsig_check.py` 0.03〜0.04 秒 (n=3、load 0.44)。`analysis/flapi_kwargs.py` の再生成は両 JSON とも commit 済みとバイト一致。

## 13. 未解決 (#81)
- (a) 実機 FL での `mixer.getCurrentTempo(1)` 等の意味差確認は実機が必要で未着手 (#81 のブロッカーのまま)。`device.flrMidiNote` / `flrMidiCC` の書式・kwlist も未復元 (2 件)。
- 途中の省略 (既定値不明の引数を飛ばして後続を kw 指定) の `TypeError` は §14 で決定 (推測で埋めない。末尾の省略だけ C 側の既定値に任せる)。実 FL は C 側の既定値で通す可能性があり、実機での意味差は未確認 (#81 (a))。ホスト側の省略の表し方 (provider の `None`、JS mock の `undefined` 扱い) は本 PR の検証範囲外で未統一のまま (起票先は §14 の表)。
- stubs 既定値 `midi.*` 10 種 (21 引数) は main では `eval` で `NameError` だった。本 PR で `eval` を廃止し単純リテラルだけ採用するため、`midi.*` の既定値は使われない (省略は C 側に任せ、途中なら `TypeError`)。main の `NameError` は本 PR で解消 (件数は §14)。

## 14. 省略引数のホスト受け渡し方式と誤束縛 0 検証 (PY-15, #653)

既知類型との関係 (DEFECTS.md): 該当なし (lift ではなく Python 側の引数束縛。「別の引数の既定値が入る」は本 run の誤束縛の定義)。
親: #81 (PY-9 b)。起点 HEAD: `8d883c3` (main)。検証版 HEAD: 本 PR の最終 commit (下記)。

### 方式の決定 (3 案の比較)
| 案 | 内容 | 判定 |
|---|---|---|
| センチネル | 省略を表す新タグを 16B スロット ABI に追加 | **不採用**。`flhost_lib.js` / `provider/fl_dispatch.c` / `fl_mock.mjs` / 実 FLEngine 側の 4 箇所を同時変更が要る。途中の省略を使う実呼出しが、本 run の MCPTools 20 箇所 (14 パターン) には 0 件 (下表) |
| 位置省略 (末尾のみ) | tuple を短くし、C 側 (`fl_dispatch.c` の `nmin ≤ argc ≤ np`) の既定値に任せる | **採用 (末尾)** |
| C 側既定値の静的特定 | 書式の既定値を binary から復元 | **不採用**。`PyArg_ParseTupleAndKeywords` の既定値は呼出し前の局所変数初期化で、静的に確定できない (#81 (a) の実機確認が必要) |

途中の省略 (既定値不明の引数を飛ばして後続を kw 指定) は `TypeError` (推測で埋めない)。

### 既定値の規則の変更 (誤束縛の原因)
旧 (main, PY-9 b): stubs の既定値を「同名」または「同位置の名前違い」から引き継いでいた。
- 名前違いの同位置 10 件は**別の引数の既定値**: 例 `channels.getChannelVolume` の `mode=False` → `useDb`、`mixer.getTrackVolume` の `mode=0` → `flag`、`general.saveUndo` の `update=True` → `updateHistory`、`device.forwardMIDICC` の `mode=1` → `forwardTo`。
- `midi.*` 10 種 (21 引数) と `'1 / 24'` (1 引数) は `eval` で `NameError` / 数値化。
- 新: 同名のみ引き継ぎ、単純リテラル (`ast.literal_eval` が通る値) のみ採用。`eval` 廃止。

§12 の旧記述「stubs 名が kwlist の別位置に現れる 3 関数 (`channels.soloChannel` / `plugins.getColor` / `plugins.getParamValueString`) は既定値を引き継がない」は**誤り** (訂正)。実装は同名なら位置によらず引き継いでおり、今回の変更で残ったのは「既定値不明の位置を飛ばす」規則だけ。`plugins.getColor` では旧 main が `useGlobalIndex` の既定値を `paramIndex` の位置へ入れて誤束縛していた (新は TypeError)。

### 計測 (全て本 run、`python3 --version` 3.14 / wasm 不要)
| 検査 | 結果 | 所要 |
|---|---|---|
| `tests/kwsig_bind_check.py` (新規) | functions 103 / cases **6122** (期待 tuple 1123 + TypeError 4999) / ok **6122** / misbind **0** / mismatch **0** → PASS | 0.09 秒 (load average 2.26 = CPython wasm ビルドと並行) |
| `tests/kwsig_bind_check.py --src <main の src>` (ネガコン) | ok 5995 / misbind **25** / mismatch **102** → **FAIL** (exit 1) | 同 |
| `tests/kwsig_check.py` (更新) | OK。旧 (stubs 署名のみ) との比較 224 件のうち同結果 208、差 16 件 (11 関数)。差はすべて上の規則変更 (a)〜(c) で説明済み | 0.09 秒 (同 load) |
| MCPTools の flapi kw 呼出し (`tests/mcp_kwcalls_extract.py` + `tests/mcp_kwcalls_bind.py`) | pyc (win64 `block25159_DATA.bin`, 100,674 B) から 20 箇所・**14 パターン**。新 bind で **14/14 通る**。途中の省略を要する呼出し **0** | 0.02 秒 (抽出 `mcp_kwcalls_extract.py` は python3.12 で別途) |

- kwlist 関数の検証定義: misbind = 位置 j ≥ k の値が「その位置の kw 識別子 (値 200000+最初の位置)」でも「同名 stubs 既定値」でもない。mismatch = それ以外の不一致 (期待と違う例外・長さ・値)。
- 期待値は `flapi_table.json` の仕様 (kwlist・required・同名リテラル既定値) から `tests/kwsig_bind_check.py` 内で組む (`src/fl_api.py` の実装は見ない)。positional のみ (kw 0 個) は既存仕様どおり素通し。
- MCP 14 パターンは main の bind でも 14/14 通った (本 run の抽出形式 = positional 個数を CALL の argc から取得)。REPORT §12 の「旧 main は 13/14 (`getParamValueString` の NameError)」はこの形式では再現しなかった。原因未確定 (旧計測の呼出し形式が違う可能性)。**要確認**。

### 検証環境
- 実測 load average・秒は表の値。`tests/kwsig_bind_check.py` の並列 1 本、Python 3.14、`tools/python` の既存テスト (`kwsig_check.py`) と同一条件。
- `tests/mcp_kwcalls_extract.py` は `python3.12` (3.12 の pyc を読むため)。入力は `fl-win64.tar.zst` の `extracted/block25159_DATA.bin` (`tar --zstd -xf ... extracted/block25159_DATA.bin`、2.4 秒)。
