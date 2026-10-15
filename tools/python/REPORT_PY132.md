# tools/python REPORT: PY-132 ui のブラウザノード・メニュー項目 3 件 (toggleBrowserNode・selectBrowserMenuItem・previewBrowserMenuItem) の PE 確定と C provider 実装 (#3013, 親 #2982)

> 正本: `REPORT_PY121_2982.md` (3 件の出自と保留理由)・`REPORT_PY125.md` (dispatch `0xd843d0` の out の写し方と述語 P・-2 の扱い)・`REPORT_PY193.md` (`0xbd68e0` の通知)。本付録は PY-132 の実測のみ。
> 既知類型との関係: 該当なし (PE の逆アセンブルの読みだけ。lift・IR pass は行っていない。`docs/DEFECTS.md` の類型は適用しない)。

## 結論

- 3 件の PyArg 書式・既定値・戻り値 (None) と、共通の dispatch 呼出し形を PE で確定した。
- `toggleBrowserNode` は、値 -1 / 0 / 1 で作用先の分岐が 3 通りに分かれることまで確定した (`0xa89690` → `0xa26190`・`0xa07d00(0)`・`0xa07d00(1)`)。
- mock と C に 3 件を実装し、差分は 0 (`tests/ui_browser_diff.mjs`)。**作用は未モデル**: toggle は要求された分岐 (`browserOp`) だけを残す。ノードが実際に開閉するかは未確定。select・preview の作用 (キー送出 `0xfdd2c0`) も未確定。
- `provider_check`: 実装 155 → 158、未実装 280 → 277。

## PE 根拠 (block00031_PE.bin・VA)

| 関数 | entry | fn | flags | 引数の書式 | 作用の callback | 作用先 | 戻り |
|---|---|---|---|---|---|---|---|
| `ui.toggleBrowserNode` | 0x151b9a8 | 0xd6dcd0 | 1 | `\|i` (既定 -1: `mov dword [rbp+0x9c],0xffffffff` 0xd6dd04) | 0xd6dc70 | `0xa89690` | None |
| `ui.selectBrowserMenuItem` | 0x151ba08 | 0xd6e170 | 4 (NOARGS) | なし | 0xd6e060 | `0xfdd2c0` (鍵 0x5b・0x50) | None |
| `ui.previewBrowserMenuItem` | 0x151ba28 | 0xd6e330 | 4 (NOARGS) | なし | 0xd6e240 | `0xfdd2c0` (鍵 0x50)・`0x107eb10`・`0xbd68e0` | None |

共通の骨格 (3 件とも):

1. `0xd6fd10` (`call [rip+0x87089d]`・rcx は self のまま) の戻りを `obj = *ret` とする。
2. `call 0xd843d0(rcx=obj, rdx=&out, r8=callback, r9=0, arg5=値 (toggle のみ・他は 0), arg11 flag=1)`。callback は `lea r8` の先 (表の callback 列)。
3. 戻りは `0xd82c20(out[0])`。status 0 の経路は None (REPORT_PY125 の確定と同じ)。
4. toggle の PyArg 失敗 (eax ≤ 0・`jle 0xd6dd8f`) は `0xd82c20(eax)` へ直行。

callback の共通の述語: `G = [0x15e4790]`・`P = call [[[G]+8]+0x98]`。P 偽は `job+0x60 = -2` のまま返る (効果なし)。P 真は `job+0x60 = 0` にして効果を行う (REPORT_PY125 の clearLog・dumpScoreLog と同じ G・同じ `[+0x98]` 形。同一述語かは未照合)。

### toggleBrowserNode (callback 0xd6dc70)

- P 真で `job+0x10 = -1`、`0xa89690(*[0x15e4410], value)` (value = `job+0x18` = 引数。既定 -1)、続けて `job+0x60 = 0`。
- `0xa89690` の分岐 (実測): `node = call [[obj]+0x100](obj, dl=1)`。node == 0 なら何もしない (0xa896ac)。以後は value で分岐:
  - value == -1 → `0xa26190(*(obj+0x198), node)` (0xa896c5〜0xa896cf)
  - value == 0 → `0xa07d00(*(obj+0x198), node, r8=0)` (0xa896d6〜0xa896e3)
  - value == 1 → `0xa07d00(*(obj+0x198), node, r8=1)` (0xa896ea〜0xa896f7)
  - それ以外 → 何もしない (0xa896fc)

### selectBrowserMenuItem (callback 0xd6e060)

P 真の後、globals `A`〜`H` (`[rip+...]` の指す値) で分岐する:

- `A == 0` → 終了 (0xd6e0a5)。
- `B == 0` → 鍵 0x5b を送る (0xd6e0e2)。
- `B ≠ 0` かつ `C ≠ 0` かつ `D ≠ [[E]+0xec]` → 鍵 0x5b を送る。
- それ以外 (`C == 0` または `D == [[E]+0xec]`) → `F == 0` なら終了 (0xd6e152)。`[G] ≠ [[H]+0xec]` なら終了。一致なら鍵 0x50 を送る (0xd6e130)。

### previewBrowserMenuItem (callback 0xd6e240)

P 真の後:

- `A == 0` → 終了。`B ≠ 0` → 鍵 0x50 を送って終了 (0xd6e298)。`C == 0` → 終了。
- `Z = call [[X]+0x100](X, dl=0)` (`X = [[rip+0x876140]]`)。`Z == 0` → 終了。
- `call [[Z+0x48]+0x70]` が真 → `0x107eb10(…, edx=0x2b, r8=0)` (0xd6e2f7)。偽 → `0xbd68e0(5, 0)` (0xd6e310)。

鍵の送出は `0xfdd2c0(ecx=鍵, edx=1, r8b=フラグ byte, r9d=0xf, [rsp+0x20]=0)`。`0xfdd2c0` の本体 (0xfdd2c0〜0xfde862) は大半が未読。`ecx` で 0x0a・0x0d・0x14・0x15・0x1e・0x1f・0x28・0x32・0x3b などに分岐する。鍵 0x5b と 0x50 の意味は未確定。

## 確定と保留

**確定**:

1. 3 件の書式と既定値: `toggleBrowserNode` は `|i` (既定 -1)、他 2 件は NOARGS。flags は probe の 1・4・4 と一致する。
2. 戻り値は None (`0xd82c20(out[0])` の status 0 経路。P 真を仮定)。
3. `toggleBrowserNode` の値 -1 / 0 / 1 の分岐と呼出し先 (`0xa26190`・`0xa07d00` の flag 0・1)。他の値は分岐なし。

**保留** (確定に必要な情報):

- `0xa26190`・`0xa07d00` の本体 (子 #3724 [PY-240]): 開閉の結果と、ノード状態の所在。`0xa89690` の `[obj+0x100](obj, 1)` の戻り (node の意味) も未読。node が 0 のときは何もしないことだけ確定している。
- select・preview の作用 (子 #3726 [PY-241]): `0xfdd2c0` の本体、globals `A`〜`H` の初期値 (実行時値)、`0x107eb10` と `0xbd68e0(5,0)` の効果。`#3719` (ui.snapMode。`0xfdd2c0` の id 0x31 を扱う) の結果を参照してよい。
- -2 の経路 (P 偽・dispatch の gate `0xd84f30` 偽): 報告ゲートの実行時値に依存 (REPORT_PY125 と同じ)。mock・C は P 真を仮定する。

## 実装 (mock と C の差分 0)

- `toggleBrowserNode`: 引数 0 から 1 個 (超過は code 5)。型違い (文字列・小数) は code 5。既定 -1。読出し口 `fl_engine_browser_op()` (mock は `st.browserOp`) に分岐を残す: 0 なし・1 切替 (-1)・2 閉じる (0)・3 開く (1)。ノードの状態は持たない。
- `selectBrowserMenuItem`・`previewBrowserMenuItem`: NOARGS (引数ありは code 5)。None を返す。作用は未モデル (推測での実装はしない)。
- 変更箇所: `host/fl_mock.mjs`・`host/fl_provider.mjs`・`provider/fl_engine.c`・`provider/build.sh` (EXPORTED_FUNCTIONS)・`tests/provider_check.mjs` (集合 `pe132`・件数)・`tests/ui_browser_diff.mjs` (新規)。

## 検証

測定 commit: `2b72baa3c` (コードを変えた最後の commit: `feat(python): implement ui browser node and menu item functions (PY-132, refs #3013)`)。以後の commit はこの REPORT (md のみ)。
環境: runner・`uptime` は `load average: 0.38, 1.14, 0.70` (03:30:12)。`FL_WIN64_DIR` は `$RUNNER_TEMP/fl-win64` (fl-win64 を `tar --zstd -xf` で全展開、11.3 秒)。emsdk は `[EMSDK]` (`docs/REFERENCES.md`、pin 済みの既存インストール) を使った。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 (ハンドラ 158・`flprov.wasm` 64,275 B) | 1.746 秒 |
| `bash fetch_inputs.sh` | rc 0 | 0.526 秒 |
| `bash build_cpython_wasm.sh` | rc 0 (python.wasm 5,927,852 B) | 計測せず |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 (`flpy.wasm` 5,924,680 B) | 計測せず |
| `node tests/ui_browser_diff.mjs` | PASS (正常 8・異常 5・diffs 0・browserOp 3) | 0.039 秒 |
| `node tests/ui_display_diff.mjs` | PASS (正常 12・異常 11・diffs 0・displayTime 2000) | 0.039 秒 |
| `node tests/ui_diff.mjs` | PASS (calls 17・diffs 0・範囲外既知差分 3) | 0.043 秒 |
| `node tests/ui_state_diff.mjs` | PASS (calls 33・diffs 0) | 0.039 秒 |
| `node tests/screen_diff.mjs` | PASS (calls 32・diffs 0) | 0.040 秒 |
| `node tests/general_diff.mjs` | PASS (calls 41・diffs 0) | 0.041 秒 |
| `node tests/mixer_diff.mjs` | PASS (calls 62・diffs 0) | 0.040 秒 |
| `node tests/channels_diff.mjs` | PASS (calls 214・grid 1200・diffs 0) | 0.051 秒 |
| `node tests/transport_diff.mjs` | PASS (calls 7・diffs 0) | 0.039 秒 |
| `node tests/midi_path_diff.mjs` | PASS (cases 30・diffs 0) | 0.042 秒 |
| `node tests/ilmcp_diff.mjs` | PASS (calls 32・state_checks 9・diffs 0) | 0.048 秒 |
| `node tests/arrangement_diff.mjs` | PASS (calls 25・diffs 0) | 0.038 秒 |
| `node tests/device_diff.mjs` | PASS (calls 8・rejects 4・midi_out 5・diffs 0) | 0.038 秒 |
| `python3 tests/kwsig_check.py` | OK | 0.040 秒 |
| `node tests/provider_check.mjs` | PASS (functions 435・実装 158・未実装 277・MCP 静的 60) | 0.259 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・host_calls 37,425・callback 往復 true | 1.466 秒 |

ネガティブコントロール: `host/fl_mock.mjs` の toggle の分岐を `v === 1 ? 3` から `v === 1 ? 2` に変えると、`node tests/ui_browser_diff.mjs` は rc 1 (AssertionError・差分 8 件)。元に戻すと PASS。

## 件数の変化

main 75c48ab21 基準: 実装 155 → 158 (+3)、未実装 280 → 277 (-3)。`pe132` (3 件) を判定に入れた。

## main 取り込み後の再測定 (競合解消)

main を 3 回取り込んだ。`8c23860cd` の取り込みでは競合 3 件 (`provider/build.sh`・`provider/fl_engine.c`・`tests/provider_check.mjs`)、`1ccf20c6a` の取り込みでは競合 2 件 (`docs/DOC_MAP.md`・`tests/provider_check.mjs`) が出た。解消は両側の追加を残す方針 (`provider_check` の期待値だけ main の数に本 PR の +3 を足した)。`71e64d058` の取り込みは競合なし (変更は `analysis/py137_saveundo_record.py`・REPORT_PY124・DOC_MAP で、provider と本節の検証には入らない)。測定 commit: `359cf28af` (main `71e64d058` を取り込んだ merge。コードを変えた最後の commit)。以後の HEAD のコード差分 `git diff 359cf28af HEAD -- tools/python ':!*.md'` は 0 行。

基準 main `71e64d058`: 実装 165 → 168 (+3)、未実装 270 → 267 (-3)。

| コマンド | 結果 (359cf28af) |
|---|---|
| `bash provider/build.sh` (emsdk は `[EMSDK]` の pin 6.0.12 を上流から取得) | rc 0・ハンドラ 168 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` (CPython wasm は `build_cpython_wasm.sh` で再ビルド済み) | rc 0・5.98 s |
| `node tests/provider_check.mjs` | PASS (関数 435・実装 168・未実装 267・mcp 静的 60) |
| `node tests/ui_browser_diff.mjs` | PASS (正常 8・異常 5・diffs 0・browserOp 3) |
| `node tests/ui_display_diff.mjs` と ui_state (58 calls)・ui・general・mixer・channels・transport・midi_path・ilmcp・arrangement・device の各 diff | 全て PASS (diffs 0) |
| step_item・note_enum・patterns・patterns_group・playlist・launchmap の各 diff | 全て PASS (diffs 0) |
| `python3 tests/kwsig_check.py` | OK |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・host_calls 37,425・2.14 s |

実行後の uptime load average: 0.84 / 0.94 / 0.68 (1・5・15 分)。ネガティブコントロールは取り込み前の測定 (`2b72baa3c`) のままで、本節では再実行していない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xa26190`・`0xa07d00` の本体と `0xa89690` の node 戻り | toggle の開閉が状態に反映されない (分岐の要求だけ残す) | 子 #3724 [PY-240] |
| `0xfdd2c0` の本体と鍵 0x5b・0x50、globals A〜H の意味 | select・preview の作用が未実装 (None を返すだけ) | 子 #3726 [PY-241] |
| `0x107eb10`・`0xbd68e0(5,0)` の効果 | preview の分岐先の作用が未実装 | 子 #3726 [PY-241] |
| P 偽・dispatch gate 偽の -2 経路 | 実行時に RuntimeError か None に分かれる (mock・C は P 真を仮定) | REPORT_PY125 の未解決 (子 #3045) |
