# tools/python REPORT: PY-121 ui の表示・メニュー 15 関数のうち 6 件の PE 確定と C provider 実装 (#2982, 親 #2831)

> 正本: `tools/python/REPORT_PY87.md` (PY-87 の付録様式)。親 #2831 と本 issue が参照する `REPORT_PY95.md` は、本 run の checkout と全 ref に存在しなかったため、本付録の表を一次資料とする。PE の一次データは `tools/python/analysis/flapi/pe_handler_probe.py` の出力。

## 結論

- 対象 15 件のうち **6 件** を実装した: 表示矩形 3 件 (`crDisplayRect` / `miDisplayRect` / `miDisplayDockRect`)・通知 1 件 (`showNotification`)・メニューを閉じる 2 件 (`closeAllMenu` / `closeActivePopupMenu`)。mock と C の差分は 0 (`tests/ui_display_diff.mjs`: 正常 12 呼出し・異常 11 呼出し)。
- **表示矩形 3 件の確定範囲**は PyArg 書式 (引数の個数と型) と、時間引数の頭打ち (`0x7d0` = 2000) だけ。表示の作用先 (UI) は未モデル。Python から観測できるのは引数の検査と、頭打ち後の値 (`fl_engine_display_time`) のみ。
- 残り **9 件**は確定していない。理由は作用先の逆アセンブル (共通の呼出し口 `0xd843d0`・変換 `0xd82c20` の同定) が未了のため。子 issue 3 件 (PY-131 (#3012)・PY-132 (#3013)・PY-133 (#3014)) に分けた。
- 題名の `[PY-121]` は #2985 (screen 28 件) と重複している。本 run では新規採番せず、本 issue の番号 (#2982) の題名を変えなかった。整理は PM の判断。

## PE 根拠 (15 件)

PE: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <名前...>` (`block00031_PE.bin`)。entry は PyMethodDef のエントリ VA、fn は関数先頭 VA、fmt は `PyArg_ParseTuple` の書式 (関数内の `lea rdx,[rip+X]` が指す文字列)。stub は `analysis/flapi/flapi_table.json` の `sig`。

| 関数 | entry | fn | flags | PyArg 書式 (PE) | stub の引数 | stub の戻り | 状態 |
|---|---|---|---|---|---|---|---|
| `ui.showNotification` | 0x151b688 | 0xd6c8b0 | 1 | `i` | notificationId: int | None (null) | **実装** |
| `ui.launchAudioEditor` | 0x151b828 | 0xd6d540 | 1 | `isiss` | reuse, filename, index, preset, presetGUID | int | 保留 (子 PY-133 (#3014)) |
| `ui.closeAllMenu` | 0x151b868 | 0xd6d7c0 | 4 | NOARGS | なし | None | **実装** |
| `ui.closeActivePopupMenu` | 0x151b888 | 0xd6d8e0 | 4 | NOARGS | なし | None | **実装** |
| `ui.crDisplayRect` | 0x151b928 | 0xd6e860 | 1 | `iiiii\|i` | left, top, right, bottom, duration, flags=0 | None | **実装** |
| `ui.miDisplayRect` | 0x151b948 | 0xd6ea40 | 1 | `iii\|i` | start, end, duration, flags=0 | None | **実装** |
| `ui.miDisplayDockRect` | 0x151b968 | 0xd6ebf0 | 1 | `iiii` | start, length, dock_side, time | None | **実装** |
| `ui.navigateBrowser` | 0x151b988 | 0xd6dad0 | 1 | `ii` | direction, shiftHeld (bool) | str | 保留 (子 PY-131 (#3012)) |
| `ui.toggleBrowserNode` | 0x151b9a8 | 0xd6dcd0 | 1 | `\|i` | value=-1 | None | 保留 (子 PY-132 (#3013)) |
| `ui.navigateBrowserTabs` | 0x151b9c8 | 0xd6ded0 | 1 | `i` | direction | str | 保留 (子 PY-131 (#3012)) |
| `ui.navigateBrowserMenu` | 0x151b9e8 | 0xd6dad0 (navigateBrowser と共有) | 1 | `ii` | direction, shiftHeld (bool) | str | 保留 (子 PY-131 (#3012)) |
| `ui.selectBrowserMenuItem` | 0x151ba08 | 0xd6e170 | 4 | NOARGS | なし | None | 保留 (子 PY-132 (#3013)) |
| `ui.previewBrowserMenuItem` | 0x151ba28 | 0xd6e330 | 4 | NOARGS | なし | None | 保留 (子 PY-132 (#3013)) |
| `ui.openEventEditor` | 0x151bac8 | 0xd6ef80 | 1 | `Ii\|i` | eventId, mode, newWindow=False | int | 保留 (子 PY-133 (#3014)) |
| `ui.showPicker` | 0x151bb28 | 0xd6f2e0 | 1 | `i\|i` | stub 無し (new_vs_stubs) | 未確定 | 保留 (子 PY-133 (#3014)) |

- `navigateBrowser` と `navigateBrowserMenu` は同じ fn 0xd6dad0 を指す (entry は別)。親 issue の手掛かりどおり。
- `closeAllMenu` と `closeActivePopupMenu` は同形 (fn の先頭から 35 命令程度で、`0xd843d0`・`0xd82c20`・`0x415c30` を呼ぶ)。親 issue の手掛かりどおり。

## 実装した 6 件の根拠

1. **PyArg 書式 = 引数の個数と型**: 上の表の fmt。stub の必須・既定値 (`duration` 必須・`flags=0` 既定) と一致する (`crDisplayRect`: 必須 5 + 任意 1 = `iiiii|i`)。C と mock は `NARGS` / `argI` で同じ個数検査をし、型違い (文字列・小数) は code 5 (`WRONG`)。
2. **時間引数の頭打ち**: 3 関数とも `movsxd rax,[時間引数]; cmp rax,0x7d0; jle …; mov eax,0x7d0` の形。時間引数は PyArg の out ポインタ順で決まる。
   - `crDisplayRect`: out ポインタは `r8/r9` と `[rsp+0x20..0x38]` の順で arg0..arg5。頭打ちされるのは `[rbp+0x9c]` = arg4 (duration)。`flags` の既定 0 は `mov dword [rbp+0x98],0`。
   - `miDisplayRect`: 頭打ちされるのは `[rbp+0xa4]` = arg2 (duration)。頭打ち後の値は `mov [rsp+0x30],rax` で作用先の 3 番目の引数へ渡る。
   - `miDisplayDockRect`: 頭打ちされるのは `[rbp+0xa4]` = arg3 (time)。頭打ち後の値は `mov [rsp+0x38],rax` で 4 番目の引数へ渡る。
   - 負の値は頭打ちしない (`cmp` の後 `jle` で素通し)。C の `v > DISP_MAX ? DISP_MAX : v` と mock の `Math.min(v, 0x7d0)` は、この素通しの規則を再現する。
3. **no-op の 3 件** (`showNotification`・`closeAllMenu`・`closeActivePopupMenu`): PE に引数の範囲検査は無い (`showNotification` は PyArg の成否判定 `test rax,rax; jle` のみ)。作用は未モデル。mock と C は個数・型だけ検査し、`None` を返す。
4. **戻り値 None**: stub の `returns` に従う。PE の末尾は `0xd82c20` (結果 → PyObject と推定、同定は未了) を通る。`returns` の根拠は stub のみ。

## 保留 9 件 (未確定の理由)

- `navigateBrowser` / `navigateBrowserMenu` / `navigateBrowserTabs` (子 PY-131 (#3012)): 戻り値が `str` (stub)。0xd6dad0 の本体は `0xd843d0` (作用先の呼出し口) の戻り値を `[rbp+0x88]` で判定して分岐する。作用先の中身 (ブラウザの選択名の取得元) が未同定。
- `toggleBrowserNode` / `selectBrowserMenuItem` / `previewBrowserMenuItem` (子 PY-132 (#3013)): `toggleBrowserNode` は `\|i` 書式で、値 `-1` (既定) は PE の初期化 `mov dword [rbp+0x9c],0xffffffff` で確認済み。ただし作用先の呼出しが `0xd843d0` の 1 段で、ノードの状態変化の所在が未同定。`selectBrowserMenuItem` / `previewBrowserMenuItem` は `closeAllMenu` と同じ `0xd843d0`・`0xd82c20` の呼出しに加えて、`call [rax+0x98]`・`call [rax+0x100]`・`call [rax+0x70]` を含む別の分岐がある (同形ではない。probe の 260 命令の範囲で確認)。
- `launchAudioEditor` / `openEventEditor` / `showPicker` (子 PY-133 (#3014)): 戻り値が int (2 件) か未確定 (`showPicker` は stub 無し)。`launchAudioEditor` は 5 引数の書式 `isiss` で、`filename`・`preset`・`presetGUID` は文字列の参照先を伴う。作用先 (エディタの起動経路) が未同定。

## 検証

測定 commit: `7f7572f4` (main 取り込みの merge commit。コードを変えた最後の commit)。`git diff 7f7572f4 HEAD -- tools/python ':!*.md'` は空 (本節の追加は md のみ)。取り込み前の測定は `fcfb290c` (PR 実装 commit)。
環境: runner 4 core、再測定時の `uptime` は `load average: 0.80, 1.31, 0.73` (21:21:38)。`FL_WIN64_DIR` は `$RUNNER_TEMP/fl-win64` (`fl-win64.tar.zst` を全展開)。emsdk は上流 `emscripten-core/emsdk` から 6.0.12 を `$RUNNER_TEMP/tc/emsdk` に入れ、`/opt/emsdk` に symlink (scripts の既定 `[EMSDK]` に合わせた)。

前提の生成物 (gitignore・取り込み後に再生成): `bash fetch_inputs.sh` (rc 0)・`bash build_cpython_wasm.sh` (rc 0、2 分 42 秒)・`FLPY_SKIP_TABLE=1 bash build_flpy.sh` (rc 0、6.2 秒)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 (`dist/flprov.wasm` 57,922 B・ハンドラ 90) | 0.966 秒 |
| `node tests/ui_display_diff.mjs` | PASS (正常 12・異常 11・diffs 0・displayTime 2000) | 0.049 秒 |
| `node tests/ui_diff.mjs` | PASS (calls 17・diffs 0・範囲外既知差分 3) | 0.048 秒 |
| `node tests/general_diff.mjs` | PASS (calls 9・diffs 0) | 0.049 秒 |
| `node tests/device_diff.mjs` | PASS (calls 8・diffs 0) | 0.048 秒 |
| `node tests/provider_check.mjs` | PASS (functions 435 / 実装 90 / 未実装 345 / MCP 静的 60) | 0.369 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 2.327 秒 |

取り込み後に追加で通した main 側変更の回帰 (wall 未計測): `mixer_diff.mjs` PASS (calls 57・diffs 0)・`channels_diff.mjs` PASS (calls 123・diffs 0)・`transport_diff.mjs` PASS (calls 7・diffs 0)・`midi_path_diff.mjs` PASS (cases 30・diffs 0)・`ilmcp_diff.mjs` PASS (calls 32・diffs 0)・`kwsig_check.py` OK。

件数の変化: 取り込み前 (`fcfb290c`) は 実装 83 → 89 (+6・PR)、未実装 352 → 346。取り込み後は main の PY-115 (`mixer.getTrackColor`・+1) を足して 実装 90 / 未実装 345。`provider_check.mjs` の期待値は両方を足した値に更新した (競合解消)。

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の時間引数の頭打ち値を `0x7d0` から `0x7cf` にすると、`node tests/ui_display_diff.mjs` は `ui 表示 差分 19 件` で rc 1 (FAIL)。元に戻すと PASS (rc 0)。比較は測定 commit `7f7572f4` で行った。

## 製品 KPI (起動・GUI に関わる PR の記載)

- FLEngine 起動の dispatch 数・通過 unit 数 (`tools/flelift/boot/REPORT.md`)・最初のウィンドウの有無: **動かしていない**。本 PR は provider の UI 関数 6 件の追加で、起動の経路 (`flelift`・`boot`) は変えていない。KPI は測定していない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 保留 3 件 (navigateBrowser・navigateBrowserMenu・navigateBrowserTabs) | 戻り値 `str` の意味が未確定。ブラウザ移動の Python 側の戻り値が未実装 | 子 issue PY-131 (#3012) |
| 保留 3 件 (toggleBrowserNode・selectBrowserMenuItem・previewBrowserMenuItem) | ブラウザノードの状態変化と、メニュー選択の作用先が未確定 | 子 issue PY-132 (#3013) |
| 保留 3 件 (launchAudioEditor・openEventEditor・showPicker) | エディタ起動の戻り値 (int) と、showPicker の stub 無し | 子 issue PY-133 (#3014) |
| 表示矩形 3 件の作用先が未モデル (頭打ち後の値のみ観測) | 表示の副作用 (選択矩形の位置) は Python から観測できない。C の `fl_engine_display_time` は検査用の読出し口で、FL 側の状態ではない | 本 PR の未解決表で扱う (子 issue は起票しない。表示の実測は PM 判断) |
| `0xd82c20` (結果 → PyObject) と `0xd843d0` (作用先の呼出し口) の同定が未了 | 戻り値 None と no-op の根拠は stub と書式に限られる | 子 issue PY-131 (#3012)・PY-132 (#3013)・PY-133 (#3014) の本文に含める |
| 題名 `[PY-121]` が #2985 と重複 | 検索・分類の混乱 | PM が Issue 整理時に正規化 (AGENTS.md §3) |
