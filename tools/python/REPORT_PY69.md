# PY-69 (#2499): selectOneChannel の PE 意味論 (排他選択・stack 引数・前提ゲート)

親: #1527 (PY-39)・子 #2499 (PY-69)。前段: `REPORT_PY39.md` の selectAll 等の読解。250 行上限のため `REPORT_PY39.md` から分割移動した (内容は変更していない)。

## 解析の詳細 (PY-69)

- 既知類型との関係: 該当なし (lift 作業ではない。PE 逆アセンブルによる意味論の確定)。
- 測定 commit: `96de54b9` (コード変更の最後の commit。main の取り込み merge。PY-69 のコード変更は `68aefd04`: `provider/fl_engine.c`(コメント)・`host/fl_mock.mjs`・`tests/channels_diff.mjs`・`tests/provider_check.mjs`(コメント)・`analysis/flapi/pe_scan_store.py`。`683aef61` の後に mock の 2 番目引数の型検査と差分テストの呼出し 3 件を足した)。
- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'`。`-C` を省くと作業ツリーに展開される。実測 2.9 秒)。
- 書込み箇所の列挙: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_scan_store.py 0x32c` (PE 全 `.text` 16,397,488 バイトの線形走査、19.6 秒、10 件)。

### 結論

- `selectOneChannel(index, useGlobalIndex=False)`: index が範囲外なら status `-4` → Python 例外 "Index out of range" (C provider の code 4 と同じ)。範囲内で選択ゲート `0xffac20` が真なら、対象の選択フラグ `+0x32c` を 1 にし、**他の全 channel の同フラグを 0 にする (排他選択)**。
- 次の 2 つのゲートは未確定で、C provider・mock では未モデル (C provider は常に選択する)。(a) 前提ゲート `0xd5af58` が偽なら何もせず status `-2` のまま返る (選択も解除もしない)。(b) 選択ゲート `0xffac20` が偽なら対象は選ばれず、他の channel は解除される (`0xff8a90` の `v != 0` 分岐)。返った status の扱いは `0xd82c20` のゲート次第 (処理経路の表)。
- 排他選択の所在は `0xd5af30` ではなく `0x11e84a0` (全件ループ)。フラグの書込みは setter `0xff8a90` を経由する。PE 全 `.text` の線形走査で `[reg+0x32c]` への byte 書込みは 10 箇所 (setter `0xff8abe` を含む)。構造体の型が未確定のため、setter 以外の 9 箇所がこの channel の選択と関係するかは未確定 (未解決表)。

### stack 引数の出所

- `0xd5afc0`: PyArg 解析 `i|i` (fmt は `0xd5b0f4`、`call [IAT 0x889571]`) の出力。index → `[rbp+0x9c]`、useGlobalIndex → `[rbp+0x98]`。
- `0xd5b041`〜`0xd5b096`: `0xd843d0(container, out=[rbp+0x80], cb=0xd5af30, ctx=0, a5=index, a6=useGlobal, a7..a10=0, a11=1)` を呼ぶ。
- `0xd843d0`: a5 → task `+0x18`、a6 → task `+0x20`、cb → task `+0x58`。out の初期値は -2 (`0xd843e9`)、task の status `+0x60` は cb の先頭で -2 (`0xd5af3c`)。thunk `0xd84290` (`call [task+0x58]`) を `0x526190` に渡し、その後 `[out] = [task+0x60]` (`0xd844d7`)。`0x526190` が同期実行か後段未読のため、同期実行は推定。

### 処理経路 (selectOneChannel)

| 段 | VA | 内容 |
|---|---|---|
| 前提ゲート | `0xd5af44`〜`0xd5af60` | `[[[0x15E4790]]+8]` を `rcx` にして vtable `+0x98` を呼ぶ (`0xd5af58`)。`al=0` なら `je 0xd5afa4` で epilogue へ飛び、`0xd5af3c` で設定した status `-2` のまま返る (選択・解除・表示はしない)。判定条件は未確定 (未解決表) |
| 検査 | `0xd5af62`〜`0xd5af71` → `0x1005730` | `ecx` = index (`[rbx+0x18]`)、`dl` = `useGlobalIndex > 0` (`cmp [rbx+0x20],0; setg dl`)。`dl=1` は `[rip+0x5dcad3]` の表、`dl=0` は `[rip+0x5da9a8]` の表 (`0x1005730` の内部は未読)。範囲は `0..count-1` |
| 範囲外 | `0xd5af9c` | `[task+0x60] = -4` |
| 選択 | `0xd5af7a` → `0x11e84a0(item+0x794)` | 排他選択 (次節) |
| 表示 | `0xd5af95` → `0xffaf80(item)` | `item+0x7b4` の表示矩形の調整 (UI 副作用。意味は未確定) |
| 戻り値 | `0xd5b09b`〜`0xd5b0a4` → `0xd82c20(status)` | status は `[out]` (`0xd844d7` で `[task+0x60]` を複写)。`0xd82c20` の判定: `0` は `[0x860485]` の関数が偽なら成功経路 `0xc38bc0`、真なら 0 (NULL) を返す (PyErr_Occurred 相当と推定)。`status < 0` は `0xd82c6a` で別ゲート `[[[0x861b1f]]+8]` の vtable `+0x88` を呼び、**真のときだけ**文言を設定する: `-4` → `0xd82d3c` の "Index out of range" (`0xd82e8c`)、`-2` → `0xd82d18` の "Operation unsafe at current time" (`0xd82e44`)。ゲートが偽のときは `0xc38bc0` へ進む (`-4` も同じ) |

### 排他選択 `0x11e84a0(id)`

1. 対象 `item = fe8bb0(table, id)`。`item+0x32d != 0` なら何もしない (`0x11e84e2`)。
2. 全 `j` in `0..count-1` について `want = (j == id)`。`item_j+0x32c != want` のときだけ `0xff8a90(item_j, want)` を呼ぶ (`0x11e8522`〜`0x11e8532`)。
3. 後段 (`0x11e8542`〜): 対象の `+0xd34`・`+0x160` を見る分岐。UI 系と推定 (未読・未モデル)。

`0xff8a90(item, v)` (選択フラグの setter):
- `v != 0` のとき `0xffac20(item)` が真なら `+0x32c = 1`、偽なら `0` (`0xff8aa7`〜`0xff8abe`)。**選択の gating**。
- `0xffac20(item)` は `*(*(0x15E3A60)) < 0` なら真、それ以外は `item+0x798 == *(*(0x15E3A60))` (`0xffac20`〜`0xffac43` で確認)。偽のとき対象は選ばれない。
- その後 `[+0x7c4]` の vtable `[+0x200]` (通知) と `0xfdee80`。新たに選択されたときは `0xfdf020(id, 4)` (UI 通知と推定)。

フラグ `+0x32c` への書込み (`pe_scan_store.py 0x32c`、10 件): `0xff8abe` (setter 内)、`0x6e9f4d`・`0x82bbf4`・`0x82bcb5`・`0x82bce0`・`0xfe96ed`・`0x11f8889`・`0x11f88e9`・`0x11f8981`・`0x11f8a43`。`0x11e84a0` 自体は書かず setter を呼ぶ。setter 以外の 9 箇所の構造体の型は未確定。

### 実装

- `provider/fl_engine.c` `FL_H(channels, selectOneChannel)`: `CH(0)` で範囲外を code 4、次に `(void)A_INT(1, 0)` で 2 番目の型を検査 (型違いは code 5)、`ch[i].sel = (i == _i)`。未モデル: useGlobalIndex・前提ゲート `0xd5af58`・選択ゲート `0xffac20`。
- `host/fl_mock.mjs`: `arity(a, 1, 2)`、`ch(a[0])`、`argI(a, 1, 0)` (C と同じ型検査)、`c.sel = c === k`。

### 検証 (コミット済み HEAD `96de54b9` で実行)

| 検証 | 結果 |
|---|---|
| `node tests/channels_diff.mjs` (C provider と mock) | 69 呼出し、diffs 0、PASS |
| ネガティブコントロール: mock から `argI(a, 1, 0)` を外す | diffs 4 件 (`selectOneChannel [0,"x"]`・`[0,1.5]`・`[0,[1]]` は C が code 5、mock は ok。後続の `isChannelSelected [2]` で状態差 1 件)、exit 1。戻すと PASS |
| ネガティブコントロール (`683aef61` で実測。排他選択の行は `68aefd04` で変更していない): mock を `c.sel = c === k \|\| c.sel` (他を解除しない) に壊す | diffs 1 件 (`channels.isChannelSelected [0]`: mock true / C false)、exit 1。元に戻すと PASS |
| `node tests/provider_check.mjs` | functions 435、implemented 71、unimplemented 364、mcp_static 60、PASS |
| `node tests/all_tools.mjs` (mock) | 48/48 ok、soft_error 0、raised 0、host_calls 37425、callback_roundtrip true |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37425、callback_roundtrip true |

- 所要 (実測, `96de54b9`): `provider/build.sh` 0.6 秒、`build_flpy.sh` 4.8 秒、`channels_diff` 0.04 秒、`provider_check` 0.25 秒、`all_tools` 1.12 秒 (mock) / 1.13 秒 (wasm)。`build_cpython_wasm.sh` 2 分 42 秒と `pe_scan_store.py 0x32c` 19.6 秒は `68aefd04` での実測 (`96de54b9` では再実行していない)。
- load average: nproc 4、`uptime` は 15:37:20 時点で `0.13 / 0.38 / 0.44` (1・5・15 分平均)。ビルド中の値は採取していない。
- 差分 0 の証跡: `git diff 96de54b9 HEAD -- tools/python/provider tools/python/host tools/python/tests` (本節を含む commit は docs のみのため出力 0 行。PR 作成時に実行して確認)。

### main 取り込み後の再実行 (HEAD `116cd354`)

- main (`81799351`) を merge した `116cd354` で、`docs/DOC_MAP.md`・`tools/python/REPORT_PY39.md` の 2 件を解消した (どちらも文書の分割移動の両立。コード側は無競合)。
- 上の表と同じ 5 検証を `116cd354` で再実行し、全件 PASS (`channels_diff` 69 呼出し diffs 0、`provider_check` implemented 71、`all_tools` 48/48 の mock・wasm 両方)。
- 差分 0 の証跡: `git diff 96de54b9 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (HEAD は main `ad4c27b3` の取り込み後。`116cd354` 時点でも 0 行)。main 取り込みで `tools/python` 内に入った変更は文書 (`REPORT_PY39.md`・`REPORT_PY39_2548.md`・`REPORT_PY72.md`) と解析スクリプト `analysis/flapi/pe_rip_consts.py` のみ。
- 所要 (実測, `116cd354`): `provider/build.sh` 1.4 秒、`build_cpython_wasm.sh` 4 分 2 秒 (この run の初回ビルド)、`build_flpy.sh` 6.1 秒、`channels_diff` 0.12 秒、`provider_check` 0.35 秒、`all_tools` 2.1 秒 (mock) / 2.0 秒 (wasm)。
- 入力の準備: `work/` は `fetch_inputs.sh` (`FL_WIN64_DIR` = fl-win64 素材の展開先。4 ブロックだけを `tar --wildcards` で展開)。`dist/flpy` は `FLPY_SKIP_TABLE=1 build_flpy.sh` で作り、追跡済みの `flapi_table.json` をそのまま使った (表は再生成していない)。
- load average: `uptime` 15:52:51 時点で `1.72 / 1.80 / 0.89` (直前の CPython・flpy ビルドの影響を含む。テスト単体の値は採取していない)。

### 検証範囲 / 範囲外

- 範囲内: 範囲外判定と排他選択。検証した呼出しの `useGlobalIndex` は省略か `false` (`dl=0` 相当) のみ。C provider・mock の呼出し列 69 件 (2 番目引数の型違い 3 件を含む)。
- 範囲外 (未モデル): `useGlobalIndex>0` の表、前提ゲート `0xd5af58`、後段のゲート `0xd82c6a`、選択ゲート `0xffac20`、`item+0x32d` の前置、UI 副作用 (`0xffaf80`・`0xfdf020`・後段 `+0xd34`/`+0x160`)。実機 FL の UI は検証していない。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 前提ゲート `0xd5af58` (`[[[0x15E4790]]+8]` の vtable `+0x98`) の判定条件。偽なら status `-2` のまま返る。`-2` の文言 (上記) から「操作不可時の失敗」と推定するが未確定 | 偽の経路で結果が変わる。C provider は常に選択する | #2542 |
| ゲート `0xd82c6a` (`[[[0x861b1f]]+8]` の vtable `+0x88`) の意味。真なら status < 0 を例外化、偽なら成功経路 `0xc38bc0` | `-4`・`-2` の例外の有無 | #2542 |
| `useGlobalIndex>0` の表 (`0x1005730` の `dl=1` 分岐 `[rip+0x5dcad3]`) | `dl=1` の経路を C 側で rack 扱いしている | #2542 (受入 2) |
| 選択 gating `0xffac20` (偽なら対象は選ばれず他は解除) | 選択不可の channel で結果が変わる可能性。C 側は未モデル | #2542 (受入 2) |
| `+0x32c` への byte 書込み 9 箇所 (`0x6e9f4d`・`0x82bbf4`・`0x82bcb5`・`0x82bce0`・`0xfe96ed`・`0x11f8889`・`0x11f88e9`・`0x11f8981`・`0x11f8a43`) | 構造体の型が未確定。channel item への書込みかは未確定 | #2542 |
| `item+0x32d` の前置と後段 UI 分岐 (`+0xd34`・`+0x160`) | UI 状態のみ。C provider に UI 状態は無い | 追跡のみ (子は起票しない) |
| `setChannelPitch` の意味論と実装 | 未実装 | #2542 |

### 次の提案 (#2542)

- `0x1005730` の global 表 (`[rip+0x5dcad3]`) の対応を解決し、rack と global の違いを REPORT に残す。
- `0xffac20` の判定は本節で読んだ。残りは前提ゲート `0xd5af58` と `0xd82c6a` の vtable 先を読み、判定条件を確定する。
- `setChannelPitch` は `0x477180`・`0x40c660`・`0xf81ce0` を読んでから実装する。
