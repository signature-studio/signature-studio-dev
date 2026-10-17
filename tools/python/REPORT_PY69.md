# PY-69 (#2499): selectOneChannel の PE 意味論 (排他選択・stack 引数・前提ゲート)

親: #1527 (PY-39)・子 #2499 (PY-69)。前段: `REPORT_PY39.md` の selectAll 等の読解。250 行上限のため `REPORT_PY39.md` から分割移動した (内容は変更していない)。

## 解析の詳細 (PY-69)

- 既知類型との関係: 該当なし (lift 作業ではない。PE 逆アセンブルによる意味論の確定)。
- 測定 commit: `96de54b9` (main の取り込み merge。main の PY-70 (`1530a544`) のコード変更を含む merge 上で測定した。PY-69 のコード変更は `68aefd04`: `provider/fl_engine.c`(コメント)・`host/fl_mock.mjs`・`tests/channels_diff.mjs`・`tests/provider_check.mjs`(コメント)・`analysis/flapi/pe_scan_store.py`。`683aef61` の後に mock の 2 番目引数の型検査と差分テストの呼出し 3 件を足した)。
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
| 前提ゲート | `0xd5af44`〜`0xd5af60` | `[[[0x15E4790]]+8]` を `rcx` にして vtable `+0x98` を呼ぶ (`0xd5af58`)。`al=0` なら `je 0xd5afa4` で epilogue へ飛び、`0xd5af3c` で設定した status `-2` のまま返る (選択・解除・表示はしない)。判定条件は PY-248 節で確定 |
| 検査 | `0xd5af62`〜`0xd5af71` → `0x1005730` | `ecx` = index (`[rbx+0x18]`)、`dl` = `useGlobalIndex > 0` (`cmp [rbx+0x20],0; setg dl`)。`dl=1` は `[rip+0x5dcad3]` の表、`dl=0` は `[rip+0x5da9a8]` の表 (`0x1005730` の内部は未読)。範囲は `0..count-1` |
| 範囲外 | `0xd5af9c` | `[task+0x60] = -4` |
| 選択 | `0xd5af7a` → `0x11e84a0(item+0x794)` | 排他選択 (次節) |
| 表示 | `0xd5af95` → `0xffaf80(item)` | `item+0x7b4` の表示矩形の調整 (UI 副作用。意味は未確定) |
| 戻り値 | `0xd5b09b`〜`0xd5b0a4` → `0xd82c20(status)` | status は `[out]` (`0xd844d7` で `[task+0x60]` を複写)。`0xd82c20` の判定: `0` は `[0x860485]` の関数が偽なら成功経路 `0xc38bc0`、真なら 0 (NULL) を返す (PyErr_Occurred 相当と推定)。`status < 0` は `0xd82c6a` で別ゲート (`0x15E4790` 起点・vtable `+0x88`。PY-248 節で確定) を呼び、**真のときだけ**文言を設定する: `-4` → `0xd82d3c` の "Index out of range" (`0xd82e8c`)、`-2` → `0xd82d18` の "Operation unsafe at current time" (`0xd82e44`)。ゲートが偽のときは `0xc38bc0` へ進む (`-4` も同じ) |

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
- 差分 0 の証跡: `git diff 96de54b9 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (`9674d0cb`・その後の docs のみの commit で確認。PR 本文の検証 HEAD で再確認)。

### main 取り込み後の再実行 (HEAD `116cd354`)

- main (`81799351`) を merge した `116cd354` で、`docs/DOC_MAP.md`・`tools/python/REPORT_PY39.md` の 2 件を解消した (どちらも文書の分割移動の両立。コード側は無競合)。
- 上の表と同じ 5 検証を `116cd354` で再実行し、全件 PASS (`channels_diff` 69 呼出し diffs 0、`provider_check` implemented 71、`all_tools` 48/48 の mock・wasm 両方)。
- 差分 0 の証跡: `git diff 96de54b9 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (HEAD は main `ad4c27b3` の取り込み後。`116cd354` 時点でも 0 行)。main 取り込みで `tools/python` 内に入った変更は文書 (`REPORT_PY39.md`・`REPORT_PY39_2548.md`・`REPORT_PY72.md`) と解析スクリプト `analysis/flapi/pe_rip_consts.py` のみ。
- 所要 (実測, `116cd354`): `provider/build.sh` 1.4 秒、`build_cpython_wasm.sh` 4 分 2 秒 (この run の初回ビルド)、`build_flpy.sh` 6.1 秒、`channels_diff` 0.12 秒、`provider_check` 0.35 秒、`all_tools` 2.1 秒 (mock) / 2.0 秒 (wasm)。
- 入力の準備: `work/` は `fetch_inputs.sh` (`FL_WIN64_DIR` = fl-win64 素材の展開先。4 ブロックだけを `tar --wildcards` で展開)。`dist/flpy` は `FLPY_SKIP_TABLE=1 build_flpy.sh` で作り、追跡済みの `flapi_table.json` をそのまま使った (表は再生成していない)。
- load average: `uptime` 15:52:51 時点で `1.72 / 1.80 / 0.89` (直前の CPython・flpy ビルドの影響を含む。テスト単体の値は採取していない)。

### 差し戻し round 2 の再実行 (HEAD `0ef43b21`)

- 入力: fl-win64 から `block24429`・`block24430`・`block25159`・`block24618` の 4 block を `tar --zstd -xf` で `FL_WIN64_DIR/extracted` に展開し、`fetch_inputs.sh` で `work/` を作った。`build_cpython_wasm.sh` は 4 分 10 秒 (初回)、`FLPY_SKIP_TABLE=1 build_flpy.sh` は 6.2 秒、`provider/build.sh` は OK (ハンドラ 71)。emsdk は [EMSDK] (`toolchain-emsdk`)。
- `channels_diff`: 69 呼出し、diffs 0、PASS。`provider_check`: functions 435、implemented 71、unimplemented 364、mcp_static 60、PASS。`all_tools`: mock・`FL_ENGINE=wasm` とも 48/48 ok、soft_error 0、raised 0、host_calls 37425、callback_roundtrip true。
- 差分 0 の証跡: `git diff 96de54b9 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (HEAD `0ef43b21`)。
- load average: `uptime` 16:18:12 時点で `1.81 / 1.68 / 0.83` (ビルド直後。テスト単体の値は採取していない)。

### 差し戻し round 3 (main 取り込み後の証跡)

- main (`f4fa48f9`) を merge `ff992168` で取り込んだ。main は merge-base `f3102162` 以降 `tools/python/provider`・`host`・`tests` を変更していない。
- 差分 0 の証跡: `git diff 96de54b9 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (`ff992168` 以降の docs のみの commit でも 0 行)。測定は round 2 (`0ef43b21`) の実測をそのまま使う (WORKFLOW §6)。

### 検証範囲 / 範囲外

- 範囲内: 範囲外判定と排他選択。検証した呼出しの `useGlobalIndex` は省略か `false` (`dl=0` 相当) のみ。C provider・mock の呼出し列 69 件 (2 番目引数の型違い 3 件を含む)。
- 範囲外 (未モデル): `useGlobalIndex>0` の表、前提ゲート `0xd5af58`、後段のゲート `0xd82c6a`、選択ゲート `0xffac20`、`item+0x32d` の前置、UI 副作用 (`0xffaf80`・`0xfdf020`・後段 `+0xd34`/`+0x160`)。実機 FL の UI は検証していない。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 前提ゲートの判定式は PY-248 節で確定 (F1・F2・Z が 0 かつ D+0x168 <= 0)。残る未確定はフラグの意味と D の同定 (下の 2 行) | 偽の経路の結果 (C provider は常に選択) | [PY-82] #2642 |
| 後段ゲートの判定式 (F1・F2・Z が 0) と意味 (真で例外文言・偽で例外なし) は PY-248 節で確定 | `-4`・`-2` の例外の有無の C・mock 側反映は未実装 | [PY-82] #2642 |
| F1・F2・Z の意味 (状態名)。Z の 2 件目の setter `0x11c761c` の文脈は未読 | 例外が出る実行時条件を説明できない | [PY-82] #2642 |
| D (cell `0x15F7190` の指す先) の生成箇所と `+0x168` の書込み元 | 前提ゲートの偽条件 (`D+0x168 > 0`) の発生源 | [PY-82] #2642 |
| `useGlobalIndex>0` の表 (`0x1005730` の `dl=1` 分岐 `[rip+0x5dcad3]`) | `dl=1` の経路を C 側で rack 扱いしている | [PY-82] #2642 |
| 選択 gating `0xffac20` の `*p` 書込み元 (PY-249 で 5 箇所・4 関数を確定。F の条件・F4 の式・S の書込み元は未確定。節は `REPORT_PY249.md`) | 選択不可の channel で結果が変わる可能性。C 側は未モデル | [PY-82] #2642 |
| `+0x32c` への byte 書込み 9 箇所のうち 5 件 (`0x6e9f4d`・`0x82bbf4`・`0x82bcb5`・`0x82bce0`・`0xfe96ed`) の基底の型。残り 4 件 (`0x11f8889`・`0x11f88e9`・`0x11f8981`・`0x11f8a43`) はチャネル表の要素と確定 (節は `REPORT_PY249.md`) | 5 件が channel item 以外への書込みかは未確定 | [PY-82] #2642 |
| `item+0x32d` の前置と後段 UI 分岐 (`+0xd34`・`+0x160`) | UI 状態のみ。C provider に UI 状態は無い | 追跡のみ (子は起票しない) |
| `setChannelPitch` の効果関数・guard の PE (意味論の残り。確定済み部分は `REPORT_PY72.md`) と C provider / mock 実装 | 未実装 | #2576 (PY-77)・#2563 (PY-76) |

### 次の提案 (起票先 [PY-82] #2642)

- `0x1005730` の global 表 (`[rip+0x5dcad3]`) の対応を解決し、rack と global の違いを REPORT に残す。
- `0xffac20` の判定は本節で読んだ。残りは前提ゲート `0xd5af58` と `0xd82c6a` の vtable 先を読み、判定条件を確定する。(→ 前提・後段の判定条件は下の PY-248 節で確定。残りは F1・F2・Z の意味と D の同定)

## PY-248 (#3767): 前提ゲート `0xd5af58`・後段ゲート `0xd82c6a` の判定条件

親: #2642 (PY-82)・子 #3767 (PY-248)。受入条件の項目 1・2 (判定条件を PE 解析箇所つきで残す) を扱う。全件は `analysis/flapi/py248_gate_chain.py` で再現する。

- 既知類型との関係: 該当なし (lift 作業ではない。PE 逆アセンブルによる判定条件の確定)。
- 測定 commit: `614b84bcf` (再現スクリプトを含む commit。main 取り込みの rebase 前の同内容は `e1ad20d6d`)。以後の docs のみの commit では `analysis/` などのコード範囲の差分は 0 行 (下記)。

### 結論

- 2 ゲートは**同じ receiver `O`** の仮想メソッドを呼ぶ。`O` の型は `TFLProgramInfo` (VMT `0x125B1C0`。VMT+0xe6 の短文字列で確認)。
- 前提 (`0xd5af58` → VMT+0x98 = `0x1262B80`): 真 ⟺ `F1 == 0` かつ `F2 == 0` かつ `Z == 0` かつ `dword[D+0x168] <= 0`。
- 後段 (`0xd82c6a` → VMT+0x88 = `0x1262A90`): 真 ⟺ `F1 == 0` かつ `F2 == 0` かつ `Z == 0`。
- `Z` は `O.vt[+0x48]()` (VMT+0x48 = `0x1262950`) の返り値 = `byte [0x13E7628]`。
- 意味 (呼出し側から確定): 前提が偽なら status `-2` のまま。後段は status < 0 のときだけ見て、真なら例外文言を設定し、偽なら例外を出さない。`F1`・`F2`・`Z` の状態名と `D` の同定は未確定 (未解決表)。

### 連鎖 (起点・生成・vtable)

| 段 | PE 解析箇所 | 内容 |
|---|---|---|
| 起点 `S` | `0xd5af44`・`0xd82c6a` の `mov rax,[rip+d]` | 両ゲートが同じ cell `0x15E4790` を読む (PE 値 `0x141D6B8`) |
| `X1 = [S]` | cell `0x141D6B8` | PE 値 0。実行時に `0x976aad` の `mov [0x141D6B8], rax` で埋まる (遅延生成 `0x976a90` → ctor `0x976b60`) |
| `O = [X1+8]` | 生成 `0x1263571` (関数 `0x1263540`)・`0x1264145` (関数 `0x1264100`) | `[X1+8]` が null のとき `0x125da90` がクラス参照 `[0x125b0f8]` (PE 値 `0x125b1c0`) から生成する。ctor `0x976b60` は `[X+8]` を 0 で初期化する (非 0 は入れない) |
| vptr | `0x410320` → VMT-0x30 `0x40f960` (NewInstance。InstanceSize = VMT-0x80 = `0x78`) → `0x40fb66` `mov [rsi],rdi` | vptr = クラス参照 = VMT `0x125B1C0` |

前節の記述の訂正 (本節が正):
1. 連鎖の中段は `0x141D6C0` ではない。`[[[0x15E4790]]+8]` は `[0x15E4790]` → `0x141D6B8` → `[0x141D6B8]` (= X1、遅延生成) → `+8` (= O) の 3 段。`0x141D6C0` は `0x976a90` の関数ポインタ (`call [0x141D6C0]` の後に `mov [0x141D6C0],0`) で、ゲートの連鎖には無い。
2. `G2 = 0x1643790` は誤り。`.text` に `0x1643790` を指す RIP 相対参照は 0 件 (`pe_xref.py`)。
3. 後段の `[[[0x861b1f]]+8]` の `0x861b1f` は RIP 相対の disp で、解決先は `0x15E4790` (両ゲート共通)。

### 判定式 (VMT の逆アセンブル。スクリプト §4・§5)

| 変数 | 定義 (cell → 実体) | 読み (逆アセンブル VA) | 書込み (セル読込み直後の store) |
|---|---|---|---|
| F1 | cell `0x15E04A8` → byte `0x16BAFF0` (bss) | 後段 `0x1262a95`・前提 `0x1262b85` (`cmp byte [rax],0`) | 1: `0xc4dea0`・`0xd1a2ac`。0: `0xc4ea3b`・`0xd1cb19` |
| F2 | cell `0x15E0FF0` → byte `0x16BAFF1` (bss) | 後段 `0x1262aa1`・前提 `0x1262b91` | 1: `0xf520eb`・`0xfefbd3`・`0xfff311`・`0x1042e47`・`0x11d6145`。0: `0xf46338`・`0xf53f20`・`0xfefcd7`・`0x11d6310`・`0x11d631f`。`bl`: `0xfff3c3`。`cl`: `0x10440af` |
| Z | cell `0x15E1890` → byte `0x13E7628` | `O.vt[+0x48]` (`0x1262950`) を前提 `0x1262ba6`・後段 `0x1262ab6` で呼ぶ | 1: `0x11c761c`・`0x1262977` (VMT+0x60 の setter) |
| D | cell `0x15E30F8` → cell `0x15F7190` (bss) → D | 前提 `0x1262bad`〜`0x1262bbe`: `cmp dword [D+0x168],0` の後 `jle` (`<= 0` で真) | 未特定 (未解決表) |

- 前提 `0x1262b80`: F1 → F2 → `O.vt[+0x48]()` → `D+0x168` の順に見る。いずれかが真なら偽 (`xor eax,eax`)、全て通れば `mov al,1`。
- 後段 `0x1262a90`: F1 → F2 → `O.vt[+0x48]()` の順。いずれかが真なら偽、全て偽なら真。

### 呼出し側の意味 (`0xd5af30`・`0xd82c20` の逆アセンブル)

| 前提 | 後段 (status < 0 のときだけ見る) | 結果 |
|---|---|---|
| 真 | — | 範囲検査。範囲外 `-4`、範囲内 `0` (選択) |
| 偽 | 真 | status `-2` → 例外 "Operation unsafe at current time" (`0xd82d18`) |
| 偽 | 偽 | status `-2` → 例外なし (`0xc38bc0` へ。`0xc38bc0` は成功経路と同じ戻り値を作る関数と推定) |
| 真 (範囲外 `-4`) | 真 | 例外 "Index out of range" (`0xd82d3c`) |
| 真 (範囲外 `-4`) | 偽 | 例外なし (`0xc38bc0`) |

- 含意: F1・F2・Z が全て 0 で `D+0x168 > 0` のとき、"Operation unsafe at current time" が出る (前提だけが偽になる経路)。F1・F2・Z のいずれかが 1 なら、status `-2` は例外なしで戻る。
- C provider (`provider/fl_engine.c`) と mock は未モデル (常に選択)。本節は C・mock を変えない。

### 再現と測定

- 展開: `mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin'` (実測 2.8 秒)。
- 実行: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/py248_gate_chain.py` (測定 commit `614b84bcf` を取り込んだ HEAD `d5f1d537f` で実行: 走査 39.0 秒、instructions=5022467)。前後の load average (uptime 1/5/15 分): `0.28 0.43 0.33` → `0.90 0.57 0.38`。rebase 前の `e1ad20d6d` でも 2 回実行し、出力は走査秒以外が一致。
- ネガティブコントロール: VMT の同定を 1 スロットずらす (クラス参照 `0x125b0f0` を読む) と、値 `0x20000` がファイル内に無く VMT 名の読みが失敗する (FAIL)。正しい `0x125b0f8` では `TFLProgramInfo` を得る (PASS)。
- 差分 0 の証跡: `git diff 614b84bcf HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR の docs commit で確認)。

### 検証範囲 / 範囲外

- 範囲内: 2 ゲートの呼出し先 (VMT の 3 スロット)、判定式 (VMT の逆アセンブル)、`O` の生成 2 件、VMT の同定、F1・F2・Z の書込み候補 (セル読込み直後の同一レジスタへの byte store を全 `.text` で走査)。
- 範囲外: `X1` の書込みは `0x976aad` の 1 件のみ確認。`X1+8` (= O) の書込みは生成 2 件のみ (`this` 経由の書込みは未走査)。D の生成と `+0x168` の書込み元 (未特定)。F1・F2・Z の状態名。実機 FL の動作。
- 限界: 書込み走査は「セル読込み → 同一レジスタへの byte store (直後 5 命令以内)」の型に限る。別レジスタへ写した後の書込みは拾わない。全 `.text` の `dword [reg+0x168]` 書込みは 98 件あり、そのうち D のものは同定していない。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| F1・F2・Z の意味 (どの状態で 1 になるか)。Z の 2 件目の setter `0x11c761c` の文脈 | 例外が出る実行時条件を説明できない | [PY-82] #2642 (親へ提案) |
| D (cell `0x15F7190`) の生成箇所と `+0x168` の書込み元 | 前提ゲートの偽条件 (`D+0x168 > 0`) の発生源 | [PY-82] #2642 (親へ提案) |
| `O` (= `X1+8`) の書込みは生成 2 件のみ。`X1` の `this` 経由の書込みは未走査 | O の型の同定の範囲。他の代入があれば型が変わりうる | [PY-82] #2642 |
| C provider・mock の反映 (前提・後段の判定を含む) | 未実装 (常に選択) | 親 #2642 の残り (受入 2・3) |

### 次の提案 (親 #2642 へ)

- F1・F2・Z の書込み箇所 (上の表) の周辺関数から状態名を付ける。
- cell `0x15F7190` への store を探して D の生成箇所を読み、`+0x168` の書込み元を特定する。

## PY-5413 (#6014): F1・F2・Z の書込み関数と状態名 (子 1 の結果)

親: #2642 (PY-82)・子 #6014 (PY-5413)。再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/py5413_flag_writers.py` (0.2 秒・rc 0)。

### 結論

- 3 フラグとも書込み関数は境界が確定した (`.pdata`)。F1 は 4 箇所が 4 関数 (`0xc4dba0`・`0xc4e570`・`0xd18130`・`0xd1af20`)、F2 は 12 箇所が 6 関数 (`0xf46310`・`0xf51fd0`・`0xfefba0`・`0xfff070`・`0x1042d20`・`0x11d58c0`)、Z は 1 関数 (`0x11c71b0`) + setter `0x1262970`。
- **状態名は確定できなかった**: 書込み関数の周辺 (含む関数の全 RIP 参照) に読める文字列が無く、呼出し元の関数にも状態を示す文字列が無い。よって F1・F2・Z の名前は**未確認**。推測では付けない。
- 直接の呼出し元で確認できたのは: F1 の set/clear 関数 `0xc4dba0` の呼出し元 `0xc4f32e` (`0xc4ecf0`)、F2 の `0x1042d20` の呼出し元は E8 全走査で 54 件 (`0xfefba0` は 15 件)、Z の `0x11c71b0` の呼出し元は `0x11c88d3` 1 件 (`0x11c8870`、`[0x16bcc00] != 0` のときだけ)。
- 間接呼出し (vtable 経由) は E8 走査で拾えないため、呼出し元は下限。

### 書込み関数の表 (`py5413_flag_writers.py` の出力)

| フラグ | 書込み箇所 (set 1 / clear 0) | 含む関数 (`.pdata`) | 直接の呼出し元 |
|---|---|---|---|
| F1 | `0xc4dea0` (1), `0xc4ea3b` (0) | `0xc4dba0`・`0xc4e570` | `0xc4f32e`・`0xc4f35b` |
| F1 | `0xd1cb19` (0) | `0xd1af20` | 直接呼出し無し |
| F1 | `0xd1a2ac` (1) | `0xd18130` | `0xd1d656`・`0xd1f026` |
| F2 | `0xf520eb`・`0xf53f20` | `0xf51fd0` (set/clear 両方) | `0xf547f3`・`0x10055ec`・`0x125946c`・`0x1319d61` |
| F2 | `0xfefbd3`・`0xfefcd7` | `0xfefba0` (定数 1 と 0 の store) | 15 件 |
| F2 | `0xfff311` (1)・`0xfff3c3` (レジスタ値 `88 18`) | `0xfff070` (定数 0 は未確認) | 直接呼出し無し |
| F2 | `0x1042e47` (1)・`0x10440af` (レジスタ値 `88 08`) | `0x1042d20` (定数 0 は未確認) | 54 件 |
| F2 | `0x11d6145` (1)・`0x11d6310`・`0x11d631f` (0) | `0x11d58c0` (定数 1 と 0 の store) | 7 件 |
| F2 | `0xf46338` (0) | `0xf46310` | `0xf53d09`・`0xf53d7d`・`0xf53dca`・`0xf53e75` |
| Z | `0x11c761c` (1) | `0x11c71b0` | `0x11c88d3` (1 件) |
| Z | `0x1262977` (1) | `0x1262970` (setter・vt+0x60) | 間接のみ |

- F1 の set `0xc4dea0` と clear `0xc4ea3b` は別関数。F1 に set/clear が同一関数で対になる箇所は無い。
- 「対」の判定は store の値で行う (スクリプト §4)。同一関数に定数 1 と定数 0 の store があるのは F2 の `0xf51fd0`・`0xfefba0`・`0x11d58c0` の 3 関数。`0xfff070`・`0x1042d20` は定数 1 の store のみで、もう一方は `88 xx` (レジスタ値の store) のため定数 0 は PE 上で未確認。
- 測定 commit: `d444114e6` (`py5413_flag_writers.py` を含む commit)。以後 `tools/python/analysis` の差分は本 PR 内の docs のみ。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| F1・F2・Z の状態名 (どの機能状態を表すか) | 例外が出る実行時条件を説明できない | #6029 [PY-5416] (子 issue。親 #2642) |
| 書込み関数の実行時の呼出し条件 (vtable・`[0x16bcc00]` 等の runtime 値) | 1 になる条件が静的に決まらない | [PY-82] #2642 |
| Z の 2 件目 setter `0x1262970` の呼出し元 (間接) | 同上 | [PY-82] #2642 |
