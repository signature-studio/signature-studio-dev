# tools/python REPORT: PY-133 ui のエディタ起動・ピッカー 3 件の PE 確定と C provider 実装 (#3014, 親 #2982)

> 前段: `tools/python/REPORT_PY121_2982.md` (保留 3 件の出典。PR #3019 で merge 済み)。戻り値 None の根拠: `tools/python/REPORT_PY102.md` (`0xd82c20` の status 0 → None)。
> 既知類型との関係: 該当なし (PE の直接逆アセンブル。`docs/DEFECTS.md` の類型は対象外)。
> 同じ形の実装は `tools/python/REPORT_PY121_2982.md` (showNotification・closeAllMenu) と同じ扱い (作用は未モデル、個数・型の検査と戻り値だけ)。

## 結論

- 3 件の PyArg 書式・引数の出力先・dispatch への渡し方・戻り値の経路を PE (`block00031_PE.bin`) から VA 付きで確定した。
- **showPicker・openEventEditor は実装した** (mock と C の差分 0)。戻り値は PE の経路で None (stub の `openEventEditor` 戻り `int` とは食い違う。下の未解決)。作用先 (picker・エディタの起動) は未モデルの no-op。
- **launchAudioEditor は保留**。戻り値 int は callee `0x118a810` の戻り値で、その意味が未同定。値を mock/C に書くと silent miscompile になるため実装しない。子 issue #3734 (PY-242) に移した。
- 件数 (main `45182bf1b` の `provider_check.mjs` の期待値 173/262 に、PR の `pe133` の 2 件を足した値): 実装 173 → 175 (+2・`pe133`)、未実装 262 → 260。`gen_provider.py --check-handlers` のハンドラ数 175 と一致する。
- 引数の意味: 検索キー・格納・分岐の用途を VA で確定した (「引数の意味」節)。`launchAudioEditor` の 5 引数は callee `0x118a810` への渡し方を VA で確定した。意味を確定できない引数 (`launchAudioEditor` の 5 引数の意味、`showPicker` の arg1・arg2、`eventId` の上位 16 bit、`newWindow=2` の委譲先) は、理由を書いて未解決表に載せた (子 #3734)。

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

## 引数の意味 (受入条件 1・VA 根拠)

確定と未確定を分けて書く。「確定」は PE の格納・分岐・呼出しで示せる範囲に限る。引数名 (`eventId` 等) は stub 由来で、PE の動作からは裏付けていない。

| 引数 | 格納・渡し方 (VA) | 使われ方 (VA) | 意味 | 状態 |
|---|---|---|---|---|
| `openEventEditor` eventId | PyArg 出力 `[rbp+0xac]` (0xd6efc9)。dispatch 5 番目 → task+0x18 → callback `mov ecx,[rbx+0x18]` (0xd6ef56) → callee `0xe34450` の ecx (保存 `[rbp+0x34]`・0xe34468) | (1) 既存エディタの検索キー: `0xe34190` が `+0xc4c`・`+0xc68` の子の `+0x3f4` と照合 (0xe341d1・0xe341e6、呼出し 0xe345ba)。(2) `mode > 0` の新規作成で `+0xc68` の `+0x3f4` に格納 (0xe36784)、`+0x3f8` = eventId + 0x1f (0xe3678a〜0xe36793)。(3) 上位 16 bit (`shr 0x10`) を `0xe3d690` の引数へ (0xe367a3) | 「既存エディタを識別する ID」は (1)(2) の検索と格納で確定。ID が何の対象の ID かと、上位 16 bit の意味は未確定 (`0xe3d690` の解析が要る) | 一部確定 |
| `openEventEditor` mode | PyArg 出力 `[rbp+0xa8]` (0xd6efd0)。callback `mov edx,[rbx+0x20]` (0xd6ef59) → callee edx (保存 `[rbp+0x38]`・0xe3446b) | (1) 新規エディタの `+0xb18` に格納 (0xe346ad)。(2) 同じ mode のエディタ数を `0xe34220` が数え (0xe34683・0xe34255)、再利用検索 (0xe366dd) が同じ値で探す。(3) `mode > 0` と `≤ 0` で後処理が分かれる (0xe36718・0xe36750)。(4) mode 0・1・2 は `+0x6d0` の 16 bit flag を立てる (0xe346c3〜0xe346cc)。mode 1・2 は vtbl+0x298 を呼ぶ (0xe34709〜0xe3475b) | エディタの種類 (kind) の判別子は (1)〜(4) の分岐で確定。0・1・2 が何のエディタかは未確定 | 一部確定 |
| `openEventEditor` newWindow | PyArg 出力 `[rbp+0xa4]` (既定 0 は 0xd6efb4)。callback `mov r8d,[rbx+0x28]` (0xd6ef5c) → callee r8d (保存 `[rbp+0x3c]`・0xe3446e) | 既存の eventId が無い経路でだけ読む (既存の経路 0xe345c6〜0xe3460f は読まない)。(1) `== 2` かつ大域 `[0x8861dc] != 0` のとき、大域マネージャへ委譲: `0xe3d440(mgr, eventId)`・`0x80c9f0`・vtbl+0x260 (0xe34614〜0xe34663)。(2) `== 1` 以外で同 mode のエディタがあれば再利用 (0xe34688・0xe366aa〜0xe366e5)。(3) `== 1` は (2) を飛ばし必ず新規作成 (0xe34678〜0xe3467e → 0xe34690) | `1` = 新しいウィンドウを作る、既定 `0` = 同 mode を再利用、は分岐の形から確定。`2` = 大域マネージャへの委譲も分岐の形から確定。委譲先 `0xe3d440` が何をするかは未確定 | 一部確定 |
| `openEventEditor` callee の第 4 引数 | `movzx r9,[rip+0x14]` (0xd6ef60)。対象 VA `0xd6ef7c` の byte は `0x01` (`pe_va_read.py`) | 既存エディタ経路で `test al,1` (0xe345e3): 1 なら `0xe432d0(obj)`、0 なら vtbl+0x260 (0xe34609) | 値 1 は確定。`0xe432d0` の作用は未確定 | 値は確定 |
| `showPicker` arg1 | PyArg 出力 `[rbp+0x9c]` (0xd6f329・必須) → dispatch 5 番目 → task+0x18 → callback `mov edx,[rbx+0x18]` (0xd6f2c0) | picker の `vtbl[+0x48]` の第 2 引数 (0xd6f2cd) | 未確定。受け側の picker オブジェクト `*(*(G)+0x54)` のクラスと slot +0x48 の実装 VA が未同定のため、何の index かを言えない | 未確定 |
| `showPicker` arg2 | PyArg 出力 `[rbp+0x98]` (0xd6f330・既定 -1 は 0xd6f314) → task+0x20 → callback `mov r8d,[rbx+0x20]` (0xd6f2c3) | `vtbl[+0x48]` の第 3 引数 | 未確定 (arg1 と同じ理由) | 未確定 |
| `showPicker` の第 4 引数 | callback `mov r9b,1` (0xd6f2c7) | 定数 | 値 1 は確定。意味は arg1・arg2 と同じく未確定 | 値は確定 |
| `launchAudioEditor` reuse | PyArg 出力 `[rbp+0xbc]` (0xd6d57f)。dispatch の 5 番目の引数 → `movsxd` で task+0x18 (0xd6d5da)。callback が `cmp qword [task+0x18],1` → `sete cl` (0xd6d4cf〜0xd6d4d4) | callee `0x118a810` の第 1 引数 rcx (`reuse == 1` の bool・0xd6d4f0 の直前) | callee 未解析のため、1 のとき何を再利用するかは未確定 | 渡し方は確定。意味は未確定 |
| `launchAudioEditor` filename | PyArg 出力 `[rbp+0xb0]` (0xd6d586)。task+0x20 (0xd6d5e6〜0xd6d5ed)。callback が `0x41c6e0(&[rbp+0x58], [task+0x20])` で局所へ複製 (0xd6d497〜0xd6d4a0) し、その値を rdx へ (0xd6d4d7) | callee 第 2 引数 rdx | 未確定。`0x41c6e0` は引数 2 つを受け `[src]` の先頭 byte を調べる helper で、中身は未解析 | 渡し方は確定。意味は未確定 |
| `launchAudioEditor` index | PyArg 出力 `[rbp+0xb8]` (0xd6d58d)。task+0x28 (0xd6d5f2〜0xd6d5f9)。callback が `mov r8d,[task+0x28]` (0xd6d4df) | callee 第 3 引数 r8 (32 bit 読み) | 未確定 | 渡し方は確定。意味は未確定 |
| `launchAudioEditor` preset | PyArg 出力 `[rbp+0xa8]` (0xd6d599)。task+0x30 (0xd6d5fe〜0xd6d605)。callback が `0x41c6e0(&[rbp+0x50], [task+0x30])` で複製 (0xd6d4a7〜0xd6d4b2) し、その値を r9 へ (0xd6d4e3) | callee 第 4 引数 r9 | 未確定 (filename と同じ理由) | 渡し方は確定。意味は未確定 |
| `launchAudioEditor` presetGUID | PyArg 出力 `[rbp+0xa0]` (0xd6d5a5)。task+0x38 (dispatch の複製先。callback の読みは 0xd6d4bb)。callback が `0x41c6e0(&[rbp+0x48], [task+0x38])` で複製 (0xd6d4bb〜0xd6d4c6) し、その値をスタックの第 5 引数 `[rsp+0x20]` へ (0xd6d4e7〜0xd6d4eb) | callee 第 5 引数 (スタック) | 未確定 (filename と同じ理由) | 渡し方は確定。意味は未確定 |

- 型: PyArg は `newWindow` を `i`、fl_table は `b`。`provider/fl_dispatch.c` の `'b'` は tag `'I'` (int) も受理する (61 行) ので、値 2 が型検査で弾かれることはない。
- `launchAudioEditor` の 5 引数は、task から callee `0x118a810` への渡し方 (上の表) までを VA で確定した。意味が未確定な理由は、callee 本体が大きく未解析なため (`sub rsp,0x888`・0x118a810 の先頭 40 命令は各スロットのゼロ初期化)。確定に必要な情報は、callee 内で rcx・rdx・r8・r9・`[rsp+0x20]` がどの読み出し・分岐に使われるかの追跡。この追跡は本 PR の範囲外として子 #3734 に移した。
- 未確定の引数は未解決表に載せた (起票先は子 #3734)。

## 実装 (作用は未モデル)

- `ui.showPicker`: C `NARGS(1, 2)`・`A_INT(0, 0)`・`A_INT(1, -1)`・戻り None。mock は `arity(1, 2)`・`argI`。
- `ui.openEventEditor`: 個数 2〜3 と型 (`i`・`b`) は fl_table の `iib` (dispatcher の `type_ok`) が検査する。C の本体は戻り None のみ。mock は `arity(2, 3)`・`argI`。
- 作用 (picker の表示、`0xe34450` の処理) は未モデル。画面に何も出ない点は `ui.showNotification`・`ui.closeAllMenu` と同じ扱い。

## 検証

- 測定 commit: `7b61dea36` (コードを変えた最後の commit。`origin/main` (`45182bf1b`) を取り込んだ merge)。main の取り込みは 2 回目の競合 (`tests/provider_check.mjs`・1 件) を解消した。前の測定 `19831e71f` (main `091e4a7b6` の取り込み) は、main がさらに進んだため無効になった。`45182bf1b` の取り込みで入った tools/python の変更は `provider/build.sh`・`provider/fl_engine.c`・`host/fl_mock.mjs`・`host/fl_provider.mjs`・`tests/*.mjs` (11 file)。CPython・flpy の入力 (`build_cpython_wasm.sh`・`build_flpy.sh`) は変わっていないため、前回の生成物を流用した。
- `git diff 7b61dea36 HEAD -- tools/python ':!*.md'` の出力は空 (測定後の変更は REPORT の md のみ)。
- 環境: runner 4 core、測定時の `uptime` は `load average: 0.64, 0.96, 0.66` (04:37)。emsdk は上流から `git clone --depth 1 https://github.com/emscripten-core/emsdk.git [EMSDK]` → `./emsdk install 6.0.12` (24 秒) → `./emsdk activate 6.0.12` で導入した (`[EMSDK]`、pin は `tools/m1/flags.sh`)。`fl-win64` 素材は `extracted/block00031_PE.bin`・`block25159_DATA.bin`・`block24429_DATA.bin`・`block24430_DATA.bin`・`block24618_DATA.bin` を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst` で展開した (2.6 秒)。
- 前提の生成物 (gitignore・`work/`・`dist/`): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` (rc 0)・`bash build_cpython_wasm.sh` (rc 0、4 分 05 秒)・`FLPY_SKIP_TABLE=1 bash build_flpy.sh` (rc 0、5.9 秒)。`bash provider/build.sh` は main 取り込み後に再実行 (rc 0、`fl_table.c`: 関数 435・ハンドラ 175)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 (ハンドラ 175) | 未計測 (rc のみ) |
| `node tests/ui_editor_diff.mjs` | PASS (正常 6・異常 8・diffs 0) | 0.045 秒 |
| `node tests/ui_display_diff.mjs` | PASS (正常 12・異常 11・diffs 0・displayTime 2000) | 0.048 秒 |
| `node tests/ui_diff.mjs` | PASS (calls 17・diffs 0・範囲外既知差分 3) | 0.046 秒 |
| `node tests/ui_state_diff.mjs` | PASS (calls 58・diffs 0) | 0.052 秒 |
| `node tests/ui_browser_diff.mjs` | PASS (ok 8・bad 5・diffs 0・browserOp 3) | 0.046 秒 |
| `node tests/provider_check.mjs` | PASS (functions 435 / 実装 175 / 未実装 260 / MCP 静的 60) | 0.346 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.619 秒 |

- ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `ui.openEventEditor` の個数上限を 3 から 2 にすると `node tests/ui_editor_diff.mjs` は rc 1 (`AssertionError [ERR_ASSERTION]: ui.openEventEditor`)。元に戻すと `arity(a, 2, 3)` に戻り、テストは PASS (測定 commit `7b61dea36` の内容で確認した。元に戻した後、上の表の全件を同じ commit で再測定)。
- PE の VA の再確認 (差し戻し round 3 への対応で、この run で実行)。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 extracted/block00031_PE.bin` (1 ファイル・2.6 秒)。実行は `tools/python` で `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
  - `python3 analysis/flapi/pe_handler_probe.py launchAudioEditor openEventEditor showPicker` → fn `0xd6d540`・`0xd6ef80`・`0xd6f2e0`、PyArg `isiss` (0xd6d6a4)・`Ii|i` (0xd6f0b4)・`i|i` (0xd6f404)、既定値の `mov dword ptr [rbp+0xa4],0` (0xd6efb4) が REPORT の表と一致。
  - `python3 analysis/flapi/pe_disasm.py d6d440 75` → launchAudioEditor の callback の `sete cl` (0xd6d4d4)・`mov r8d,dword ptr [rax+0x28]` (0xd6d4df)・`call 0x118a810` (0xd6d4f0) が一致。
  - `python3 analysis/flapi/pe_disasm.py e34614 12` → newWindow==2 の分岐 (`cmp eax,2` 0xe34617・`call 0xe3d440` 0xe34630) が一致。
  - `python3 analysis/flapi/pe_va_read.py d6ef7c` → byte `0x01` (`openEventEditor` の 4 番目の引数の値)。
  - `python3 analysis/flapi/pe_disasm.py 118a810 40` → callee の先頭は `sub rsp,0x888` と各スロットのゼロ初期化。本体の使われ方は未解析。

## 製品 KPI (起動・GUI に関わる PR の記載)

- FLEngine 起動の dispatch 数・通過 unit 数 (`tools/flelift/boot/REPORT.md`)・最初のウィンドウの有無: **動かしていない**。本 PR は Python provider の ui 関数 2 件 (作用は no-op) の追加で、起動の経路 (`flelift`・`boot`) は変えていない。KPI は測定していない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ui.launchAudioEditor`: callee `0x118a810` の戻り値の意味と、述語偽 (status -2) の挙動 | 戻り int の値が決まらず、mock/C 未実装 | 子 issue #3734 (PY-242) |
| `showPicker`・`openEventEditor`: 作用先 (`0xe34450`・picker の vtbl[+0x48]) と、述語偽 (-2) の戻り (None か例外か) | 作用は no-op。述語偽の経路は未実装 | 子 issue #3734 (PY-242) の範囲に含める |
| `openEventEditor`: stub・fl_table の戻り `int` と PE の戻り None が不一致 (本 PR は PE に合わせた) | Python 側の戻り型。stub と実装が食い違う。`fl_api_call` (`provider/fl_dispatch.c` 68〜88 行) は `fl_desc` の戻り kind を読まないため、動作は変わらない | PM agent の判断待ち: 生成元 (`tools/python/analysis/flapi/`) の戻り型を `int` のまま残すか None に直すか・既定案: PE に合わせて None (現実装) |
| `launchAudioEditor` の 5 引数 (reuse・filename・index・preset・presetGUID) の意味: callee `0x118a810` (`sub rsp,0x888`) の本体が未解析 | 渡し方 (VA) は「引数の意味」節で確定。意味が未確定で、mock/C 未実装 | 子 issue #3734 (PY-242) |
| `showPicker` の必須引数 (`i`) に None を渡したとき: PyArg は TypeError、本 PR は既定値扱い | None を渡しても code 5 にならない | プロジェクト共通の規約 (`fl_a_int`・mock の `argI`: None は既定値)。REPORT_PY121_2982 と同じ扱い |
| `showPicker` の arg1・arg2 の意味: 受け側の picker オブジェクト `*(*(G)+0x54)` のクラスと、vtbl[+0x48] の実装 VA | 引数の意味が未確定。作用は no-op | 子 issue #3734 (PY-242) |
| `openEventEditor` の eventId の上位 16 bit の意味 (`0xe3d690` の引数)、ID が何の対象か | ID の体系が未確定。C/mock は ID を検査しない | 子 issue #3734 (PY-242) |
| `openEventEditor` の newWindow=2 の委譲先 `0xe3d440` の作用、mode の種類名 (0・1・2 が何のエディタか) | 分岐の形は確定。作用は no-op | 子 issue #3734 (PY-242) |

## 追補 (#5991・親 #4820): 実行時 VA の採取 (未確認・命中なし)

- 目的: `0xd82dc6` の `call qword ptr [rbx]` (例外投入) と `0x1330c70` の `[rsi+0xe0]` 仮想呼出しの実行時の呼出し先を gdb で採る。
- 対象モジュール: `FLEngine_x64.dll` (`block00031_PE.bin`・image base `0x400000`)。上の VA は絶対 VA。実行時アドレス = ロード先 + (VA − 0x400000)。ロード先は wine のログ (`mapping PE file`) から取る。
- 手順: `tools/flp/s5991_gdb_dll_probe.sh` (FL64.exe を起動し、DLL のロード先を読み、gdb `-p` で両 VA に `break`、`continue`)。前提は `tools/flp/REPORT_APPENDIX_5649.md` §4 と同じ (wine64 9.0・gdb 15.1・`ptrace_scope=0`・`fl-install` 組立て済み)。
- 実測:
  - `s1_wine_probe.sh` で `fl-install` を組立て (G03 パッチ済み)。起動は `S1 rc=124` (120 s で終了せず GUI 継続)。
  - DLL のロード先 `0x7a730000` → 実行時 `0x7b0b2dc6` (`0xd82dc6`)・`0x7b660c70` (`0x1330c70`)。gdb は両方に `Breakpoint` を張れた (`gdb` の `Breakpoint 1 at 0x7b0b2dc6`・`Breakpoint 2 at 0x7b660c70`)。
  - 命中: **なし**。60 s の試行 (gdb rc=124・real 1 m 1 s) と 200 s の試行 (gdb rc=124・real 3 m 21 s) の両方で、どちらの VA にも停止しなかった。
- 判定:
  - 受入 1 (`0xd82dc6` の呼出し先 VA の採取と例外型): **未確認 (命中なし)**。
  - 受入 2 (`0x1330c70` の呼出し先 VA の採取と戻り値 1 の経路): **未確認 (命中なし)**。
  - 受入 3 (本追補への記録): 達成 (本節)。
- 理由 (推定・未検証): 両 VA は Python 側の `ui.*` 呼出し経路 (`launchAudioEditor`・`openEventEditor` の dispatch と、その例外経路) の中にある。GUI の起動だけでは Python の `ui.*` 呼出しは発生しないと考えられる。命中させるには、この関数を呼ぶ Python スクリプトを FL 内で実行する必要がある (その駆動手段は未確立)。
- 製品 KPI (起動・GUI に関わる): FLEngine 起動の dispatch 数・通過 unit 数 (`tools/flelift/boot/REPORT.md`)・最初のウィンドウの有無は **動かしていない** (本 PR は計測のみで起動経路を変えていない。KPI は測定していない)。
- 測定 commit: `56ddce822` (`tools/flp/s5991_gdb_dll_probe.sh` を追加した commit。処理は測定時と同一。測定後の変更はコメント行のみ)。runner 4 core・load average 1.93 (02:42)・`ptrace_scope` は測定前に `0` へ変更。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xd82dc6` の `call [rbx]` の実行時の呼出し先 (VA)・例外型 | 例外型は未確定のまま (PY-106・REPORT_PY61 §4-2 の未確定が続く) | 本 issue #5991 (命中させる駆動手段が必要) |
| `0x1330c70` の `[rsi+0xe0]` の実行時の呼出し先 (VA)・戻り値 1 の経路 | launchAudioEditor 系の戻り値の意味は未確定 (#3734 の範囲) | 本 issue #5991 |
| 両 VA を命中させる駆動手段 (FL 内で `ui.launchAudioEditor`・`openEventEditor` を呼ぶ手段) | 命中が得られない限り受入 1・2 は未確認 | 子 issue なし (駆動手段は要設計。PM 判断) |
