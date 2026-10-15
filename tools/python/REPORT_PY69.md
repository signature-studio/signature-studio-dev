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
| 前提ゲート `0xd5af58` (`[[[0x15E4790]]+8]` の vtable `+0x98`) の判定条件。偽なら status `-2` のまま返る。`-2` の文言 (上記) から「操作不可時の失敗」と推定するが未確定 | 偽の経路で結果が変わる。C provider は常に選択する | [PY-82] #2642 |
| ゲート `0xd82c6a` (`[[[0x861b1f]]+8]` の vtable `+0x88`) の意味。真なら status < 0 を例外化、偽なら成功経路 `0xc38bc0` | `-4`・`-2` の例外の有無 | [PY-82] #2642 |
| `useGlobalIndex>0` の表 (`0x1005730` の `dl=1` 分岐 `[rip+0x5dcad3]`) | `dl=1` の経路を C 側で rack 扱いしている | [PY-82] #2642 |
| 選択 gating `0xffac20` の `*p` 書込み元 (PY-249 で 5 箇所・4 関数を確定。F の条件・F4 の式・S の書込み元は未確定。節「PY-249」) | 選択不可の channel で結果が変わる可能性。C 側は未モデル | [PY-82] #2642 |
| `+0x32c` への byte 書込み 9 箇所のうち 5 件 (`0x6e9f4d`・`0x82bbf4`・`0x82bcb5`・`0x82bce0`・`0xfe96ed`) の基底の型。残り 4 件 (`0x11f8889`・`0x11f88e9`・`0x11f8981`・`0x11f8a43`) はチャネル表の要素と確定 (節「PY-249」) | 5 件が channel item 以外への書込みかは未確定 | [PY-82] #2642 |
| `item+0x32d` の前置と後段 UI 分岐 (`+0xd34`・`+0x160`) | UI 状態のみ。C provider に UI 状態は無い | 追跡のみ (子は起票しない) |
| `setChannelPitch` の効果関数・guard の PE (意味論の残り。確定済み部分は `REPORT_PY72.md`) と C provider / mock 実装 | 未実装 | #2576 (PY-77)・#2563 (PY-76) |

### 次の提案 (起票先 [PY-82] #2642)

- `0x1005730` の global 表 (`[rip+0x5dcad3]`) の対応を解決し、rack と global の違いを REPORT に残す。
- `0xffac20` の判定は本節で読んだ。残りは前提ゲート `0xd5af58` と `0xd82c6a` の vtable 先を読み、判定条件を確定する。

## PY-249 (#3769): 選択ゲート `0xffac20` の `*p` 書込み元と `+0x32c` 書込み先の型 (親 #2642 の項目 3・5)

- 親 #2642 (PY-82) の分割。項目 1・2 (前提ゲート `0xd5af58`・後段ゲート `0xd82c6a`) は #3767 (PY-248)、項目 4 (`useGlobalIndex>0` の表) は #3684 (PY-232)。本節は項目 3 (`*p` 書込み元) と項目 5 (`+0x32c` 書込み 9 箇所の型) のみ。
- 既知類型との関係: 該当なし (lift 作業ではない。PE 逆アセンブルと静的参照の列挙による意味論の確定)。
- 測定 commit: `527bc1eee` (`analysis/flapi/pe_py249_probe.py` を追加した commit)。コードの変更はこの 1 件のみ。以後の commit は `tools/python/REPORT_PY69.md` と `docs/DOC_MAP.md` (索引の行) のみ。
- 差分 0 の証跡: `git diff 527bc1eee HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (PR 本文の検証 HEAD で再確認)。
- 入力: `fl-win64.tar.zst` から `block00031_PE.bin` (22,227,016 B) のみ展開 (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'`、実測 2.9 秒)。
- 再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py249_probe.py 24` (静的値と 15 箇所の文脈を出す。実測 0.09 秒。load average 0.06 / 0.32 / 0.30 (1・5・15 分平均・実行前)、nproc 4)。

### 結論 (項目 3: `*p` の書込み元)

- 判定式 (再確認): `0xffac20(item) = (*p < 0) ∨ (item.+0x798 == *p)` (`0xffac20`〜`0xffac43`)。`p = *(0x15E3A60) = 0x154528c`。
- `*p` の PE 静的初期値は `-1` (`pe_va_read.py`)。実行時に `*p < 0` の間は全 channel が選択可能 (ゲート真)。
- `*p` への dword 書込みの候補は `0x15E3A60` を読んだ直後の `[reg]` 書込み 6 件 (`pe_slot_writers.py 0x15e3a60 0`)。`0xfffa00` は基底が `0x15E0BD0` 由来で偽陽性 (`pe_py249_probe.py` の節 A が由来スロットを出す)。残り 5 件が真の書込みで、関数は 4 つ。

| 書込み | 所属関数 | 書く値 | 条件 |
|---|---|---|---|
| `0x103b781` | F = `0x103b710(ecx=id, dl=mode, r8b, r9b)` | `max(ecx', -1)` (符号付き) | F の判定 (下) |
| `0x103b9ec` | F2 = `0x103b950(ecx=A, edx=B)` | `B` | `*p == A` のとき |
| `0x103ba02` | F2 | `A` | `*p == B` のとき (`*p == A` でない場合) |
| `0x103be3a` | F3 = `0x103bd60(ecx=id, edx=mode)` | `min(max(*p,-1), R-1)`、`R = 0x103b7c0()` | ループ後に無条件 |
| `0x103c01c` | F4 (`0x103bee0` 付近〜`0x103c034`。先頭は推定) | `esi` | 下 (F4) |

- **F の判定** (`0x103b710`〜`0x103b7b7`、分岐を順に追った):
  - `S` = 状態バイト `byte[*(0x15E4B08)]`。静的初期値は `*(0x15E4B08) = 0x15452a0`、`byte[0x15452a0] = 1`。
  - `A = (ecx == *p) ∨ (S == 1) ∨ (dl == 3)` (`0x103b71b`・`0x103b726`・`0x103b72b`)。初期状態は `S == 1` なので `A` は真。
  - `A` 偽のとき、`dl ≠ 2` かつ `(S == 2 ∨ dl == 1)` なら `ecx' = -1` として書込みへ進む (`0x103b73a`〜`0x103b753`)。それ以外は書かず、フラグ `R` を 3 にする (`0x103b79a`)。
  - 書込みへ進むと、`*p == ecx'` かつ `r8b ≠ 1` なら書かない (`0x103b75c`〜`0x103b76b`)。それ以外は `*p ← max(ecx', -1)` (`0x103b76d`〜`0x103b781`)。
  - 書いた後、フラグ `R` (`0x1548b95`) = 1 (`r9b == 0` なら 2)。`dl = 1` なら通知 `0xbd68e0(0x29, 0)` (`0x103b7a7`)。`R` は `0x103c392`・`0x103c53b`・`0x103c5ac`・`0x103c628` で読まれる (意味は未確定)。
  - F の呼出し例 (確認済み): `0xfff9e8` (`ecx = item.+0x798`、`dl=0`、`r8=0`、`r9b=1`)、`0x11f8856` (`ecx=-1`、`dl=3`、`r8=0`、`r9b=1`)、`0x103be52` (`ecx=-1`、`dl=3`、`r8b=1`、`r9b=1`)。
- **F2** (`0x103b950`): チャネル表 `T1` (`0x15E2218`) の要素を走査し、`+0x798` が `A` または `B` の要素に `0xffaf40` を呼ぶ。その後 `*p` の `A`↔`B` を入れ替える (推定: チャネル順の入替。`0xffaf40` の意味は未確定)。
- **F3** (`0x103bd60`): 冒頭で旧 `*p` を `r13d` に保存する (`0x103bd77`)。チャネル表の `+0x798` を比較して走査し、ループ後に `*p ← min(max(*p,-1), R-1)`。`id == 旧 *p` かつ `mode` が奇数のとき `F(-1, 3, 1, 1)` を呼ぶ (`0x103be3c`〜`0x103be52`)。
- **F4** (`0x103c01c` の関数): エントリで `esi = *p` (`0x103befd`)。`0x103b7c0()` 個の配列 `[rbp+0x28]` を `0x417fc0` で作る (`0x103bf04`〜`0x103bf18`)。チャネル表の要素の `+0x798` を配列へ記録し (記録の箇所 `0x103bfac` 以降は未読)、`k` を降順に走査して `arr[k] == 0` の `k` で `esi > k` なら `esi -= 1`。結果 `*p ← esi` (推定: 未使用の id の分だけ `*p` を下げる)。ゲート `0x103bee8` の `call [rax+0x80]` は未確定。

### 結論 (項目 3: 状態バイト `S` の書込み元)

- `S` (`*(0x15E4B08)` の指す先) の書込み元は 2 系統:
  - `0x11a15b0` 系 (`0x11a1626`・`0x11a1632`・`0x11a163e`・`0x11a164a`): `S ← map(v)`。`v` は `call 0xba6540` が出力する `[rbp+0x1cc]`。`map`: `v=0→0`・`v=1→1`・`v=2→2`・その他 `→1`。`[rbp+0x200] == 0` のときだけ実行される。
  - `0x11a56d0` 系 (`0x11a56d9`・`0x11a56e5`): `S ← ([arg+0x80] ≠ 0) ? 1 : 0`。
  - 両者とも直接 call は 0 件 (`pe_callgraph.py callers`)。呼出し元は未確定 (間接呼出し経由と推定)。
- `S` の読込み: `0x103b71f`・`0x103b73a` (F)、`0x120ccbb` (`sete dl` で `0x8404a0` へ渡す)。`0x15452a0` 自体への RIP 相対参照は 0 件。`S` は `Q` (`0x15E4B08`) 経由でしか触られない (`Q` の参照 10 件・store 0 件)。

### 0xea6b30 の呼出し位置 (#3769 の次の手順 1)

- `0x11e84a0(id)` は、排他選択ループ (`0x11e84ef`〜`0x11e853f`) の**後**で `0xea6b30` を呼ぶ (`0x11e85b5`)。
- その前に 3 つの gate がある (いずれか偽なら `0xea6b30` を呼ばず `0x11e85ba` へ進む):
  - `[G+0xd34] ≠ 0` (`G = *(0x15E35C8)`、`0x11e8542`〜`0x11e8554`)。
  - `byte[*(0x15E1748)] ≠ 0` (`0x11e8556`〜`0x11e8560`)。
  - `item.+0x160 ∈ {4,5}` (`item = fe8bb0(*T1, id)`、`0x11e8562`〜`0x11e859a`。mask `byte[0x11e8604] = 0x30`)。
- 呼出し引数: `rcx = [G+0xd34]`、`edx = 0`、`r8d = id`、`r9b = 1`。`0xea6b30` 以下の閉包 (`0xea6e50` → `0xdce130` → `0x103b710`) は既存の記述 (`0xd5af30` 節) どおりで、本節では再確認していない。

### 結論 (項目 5: `+0x32c` 書込み 9 箇所)

| 書込み | 所属関数 | 基底の由来 | 判定 |
|---|---|---|---|
| `0x11f8889` | `0x11f8840` | `fe8bb0(*T1, idx)` の戻り値 | チャネル表の要素 (確定) |
| `0x11f88e9` | `0x11f8840` | 同 (`mov rdi, rax`) | チャネル表の要素 (確定) |
| `0x11f8981` | `0x11f8840` | 同 | チャネル表の要素 (確定) |
| `0x11f8a43` | `0x11f8840` | 同 | チャネル表の要素 (確定) |
| `0x6e9f4d` | `0x6e9f40` (`if [rcx+0x32c] != dl then store`) | 引数 `rcx` | 未確定。直接 call 0 件 |
| `0x82bbf4` | `0x82bb50` | フレーム `[rbp+0x90]` (引数由来) | 未確定。直接 call 0 件 |
| `0x82bcb5` | `0x82bb50` | 同 | 未確定 |
| `0x82bce0` | `0x82bcd0` | 引数 `rdx` の `[rdx+0x90]` | 未確定。直接 call 0 件 |
| `0xfe96ed` | `0xfe95a0` | フレーム `[rbp+0x60]` | 未確定。直接 call 6 件 (`0xe210e2`・`0xead98e`・`0xff5ad7`・`0x1001653`・`0x11c3835`・`0x132b42d`。呼出し元の型は未読) |

- 確定の根拠 (4 件): `T1 = 0x15E2218` の静的初期値は `0x16bafc8` (コンテナ)。`0x11f8840` は `T1` 由来の要素だけに書く (`0x11f8878`・`0x11f88cc`・`0x11f896e`・`0x11f89da` の 4 箇所すべて `0x15E2218`)。同じ表の要素の `+0x798` を `0x103b950` (`0x103b9ad`) と `0x103bd60` (`0x103bda2`) が id と比較し、`0x11e84a0` は `+0x32d`・`+0x160` を同じ表から読む。よって表の要素は channel item と同定する (同定の根拠は `+0x798` の比較。構造体の正式名称は未確定。REPORT_PY69 の `item` と同じ語)。
- 未確定の 5 件は、`+0x34` (word)・`+0x304`・`+0x310`・`+0x14`・`+0x158`・`+0x160`・`+0x398` (16 件の配列) などを読むが、表示した窓 (関数先頭から書込みまで) では channel item の `+0x798` を読む箇所は見当たらない (関数全体は未読)。型の確定には呼出し元の vtable 先か、呼出し元の基底の由来が要る (未解決表)。

### 検証 (測定 commit `527bc1eee`)

| 検証 | 結果 |
|---|---|
| `pe_disasm.py 0xffac20 30` | 判定式 (`cmp [p],0`・`cmp ecx,[p]`) を再確認 |
| `pe_xref.py 0x15e3a60` | hits 50・stores 0 (測定 63.0 秒) |
| `pe_slot_writers.py 0x15e3a60 0` | 候補 6 件 (`candidates=6`)。測定 63.9 秒。偽陽性 1 件 (`0xfffa00`) は節 A で切り分け |
| `pe_xref.py 0x15e4b08,0x15e2218` | 合計 hits 1573 (`Q` 10・`T1` 1563)・stores 0 (測定 63.7 秒) |
| `pe_xref.py 0x15452a0,0x1548b8e,0x1548b95,0x1548b89,0x154528c` | `0x1548b95` の store 4・load 4、`0x15452a0`・`0x154528c` の RIP 相対参照 0 (測定 63.3 秒) |
| `pe_py249_probe.py 24` | 静的値 (`*p` = -1、`S` = 1、`T1` = `0x16bafc8`、mask = `0x30`)。節 A の基底由来 (`0x15e3a60` 5 件・`0x15e0bd0` 1 件)。節 B の由来 (`fe8bb0(*0x15e2218)` 4 件、`frame[..]` 3 件、なし 2 件 (`0x6e9f4d` は `rcx`、`0x82bce0` は `rdx` の引数由来で手で確認))。実行 0.09 秒 |
| ネガティブコントロール (節 A) | 基底の由来を見て `0xfffa00` (`0x15e0bd0`) を除外できる。`0x15e3a60` と一致する 5 件とは区別される |

- 検証範囲 / 範囲外: 静的な PE 解析のみ。実行時の値 (`*p`・`S`) は推定。`*p` と `S` の書込みは線形の窓 (40 命令) と RIP 相対の参照に基づき、別レジスタへの複写経由の書込みは見ていない (未解決表)。実機 FL の挙動は検証していない。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 項目 5 の 5 件 (`0x6e9f4d`・`0x82bbf4`・`0x82bcb5`・`0x82bce0`・`0xfe96ed`) の基底の型。直接 call は `0x6e9f40`・`0x82bb50`・`0x82bcd0` が 0 件、`0xfe95a0` が 6 件 (呼出し元の型は未読) | この 5 件が channel item 以外への書込みかが未確定 | [PY-82] #2642 |
| `S` の書込み元 (`0x11a15b0`・`0x11a56d0`) の呼出し元と、`0xba6540` の出力 `[rbp+0x1cc]` の意味 | `S` が 1 から変わる条件。`S == 1` の間は F の `A` が真 | [PY-82] #2642 |
| F4 (`0x103c01c`) の関数先頭・ゲート `0x103bee8` の `call [rax+0x80]`・配列への記録 (`0x103bfac` 以降) | `*p` の終値 (F4 の式) の確定。本節の式は推定 | [PY-82] #2642 |
| `G` (`*(0x15E35C8)` の `+0xd34`) と `byte[*(0x15E1748)]` の意味 | `0xea6b30` の gate の意味づけ (gate の式自体は確定) | [PY-82] #2642 |
| `0xffaf40` の内容 (F2・F3 から呼ばれる。チャネル順の入替・表示と推定) | F2・F3 の副作用 | 追跡のみ (子は起票しない) |
| 線形窓による書込み列挙の限界: `*p` を別レジスタへ複写して書く経路は、スロット読込みの 40 命令窓の外なら見えない | `*p` の書込み元の網羅性 (6 候補は窓内のみ) | 追跡のみ (子は起票しない) |
