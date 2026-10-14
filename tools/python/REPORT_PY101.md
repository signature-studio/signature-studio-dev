# PY-101 (#2878): channels.isGridBitAssigned・getGridBitWithLoop の PE 経路と実装

既知類型との関係: 該当なし (逆アセンブル解釈と mock/C の照合。`docs/DEFECTS.md` の lift 欠陥類型には当たらない)。

## 結論

- `channels.isGridBitAssigned` と `channels.getGridBitWithLoop` を C provider (`provider/fl_engine.c`) と mock (`host/fl_mock.mjs`) に実装した。`tests/channels_diff.mjs` は diffs 0。
- `+0x7ac` (channel の grid 構造体ポインタ) の生成元を PE で読んだ。直接 call の範囲では grid は生成時に作られ、null 経路 (status 0) には到達しない (間接呼出しは未走査)。
- `getGridBit` の position < 0 は PE で 0 を返す (エラーにならない)。mock/C の code 4 を 0 に直した (本 PR の照合の結果)。
- **未確定**: `getGridBitWithLoop` の loop 分岐 (loop 行テーブルの参照条件・loop 長) は条件式の形まで読めたが、グローバル G1・G2 と行テーブルの意味が決まらない。mock に loop 記録が無いため、この分岐は未モデル (到達条件は未確定)。子 issue #2932 (`[PY-112]`) に分けた。

## 測定

- 測定 commit: `3dc3de0b` (main (`f81c46bb`) の取り込みの merge commit。コードを変えた最後の commit)。競合は `tests/provider_check.mjs` の 1 箇所だけ。main 側の `pe96` (PY-96・#2832、arrangement 選択 4 関数) と `pe121_2982` (PY-121・#2982、ui 表示・メニュー 6 関数) を追加し、判定条件に両方を入れ、件数を 121/314 にした。両側の集合は全て残した。件数は集合の和集合で両側の旧値 (111・119) を再現して検算した。
- 検証 HEAD: 本 REPORT の commit。コード範囲 `git diff 3dc3de0b HEAD -- tools/python/host tools/python/provider tools/python/tests` は 0 行 (本 REPORT の commit は範囲外)。前回測定 (`fa5bf9fb`) から `3dc3de0b` までの main 取り込み分は `git diff --stat fa5bf9fb 3dc3de0b -- tools/python/host tools/python/provider tools/python/tests` で 7 files・158 insertions・5 deletions。
- 素材: `fl-win64` (26.1.7) を `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` で全展開 (7.185 秒、`extracted/` を含む)。`toolchain-emsdk` は `[EMSDK]` (`/opt/emsdk/emsdk_env.sh` の実在を確認) が既に実在し、tarball は展開していない。`fetch_inputs.sh` rc 0 (1.516 秒)。`provider/build.sh` rc 0 (1.370 秒)。`build_cpython_wasm.sh` rc 0 (227.85 秒)。`FLPY_SKIP_TABLE=1 build_flpy.sh` rc 0 (5.803 秒)。追跡ファイルの変更は 0 件。
- 環境: runner 4 core、node v22.23.3。`all_tools` 終了時の load average 2.37 / 1.83 / 0.90。
- 旧測定 (`09f6668b`・`c5602929`・`dcbb50a2`・`c96ea0b8`・`7d52a228`・`fa5bf9fb` の表) は根拠にしない。Git 履歴に残る。main の取り込みは `c5602929` (`94b6c6bd`)・`dcbb50a2` (`718e90fb`)・`7d52a228` (`3e8c8d25`)・`fa5bf9fb` (`eeca4ded`)・`3dc3de0b` (`f81c46bb`) の 5 回。`fa5bf9fb` の競合は `tests/provider_check.mjs` の 1 箇所 (main の `pe119set`・`pe152` を追加し 111/324)。`docs/DOC_MAP.md` は自動解決。

| 検査 (3dc3de0b) | コマンド | 結果 | 所要 |
|---|---|---|---|
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0・関数 435・ハンドラ 121 | 1.370 秒 |
| channels 差分 | `node tests/channels_diff.mjs` | calls 170・diffs 0・PASS | 0.051 秒 |
| general 差分 (main 取り込みの PY-119 setter を含む) | `node tests/general_diff.mjs` | calls 25・diffs 0・PASS | 0.050 秒 |
| device 差分 | `node tests/device_diff.mjs` | calls 8・rejects 4・midi_out 5・diffs 0・PASS | 0.048 秒 |
| ui 差分 (main 取り込みの PY-119) | `node tests/ui_state_diff.mjs` | calls 12・diffs 0・PASS | 0.044 秒 |
| screen 差分 (main 取り込みの PY-121) | `node tests/screen_diff.mjs` | calls 32・diffs 0・PASS | 0.052 秒 |
| mixer 差分 (main 取り込みの PY-118) | `node tests/mixer_diff.mjs` | calls 59・diffs 0・PASS | 0.047 秒 |
| arrangement 差分 (main 取り込みの PY-152) | `node tests/arrangement_diff.mjs` | calls 25・diffs 0・PASS | 0.048 秒 |
| arrangement 選択差分 (main 取り込みの PY-96) | `node tests/arrangement_selection_diff.mjs` | calls 8・diffs 0・PASS | 0.049 秒 |
| ui 表示差分 (main 取り込みの PY-121 #2982) | `node tests/ui_display_diff.mjs` | ok_calls 12・bad_calls 11・diffs 0・PASS | 0.051 秒 |
| 実装数 | `node tests/provider_check.mjs` (第 3 節の flpy を含む全体) | functions 435・implemented 121・unimplemented 314・mcp_static 60・PASS | 0.405 秒 |
| 全 tool | `FL_ENGINE=wasm node tests/all_tools.mjs` | total 48・ok 48・soft_error 0・raised 0・host_calls 37425・callback_roundtrip true・PASS | 1.599 秒 |
| PE 書込み元の列挙 | `python3 analysis/flapi/pe_grid_writers.py` | +0x7ac 書込み 21 件・`0xff63f0` の直接 call 元 `0xff5b42`・`0xff5aa0` の直接 call 元 `0x1003c05` | 25.008 秒 |

- ネガティブコントロール (3dc3de0b で再実施): mock の `channels.isGridBitAssigned` (`host/fl_mock.mjs` の `return true;`) を `return false;` に変えると `channels_diff` は `channels/playlist 差分 2 件` の AssertionError で rc 1 (FAIL)。元に戻すと PASS (calls 170・diffs 0)。作業ツリーは測定後に元へ戻し、`git status --short` が 0 行であることを確認した。
- KPI: 起動・GUI に関わらない PR のため対象外。

## PE 解析 (FL_WIN64_DIR の `extracted/block00031_PE.bin`)

逆アセンブルは `analysis/flapi/pe_disasm.py` (capstone)。VA は全て絶対 VA (image base 込み)。

| VA | 関数 | 読めた処理 |
|---|---|---|
| `0xd5b360` | isGridBitAssigned | `0x1005730(index, dl=useGlobal>0, &obj)`。偽なら -4。`[obj+0x7ac]` が 0 なら status 0 (`0xd82c20` へ)。非 0 なら callback(1) = True |
| `0xd5b420` | getGridBit | 解決失敗 -4。grid が 0 なら -1。非 0 なら `0x12d3e20(grid, position)` の値を callback |
| `0xd5bc10` | getGridBitWithLoop | 解決失敗 -4。grid が 0 なら status 0。非 0 なら `0x12d3ff0(grid, position)` の値を callback |
| `0x12d3e20` | 基底の読出し | position < 0 で 0 を返す (`0x12d3e34`〜`0x12d3e36`、エラーにしない)。`[grid+0x22fc]` のバイト配列 (件数は `[ptr-8]`) で position < 件数 なら その byte。件数以上は別経路 (`0x12d16a0`・`0x12df210` を呼ぶ・未読) |
| `0xff63f0` | grid 生成 (遅延初期化) | `[obj+0x7ac]` が非 0 なら既存を返す (`0xff722e`)。0 なら `0x12d3070` で生成して `[obj+0x7ac]` に格納し、`[grid+0x3b4] = obj` (back-pointer)。続けて `+0x7c4` も生成 |
| `0xff5aa0` | channel 生成 | 直接 `call 0xff63f0` (`0xff5b42`)。channel index は vtable slot 52 (`[rbx+0x1a0]`、`[obj+0x794]` への書込み。REPORT_PY67 と一致) で設定 |
| `0x12d3ff0` | loop 分岐 | 下の「loop 分岐の読めた範囲」 |

### `+0x7ac` の書込み元 (`pe_grid_writers.py` の実測)

- 書込みは 21 件 (`pe_grid_writers.py` が mnemonic `mov` だけを走査した件数。add・and・movups 等の書込みは未走査)。qword の書込みは `0xff647c` の 1 件だけ (`mov qword ptr [rcx+0x7ac], rax`、`0xff63f0` の内側)。
- `0xff63f0` の直接 call 元は `0xff5b42` の 1 件 (`0xff5aa0` の内側)。`0xff5aa0` の直接 call 元は `0x1003c05` の 1 件。
- byte 書込み 12 件 (`0xa03b3c`・`0xa084e0`・`0xdd195c` 〜 `0xdd22e2`・`0xec85ce`) と dword 書込み 8 件 (`0xbd11c5`・`0xbd2d03`・`0xbd2d46`・`0x10016cb`・`0x1003376`・`0x1003503`・`0x100356f`・`0x130f7db`) は別の構造体と見られる。同一 object かは未確認。

判断: 解決表 (`0x1005730`) が返す channel は生成時に grid を持つ、と読める。直接 call の走査だけで確かめた範囲で、間接呼出し (vtable・関数ポインタ) の有無は未走査。このため「null 経路は到達しない」は**直接 call の範囲での結論**とし、到達しないとは断定しない。

### loop 分岐の読めた範囲 (`0x12d3ff0`)

1. `cid = [[grid+0x3b4]+0x794]` (channel index)。
2. `G1 = dword [VA 0x15d51a0]`。行テーブル `T = VA 0x193fd08`、行幅 192 byte。`[T + G1*192] == 0` なら loop 分岐に入らない。`obj = [T + G1*192]`。
3. `p = [[VA 0x15e14a0]]`、`q = [p + 0x7e0]` とし、`byte [q + 0x49e]` が 0 なら loop 分岐に入らない。
4. `list = [obj+0x58]`、件数 `[list-8]` (list が 0 なら 0 件)。各要素 (20 byte) について、`rec+0 == cid`、`rec+4 != 0`、`[obj+0x54]` の byte != 0 を満たす最初の要素を採る。`L = rec+8 / [G2]` (`G2` は `[VA 0x15e25f8]` が指す int)。
5. 採った `L > 0` のとき: position < L なら `base(position)`。position ≥ L なら `base(position mod L) == 1 ? 2 : 0`。`L <= 0` または採らなかったときは `base(position)`。
6. 戻り値は callback に渡る。getGridBitWithLoop の table 型は `bool` のため、2 は True に写る。callback の実型は未確認。

未確定: G1 と G2 が何の設定値か、行テーブル `obj` の意味、`0x15e14a0` 経由 flag の意味。このため loop 分岐の**値**は決められず、mock/C は loop 分岐を未モデル (到達条件は未確定・#2932) として扱った。

## 実装の内容

- `channels.isGridBitAssigned(index, useGlobalIndex)`: index が範囲外なら -4。範囲内なら True (grid は生成済み)。`useGlobalIndex` は未モデル (既存 `getGridBit` と同じ)。
- `channels.getGridBitWithLoop(index, position, useGlobalIndex)`: index 範囲外は -4。`position >= 64` は RANGE (4)。`position < 0` は False。それ以外は `steps[position]` (base 読出しと同じ。loop 分岐は未モデル)。
- `channels.getGridBit`: `position < 0` を RANGE (4) から False に変更。根拠は `0xd5b420` → `0x12d3e20` の position < 0 が 0 を返すこと。`position >= 64` は変えない (PE 未照合)。
- 変更前の mock/C は `getGridBit` の `position < 0` で code 4 を返していた。PE の経路と違うため直した。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| G1 (VA `0x15d51a0`)・行テーブル (VA `0x193fd08`)・flag (VA `0x15e14a0` → `+0x7e0` → `+0x49e`)・G2 (VA `0x15e25f8`) の意味 | getGridBitWithLoop の loop 分岐 (戻り値 2・loop 長) が mock/C で未モデル | 子 #2932 (`[PY-112]`) |
| `position >= 件数` の経路 (`0x12d16a0`・`0x12df210`) | getGridBit / getGridBitWithLoop の `position >= 64` (RANGE 4) が PE と未照合 | 子 #2932 (`[PY-112]`) |
| callback の実型 (2 を bool にするか int にするか) | loop 分岐の戻り値の見え方 | 子 #2932 (`[PY-112]`) |
| +0x7ac の byte・dword 書込み 20 件の型、間接呼出しによる `0xff63f0`・`0xff5aa0` の呼出し | null 経路が到達しない結論は直接 call の範囲のみ | 本 REPORT の未解決 (追跡子は作らない) |
| `0x1005730` の解決表に入る全 object が `0xff5aa0` で作られるか (`0x1003c05` 以外の生成経路) | isGridBitAssigned の True 固定の前提 | 本 REPORT の未解決 (追跡子は作らない) |

## 範囲外

- `useGlobalIndex = 1` (`0x1005730` の dl=1 表) は既存の未モデルのまま。
- `getStepParam`・`getCurrentStepParam` は #2879 の範囲 (`[PY-100]`・`[PY-111]`)。

## 再現

- 素材展開: `tar --zstd -xf <fl-win64>.tar.zst -C <展開先>` (`FL_WIN64_DIR=<展開先>`)。PE は `extracted/block00031_PE.bin`。
- PE 書込み元の列挙: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_grid_writers.py` (約 17 秒)。
- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py d5bc10 60` ほか、`12d3ff0`・`12d3e20`・`d5b360`・`d5b420`・`ff63f0`・`ff5aa0`。
- flpy の前提: `fetch_inputs.sh` → `build_cpython_wasm.sh` → `FLPY_SKIP_TABLE=1 build_flpy.sh` (`EMSDK_DIR` は `[EMSDK]`)。
- 検査: `node tests/channels_diff.mjs`・`node tests/provider_check.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs` (前提: `provider/build.sh` 済み)。
