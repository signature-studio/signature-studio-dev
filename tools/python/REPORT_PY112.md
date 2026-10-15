# PY-112 (#2932): channels.getGridBitWithLoop の件数超え経路と loop 分岐の PE 照合

既知類型との関係: 該当なし (逆アセンブル解釈と mock/C の照合。`docs/DEFECTS.md` の lift 欠陥類型には当たらない)。

## 結論

- **件数超えの照合 (受入 2) は決着。mock/C の修正を入れた**: `0xd5b420` (getGridBit) も `0xd5bc10` (getGridBitWithLoop) も position の範囲検査を持たない。件数以上の position は `0x12d3e20` の event 経路 (`0x12d16a0`・`0x12df210`) の値 (0 か 1) を返し、エラーにしない。mock/C の `p >= 64 → RANGE(4)` は PE と合わなかったため外し、event 未モデルとして `false` を返す (C と mock で同一)。
- **loop 分岐の条件式は PE で読み切った** (下の「loop 分岐 `0x12d3ff0`」)。ただし**値を決める 2 点が未確定**: 行テーブル T の行 (`obj`) の書込み元と、G2 の値 (ticks per step と見える)。起動直後は T が `.bss` (ゼロ埋め) なので、T の行が書かれるまで loop 分岐は到達しない。このため loop 分岐は未実装のまま残し、子 issue に分けた (#3595・`[PY-217]`)。
- 件数超えの event 経路は未モデル。mock は event を持たないため、PE で event があれば 1 になる位置も false を返す。子 issue (#3596・`[PY-218]`)。

## 測定

- 測定 commit: `404931a8a` (`fix(python): getGridBit・getGridBitWithLoop の件数以上を RANGE にしない`。コードを変えた最後の commit)。
- 検証 HEAD: 本 REPORT の commit。コード範囲 `git diff 404931a8a HEAD -- tools/python/host tools/python/provider tools/python/tests` は 0 行 (本 REPORT の commit は範囲外)。
- 素材: `fl-win64` (26.1.7) を `tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C $RUNNER_TEMP/fl-win64` で全展開 (5.550 秒)。`toolchain-emsdk` は `/opt/emsdk/emsdk_env.sh` (既定の `EMSDK_ENV`) で使った。`fetch_inputs.sh` rc 0。
- 環境: runner 4 core、node v22.23.3。測定後の `uptime` は load average 3.24 / 1.99 / 0.98 (ビルド直後)。

| 検査 (404931a8a) | コマンド | 結果 | 所要 |
|---|---|---|---|
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0・関数 435・ハンドラ 149 | 1.559 秒 |
| CPython wasm | `bash tools/python/build_cpython_wasm.sh` | rc 0・python.wasm 生成 | 4 分 7.215 秒 |
| flpy ビルド | `FLPY_SKIP_TABLE=1 bash tools/python/build_flpy.sh` | rc 0・flpy.wasm 5,924,680B | 6.275 秒 |
| channels 差分 | `node tests/channels_diff.mjs` | calls 214・diffs 0・PASS | 1 秒未満 |
| 実装数 | `node tests/provider_check.mjs` | functions 435・implemented 149・unimplemented 286・mcp_static 60・PASS | 1 秒未満 |
| 全 tool | `FL_ENGINE=wasm node tests/all_tools.mjs` | total 48・ok 48・soft_error 0・raised 0・host_calls 37425・callback_roundtrip true | 2.257 秒 |

- ネガティブコントロール (404931a8a): mock の `channels.getGridBit` を旧挙動 (`if (p >= 64) throw RANGE();`) に戻すと `channels_diff` は `channels/playlist 差分 1 件` の AssertionError で rc 1 (FAIL)。元に戻すと PASS (calls 214・diffs 0)。作業ツリーは測定後に元へ戻し、`git diff --stat -- tools/python/host` が 0 行であることを確認した。
- KPI: 起動・GUI に関わらない PR のため対象外。
- 未実行: `tests/fulltext_parity.mjs` (main 由来の全文比較・`dist/flpy_static.js` が前提)。この PR の範囲外。

## PE 解析 (FL_WIN64_DIR の `extracted/block00031_PE.bin`)

逆アセンブルは `analysis/flapi/pe_disasm.py`、参照元の列挙は `analysis/flapi/pe_xref.py` (capstone)。VA は絶対 VA。

| VA | 関数 | 読めた処理 |
|---|---|---|
| `0xd5b420` | getGridBit | 引数 parse の後、`0x1005730` で index を解決 (失敗は -4)。grid が 0 なら -1。`0x12d3e20(grid, position)` の値を callback。**position の範囲検査は無い** |
| `0xd5bc10` | getGridBitWithLoop | `0x12d3ff0(grid, position)` の値を callback |
| `0x12d3e20` | 基底の読出し | position < 0 で 0。position < 件数 (`[grid+0x22fc]` の件数 `[ptr-8]`) で その byte。**件数以上**は event 経路: `0x12d16a0(G1, dl=1)` で pattern を得て、閾値 `(position+1) * G2` を作り、`0x12df210` で item を走査。item の channel が grid の obj と一致 (`0xfe8bb0`)・time < 閾値・`byte [item+0x13] & 0x20 == 0` の item があれば 1、無ければ 0 |
| `0x12d3ff0` | loop 分岐 | 下の「loop 分岐」 |

### loop 分岐 `0x12d3ff0` (逆アセンブルで確認した制御フロー)

1. `cid = dword [[grid+0x3b4]+0x794]` (channel index)。
2. `G1 = dword [VA 0x15d51a0]`。行テーブル `T = VA 0x193fd08`、行幅 192 byte。`obj = qword [T + G1*192]`。`obj == 0` なら loop 分岐に入らない。
3. `p = qword [VA 0x15e14a0]`、`q = qword [p+0x7e0]`。`byte [q+0x49e] == 0` なら入らない。
4. `list = [obj+0x58]` (件数 `[list-8]`、list が 0 なら 0 件)。各要素 (20 byte) を先頭から走査し、`rec+0 == cid`・`rec+4 != 0`・`byte [obj+0x54] != 0` を満たす最初の要素を採る。`L = rec+8 / G2` (`G2 = *(int *)[VA 0x15e25f8]`)。
5. 採った `L > 0` のとき: `position < L` なら `base(position)`。`position >= L` なら `base(position mod L) == 1 ? 2 : 0`。`L <= 0` か採らなかったときは `base(position)`。
6. 戻り値は callback に渡る。2 を bool に写すか int に写すかは未確認 (`getGridBitWithLoop` の table 型は `b`)。

### 静的初期値 (`.data` / `.bss` の読出し・起動直後の状態)

| 対象 | 静的値 | 意味 |
|---|---|---|
| G1 (VA `0x15d51a0`) | `.data` で 1 | 実行中に書き換わり得る |
| T (VA `0x193fd08`) | `.bss` (ゼロ埋め) | 起動直後は全行の `obj` = 0。`obj == 0` で loop 分岐に入らない |
| G2 の指す先 (`0x15e25f8` → `0x15d89c4`) | `.data` へのポインタ | 値は未読 (子 #3595) |
| p (VA `0x15e14a0`) | `.data` で `0x16b6b98` (`.bss` 内の object) | 起動後の object。`q` と flag は実行時の値 |

判断: 起動直後は T が 0 なので、loop 分岐は T の行が書かれるまで到達しない。T の行を書く経路と G1 の書込み元は未特定 (下の未解決)。逆に、T の行が書かれた後の挙動 (L と戻り値 2) は PE の制御フローから確定できるが、L に使う G2 の値が無く、テストで観測できる値にならない。

### T の参照元 (`pe_xref.py`)

- `G1 (0x15d51a0)` は `mov ecx, dword [rip+...]` の load が約 100 件。直接の store は RIP 相対では見えず、ポインタ経由の書込みと見られる。
- `T (0x193fd08)` は `lea` で約 24 件 (`0x12cee5d`〜`0x12d8972`)。`0x12cee00` は T の行を読み、`obj+0x58` の件数を見る読出し側。書込み側は未特定。

## 実装の内容

- `provider/fl_engine.c`・`host/fl_mock.mjs`: `channels.getGridBit` と `channels.getGridBitWithLoop` の `p >= 64` の RANGE を外した。`0 <= p < 64` は従来どおり `steps[p]`、それ以外は `false` (件数超えの event 経路の未モデル)。
- `channels.setGridBit` の `p >= 64` RANGE は変えない (PE 未照合)。
- `channels.isGridBitAssigned` と loop 分岐は変えない (前版 PY-101 のまま)。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| T の行 `obj` と G1 の書込み元 | loop 分岐の到達条件が決まらない。getGridBitWithLoop の loop 分岐を実装できない | 子 #3595 (`[PY-217]`) |
| G2 の値と意味 (ticks per step か) | loop 長 L の値が決まらない | 子 #3595 (`[PY-217]`) |
| 戻り値 2 の callback での見え方 (bool か int か) | getGridBitWithLoop の loop 分岐の戻り値 | 子 #3595 (`[PY-217]`) |
| 件数超えの event 経路 (`0x12d16a0`・`0x12df210`) | getGridBit/getGridBitWithLoop の `p >= 件数` が PE では event の有無で 1 になり得る。mock は false | 子 #3596 (`[PY-218]`) |
| 件数 `[grid+0x22fc]-8` の値 (64 か) | 64 未満なら件数と steps の境界が合わない | 子 #3596 (`[PY-218]`) |

## 再現

- 素材展開: `tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C <展開先>` (`FL_WIN64_DIR=<展開先>`)。PE は `extracted/block00031_PE.bin`。
- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py 12d3ff0 90` ほか、`12d3e20`・`d5b420`・`12cee00`。
- 参照元: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_xref.py 0x15d51a0,0x193fd08`。
- 検査: `bash provider/build.sh` の後に `node tests/channels_diff.mjs`・`node tests/provider_check.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs` (flpy は `build_cpython_wasm.sh` → `FLPY_SKIP_TABLE=1 build_flpy.sh`)。
