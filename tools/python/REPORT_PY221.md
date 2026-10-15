# PY-221 (#3617): 0x11fba90 の `[rbp+0x140]` の上流 (受入 3 を確定)。受入 1・2 は未着手

親: #3476 (PY-203)。前段: `tools/python/REPORT_PY203.md` §1 (0x1192f80 の r8d)・§5 (未解決表)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- **受入 3 (確定)**: 0x11fc44 の `call 0x1192f80` の第 3 引数 `r8d = [[rbp+0x140]+0x20]` の `[rbp+0x140]` は、関数 0x11fba90 が回すリストの**現在ノード**である。
  `[rbp+0x140]` への書込みは 2 箇所だけで、どちらも「リストを 1 つ進めた次ノード (`[cursor+8]`)」を入れる。
  - 初回 0x11fbb28: `call 0x6668d0(rcx = P)` の戻り値。
  - 2 回目以降 0x11fc526: 0x11fc4e8〜0x11fc51e に 0x6668d0 と同じ前進がインラインで展開されている (`[rbp+0x70]` 経由)。
  - P = `[Y]`、Y = VA `0x16b6e00` (`.bss`)。Y の値は 0xbd6a28 で `call 0x6666d0` (dl=1・r8d=0x40) の戻り値が入り、0xbd69f0 で `call 0x40faa0` の後に 0 になる。Y の入口は `.data` の大域 G (VA `0x15e2e18`、初期値 = Y の番地)。
- **未追跡 (次の段)**: P のカーソル `[P+0x10]`・終端 `[P+0x20]` の初期値、P の確保条件 (0xbd6a00 の呼出し元)、node (`[node+0x8]`・`[node+0x20]`) の連結元。詳細は §4。
- **受入 1 (0x45c290 の戻り値の意味) と受入 2 (0x128f9e0 の edx の基底 MEM 38・COPY 7・AMBIG 8 の上流) は今回着手していない**。issue の範囲を縮め、子 issue に移した (#3926 = PY-272・#3927 = PY-273)。前段の結果は `REPORT_PY203.md` §2・§3 のまま。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GiB) を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で展開し、`$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` に置く (1.5 秒)。
- 検証起点 commit: `396f9f8b6` (origin/main 取得時点)。測定 commit: `357e58987` (スクリプトを追加した commit。以下の数値はこの commit で実行)。
- 逆アセは `pe_callgraph.py` の線形走査 (`load()`)。VA は ImageBase 0x400000 を含む絶対値。
- 窓・関数範囲の判定は線形走査の命令境界に依存する。0x11fba90 の 622 命令と 0xbd68e0・0xbd69d0 付近は境界が整合している (データ島は含まない)。全面的な境界検証は範囲外 (`REPORT_PY203.md` §0 の限界と同じ)。

## 1. 受入 3: `[rbp+0x140]` の上流 (関数 0x11fba90)

### 1-1 書込みと読出し

| 項目 | 命令 (VA) | 内容 |
|---|---|---|
| 書込み A | 0x11fbb28 `mov qword ptr [rbp+0x140], rax` | rax = `call 0x6668d0` (0x11fbb23) の戻り値 |
| 書込み B | 0x11fc526 `mov qword ptr [rbp+0x140], rax` | rax = `[rbp+0x70]` (0x11fc522)。`[rbp+0x70]` は 0x11fc51e の `[cursor+8]` か、0x11fc508 の 0 |
| null 判定 | 0x11fbb2f・0x11fc52d | 0 なら終了 (0x11fc53b) |
| 読出し | 0x11fbc2f・0x11fbc39 | `rax = [rbp+0x140]` → `edx = [rax+0x18]`・`r8d = [rax+0x20]` |
| 呼出し | 0x11fbc44 `call 0x1192f80` | ecx = `[rbp+0x170]` (エントリの rcx)。0x11fbc28 の枝は node の型 `[node+0x10]` が 0 のとき |

- 関数 0x11fba90 (0x11fba90〜0x11fc650、622 命令) の `[rbp+0x140]` を書く命令は上の 2 件だけ (`pe_py221_chain.py` W)。
- 読出し窓 [0x11fbb3d, 0x11fbc40] (67 命令): call 0・`[rbp+0x140]` への書込み 0・間接 jmp 0・ret 0 (N・N2)。窓の外から窓の内部への直接 jmp/jcc は 0 (J)。ループ頭 0x11fbb3d へ入る経路は、0x11fbb37 の fallthrough (初回) と 0x11fc535 の `jne` (2 回目以降) だけ (L)。
- よって 0x11fbc40 の時点の `[rbp+0x140]` は、直前に通った書込み A か B の値そのもの。窓内で値が変わる経路は無い。

### 1-2 初回の P と 0x6668d0

- 0x11fbaf5〜0x11fbb1c: `rax = [G]`・`rax = [rax]` (= P)・`[rbp+0x100] = P`。`rcx = [P+0x18]`・`[P+0x20] = rcx` (終端の再設定)。その後 `call 0x6668d0` (rcx = P)。
- 0x6668d0 (8 命令): `cur = [P+0x10]`。`cur == [P+0x20]` なら戻り値 0 (ストア無し)。それ以外は `next = [cur+8]`・`[P+0x10] = next`・戻り値 `next`。
  → カーソル P+0x10 を 1 つ進める反復子。終端は P+0x20 (初回だけ P+0x18 の値に再設定される)。

### 1-3 2 回目以降のインライン前進 (0x11fc4e8〜0x11fc535)

- 同じ G (VA 0x15e2e18) を読み (`rax = [G]`・`rax = [rax]` = Q)、0x6668d0 と同じ前進を `[rbp+0x78] = Q` で行う (T・T2)。終端 `[Q+0x20]` の再設定は無い。
- 結果を `[rbp+0x70]` → `[rbp+0x140]` に入れ、非 0 なら 0x11fbb3d (型判定) へ戻る。

### 1-4 P の入口 G と Y

- G (VA 0x15e2e18, `.data`): 初期 qword = `0x16b6e00` (`.data` の raw 8 バイト。`pe_py221_chain.py` I)。
  このブロックの RIP 相対参照は 35 件で、すべて `mov reg, qword ptr [rip+X]` の読込み (G)。書込みと `lea` は 0 件。
- Y (VA 0x16b6e00, `.bss`: RVA 0x12b6e00 は `.bss` の範囲 0x11e6000〜0x156ee9c 内): RIP 相対参照 4 件 (Y)。

| VA | 命令 | 関数 | 意味 |
|---|---|---|---|
| 0xbd6901 | `mov rax, [Y]` | 0xbd68e0 | 読込み (rcx = P として `call 0x666780`) |
| 0xbd69e4 | `mov rcx, [Y]` | 0xbd69d0 | 読込み。0xbd69eb `call 0x40faa0` (P の破棄) |
| 0xbd69f0 | `mov [Y], 0` | 0xbd69d0 | 破棄後に P = 0 |
| 0xbd6a28 | `mov [Y], rax` | 0xbd6a00 | rax = `call 0x6666d0` (0xbd6a23) の戻り値。0xbd6a1b `dl = 1`・0xbd6a1d `r8d = 0x40` |

- 0x6666d0 は 0x40 を 0x666570 の第 4 引数 (r9d) に渡す確保ラッパー (推定: 0x40 バイトの確保)。0x6666d0 の第 1 引数 rcx = `[0x6661d0]` (`.text` 内の 8 バイト・値 0x666298)。型情報か誤復号かは未確定。
- 0xbd69d0 と 0xbd6a00 は、それぞれカウンタの条件 (`cmp dword [..], 0` と `cmp dword [..], -1`) で分岐する。呼出し元は未追跡。

### 1-5 まとめ (受入 3 の答え)

```
[rbp+0x140] (0x11fc44 の [[..]+0x20] の基底)
  = 0x6668d0(P) の戻り値 (初回) / [rbp+0x70] = 0x6668d0 と同じ前進 (2 回目以降)
  P = [Y] (VA 0x16b6e00, .bss)      ← 0xbd6a28 で 0x6666d0 (確保・r8d=0x40) の戻り値、0xbd69f0 で 0
  Y の番地 = [G] (VA 0x15e2e18, .data の初期値 0x16b6e00)
```

- 「リストの次ノード」の意味: P+0x10 がカーソル、P+0x20 が終端、node+0x8 が次、node+0x10 が型 (dword)、node+0x18 と node+0x20 が 0x1192f80 の第 2・第 3 引数 (edx・r8d)。
- 0x11fbc44 の呼出しは、型判定 (0x11fbb63 `sub eax, 1` → 0x11fbb66 `cmp eax, -1` → 0x11fbb69 `je 0x11fbc28`) で型 0 のときだけ到達する (関数内で 0x11fbc28 へ直接飛ぶのは 0x11fbb69 の 1 件)。

## 2. 検証

- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_py221_chain.py` → 17/17 PASS・終了 0。
- 所要 (n=3、commit `357e58987`): 24.4・24.2・24.3 秒。load average 0.56・0.68・0.79 (1 分値、並列 1)。
- ネガティブコントロール: `--ablate-write 0x11fc526` (書込み B を観測から外す) → W が FAIL・`summary: 15/16`・終了 1。
- 別アルゴリズムの検算 (既存ツール `pe_rip_refs.py`、RIP 相対の解決を別の実装で行う): `pe_rip_refs.py 0x15e2e18` → hits 35 (スクリプトの G と一致)。`pe_rip_refs.py 0x16b6e00` → hits 4 (Y と一致)。
- 差分: `git diff 357e58987 HEAD -- tools/python/analysis/flapi` の出力は 0 行 (測定 commit から flapi は変わらない)。

## 3. 受入 1・2 (未着手。子 issue #3926・#3927 に移した。前段の状態)

- 受入 1 (0x45c290 の戻り値 eax = `[rbp+0x3c]` の意味): 書込み 36 件の内訳 (call 24・読出し 12) は `REPORT_PY203.md` §3 のまま。
- 受入 2 (0x128f9e0 の直接呼出し 60 箇所の edx の基底): `pe_py203_edx_sites.py` を再実行 → 60 行・終了 0 (20.99 秒、1 run)。クラス件数 IMM 7・COPY 7・MEM 38・AMBIG 8 は `REPORT_PY203.md` §2 と一致 (件数のみ照合。site 単位の一致は未照合)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| P のカーソル `[P+0x10]`・終端 `[P+0x20]`・基準 `[P+0x18]` の初期化 (確保関数 0x666570・0x6666d0 の中) | `[rbp+0x140]` の初期ノード | 親 #3476 への提案 (未起票) |
| P の確保・破棄の呼出し元 (0xbd6a00・0xbd69d0 の呼出し元)、rcx = `[0x6661d0]` の意味 | P の生成・破棄の条件 | 親 #3476 への提案 (未起票) |
| node の連結元 (`[node+0x8]`・`[node+0x10]`・`[node+0x18]`・`[node+0x20]` の書込み) | 0x1192f80 の edx・r8d の値 | 親 #3476 への提案 (未起票) |
| 受入 1: 0x45c290 の戻り値の意味、引数構造体 +0/+8 の意味、0x40f540・0x45c040・0x45c170・0x45c1c0 の意味 | 0x1021670 の ecx | #3926 (PY-272) |
| 受入 2: 0x128f9e0 の edx の基底 MEM 38・COPY 7・AMBIG 8 の上流 | 0x128f9e0 の第 2 引数 | #3927 (PY-273) |
| 線形走査の限界 (非境界の飛び先・データ島) | 窓の結論の前提。窓 N・J の結論は境界の整合に依存 | `REPORT_PY203.md` §5 の行と同じ (親 #3476) |
