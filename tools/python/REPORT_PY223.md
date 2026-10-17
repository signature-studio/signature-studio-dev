# PY-223 (#3627): 0xed4b70 (0x12da6d0 の唯一の呼出し元) を間接に呼ぶ候補の所在 (PE 解析。製品コード変更 0 件・解析スクリプト 2 本)

親: #3595 (PY-217) / 前段: PY-112 (#2932)。既知類型との関係: 該当なし (PE の逆アセンブル読解と検査スクリプト。lift 作業ではない)。

## 結論

- **受入 1 (間接 call 箇所の特定): 部分達成。** 0xed4b70 の所在 (関数ポインタ配列の添字 51) と、それを指せる vtable 候補 2 つ (基点 `0xed0bb0` のスロット `0x198`・基点 `0xed0c28` のスロット `0x120`) は確定した。ただし実際に呼ぶ call 箇所は 1 件に絞れない。候補は `call qword ptr [reg+0x198]` 24 件・`[reg+0x120]` 114 件 (仮想呼出し。receiver の vptr は実行時の値)。vptr を書く箇所が block00031 に無く、どの候補が receiver かは未確定。本 run で、`0xed0bb0` を指す 8 byte の絶対値・RIP 相対は PE 全体で 0 件と確定し (4 byte の 1 件は `.pdata` の RVA 値で、ポインタではない)、`0xed0c28` の材料はセル `0xed0b60` (読出し 1 件) だけと分かった (節「G1・ポインタ・vptr の材料」)。残りは子 #3888 (PY-264)。
- **受入 2 (obj が非 0 になる条件): 未着手** (子 #3889 (PY-265))。G1 への RIP 相対の書込みは 1 件 (`0x12d9629`・関数 `0x12d94f0`)。前 REPORT の「G1 の RIP 相対 store 0 件」は mov 系だけを数えた誤りで、ここで訂正する。
- **受入 3 (flag の書込み元): 未着手** (子 #3890 (PY-266))。`0x15e14a0` を RIP 相対で指す命令は 439 件。
- **受入 4 (全 PE block で G1・T への書込みを走査): 完了 (本 run)。** 313 block の絶対値参照 (8 byte・4 byte) で、block00031 の G1・T・flag・表・caller の VA を指すものは他 block に 0 件 (節「全 PE block の絶対値参照」)。
- 親 #3595 へのコメント (元の受入 5): 本 PR の範囲外。merge 後に PM が投稿する (子 issue は作らない)。
- 0xed4b70 の参照は、RIP 相対・`lea` が 0 件 (`pe_rip_refs.py`)、生バイト列 (4 バイト・8 バイト) の一致も表の 1 要素だけ。表の番地は、`.text` 内の 1 件 (`0xed0b60`) からだけ指される。

## 測定

- 測定 commit: `63789e470` (main の取り込み merge。以下の 2 本の検査と `flapi/pe_callgraph.py` は、この commit の内容で再測定した)。`git diff 63789e470 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (REPORT のみ変更)。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`)。展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C tools/python/work/py223 --wildcards '*block00031_PE.bin'` (2.9 秒)。展開先 `tools/python/work/py223/extracted/` は gitignore。
- 検査 (PASS): `FL_WIN64_DIR=$PWD/work/py223 python3 analysis/py223_indirect_callers.py` → `table.check PASS`・rc 0。所要 99.39 秒 (n=1)、user 99.31 秒、実行後の load average (1/5/15 分) `0.99 0.52 0.23`、並列数 1 (4 コア)。
- ネガティブコントロール: `--mutate` (表の添字 51 の値を 1 ビット反転したメモリ上の複製で検査) → `table.check FAIL`・rc 1。所要 98.74 秒 (n=1)。検査は効いている。
- 独立算法の検算: 命令の逆アセンブルを使わず、`.text` のバイト列を正規表現 `\xff[\x90-\x97]<disp32>` で数えた (`call r/m64` の ModRM mod=10 reg=010 の形)。結果は `[reg+0x120]` 114 件・`[reg+0x198]` 24 件で、逆アセンブル側と一致。
- 表の参照の検算: `pe_rip_refs.py 0xed4b70 0xed0c28 0xed0bb0 0x12da6d0` → `hits 0` (RIP 相対の `lea`/`mov` で指す命令は 0 件)。`pe_callgraph.py callers 0x12da6d0` → 直接 call 元 1 件 (`0xed4c6a` in `0xed4b70`)。
- 全 block 走査 (受入 4): `analysis/py223_block_scan.py` (測定 commit `63789e470`)。本番 (`block.check PASS`) は rc 0・23.48 秒 (n=1)・user 23.28 秒・実行後の load average `0.44 0.22 0.10`・並列数 1。`--mutate` は `block.check FAIL`・rc 1・23.43 秒。

## 全 PE block の絶対値参照 (受入 4)

`analysis/py223_block_scan.py`。素材の PE 313 個 (x64 258・i386 55・ImageBase 0x400000 の block は 165) の生バイト列に対し、block00031 の VA の値を 8 byte (qword) と 4 byte (imm32・絶対 disp32) のリトルエンディアン一致として数える。RIP 相対は、その命令と同じ PE の VA 空間の中だけを指すので、別 block の RIP 相対は block00031 の VA に当たらない (構造上の理由。線形走査はしていない)。

| 対象 (block00031 の VA) | 他 312 block の一致 (8 byte / 4 byte) | block00031 の一致 (8 byte / 4 byte) と場所 |
|---|---|---|
| G1 `0x15d51a0` | 0 / 0 | 1 / 1: `.data` の `0x15e4018` の qword (= &G1) |
| flag cell `0x15e14a0` | 0 / 0 | 0 / 0 |
| T base `0x193fcf8`・T row `0x193fd08` | 0 / 0 | 0 / 0 |
| 表の添字 51 `0xed4b70` | 0 / 0 | 1 / 1: 表の要素 (VA `0xed0d48`) |
| 表の基点 A `0xed0bb0` | 0 / 0 | 0 / 1: 4 byte のみ。`.pdata` の RUNTIME_FUNCTION の RVA 値 (ポインタではない) |
| 表の基点 B `0xed0c28` | 0 / 0 | 2 / 2: `.text` のセル `0xed0b60`、と `.text` 内の文字列データ中の非整列一致 (VA `0xed0dac`) |
| セル `0xed0b60` | 0 / 0 | 0 / 0 |
| caller `0x12da6d0` | 0 / 0 | 0 / 0 |

検査: (1) block00031 の既知の一致 (qword の `0xed4b70`・`0xed0c28`) が各 1 件以上 (PASS)。(2) x64 の全 258 block が自分の ImageBase の qword をヘッダに持つ (他 block の走査経路の対照。258/258 PASS)。(3) `--mutate` で (1) の値を反転すると FAIL (rc 1)。

結論: 他 block から G1・T・flag・表・caller への絶対値の参照は無い。この走査は書込み命令の列挙ではなく、絶対値参照 (8 byte・4 byte の値の一致) の走査である。他 block が G1 を書くには、実行時に計算した番地を使う必要があると推定する (根拠: block ごとに ImageBase が異なる別 PE で、他 block の絶対値は自 block の VA 空間を指すため)。この番地は静的な走査では見えない (限界は「検証範囲」節)。

## G1・ポインタ・vptr の材料 (前 REPORT の訂正を含む)

- G1 (`0x15d51a0`) の RIP 相対参照は 51 件 (`pe_rip_refs.py`): `cmp` 8・読出し (`mov`・`movsxd`) 42・書込み 1。**書込みは `0x12d9629` (`sub dword ptr [rip+0x2fbb70], 1`) の 1 件**で、関数 `0x12d94f0` (`.pdata` の RUNTIME_FUNCTION `0x12d94f0`〜`0x12d96d0` で確認。`pe_callgraph.py func` は `0x12d9450` を返すが、限界の節を参照)。この関数は G1 を 1 減らし、`G1 > 1` の間 `call 0x12d8d30(ecx=G1)` の戻り値が非 0 なら `0x12d9629` へ戻る loop。前 REPORT の「G1 の RIP 相対 store 0 件」は mov 系だけを数えた誤り。
- ポインタ格納セル `0x15e4018` (`.data`・値 `0x15d51a0`): RIP 相対の読出し 444 件 (`mov reg, [rip+..]`)。G1 はこのセル経由で広く扱われる。このセル経由の書込みは未走査 (子 #3889)。
- セル `0xed0b60` (`.text`・値 `0xed0c28`): RIP 相対の読出し 1 件 (`0x11b2af9`・関数 `0x11b2ac0`)。`0x11b2ac0` は `[0xed0b60]` を rcx に読み、`dl=1` で `call 0xed4ee0` する。rcx の使い道は未確定 (子 #3888)。
- `0xed0bb0`・`0xed0c28`・`0xed4b70`・`0x12da6d0` を指す RIP 相対: 0 件。

vptr 候補 (受入 1 の残り):
- `[reg+0x198]` (24 件) の receiver の vptr `0xed0bb0`: PE 全体に 8 byte の絶対値も RIP 相対も無い (4 byte の 1 件は `.pdata` の RVA 値で、ポインタではない)。静的に vptr を得る材料が無いので、算術で作る経路 (例: `0xed0c28 - 0x78`) を除けば、この 24 件は 0xed4b70 に到達しないと推定する (推定。算術経路は未検査)。
- `[reg+0x120]` (114 件) の receiver の vptr `0xed0c28`: 材料はセル `0xed0b60` の読出し 1 件 (`0x11b2af9`) だけ。receiver の vptr を格納する箇所は、このセルの値を複写する経路と推定する (子 #3888)。

## 0xed4b70 の所在 (表)

| 項目 | 値 (VA) | 根拠 |
|---|---|---|
| 表の範囲 | `0xed0bb0`..`0xed0d68` (55 要素・`.text` 内の連続した VA) | `py223_indirect_callers.py` の表の検査 |
| 0xed4b70 の添字 | 51 (オフセット `0x198`) | 同 |
| 0xed4b70 を含む qword の個数 (全セクション) | 1 (表の中) | 全セクションの qword 走査 |
| 表を指す aligned qword (表の外) | 1 件: `0xed0b60` → `0xed0c28` (`.text` 内) | 同 |
| コード中の RIP 相対・絶対参照が表の範囲を指す件数 | 0 件 (表の範囲内)。範囲 `[0xed0b00, 0xed0e00)` では 3 件 (`0xed0902`→`0xed0b38`・`0xed4899`→`0xed0de0`・`0x11b2af9`→`0xed0b60`。いずれも表の外) | 表の範囲は `py223_indirect_callers.py` の code refs into table 行。範囲を広げた件数は repo に含めない一時の線形走査 (同じ逆アセンブル方式) |
| 表を指す仮想 call の基点候補 | `0xed0bb0` (スロット `0x198`)・`0xed0c28` (スロット `0x120`) | `0xed0c28 + 0x120 = 0xed0d48` |

- `0xed0b60` の値 `0xed0c28` を読む命令は 1 件 (`0x11b2af9`、関数 `0x11b2ac0`)。`mov rcx, [0xed0b60]` の後に `call 0xed4ee0` (dl=1) する。`0xed4ee0` は dl≠0 のとき `0x410320(rcx, rdx)` の戻り値を `this` に入れ替える (推定: この `rcx` は vptr ではなく割付け・記述子の引数)。よって `0xed0c28` が vptr である根拠は無い (推定)。

## 間接 call の候補 (受入 1)

| スロット | 候補の数 (block00031) | 対応する基点 | 関数が T (`0x193fcf8` 付近)・G1 (`0x15d51a0`)・flag (`0x15e14a0`) を参照する件数 |
|---|---|---|---|
| `[reg+0x198]` | 24 | `0xed0bb0` | 0 (T・G1)・flag を参照する関数は 5 件 |
| `[reg+0x120]` | 114 | `0xed0c28` | 0 (T・G1)・flag を参照する関数は 0 件 |

`[reg+0x198]` で flag を参照する関数の仮想呼出し (確認した 3 件 `0xe78d8c`・`0x104878f`・`0x1242f47` はいずれも `mov rbx, [rax]` の直後の `call qword ptr [rbx+0x198]`。残り 2 件 `0x12f2ca1`・`0x12f87f4` は未確認):

| call 箇所 | 所属関数 | flag 参照数 |
|---|---|---|
| `0xe78d8c` | `0xe73950` | 2 |
| `0x104878f` | `0x1046a30` | 4 |
| `0x1242f47` | `0x123dbc0` | 2 |
| `0x12f2ca1` | `0x12f29d0` | 2 |
| `0x12f87f4` | `0x12f38b0` | 2 |

- 候補の絞り込みに使えない理由: 上の 5 件は receiver が `[rax]` (vptr) から得られる仮想呼出しで、receiver の vptr が `0xed0bb0` かどうかは静的に決まらない。`0xed0bb0` を vptr として書く `lea`・即値・絶対番地は block00031 に無い。
- 結論の強さ: 「0xed4b70 を呼ぶ仮想呼出しは `[reg+0x198]` (receiver の vptr が 0xed0bb0) か `[reg+0x120]` (vptr が 0xed0c28) のどちらか」までは確定。どの call 箇所かは未確定。

## 再現

```
cd tools/python
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py223 --wildcards '*block00031_PE.bin'
FL_WIN64_DIR=$PWD/work/py223 python3 analysis/py223_indirect_callers.py          # table.check PASS・rc 0
FL_WIN64_DIR=$PWD/work/py223 python3 analysis/py223_indirect_callers.py --mutate # table.check FAIL・rc 1
FL_WIN64_DIR=$PWD/work/py223 python3 analysis/flapi/pe_callgraph.py callers 0xed4b70,0x12da6d0
FL_WIN64_DIR=$PWD/work/py223 python3 analysis/flapi/pe_rip_refs.py 0xed4b70 0xed0c28 0xed0bb0 0x12da6d0
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py223 --wildcards '*_PE.bin'   # 全 PE block (313 個・約 3 秒)
FL_WIN64_DIR=$PWD/work/py223 python3 analysis/py223_block_scan.py                 # block.check PASS・rc 0 (約 23 秒)
FL_WIN64_DIR=$PWD/work/py223 python3 analysis/py223_block_scan.py --mutate        # block.check FAIL・rc 1
```

## 検証範囲 / 範囲外

- 範囲内: `block00031_PE.bin` の `.text` の逆アセンブル・表の所在・RIP 相対と絶対参照・間接 call の集計。全 313 PE block の絶対値参照 (8 byte・4 byte)。
- 範囲外: 実行時に計算される番地 (ポインタの値として格納される前の計算) による書込み。静的な絶対値・RIP 相対に現れないので、この走査では見えない。他 block の RIP 相対は、別 VA 空間を指すため対象外 (構造上)。実行時の値 (vptr の中身・flag の値・obj の値)。
- 限界 (関数境界): `pe_callgraph.py func 0x12d9629` は `0x12d9450` を返すが、`.pdata` (RUNTIME_FUNCTION) では `0x12d94f0`〜`0x12d96d0` の関数に含まれ、`0x12d9450`〜`0x12d94f0` の関数は `0x12d94ef` の `ret` で終わる (`0x12d94f0` の直前は int3 でない。`function_starts` の見落としと推定)。関数境界の根拠は `.pdata` とし、`pe_callgraph.py func` の結果は根拠にしない (`.pdata` の直接読みは repo に含めない一時の検算)。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1 の残り: `0xed4b70` を呼ぶ receiver の vptr (`0xed0c28` のセル `0xed0b60` からの格納経路) の書込み元。`0x11b2ac0` の呼出し側を含む | 呼出し箇所の絞り込み (`[reg+0x198]` 24 件は静的材料が無いと推定。`[reg+0x120]` 114 件が残る) | #3888 (PY-264) |
| 受入 2: `0x12d3ff0` の loop 分岐で `obj = qword [T + G1*192]` が非 0 になる条件 (`0xed4b70` の `[rbp+0x40]` 分岐と引数)。G1 の書込み元 (`0x12d9629`・セル `0x15e4018` 経由) | loop 分岐の入力 (PY-229 #3659 の前提) | #3889 (PY-265) |
| 受入 3: flag `byte [[[0x15e14a0]]+0x7e0+0x49e]` の書込み元 (`0x15e14a0` の RIP 相対参照 439 件) | flag の値 | #3890 (PY-266) |

## PY-265 (#3889): obj の書込み箇所と G1 の書込み元 (部分達成)

- 測定 commit: 解析スクリプト `analysis/py265_g1_writers.py` の追加 commit (PR 本文の HEAD。`git diff <測定 commit> HEAD -- tools/python` の出力は 0 行)。素材 `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`) の `block00031` を `work/py265/` に展開 (2.9 秒)。
- 結論 (受入 2 の一部): G1 (`0x15d51a0`) への書込みは、RIP 相対 1 件 (`0x12d9629`・関数 `0x12d94f0`。`.pdata` の境界と一致) と、セル `0x15e4018` 経由の候補 12 件 (直線の近似で、目視未確認)。`0x12d94f0` の直接 call 元は `0xed2c96`・`0x1004db5` の 2 件。
- 結論 (受入 1 の一部): `0xed4b70` は `0x12da6d0` を `dl=1` で直接 call (`0xed4c6a`) し、戻り値 `al==2` で loop を抜ける。`0x12da6d0` は T 行 (`0x193fd00`・`0x193fd08`) の行 (stride 24) へ、`0xfe8bb0` の戻り値を基点に書く。
- 訂正: issue の `store 0x12da89` は `0x12daa89` (`mov qword ptr [rcx+rdx*8], rax`・基底 `0x193fd08`) の桁落ち。`0x12da89f` は vcall (`call qword ptr [rsi+0x40]`) で store ではない。
- 未確定 (未解決): `obj` (`[T + G1*192]`) が非 0 になる分岐 (`0x12da6d0` の `[rbp+0x33]`・`0x12d3ff0` の loop 分岐) と、`[rbp+0x40]` の供給元。`0x12d3ff0` の中の T 参照 (`0x12d4013`・`0x12d4030`) は読み取り側で、書込みの確定は未了。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| obj が非 0 になる分岐の確定 (`0x12da6d0` の `[rbp+0x33]`・`0x12d3ff0`・`[rbp+0x40]` の供給元) | PY-229 (#3659) の前提 | #3889 (PY-265) を Refs のまま残す |
| セル `0x15e4018` 経由の 12 候補の目視確認 (reg 追跡は直線近似) | G1 書込み元の完全列挙 | #3889 |

## PY-264 (#3888): 0x11b2ac0 の呼出し経路と vptr 0xed0c28 の書込み元 (部分達成)

検査: `analysis/py264_vptr_writer.py` (測定 commit は本 PR の HEAD の親 `54a943aac`。素材 `fl-win64`・block00031 のみ展開)。

- 0x11b2ac0 の直接 call 元: 0 件 (`pe_callgraph.py callers`)。RIP 相対の `lea` が 1 件 (`0x1375a18`・関数 `0x1375990`)。この `lea` は `0x11b2ac0` を大域セル `0x15e0f78` に格納する (関数ポインタ経由の呼出し)。`0x15e0f78` の RIP 相対参照は 27 件。どの参照が呼出しかは未確定。
- 0x11b2ac0 の本体: `[0xed0b60]` の値 (= 0xed0c28) を rcx に読み、`dl=1` で `0xed4ee0` を呼ぶ (1 件)。`0xed4ee0` は `rcx` を `[rbp+0x60]` に保存し、`0x410320`・`0x40f9e0`・`0x423940` などを経て、`[rcx+8]`・`[rcx+0x10]`・`[rcx+0x28]`・`[rcx+0x58]` などを書く。`[rcx]` への store は本体 (深さ 1) に無い。
- vptr 候補 `0xed0c28` の絶対値: qword・dword の一致は `0xed0b60` (`.text` の 8 byte セル) と `0xed0dac` (文字列データ中の非整列一致) の 2 件のみ。`0xed0c28` を即値・`lea` で格納する命令は 0 件。`0xed0c28` は `.text` 内の表で、`[0xed0c28 + 0x120] = 0xed4b70` を確認 (検査の 1 行目で PASS)。
- 受入 1 (`0x11b2ac0` の呼出し側を 1 段以上辿り、vptr `0xed0c28` を格納する書込みを特定): **未達**。直接 call 元は無く、入口は大域セル `0x15e0f78` (参照 27 件)。`0xed0c28` を格納する命令は、既知の経路 (`0x11b2af9` の読出し → `0xed4ee0`) の深さ 1 には無い。
- 受入 2 (`0xed0bb0` を vptr として得る経路が無いことを関数単位で確かめる): **未達**。8 byte の絶対値・RIP 相対は前 REPORT の通り 0 件 (4 byte の 1 件は `.pdata` の RVA)。算術で作る経路 (例 `0xed0c28 - 0x78`) は未検査。
- 受入 3 (結果を REPORT に残し、親 #3627 にコメント): REPORT は本節。親へのコメントは PM の判断に任せる。

未解決 (起票先付き):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x15e0f78` の参照 27 件のうち、`0x11b2ac0` を呼ぶ call の特定 (間接 call の receiver と vptr の書込み元) | 受入 1 の残り。`[reg+0x120]` 114 件の receiver の確定 | #3888 (継続) |
| `0xed4ee0` 以下の深い callee (`0x410320`・`0x40f9e0`・`0x423940`) で、rcx を vptr として store する箇所の有無 | 受入 1 の残り | #3888 (継続) |
| `0xed0bb0` の算術経路 (`0xed0c28 - 0x78` など) の検査 | 受入 2 | #3888 (継続) |

### PY-264 続き (#3888 の再開 run)

- **前節の訂正**: 「大域セル `0x15e0f78`」は誤り。`0x1375a18` の `lea rcx, [rip-0x1c2f5f]` (= `0x11b2ac0`) は、`0x1375a11` の `mov rax, [rip+0x26a560]` で得たポインタ先 (セル `0x15dff78`) に `mov [rax], rcx` で格納する (`0x1375a1f`)。`0x15e0f78` は読み出しの番地を取り違えた値。
- `0x15e0f78` の RIP 相対参照は 27〜28 件 (`pe_rip_refs.py`)。全件が `mov reg, [rip+..]` の**読出し**で、直後 8 命令内に `call` があるのは 6 件 (`0x1042fb8`・`0x1186416`・`0x11864a2`・`0x11f36ac`・`0x103a90a`・`0x103a915`。すべて直接 call (`call 0x12d4940` などで、間接 call は 0 件)。`analysis/py264_cell_callers.py` の引数 (hits 27 件の番地) を逆アセンブルして数えた)。残り 21 件は直後 8 命令に call が無い。直後 8 命令の範囲では間接 call が無いので、関数ポインタの呼出し箇所ではない。
- `0x11b2ac0` の RIP 相対 `lea` は 1 件 (`0x1375a18`) で、関数 `0x1375990` (直接 call 元 0 件)。`0x1375990` が呼出し経路の起点と推定するが、呼出し側は未特定。
- 大域ポインタ格納 `0x15dff78` 経由の書込みは本 run で未走査 (次の一手)。
- `pe_vptr_stores.py 0x0` (`lea` で作った vptr を `[reg+0]` に格納する箇所を全 .text 走査): 1 件 (`0x44a86e`・vtbl `0x13acb88`)。このツールは disp 0 だけを見るので、`0xed0c28` は disp 0 への `lea` 格納には現れなかった。他の disp (`0x120` 系の基底オフセットなど) は未走査。
- 受入 1・2 は引き続き未達。`0xed0c28` の格納箇所は未確定。

### PY-264 第 3 run (#3888): 呼出し経路の確定 (部分達成)

- 検査 `analysis/py264_chain_probe.py` → `chain.check PASS`・rc 0 (測定 commit は下記)。所要 211 秒 (n=1)。
- `0x1375990` の直接 call 元は 0 件 (`pe_callgraph.py callers`)。`0x11b2ac0` を格納するのは `0x1375a18` (`lea`) → `0x1375a1f` (`mov [rax], rcx`) で、`rax` は `[rip+0x26a560]` の値 (= セル `0x15dff78`)。セル `0x15dff78` の RIP 相対参照は 1 件 (`0x1375a11`)。
- 第 2 run の「`0x15e0f78` の 27 件」は、この経路の訂正により、呼出し経路の根拠として使わない。
- `0x11b2ac0` の本体は `0xed0b60` の値を rcx に読んで `0xed4ee0` を `dl=1` で呼ぶ (1 件)。`0xed4ee0` は `0x410320` を経由して vtable の間接 call (`call [rbx-0x28]`・`call [rbx-0x50]`) を行うが、vptr の格納はしていない。
- 未解決 (受入 1・2): `0x1375990` の呼出し元が直接 call で見えないため、間接 call の受け手を特定できていない。`0xed0c28` を receiver の vptr として格納する箇所は未確定。`0xed0bb0` の算術経路は未検査。
- 次の一手: `0x1375990` を格納する vtable (`0x11b2ac0` を含む間接 call の受け手) の探索。

### PY-264 第 4 run (#3888): vptr の書込み箇所の不在 (部分達成)

- 検査 `analysis/py264_vptr_scan.py` → `chain.check PASS`・rc 0。所要 38.4 秒 (n=1)。展開は 313 PE block (`*_PE.bin`)。
- 全 313 PE block で、vptr 候補の絶対値 `0xed0c28` は `.text` の 2 箇所 (`0xed0b60` のセル・`0xed0dac` の ASCII 文字列内)、`0xed0bb0` は `.pdata` の RVA 値 1 件 (ポインタではない)。`0x1375990`・`0x11b2ac0` の絶対値は 0 件。他 block から表への参照は無い。
- block00031 の `.text` で `0xed0000..0xed1000` を RIP 相対で指す命令は 10 件。うち `0xed0b60` は `0x11b2af9` の読出し 1 件、`0xed0b38`・`0xed0de0`・`0xed0f48`・`0xed0328`・`0xed0718`・`0xed0824`・`0xed0848` は表の内側 (`lea` / 読出し)。vptr への格納 (`mov [reg], reg`) は 0 件。
- 呼出し経路: `0x11b2ac0` は `rcx = [0xed0b60] (= 0xed0c28)`、`dl = 1` で `0xed4ee0` を呼ぶ。`0xed4ee0` は `dl ≠ 0` のとき `rcx` を `0x410320` に渡し、その戻り値を `[rbp+0x60]` に入れる。その後、`rcx` を引数にして `[rcx+8]`・`[rcx+0x10]`・`[rcx+0x18]`・`[rcx+0x19]` などを書く。つまり `rcx` は書かれる object の本体として使われており、`0xed0c28` は vptr そのものではなく object の番地と読める (推定)。`[0xed0c28]` の先頭 qword は `0xed62e0` (`.text` 内の値)。本 issue の「0xed0c28 は vptr」という前提は、この読みと合わないため再確認が要る。
- 表 A の `0xed0bb0` と表 B の `0xed0c28` は、スロット `+0x198` / `+0x120` が同じ `0xed0d48` (= `0xed4b70`) を指す。よって receiver は表 A でも表 B でも同じ仮想 call になる。
- 受入 1 (vptr `0xed0c28` の書込み箇所): **未達**。静的な格納は PE に無い。vptr は実行時に別の経路で作られると推定 (推定)。
- 受入 2 (`0xed0bb0` を vptr として得る経路の不在): **未達**。`0xed0bb0` の絶対値は 0 件。算術経路は未検査。
- 未解決 (#3888 で継続・子は起票せず): 受入 1 の実行時経路 (動的な vtable 構築か別 block の未解析部分) と受入 2 の算術経路。

### PY-264 第 5 run (#3888): 算術経路の走査 (受入 2・部分達成)

- 検査 `analysis/py264_arith_scan.py` (直線区間の定数伝播: lea rip・mov imm・mov reg・add/sub imm。候補 `0xed0bb0`・`0xed0c28` の値を持つレジスタを qword の `mov [..], reg` の源にする箇所を列挙)。測定 commit `ec6b96de2`。素材 `fl-win64`。
- 陽性対照: 候補 `0x13acb88` (既知の vtable 格納 `0x44a86e`・`pe_vptr_stores.py 0` で検出済み) を block00031 に当てると 1 件検出 (PASS)。検出器は格納を見つけられる。
- block00031 (5,022,467 命令): 候補 `0xed0bb0`・`0xed0c28` の算術格納は 0 件・38.0 秒 (HEAD `ec6b96de2` で再現)。
- 全 313 block は未完走。1 プロセス 900 秒・4 並列 480 秒の上限で打ち切り (負荷 3.8〜3.9、4 コア)。全 block の結果は無い。
- 受入 2: block00031 の範囲では算術で作る経路は見つからない。全 block の結論は未達。

### PY-264 第 6 run (#3888): 全 313 block の算術経路走査 (受入 2・部分達成)

- 測定: 素材 `fl-win64` の 313 PE block (1.26GB) を展開 (3.2 秒)。`analysis/py264_arith_scan.py` を block ごとに 1 プロセスで、4 並列・block 単位の timeout 1200 秒で走査。第 5 run の『全 block 未完走』を解消するための分割。
- 測定 commit: `ba4bc73f8` (origin/main での測定)。スクリプトは `ec6b96de2` から変更なし。
- 結果: 313 block 全て rc=0 で完走 (全 block の命令数 240,526,119・候補の算術格納 0 件)。陽性対照 (`block00031` に候補 `0x13acb88`) は再実行で 1 件検出 (`0x44a86e`・rc 0・67.1 秒・n=1)。
- 所要 (実測・本 run の再測定 = `analysis/py264_arith_scan_all.sh`): `real 19m03.8s`・user 74m17s・実行後の load average `3.67 3.92 2.96` (4 コア・並列数 4)。313 block 全て rc=0・命令数合計 240,526,119・hits 0。
- 限界: 直線区間の定数伝播のみ。関数をまたぐ値・メモリ経由の値は追わない。`0xed0bb0` の関数単位の全経路確認は未達。

## PY-4914 (#5348): 関数単位の vptr 候補 0xed0bb0 検査 (受入 2・部分達成)

- 検査: `analysis/py4914_vptr_fn_scan.py` (block00031 の .pdata 57,816 関数。関数先頭ごとに値・スタック slot を追い、call で揮発レジスタを捨てる。RIP 相対の qword 読出しは PE の実バイトを使う)。測定 commit `a42680321`。素材 `fl-win64` (`block00031` のみ展開)。
- 陽性対照: 候補 0x13acb88 は `0x44a86e` で 1 件検出 (PASS)。
- 結果 (実測・HEAD で再現): 0xed0bb0 を生成する命令 0 件・qword 格納 0 件。0xed0c28 を生成するのは `0x11b2af9` (関数 `0x11b2ac0`) の 1 件で、格納は 0 件。所要 100.8 秒 (n=1)・load average 0.94。
- 受入 2 の残り: 関数をまたぐ値 (呼出し先の戻り値・分岐合流・ポインタ経由の書換え) は追っていない。`-0x78` の算術は 519 関数・524 命令あり (大半は `sub rsp, 0x78` のフレーム確保) で、個別には検査していない。
- 前提の疑い: 上の『0xed0c28 は object の番地と読める』(第 4 run) は、本 run でも変わらない。0xed0bb0 を vptr とする経路の有無は、この検査の範囲では 0 件。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 関数をまたぐ値・分岐合流・メモリ経由の値で 0xed0bb0 を作る経路 | 受入 2 の残り | #3888 (親) |

### PY-4914 追補: 即値・RIP 相対・データ領域の静的格納 (#5348)

- 検査: `analysis/py4914_imm_data_scan.py` (block00031・`.text` 5,022,299 命令)。候補 0xed0bb0・0xed0c28 を、相対形と絶対形 (ImageBase 0x400000 + 相対) の両方で、非分岐命令の即値・RIP 相対の番地・`.text` 以外の 4 byte 値に対して照合。
- 陽性対照: 0x13acb88 の RIP 相対 `lea` (0x44a867) を検出 (PASS)。
- 実測 (n=1): FL_WIN64 素材 `fl-win64` の block00031 のみ展開 (2.9 秒)。所要 64.9 秒・load average 0.81。`rc=1` は、下の `.pdata` の 1 件を機械的に数えたため。
- 結果:
  - 非分岐命令の即値・RIP 相対で候補を指す命令: **0 件**。
  - `call 0x12d0bb0` の飛び先 (絶対形 0xed0bb0 と一致): 8 件。これは関数 0x12d0bb0 への直接 call で、vptr の格納ではない。
  - `.pdata` の 4 byte 値 0xed0bb0 (`0x1aa9ef4`): 1 件。`.pdata` エントリ 55615 の begin (関数開始 RVA) で、0x12d0bb0 の unwind 情報。vptr ではない。
  - `.data`・`.rdata`・その他のセクションの 4 byte 値: 0 件 (スクリプトの検査)。8 byte 値 (絶対・相対) は、同じ候補で別の one-off 走査を流して 0 件 (スクリプトには含めていない)。
- 判定: 0xed0bb0 を vptr として格納する静的な経路 (即値・RIP 相対・データ領域) は 0 件。関数をまたぐ値・メモリ経由の動的な経路は未検査 (上の未解決表のまま)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 関数をまたぐ値・分岐合流・メモリ経由の動的な経路で 0xed0bb0 を作る経路 | 受入 2 の残り | #3888 (親) |

## PY-266 (#3890): flag `+0x49e` の書込み元 (部分達成)

- 測定 commit: `251f0e1a5` (`analysis/py266_0x49e_writers.py` の追加 commit)。素材 `fl-win64`・block00031 のみ展開 (1.6 秒)。`.text` 5,022,299 命令・`.pdata` 57,816 関数。
- 検査 (実測・commit `251f0e1a5`): `FL_WIN64_DIR=$PWD/work/py266 python3 analysis/py266_0x49e_writers.py --tsv work/py266/writers.tsv` → rc 0・70.7 秒 (n=1)・user 70.6 秒・load average 0.75→0.98 (並列数 1・4 コア)。
- 結論 1: `[base+0x49e]` へ正確に書く命令は **3 件・2 関数** (capstone の access が WRITE)。ほかの 843 件は読出し。逆アセンブルの全件照合で、`lea` による番地計算は 0 件。
- 結論 2: 3 件のうち、`+0x49e` への正確な書込みで、ヒープ上のオブジェクトへの書込みは **1 件**: 関数 `0x737560` (`mov byte ptr [rbx+0x49e], dl`・`this`=rcx・値=引数 dl)。`0x737560` は値が違うときだけ書く setter。直接 call 元は 3 件 (`0x73d102` in `0x73d0e0`・`0x73d2a2` in `0x73d280`・`0x79fd44` in `0x79fd40`)。
- 結論 3: 残り 2 件 `0x1291829`・`0x1291883` (`0x128f9e0`・`mov byte ptr [rbp+0x49e], 0/1`) は **関数自身の 0x818 バイトのスタックフレーム** への書込み (`sub rsp,0x818`・`rbp=rsp`・`rbp` は入口と出口でしか変わらない)。ヒープの flag ではない。
- 結論 4 (幅広の書込み): 基底 + disp で `+0x49e` を覆う幅広の書込みが **60 件・38 関数** (qword `+0x498`・dword `+0x49c`)。`+0x49e` と厳密に一致はしないが、同じバイトを書く。基底の内訳は `rbp` (スタックフレーム) 47 件・ヒープ候補 (`rax`・`rcx`・`rbx`・`rsi`) 13 件。ヒープ候補の 13 件は、そのオブジェクトの `+0x49e` の値を変える可能性があり、未確定 (下表)。index 形式 (`[base+index+disp]`) の書込みは、解析スクリプト (`base+disp` の一致判定) の対象外。粗い走査では `0x54caf8` `mov dword ptr [rdi+rax*4+0x490], esi` (関数 `0x54ca20`)・`0x73b5cf` `mov byte ptr [rcx+rdx+0x490], 0` (関数 `0x73b580`) の 2 件が見つかった。どちらも `0x49e` を覆うかは index の値域が確定できないため判定していない。
- 結論 5: flag セル `0x15e14a0` への RIP 相対参照 439 件は**全て読出し** (書込み 0 件)。ポインタ `p` は本 block 内では格納されず、外から来る。
- 結論 6 (未解決): 唯一のヒープ書込み `0x737560` の `this` は、直接 call 元 `0x73d0e0`・`0x73d280`・`0x79fd40` の引数で決まる。`0x73d0e0` の直接 call 元は `0x6f2522` (関数 `0x6f24f0`) の 1 件。`0x6f24f0` の直接 call 元は 0 件 (間接呼出し経由と推定)。`0x79fb70` の直接 call 元は `0x7a05cc` (関数 `0x7a05b0`) の 1 件で、`0x7a05b0` の直接 call 元は 0 件。`this` が `[p+0x7e0]` のオブジェクトかは未確定。`+0x7e0` を直接参照する関数は、検査した 2 関数 (`0x6f24f0`・`0x7a05b0`) では 0 件。
- 検査の限界: `+0x49e` の書込みを生の命令列の線形走査で数えた (逆アセンブラで復号できない 161,366 バイトを含む)。生バイトの disp32 `0x49e` の一致 857 件は全て復号済み命令の内側に入る (照合 0 件の不一致)。間接呼出しの先と、実行時に作る番地は見えない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x737560` の `this` (直接 call 元 `0x73d0e0`・`0x73d280`・`0x79fd40`) が `[p+0x7e0]` のオブジェクトか。`0x73d0e0` の直接 call 元は `0x6f2522` (関数 `0x6f24f0`) の 1 件。`0x6f24f0` の直接 call 元は 0 件 (間接呼出し経由と推定) | flag の書込み元の確定 | 親 #3627 の本文にチェックリストとして追記 (本 PR の merge 後) |
| ヒープ候補の幅広の書込み 13 件 (`0x622650`・`0x637cc0`・`0x6385e0`・`0x824290`・`0x8599e0`・`0xe72cd0`・`0xe73010`・`0xe73950`) が、`+0x49e` の flag 値を変えるか | flag の値 (ヒープ上の 0x49e バイトを上書きする可能性) | 親 #3627 の本文にチェックリストとして追記 (本 PR の merge 後) |

- 付録 (全 63 件): `tools/python/REPORT_PY266.md`。
