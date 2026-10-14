# tools/python REPORT: PY-95 ui 状態ゲッター 9 件の PE 確定と C provider 実装 (#2831, 親 #2738, 子 #2980・#2981・#2982)

既知類型との関係: 該当なし (lift 作業ではない。flapi 関数の PE 確定と provider 実装)。前段: `tools/python/REPORT_PY87.md` (general 4 件・同じ手順)。

## 結論

- ui の未実装 69 関数のうち **9 件** (`isClosing`・`getTimeDispMin`・`isMetronomeEnabled`・`isPrecountEnabled`・`isStartOnInputEnabled`・`isLoopRecEnabled`・`getStepEditMode`・`isBrowserAutoHide`・`getSnapMode`) を PE で確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/ui_state_diff.mjs` 18 呼出し)。
- 9 件はいずれも「状態 1 つを読んで変換 slot `0x15e4280` に渡すだけ」で、副作用・分岐は無い。bool 8 件と int 1 件 (`getSnapMode`)。型は公開 stub の `returns` に従う。
- **値は未確定 (仮置き)**。全て既定値 (`false` / `0`) の固定で、実機の値は未実測。setter が未実装のため、現状の C provider は既定値のみを返す。
- `isMetronomeEnabled` / `isPrecountEnabled` は、PY-87 の `general.getUseMetronome` / `general.getPrecount` と同じ状態 (同じ slot) を読む。C では同じ変数 (`use_metronome`・`precount`) を参照する。
- 残り **60 件** は子 issue 3 件に分けた (上限 3 件): 状態・フォーカス・文字列・setter 18 件 = #2980 (PY-119) / 操作・キー・ジョグ・編集 27 件 = #2981 (PY-120) / ブラウザ・メニュー・表示・ダイアログ 15 件 = #2982 (PY-121)。各 handler の VA は §5。

## 1. 手段

- 素材: `fl-win64.tar.zst` から `extracted/block00031_PE.bin` (関数探索) と DATA block 4 件 (`block25159`・`block24429`・`block24430`・`block24618`、`fetch_inputs.sh` 用) を `$RUNNER_TEMP/fl-win64/extracted/` に展開。`toolchain-emsdk` は展開せず、runner 既存の `[EMSDK]` (`docs/REFERENCES.md`。emcc 6.0.12、`tools/m1/flags.sh` の pin) を使った。
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
- 9 件の読み先 (slot の指す状態) の意味 (例: `0x15e1890` が「閉じている」の状態か) は未確定。値の意味は仮置きで、setter (PY-119・PY-120 の範囲) の同定で確かめる。

## 3. 実装

- `host/fl_mock.mjs`: state に `uiClosing` ほか 7 項目を追加 (既定 `false` / `0`)、`ui.*` 9 件を定義 (`arity(a, 0, 0)`)。`isMetronomeEnabled` / `isPrecountEnabled` は既存の `useMetronome` / `precount` を読む。
- `provider/fl_engine.c`: 静的変数 7 件 (`ui_closing`・`ui_time_disp_min`・`ui_start_on_input`・`ui_loop_rec`・`ui_step_edit`・`ui_browser_auto_hide`・`ui_snap_mode`) を `fl_engine_reset` で 0 に初期化。`FL_H(ui, ...)` 9 件を `NARGS(0, 0)` 付きで定義。
- `tests/provider_check.mjs`: `pe95` の集合を追加。実装 83 → 92、未実装 352 → 343 (total 435 は不変)。
- `tests/ui_state_diff.mjs` (新規): 9 件の既定値呼出し (9) と引数過多 (9) の計 18 呼出しを mock と C で照合。

## 4. 検証

測定 commit: `b0a8a46d` (コードを変えた最後の commit。`origin/main` (`314e2e94`) を取り込んだ merge。衝突は無し。本 PR のコード commit は `07ff6f89`)。測定は同 commit のクリーンな作業ツリーで、`provider/build.sh` を再実行してから行った (`git status --porcelain` は空)。

環境: runner 4 core、測定開始時の load average 0.31 (1 分平均)、終了時 0.44。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` (再ビルド) | rc 0・ハンドラ 92 | — |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` (再ビルド) | rc 0 | — |
| `node tests/provider_check.mjs` | PASS (435 / 実装 92 / 未実装 343 / MCP 静的 60) | 0.36 s |
| `node tests/general_diff.mjs` | calls 9、diffs 0、PASS (PY-87 の回帰) | 0.05 s |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS (既存) | 0.05 s |
| `node tests/ui_state_diff.mjs` | calls 18、diffs 0、PASS | 0.05 s |
| `node tests/channels_diff.mjs` | calls 123、diffs 0、PASS (回帰。main 取り込みで呼出しが 1 件増えた) | 0.06 s |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 2.32 s |

前提の生成物 (測定前に作成・gitignore): `fetch_inputs.sh` (rc 0)・`build_cpython_wasm.sh` (rc 0、4 分 08 秒、`07ff6f89` の測定時)。

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `uiClosing` の既定値を `false` から `true` にすると、`node tests/ui_state_diff.mjs` は `AssertionError [ERR_ASSERTION]: ui 状態ゲッター差分 1 件` で rc 1 (FAIL)。元に戻すと calls 18・diffs 0・PASS (rc 0)。

コード差分 (測定 commit から PR HEAD まで、`tools/python` の .md 以外):

```
$ git diff b0a8a46d HEAD -- tools/python ':!*.md'
(空)
```

PY-87 の REPORT と同じく、本 REPORT を含む md のみの commit を後から足しても、この出力は 0 行のまま。

## 5. 保留 (残り 60 件・子 issue へ)

PE の handler VA だけを記録した。引数の意味・戻り値の範囲・作用先は未解析。

| 子 issue | 関数 (fn VA) | 手掛かり |
|---|---|---|
| #2980 (PY-119) 状態・フォーカス・文字列・setter 18 件 | `getFocused` 0xd6cd80・`getFocusedFormCaption` 0xd6c9d0・`getFocusedFormID` 0xd6ca80・`getFocusedNodeCaption` 0xd6e470・`getFocusedNodeFileType` 0xd6e400・`getFocusedPluginName` 0xd6cab0・`getHintMsg` 0xd6c4c0・`getHintValue` 0xd6cb60・`getProgTitle` 0xd6c250・`getVersion`(ui) 0xd6c2f0・`isInPopupMenu` 0xd6d6b0・`setHintMsg` 0xd6c5b0・`setSnapMode` 0xd6b7b0・`snapMode` 0xd6b8d0・`setStepEditMode` 0xd6f170・`setTimeDispMin` 0xd6ccb0・`setBrowserAutoHide` 0xd6ee00・`setFocused` 0xd6ce50 | 文字列 5 件は `0x41c420`・`0x414000`・文字列 slot `0x15e3d50` を通る。`getFocusedFormID`・`getFocused` は object の仮想関数を呼ぶ。`isInPopupMenu` は `call 0x728f40` の戻りを変換 |
| #2981 (PY-120) 操作・キー・ジョグ・編集 27 件 | `jog` 0xd6a960・`jog2` 0xd6aa50・`strip` 0xd6ab40・`stripJog` 0xd6ac30・`stripHold` 0xd6ad20・`previous` 0xd6ae10・`next` 0xd6aed0・`moveJog` 0xd6af90・`up` 0xd6b080・`down` 0xd6b170・`left` 0xd6b260・`right` 0xd6b350・`horZoom` 0xd6b440・`verZoom` 0xd6b530・`snapOnOff` 0xd6b620・`cut` 0xd6b9c0・`copy` 0xd6ba80・`paste` 0xd6bb40・`insert` 0xd6bc00・`delete` 0xd6bcc0・`enter` 0xd6bd80・`escape` 0xd6be40・`yes` 0xd6bf00・`no` 0xd6bfc0・`nextWindow` 0xd6c080・`selectWindow` 0xd6c140・`scrollWindow` 0xd6d300 | 同形の 40〜41 命令。`call 0x415610`・`call 0xd6fd10` (object 取得) の後に、引数解析 (`call [0x15e1e58]`・書式 'i' など) を行い、`call 0xd84680` (作用) を呼ぶ。戻り値の int は `0x15e4280` へ。`jog` で確認 (`scrollWindow` だけ `0xd84680` を呼ばない) |
| #2982 (PY-121) ブラウザ・メニュー・表示・ダイアログ 15 件 | `navigateBrowser` 0xd6dad0・`navigateBrowserMenu` 0xd6dad0 (同じ fn)・`navigateBrowserTabs` 0xd6ded0・`toggleBrowserNode` 0xd6dcd0・`selectBrowserMenuItem` 0xd6e170・`previewBrowserMenuItem` 0xd6e330・`closeAllMenu` 0xd6d7c0・`closeActivePopupMenu` 0xd6d8e0・`crDisplayRect` 0xd6e860・`miDisplayRect` 0xd6ea40・`miDisplayDockRect` 0xd6ebf0・`showNotification` 0xd6c8b0・`launchAudioEditor` 0xd6d540・`openEventEditor` 0xd6ef80・`showPicker` 0xd6f2e0 | 表示矩形は int 引数の順序と単位の同定が先 |

- 上の表の VA は `pe_handler_probe.py` の出力 (ui の PyMethodDef 範囲 0x151b2xx〜0x151bbxx) を正とする。`left`・`right` の 2 件の probe 出力は別モジュールの同名エントリも含むため、ui 側の entry だけを採った。
- `0xd81740` は呼出しではなく、`mov rdx, [rip+...]` で読む data 参照 (jog など)。PY-120 では、`0xd84680` の作用先と、引数解析の slot `0x15e1e58` の役割を先に同定する。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 9 件の値は既定値の仮置き (未実測) | 実機と値が違う可能性。下流の値を信用しない | 起票なし (未解決の追跡のみ)。実機値は setter と合わせて PY-119・PY-120 で確かめる |
| 状態 slot の意味 (`0x15e1890`・`0x15e1e40`・`0x15e4ea0`・`0x15e2eb8`・`0x15e4b10`・`0x15e41f8` が何の状態か) | setter 実装時に読み書きの対応を確かめる必要 | #2980 (PY-119)・#2981 (PY-120) |
| 変換 slot `0x15e4280` の先の関数 (bool と int の区別) | 戻り型は stub に従った | 起票なし (PY-87 からの持越し。PE の同定作業のみ) |
| 残り 60 件 | 未実装 (343 件のうち) | #2980 (18)・#2981 (27)・#2982 (15) |
