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

## 4. PY-71 (#2501): g の値 P の型・0xffe370 の所属 (追加解析)

§1 の「未完」の `.data` slot `0x15e3d38` は本節 4.1 で解決した (値は `&g`)。

| # | 受入条件 (#2501) | 結果 |
|---|---|---|
| 1 | `0x86a4cf` の `call [A-0x30]` の戻り値型と g の値 P の型 | **達成**。P は vptr `0x13063c8`・サイズ `0x840` のクラス (クラス名は stripped で無い) |
| 2 | `0xffe370` の所属クラスと呼出し元 | 所属は**達成** (vptr `0xfe2cf8`・サイズ `0x8a8` のクラス、仮想スロット 52)。呼出し元は**未達** |
| 3 | `0xec60ae` の対象型 (chan 以外なら除外) | **未達** (`[rbp+0x120]` の出所を追えず) |
| 4 | `0x8ed012` の `[rbp+0x70]` が chan か | **未達** (判定材料を得られず) |

- 測定 commit: `d7919454` (`analysis/py67_callers.py`・`py67_slot.py`・`py67_vtable.py` を追加)。基点 `47bbd8d3` (origin/main)。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` を `$RUNNER_TEMP/fl-win64` に展開 (22,227,016 バイト)。`tools/**/work/` は使わない。
- 実測 (コミット済み `d7919454`・wall は `/usr/bin/time`・n=1):
  - `py67_callers.py $P 0x86a470,0x11c8950 8`: 120.8 秒 (直接 call 25 件)
  - `py67_slot.py $P 0x1306300,0x13a5c90,0x15e3d38 16 16`: 112.3 秒
  - `py67_callers.py $P 0xfe2c80+8k (k=0..68) 0`: 86.9 秒 (RIP・即値の参照 0 件)
  - `py67_vtable.py` (vptr `0xfe2cf8`・`0x13063c8`): 各 0.2 秒
  - load average (1 分): 計測開始前 0.13、最初の sweep 直後 2.02 (sweep は 1 プロセス)
- 正の対照: `0x11c8950` の直接 call 23 件 (前回の逆アセと一致)、`0x11be450` の `0x15e3d38` 読込みが `0x11c8950` の第 2 引数に入る (`py67_slot.py` の出力)。
- ネガティブコントロール: スクリプトとしては未実施。`0xffe370` が vptr `0x13063c8` のスロットに無いことは静的に確認 (110 スロット・`[]`)。`0xfe2c80+8k` の RIP・即値参照 0 件は実測。

### 差分 0 の証跡

```
$ git diff d7919454 HEAD -- tools/python/analysis tools/python/src
(出力 0 行)
```

### 4.1 g ← P の経路 (静的)

1. 書込み: `0x86a4e1` の `mov [rax], rcx` (P を `*r8` へ)。`r8 = &g`。関数 `0x86a470` は `this=rcx`・`A=rdx`・`out=r8`。
2. 直接 call は 2 件。`0x10dc775` は `out=&[rbp+0x68]` (ローカル。g ではない)。もう 1 件は thunk `0x11c8950` (`0x11c896d`) で、`this=*(0x15e50f8)`・`A=rcx`・`out=rdx` に並べ替える。
3. thunk `0x11c8950` の呼出しは 23 件。g へ書くのは fn `0x11be0a0` (11 件の内) の `0x11be457`。その直前で `rcx=*(0x1306300)=A`、`rdx=*(0x15e3d38)=&g` (`0x11be450`)。
4. `A = *(0x1306300) = 0x13063c8` (`.text` の静的値)。`0x1306300` への RIP 相対の書込みは 0 件。
5. `call [A-0x30]`: `[0x1306398] = 0x40f960` (F)。F は `size = dword[this-0x80] = 0x840` を読み、`0x409410(size)` で確保、`0x40fb40(this, X)` で `*X = this` (vptr = A) を書いて `X` を返す。よって P = X (新規 `0x840` バイトのオブジェクト)。
6. `0x409410` の確保は `call [0x13a5c90]` の間接呼出しで、`0x13a5c90` は `.data` の静的値 `0x407a50` (`lock cmpxchg` を含むアロケータ)。

### 4.2 P の型 (vptr `0x13063c8`)

- `[A]=0x619200` で、vtable は 110 スロット (`py67_vtable.py` の実測)。`0x86a4f6` の `call [P+0x78]` は vtable スロット 15 (`0x80c850`)。
- `0x1306dbf` (`mov [rcx+0x794], rax`・`rcx=g`) と `0x130760f` (`mov [rax+0x794], r14`・`rax=g`) はどちらも P の `+0x794` へ書く。`0x794 < 0x840` で、対象型は vptr A のクラス。
- クラス名は無い (stripped)。chan かどうかは 4.4 の近似でも確定しない。

### 4.3 0xffe370 の所属 (vptr `0xfe2cf8`)

- `V = 0xfe2cf8`: `[V-0x80] = 0x8a8` (サイズ)、`[V-0x30] = 0x40f960` (A と同じ factory F)。`0xfe2c78..0xfe2cf0` (V-0x80..V-0x8) は V の 16 語のメタデータ (A の `A-0x80..A-0x8` と同じ形)。
- 仮想表 `0xfe2cf8..0xfe2ea0` は 54 スロット。`0xffe370` = スロット 52 (`+0x1a0`)、`0xffa930` = スロット 53。`0xffe370` は `[rcx+0x794]`・`[rcx+0x9c]` を書き、`[rcx+0x7ac]` を読む (V のメソッドとして整合)。
- 表を指す参照は、RIP 相対・即値の参照 0 件 (`0xfe2c80+8k` の 69 個全て)。絶対 8 バイト値 `0xfe2cf8` は 2 件 (`.text` の `0xfe2c30`・`0xfe2ed8` に格納)。
- 未解決: 呼出し元 (V のインスタンスの `call [reg+0x1a0]`) と、V の vptr を書く箇所。`0xfe2c30`・`0xfe2ed8` の格納元も未追跡。

### 4.4 chan 判定の材料 (近似。vtable 単位・ベース不問の disp 一致)

| クラス (vptr) | サイズ | `+0x714` | `+0x718` | `+0x739` | `+0x794` |
|---|---|---|---|---|---|
| P: A `0x13063c8` | `0x840` | 1/110 | 1/110 | 0/110 | 0/110 |
| V `0xfe2cf8` | `0x8a8` | 0/54 | 0/54 | 0/54 | 12/54 |

(数値はスロット数。`py67_vtable.py`。chan の判定根拠 (`+0x714`・`+0x718`・`+0x739`) は両クラスとも弱く、chan とは確定できない。)

### 4.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xec60ae` の `[rbp+0x120]` の出所 (`push rbp` を 0x3000 バイト内に見つけられず) | 受入条件 3 | #2501 (Refs で残す) |
| `0x8ed012` の `[rbp+0x70]` の出所 (関数先頭は未特定。直前の `push rbp` `0x8ea780` は `sub rsp,0x28` の別関数で、`[rbp+0x70]` の代入元ではない) | 受入条件 4 | #2501 |
| V (`0xfe2cf8`) のインスタンス生成箇所と、`call [reg+0x1a0]` の呼出し元 | 受入条件 2 (呼出し元) | #2501 |
| A (`0x13063c8`) のクラス名と chan 判定 | 4.4 の判定根拠 | #2501 |
