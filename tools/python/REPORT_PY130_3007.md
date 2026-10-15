# tools/python REPORT: PY-130 ui setter 2 件と ui 版 getVersion の PE 確定と C provider 実装 (#3007, 親 #2980・PY-119)

> 正本: `tools/python/REPORT_PY119.md` (保留 4 件の一覧)・`tools/python/REPORT_PY119_2977.md` (同形の setter・dispatch と status 表)・`tools/python/REPORT_PY95.md` (getter 側の所在)。

## 結論

- 保留 4 件のうち **3 件**を実装した: `ui.setBrowserAutoHide` (確定)・`ui.setStepEditMode` (状態の所在は確定、末端の書込みは未確定)・`ui.getVersion` (ui 版、mode の型分岐は確定・値は仮置き)。mock と C の差分は 0 (`tests/ui_state_diff.mjs` 58 呼出し)。
- **`ui.setTimeDispMin` は保留**。callback は値を使わず、getter `getTimeDispMin` が読む field とは別の global byte を toggle するだけ。getter と整合する状態モデルを PE から立てられないため、未実装のまま子 issue に分けた。
- HEAD (測定 commit `3b74a1077`・main 再取り込み後) の実測: `provider/build.sh` rc 0・ハンドラ 165。`ui_state_diff` 58 呼出し diffs 0 PASS・`ui_diff` 17 呼出し diffs 0 PASS (いずれも wasm)。flpy 不要の 20 本は全件 rc 0・diffs 0。
- 未実行: `tests/provider_check.mjs` の section 3 以降と `FL_ENGINE=wasm node tests/all_tools.mjs` (48/48)。`dist/flpy.js` (CPython wasm) と flapi_table の生成が要り、本 run の時間内に収まらなかった (§検証 の『HEAD 再測定』)。

## 手段

- ハンドラ探索: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py setBrowserAutoHide setStepEditMode setTimeDispMin getVersion`。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'`。
- 逆アセンブル: `python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (callback・共通経路)。
- 共通の経路 (REPORT_PY119_2977 と同形): wrapper → `0xd6fd10(self)` で engine の object を得る → 共通 dispatch `0xd843d0(obj, temp, callback, 0, value, 0..., 1)` → callback が書込む → status を `0xd82c20` で Python 値へ変換。gate は `G = 0x15e4790` の `[[G]]+8` の vtbl[0x98] (PY-119_2977 と同じく真と仮定)。

## 確定表 (PE VA)

| 関数 | entry | wrapper fn | callback | 引数 | 書込み先・読出し先 (getter) | 状態の意味 | 実装 |
|---|---|---|---|---|---|---|---|
| `ui.setBrowserAutoHide` | 0x151baa8 | 0xd6ee00 | 0xd6ed70 | `i` (PyArg) | `O = *(*0x15e4b10)` の `byte [O+0x8c4] = (v == 1)`。getter `isBrowserAutoHide` (0xd6ed40) は同じ slot 0x15e4b10 から同じ `[O+0x8c4]` を読む | bool。値が 1 のときだけ真、他は偽。範囲検査は無い | 実装 |
| `ui.setStepEditMode` | 0x151bb08 | 0xd6f170 | 0xd6f0f0 | `i` | `S = [O+0xab8]` (O は slot 0x15e2eb8 から)。getter `getStepEditMode` (0xd6f0c0) と同じ `byte [S+0x49e]` を読む。書込みは `byte [S+0x49e] != (v==1)` のとき `0x737640(S, v==1, 1)` | bool | 実装 (末端は下記) |
| `ui.getVersion` (ui 版) | 0x151b628 | 0xd6c2f0 | — | `\|i` (既定 4) | mode 0..3: `word [X+0x20/0x22/0x24/0x26]` (X は runtime の版情報)。mode 4..6: 3 種の global 文字列 (`0x41c420`→`0x414000`→str 化)。他の mode: `eax = 0` のまま int 0 | int (0..3・他) / str (4..6) | 実装 (値は仮置き) |
| `ui.setTimeDispMin` | 0x151b748 | 0xd6ccb0 | 0xd6cc60 | なし (flags 4 NOARGS・PyArg 無し) | callback は値を読まない。gate 真なら `call 0x12491c0()`。0x12491c0 は `byte [0x16bc9f2] = ([0x16bc9f2] == 0)` (toggle) と `0x1248ac0`・`0x12e2ac0`・`0xfdee80` を呼ぶ | 不明 (toggle の先は未追跡) | **保留** |

### 補足

- `setBrowserAutoHide` の callback は書込みの前に `0x107f310(O, v==1, 0)` を呼ぶ。効果は未追跡だが、API からは観測できない (副作用の一種として記録)。
- `setStepEditMode` の末端: `0x737640(S, dl=v==1, r8b=1)` は `byte [S+0x49e] == dl` なら何もしない。異なるときは `call [vtbl(S)+0x200](S)` (dl は渡したまま) を呼び、`r8b != 0` なら `0x40ffe0(S, 0xffeb)` の関数を `S` に対して呼ぶ。**`[S+0x49e]` に dl を書くのは vtbl[0x200] の先の関数で、S の型が未同定のため確定できない。** 実装は「getter の field に v==1 を入れる」model で、末端は未確定。
- `getVersion` (ui) の mode 0..6 以外は、C 側の `xor eax,eax` (0xd6c330) のまま 0xd6c464 の int 変換へ進む。例外経路は引数解析失敗 (`jle 0xd6c475`) のみ。
- 値の仮置き: int は 0、str は `""` (実値の X は runtime のため未実測)。

## 保留: setTimeDispMin (stub と kwsig の食い違い)

- kwsig (`analysis/flapi/flapi_kwargs.json` の `setTimeDispMin`: flags 4・fmt null) と PE は一致する (引数を読まない・None を返す)。
- 食い違っているのは説明文。stub の doc は getter 風だが、本体は引数なしの toggle (0x12491c0)。説明文を PE に合わせる作業は未実施。
- getter 側の `getTimeDispMin` (0xd6cc40, PY-95) は slot 0x15e1e40 の object の `byte [C]` を読む。toggle の先 (0x16bc9f2) と読出し field の関係は未確定のため、mock の状態を結び付けない。

## 実装

- `host/fl_mock.mjs`: `ui.setBrowserAutoHide` (`st.uiBrowserAutoHide = (v === 1)`)・`ui.setStepEditMode` (`st.uiStepEdit = (v === 1)`)・`ui.getVersion` (mode 4..6 → `""`、他 → `0`)。引数検査は既存の `arity`/`argI` (PY-119 と同じ)。
- `provider/fl_engine.c`: 同じ 3 関数 (`NARGS(1,1)`・`NARGS(0,1)`・`A_INT(0, 4)` の既定 4)。
- `tests/ui_state_diff.mjs`: 本 PR で 25 呼出しを追加 (setter → getter の順で状態の一致を見る 19 件と、引数個数違い 6 件)。追加前は 33 呼出し、追加後 58 呼出し。
- `tests/provider_check.mjs`: `pe130` 集合を追加し、取り込み前 (PR 作成時) は 実装 155 → 158・未実装 280 → 277 とした (総数 435 は不変)。main 取り込み後の現行値は 実装 165・未実装 270 (§検証 の『HEAD 再測定』)。

## 検証

測定 commit は節ごとに書く。現行 (最新) の測定は『HEAD 再測定』節 (測定 commit `3b74a1077`)。以下の 2 節は履歴。

環境: runner 4 core。素材は `$ARTIFACTS_DIR` の `fl-win64.tar.zst`・`toolchain-emsdk.tar.zst` を確認済み。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` に `block00031_PE.bin` と `block24429/24430/25159/24618_DATA.bin` を展開し、`fetch_inputs.sh` (rc 0) で `work/` を作った。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 158 (emcc キャッシュ済み) | 1.47 秒 |
| `node tests/ui_state_diff.mjs` | calls 58、diffs 0、PASS | 未計測 |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 未計測 |
| `node tests/provider_check.mjs` | **未実行**: `dist/flpy.js` が無く起動できない (`build_cpython_wasm.sh` が必要・本 run の時間内に収まらなかった) | — |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **未実行**: 同上 (`work/midi.py` は生成済み・`dist/flpy.js` が無い) | — |

- ネガティブコントロール: 未実施 (時間不足)。
- コード差分 (取り込み前の測定 commit `0dd1d67c8` から PR 作成時の HEAD `9692b214a` まで、`tools/python` の .md 以外): 空。(取り込み後の範囲は main の変更を含むため、下の節で別に測る。)

```
$ git diff 0dd1d67c8 9692b214a -- tools/python ':!*.md'
(空)
```

### main 取り込み後 (測定 commit `d0e81d2f8`・履歴。現行は『HEAD 再測定』)

`origin/main` (`1bb93134e`) を merge した。競合は `tests/provider_check.mjs` の 1 箇所だけで、PR 側の `pe130` 条件式と main 側の `pl61` 条件式を両方残し、件数の期待値を 158/277 → 165/270 に直した。自動マージされた `provider/fl_engine.c`・`host/fl_mock.mjs`・`docs/DOC_MAP.md` は PR 側の変更が残っていることを確認した。

| コマンド | 結果 |
|---|---|
| `python3 provider/gen_provider.py --check-handlers provider/fl_engine.c` | rc 0・`fl_table.c 435 関数, ハンドラ 165` |
| `gcc -fsyntax-only -Wall -Wextra` (`fl_dispatch.c` `fl_engine.c`、`gen/fl_table.c` も同様) | rc 0・警告 0 |
| `node --check` (`host/fl_mock.mjs`・`tests/provider_check.mjs`・`tests/ui_state_diff.mjs`) | 3 件とも OK |
| provider_check の件数を、テストの `if` 条件式に現れる集合の和集合から再計算 | impl 165・unimpl 270 (総数 435)。同じ方法で HEAD 版 158/277・main 版 162/273 を再現 |
| mock の直接呼出し (`createMockEngine().call`) | `setBrowserAutoHide(1)` → `isBrowserAutoHide` = true・`setStepEditMode(1)` → `getStepEditMode` = true・`getVersion()` = `""` (mode 4)・mode 9 → `0`・引数 2 個 → code 5 |
| `EMSDK_ENV=<emsdk の emsdk_env.sh> bash provider/build.sh` (emsdk latest = emcc 6.0.12 を新規 install) | rc 0・警告 0・ハンドラ 165 | 1.43 秒 |
| `node tests/ui_state_diff.mjs` | calls 58・diffs 0・PASS | 0.057 秒 |
| `node tests/provider_check.mjs` | 134 行目の `work/midi.py` が無く rc 1 で停止。それまでの assert (件数 165/270 の 83 行目を含む) は通過。section 3 以降は `dist/flpy.js` が要る | 0.063 秒 |
| flpy 不要のテスト 20 本 (`ui_diff` `ui_display_diff` `playlist_diff` `mixer_diff` `general_diff` `device_diff` `channels_diff` `patterns_diff` `transport_diff` `arrangement_diff` `screen_diff` `launchmap_diff` `tool_args` `ilmcp_diff` `midi_path_diff` `note_enum_diff` `step_item_diff` `patterns_group_diff` `arrangement_selection_diff`) | 全件 rc 0。`diffs` は全て 0 (例: ui_diff calls 17・playlist_diff 72・channels_diff 214・note_enum_diff 33264) | 未計測 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **未実行**: `dist/flpy.js` (CPython wasm・`build_cpython_wasm.sh`) が無い | — |

取り込み後のコード差分 (`d0e81d2f8` から HEAD まで、`tools/python` の .md 以外): 空 (本節は md のみ)。

```
$ git diff d0e81d2f8 HEAD -- tools/python ':!*.md'
(空)
```

### HEAD 再測定 (測定 commit `3b74a1077`・main 再取り込み後)

測定 commit `3b74a1077` は `origin/main` (`bb0f61949`) を merge した commit。この commit で `tools/python` のコードを最後に変えた。

環境: runner 4 core・load 0.19 (03:54 時点)。`$ARTIFACTS_DIR` には `fl-win64.tar.zst` のみ (`toolchain-emsdk` は無し)。emsdk は upstream から `./emsdk install latest` で入れた (emcc 6.0.12)。fl-win64 の `extracted/` から `block24429/24430/25159/24618_DATA.bin` を取り、`work/midi.py`・`work/utils.py`・`work/MCPTools.pyc`・device script を配置した (`fetch_inputs.sh` の win64 分岐の抜粋)。`block00031_PE.bin` と fl-stubs は取得していない (flpy 経路の未実行の理由)。

| コマンド | 結果 | wall |
|---|---|---|
| `EMSDK_ENV=<emsdk>/emsdk_env.sh bash provider/build.sh` | rc 0・警告 0・ハンドラ 165 (`gen_provider.py --check-handlers` も 165) | 1.61 秒 |
| `node tests/ui_state_diff.mjs` (wasm) | calls 58・diffs 0・PASS | 0.04 秒 |
| `node tests/ui_diff.mjs` (wasm) | calls 17・diffs 0・範囲外既知差分 3・PASS | 0.05 秒 |
| `node tests/provider_check.mjs` | 第 1〜2 節 PASS (件数 assert impl 165・unimpl 270 を含む)。第 3 節 (`dist/flpy.js` の読込) で `ERR_MODULE_NOT_FOUND` により rc 1 | 0.06 秒 |
| flpy 不要の 20 本 (`ui_display_diff` `playlist_diff` `mixer_diff` `general_diff` `device_diff` `channels_diff` `patterns_diff` `transport_diff` `arrangement_diff` `screen_diff` `launchmap_diff` `tool_args` `ilmcp_diff` `midi_path_diff` `note_enum_diff` `step_item_diff` `patterns_group_diff` `arrangement_selection_diff`) | 全件 rc 0・diffs 0 (例: ui_display_diff ok 12・bad 11、note_enum_diff calls 33264・nonempty 5869、channels_diff calls 231) | 各 1 秒未満 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **未実行**: `dist/flpy.js` (CPython wasm・`build_cpython_wasm.sh` と `build_flpy.sh`) が無い。48/48 は未検証 | — |

- ネガティブコントロール: 未実施 (時間不足)。
- 件数の内訳: 実装 165 = MCP 60 + device 5 + mig 5 + pe39 1 + pe40 5 + pe102 1 + stub41 6 + pe101 2 + pe100 2 + stub89 2 + pe87 4 + pe94 7 + pe95 9 + pe96 4 + pe115 1 + pe121 5 + pe119 6 + pe119set 6 + pe152 6 + pe121_2982 6 + pe125 2 + pe120 1 + pe76 1 + pe172 2 + pl61 7 + pe179 4 + pe205 2 + pe130 3 (= 本 PR の 3 件)。未実装 270 = 435 − 165。

コード差分 (測定 commit から HEAD まで、`tools/python` の .md 以外):

```
$ git diff 3b74a1077 HEAD -- tools/python ':!*.md'
(空。HEAD は REPORT の md 更新のみ)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ui.setTimeDispMin` の実装 (toggle 0x16bc9f2 の先と、getter の field との関係) | 未実装のまま。getVersion と setter 2 件とは別作業 | #3706 |
| `setStepEditMode` の書込み末端 (`vtbl[0x200]` の先・S の型) | `[S+0x49e]` への書込みは model 上の仮定 | #3706 |
| `setBrowserAutoHide` の notify `0x107f310`・`setStepEditMode` の `0x40ffe0` 通知 | API から観測不能 | 親 #2831 の残件として追跡 |
| `getVersion` (ui) の値 (X の word 群・3 種の文字列) | 仮置き。実機と異なる | 親 #2831 の残件として追跡 |
| `provider_check.mjs` の section 3 以降・`all_tools.mjs` (flpy 経路) の未実行 | 48/48 は未検証。件数 165/270 の assert は HEAD `3b74a1077` で通過 | PM 判断 (再測定のみのため子 issue は起票しない。CPython wasm と flapi_table の用意後に別 run で再測定) |
| 説明文の食い違い (`setTimeDispMin` の stub doc) | 説明文のみ | #3706 |
