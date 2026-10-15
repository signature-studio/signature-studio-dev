# tools/python REPORT: PY-129 ui setter 4 件の PE 呼出し経路と C provider 実装 (#3006, 子 #3719 PY-242。前段 PY-119)

> 正本: `tools/python/REPORT_PY119.md` (保留 12 件の一覧と VA)。本 run の根拠は PE `block00031_PE.bin` の逆アセンブル (VA 付き)。

## 結論

- PY-119 で保留した ui の setter 4 件のうち、**3 件** (`ui.setHintMsg` / `ui.setFocused` / `ui.setSnapMode`) は呼出し経路 (書込み先の呼出し・引数の変換・戻り型) を PE で確定し、mock と C provider に実装した。実装の戻り値は None。**状態は持たない (仮置き)**。書込んだ値を後で読み出す経路は未確定のため、setter は値を記録しない。
- 残り **1 件** `ui.snapMode` は保留 (`0xfdd2c0` の意味が未同定)。実装しない。
- mock と C の差分は 0 (`tests/ui_state_diff.mjs` calls 77・diffs 0。増分 25 件は main の PY-130 の呼出し (setter・getVersion) を含む)。`tests/provider_check.mjs` は実装 174 / 未実装 261 (main 取り込み後の `c7992ff5f`。本 PR の pe129 3 件に、main 側の判定行 pe130・pe132・pe138・pl61 を残した)。`FL_ENGINE=wasm tests/all_tools.mjs` は 48/48 ok を維持 (host_calls 37,425)。
- 未確定の点 (setter の状態モデル・setSnapMode の範囲外・snapMode) は子 issue **#3719 ([PY-242])** に分けた。

## 手段

- ハンドラ探索と逆アセンブル: `tools/python/analysis/flapi/pe_handler_probe.py` (入力は `$FL_WIN64_DIR/extracted/block00031_PE.bin`。取り出し: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'`)。entry・fn VA は名前指定で得た (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_handler_probe.py setHintMsg setFocused setSnapMode snapMode`)。cb と共通経路は VA 指定で ret まで逆アセンブルした (`... pe_handler_probe.py 0xd6b700 0xd843d0`。VA 指定は本 PR で追加: `c2ee73c93`)。RIP 相対の絶対アドレスは `次命令 + disp` で求めた。
- 形式・戻り型: 公開 stub (`analysis/flapi/flapi_table.json` の `sig.returns` / `kwsig.fmt`)。`flapi_table.json` の既存エントリ (`ui.setHintMsg` = `s`・`ui.setFocused` / `ui.setSnapMode` = `i`、np 1) と PE の PyArg 書式は一致した。
- 共通経路 `0xd6fd10` (self → object) と `0xd843d0` (書込みの投入):
  - `0xd843d0(obj, &ret, cb, value, ...)`: 第 1 引数 obj の +0x50 sub-object が非 null かつ `0xd84f30(sub)` が偽なら何もしない (status -2 = 未適用)。それ以外は node を作り (`0xd841e0`)、value・stack 引数・cb (node+0x58) を格納して `0x526190` で投入する。`0xd84290` が node+0x58 の cb を呼ぶ。戻り status は node+0x60 (-2 = 未適用 / -4 = 途中 / 0 = 適用)。
  - 本 PR の 3 setter は、いずれも cb の中で書込む。cb の gate は `G = 0x15e8790` (UI 根オブジェクト) を起点にする。

## 確定した 3 関数 (PE 根拠・実装済み・値は持たない)

`G` = 絶対アドレス `0x15e8790`。

| 関数 | entry | fn (VA) | 形式 | 経路 (cb の中身) | 書込み先 | 変換 | 戻り型 (stub) | 実装の値 |
|---|---|---|---|---|---|---|---|---|
| `ui.setHintMsg` | 0x151b668 | 0xd6c5b0 | VARARGS `s` (flags 1) | `0x41c6e0` で std::string 化 → `0xd6fd10(self)` の obj → `0xd843d0(obj, &ret, cb=0xd6c570, value)`。cb は gate `0x11d1430` (`G→+8→vtbl[0x88]()` の真偽) が真なら `0x11f16b0(*[0x15e0ff8], value, 0)` | `0x11f16b0` 経由 (`[0x15e2eb8]→+0x858` 系を参照) | str → std::string | None | None (状態なし) |
| `ui.setFocused` | 0x151b788 | 0xd6ce50 | VARARGS `i` (flags 1) | `0xd6fd10` → `0xd843d0(obj, &ret, cb=0xd6cdf0, i)`。cb は `G→+8→vtbl[0x98]()` が真なら `G→+0x54` の sub-object の `vtbl[0x38](i を 1 byte に切り詰めた値)` | sub-object (`G→+0x54`) の vtbl 0x38 (getFocused の vtbl 0x28 と対。意味は未確定) | int → byte | None | None (状態なし) |
| `ui.setSnapMode` | 0x151b448 | 0xd6b7b0 | VARARGS `i` (flags 1) | `0xd6fd10` → `0xd843d0(obj, &ret, cb=0xd6b700, i)`。cb は gate `G→+8→vtbl[0x98]()` が真で、かつ `i ∈ 0..15` かつ 16bit マスク `0xd6b7a0` (値 0x7fff) のビット i が立つ場合のみ、`*([0x15e2eb8])+0xb18` の object の `vtbl[0x1f0](0x7a0d50(obj, i), 1)` を呼ぶ | `[0x15e2eb8]→+0xb18` の object | int | None | None (状態なし) |

- 有効域と status: `setSnapMode` の cb (`0xd6b700`) は、gate 偽なら status -2 のまま何もしない。gate 真なら status を -4 にしてから範囲検査 (`cmp eax, 0xf`・マスク `0x7fff` のビット i) に入り、i ∈ 0..14 で bit が立つときだけ書込み (`vtbl[0x1f0]`) を行い、status を 0 にする。i ∉ 0..14 (i = 15 を含む) では書込みをせず、status は -4 のまま終わる (逆アセンブル: `-2` を書く d6b709 → gate 通過で `-4` を書く d6b72f → 範囲検査が偽なら d6b75f から終了)。
- 3 関数とも PE の戻り値は None (戻り値の格納は共通経路の `&ret` で、Python には返さない)。
- 実装の仮置き: mock と C は型検査 (引数個数 1・setHintMsg は文字列・setFocused / setSnapMode は整数 (bool 可・None は 0)) のみ行い、状態を変えない。範囲外の挙動は実装していない (有効域チェックはしない)。

## 保留 1 件 `ui.snapMode` (子 #3719)

| 関数 | entry | fn (VA) | 確定した事実 | 未確定の点 | 子 issue |
|---|---|---|---|---|---|
| `ui.snapMode` | 0x151b468 | 0xd6b8d0 | flags 1 (VARARGS)・stub は int。PyArg `i` の後 `0xd84680(obj, &out, id=0x31, value=i, flag=0xfdd270(), 0xf)` → 内部で `0xfdd2c0(id, value, flag, 0xf)` | `0xfdd2c0` の意味 (読み書きの別・戻り値の範囲)。`0xd82c20` (戻り変換) の確認 | PY-242 (#3719) |

## 検証

測定 commit: `c7992ff5f` (コードを変えた最後の commit。`origin/main` の取り込み merge を 2 回行った)。1 回目 `3675aa412` (origin/main `091e4a7b6`): 衝突は `tests/provider_check.mjs` の 1 件で、PR 側の pe129 と main 側の pe132・pe138 の判定行を両方残して解消し、件数 assert を 174 / 261 にした。2 回目 `c7992ff5f` (origin/main `335955f3e`): 衝突 0 件 (`git merge-tree` で確認してから取り込み)。`host/fl_mock.mjs`・`provider/fl_engine.c`・`docs/DOC_MAP.md` は自動 merge で、同じキーや関数の二重定義が無いことを grep で確認した。取り込みで入った tools/python の差分 (host・provider・tests・analysis) は `git diff 5b2a9b8f6 c7992ff5f -- tools/python ':!*.md'` の範囲。CPython の入力 (`build_cpython_wasm.sh`・`build_flpy.sh`・`fetch_inputs.sh`・`analysis/flapi/flapi_table.json`) はこの範囲で変わっていない。CPython の wasm は本 worktree で初回ビルドし (native build を含む)、`3675aa412` 時点で測定した。それ以前の取り込み (`72ae6d066`・`a052f7390`・`ec8e7f897`) の衝突解消は、いずれも PR 側と main 側の両方を残した (Git 履歴に残る)。

環境: runner 4 core。`load` は各コマンドの終了直後の `/proc/loadavg` (1 分平均)。`toolchain-emsdk.tar.zst` は `$HOME/artifacts` に実在したが、`/opt/emsdk` (`emcc --version` = 6.0.12) が既にあって動作したため展開せず、そのまま使った (`build_cpython_wasm.sh`・`build_flpy.sh`・`provider/build.sh` は `/opt/emsdk` を直接 source する)。`fl-win64` は `tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin' '*block25159_DATA.bin' '*block24429_DATA.bin' '*block24430_DATA.bin' '*block24618_DATA.bin'` で必要分だけ展開し (`$RUNNER_TEMP/fl-win64/extracted/`)、`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` で `work/` に配置した。

| コマンド | 測定 commit | 結果 | wall | load |
|---|---|---|---|---|
| `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` | `3675aa412` | rc 0 (`work/` に MCPTools.pyc・midi.py・utils.py・device script を配置) | 0.285 秒 | — |
| `bash build_cpython_wasm.sh` | `3675aa412` | rc 0 (本 worktree での初回。native build を含む) | 245.9 秒 (4 分 05.9 秒) | 2.87 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | `c7992ff5f` | rc 0 | 6.008 秒 | 0.52 |
| `bash provider/build.sh` | `c7992ff5f` | rc 0・ハンドラ 174 (`fl_table.c`: 関数 435) | 1.460 秒 | 0.29 |
| `node tests/provider_check.mjs` | `c7992ff5f` | PASS (functions 435・実装 174・未実装 261・MCP 静的 60) | 0.363 秒 | 0.29 |
| `node tests/ui_state_diff.mjs` | `c7992ff5f` | calls 77・diffs 0・PASS (rc 0) | 0.051 秒 | 0.29 |
| `node tests/general_diff.mjs` | `c7992ff5f` | calls 41・diffs 0・PASS (rc 0) | 0.052 秒 | 0.29 |
| `node tests/ui_diff.mjs` | `c7992ff5f` | calls 17・diffs 0・範囲外既知差分 3・PASS (rc 0) | 0.051 秒 | 0.29 |
| `node tests/mixer_diff.mjs` | `c7992ff5f` | calls 69・diffs 0・PASS (rc 0) | 0.054 秒 | 0.29 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | `c7992ff5f` | 48/48 ok・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true (rc 0) | 2.171 秒 | 0.29 |

- `ui_state_diff.mjs` の calls 77 の内訳 (ここが正本): 通常呼出し 49 = ui ゲッター 14 + getFocused 3 + setter 3 件 13 (setHintMsg 4・setFocused 4・setSnapMode 5) + PY-130 分 19 (setBrowserAutoHide 6・setStepEditMode 4・getVersion 9)。引数個数違い 28 = ゲッター 14 + getFocused 2 + setter 3 件 6 + PY-130 分 6 (setBrowserAutoHide 2・setStepEditMode 2・getVersion 2)。PR 前 (main 取り込み前) の 52 (通常 30 + 個数違い 22) に、main の PY-130 分 25 (通常 19 + 個数違い 6) を足した数。
- 参考: PY-119 報告の `ui_state_diff` calls 12 は、現在のスクリプトの呼出し列と一致しない (PR 前の列は、ゲッター 17 + 個数違い 16 = 33 件と列から数えた値で、実行して測ったものではない)。PY-119 の件数は古いまま残っている (本 PR では訂正しない)。

ネガティブコントロール (`c7992ff5f`): `host/fl_mock.mjs` の `ui.setSnapMode` の引数個数検査 (merge 後は 427 行: `arity(a, 1, 1)`) を `arity(a, 1, 2)` に変えると、`node tests/ui_state_diff.mjs` は `AssertionError: ui 状態ゲッター差分 1 件` で rc 1 (FAIL)。元に戻すと calls 77・diffs 0・PASS (rc 0)。元に戻した後の `git diff -- tools/python/host/fl_mock.mjs` は空。`provider/*.wasm` は変えていない (mock のみの変更)。

## コード差分

- `host/fl_mock.mjs`: `ui.setHintMsg` (文字列検査)・`ui.setFocused` / `ui.setSnapMode` (整数検査) を PY-119 の ui 行の直後に追加。状態は持たない。
- `provider/fl_engine.c`: 同じ 3 関数を `FL_H(ui, ...)` で追加 (`NARGS(1, 1)` と `A_STR(0)` / `A_INT(0, 0)`、戻り `fl_ret_none`)。
- `tests/provider_check.mjs`: `pe129` の Set (3 件) と実装判定への追加。main 取り込みで入った判定行 (pe130・pe132・pe138・pl61) は両方残し、件数 assert は 174 / 261。
- `tests/ui_state_diff.mjs`: setter の呼出し列 (通常 13・引数個数違い 6) を追加。
- `analysis/flapi/pe_handler_probe.py`: VA 指定 (`0x...`) で任意の VA を逆アセンブルできるようにした。名前指定の動作は変えていない。

```
$ git diff c7992ff5f HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| setHintMsg / setFocused / setSnapMode の状態モデル (値を持たない。書込んだ値の読出し経路は未確定: getHintMsg の `[0x15e2eb8]→+0xbe8` と `0x11f16b0` の `+0x858` 系が同じ object か、getFocused の sub-object の読出し) | 書いた値を後で読めない。mock と C は getHintMsg / getFocused / getSnapMode を初期値で返す | 子 #3719 (PY-242) |
| setSnapMode の範囲外 (i ∉ 0..14)。gate 真では status -4 のまま書込み無し (`0xd6b75f`)。gate 偽は -2 のまま | 範囲外の status (-4) を Python 側の戻り変換 `0xd82c20` が例外・値のどれにするかが未確認。mock と C は範囲検査せず None を返す | 子 #3719 (PY-242) |
| snapMode (`0xfdd2c0` id 0x31) の意味・戻り型 | `ui.snapMode` は未実装 (Unspecified error) | 子 #3719 (PY-242) |
| 実装 3 件の値 (None・状態なし) は実機測定していない | 実機の戻り挙動は未確認 | 子 #3719 (PY-242) |
