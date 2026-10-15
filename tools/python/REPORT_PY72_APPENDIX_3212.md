# PY-72 付録 (#3212 / PY-169): guard の O・判定入力 X の PE 解析

親: `tools/python/REPORT_PY72.md` の「追加解析 (PY-169 / #3212)」節。本文の行数上限 (250 行) のため分割移動 (内容は削除していない)。

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2576 (PY-77)。前段: 本ファイル上の「追加解析 (PY-75 / #2562)」節。親 #2576 の本文が指す「追加解析 (PY-77 / #2576)」節は main に存在しなかった。本節を PY-77 系の PE 結果の記録先とする。

### 結論

- guard の大域 G = `0x15e4790` (.data) のファイル上の値は Q スロット `0x141d6b8` (.data、ファイル上 0) の VA。鎖は `P=[G]=0x141d6b8`・`Q=[P]`・`O=[Q+8]`・`call [O.vtbl+0x98]` (`0xd5a73b`〜`0xd5a74f`)。
- O への非 0 書込みは PE 上 2 箇所 (`0x1263571`・`0x1264145`)。どちらも `mov [rcx+8], rax`、rcx = Q、rax = `call 0x125da90` の戻り値。ctor `0x976b60` の +8 書込みは 0 のみ。
- **未確定**: `0x125da90` の戻り値 (O の実体) と O の vptr。よって vtable `[O+0x98]` の本体と、guard が偽になる条件は PE だけでは確定しない。
- `0xd5e620` の間接先は `.bss` の関数ポインタ `0x16b8300` の値。その値は init `0xc395a0` の `0xc39831` で `call 0x4235f0` の戻り値として格納される。0x4235f0 は実行時の表を引くため、静的には確定しない。
- `0xd84f30` の判定式 (X = rcx の各フィールド) は PE で確定した (§6)。X の実体 `[this+0x50]` の書込み元は未解析。

### 測定

- 測定 commit: `bfceba9e` (`tools/python/analysis/flapi/pe_chain_stores.py` を追加した commit。コードを変えた最後の commit)。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/python/work/fl extracted/block00031_PE.bin` (2.9 秒。`tools/python/work/` は gitignore)。
- 再現コマンド: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_chain_stores.py 0x15e4790 8` (陽性)、同 `0x13a5000 8` (陰性対照。G の値 0 で鎖が切れる)。既存ツール: `pe_xref.py 0x15e4790,0x141d6b8`・`pe_xref.py 0x15e05b8,0x16b8300`・`pe_callgraph.py callers 0x976b60,0x976a90,0x976af0`・`pe_slot_writers.py 0x141d6b8 8` (候補 0 件。直接参照だけでは O の書込みを拾えない)。
- 実測 (`bfceba9e`): 陽性 `intra_store=2 intra_load=277 callee_refs=5 callee_store=0 sec=73.4`。陰性 `intra_store=0 intra_load=0 callee_refs=0 callee_store=0 sec=72.5`。load average (1 分値) 0.21 → 0.78。陽性の読出し例: `0xd5a745 load mov rax, qword ptr [rax + 8]` (guard の O 読出し)。
- 差分の証跡: `git diff bfceba9e HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は測定後のコミットが本ファイルだけなので 0 行 (後続の commit は本ファイルのみ)。

### 1. Q スロットと Q 本体

- `0x141d6b8` の直接参照 (RIP 相対) は 6 件: load `0x976a95` (cmp)・store `0x976aad` (`[Q]←rax`、init `0x976a90` の ctor 戻り値)・load `0x976acf`・`0x976af5`・`0x976b09`・store `0x976b10` (`[Q]←0`、shutdown `0x976af0`)。
- init `0x976a90`: `if [Q]==0 { [Q] = ctor 0x976b60(rcx=[0x976410], dl=1) }`、続けて `[Q+0x40]` の vtbl[0] を呼ぶ。init の呼出元は 6 件 (`0x977114`・`0x11b32de`・`0x1253c39`・`0x1263554`・`0x1264112`・`0x1374364`)。
- ctor `0x976b60` (this = Q 本体) の呼出元は `0x976aa8` の 1 箇所。ctor の範囲 (`0x976b60`〜`0x976d86`) で `+8` への書込みは `0x976b9c` の `mov [rax+8], 0` の 1 件だけ。

### 2. O (`[Q+8]`) の非 0 書込み

| VA | 関数 | 書込み | 文脈 |
|---|---|---|---|
| `0x1263571` | `0x1263540` | `mov [rcx+8], rax` | `0x126354b` の `cmp [0x459e22],-1` が成立したときだけ実行 (O の既存値は見ない)。`0x1263554` init → `0x1263562` `call 0x125da90` → `0x126356e` で rcx = `[[G]]` = Q |
| `0x1264145` | `0x1264050` | `mov [rcx+8], rax` | `0x1264126` `cmp [Q+8],0; jne 0x1264149`。O が 0 のときだけ `0x126412d` `call 0x125da90` → `0x1264142` で rcx = Q |

- 両方とも `0x125da90` を `rcx = [0x125b0f8]`・`dl=1` で呼ぶ (`0x1263559`・`0x126412d` の `mov rcx,[rip+…]` の先が同じ `0x125b0f8`)。
- 陽性の chain 追跡では、Q 本体を rcx に載せて直接 call した 5 件の先頭 40 命令にも +8 書込みは無い (`callee_store=0`)。
- 範囲外: 間接 call・レジスタ以外 (メモリ経由) で Q を受け渡す経路・vtable 経由の dispatch。

### 3. O の生成関数 `0x125da90` (未確定)

- 戻り値は `this` (`0x125e75d` の `mov rax,[rbp+0x4220]`)。逆アセ 4000 命令 (`0x125da90` から) に、任意のベースと任意のソースによる 8 バイト `mov [reg], reg` 形式の書込みは 0 件。`lea rax,[rip+…]` は 2 件 (`0x125fd5a`・`0x1261263`) だが、いずれも関数末尾 `0x125e76e` より後の別の関数内。
- `this` 引数の値 `[0x125b0f8]` = `0x125b1c0` は .text 内の関数ポインタ 8 個 (`0x1262140`・`0x12620b0`・`0x125e9a0`・…) を並べた表で、O 本体ではなく vtable 様。`0x410320` は `call [this-0x30]` を行う。
- 推定: `0x125b0f8` の内容と `this` の意味が一致していない (`mov` と `lea` の取り違えか、別の意味の引数)。どちらかは PE だけでは確定できない。O の実体は実行時にしか決まらない。

### 4. guard の vtable と偽になる条件 (未確定)

- vtable `[O+0x98]` は O の vptr が未確定のため読めない。status −2 のまま終わる条件 (guard が偽) の PE 上の本体は未確定。

### 5. `0xd5e620` の間接先と `this`

- `0xd5e620(self)`: `mov rax,[0x15e05b8]` (`0xd5e624`)・`call [rax]` (`0xd5e62b`)。rcx (self) は素通し。`[0x15e05b8]` のファイル値は `0x16b8300` (.bss)。間接先は `*(0x16b8300)`。
- `0x16b8300` への RIP 相対 store は `0xc39831` の 1 件 (`mov [rip+0xa7eac8], rax`)。rax は直前 `0xc3982c` の `call 0x4235f0` (rcx = `[rip+0xa7edbd]` (`0xc39804`)、rdx = `lea 0xc8c` = `0xc404b8`)。init は `0xc395a0` (`pe_callgraph func`)。
- `0x4235f0` は `rdx>>16` で分岐する表引き (`0x423608`〜`0x423614`)。戻り値は表の内容 (実行時の値) に依存。間接先の確定は実行時に限る (推定)。
- `this` は呼出元 `0xd5aa30` の `0xd5e620(self)` 戻り値 `rax` の指す値 (`mov rbx,[rax]`)。

### 6. `0xd84f30` の判定式 (入力 X = rcx、PE 確定)

- X = `[this+0x50]`: `0xd843f0` `mov rax,[rbx+0x50]`・`0xd843fc` `call 0xd84f30` (rcx = X)。
- 戻り値 = A ∨ B。A = `[X+0x2d8]==0 ∧ [X+0x3b8]==0 ∧ [X+0x2da]!=0 ∧ [X+0x2d9]!=0`。B = `[X+0x410]!=0`。(`0xd84f37`〜`0xd84f5b`。A の分岐は `0xd84f4b`・`0xd84f52`)。
- X の実体 (`[this+0x50]` の書込み元) は未解析。`this` が実行時にしか決まらないため、X の値も実行時に限る (推定)。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| O の生成関数 `0x125da90` の this の実体と O の vptr (§3) | vtable `[O+0x98]` の本体と偽になる条件が確定しない。status −2 の PE 条件が出ない | #3212 (open のまま継続) |
| `0x4235f0` の表引き結果 (`0xc39831`・§5) | `0xd5e620` の間接先が確定しない | #3212 |
| X = `[this+0x50]` の書込み元 (§6) | `0xd84f30` の入力の実体が確定しない | #3212 |
