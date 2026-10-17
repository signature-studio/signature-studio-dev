# PY-72 付録 (#3212 / PY-169): guard の O・判定入力 X の PE 解析

親: `tools/python/REPORT_PY72.md` の「追加解析 (PY-169 / #3212)」節。本文の行数上限 (250 行) のため分割移動 (内容は削除していない)。

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2576 (PY-77)。前段: `REPORT_PY72.md` の「追加解析 (PY-75 / #2562)」節・「追加解析 (PY-77 / #2576)」節。

### 結論 (最新・第 2 段。詳細は §7)

- 受入 1: O (`[Q+8]`) は `0x125da90` の戻り値。`0x40fb40` が割り当てたヒープ上のオブジェクトで、vptr は PE 上の固定値 `0x125b1c0` (`0x40fb66` の書込み)。O への非 0 書込みは従来どおり 2 箇所 (`0x1263571`・`0x1264145`)。受入 1 は部分達成 (別名経由の書込みの網羅は未了。§7.4)。
- 受入 2: vtable `[O+0x98]` の本体は `0x1262b80`。戻り値が偽 (status −2 のまま) になるのは、フラグ A・B・C のいずれかが非 0、または D > 0 のとき (§7.2)。A〜D の値は .bss/.data の実行時状態。
- 受入 3: 間接先 `*(0x16b8300)` は `GetProcAddress(hmod, "PyModule_GetState")` の戻り値。`[0x1971600]` = kernel32!GetProcAddress (import directory)、名前は PE 上で確定。hmod (`[0x16b85c8]`) は実行時の DLL 読込みの結果なので、間接先の実体は実行時にしか決まらない。X = `[this+0x50]` の this も同じ経路の戻り値 (§7.3)。

### 結論 (前段 PR #3290 時点。履歴として残す)

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
- main 取り込み前の測定。以降にコード差分があるため参考値。正本は下の a7d1255b の節。

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
- 陽性の chain 追跡では、Q 本体を rcx に載せて直接 call した 5 件の先頭 640 バイト (`CALLEE_WINDOW`×16) にも +8 書込みは無い (`callee_store=0`)。
- 範囲外: 間接 call・レジスタ以外 (メモリ経由) で Q を受け渡す経路・vtable 経由の dispatch。

### 3. O の生成関数 `0x125da90` (前段の記録。第 2 段で確定: §7.1)

- 戻り値は `this` ではない。`0x125e75d` が返すのは `[rbp+0x4220]`。`dl≠0` の経路 (呼出元 2 件はいずれも `mov dl,1`) では `0x125db18` で `0x125db13` の `call 0x410320` の戻り値を格納し、`0x125daee` の `this` の格納を上書きする。`0x125e70b` の `call 0x410360` は引数をそのまま返す (`0x410380`〜`0x4103a2`) ので、値は変わらない。
- `0x410320` は `dl` の符号ビットが 0 のとき (`0x410327`〜`0x41032e`) `call qword ptr [this-0x30]` を呼び、その戻り値をそのまま返す。ファイル上の `[0x125b0f8]` = `0x125b1c0` を this とみなすと、`[this-0x30]` = VA `0x125b190` の値は `0x40f960` (ファイル上)。よって O の実体は `0x40f960` の戻り値で、その本体は未解析。
- 逆アセ 4000 命令 (`0x125da90` から) に、任意のベースと任意のソースによる 8 バイト `mov [reg], reg` 形式の書込みは 0 件。`lea rax,[rip+…]` は 2 件 (`0x125fd5a`・`0x1261263`) だが、いずれも関数末尾 `0x125e76e` より後の別の関数内。
- `this` 引数の値 `[0x125b0f8]` = `0x125b1c0` は .text 内の関数ポインタ 8 個 (`0x1262140`・`0x12620b0`・`0x125e9a0`・…) を並べた表で、O 本体ではなく vtable 様。
- 推定: `0x125b0f8` の内容と `this` の意味が一致していない (`mov` と `lea` の取り違えか、別の意味の引数)。どちらかは PE だけでは確定できない。O の実体は実行時にしか決まらない。

### 4. guard の vtable と偽になる条件 (前段の記録。第 2 段で確定: §7.2)

- vtable `[O+0x98]` は O の vptr が未確定のため読めない。status −2 のまま終わる条件 (guard が偽) の PE 上の本体は未確定。

### 5. `0xd5e620` の間接先と `this`

- `0xd5e620(self)`: `mov rax,[0x15e05b8]` (`0xd5e624`)・`call [rax]` (`0xd5e62b`)。rcx (self) は素通し。`[0x15e05b8]` のファイル値は `0x16b8300` (.bss)。間接先は `*(0x16b8300)`。
- `0x16b8300` への RIP 相対 store は `0xc39831` の 1 件 (`mov [rip+0xa7eac8], rax`)。rax は直前 `0xc3982c` の `call 0x4235f0` (rcx = `[0x16b85c8]` (`0xc3981e`)、rdx = `0xc3a4b8`)。init は `0xc395a0` (`pe_callgraph func`)。(第 2 段で訂正: 前段の `0xc404b8` は算術の誤り。§7.3)
- `0x4235f0` は `rdx>>16` で分岐する (`0x423608`〜`0x423614`)。非 0 なら名前引数で `GetProcAddress` を呼ぶ (§7.3)。戻り値は実行時の hmod に依存。
- `this` は呼出元 `0xd5aa30` の `0xd5e620(self)` 戻り値 `rax` の指す値 (`mov rbx,[rax]`)。

### 6. `0xd84f30` の判定式 (入力 X = rcx、PE 確定)

- X = `[this+0x50]`: `0xd843f0` `mov rax,[rbx+0x50]`・`0xd843fc` `call 0xd84f30` (rcx = X)。
- 戻り値 = A ∨ B。A = `[X+0x2d8]==0 ∧ [X+0x3b8]==0 ∧ [X+0x2da]!=0 ∧ [X+0x2d9]!=0`。B = `[X+0x410]!=0`。(`0xd84f37`〜`0xd84f5b`。A の分岐は `0xd84f4b`・`0xd84f52`)。
- X の実体 (`[this+0x50]` の書込み元) は未解析。`this` が実行時にしか決まらないため、X の値も実行時に限る (推定)。

### 未解決 (前段の表。第 2 段で 3 行とも解決・再分類。現行の未解決は §7.4)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| O の実体 (`0x125da90` の戻り値 = `[this-0x30]` の関数。ファイル上 VA `0x125b190` → `0x40f960`) の本体と、O の vptr (§3) | vtable `[O+0x98]` の本体と偽になる条件が確定しない。status −2 の PE 条件が出ない | #3212 (open のまま継続) |
| `0x4235f0` の表引き結果 (`0xc39831`・§5) | `0xd5e620` の間接先が確定しない | #3212 |
| X = `[this+0x50]` の書込み元 (§6) | `0xd84f30` の入力の実体が確定しない | #3212 |

### 測定 (main 取り込み後の再測定)

- 測定 commit: `a7d1255b` (`origin/main` (`1c8ca077`) を取り込んだ merge commit。コードを変えた最後の commit)。main 側で `tools/python/analysis`・`provider`・`host`・`tests` にコード変更が入ったため、`bfceba9e` の測定は HEAD の値として使わず再測定した。
- 差分の証跡: 測定に使ったのは `pe_chain_stores.py` だけで、その import は capstone・pefile のみ。この差分は docstring の 2 行の書換えと空行 1 行の追加だけ (定数値・処理は不変。実行結果に影響しないため再測定はしない)。出力は下の diff。
- `git diff --stat a7d1255b HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力 (main 取り込み (merge) による差分。測定の入力ではない)。

```
 tools/python/analysis/flapi/pe_bb_state_probe.py | 129 +++++++++++++++++++++++
 tools/python/analysis/flapi/pe_chain_stores.py   |   5 +-
 tools/python/analysis/flapi/pe_pattern_probe.py  |  82 ++++++++++++++
 tools/python/analysis/flapi/pe_scan_store.py     |  12 ++-
 tools/python/host/fl_mock.mjs                    |  40 +++++++
 tools/python/host/fl_provider.mjs                |   1 +
 tools/python/provider/build.sh                   |   2 +-
 tools/python/provider/fl_engine.c                |  60 ++++++++++-
 tools/python/tests/provider_check.mjs            |   9 +-
 tools/python/tests/step_item_diff.mjs            |  36 +++++++
 tools/python/tests/ui_state_diff.mjs             |  14 +--
 11 files changed, 373 insertions(+), 17 deletions(-)
```

`pe_chain_stores.py` の diff (`git diff a7d1255b HEAD -- tools/python/analysis/flapi/pe_chain_stores.py`):

```diff
diff --git a/tools/python/analysis/flapi/pe_chain_stores.py b/tools/python/analysis/flapi/pe_chain_stores.py
index 74501ec3..d2a57b72 100644
--- a/tools/python/analysis/flapi/pe_chain_stores.py
+++ b/tools/python/analysis/flapi/pe_chain_stores.py
@@ -8,8 +8,8 @@
 - タグ: `QS` = Q スロットの VA (`mov r,[G]` の直後)、`QO` = Q の値 (`mov r,[QS]` または `mov r,[QS-ptr]`)、
   `QO+d` = Q 本体 + d の VA (`lea`)、`O` = `[Q+disp]` の値。
 - 出力: (a) 同一関数内で `[QO+disp] ← X` の書込み (X が imm 0 か否か)、(b) `[QO+disp]` の読出し、
-  (c) rcx に QO を載せて直接 call した先で `mov [rcx+disp], X` を行う箇所 (先頭 40 命令・rcx が
-  書き換わるまで)。(c) の範囲は直接 E8 の call 先のみ。
+  (c) rcx に QO を載せて直接 call した先で `mov [rcx+disp], X` を行う箇所 (先頭 CALLEE_WINDOW×16 =
+  640 バイト・rcx が書き換わるまで・ret/jmp/call で止まる)。(c) の範囲は直接 E8 の call 先のみ。
 - 走査は線形。ret・jmp で全タグを消し、call で caller-saved (rax,rcx,rdx,r8-r11) を消す。
   分岐の合流は考慮しない (タグは保守的に残るため、候補は手で逆アセして確定する)。
 
@@ -53,6 +53,7 @@ def canon(name):
 def rip_target(ins, op):
     return ins.address + ins.size + op.mem.disp
 
+
 def step(ins, tags, rows, callee_refs, g_va, q_slot, disp_want):
     ops = ins.operands
     mn = ins.mnemonic
```
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst extracted/block00031_PE.bin` (2.9 秒・22,227,016 B。展開先は `$RUNNER_TEMP/fl3290`)。
- 陽性 `FL_WIN64_DIR=$RUNNER_TEMP/fl3290 python3 analysis/flapi/pe_chain_stores.py 0x15e4790 8`: `instructions=5022467 intra_store=2 intra_load=277 callee_refs=5 callee_store=0 sec=73.1` (real 1 分 13.2 秒)。
- 陰性対照 `... 0x13a5000 8` (G の値 0 で鎖が切れる): `instructions=5022467 intra_store=0 intra_load=0 callee_refs=0 callee_store=0 sec=72.5` (real 1 分 12.6 秒)。
- load average (1 分値): 陽性の開始 0.08 → 終了 0.74、陰性の開始 0.68 → 終了 0.90。

### 7. 第 2 段 (#3212 の再 run): O の実体・vtable 本体・偽になる条件

前段 (§1〜§6) の未確定点を、同じ PE ファイル (`extracted/block00031_PE.bin`) の静的な読みで埋めた。ここでの「PE 上の値」はファイル上の初期値で、実行時の値ではない。道具は `analysis/flapi/pe_va_read.py` (VA の所属セクション・ファイル上の値・C 文字列を出す。本 run で追加)。

#### 7.1 O の生成 (受入 1)

| 段 | VA | 内容 |
|---|---|---|
| 呼出 | `0x1263559`・`0x126412d` | `rcx = [0x125b0f8]` = `0x125b1c0` (this) を読む |
| 呼出 | `0x1263560`・`0x1264134` → `0x1263562`・`0x1264136` | `dl = 1` で `call 0x125da90` |
| 本体 | `0x125db0b`〜`0x125db18` | `dl ≠ 0` のため `call 0x410320(this)`。戻り値を `[rbp+0x4220]` へ格納 |
| 分岐 | `0x410327`〜`0x41032e` | `dl` の符号が 0 (dl = 1) のとき `call [rax-0x30]`。`[0x125b190]` = `0x40f960` |
| 割当 | `0x40f960` → `0x40941e` | `movsxd rcx, [this-0x80]` = dword `[0x125b140]` = `0x78` (120)。`call 0x409410(120)` → `call [0x13a5c90]`。`0x13a5c90` の PE 上の値は `0x407a50`。`0x13a5c90` へのストアは PE 上 0 件 (`pe_xref.py`) |
| 割当 | `0x407a50` | サイズ分岐 (`cmp rcx, 0xa28`) と `lock cmpxchg` を含む割当関数。戻り値が新しい O |
| 初期化 | `0x40fb40` | `call 0x40d210(O, 120, 0)` の後、`0x40fb66`: `mov [O], this`。O.vptr = `0x125b1c0`。`mov rax, rsi` で O を返す (`0x40fbf3`) |
| 戻り | `0x125db2a` | `call 0x40f9e0(O, dl = 0)` は `0x40fa0d` で即 return (副作用なし)。`[rbp+0x4220]` (= O) を返す |

vptr の書込み後に PE 上で到達する書込みの確認: `0x40fb40` は `[node-0x78]` で連結リストを回る (this → `0x975a80` → `0x401a38`)。各 node の表 `[node-0xc0]` は PE 上すべて 0 で、表駆動の `[O+off] ← val` は 0 件。tag `[node-0xb0]` は this と `0x401a38` で 0、`0x975a80` で `0x975b60` (値 0x0e。0x16 でない) のため、`0x40fac0`・`0x417150` は呼ばれない。この確認範囲に限り、O.vptr は `0x125b1c0` のまま。

受入 1 の「非 0 を書く箇所」: 前段 §2 のとおり `0x1263571`・`0x1264145` (`mov [rcx+8], rax`。rcx = Q、rax = `0x125da90` の戻り値 = O)。ctor `0x976b60` の +8 書込みは 0 のみ (前段 §1)。探索範囲は前段 §2 の制限 (2 段の二重間接・rcx 渡しの直接 call 5 件の先頭 640 バイト)。

#### 7.2 vtable `[O+0x98]` の本体と偽になる条件 (受入 2)

- guard の呼出し `0xd5a73b`〜`0xd5a74f`: `rcx = O`、`call [[O]+0x98]`。`[O]` = `0x125b1c0` (7.1) なので slot `[0x125b258]` = `0x1262b80` (PE 上の値)。
- 本体 `0x1262b80` は al を返す。al = 1 (真) になるのは A・B・C がすべて 0 かつ D ≤ 0 のとき。いずれかが偽になると al = 0。

| 条件 | 偽になる条件 | PE 箇所 | 参照先 (PE 上の値) |
|---|---|---|---|
| A | byte `[*0x15e04a8]` ≠ 0 | `0x1262b85`〜`0x1262b8f` | `0x15e04a8` の値 `0x16baff0` (.bss) |
| B | byte `[*0x15e0ff0]` ≠ 0 | `0x1262b91`〜`0x1262b9b` | `0x15e0ff0` の値 `0x16baff1` (.bss) |
| C | `call [O+0x48]` の戻り値 ≠ 0 | `0x1262ba6`〜`0x1262ba9` | slot `[0x125b208]` = `0x1262950`。その本体 (`0x1262950`) は byte `[*0x15e1890]` を返す。`0x15e1890` の値 `0x13e7628` (.data、PE 上 0x00) |
| D | dword `[[*0x15e30f8] + 0x168]` > 0 (符号付き) | `0x1262bad`〜`0x1262bbe` | `0x15e30f8` の値 `0x15f7190` (.bss)。その先 `[0x15f7190]` (.bss) の +0x168 |

- C を立てる箇所: vtable `[O+0x60]` = `0x1262970` (`mov byte [rax], 1` at `0x1262977`)。`pe_slot_writers.py 0x15e1890 0` の候補 (逆アセ未確認): `0xa8dea1`・`0x11c761c` (byte ← 1)、`0x11cfce9` (word ← 0)。
- A・B・D の書込み元: `pe_slot_writers.py` の候補は多数 (`0x15e04a8` 19 件、`0x15e0ff0` 22 件、`0x15e30f8` 29 件。いずれも逆アセ未確認)。順序は実行時にしか決まらない。
- 呼出元 `0xd5a755`: `test al, al` → `je 0xd5a9cf`。偽のとき `0xd5a9cf` へ抜け、`[rbx+0x60]` は `0xd5a733` の −2 のまま (status −2)。

#### 7.3 間接先 `*(0x16b8300)` と判定入力 X (受入 3)

- `0xd5e620(self)`: `mov rax, [0x15e05b8]` (`0xd5e624`) の値は `0x16b8300` (.bss)。`call [rax]` (`0xd5e62b`)。rcx (self) は素通し。間接先 = `*(0x16b8300)`。
- `0x16b8300` への store は `0xc39831` (`mov [rip+0xa7eac8], rax`) の 1 件。rax は `0xc3982c` の `call 0x4235f0` の戻り値。引数は rcx = `[0x16b85c8]` (`0xc3981e` の RIP 相対ロード)、rdx = `0xc3a4b8` (`0xc39825` の `lea`。次の命令 `0xc3982c` + `0xc8c` = `0xc3a4b8`)。
- `0xc3a4b8` は UTF-16LE の `PyModule_GetState` (`pe_va_read.py` の wstr で確認)。名前引数は PE 上で確定。
- `0x4235f0`: `rdx >> 16` が 0 なら序数として `0x4235e0(rcx, rdx)` を呼ぶ (`0x42361e`)。非 0 の `0xc3a4b8` は名前側 (`0x423629`): `0x4139f0(&tmp, rdx, 0)` (wchar 列の長さ計算を含む。変換本体は未確認) → `0x414000` (ポインタの取り出し) → `0x4235e0(rcx, ptr)`。
- `0x4235e0` は `jmp [0x1971600]`。`[0x1971600]` は pefile の import directory で `kernel32.dll!GetProcAddress` (IAT の VA。ImageBase `0x400000` 込み)。IAT のファイル上の値 `0x1573c7c` は RVA で、VA `0x1973c7c` の IMAGE_IMPORT_BY_NAME (hint 2 バイト + `GetProcAddress`、`0x1973c7e` で確認) を指す。`0x1573c7c` を VA として読むと .data の別の値になる (前段の「名前テーブルとして読めない」は誤り)。
- hmod = `[0x16b85c8]`: PE 上は .bss。書込みは `0xc395ca` (`mov [rip+0xa7eff7], rax`) の非 0 の 1 件と、`0xc3938a` の 0 の 1 件 (`pe_xref.py`)。非 0 の格納元は `0xc395b5` の `call 0x6539e0(rcx = L"Python312" (VA `0xc3a124`), rdx = 0, r8 = L"Python\" (VA `0xc3a144`))` の戻り値。`0x6539e0` の中身 (モジュール読込みの経路) は未確認。
- よって間接先 = `GetProcAddress(hmod, "PyModule_GetState")` の戻り値。名前は PE で確定し、hmod は実行時の値なので、関数の実体は実行時にしか決まらない。名前は CPython の `PyModule_GetState(PyObject*)` と同じ形と読める (推定。未検証)。
- X = `[this+0x50]` (`0xd843f0`・`0xd843fc`)。this は `0xd5e620` の戻り値が指す値 (前段 §5)。this が実行時の値なので、X の実体は PE 上では決まらない。X の書込み元 (`0xd843f0` の先) は、this が決まらないため特定の対象にしない。

#### 7.4 未解決 (第 2 段の時点)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 偽条件 A・B・C・D の状態を書く側の確定 (7.2 の候補は未確認) | guard の実行時の真偽 | #3212 (本 issue に残す。PE 静的解析の範囲外) |
| 7.1 の書込み探索の範囲外 (別名経由の `[Q+8]` 書込み。前段 §2 の制限) | `[Q+8]` の書込みの網羅。受入 1 の「間接 store を含む」が部分達成 | #3212 (本 issue に残す) |
| 間接先の hmod `[0x16b85c8]` (`0x6539e0(L"Python312", …)` の戻り値。格納は `0xc395ca`) と X の実体。確定済み: `[0x1971600]` = kernel32!GetProcAddress、名前 `PyModule_GetState` | `*(0x16b8300)` の実体と X の実行時の値 | #3212 (本 issue に残す。実行時の観測が要る) |

#### 測定 (第 2 段)

- 測定 commit: `75bac8b5c` (`pe_va_read.py` に UTF-16LE 出力を追加した commit。コードを変えた最後の commit)。前段の probe 追加は `e833017d7`。
- 展開: 前段と同じ (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin`。22,227,016 B・2.9 秒)。
- 実測: `FL_WIN64_DIR=$RUNNER_TEMP/fl3549 python3 analysis/flapi/pe_va_read.py 0x125b0f8,0x125b1c0,0x125b190,0x125b140,0x13a5c90,0x125b258,0x15e04a8,0x16baff0,0x15e0ff0,0x125b208,0x15e1890,0x13e7628,0x125b220,0x15e30f8,0x15f7190,0x15f72f8,0x16baff1,0x15e05b8,0x16b8300,0x1971600,0x1573c7c,0x1973c7c,0x1973c7e,0x16b85c8,0xc3a4b8,0xc3a124,0xc3a144` (27 VA・§7 の値の一覧) は real 0.036 秒・user 0.022 秒。load average (1 分値) 0.04 → 0.04。出力 27 行。
- 出力の要点: `0x125b0f8` → `0x125b1c0`、`0x125b258` → `0x1262b80`、`0x15e05b8` → `0x16b8300` (.bss)、`0x1971600` → `0x1573c7c` (RVA)、`0x1973c7e` = `GetProcAddress`、`0xc3a4b8` = `PyModule_GetState`、`0xc3a124` = `Python312`、`0xc3a144` = `Python\`。出力の値は 7.1〜7.3 の記載と一致。
- 差分: `git diff 75bac8b5c HEAD -- tools/python/analysis` の出力は空 (0 行)。

### 8. 第 3 段 (#3212 の 3 回目の run): 別名経由の書込みを制御フローに沿って追跡 (受入 1 の残り)

前段 §7.4 の未解決「別名経由の `[Q+8]` 書込みの網羅」を、新規 probe `analysis/flapi/pe_chain_alias.py` で追った。線形走査 (`pe_chain_stores.py`) は `jmp` でタグを消すため、ジャンプ先の書込みを取り逃がす。新 probe は次の規則で追う。

- seed: `.text` 全体の `mov r, [G]` (タグ QS) と `mov r, [Q スロット]` (タグ QO) の直後の位置 (2425 箇所)。
- 分岐は両方の飛び先へ (状態 = タグ集合で重複排除)、`jmp` は飛び先へ、`ret`・間接 jmp で止まる。`add/sub reg, imm` で Q のオフセットを更新する。
- Q を保持するレジスタと `[rsp|rbp+d]` の spill を追う。引数レジスタ (rcx/rdx/r8/r9) に Q を載せた直接 call は、callee の先頭から同じ規則で再帰的に追う。
- 追加の起点 (Q 固有。seed があるときだけ): (a) Q の仮想デストラクタ `0x976dc0`、(b) Q の vptr 表 `0x9764d8` の `-0x48`〜`-0x8` の全スロット。
  - 根拠 (PE 上の値の連鎖): ctor `0x976b60` が `dl=1` で `0x410320(this = [0x976410] = 0x9764d8)` を呼ぶ。`0x410320` は `call [this-0x30]` (= `[0x9764a8]` = `0x40f960`)。`0x40f960` は rcx (= this) を保存して `0x40fb40` に渡し、`0x40fb40` は `mov rdi, rbx` (rbx = rcx) して `0x40fb66` で `mov [rsi], rdi`。よって Q の vptr = `0x9764d8`。
  - dtor: `0x40faa0` の `call [rbx-0x20]` (rbx = Q の vptr) = `[0x9764b8]` = `0x976dc0`。`0x976dc0` は `[Q+8]` を読んで `0x40faa0` (O の解放) に渡す。追跡した範囲に `[Q+8]` への書込みは無い。
- 追わないもの: 戻り値 (`rax`) による Q の受け渡し、間接 jmp、間接 call の先 (vptr 表の seed 以外)。

#### 結果 (測定 commit `2b735fa53`)

| 項目 | 件数 | 内容 |
|---|---|---|
| seed (G・Q スロットからの `mov r, [..]`) | 2425 | 全 `.text` の線形走査で集めた |
| 追跡した状態 | 8742 | ret で止まった経路 23 |
| `[Q+8]` の非 0 書込み | 2 | `0x1263571`・`0x1264145` (前段と同じ。`mov [rcx+8], rax`) |
| `[Q+8]` の読出し (O) | 278 | 前段の 277 に、dtor `0x976df6` の 1 件を加えた |
| 引数で Q を渡した直接 call の先 | 22 | 再帰的に追跡。いずれも `[Q+8]` への書込みは無い |
| スタックへの spill | 6 | 追跡 (タグはスタック slot に乗る)。格納先は Q として追う |
| グローバル・別オブジェクトへの格納 | 0 / 1 | 1 件 (`0x40fb66`) は偽陽性: 割当関数 `0x40f960` を this = Q として seed したため、this が `0x9764d8` (vptr 自身) の経路を Q と誤認した |
| push で Q を積む | 0 | |
| Q を引数に持つ間接 call (未解決) | 8 | `0x40944e`・`0x40fab5`・`0x4100d1`・`0x4100df`・`0x4100ed`・`0x41034e`・`0x4103d2`・`0x415ca8`。`0x40fab5` は dtor として seed 済み |
| Q を `rax` で返す ret (未解決) | 1 | `0x416091` |

- 陰性対照 `0x13a5000` (Q スロットの値 0): seed 0・追跡 0 (`store=0 load=0`)。Q 固有の起点は seed があるときだけ使う (`2b735fa53` の修正)。
- 参照の一致: 線形版 `pe_chain_stores.py 0x15e4790 8` の pass 1 (`bfceba9e` 測定) は `intra_store=2`・`intra_load=277`。新 probe の書込み 2 箇所は線形版と一致。

#### 測定

- 測定 commit: `2b735fa53` (`pe_chain_alias.py` の最後のコード変更)。測定は HEAD で再現した。
- 展開: 前段と同じ (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl3212 extracted/block00031_PE.bin`。22,227,016 B・2.9 秒)。
- 陽性: `FL_WIN64_DIR=$RUNNER_TEMP/fl3212 python3 analysis/flapi/pe_chain_alias.py 0x15e4790 8` (real 1 分 1.2 秒。scan 60.8 秒・walk 0.3 秒)。load average (1 分値) 0.60 → 0.86。
- 陰性対照: `... 0x13a5000 8` (scan 60.8 秒。walk 0)。load average 0.95 → 0.98。
- 差分: `git diff 2b735fa53 HEAD -- tools/python/analysis` の出力は空 (0 行)。

#### 結論 (受入 1 の残り)

- 別名 (スタック・直接 call・CFG 合流) を経由した `[Q+8]` の非 0 書込みは、追跡した範囲で 2 箇所 (`0x1263571`・`0x1264145`) のみ。前段と同じ。
- 未解決 (子 issue へ移送): Q を this として呼ぶ間接 call 8 箇所の先と、Q を返す `0x416091` の呼出し元。受入 1 の「間接 store を含む」は、この 8 + 1 箇所の範囲で未達。

### 追加解析 (#3817 受入 1: this = Q の呼出元・同一基本ブロック判定)

- 測定 commit: `2067a068b` (`pe_this_q_callers.py` 追加。コードを変えた最後の commit)。展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'`。
- 再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_this_q_callers.py 0x410090 0x410340 0x4103c0`。同一基本ブロック内で rcx が `[0x15e4790]`→`[0x141d6b8]` 由来の Q と確定できる呼出元 (Q 列) は、3 関数とも 0 件 (`0x410340` 3558 件・`0x4103c0` 1296 件の大半はブロック外 = unknown/other)。陽性対照は未確認 (既知の鎖は間接 call のため E8 元にならない)。
- 未確定・未確認: 間接 call 8 箇所のうち `0x4100d1`・`0x415ca8` は実行時テーブル (未確定)。`0x410090`・`0x410340`・`0x4103c0` の this = Q はブロック跨ぎを含めて未確認。
