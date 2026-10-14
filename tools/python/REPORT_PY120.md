# tools/python REPORT: PY-120 ui の操作・キー・ジョグ・編集 27 関数の PE 意味論 (#2981, 親 #2831)

> 正本: `tools/python/REPORT_PY87.md` (PE 確定の書式・ネガティブコントロール)、`tools/python/REPORT_PY27.md` (保留 150 件の出自)。本付録は PY-120 の実測のみ。
> 前段 `REPORT_PY95.md` は main に存在しない (issue 本文の記述は誤り)。PE から直接確認した。

## 結論

- issue #2981 の 27 関数は **PE から確定できた関数 0 件**。mock (`host/fl_mock.mjs`) と C (`provider/fl_engine.c`) には実装を入れていない。作用先 (UI のどの状態を変えるか) と戻り値の値が PE から定まらないため、根拠のない値を入れない方針 (PY-87 と同じ) に従った。
- PE から確定した事実は **呼出し契約の一部** (引数書式・既定値・ディスパッチの op code・経路)。全 27 関数の表は本文 §確定 (保留) の表。
- issue 本文の仮説は 2 点とも誤り (PE で訂正):
  - `0xd81740` は関数ではない。27 関数のどれも `call 0xd81740` を含まない。`0xd81740` は `PyCallSynchronizedResult` の名前を持つ静的な型記述子 (先頭 qword はその自己参照 0xd81748) で、各 handler が `mov rdx, [rip+X]` (X は 0xd81740 を指す) で読んで `0x415610` (フィールドの既定値設定と見られる) と `0x415c30` (後始末と見られる) に渡す。
  - `0x15e1e58` は状態ではない。VARARGS の 14 関数は `mov rax, qword ptr [rip+X]` (X の解決先は 0x15e1e58。例: 0xd6a99d) で値を読み、`call qword ptr [rax]` で呼ぶ。0x15e1e58 は **PyArg_ParseTuple 相当の CPython API スロット** (戻り値 ≤ 0 で失敗: `movsxd rax,eax; test rax,rax; jle`)。`0x15e4280` も同じ形 (26 関数、`mov rax, qword ptr [rip+X]` → `call qword ptr [rax]`) で、int 変換スロット。
- 共通の作用経路は `0xd84680(engine, &out, op, arg, mode, 0xf)` → `0xfdd2c0(op, arg, mode, 0xf, 0)` (約 5 KB の UI 側ディスパッチャ)。`scrollWindow` だけは `0xd843d0` を直接呼ぶ。作用の中身 (`0xfdd2c0` の op 別の分岐先) は未追跡で、これが保留の本体。

## 手段

- ハンドラ探索: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <名前...>` (entry VA・fn VA・flags・先頭 40 命令)。`left`・`right` は同名の文字列が別テーブルにもあり、先頭に別 entry (0x1516038・0x1516048) が出るが無関係。ui の entry は本文表の値。
- 呼出し契約の抽出: 新規 `analysis/flapi/pe_ui_ops_probe.py` (本 PR)。関数の範囲は `.pdata` の終端で決め、最初の ret では止めない (`.pdata` に無い fn はエラー)。`FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_ops_probe.py jog:d6a960 ...` で、関数先頭から終端までの PyArg 書式 (`lea rdx` の参照先文字列)・既定値 (`mov dword [rbp+0x6c], 1`)・型記述子参照・`call 0xd84680` 直前の r8/r9 を出す。
- 素材: `[WIN64]` の素材 tar (fl-win64) から `block24429/24430/25159/24618_DATA.bin` を追加展開 (`fetch_inputs.sh` 用)。`toolchain-emsdk` は `[EMSDK]` (6.0.12 pin) を使用。
- 公開 stub の戻り型: `analysis/flapi/flapi_table.json` の `modules.ui` (`sig.returns`)。PE の結論とは別に併記する。

## 確定・保留 (27 関数の PE 契約)

凡例: fn = 関数先頭 VA。書式 = `lea rdx` が指す PyArg 書式。op = `call 0xd84680` 直前の `r8` (jog のみ `xor r8,r8` = 0)。r9 = 第 4 引数 (`[rbp+0x6c]` = 受け取った引数、1 = 定数)。stub = `flapi_table.json` の戻り型と引数。

| 関数 | PyMethodDef entry | fn (VA) | flags | 書式 | 既定 | op (r8) | r9 | 呼出し先 | stub | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|
| `ui.jog` | 0x151b248 | 0xd6a960 | 1 | `i` | — | 0 | 引数 | d84680 | int(value) | 保留 |
| `ui.jog2` | 0x151b268 | 0xd6aa50 | 1 | `i` | — | 1 | 引数 | d84680 | int(value) | 保留 |
| `ui.strip` | 0x151b288 | 0xd6ab40 | 1 | `i` | — | 2 | 引数 | d84680 | int(value) | 保留 |
| `ui.stripJog` | 0x151b2a8 | 0xd6ac30 | 1 | `i` | — | 3 | 引数 | d84680 | int(value) | 保留 |
| `ui.stripHold` | 0x151b2c8 | 0xd6ad20 | 1 | `i` | — | 4 | 引数 | d84680 | int(value) | 保留 |
| `ui.previous` | 0x151b2e8 | 0xd6ae10 | 4 | — | — | 5 | 1 | d84680 | int() | 保留 |
| `ui.next` | 0x151b308 | 0xd6aed0 | 4 | — | — | 6 | 1 | d84680 | int() | 保留 |
| `ui.moveJog` | 0x151b328 | 0xd6af90 | 1 | `i` | — | 8 | 引数 | d84680 | int(value) | 保留 |
| `ui.up` | 0x151b348 | 0xd6b080 | 1 | `\|i` | 1 | 0x28 | 引数 | d84680 | int(value=1) | 保留 |
| `ui.down` | 0x151b368 | 0xd6b170 | 1 | `\|i` | 1 | 0x29 | 引数 | d84680 | int(value=1) | 保留 |
| `ui.left` | 0x151b388 | 0xd6b260 | 1 | `\|i` | 1 | 0x2a | 引数 | d84680 | int(value=1) | 保留 |
| `ui.right` | 0x151b3a8 | 0xd6b350 | 1 | `\|i` | 1 | 0x2b | 引数 | d84680 | int(value=1) | 保留 |
| `ui.horZoom` | 0x151b3c8 | 0xd6b440 | 1 | `i` | — | 0x2c | 引数 | d84680 | int(value) | 保留 |
| `ui.verZoom` | 0x151b3e8 | 0xd6b530 | 1 | `i` | — | 0x2d | 引数 | d84680 | int(value) | 保留 |
| `ui.snapOnOff` | 0x151b408 | 0xd6b620 | 4 | — | — | 0x30 | 1 | d84680 | int() | 保留 |
| `ui.cut` | 0x151b488 | 0xd6b9c0 | 4 | — | — | 0x32 | 1 | d84680 | int() | 保留 |
| `ui.copy` | 0x151b4a8 | 0xd6ba80 | 4 | — | — | 0x33 | 1 | d84680 | int() | 保留 |
| `ui.paste` | 0x151b4c8 | 0xd6bb40 | 4 | — | — | 0x34 | 1 | d84680 | int() | 保留 |
| `ui.insert` | 0x151b4e8 | 0xd6bc00 | 4 | — | — | 0x35 | 1 | d84680 | int() | 保留 |
| `ui.delete` | 0x151b508 | 0xd6bcc0 | 4 | — | — | 0x36 | 1 | d84680 | int() | 保留 |
| `ui.enter` | 0x151b528 | 0xd6bd80 | 4 | — | — | 0x50 | 1 | d84680 | int() | 保留 |
| `ui.escape` | 0x151b548 | 0xd6be40 | 4 | — | — | 0x51 | 1 | d84680 | int() | 保留 |
| `ui.yes` | 0x151b568 | 0xd6bf00 | 4 | — | — | 0x52 | 1 | d84680 | int() | 保留 |
| `ui.no` | 0x151b588 | 0xd6bfc0 | 4 | — | — | 0x53 | 1 | d84680 | int() | 保留 |
| `ui.nextWindow` | 0x151b5a8 | 0xd6c080 | 4 | — | — | 0x3a | 1 | d84680 | int() | 保留 |
| `ui.selectWindow` | 0x151b5c8 | 0xd6c140 | 1 | `i` | — | 0x3b | 引数 | d84680 | int(shift: **bool**) | 保留 (型不一致) |
| `ui.scrollWindow` | 0x151b808 | 0xd6d300 | 1 | `ii\|i` | c=0 | (d843d0) | — | d843d0 | None(index, value, directionFlag=0) | 保留 |

判定はすべて「保留」。理由は次の 3 点に共通する (確定基準: 戻り値の値と範囲・作用先が PE から言えること を満たさない)。

1. **作用先が未確定**: 26 関数は `0xd84680` → `0xfdd2c0(op, arg, mode, 0xf, 0)` に渡すだけ。`0xfdd2c0` は UI 側の大きな分岐 (約 5 KB) で、op ごとの作用 (どの状態・どの関数を変えるか) は未追跡。`scrollWindow` は `0xd843d0` に callback 風の `lea r8,[rip-0xf5]` (= 0xd6d290) を渡すため、別経路で未追跡。
2. **戻り値の値が未確定**: 26 関数は `status == 0` のとき `out+8` の dword を `0x15e4280` で変換して返す (`out` は `0xd84680` の第 2 引数)。`0xd84680` が書くのは `out+0` (qword) だけで (`mov qword [rbx], 0 / -1 / -2` の 3 箇所)、`out+8` は書かない。その初期値は `0x415610` が型記述子 `0xd81740` から設定すると見られるが、既定値規則は未解析。`scrollWindow` は `0xd82c20(status)` の戻り値を返す。`0xd82c20` は `status == 0` のとき、`[0x860485]()` が非 0 なら NULL、0 なら `0xc38bc0()` を返す。`0xc38bc0` は未同定 (stub の None と整合するが、PE からは確定しない)。
3. **引数型の不一致**: `ui.selectWindow` の stub は `shift: bool` だが、PE の書式は `i` (C int)。PE を正とすると int で受け、0/1 以外の値の扱いは未確定。

PE から確定した契約 (保留の中身。実装には使わない):

- 全 27 関数が `call 0xd6fd10` を 1 回ずつ直接呼ぶ (例: 0xd6a986。`.pdata` 範囲の検算で 27 件)。`0xd6fd10` は `sub rsp,0x28; mov rax,[rip+X]; call qword ptr [rax]; add rsp,0x28; ret` だけの薄いラッパで、X の解決先は 0x15e05b8。戻り rax の `*(rax)` (例: 0xd6a98b `mov rbx, qword ptr [rax]`) を engine handle とする。
- 失敗経路: `0xd84680` の `out.status` が 0 以外 → `0xd82c20(status)` (例外経路)。`0x11d1430` は `[vtbl+0x88]` の前提判定 (偽で status = -2)。`0xfdd2c0` は `mode` の bit 1 (`test al,2`) が 0 なら即 -1。`mode` は `0xfdd270` の戻り (vtbl+0x80 の結果を表で引く)。
- 既定値: `up`・`down`・`left`・`right` は `mov dword [rbp+0x6c], 1` の後に `|i` で解析 (省略時 1)。`scrollWindow` の第 3 引数は `mov dword [rbp+0xa4], 0` (省略時 0)。stub の `directionFlag default 0` と一致。

## 保留 (本 run で未確定の項目)

- 27 関数の作用先: `0xfdd2c0` の op 別の分岐。
- 戻り値: `0x415610` の既定値規則 (out+8)、`0x15e4280` の型 (int と bool の区別)、`0xc38bc0` の同定。
- `scrollWindow` の `0xd843d0` と callback 候補 `0xd6d290`。
- `0xd6fd10` の先 (スロット 0x15e05b8 の実体) の同定 (engine handle の取り方)。

## 検証

- 測定 commit (コードを変えた最後の commit): `8306f425` (`origin/main` の 2 回目の取り込み。PR 側のコードは `97c60b6c` から変わっていない)。解析補助 `pe_ui_ops_probe.py` の最後の変更は `97c60b6c` (`.pdata` 終端にし、r8/r9 の判定を書き直した)。`97c60b6c` の作業ツリー clean 状態で 27 関数を再実行した。`8306f425` でも同じ 27 関数を再実行し、出力は `13087005` での再実行と一致した (下表)。
  - 改修前の出力との比較: 関数ごとの本体行は同一。header に `ret=1` が加わった (27 関数すべて ret 1 個)。`py_compile` rc 0。
  - 独立検算 (`.pdata` 範囲の逆アセンブル、リポジトリ外の一時スクリプト): 27 関数すべて ret 1 個、`call 0xd6fd10` 1 個、`call 0xd84680` 26 個、`call 0xd843d0` 1 個 (scrollWindow のみ)。`mov rax,[rip+X]` の解決先は 0x15e1e58 (14 関数) と 0x15e4280 (26 関数)。
- provider・host・tests: 旧版はこの節で「`13b6ae46` 以降は差分 0」と書いたが、確認に使ったパスがリポジトリ直下基準で、実際には見ていなかった。main の取り込みで `tools/python/provider/fl_engine.c`・`tools/python/host/fl_mock.mjs`・`tools/python/tests/` などが変わっている (`git diff --stat 97c60b6c 8306f425 -- tools/python/provider tools/python/host tools/python/tests`: 11 files, 438 insertions(+), 14 deletions(-))。下表は `8306f425` での実測。旧測定 (`13b6ae46`: ハンドラ 83・実装 83・未実装 352) からの増分 9 件は main の provider 変更によるもので、PY-120 の増減は 0。

環境 (`13b6ae46` の測定): runner 4 core、load average は開始時 0.29 (`uptime`、20:52)、検証時 0.10 (21:04)。`FL_WIN64_DIR` は `[WIN64]` の展開先 (`block00031_PE.bin` と DATA 4 本を展開)。emsdk は `[EMSDK]` (6.0.12)。
環境 (`97c60b6c` の probe 再実行): `FL_WIN64_DIR` は `$RUNNER_TEMP/fl-win64` (`extracted/block00031_PE.bin` と DATA 4 本を `tar --zstd -xf` の `--wildcards` で展開)。
環境 (`13087005`・`8306f425` の再実行): 素材は `$ARTIFACTS_DIR` の `fl-win64` と `toolchain-emsdk` (`[EMSDK]`、emcc 6.0.12)。`fl-win64` から `extracted/block00031_PE.bin` と DATA 4 本 (block24429・24430・25159・24618) を `--wildcards` で展開 (2.96 秒)。runner 4 core、load average は計測時 0.30 (21:44:15)。

前提の生成物 (gitignore): `bash fetch_inputs.sh` (rc 0)・`bash build_cpython_wasm.sh` (rc 0、4 分 2.7 秒、`13087005` の環境で作成)・`FLPY_SKIP_TABLE=1 bash build_flpy.sh` (rc 0、`8306f425` で 5.78 秒)。旧測定の生成物は `13b6ae46` の環境 (3 分 31 秒・4.6 秒)。下表は `8306f425` の再実行。

| コマンド (測定 commit 8306f425) | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 92 | 0.94 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 92 / 未実装 343 / MCP 静的 60) | 0.35 秒 |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 0.05 秒 |
| `node tests/ui_state_diff.mjs` (main の PY-119 追加テスト。参考) | calls 12、diffs 0、PASS | 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback_roundtrip true | 1.64 秒 |
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_ops_probe.py <27 関数 名前:fn VA>` | rc 0。27 関数すべて `ret=1`、`call d84680` 26 件、`call d843d0` 1 件 | 3.15 秒 |
| `py_compile analysis/flapi/pe_ui_ops_probe.py` (97c60b6c) | rc 0 | — |

ネガティブコントロール (`docs/WORKFLOW.md` §5・`8306f425` で実測): `host/fl_mock.mjs` の `windows` 既定値 (35 行。旧版は 29 行) の `0: true` を `0: false` に変えると、`node tests/ui_diff.mjs` は `AssertionError [ERR_ASSERTION]: ui 差分 1 件` で rc 1 (FAIL)。元に戻すと calls 17・diffs 0・PASS (rc 0)。

コード差分 (測定 commit `8306f425` から HEAD まで、`tools/python` の .md 以外):

```
$ git diff 8306f425 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xfdd2c0` の op 別作用 (UI のどの状態を変えるか) | 27 関数すべて保留 (実装不可) | #3035 (`[PY-140]`) |
| `mode` (`0xfdd270` の戻り) の実機値 | 作用の成否 (bit 1) | #3035 (`[PY-140]`) |
| `scrollWindow` の `0xd843d0` 経路と callback `0xd6d290` | scrollWindow の作用 | #3035 (`[PY-140]`) |
| `0x415610` の out+8 既定値規則・`0xc38bc0` の同定・`0x15e4280` の int/bool 判定 | 戻り値の値と型 | #3034 (`[PY-141]`) |
| `selectWindow` の引数型 (stub bool / PE `i`) | 引数契約の正 | #3034 (`[PY-141]`) |

子 issue は起票済み: #3035 `[PY-140]` (案 A: 作用先の確定と確定関数の mock/C 実装)、#3034 `[PY-141]` (案 B: 戻り値の値と型の確定)。親 #2981 の本文は受入 1・3・4 に縮めた。
