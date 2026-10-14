# PY-67 (#2159): PY-66 の残り — 0x196eba0 の書込み元・0xffe370 の所属・0xec60ae/0x8ed012 の対象 (部分・未達)

親: #2078 (PY-66)・前段: `REPORT_PY66.md`・`REPORT_PY58.md`。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 受入条件 1 (`0x196eba0` の書込み元) は**未達**。RIP 相対の store・`lea`・disp32 絶対参照の全てで 0 件。`.data` の slot (VA `0x15e3d38`) 経由の書込みは未確認 (下記「未完」)。
- 受入条件 2 (`0xffe370` の所属・呼出し元) は**未達**。`0xffe370` への直接 call/jmp は 0 件。`0xfe2e98` 表 (`.text` 内、`0xffe370`・`0xffa930` の 2 エントリ) を参照する RIP 相対・絶対参照も 0 件。表自体の参照元が見つからない。
- 受入条件 3 (`0xec60ae` の対象型) は**未達**。`0xec60ae` の対象は `[rbp+0x120]` 上 (`cmp [rax+0x7e0],1` の分岐内)。REPORT_PY58 と同じ判断で、chan 系フィールドは見当たらない。型は未確定。
- 受入条件 4 (`0x8ed012` の `[rbp+0x70]` が chan か) は**未達**。直前に `[rbp+0x70]` へ `+0x18`・`+0x6dc`・`+0x75c`・`+0x10`・`+0x20`・`+0x28` を書く。chan の判定材料は得られず、判断保留のまま。

## 測定条件

- 測定 commit: `3be69c80` (`tools/python/analysis/py67_indirect.py` 追加。解析コードはこの commit で初めて作った)。基点 `6444b186` (origin/main)。
- 素材: `fl-win64` の `block00031_PE.bin` を `tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C tools/python/work/py67 --wildcards '*block00031_PE.bin'` で展開 (22,227,016 バイト)。`work/` は gitignore。
- 実測 (wall):
  - `py55_fieldwrites.py $P 0x794`: 0.114 秒 (`PY-58` の 20 件と一致)
  - `py58_context.py $P 0x1306dbf,0x130760f 0x60 0x40`: 命令境界は REPORT_PY66 と一致
  - `py67_indirect.py $P 0x196eba0`: 59.4 秒 (1 回・5,022,467 命令)
  - `py67_indirect.py $P 0x196eba0,0xffe370,0xffa930,0xec60ae,0x8ed012`: 60.0 秒 (1 回)
  - load average の測定は行っていない。

### 差分 0 の証跡

測定 commit `3be69c80` 以後にコードは変更していない。REPORT 追加のみ。

```
$ git diff 3be69c80 HEAD -- tools/python/analysis tools/python/src
(出力 0 行)
```

## 1. 解析結果

### 0x196eba0 (`.bss`)

- RIP 相対参照 64 件 (`0x1306db8`・`0x1306dc6`・…・`0x1310b06`)。全て load・比較。RIP 相対の store 0 件、`lea` 0 件。
- disp32 絶対参照 0 件。
- ファイル内の絶対値 `0x196eba0` の 8 バイト一致は `.data` の 1 箇所のみ (file offset `0x11e2738`、VA `0x15e3d38`)。ImageBase (`0x400000`) を足していない値のため、再配置済みポインタかどうかは未確定。
- `0x15e3d38` を RIP 相対で load する箇所は 40 件以上 (`0xd5c8f4`・`0xfc6ffb`…)。この slot の store 元は未確認 (下記「未完」)。

### 0xffe370 / 0xffa930 (`0xfe2e98` の表)

- `0xbe2298` (file offset) に `0xffe370`、`0xbe22a0` に `0xffa930` の 8 バイト絶対値。表を指す絶対値・RIP 相対参照は 0 件。
- `0xffe370` の命令: `mov dword [rcx+0x794], edx`・続けて `[rcx+0x9c]`・`[rcx+0x7ac]` への書込み。`rcx` が受ける対象は引数で、所属クラスは不明。
- 直接 call/jmp 0 件。間接呼出し (vtable 経由) の経路は未特定。

### 0xec60ae (`[rbp+0x120]` 上)

- 直前で `[rax+0x79c]` (dword) を書き、直後に `[rax+0x798]`・`[rax+0x7c4]`… を書く。REPORT_PY58 と一致。chan 系フィールド (`+0x714`・`+0x718`・`+0x739`) は範囲内に無い。

### 0x8ed012 ([rbp+0x70] 上)

- 直前の `call 0x511fe0` の戻り値を `[rcx+0x794]` に格納。`[rbp+0x70]` は同関数内で `+0x18`・`+0x6dc`・`+0x75c`・`+0x10`・`+0x20`・`+0x28`・`+0x77c` を書く。`+0x718` (chan 判定に使われるフィールド) の参照は無い。

## 未完

- `.data` slot `0x15e3d38` を load した直後のレジスタ経由 store の追跡は、Python ワンライナーがタイムアウト (300 秒) したため未完。`py67_indirect.py` への追加は未実施。
- `0x196eba0` の `.data` 一致が本当に再配置済みポインタかは未確定 (ImageBase を含まない値)。

## 2. 未確定

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x196eba0` の書込み元 (`.data` slot `0x15e3d38` 経由を含む) | chan 上の `+0x794` 書込みが確定しない | #2159 (PY-67 の続き) |
| `0xfe2e98` 表の参照元と `0xffe370` の所属・呼出し元 | `0xffe370` の書込み対象の型が確定しない | #2159 (PY-67 の続き) |
| `0xec60ae` の `[rbp+0x120]` の型 | chan 以外と確定できない | #2159 (PY-67 の続き) |
| `0x8ed012` の `[rbp+0x70]` が chan か | 判断保留 | #2159 (PY-67 の続き) |

## 3. 次の手順 (提案)

- `.data` slot `0x15e3d38` の load 直後の store を `py67_indirect.py` 内で 1 関数にまとめて追う (ワンライナーは使わない)。
- `0xfe2e98` の表が vtable かどうかを、`.rdata` / `.data` の vtable 候補 (絶対値の連続配置) で確認する。
- `0xec60ae`・`0x8ed012` の対象型は、所属関数の引数の由来 (`rbp+0x120`・`rbp+0x70` の代入元) を遡る。
