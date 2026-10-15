# PY-204 (#3477): 表セル 0x15e26a0 の読込み 247 箇所の書込み先を分類し、0x193fa10 への書込みを確定する

親: #3442 (PY-198)。前段: `tools/python/REPORT_PY198.md` §3・§5 (「書込みは 2 箇所だけ」は未検証と記載)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと前向きデータフローによる解析)。

## 結論 (PE 実測。3 つの受入条件)

1. **0x193fa10 への直接書込みは `0x12900d7` と `0x12a458d` の 2 箇所だけ** (確定。範囲は下の「検証範囲」)。
   - 表セル 0x15e26a0 を RIP 相対で読む命令は 247 件 (`mov reg, qword ptr [rip+..]`・`rax` 167・`rcx` 63・`rdx` 14・`r8` 1・`r9` 2)。
   - 読んだ値 P (= 0x193fa10) を全 247 起点から前向きに追うと、P へ書く命令は 2 件 (各 1 起点)。
     P+k (k ≠ 0) への書込み・索引付き書込み (`[P+idx*s]`)・フレーム退避・間接 call は 0 件。
   - P を引数で渡す call は 1 件 (0x12a586d → 0x1182d30)。この callee は先頭で `rcx` を `mov rcx,[rip+..]` で再代入してから読むので P を使わない (下の C5 注)。
2. **`0x12a4390` は `[0x193fa10]` を書かない** (確定)。
   - 0x12a4390 へ P が入るのは 0x12a442d の 1 箇所だけで、そこでは `cmp dword ptr [rcx], esi` の読込みしか無い。
   - 到達できる書込みは 5 件で、どれも P 由来でない: `[rbp+0x28]`・`[rbp+0x20]` (自フレーム 2)、`[rbx+0x3c]` (rbx = 呼出し元フレーム 1)、`[rdx]` (2)。
     rdx は `[rbx+0x40]` の要素アドレス (`[rbp+0x28]`・`[rbp+0x20]` を経由)。`[rbx+0x40]` は `0x12a44a6` で `call 0x409410` (引数 `ecx = 0x7d8`) の戻り値を格納した値で、この関数を確保関数と推定している (未確認)。
   - 呼出し元 (0x12a4558・0x12a4576) の引数は `rcx = rbp`・`edx = int` で、P は渡らない。
3. **`f8ca50` (ii) 枝の tag と `[0x193fa10]` の対応** (確定)。
   - tag = `[rcx+0x10] >> 22` (10 bit。値域 0..0x3ff)。(ii) 枝へ入るのは `([rcx+0x10] >> 16) != 0xfff` のとき (0xf8ca66)。
   - (ii) 枝で P を読む (0xf8caa1 `mov rax,[rip+0x655bf8]` = 0x15e26a0) のは **tag == 0xff のときだけ** (0xf8ca9a `cmp eax,0xff`・0xf8ca9f `jne`)。
     その場合 `ebx = [P]` (cur) を返す。他の tag は初期値 `ebx = -1` (0xf8ca55) を返し、P を読まない。
   - よって tag と `[P]` の対応は「tag == 0xff のとき `[P]` の値をそのまま返す」1 通りで、P への書込みは `f8ca50` の中に無い。

## 1. 方法

- 起点: `.text` を線形走査し、RIP 相対で 0x15e26a0 を指す命令を全件列挙 (`pe_py204_cell_writes.py` の `rip_loads`)。
- 追跡 (cfg 法): 読込直後のレジスタを `P+k` (k は既知の定数) として持つ。
  `mov reg,reg`・`mov reg,[rbp|rsp+d]`・`lea`・`add/sub reg,imm` で `P+k` を伝播し、書込まれたレジスタは kill する。
  rbp・rsp 基準のフレーム slot への退避も追う。分岐は両方、`ret` で終端。`call` は戻り先へ進み、caller-saved を kill する。
  P を持つ状態が消えた時点で打ち切る。
- 分類: 書込み先 `P+k+disp` (サイズ `s`) が `0x193fa10..0x193fa13` と重なれば HIT (完全一致 4 byte なら HIT)、重ならなければ OFF、索引を含めば IDX、P が索引なら PIDX。
- 記録する事象: `store` (P への書込み)・`read` (P の読込み)・`passed` (P を rcx/rdx/r8/r9 か stack 引数で call/jmp へ渡す)・`escape` (P をフレーム外へ格納)・`indirect` (間接 jmp)・`spill` (フレーム退避)。

## 2. 結果 (`--dump` の実測。247 起点・STEP_CAP 200000 で全件 truncated=0)

| 事象 | 件数 (起点 VA の distinct) | 内訳 |
|---|---|---|
| read (P の読込み) | 245 | 配列添字・比較・ポインタ参照 |
| store (P への書込み) | 2 | HIT の 2 件 (下表) |
| passed (P を引数で渡す) | 1 | 0x12a586d → call 0x1182d30 (rcx) |
| escape / indirect / spill / undecodable | 0 | — |

| 書込み VA | 命令 | 起点 | 分類 |
|---|---|---|---|
| `0x12900d7` | `mov dword ptr [rax], ecx` (値 = `[rbp+0x838]` = idx) | 0x12900ca の 1 件 | HIT |
| `0x12a458d` | `mov dword ptr [rax], ecx` (値 = `[rbp+0x3c]`) | 0x12a4583 の 1 件 | HIT |

- 0x12a4528 の読込み (0x12a452f `mov eax,[rax]`) は rax を V1 で上書きするので、0x12a458d へは届かない (cfg の kill どおり)。
- 書込み値の出どころ (idx の範囲・`[rbp+0x3c]` の値域) は本件の受入条件外。下の未解決 U1・U2。

## 3. 検証

- 解析の再現: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py204_cell_writes.py --check` (11 項目)。
  `--dump <TSV>` で事象の一覧、`--method window` で窓法の検算、`--negctl-nokill` で kill を外した場合 (N1)。
- 測定 commit: `ee18182d9` (解析 script の最後のコード変更)。以降のコード差分: `git diff ee18182d9 HEAD -- tools/python/analysis` は空 (本 REPORT の commit だけが後に続く)。
- 実測時間 (各コマンドの `time` の real。1 プロセス・単一スレッド。4 core。実行後の loadavg 0.38 0.70 0.57。実行中の loadavg は未採取。`tar` 展開は `block00031_PE.bin` のみ抽出で 2.9 s):
  - `--check` (起点の列挙 + cfg 247 起点 + N1 の cfg 再実行 + 静的検査): 97.9 s
  - `--dump` (起点の列挙 + cfg 247 起点): 95.7 s
  - `--method window` (起点の列挙 + 窓法): 91.9 s
  - 比較: `pe_rip_refs.py 15e26a0` は 34.2 s (同じ `.text` の線形走査)。
- PASS/FAIL (`--check` の結果。`11/11 PASS`):
  - C0: 起点は 247 件・全て `mov r.., qword ptr [rip..]` (読込みのみ)。
  - C1: cfg 追跡は全件 STEP_CAP 内で終わる (truncated 0)。
  - C2: HIT の集合は `{0x12900d7, 0x12a458d}` と一致。C3: HIT は全て 4 byte・offset 0 の完全一致。
  - C4: OFF・IDX・PIDX の書込みは 0 件。
  - C5: passed は `0x12a586d` の 1 件だけ。注: 0x1182d30 は `mov rax,[rip+0x45e763]` (0x1182d36) → `mov rcx,[rax]` (0x1182d3d) で rcx を再代入し、その前に rcx を読まない。
  - C6: escape・indirect は 0 件。
  - C7: 0x12a4390 の到達可能な書込みは 5 件 (`rbp`・`rbx`・`rdx` 基底) で、P 由来の基底は無い。
  - C8: 0x12a449c `mov ecx,0x7d8`・0x12a44a1 `call 0x409410`・0x12a44a6 `mov [rbp+0x40],rax` (呼出しの並び。確保関数であることは未確認)。
  - C9: f8ca50 (ii) の分岐と読込み先 (`shr eax,0x16`・`cmp eax,0xff`・`jne 0xf8caaa`・`mov rax,[rip+0x655bf8]` = 0x15e26a0)。
- **ネガティブコントロール N1 (kill を外す)**: レジスタ kill を無効にすると HIT が 8 件に増える
  (`0x104cc4e`・`0x128d273`・`0x12900d7`・`0x129040f`・`0x1290427`・`0x12a458d`・`0x12ab83d`・`0xfb2707`)。
  kill を外すと再代入後も P を持ち続けるため、増えた分は偽陽性になる。例えば `0x104cc47 mov rax,[rip+0x593f82]` は別のセルで rax を再代入するので、`0x104cc4e mov [rax],1` は P への書込みではない (確認済み。残り 5 件は個別には確認していない)。
  kill の有無で結果が変わる (= 検出器が再代入を見ている) ことを示す。
- **独立検算 (窓法・別アルゴリズム)**: 起点から線形に 40 命令だけ見て、`base == 読込んだレジスタ` の書込みを数える (kill なし・分岐無視)。
  HIT 20 件・HIT-PART 4 件・OFF 6 件が出る (過検出)。cfg の HIT 2 件 (0x12900d7・0x12a458d) は窓法の HIT に含まれる (包含)。
  窓法の余分な HIT は kill が無いための偽陽性。代表 0x128a41f (`add dword ptr [rax],1`) は 0x128a418 `mov rax,[rip+0x356f51]` (別セル) の後の書込みで、P への書込みではない。
- 他の経路 (表セル以外) の確認: `pe_rip_refs.py 193fa10` は 6 件 (0x12c1967・0x12c198d・0x12c2f5b・0x12c592f・0x12c6082・0x12c6224)、全て読込み (`movsxd`・`cmp`)。
  `.data` (file 上のセクション) 内で値 `0x193fa10` を持つ qword は表セル `0x15e26a0` の 1 件だけ。

## 4. 検証範囲 / 範囲外

- 範囲: 表セル 0x15e26a0 の読込み 247 起点から、レジスタ・フレーム slot を経由する P の流れ。P が call/jmp の引数になる箇所は 1 件。
- 範囲外 (弱める):
  - P を引数として受け取った callee の内部の書込み: 1 件 (0x1182d30) は先頭の rcx 再代入で P を使わないことを C5 で確認。他に P を渡す call は無い。
  - ヒープや構造体を経由する別ポインタ経由の書込み: 解析していない (表セル以外に値 0x193fa10 を持つ `.data` の qword が無いことと、RIP 参照が全て読込みであることだけ確認)。
  - `.bss` の初期値 (ファイルに無い。0 の前提)。
  - 書込み値の値域 (0x12900d7 の idx = 0..0x1f5 は PY-198 の既存結論。0x12a458d の eax は未確定 → U1)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U1: 0x12a458d が書く `[rbp+0x3c]` の値 (V1、または 0x12a4438 で書いた `eax` = `idiv` の剰余 + 1 (0x12a43f5)) の値域 | 0x193fa10 の値域 | PY-198 §5 では #3477 に割当てていたが、本 issue の受入条件 3 件に含まれない。PM 判断 |
| U2: 0x128f9e0 の `edx` (idx) の上流 (60 件の直接 call) と、6 呼出し元の引数の上流 | 0x12900d7 の書込み値・0x12a4450 の ecx | 既存の子 [PY-203] #3476 (PY-198 §5 の起票先) |
| U3: 表セル以外 (ヒープ・構造体) を経由する別ポインタの P への書込み | 0x193fa10 の書込みの網羅 | 解析の限界として明記。起票しない (PM 判断) |

## 6. 再現の注意

- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'`
- 窓法の HIT 20 件・OFF 6 件は、kill を持たない検算の過検出 (結論には使わない)。
