# PY-223 (#3627): 0xed4b70 (0x12da6d0 の唯一の呼出し元) を間接に呼ぶ候補の所在 (PE 解析・コード変更 0 件)

親: #3595 (PY-217) / 前段: PY-112 (#2932)。既知類型との関係: 該当なし (PE の逆アセンブル読解と検査スクリプト。lift 作業ではない)。

## 結論

- **受入 1 (間接 call 箇所の特定): 部分達成。** 0xed4b70 の所在 (関数ポインタ配列の添字 51) と、それを指せる vtable 候補 2 つ (基点 `0xed0bb0` のスロット `0x198`・基点 `0xed0c28` のスロット `0x120`) は確定した。ただし実際に呼ぶ call 箇所は 1 件に絞れない。候補は `call qword ptr [reg+0x198]` 24 件・`[reg+0x120]` 114 件 (仮想呼出し。receiver の vptr は実行時の値)。vptr を書く箇所が block00031 に無く、どの候補が receiver かは未確定。
- **受入 2 (obj が非 0 になる条件): 未着手** (本 run の時間内に入れず。未解決表へ)。
- **受入 3 (flag の書込み元): 未着手** (`0x15e14a0` を RIP 相対で指す命令は 439 件。書込み元の絞り込みは未実施)。
- **受入 4 (親 #3595 へのコメント): 本 PR の完了時に投稿する。**
- 0xed4b70 の参照は、RIP 相対・`lea` が 0 件 (`pe_rip_refs.py`)、生バイト列 (4 バイト・8 バイト) の一致も表の 1 要素だけ。表の番地は、`.text` 内の 1 件 (`0xed0b60`) からだけ指される。

## 測定

- 測定 commit: `674ac4248` (`tools/python/analysis/py223_indirect_callers.py` を最後に変えた commit)。この後のコード差分は 0 行 (`git diff 674ac4248 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力 0 行。REPORT のみ変更)。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`)。展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C tools/python/work/py223 --wildcards '*block00031_PE.bin'` (1.5 秒)。展開先 `tools/python/work/py223/extracted/` は gitignore。
- 検査 (PASS): `FL_WIN64_DIR=$PWD/work/py223 python3 analysis/py223_indirect_callers.py` → `table.check PASS`・rc 0。所要 47.46 秒 (n=1)、user 47.43 秒、load average (1/5/15 分) は実行前 `0.43 0.55 0.35`・実行後 `0.77 0.63 0.39`、並列数 1。
- ネガティブコントロール: `--mutate` (表の添字 51 の値を 1 ビット反転したメモリ上の複製で検査) → `table.check FAIL`・rc 1。所要 48.05 秒 (n=1)。検査は効いている。
- 独立算法の検算: 命令の逆アセンブルを使わず、`.text` のバイト列を正規表現 `\xff[\x90-\x97]<disp32>` で数えた (`call r/m64` の ModRM mod=10 reg=010 の形)。結果は `[reg+0x120]` 114 件・`[reg+0x198]` 24 件で、逆アセンブル側と一致。
- 表の参照の検算: `pe_rip_refs.py 0xed4b70 0xed0c28 0xed0bb0 0x12da6d0` → `hits 0` (RIP 相対の `lea`/`mov` で指す命令は 0 件)。`pe_callgraph.py callers 0x12da6d0` → 直接 call 元 1 件 (`0xed4c6a` in `0xed4b70`)。

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
```

## 検証範囲 / 範囲外

- 範囲内: `block00031_PE.bin` の `.text` の逆アセンブル・表の所在・RIP 相対と絶対参照・間接 call の集計。
- 範囲外: 他の PE block (素材 `fl-win64` は 313 個の `*_PE.bin` を含む。本 run は block00031 のみ走査)。vptr を書く箇所が他 block にある可能性は未確認。実行時の値 (vptr の中身・flag の値・obj の値)。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1 の残り: `0xed4b70` を呼ぶ receiver の vptr (`0xed0bb0` か `0xed0c28` か) の書込み元。block00031 に vptr 書込みが無い。他の PE block の走査 | 呼出し箇所 (`[reg+0x198]` 24 件・`[reg+0x120]` 114 件) の絞り込み | #3627 (続き・open のまま) |
| 受入 2: `0x12d3ff0` の loop 分岐で `obj = qword [T + G1*192]` が非 0 になる条件 (呼出し時の引数と `[rbp+0x40]` の分岐) | loop 分岐の実装 (親 #3595) | #3627 (続き) |
| 受入 3: flag `byte [[[0x15e14a0]]+0x7e0+0x49e]` の書込み元 (`0x15e14a0` の RIP 相対参照 439 件) | flag の値 | #3627 (続き) |
