# PY-195 (#3403): item tag の解決リスト (L1・L2・P) と K の複写経路の PE 確定

親: #3287 (PY-182)。前段: `tools/python/REPORT_PY176.md` §4・§6。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- **受入 1 は確定** (要素の型名を除く)。`0xf8ca50` (item の tag) の 3 分岐の値域を確定した (§1-4)。L1 は大域 channel 列 (スロット `0x15e2218`)、要素の `+0x2f8` は MIDI 入力ポート (既定 -2)。L2 は channel rack 列 (スロット `0x15e0128`)、要素の `+0x32c` は選択フラグ、`+0x794` は chanId (§1-2・§1-3)。
- **受入 2 は意味を確定、書込み値は未確定**。issue の `[0x655bf8]` は命令 `0xf8caa1` の RIP 相対変位の表示で、実 VA は `0x15e26a0` (`0xf8caa8 + 0x655bf8`)。そのスロットが指す `.bss` の dword `0x193fa10` は、表 `[0x15e06a0]` の要素添字 (cur index) である (§2)。その値の書込み元は子 #3442 [PY-198]。
- **受入 3 は部分**。K (`0x16bacf0`) への RIP 相対の store は 0 件、読出しは 2 件 (`cmp`)。K 周辺を RIP 相対で指す bulk 複写は 0 件。ポインタ経由の書込みは未検査で、子 #3443 [PY-199] に移した (§3)。

## 測定

- 測定 commit (コードを変えた最後の commit): `4df135f10` (`pe_item_tag_probe.py`・`pe_item_tag_scan.py` の追加)。ベースは origin/main `42357b73e`。作業は `3403-py195-item-tag` の worktree (`../ws-3403`)。
- 展開: `cd <展開先> && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst extracted/block00031_PE.bin` (real 2.785 秒・22,227,016 バイト・1 回)。`$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) の実在は `ls` で確認済み。展開先は repo 外 (`FL_WIN64_DIR`)。
- probe: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_item_tag_probe.py` → 20 件 PASS (命令 17・大域スロット 3)・summary OK・終了 0。
- ネガティブコントロール: repo 外の複製で `0xf8ca60` の `cmp edx, 0xfff` の即値の 1 バイト (`0x0f`→`0x0e`) を壊した → `FAIL 0xf8ca60 cmp edx, 0xfff (got: cmp edx, 0xeff)`・summary: 1 FAIL・終了 1。
- scan: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_item_tag_scan.py` → real 16.458 秒・終了 0。命令 4,877,087。P (`0x15e26a0`) の読出し 247・P 経由の dword store 2 (0x12900d7・0x12a458d)・`0x193fa10` への RIP 参照 6・K 周辺 `[K-0x200, K+0x20)` の RIP 参照 501・bulk 279 (文字列命令 272 + memset thunk `0x5e1120` の呼出し 7)・うち K 周辺の RIP 参照を直前 40 命令 (96 バイト以内) に持つもの 0。
- xref: `pe_xref.py 0x15e26a0,0x16bacf0` → 63.1 秒・命令 5,022,467・hits 249・stores 0 (K と P の全参照。K は 2 件、P は 247 件)。
- 逆アセ (`pe_disasm.py`・終了 0): `0xf8ca50` 80・`0xf8c9d0` 60・`0x11e83d0` 120・`0x11e8280` 150・`0xfe8bb0` 40・`0x12900ca` 14・`0x12a4583` 12・`0x12c1960` 14。
- 呼出し元: `pe_callgraph.py callers 0x12a4450` → 6 件 (`0x10219f8`・`0x10485aa`・`0x1193c45`・`0x12ab58b`・`0x12ab911`・`0x12acbe7`)。
- 差分の証跡: `git diff 4df135f10 HEAD -- tools/python/analysis/flapi` の出力は下 §5 に記す。
- KPI: 本 PR は解析のみで、起動・GUI の挙動は変えていない。KPI は測定していない (動かしていない)。

## 1. 受入 1: L1・L2 の要素と f8ca50 の 3 分岐

### 1-1 列の取得 (`0xfe8bb0(list, idx)`)

列オブジェクトは `+0x10` = 件数 (dword)、`+0x8` = 要素ポインタ配列。`0 <= idx < 件数` なら `[[list+8]+idx*8]`、範囲外は NULL を返す。

### 1-2 L1 (`0x11e83d0(idx)`)

- 列の参照: `[0x15e2218]` (`.data` の値 `0x16bafc8` が列オブジェクト)。大域 channel 列 (REPORT_PY72_APPENDIX_3214 の一覧 A、dl≠0 の経路)。
- `idx < 0` なら -1。それ以外は、添字 `i = 0..件数-1` で `[L1[i]+0x2f8] == idx` の最初の i を返す (要素ポインタではなく添字)。無ければ -1。
- `+0x2f8` は MIDI 入力ポート。根拠: API `getChannelMidiInPort` が `+0x2f8` を返す (REPORT_PY41_1514)、既定値 -2 を `0xfe976e` が書く (同)。本 PR の再読でも `0x11e8415` が `cmp dword ptr [rax+0x2f8], ebx` であることを確認 (probe)。

### 1-3 L2 (`0x11e8280(F, n, S)`)

- 列の参照: `[0x15e0128]` (`.data` の値 `0x16bafd0`)。channel rack 列 (REPORT_PY39 §7 の `useGlobal=0` の経路)。
- 件数分の走査で、`[L2[i]+0x32c] != 0` を満たす n+1 番目 (n=0 なら最初) の添字 i を取る。
- 見つからず、F≠0 なら -1。`f8ca50`・`f8c9d0` の呼出しは `F=1, n=0, S=0` の 1 通りで、F=0 の補助走査 (`+0x32d` の比較) はこの 2 関数からは通らない。
- 見つかったとき、S=0 なら `[L2[i]+0x794]` (chanId)、S≠0 なら i。`f8ca50`・`f8c9d0` は S=0 なので chanId を返す。
- `+0x32c` は選択フラグ (setter `0xff8a90` が `[rbx+0x32c]` に書く、REPORT_PY39 §7)。`+0x794` は chanId (REPORT_PY100 の読み方、本 PR の probe で `0x11e8371` の `mov eax, dword ptr [rax+0x794]` を確認)。

### 1-4 f8ca50 の 3 分岐 (tag の値域)

`id = [item+0x10]`・`top10 = id >> 22`・`high16 = id >> 16` とする。

| 枝 | 条件 | 戻り値 (tag) | 値域 |
|---|---|---|---|
| (i) | `high16 != 0xfff` かつ `top10 != 0xff` | -1 | {-1} |
| (ii) | `high16 != 0xfff` かつ `top10 == 0xff` | `dword[P]` (= `dword[0x193fa10]`) | 0x193fa10 の値 (§2。書込み値は未確定) |
| (iii-a) | `high16 == 0xfff`・`top10 != 0` (`idx = top10 - 1`)、L1 に `+0x2f8 == idx` の要素がある | L1 の添字 i | [0, L1 の件数 - 1] |
| (iii-b) | (iii-a) 不成立、L2 に `+0x32c != 0` の要素がある | `[L2[i]+0x794]` | chanId (dword の全域) |
| (iii-c) | `high16 == 0xfff` で (iii-a)・(iii-b) とも不成立 (`top10 == 0` を含む) | -1 | {-1} |

### 1-5 f8c9d0 (key 生成) への反映

- (i): key = `id`。
- (ii): key = `(id & 0x3fffff) + (dword[P] << 22) + 0x70000000` (`0xf8ca33`〜`0xf8ca41`)。
- (iii): tag ≥ 0 なら key = `(id & 0xffff) | (tag << 16)`、tag = -1 なら key = -1 (`0xf8ca0d`〜`0xf8ca1f`)。
- REPORT_PY176 §4 の記述と一致する。本節で (iii) の中身 (L1・L2) を確定した。

## 2. 受入 2: `[0x655bf8]` (スロット P = `0x15e26a0`) の指す値

- 変位の解決: `0xf8caa1` の `mov rax, qword ptr [rip + 0x655bf8]` は `0xf8caa8 + 0x655bf8 = 0x15e26a0` を読む。`0xf8c9d0` の `0xf8ca33` (`[rip + 0x655c66]`) も同じ `0x15e26a0`。
- P の値は `.data` の初期値 `0x193fa10` (`.bss` の dword)。`P` への RIP 相対の store は 0 件 (`pe_xref`・stores 0)。
- 役割: dword `0x193fa10` は表 `[0x15e06a0]` の添字 (cur index)。`0x12900d9`〜`0x12900f1` が `[0x15e06a0] + (*P * 0x28f) * 8` で要素 (1 要素 0x1478 バイト) のアドレスを作る。静的表 `0x16bd564` も同じ stride で、`0x12c1960` は `table[*P] == rcx` を返す (`sete`)。別関数の `0x12c1980` は、`[rcx+0x19] != 0` のとき 1 を返し、それ以外は同じ比較をする。
- 読出し: RIP 相対の直接参照 6 件 (`0x12c1967`・`0x12c198d` (movsxd)・`0x12c2f5b`・`0x12c592f` (movsxd)・`0x12c6082`・`0x12c6224` (cmp))。P 経由の読出し 247 件 (`mov reg, [P]`)。
- 書込み (dword): P 経由の store が 2 件。
  - `0x12900d7` (`mov dword ptr [rax], ecx`、rax = P)。関数 `0x128f9e0`〜`0x1294ab8` (`tools/icall/REPORT.md` の巨大 GUI 構築関数)。ecx = `[rbp+0x838]`。
  - `0x12a458d` (同形、rax = P)。関数 `0x12a4450`〜`0x12a46aa`、呼出し元 6 件。ecx = `[rbp+0x3c]`。
- 書込み値の出どころ (呼出し元の引数と `[rbp+0x838]` の由来) は未確定。よって f8ca50 (ii) 枝の tag の値域も未確定。子 #3442 [PY-198] に移す。

## 3. 受入 3: K (`0x16bacf0`) の書込みと複写

- K は `.bss` の dword。RIP 相対の参照は 2 件で、どちらも読出し (`cmp`): `0xf82a43` (`cmp dword ptr [rip + 0x7382a7], eax`、関数 `0xf82a10`) と `0xf82c48` (`cmp dword ptr [rip + 0x7380a2], ebx`、関数 `0xf82c20`)。RIP 相対の store は 0 件。
- K 周辺 `[K-0x200, K+0x20)` の RIP 相対参照は 501 件。大域が密に並ぶため、K を含む構造体の基底と大きさは未特定。
- bulk: 文字列命令 272 件 (`rep movsq` 162・`rep stosq` 60・`rep movsb` 17・`rep movsd` 8・`rep stosb` 2 ほか) と、memset の thunk `0x5e1120` (IAT `0x1972170` の `jmp`) の呼出し 7 件。K 周辺を RIP 相対で指す命令が直前 40 命令 (96 バイト以内) にあるものは 0 件。
- 限界: 上の検査は RIP 相対の直接指定だけを見る。レジスタ経由 (ポインタ) の store と bulk は検査していない。よって「K = 0 (書込み無し)」は、RIP 相対の store が 0 件で K 周辺の直接の複写が 0 件である範囲でのみ成立する。残りは子 #3443 [PY-199] に移す。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x193fa10` の書込み値の出どころ (`0x12a4450` の 6 呼出し元の ecx、`0x128f9e0` の `[rbp+0x838]`) | f8ca50 (ii) 枝の tag の値域、f8c9d0 (ii) の key | #3442 [PY-198] |
| K のポインタ経由の書込みと、K を含む構造体の基底・大きさ | K = 0 の前提 | #3443 [PY-199] |
| L1・L2 の要素の struct 型名 | 名前付けのみ。動作は確定済み (本 REPORT は「channel レコード」と呼ぶ) | なし (動作に影響しない) |

## 5. 差分の証跡

- 測定 commit `4df135f10` 以降、`analysis/flapi` で変わったのは main 取り込み (merge `fe10569cf`) で追加された 2 本だけ。`git diff 4df135f10 HEAD -- tools/python/analysis/flapi` の出力: `pe_py183_probe.py | 206 ++++`・`pe_vmt_probe.py | 108 ++++` (2 files, 314 insertions)。PY-195 の `pe_item_tag_probe.py`・`pe_item_tag_scan.py`・`pe_xref.py` の差分は 0 行。
- main 取り込み後の再測定 (HEAD `fe10569cf`・load 0.33 (1 分平均)・4 CPU): probe 20 PASS・summary OK・終了 0 / ネガティブコントロール (`0xf8ca60` の即値 `0x0f`→`0x0e`) `FAIL 0xf8ca60 cmp edx, 0xfff (got: cmp edx, 0xeff)`・終了 1 / scan real 9.335 秒・終了 0 / xref real 34.4 秒・終了 0。件数は §測定 の値と全件一致。以降の変更は本 REPORT のみで、`git diff fe10569cf HEAD -- tools/python/analysis/flapi` は 0 行。
