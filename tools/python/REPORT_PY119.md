# tools/python REPORT: PY-119 ui 状態・フォーカス・文字列ゲッター 6 件の PE 確定と C provider 実装 (#2980, 親 #2831, 子 #3005 PY-128・#3006 PY-129・#3007 PY-130)

> 正本: `tools/python/REPORT_PY87.md` (前例・general 4 件)。前段の `REPORT_PY95.md` は main に無く、#2831 の 9 件の PE 確定は本 run の前提にできなかったため、18 件を本 run で逆アセンブルした。

## 結論

- #2831 の ui 69 件のうち、本 issue の **18 件** を逆アセンブルし、呼出し経路 (状態の所在・変換スロット・戻り型) を VA 付きで記録した。
- そのうち **6 件** は呼出し経路が確定したので mock と C provider に実装した (`ui.getFocused` / `ui.getFocusedFormID` / `ui.getFocusedFormCaption` / `ui.getFocusedPluginName` / `ui.getHintMsg` / `ui.isInPopupMenu`)。値は未実測の仮置きで、mock と C は同じ値を返す。mock と C の差分は 0 (`tests/ui_state_diff.mjs` 12 呼出し)。
- 残り **12 件** は未確定 (書込み先・内部関数の意味が未同定)。保留の理由を下表に書き、子 issue 3 件 (#3005・#3006・#3007) に分けた。
- 本 PR は issue の範囲を 6 件に縮めて `Closes #2980` とする (規範 11)。

## 手段

- ハンドラ探索: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <名前...>` (`block00031_PE.bin` のみ。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`)。PyMethodDef のエントリ VA と関数先頭 VA (`fn`) を得る。
- 逆アセンブル: 同じ probe の先頭 40 命令。RIP 相対の絶対アドレスは `次命令 + disp` で求めた。
- 戻り型・引数形式: 公開 stub (`analysis/flapi/flapi_table.json` の `sig.returns` / `kwsig.fmt`)。
- 変換スロット: int / bool の変換は 4 関数とも絶対アドレス `0x15e4280` (PY87 と同じ)。str の変換は `0x15e3d50`。

## 確定した 6 関数 (PE 根拠・実装済み)

`G` = 絶対アドレス `0x15e8790` (UI 根オブジェクトへのポインタ)。`G→+0x54` の object を以下では「sub-object」と呼ぶ。

| 関数 | entry | fn (VA) | 形式 | 読む経路 | 変換 | 戻り型 (stub) | 実装の値 |
|---|---|---|---|---|---|---|---|
| `ui.getFocused` | 0x151b768 | 0xd6cd80 | VARARGS `i` | `PyArg("i")` で index を得て `sub-object.vtbl[0x28](index)` (index は `movzx` で 1 byte に切り詰めて渡す) | bool `0x15e4280` | bool | `false` |
| `ui.getFocusedFormID` | 0x151b6c8 | 0xd6ca80 | NOARGS | `sub-object.vtbl[0x18]()` | int `0x15e4280` | int | `0` |
| `ui.getFocusedFormCaption` | 0x151b6a8 | 0xd6c9d0 | NOARGS | `sub-object.vtbl[0x10](&out)` → `0x41c420` → `0x414000` | str `0x15e3d50` | str | `""` |
| `ui.getFocusedPluginName` | 0x151b6e8 | 0xd6cab0 | NOARGS | `sub-object.vtbl[0x20](&out)` → `0x41c420` → `0x414000` | str `0x15e3d50` | str | `""` |
| `ui.getHintMsg` | 0x151b648 | 0xd6c4c0 | NOARGS | `[G2]` の object を `0x11f1940(obj, &out)` → `0x41c420` → `0x414000` | str `0x15e3d50` | str | `""` |
| `ui.isInPopupMenu` | 0x151b848 | 0xd6d6b0 | NOARGS | `0x728f40()` の戻り (al) | bool `0x15e4280` | bool | `false` |

- 値の根拠は無い (仮置き)。mock の値を正として扱わないこと。
- 形式と戻り型は PE と stub が一致した。`getFocused` の index は PE で byte に切り詰められる (上位ビットを落とす)。実機で範囲外の index がどう扱われるかは未確認。

## 保留 12 関数 (未確定・子 issue へ)

| 関数 | entry | fn (VA) | 確定した事実 | 未確定の点 | 子 issue |
|---|---|---|---|---|---|
| `ui.getFocusedNodeCaption` | 0x151ba68 | 0xd6e470 | flags 4 (NOARGS)。stub は str | 本体は未逆アセンブル | PY-128 (#3005) |
| `ui.getFocusedNodeFileType` | 0x151ba48 | 0xd6e400 | flags 4 (NOARGS)。stub は int | 本体は未逆アセンブル | PY-128 (#3005) |
| `ui.getHintValue` | 0x151b708 | 0xd6cb60 | `ii` (value, max)。`0x11f1a70(obj, &out, value, max)` → str | `0x11f1a70` の意味 | PY-128 (#3005) |
| `ui.getProgTitle` | 0x151b608 | 0xd6c250 | NOARGS。rodata 0xd6c2c4 の 1 字 `F` を `0x41c420` に渡す | 1 字がタイトル全体か断片か、`0x41c420` の引数規約 | PY-128 (#3005) |
| `ui.setHintMsg` | 0x151b668 | 0xd6c5b0 | `s` → `0x41c6e0` で std::string 化 → `0xd6fd10(self)` の obj → `0xd843d0` で書込み | 書込み先フィールドと `0xd843d0` の意味 | PY-129 (#3006) |
| `ui.setFocused` | 0x151b788 | 0xd6ce50 | `i` → `0xd6fd10` → `0xd843d0` で書込み | 同上 | PY-129 (#3006) |
| `ui.setSnapMode` | 0x151b448 | 0xd6b7b0 | `i` → `0xd6fd10` → `0xd843d0` で書込み | 同上 | PY-129 (#3006) |
| `ui.snapMode` | 0x151b468 | 0xd6b8d0 | `i` → `0xd6fd10` → `0xd84680` → `0xd82c20` | `0xd84680` の意味 | PY-129 (#3006) |
| `ui.setBrowserAutoHide` | 0x151baa8 | 0xd6ee00 | flags 1 (VARARGS)。stub は bool 引数 | 本体は未逆アセンブル | PY-130 (#3007) |
| `ui.setStepEditMode` | 0x151bb08 | 0xd6f170 | flags 1 (VARARGS)。stub は bool 引数 | 本体は未逆アセンブル | PY-130 (#3007) |
| `ui.setTimeDispMin` | 0x151b748 | 0xd6ccb0 | flags 4 (NOARGS) だが本体は `0xd6fd10` → `0xd843d0` を呼ぶ | stub の doc は getter 風・`returns None`・`params []` で、kwsig と食い違う | PY-130 (#3007) |
| `ui.getVersion` (ui 版) | 0x151b628 | 0xd6c2f0 | `\|i` (mode、既定 4)。mode の値で分岐する | 分岐表 (どの mode で str / int を返すか) | PY-130 (#3007) |

- `0xd6fd10` (self → object) と `0xd843d0` は setter 群の共通経路。どちらかの意味が分かれば PY-129 の 4 件をまとめて確定できる見込み。
- general 版 `getVersion` (entry 0x151ac20) は本 issue の対象外 (`general.getVersion` は既に実装済み)。

## 検証

測定 commit: `ea4e82ac` (コードを変えた最後の commit。origin/main `940c0d6a` (PR #3004 まで) 取り込みの merge。`tests/provider_check.mjs` は main 側 `pe100`・`pe115` と本 PR の `pe119` を合算: 実装 92 / 未実装 343)。測定は同 commit のクリーンな作業ツリー (`git status` 空) で、`provider/build.sh` を再実行してから行った。

環境: runner 4 core、測定時の load average 0.73 (`uptime`、21:20:21)。`FL_WIN64_DIR` は `$RUNNER_TEMP/fl-win64` (`fl-win64` の `block00031_PE.bin`・`block24429/24430/25159/24618_DATA.bin` を展開)。`toolchain-emsdk` は [EMSDK] (`docs/REFERENCES.md`) の既定位置を使った。前提の生成物 (gitignore): `fetch_inputs.sh` (rc 0)・`build_cpython_wasm.sh` (rc 0、21:13:42〜21:16:50 の 188 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0。merge 後に再ビルド)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 92 (86 + 6) | 0.71 秒 (emcc キャッシュ済み) |
| `node tests/provider_check.mjs` | PASS (435 / 実装 92 / 未実装 343 / MCP 静的 60) | 0.26 秒 |
| `node tests/ui_state_diff.mjs` (新規) | calls 12、diffs 0、PASS | 0.03 秒 |
| `node tests/general_diff.mjs` | calls 9、diffs 0、PASS | 0.04 秒 |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 0.03 秒 |
| `node tests/mixer_diff.mjs` | calls 57、diffs 0、PASS | 0.04 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.26 秒 |

ネガティブコントロール: `host/fl_mock.mjs` の `ui.getFocusedFormID` の既定値を `0` から `1` にすると、`node tests/ui_state_diff.mjs` は `AssertionError [ERR_ASSERTION]: ui 差分 1 件` で rc 1 (FAIL)。元に戻すと calls 12・diffs 0・PASS (rc 0)。HEAD (`ea4e82ac`) で再現。

コード差分 (測定 commit から PR HEAD まで、`tools/python` の .md 以外):

```
$ git diff ea4e82ac HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実装 6 件の値 (仮置き) | 実機と異なる。mock の値を正として扱わない | 親 #2831 の残件として追跡 (実機測定の方式は PM 判断) |
| `getFocused` の index を byte に切り詰める挙動の範囲外確認 | 範囲外 index の実機挙動が未確認 | 親 #2831 の残件として追跡 |
| 保留 4 件 (getFocusedNodeCaption / getFocusedNodeFileType / getHintValue / getProgTitle) | 未実装 | PY-128 (#3005) |
| 保留 4 件 (setHintMsg / setFocused / setSnapMode / snapMode) | 未実装。`0xd843d0` の意味が前提 | PY-129 (#3006) |
| 保留 4 件 (setBrowserAutoHide / setStepEditMode / setTimeDispMin / getVersion (ui)) | 未実装。setTimeDispMin は stub と kwsig の食い違いも含む | PY-130 (#3007) |
