# tools/python REPORT 付録

REPORT.md (250 行上限) から分割移動した節の全文 (無変更移動。移動元の要約は REPORT.md の同名節)。

## 7c. ilmcp 9 関数の実装 (PY-3 / #82) — `host/ilmcp.mjs`

既知類型との関係: 該当なし (lift ではなく JS ホスト実装。DEFECTS.md の対象外)。検証起点 commit は PR 本文参照。

**結論**: `ilmcp` 9 関数を `host/ilmcp.mjs` に実装し `fl_mock.mjs` から差し替えた (旧: 戻り値固定の偽実装)。class B 8 tool + U 2 tool を wasm CPython 上の実 `MCPTools.pyc` で実行し、**FLEngine 側状態** (チャンネル・ミキサースロット・PRScript・highlight) を検査する e2e `tests/ilmcp_e2e.mjs` が 25/25 PASS。
**ただし受入条件「実エンジン上で動作」は未達**: FLEngine は未完成 (`tools/flelift/boot` は InitUnits まで)。本実装は JS ホストの状態機械で、実 FL との戻り値・例外の一致は未検証。

| 関数 | 引数規約 (MCPTools 逆アセンブル実測) | 実装 |
|---|---|---|
| getBrowserNames(name, recursive) | name = `Plugin database[/…]`、recursive = int(0/1) | カタログ木の直下 / 全子孫を `["Effects/", …, "Drum/Kick"]` の list で返す。不明パスは ValueError |
| addChannel(plugin) | 拡張子・パスは MCPTools 側で除去済み | generator のみ受理。戻り = 0 起点 index。effect 名・未知名は ValueError |
| removeChannel(idx) | 0 起点。MCPTools が降順に呼ぶ | 範囲外は IndexError (code 4) |
| addEffect(plugin, track, slot) | slot は 0 起点 (visual−1)。**plugin="" = スロット消去** (remove_effect / reset_mixer_tracks が使う) | effect のみ受理。track 0..126・slot 0..9 |
| storePRScript(name, source) | name は拡張子なし | `/ \ :` を含む名前は拒否 (保存先は FL の Piano roll scripts dir 想定) |
| runPRScript(source) | `ui.showWindow(piano roll)` の後に呼ばれる | ソースを保持し `st.prRunner` があれば委譲。**実行本体は PY-5 (#79) の flpianoroll 待ち** |
| getHighlightNames() / showHighlight(item,name,caption,whenDone,flag) | whenDone は Python callable (`{__cb:id}`) | 名前は FLEngine win64 rodata 実測 21 件 (旧モックは 4 件・大文字小文字も違った: `Piano roll` ≠ 実機 `Piano Roll`) |
| forwardTutorialEvent | MCPTools 未使用・arity 不明 | 呼出を記録して None |

データ: `analysis/ilmcp/plugin_catalog.json` = native 136 (fst_manifest の `Data/Patches/Plugin database`: Generators 57 / Effects 79) + installed 5 (`hostbridge/nfo/specs/wasm_plugins.json`)。`analysis/ilmcp/highlight_names.json` = rodata の UnicodeString リテラル 21 件。生成 = `FL_WIN64_DIR=… python3 analysis/ilmcp_catalog.py`。
`/py/` の配信許可 (`vite.config.ts` `pyAssets`) は ilmcp.mjs が import する 2 JSON を個別に列挙している。import 一覧からの自動生成は、許可リストを意図的に固定する設計 (PY-4) を崩すため不採用。取りこぼしは `mcp_ui_check.mjs` (run_all step 11) が検出する。
カタログは**名前とカテゴリのみ** (FL 由来のバイト列は含まない)。FL 同梱プラグイン名・UI 文字列 21 件をリポジトリに置くことの可否は `docs/LEGAL.md` に照らして未確認 → PM 判断事項 (下記未解決)。

### 検証 (runner, node 22.23.3, 4 core。検証起点 = クリーン worktree の commit 828d245。環境: `work/` に MCPTools.pyc・midi.py・utils.py・fl-stubs、`dist/` に `build_flpy.sh` 産の flpy.*)
| コマンド | 結果 |
|---|---|
| `node tests/ilmcp_e2e.mjs` (n=3) | **25/25 PASS** × 3。wall 0.23 / 0.23 / 0.24 s (チェック本体 43 / 44 / 47 ms)、load average 0.14 |
| `node tests/all_tools.mjs` | 48/48 ok、host_calls 37,424 (変化なし)、callback_roundtrip true、1.05 秒 |
| `node tests/poc_mcp.mjs` | POC OK、0.60 秒 |
| `node tests/browser_check.mjs` (headless Chrome) | BROWSER OK (crossOriginIsolated, 48 tools)、12.5 秒 |
| ネガティブコントロール `--negative <fn>` (その関数を「何もしない / 空」に差替え) | 8 関数すべて検出: getBrowserNames 5 / addChannel 4 / removeChannel 1 / addEffect 3 / storePRScript 2 / runPRScript 1 / getHighlightNames 4 / showHighlight 3 件 FAIL (`NEGATIVE-CONTROL OK`) |

### 検証 2 (PR #470 head での再実測。runner, node 22.23.3, 4 core。素材 fl-win64 から `fetch_inputs.sh`、`build_cpython_wasm.sh` + `build_flpy.sh` = 253 秒。main (bd67740) merge 後の競合解消 `fl_mock.mjs` / `run_all.sh` を含む)
| コマンド | 結果 |
|---|---|
| `node tests/ilmcp_e2e.mjs` (n=3) | 25/25 PASS × 3。wall 0.44 / 0.42 / 0.41 s、load average 3.49 (ビルド直後) |
| `node tests/all_tools.mjs` / `FL_ENGINE=wasm node tests/all_tools.mjs` | どちらも 48/48 ok、host_calls 37,424 |
| `node tests/poc_mcp.mjs` / `node tests/browser_check.mjs` | POC OK 1.27 s / BROWSER OK 1.52 s |
| `node tests/provider_check.mjs` (run_all 9b) | PASS (implemented 60 / mcp_static 60) |
| **`node tools/python/tests/mcp_ui_check.mjs`** (run_all step 11) | **MCP UI OK**、exit 0、8.53 s (UI で tools/list = 48・get_tempo = 130 BPM、devtools で set_tempo(140) → 140)。`--neg` は NEG-CONTROL DETECTED |
| 同上、`vite.config.ts` の ilmcp JSON 許可を**外した**状態 | **FAIL** (`Failed to fetch dynamically imported module: …/py/host/fl_mock.mjs`)、exit 2 → 修正 (`pyAssets` の `allowed` に `analysis/ilmcp/(plugin_catalog\|highlight_names).json`) の検出力を確認。許可を戻した状態で再 OK |
| run_all step 12 / 13 / 14 | midi_script OK (23 checks、`--neg` exit 1)、subinterp OK (12 checks)、midi_ui_check OK。`midi_bundled_device.mjs` は NOT VERIFIED (exit 3): fl-win64 素材から同梱 device script を取れない (`fetch_inputs.sh` の win64 経路が配置しない)。本 PR 範囲外 |

`run_all.sh` 全体は `/home/ubuntu` 固定 (#630) のため一括実行できず、上記は step ごとの個別実行。

`all_tools.mjs` の 48/48 は「エラー文言が無い」判定なので、旧モックでも通っていた (get_browser_names の戻りが `[object Object]` だった点は `tool_coverage.json` の差分に現れる)。状態検査は `ilmcp_e2e.mjs` が担う。

### 仮定 (実機未確認)
- getBrowserNames の戻り形: 旧モックは `{name, items}` dict、本実装は文字列 list。MCPTools は `data` をそのまま返すだけで形を検査しないため静的解析では確定できない。実機の形は PY-9 (#81) で確認。
- フォルダ末尾 `/` の表記・`recursive` の深さ・エラー時が例外か空 list か。
- addEffect の既知プラグイン検査: 実機が未知名に例外を返すか黙って無視するかは未確認 (MCPTools は例外を捕捉して "Failed to add effect" を返す実装なので、どちらでも tool 側は破綻しない)。

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine 上での動作 (受入条件 1) | PY-3 を Closes にできない | #74 (PY-1) の実エンジン結線後に再検証 |
| C provider (`fl_api_call`, PR #459) の ilmcp ハンドラは旧モック意味論のまま | provider 経由 (`FL_ENGINE=wasm`) では本実装と挙動が乖離 | #459 (MERGED) にコメント済み。`fl_engine.c` を本実装と同じ意味論に更新するチケットは PM 起票待ち |
| runPRScript の実行 (flpianoroll) | run_piano_roll_script はソース受領までで、スクリプトは走らない | #79 (PY-5) |
| 実機の戻り形・例外の確認 | 上記「仮定」 | #81 (PY-9) |
| `run_all.sh` が `/home/ubuntu` 固定のまま | CI で一括実行できない (本 run は手動で work/ 配置) | #630 (PY-15) にコメント済み (親 #294) |
| カタログ (プラグイン名 141 件) と highlight 名 21 件の commit 可否 | FL 由来の名称文字列をリポジトリに含める | #569 (LGL-7)。`docs/LEGAL.md` 照合は未実施。不可なら実行時に利用者の FL から生成する形へ変更 |

## 9. 下流チケット案

| # | 内容 | 規模 |
|---|---|---|
| T1 | **(MCP 60 関数は §7b で完了。残り MIDI 経路 → 426 関数は未着手)** FLEngine wasm に flapi provider (`fl_api_call(fn_id,slots)`) を実装: まず MCP が使う 60 (公開 52 + ilmcp 8) + MIDI 経路 (device/transport/mixer/channels) 優先 → 426 関数。`flapi_table.json` から C 雛形を生成 | L |
| T2 | CPython を FLEngine wasm へ静的リンク (JS 往復撤廃)。`flpy.c` 再利用、スレッド/GIL 方針確定 | M |
| T3 | `ilmcp` 9 関数の実装 (PluginDB/Browser 列挙、addChannel/addEffect、PRScript store/run) → MCP B 群 8 tools | L |
| T4 | MCP JSON-RPC をアプリ内 UI/devtools に公開 (`mcp_rpc.mjs` を FLEngine UI に接続、外部 LLM 無し) | S |
| T5 | piano roll scripting: `flpianoroll`(Note/Marker/score/ScriptDialog) + `.pyscript` ローダ、同梱 5 本 (Euclidean/Humanize/Arpeggiator…) を回帰試験に。ScriptDialog は HUD フォーム連携 | L |
| T6 | MIDI scripting ホスト: device script(.py) ローダ、27 callback 配送、Web MIDI 入力→`dispatch_midi`。サブインタプリタ可否の wasm 検証 | M |
| T7 | Edison `enveditor` / `flcpt` / `flrack` module と Chord progression ツール (pyc 39 + pyscript 2) の動作検証 | M |
| T8 | 性能: 構造値の binary ABI、バッチ API、MIDI 1 イベント当り呼出し数の計測 | S |
| T9 | 実機 FL でのモック意味差検証 (ユーザ環境があれば) と kwargs 署名の rodata 書式文字列からの自動復元 | S |
