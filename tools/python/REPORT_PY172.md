# PY-172 (#3219): patterns グループ系 4 関数の PE 解析と C/mock 実装 (2 件)

親: #1804 (PY-48)。既知類型との関係: 該当なし (lift 作業ではない)。
測定対象の commit: `6b8dc5a9d` (main (`a5966bbc7`) 取り込みの merge。競合解消を含む。コードを変えた最後の commit)。

## 結論

- 4 関数の引数・戻り型・範囲検査・エラー code を fl-win64 (26.1.7.5653 `block00031_PE.bin`) の PE から確定した (§1)。
- 索引基準: `getPatternGroupName` は 0 始まり (`0 ≤ i ≤ 件数-1`)。`getPatternsInGroup` は範囲 `[-1, 件数-1]` を検査し、索引をパターン構造体の先頭 dword と直接比較する。索引に 1 を足す・引く処理は無い (§2)。
- `getPatternsInGroup` の索引 `-1` は範囲検査を通るが、特別扱いの分岐は PE に無い。REPORT_PY42 の「現在のグループ」という推定は PE からは支持されない (§2)。
- 実装 (C provider と mock): `getPatternGroupCount` (戻り 0) と `getPatternGroupName` (全索引が code 4)。件数 0 は仮置き (§3)。
- 未実装 2 件: `getActivePatternGroup` (グローバル int の値が未確定)・`getPatternsInGroup` (索引 -1 の意味と群番号の既定値が未確定)。子 #3278 (PY-180) に分離 (§5)。
- 訂正: REPORT_PY42 の「署名の不一致 3 件」は古い記述。現在の `flapi_table.json` は 3 件とも PyArg 書式と一致する (§4)。

## 1. 関数ごとの確定事項

PE の VA は `pe_disasm.py` が出す値 (REPORT_PY42 と同じ表記)。書式 `i` は `flapi_table.json` の kwsig `fmt` と一致。

| 関数 | 引数 | 戻り型 | 範囲・分岐 | 根拠 VA | 未確定 |
|---|---|---|---|---|---|
| getActivePatternGroup | なし | int (グローバル int を整数化・検査なし) | なし | 0xd66fe0〜0xd66ffa | グローバルの値と意味 |
| getPatternGroupCount | なし | int | 配列 null なら 0、非 null なら `[ptr-8]` の下位 32bit | 0xd67000〜0xd67026 | 配列の実状態 (§3) |
| getPatternGroupName | `"i"` 1 個 | str | `0 ≤ i ≤ 件数-1`、外は status -4 (Index out of range)。PyArg 失敗は 0xd82c20 経由 | 0xd67030〜0xd670e5 | 要素の名前の実値 |
| getPatternsInGroup | `"i"` 1 個 | tuple | `-1 ≤ i ≤ 件数-1`、外は status -4。範囲内は走査して結果を返す | 0xd67110〜0xd671ec | 索引 -1 の意味・群番号の既定値 |

補足 (根拠):
- getPatternGroupCount: 配列ポインタ G は `[rip+0x87a8ed]` の先の値。`mov rax,[rax-8]` は 64bit 読み、`mov ecx,eax` で int として渡す。
- getPatternGroupName: 件数との比較は 64bit (`lea rax,[rax-1]` の後 `cmp rcx,rax`)。要素は `[rax + rdx*8]` (8 バイト・ポインタ) を 0x41c420 → 0x414000 で文字列化し、PyUnicode 系の間接呼出しで返す。0x41c420・0x414000 の名称は未同定。
- getPatternsInGroup: 件数 0 のとき範囲は `[-1, -1]` になり、索引 -1 だけが通る。ループは ebx = 0..999 (`cmp ebx,0x3e8`)、要素は `[G2+0x10 + ebx*0xc0]` (ストライド 192 バイト)。先頭 dword が索引と等しいなら、添字 ebx を list に追加する (0xd67181〜0xd671b3)。ループ後に list を tuple 系の間接呼出しで返す (0xd671c6〜0xd671d2)。間接呼出しの名称 (PyList/PyTuple 系) は未同定。

## 2. 索引基準

- getPatternGroupName: 0 始まり。索引は配列の添字として直接使われる (0xd67078〜0xd6709c)。1 始まりへの変換は無い。
- getPatternsInGroup: 索引は「パターン構造体先頭の群番号」と直接比較される (0xd67185 `cmp eax, [rbp+0x2c]`)。群番号の基準 (0 始まりか 1 始まりか) は構造体の値の付け方に依存し、PE だけでは確定できない。索引 0 始まりの添字と混ぜる変換は無い。
- 索引 -1: 範囲検査 (0xd67157 `cmp rcx,-1; jl`) を通るが、-1 専用の分岐は無い。-1 を指す群番号を持つ構造体だけが一致する。「現在のグループ」を意味するかは PE の範囲では確定できず、推測実装しない (未解決表)。
- 対比 (本件の外): REPORT_PY42 の getPatternName・getPatternColor・getPatternLength は `0..999`、isPatternDefault は `1..999`、isPatternSelected は `index-1`。関数ごとに基準が違う問題は REPORT_PY42 の未解決に残す (#1804 の残り)。

## 3. 実装 (C provider と mock)

- `provider/fl_engine.c`: `getPatternGroupCount` は `fl_ret_i(PGRP_N)`、`getPatternGroupName` は `NARGS(1,1)` + `A_INT(0,0)` の後に範囲外なら `RANGE()` (code 4)。
- `host/fl_mock.mjs`: 同じ意味論を `PGRP_N` (= 0) で持つ。
- **件数 0 は仮置き**: 配列 ptr が null の経路 (0xd67000) を既定とみなした。FL 起動直後のグループ配列の実状態は未実測。公開 API (flapi_table の patterns 群) にグループを変える関数は無く、件数は API から変えられない。件数が 0 でなければ、`getPatternGroupName` の成功経路 (返す名前) は未モデル。
- 返す名前は空文字列 (成功経路は件数 0 では到達しないため、値は未定義)。

## 4. 訂正 (REPORT_PY42)

REPORT_PY42 は「署名の不一致 3 件 (getPatternGroupName・getPatternsInGroup・getChannelLoopStyle)」を挙げていた。`analysis/flapi/flapi_table.json` の現状:

- getPatternGroupName: sig `index: int`・kwsig `fmt: i`。PE の `"i"` と一致。
- getPatternsInGroup: sig `index: int` (戻り `tuple[int, ...]`)・kwsig `fmt: i`。PE の `"i"` と一致。
- getChannelLoopStyle: sig `pattern: int, channel: int`・kwsig `fmt: ii`。PE の `"ii"` と一致。

よって 3 件とも解消済み。REPORT_PY42 の該当行に訂正を追記した (行の削除はしない)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| getActivePatternGroup のグローバル int の値と意味 | 未実装 (C・mock とも code 2) | #3278 (PY-180) |
| getPatternsInGroup の索引 -1 の意味と、パターン構造体の既定の群番号 | 未実装 (code 2)。`-1` の結果は未定義 | #3278 (PY-180) |
| グループ配列の実状態 (件数 0 の仮置きが FL の既定値か) と、群名の実値 | getPatternGroupCount・getPatternGroupName の値は仮置き | #3278 (PY-180) |
| 群番号の基準 (0 始まりか 1 始まりか) | getPatternsInGroup の結果の解釈 | #3278 (PY-180) |
| REPORT_PY42 の索引基準の不統一 (getPatternName 等 0..999 と isPatternDefault 1..999) | PY-42 の 11 関数の残り | #1804 の残り |

## 6. 測定

測定 commit: `6b8dc5a9d` (main (`a5966bbc7`) を merge。競合は `tools/python/tests/provider_check.mjs` の 1 件。main 側の `pe120` (launchMapPages.length・実装 +1) と PR 側の `pe172` (+2) の両方を残した。件数は main 側 141 / 294 に pe172 の +2 / −2 を足して **143 / 292**)。前回の測定 (`51e3a96c`・`235f9cca`・`37e37e00`) は置き換えた。`work/` は gitignore 対象のため worktree に無く、`fetch_inputs.sh` と `build_cpython_wasm.sh` を再実行した。flpy と provider は測定 commit の tree で再リンクした。

| 検査 | 手順 (コマンド) | 結果 |
|---|---|---|
| 素材 | `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` (展開前に `$ARTIFACTS_DIR` の実在を ls で確認) | rc 0・5.7 秒 |
| emsdk | runner 既設の `[EMSDK]` (`source $EMSDK_DIR/emsdk_env.sh`) | `emcc --version` = 6.0.12 (`tools/m1/flags.sh` の pin と一致)。`toolchain-emsdk` 素材は展開していない |
| 入力 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` | rc 0・0.4 秒 |
| CPython wasm | `bash build_cpython_wasm.sh` | rc 0・wall 4 分 10 秒 |
| flpy リンク | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0・6.1 秒 |
| provider ビルド | `bash provider/build.sh` | rc 0・1.3 秒。`fl_table.c`: 435 関数・ハンドラ **143** |
| all_tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | rc 0・2.2 秒・**48/48 ok** (`soft_error` 0・`raised` 0・`no_args` 0・`host_calls` 37425・`callback_roundtrip` true) |
| provider_check (Python 型節を含む通常版) | `node tests/provider_check.mjs` | rc 0・0.5 秒・PASS。`functions` 435・実装 **143** / 未実装 **292** (MCP 60) |
| 差分検査 | `node tests/patterns_group_diff.mjs` | rc 0・14 呼出し・diffs 0・PASS |
| 差分検査 | `node tests/general_diff.mjs` | rc 0・41 呼出し・diffs 0・PASS |
| 差分検査 (main 由来の追加) | `node tests/launchmap_diff.mjs`・`ilmcp_e2e.mjs`・`midi_bundled_device.mjs`・`midi_script.mjs` | 全て rc 0。launchmap_diff 3 呼出し・diffs 0・PASS。ilmcp_e2e PASS。midi_bundled_device OK。midi_script OK |
| mock 差分 (flpy 不要の 15 本) | `node tests/<name>.mjs` (arrangement_diff・arrangement_selection_diff・channels_diff・device_diff・ilmcp_diff・midi_path_diff・mixer_diff・playlist_diff・screen_diff・tool_args・transport_diff・ui_diff・ui_display_diff・ui_state_diff・step_item_diff) | 全て rc 0・diffs 0 (呼出し数: arrangement 25・channels 170・ui_state 33・step_item 5929 ほか。tool_args は標準出力なし・rc 0) |
| 未実行 | `node tests/chord_progression_e2e.mjs` | rc 1。テスト本体に入る前に `work/fl_extract/` が無いことで止まる (FL の Python 展開物が本 run の素材に無い前提不足。この merge の差分とは無関係) |

測定時の load average は 2.2〜2.5 (`uptime`)。

コード差分の確認 (差分 0 の証跡):

```
git diff 6b8dc5a9d HEAD -- tools/python/provider tools/python/host tools/python/tests
```

この commit 以降の変更は REPORT のみ。出力は 0 行。

## 検証範囲 / 範囲外

- 範囲内: 4 関数の PE 解析 (引数書式・範囲検査・戻り型・status)、件数 0 の仮置きでの C と mock の一致、既存の provider_check と all_tools。
- 範囲外: 群の実値 (件数・名前・群番号)・`getActivePatternGroup`・`getPatternsInGroup` の結果。実機の FL を動かした確認は行っていない (PE の静的解析のみ)。
- 製品 KPI: 起動・GUI に関わらないため記載しない。
