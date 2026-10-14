# tools/python REPORT: PY-95 ui 状態ゲッター 9 件の PE 確定と C provider 実装 (#2831, 親 #2738, 残りの子 #2981・#2982・#3005・#3006・#3007)

既知類型との関係: 該当なし (lift 作業ではない。flapi 関数の PE 確定と provider 実装)。前段: `tools/python/REPORT_PY87.md` (general 4 件・同じ手順)。

## 結論

- ui の未実装 69 関数のうち **9 件** (`isClosing`・`isMetronomeEnabled`・`isPrecountEnabled`・`isStartOnInputEnabled`・`isLoopRecEnabled`・`getTimeDispMin`・`getStepEditMode`・`isBrowserAutoHide`・`getSnapMode`) を PE で確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/ui_state_diff.mjs`。本 PR 単独は 18 呼出し、main 取り込み後は PY-119 の 6 件と統合して 33 呼出し)。
- 9 件はいずれも「状態 1 つを読んで変換 slot `0x15e4280` に渡すだけ」で、副作用・分岐は無い。bool 8 件と int 1 件 (`getSnapMode`)。型は公開 stub の `returns` に従う。
- **値は未確定 (仮置き)**。全て既定値 (`false` / `0`) の固定で、実機の値は未実測。setter の所在は §6 のとおり、一部しか子 issue に無い。
- `isMetronomeEnabled` / `isPrecountEnabled` は、PY-87 の `general.getUseMetronome` / `general.getPrecount` と同じ状態 (同じ slot) を読む。C では同じ変数 (`use_metronome`・`precount`) を参照する。mock と C の一致は既定値と引数過多だけで確かめた。状態を変えた時の対応は未確認 (setter が無いため)。
- main の #3010 (PY-119) が ui ゲッター 6 件を実装し、#2980 は閉じた。残りの ui 未実装は **54 件** (#3005・#3006・#3007 の 12 件 (旧 #2980 の残り)、#2981 の 27 件、#2982 の 15 件)。各 handler の VA は §5。

## 1. 手段

- 素材: `fl-win64.tar.zst` から `extracted/block00031_PE.bin` (関数探索) と DATA block 4 件 (`block25159`・`block24429`・`block24430`・`block24618`、`fetch_inputs.sh` 用) を `$RUNNER_TEMP/fl-win64/extracted/` に展開。emsdk は runner に無かったため、`tools/m1/flags.sh` の pin (6.0.12) を `emsdk install 6.0.12` と `activate 6.0.12` で入れ、`[EMSDK]` (`docs/REFERENCES.md`) の既定位置へ symlink して使った (§4)。
- ハンドラ探索: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <名前...>`。PyMethodDef の entry VA と関数先頭 VA (`fn`) を得て、先頭 40 命令を出す。
- 参照の同定: 各命令の `[rip + disp]` は「次命令の VA + disp」で絶対 VA にした。変換 slot は `call qword ptr [rax]` の直前の `mov rax, [rip+...]` の絶対 VA。
- 戻り型: 公開 stub (`analysis/flapi/flapi_table.json` の `sig.returns`)。

## 2. 確定した 9 件 (PE 根拠)

各関数は `flags=4` (METH_NOARGS)。`sub rsp` → 状態を読む → 変換 slot `0x15e4280` を呼ぶ → `ret` のみ。C = 状態ポインタ slot の内容 (読み取る番地)。

| 関数 | entry | fn (VA) | 状態の読み方 | 変換 slot | stub の戻り型 |
|---|---|---|---|---|---|
| `ui.isClosing` | 0x151b5e8 | 0xd6c230 | slot 0x15e1890 → `byte [C]` | 0x15e4280 | bool |
| `ui.getTimeDispMin` | 0x151b728 | 0xd6cc40 | slot 0x15e1e40 → `byte [C]` | 0x15e4280 | bool |
| `ui.isMetronomeEnabled` | 0x151b8a8 | 0xd6d6d0 | slot 0x15e1498 → `byte [C]` (= general.getUseMetronome の状態) | 0x15e4280 | bool |
| `ui.isPrecountEnabled` | 0x151b8e8 | 0xd6d710 | slot 0x15e0c08 → `byte [C]` (= general.getPrecount の状態) | 0x15e4280 | bool |
| `ui.isStartOnInputEnabled` | 0x151b8c8 | 0xd6d6f0 | slot 0x15e4ea0 → `byte [C]` | 0x15e4280 | bool |
| `ui.isLoopRecEnabled` | 0x151b908 | 0xd6d730 | slot 0x15e2eb8 → C、`O=[C]`、`S=[O+0xa00]`、`byte [S+0x49e]` | 0x15e4280 | bool |
| `ui.getStepEditMode` | 0x151bae8 | 0xd6f0c0 | slot 0x15e2eb8 → C、`O=[C]`、`S=[O+0xab8]`、`byte [S+0x49e]` | 0x15e4280 | bool |
| `ui.isBrowserAutoHide` | 0x151ba88 | 0xd6ed40 | slot 0x15e4b10 → C、`O=[C]`、`byte [O+0x8c4]` | 0x15e4280 | bool |
| `ui.getSnapMode` | 0x151b428 | 0xd6b6e0 | slot 0x15e41f8 → `dword [C]` | 0x15e4280 | int |

- 変換 slot `0x15e4280` は bool 8 件と int 1 件で共通 (PY-87 と同じ観察)。PE からは bool と int を区別できず、型は stub に従う。変換先の関数の同定は未了。
- `isLoopRecEnabled` と `getStepEditMode` は同じ slot `0x15e2eb8` を起点にし、`+0xa00` と `+0xab8` で別の sub-object を読む。sub-object の名前は未同定。
- 9 件の読み先 (slot の指す状態) の意味 (例: `0x15e1890` が「閉じている」の状態か) は未確定。値の意味は仮置きで、setter の同定で確かめる (§6)。

## 3. 実装

- `host/fl_mock.mjs`: state に `uiClosing` ほか 7 項目を追加 (既定 `false` / `0`)、`ui.*` 9 件を定義 (`arity(a, 0, 0)`)。`isMetronomeEnabled` / `isPrecountEnabled` は既存の `useMetronome` / `precount` を読む。
- `provider/fl_engine.c`: 静的変数 7 件 (`ui_closing`・`ui_time_disp_min`・`ui_start_on_input`・`ui_loop_rec`・`ui_step_edit`・`ui_browser_auto_hide`・`ui_snap_mode`) を `fl_engine_reset` で 0 に初期化。`FL_H(ui, ...)` 9 件を `NARGS(0, 0)` 付きで定義。
- `tests/provider_check.mjs`: `pe95` の集合を追加。実装 83 → 92、未実装 352 → 343 (total 435 は不変)。main 取り込み後 (PY-115 の `mixer.getTrackColor` 1 件、PY-100 の 2 件、PY-119 (#3010) の 6 件を加えた) は 実装 101・未実装 334 (§4)。
- `tests/ui_state_diff.mjs` (新規): 9 件の既定値呼出し (9) と引数過多 (9) の計 18 呼出しを mock と C で照合。main 取り込みで PY-119 (#3010) も同名のファイルを追加したため、両方の検査を 1 本に統合した (add/add の競合の解消)。統合後は PY-119 の 6 件 (`getFocused`・`getFocusedFormID`・`getFocusedFormCaption`・`getFocusedPluginName`・`getHintMsg`・`isInPopupMenu`) を加えて計 33 呼出し。

## 4. 検証

測定 commit: `fb0a1619` (main 取り込みの merge。コードを変えた最後の commit)。main の #3010 (PY-119) と本 PR の ui 9 件を、同じ `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/provider_check.mjs`・`tests/ui_state_diff.mjs` に統合した。前回の測定 commit `9f540f4c` は、この統合で置き換わった。`git diff 9f540f4c fb0a1619 -- tools/python ':!*.md'` は 0 行ではない (main の PY-119・PY-124 の追加と、上の統合)。そのため現 HEAD の数値は、`fb0a1619` の作業ツリーで全て測り直した。

測定は `fb0a1619` の内容 (作業ツリーはクリーン) で行った。環境: runner 4 core。測定時の load average 0.24 (`uptime`、21:37:08)。

再ビルド (`fb0a1619` の内容から): 素材 `fl-win64.tar.zst` から上記 5 件を `tar --zstd -xf --wildcards` で展開 (rc 0、2.5 秒)・`fetch_inputs.sh` (rc 0)・`provider/build.sh` (rc 0、handlers 95)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0、4.8 秒)。`build_cpython_wasm.sh` は rc 0 (3 分 27 秒) で、その後 `tools/python/src`・`build_cpython_wasm.sh` に変更は無い (`git diff 9f540f4c fb0a1619 -- tools/python/src tools/python/build_cpython_wasm.sh` は 0 行)。

| コマンド | 結果 | wall |
|---|---|---|
| `node tests/provider_check.mjs` | PASS (435 / 実装 101 / 未実装 334 / MCP 静的 60) | 275 ms |
| `node tests/ui_state_diff.mjs` | calls 33、diffs 0、PASS | 37 ms |
| `node tests/general_diff.mjs` | calls 9、diffs 0、PASS (PY-87 の回帰) | 41 ms |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 36 ms |
| `node tests/channels_diff.mjs` | calls 161、diffs 0、PASS | 40 ms |
| `node tests/mixer_diff.mjs` | calls 57、diffs 0、PASS (PY-115 の回帰) | 39 ms |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1651 ms |

同じ mock を読む `device_diff`・`ilmcp_diff`・`midi_path_diff`・`transport_diff`・`midi_bundled_device`・`midi_script` も rc 0 で PASS (wall は未計測)。

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `uiClosing` の既定値を `false` から `true` にすると、`node tests/ui_state_diff.mjs` は `AssertionError [ERR_ASSERTION]: ui 状態ゲッター差分 1 件` で rc 1 (FAIL)。元に戻すと calls 33・diffs 0・PASS (rc 0)。

C の警告: `gcc -fsyntax-only -Wall -Wextra provider/fl_engine.c` は 3 件の警告を出す。3 件とも `fl_engine.c:84` の `unused variable 'k'` で、`CH` マクロ (`Chan *k`) 由来の既存の警告。`provider/build.sh` は `-Wno-unused-variable` を付けている。main の同じファイル (`origin/main`) も 3 件で同数のため、本 PR が増やした警告は 0 件。`gen/fl_table.c` は警告 0 件。

コード差分 (測定 commit から PR HEAD まで、`tools/python` の .md 以外):

```
$ git diff fb0a1619 HEAD -- tools/python ':!*.md'
(空)
```

## 5. 保留 (残り 54 件・子 issue へ)

PE の handler VA だけを記録した。引数の意味・戻り値の範囲・作用先は未解析。#2980 は #3010 (PY-119) で 6 件を実装して閉じ、残り 12 件は #3005・#3006・#3007 に分けられた (`tools/python/REPORT_PY119.md` の保留表)。

| 子 issue | 関数 (fn VA) | 手掛かり |
|---|---|---|
| #3005 (PY-128) 読出し 4 件 (旧 #2980 の残り) | `getFocusedNodeCaption` 0xd6e470・`getFocusedNodeFileType` 0xd6e400・`getHintValue` 0xd6cb60・`getProgTitle` 0xd6c250 | `0x11f1a70`・`0x41c420` の引数規約 |
| #3006 (PY-129) setter・snap 4 件 (旧 #2980 の残り) | `setHintMsg` 0xd6c5b0・`setFocused` 0xd6ce50・`setSnapMode` 0xd6b7b0・`snapMode` 0xd6b8d0 | `0xd6fd10` → `0xd843d0` の書込み経路。`0xd84680` の意味 |
| #3007 (PY-130) bool setter・getVersion 4 件 (旧 #2980 の残り) | `setBrowserAutoHide` 0xd6ee00・`setStepEditMode` 0xd6f170・`setTimeDispMin` 0xd6ccb0・`getVersion` (ui) 0xd6c2f0 | 本体は未逆アセンブル。`getVersion` は mode で分岐する |
| #2981 (PY-150) 操作・キー・ジョグ・編集 27 件 | `jog` 0xd6a960・`jog2` 0xd6aa50・`strip` 0xd6ab40・`stripJog` 0xd6ac30・`stripHold` 0xd6ad20・`previous` 0xd6ae10・`next` 0xd6aed0・`moveJog` 0xd6af90・`up` 0xd6b080・`down` 0xd6b170・`left` 0xd6b260・`right` 0xd6b350・`horZoom` 0xd6b440・`verZoom` 0xd6b530・`snapOnOff` 0xd6b620・`cut` 0xd6b9c0・`copy` 0xd6ba80・`paste` 0xd6bb40・`insert` 0xd6bc00・`delete` 0xd6bcc0・`enter` 0xd6bd80・`escape` 0xd6be40・`yes` 0xd6bf00・`no` 0xd6bfc0・`nextWindow` 0xd6c080・`selectWindow` 0xd6c140・`scrollWindow` 0xd6d300 | 同形の 40〜41 命令。`call 0x415610`・`call 0xd6fd10` (object 取得) の後に、引数解析 (`call [0x15e1e58]`・書式 'i' など) を行い、`call 0xd84680` (作用) を呼ぶ。戻り値の int は `0x15e4280` へ。`jog` で確認 (`scrollWindow` だけ `0xd84680` を呼ばない)。PR #3018 (docs のみ) が PE 契約を解析中 |
| #2982 (PY-151) ブラウザ・メニュー・表示・ダイアログ 15 件 | `navigateBrowser` 0xd6dad0・`navigateBrowserMenu` 0xd6dad0 (同じ fn)・`navigateBrowserTabs` 0xd6ded0・`toggleBrowserNode` 0xd6dcd0・`selectBrowserMenuItem` 0xd6e170・`previewBrowserMenuItem` 0xd6e330・`closeAllMenu` 0xd6d7c0・`closeActivePopupMenu` 0xd6d8e0・`crDisplayRect` 0xd6e860・`miDisplayRect` 0xd6ea40・`miDisplayDockRect` 0xd6ebf0・`showNotification` 0xd6c8b0・`launchAudioEditor` 0xd6d540・`openEventEditor` 0xd6ef80・`showPicker` 0xd6f2e0 | 表示矩形は int 引数の順序と単位の同定が先 |

- 上の表の VA は `pe_handler_probe.py` の出力 (ui の PyMethodDef 範囲 0x151b2xx〜0x151bbxx) を正とする。`left`・`right` の 2 件の probe 出力は別モジュールの同名エントリも含むため、ui 側の entry だけを採った。
- `0xd81740` は呼出しではなく、`mov rdx, [rip+...]` で読む data 参照 (jog など)。#2981 では、`0xd84680` の作用先と、引数解析の slot `0x15e1e58` の役割を先に同定する。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 9 件の値は既定値の仮置き (未実測) | 実機と値が違う可能性。下流の値を信用しない | 起票なし (未解決の追跡のみ)。setter の所在: `getTimeDispMin`・`getStepEditMode`・`isBrowserAutoHide` は #3007 (`setTimeDispMin`・`setStepEditMode`・`setBrowserAutoHide`)、`getSnapMode` は #3006 (`setSnapMode`) |
| `isClosing`・`isMetronomeEnabled`・`isPrecountEnabled`・`isStartOnInputEnabled`・`isLoopRecEnabled` の setter が無い | 読み書きの対応を確かめられず、値は仮置きのまま | 起票なし (未解決の追跡のみ)。どの open 子 issue にも入っていない |
| 状態 slot の意味 (`0x15e1890`・`0x15e1e40`・`0x15e4ea0`・`0x15e2eb8`・`0x15e4b10`・`0x15e41f8`) | setter 実装時に読み書きの対応を確かめる必要 | `0x15e1e40`・`0x15e2eb8`・`0x15e4b10` は #3007、`0x15e41f8` は #3006。`0x15e1890`・`0x15e4ea0` は起票先なし |
| 変換 slot `0x15e4280` の先の関数 (bool と int の区別) | 戻り型は stub に従った | 起票なし (PY-87 からの持越し。PE の同定作業のみ) |
| 残り 54 件 (未実装 334 件のうち ui) | ui の未実装が 54 件残る | #3005 (4)・#3006 (4)・#3007 (4)・#2981 (27)・#2982 (15) |
