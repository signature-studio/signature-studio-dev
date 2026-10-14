# PY-67 (#2159): PY-66 の残り — 0x196eba0 の書込み元・0xffe370 の所属・0xec60ae/0x8ed012 の対象 (部分・未達)

親: #2078 (PY-66)・前段: `REPORT_PY66.md`・`REPORT_PY58.md`。既知類型との関係: 該当なし (lift 作業ではない)。

> 2 回目 (2026-10-14 run) の結果は **§4**。受入条件 1 は書込み元 (PE 解析箇所) まで特定し、書込み先の型は未確定。受入条件 2〜4 は 1 回目と同じく未達。

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

## 4. 2 回目: slot `0x15e3d38` 経由の書込み元 (受入条件 1・部分達成)

### 結論

- `0x196eba0` (g) は `.bss` の 8 バイト変数で、値 P (= `*g`) が `0x1306dbf`・`0x130760f` の `[P+0x794]` 書込みの基底。1 回目の「`0x196eba0` が指すオブジェクト」の読みは正しい。
- g 自体への書込みは次の 1 経路だけ。
  - `0x86a4e1: mov qword ptr [rax], rcx` (関数 `0x86a470`)。`rax` = `[rbp+0x80]` = 第 3 引数 r8 = `&g`。`rcx` = `[rbp+0x48]` = `0x86a4cf` の `call qword ptr [rax-0x30]` の戻り値。
  - 同関数の `0x86a504: mov qword ptr [rax], 0` は g = 0 を書く。
- 呼出し経路: `0x11be450: mov rdx,[rip+0x4258e1]` (= slot の中身 `&g` を読む) → `0x11be457: call 0x11c8950` → `0x11c896d: call 0x86a470`。`0x11c8950` は引数を並べ替えて (r8 = rdx = &g) 渡すだけの転送関数。
- 未確定 (受入条件 1 の後半): P の型。`0x86a4cf` の間接呼出し先 `*(A-0x30)` の戻り値型が決まらない。A は `0x11be449: mov rcx,[rip+0x147eb0]` = `*(0x1306300)` で、その由来は未追跡。

### 根拠 (実測)

- `&g` の静的な出所は slot `0x15e3d38` だけ。`0x196eba0` の 8 バイト絶対値の一致は 1 件 (file offset `0x11e2738` = slot 自身)。即値 0 件、`lea` 0 件。
- slot の RIP 相対 load (`mov reg,[rip+slot]`) は 75 件。全件 load。
- 追跡 (`py67_slot.py`・window 400・call/ret で打ち切り):
  - `&g` (depth 1) からの mov store: 0 件。
  - `*g` (depth 2) からの mov store: 1 件 (`0x1037608: mov byte ptr [rcx+0x79c], al`)。
  - `&g` を引数 (rcx/rdx/r8/r9) に渡す direct call: 1 件 (`0x11be457`・rdx)。
- `py67_callers.py` の結果: `0x86a470` の direct 呼出し元は 2 件 (`0x11c8950` 経由の `0x11c896d`、`0x10dc775`。後者は r8 = ローカル `[rbp+0x68]` で g ではない)。`0x11c8950` の direct 呼出し元は 23 件で、`&g` を渡すのは `0x11be457` だけ。

### 関数 `0x86a470` (g への書込み関数) の要点

- 第 1 引数 rcx (= X) の `+0x179` へ `al` を書く (`0x86a4b8`)。
- 第 2 引数 rdx (= A) を `[rbp+0x78]` に保存し、`0x86a4cf` で `call [A-0x30]` を呼ぶ。戻り値を `0x86a4e1` で `[&g]` に書く。
- 型の手がかり: 書いた直後 (`0x86a4ef`〜`0x86a4f6`) で P (= `[rbp+0x48]`) の vtable を読み、`call [vtable+0x78]` (第 2 引数 dl = 0xff、第 3 引数 r8 = X) を呼ぶ。P は仮想関数を持つオブジェクトで、この vtable スロットの実装を読むと P の型を絞れる (次の手順)。

### 他の P 書込み (参考・深さ 2)

- `P` を引数で受けて書く呼出し先: `0x1307ae0` (`mov dword ptr [rcx+0x788], edx`・`0x12d492f` ほか 2 件から呼出し)、`0x13105d0` (`mov dword ptr [rcx+0x7a8], eax`・`0x1037593` ほか 2 件)。P 上の同一フィールドかは未確認。

### 限界

- 追跡はレジスタの複写と `mov r,[r]` (深さ 2 まで) だけ。`call` で caller-saved レジスタを破棄するため、呼出しをまたぐ store は見ない。間接呼出し (`call [reg]`) の先は追わない。
- 線形走査。store 箇所 `0x86a4e1`・`0x86a504` は `py58_context.py` で命令境界を確認済み (`<==` 付きで出力)。
- 1 回目の追跡器 (本節の前段の版) は、レジスタの上書きで追跡を止めず、store 374 件の出力を出した。誤りだったため採用しない。

### 測定

- 測定 commit: `6cc14f57` (`py67_callers.py` 追加。解析コードの最後の変更)。`py67_slot.py` は `06c29d90` で追加。
- 差分 (測定 commit から本 REPORT の親 commit まで・コード範囲 `tools/python/analysis`・`tools/python/src`): 0 行 (commit 直前に `git diff 6cc14f57 HEAD -- tools/python/analysis tools/python/src` を実行)。
- 実測 (wall・1 回・逐次・他プロセス並列なし): `py67_slot.py work/py67/extracted/block00031_PE.bin 0x15e3d38 0x196eba0 400`: 53.56 秒。`py67_callers.py ... 0x11c8950,0x86a470`: 26.77 秒。load 平均は未計測。
- 再現: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py67 --wildcards '*block00031_PE.bin'` → `cd tools/python` → 上記 2 コマンド。

### 未確定 (2 回目)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| P (= `*g`) の型: `0x86a4cf` の `call [A-0x30]` の戻り値型と、A = `*(0x1306300)` の由来 | `0x1306dbf`・`0x130760f` の `+0x794` の対象型が確定しない (受入条件 1 後半) | 子 issue #2501 (`[PY-71]`) |
| 受入条件 2〜4 (`0xffe370` の所属・`0xec60ae` の型・`0x8ed012` の chan 判定) | 未達のまま | 子 issue #2501 (`[PY-71]`) |
