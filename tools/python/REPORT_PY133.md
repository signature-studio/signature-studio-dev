# tools/python REPORT: PY-133 ui のエディタ起動・ピッカー 3 件の PE 確定と C provider 実装 (#3014, 親 #2982)

> 前段: `tools/python/REPORT_PY121_2982.md` (保留 3 件の出典。PR #3019 で merge 済み)。戻り値 None の根拠: `tools/python/REPORT_PY102.md` (`0xd82c20` の status 0 → None)。
> 既知類型との関係: 該当なし (PE の直接逆アセンブル。`docs/DEFECTS.md` の類型は対象外)。
> 同じ形の実装は `tools/python/REPORT_PY121_2982.md` (showNotification・closeAllMenu) と同じ扱い (作用は未モデル、個数・型の検査と戻り値だけ)。

## 結論

- 3 件の PyArg 書式・引数の出力先・dispatch への渡し方・戻り値の経路を PE (`block00031_PE.bin`) から VA 付きで確定した。
- **showPicker・openEventEditor は実装した** (mock と C の差分 0)。戻り値は PE の経路で None (stub の `openEventEditor` 戻り `int` とは食い違う。下の未解決)。作用先 (picker・エディタの起動) は未モデルの no-op。
- **launchAudioEditor は保留**。戻り値 int は callee `0x118a810` の戻り値で、その意味が未同定。値を mock/C に書くと silent miscompile になるため実装しない。子 issue #3734 (PY-242) に移した。
- 件数 (main 取り込み後の基準): 実装 162 → 164 (+2・`pe133`)、未実装 273 → 271。

## PE 根拠 (3 件)

PE: `FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi/pe_handler_probe.py launchAudioEditor openEventEditor showPicker` (`block00031_PE.bin`)。逆アセンブルは `analysis/flapi/pe_disasm.py <VA> <命令数>`。

| 関数 | entry | fn | flags | PyArg 書式 (VA) | PyArg の出力先 | dispatch `0xd843d0` の引数 | callback (VA) | 作用先 | 戻り値 (PE) | 状態 |
|---|---|---|---|---|---|---|---|---|---|---|
| `ui.launchAudioEditor` | 0x151b828 | 0xd6d540 | 1 | `isiss` (0xd6d6a4) | reuse `[rbp+0xbc]` (i)・filename `[rbp+0xb0]` (s)・index `[rbp+0xb8]` (i)・preset `[rbp+0xa8]` (s)・presetGUID `[rbp+0xa0]` (s) | 5 個を task+0x18〜+0x40 へ (0xd6d5da〜0xd6d60a) | 0xd6d440 | `0x118a810(reuse==1, filename, index, preset, presetGUID)` (0xd6d4f0)。戻り値は task+0x10 | status 0 なら `out[+8]` を int 変換 (slot `0x15e4280`・0xd6d63b〜0xd6d642)。status ≠ 0 なら `0xd82c20(status)` (0xd6d64c) | **保留** (子 #3734) |
| `ui.openEventEditor` | 0x151bac8 | 0xd6ef80 | 1 | `Ii\|i` (0xd6f0b4) | eventId `[rbp+0xac]` (I・符号なし 32bit)・mode `[rbp+0xa8]` (i)・newWindow `[rbp+0xa4]` (i・既定 0 は 0xd6efb4) | eventId・mode・newWindow と 0, 0, 0, sync=1 | 0xd6ef20 | `0xe34450(eventId, mode, newWindow, 大域 byte)` (0xd6ef68)。戻り値は捨てる | `0xd82c20(status)` → None (0xd6f059)。task+0x10 = -1 (0xd6ef4e) は戻りに使われない | **実装** (no-op) |
| `ui.showPicker` | 0x151bb28 | 0xd6f2e0 | 1 | `i\|i` (0xd6f404) | arg1 `[rbp+0x9c]` (i・必須)・arg2 `[rbp+0x98]` (i・既定 -1 は 0xd6f314) | arg1・arg2 と 0, 0, 0, 0, sync=1 | 0xd6f280 | picker オブジェクト `*(*(G)+0x54)` の vtbl[+0x48](obj, arg1, arg2, 1) (0xd6f2cd)。戻りは捨てる | `0xd82c20(status)` → None (0xd6f3ab) | **実装** (no-op) |

- 書式の文字列は probe の `str@… -> …` が返した値と一致する。`pe_handler_probe.py` の fn VA は `analysis/flapi/flapi_kwargs.json` と一致する。
- fl_table の行 (`provider/gen/fl_table.c`): `launchAudioEditor` は `'i', 5, 5, "isiss"`、`openEventEditor` は `'i', 3, 2, "iib"`、`showPicker` は `'a', -1, 0, ""` (署名なし np=-1。handler が個数と型を検査)。

### dispatch `0xd843d0` と callback の規約 (3 件共通)

- 入口で `*out = -2` (0xd843e9)。5 番目以降の引数を task+0x18〜+0x40 へ複製 (0xd84429〜0xd84467)。callback を task+0x58 に置く (0xd8446b)。11 番目の引数 (`[rbp+0xb0]`) が sync flag (0xd84471)。
- 完了時、`out[0] = task[+0x60]` (status・0xd844d7〜0xd844db) と `out[+8] = task[+0x10]` (value・0xd844c2〜0xd844c6) を書く。これは REPORT_PY121 の `processRECEvent` と同じ out 規約 (第 1 qword = status、第 2 dword = value)。
- callback の入口で `task[+0x60] = -2` (0xd6d469・0xd6ef28・0xd6f289)。述語 `pred = vtbl(G.this)[+0x98]()` が偽なら -2 のまま (0xd6d48d・0xd6ef4c・0xd6f2ab)。真なら本体を呼び、最後に `task[+0x60] = 0` (0xd6d500・0xd6ef6d・0xd6f2d0)。`G.this` は REPORT_PY121 と同じ読み (`*(*(*(0x15e4790))+8)`)。

### 戻り値の経路 `0xd82c20` と `0xc38bc0`

- `0xd82c20(code)` の code 0 は、関数ポインタ (`[0x860485]` 経由) の戻りが非 null なら 0 (例外の伝播)、null なら `0xc38bc0` の戻り。`0xc38bc0` は `mov rax,[rip+0xa7f719]; ret` (1 つの大域値の読出し) で、None と推定 (REPORT_PY102 で None と記録済み)。
- status が -2 (述語偽) のときは code < 0 の経路 (0xd82c6a) に入り、`vtbl[+0x88]` の真偽と code 別の文言で分かれる。この分岐の結果 (None か例外か) は未同定。

### 戻り値の食い違い (openEventEditor)

- PE: status 0 → `0xd82c20` → None (上の経路)。
- stub (`analysis/flapi/flapi_table.json`) と fl_table: 戻り `int`。
- 本 PR は PE に合わせて None を返す。stub の修正は生成元 (`analysis/flapi/`) の判断であり、本 PR では変えない (未解決)。

## 実装 (作用は未モデル)

- `ui.showPicker`: C `NARGS(1, 2)`・`A_INT(0, 0)`・`A_INT(1, -1)`・戻り None。mock は `arity(1, 2)`・`argI`。
- `ui.openEventEditor`: 個数 2〜3 と型 (`i`・`b`) は fl_table の `iib` (dispatcher の `type_ok`) が検査する。C の本体は戻り None のみ。mock は `arity(2, 3)`・`argI`。
- 作用 (picker の表示、`0xe34450` の処理) は未モデル。画面に何も出ない点は `ui.showNotification`・`ui.closeAllMenu` と同じ扱い。

## 検証

- 測定 commit: `670e99d9d` (コードを変えた最後の commit。main を取り込んだ merge。`provider_check.mjs` の競合を解消)。取り込み前の初回測定は `aeec4c877` (`feat(python): implement ui showPicker and openEventEditor (PY-133)`、件数 155 → 157)。
- `git diff 670e99d9d HEAD -- tools/python ':!*.md'` の出力は空 (本節の後の変更は md のみ)。
- 環境: runner 4 core、測定時の `uptime` は `load average: 0.31, 0.62, 0.56` (03:39:01)。`FL_WIN64_DIR` は `$RUNNER_TEMP/fl-win64` (`fl-win64.tar.zst` を `tar --zstd -xf` で全展開、7.3 秒)。emsdk は `[EMSDK]` (`docs/REFERENCES.md`) の既定位置。`FL_WIN64_DIR` は `$RUNNER_TEMP/fl-win64` (`fl-win64.tar.zst` を `tar --zstd -xf` で全展開、7.3 秒)。emsdk は `[EMSDK]` (`docs/REFERENCES.md`) の既定位置。
- 前提の生成物 (gitignore・本測定で再生成): `bash fetch_inputs.sh` (rc 0)・`bash build_cpython_wasm.sh` (rc 0、3 分 41 秒)・`FLPY_SKIP_TABLE=1 bash build_flpy.sh` (rc 0)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 (`dist/flprov.wasm` 64,219 B) | (未計測) |
| `node tests/ui_editor_diff.mjs` | PASS (正常 6・異常 8・diffs 0) | 0.041 秒 |
| `node tests/ui_display_diff.mjs` | PASS (正常 12・異常 11・diffs 0・displayTime 2000) | 0.041 秒 |
| `node tests/ui_diff.mjs` | PASS (calls 17・diffs 0・範囲外既知差分 3) | 0.042 秒 |
| `node tests/ui_state_diff.mjs` | PASS (calls 33・diffs 0) | 0.042 秒 |
| `node tests/provider_check.mjs` | PASS (functions 435 / 実装 164 / 未実装 271 / MCP 静的 60) | 0.286 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.419 秒 |

- コミット済み HEAD (`670e99d9d`) で `provider/build.sh` と `build_flpy.sh` を再実行し、上の表の検査が同じ結果で PASS することを確認した (初回の `aeec4c877` でも同じ結果)。
- ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `ui.openEventEditor` の個数上限を 3 から 2 にすると `node tests/ui_editor_diff.mjs` は rc 1 (`AssertionError: ui.openEventEditor`)。元に戻すと PASS。

## 製品 KPI (起動・GUI に関わる PR の記載)

- FLEngine 起動の dispatch 数・通過 unit 数 (`tools/flelift/boot/REPORT.md`)・最初のウィンドウの有無: **動かしていない**。本 PR は Python provider の ui 関数 2 件 (作用は no-op) の追加で、起動の経路 (`flelift`・`boot`) は変えていない。KPI は測定していない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ui.launchAudioEditor`: callee `0x118a810` の戻り値の意味と、述語偽 (status -2) の挙動 | 戻り int の値が決まらず、mock/C 未実装 | 子 issue #3734 (PY-242) |
| `showPicker`・`openEventEditor`: 作用先 (`0xe34450`・picker の vtbl[+0x48]) と、述語偽 (-2) の戻り (None か例外か) | 作用は no-op。述語偽の経路は未実装 | 子 issue #3734 (PY-242) の範囲に含める |
| `openEventEditor`: stub・fl_table の戻り `int` と PE の戻り None が不一致 (本 PR は PE に合わせた) | Python 側の戻り型。stub と実装が食い違う | PM (`analysis/flapi/` の生成元の確認) |
| `showPicker` の必須引数 (`i`) に None を渡したとき: PyArg は TypeError、本 PR は既定値扱い | None を渡しても code 5 にならない | プロジェクト共通の規約 (`fl_a_int`・mock の `argI`: None は既定値)。REPORT_PY121_2982 と同じ扱い |
