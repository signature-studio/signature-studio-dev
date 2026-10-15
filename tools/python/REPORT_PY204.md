# PY-204 (#3477): 表セル 0x15e26a0 の読込み 247 箇所の書込み先を分類し、表セル経由で 0x193fa10 へ書く箇所を確定する

親: #3442 (PY-198)。前段: `tools/python/REPORT_PY198.md` §3・§5 (「書込みは 2 箇所だけ」は未検証と記載)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと前向きデータフローによる解析)。

## 結論 (PE 実測。3 つの受入条件)

1. **表セル経由で 0x193fa10 へ書く箇所は `0x12900d7` と `0x12a458d` の 2 箇所だけ** (確定。範囲は §4)。
   - 表セル 0x15e26a0 を RIP 相対で読む命令は 247 件 (`mov reg, qword ptr [rip+..]`・`rax` 167・`rcx` 63・`rdx` 14・`r8` 1・`r9` 2)。
   - 読んだ値 P (= 0x193fa10) を全 247 起点から前向きに追うと、P へ書く命令は 2 件 (各 1 起点)。
     P+k (k ≠ 0) への書込み・索引付き書込み (`[P+idx*s]`)・フレーム退避・間接 call は 0 件。
   - P を ABI 引数レジスタ (rcx/rdx/r8/r9) で渡す call は 1 件 (0x12a586d → 0x1182d30)。この callee は先頭で `rcx` を `mov rcx,[rip+..]` で再代入してから読むので P を使わない (下の C5 注)。
   - P を ABI 外のレジスタ (rax) に残したまま call/jmp する箇所は 107 件 (呼出し先 41 種)。その呼出し先の内部 (depth 1) では P の読込み・書込み・引数渡しは 0 件 (C10・C11)。ただし depth 1 の内部から P を rax のまま更に call/jmp する箇所が 13 件あり、その先 (depth 2 以降) は解析していない (§4・U4)。
2. `0x12a4390` は `[0x193fa10]` を書かない (確定)。
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
- 記録する事象: `store` (P への書込み)・`read` (P の読込み)・`passed` (P を ABI 引数レジスタ rcx/rdx/r8/r9 か stack 引数で call/jmp へ渡す)・`passed-other` (P を ABI 外のレジスタ (rax 等) に残したまま call/jmp する)・`escape` (P をフレーム外へ格納)・`indirect` (間接 jmp)・`spill` (フレーム退避)。
- callee 検査 (C10・C11): `passed-other` の呼出し先 41 種を、rax = P の入口状態から同じ cfg で追う (depth 1。その内部からの call は記録のみで追わない)。

## 2. 結果 (`--dump` の実測。247 起点・STEP_CAP 200000 で全件 truncated=0)

| 事象 | 件数 (起点 VA の distinct) | 内訳 |
|---|---|---|
| read (P の読込み) | 245 | 配列添字・比較・ポインタ参照 |
| store (P への書込み) | 2 | HIT の 2 件 (下表) |
| passed (ABI 引数・stack 引数で P を渡す) | 1 | 0x12a586d → call 0x1182d30 (rcx) |
| passed-other (ABI 外のレジスタに P が残ったまま call/jmp) | 102 | 呼出し箇所は 107 件 (C10)。全て rax のみ |
| escape / indirect / spill / undecodable | 0 | — |

| 書込み VA | 命令 | 起点 | 分類 |
|---|---|---|---|
| `0x12900d7` | `mov dword ptr [rax], ecx` (値 = `[rbp+0x838]` = idx) | 0x12900ca の 1 件 | HIT |
| `0x12a458d` | `mov dword ptr [rax], ecx` (値 = `[rbp+0x3c]`) | 0x12a4583 の 1 件 | HIT |

- 0x12a4528 の読込み (0x12a452f `mov eax,[rax]`) は rax を V1 で上書きするので、0x12a458d へは届かない (cfg の kill どおり)。
- 書込み値の出どころ (idx の範囲・`[rbp+0x3c]` の値域) は本件の受入条件外。下の未解決 U1・U2。

## 3. 検証

- 解析の再現: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py204_cell_writes.py --check` (14 項目)。
  `--dump <TSV>` で事象の一覧、`--method window` で窓法の検算、`--negctl-nokill` で kill を外した場合 (N1)。
- 測定 commit: `f7489f0f8` (解析 script の最後のコード変更)。以降のコード差分: `git diff f7489f0f8 HEAD -- tools/python/analysis/flapi/pe_py204_cell_writes.py` は空 (0 行)。
  同ディレクトリの `pe_k_struct_probe.py` (main 取り込みで入った #3443 の解析・469 行) はこの解析が使わないので、差分の範囲に含めない。
- 直前の script 変更 (`git diff ee18182d9 f7489f0f8`・51 行追加 6 行削除): C5・C8 の表題の修正、`passed-other` の記録、`cfg_from` (callee 検査用) の切出し、C10〜C12 の追加。`window_explore` は変更していない。
- 実測時間 (1 プロセス・単一スレッド。4 core。実行中の loadavg は未採取で、uptime の 1 分平均は 0.3〜1.0):
  - `--check`: 172.6 s (C11 の判定を直す前の 1 回目の値。13/14 で、C11 だけが FAIL)。14/14 の時間は `f7489f0f8` の段階では未採取 (`--dump` と並行して走ったため)。HEAD `a0f25d5ff` で単独に再実行: 14/14 PASS・97.5 s (real 1m37.5s・実行開始時 loadavg 0.20・`fl-win64` の `block00031_PE.bin`)
  - `--dump`: 86.8 s (`truncated=0`)
  - `--method window`: 85.0 s (`truncated=0`)
  - 比較: `pe_rip_refs.py 15e26a0` は 34.2 s (同じ `.text` の線形走査。`ee18182d9` で採取。本 PR で変更していない)
- PASS/FAIL (`--check` の結果。`14/14 PASS`):
  - C0: 起点は 247 件・全て `mov r.., qword ptr [rip..]` (読込みのみ)。
  - C1: cfg 追跡は全件 STEP_CAP 内で終わる (truncated 0)。
  - C2: HIT の集合は `{0x12900d7, 0x12a458d}` と一致。C3: HIT は全て 4 byte・offset 0 の完全一致。
  - C4: OFF・IDX・PIDX の書込みは 0 件。
  - C5: ABI 引数レジスタ (rcx/rdx/r8/r9) で P を渡す call は `0x12a586d` の 1 件だけ。注: 0x1182d30 は `mov rax,[rip+0x45e763]` (0x1182d36) → `mov rcx,[rax]` (0x1182d3d) で rcx を再代入し、その前に rcx を読まない。
  - C6: escape・indirect は 0 件。
  - C7: 0x12a4390 の到達可能な書込みは 5 件 (`rbp`・`rbx`・`rdx` 基底) で、P 由来の基底は無い。
  - C8: 0x12a449c `mov ecx,0x7d8`・0x12a44a1 `call 0x409410`・0x12a44a6 `mov [rbp+0x40],rax` (呼出しの並び。確保関数であることは未確認)。
  - C9: f8ca50 (ii) の分岐と読込み先 (`shr eax,0x16`・`cmp eax,0xff`・`jne 0xf8caaa`・`mov rax,[rip+0x655bf8]` = 0x15e26a0)。
  - C10: `passed-other` (P が ABI 外レジスタに残ったまま call/jmp) の箇所は 107 件・呼出し先 41 種・全て rax のみ。
  - C11: rax = P で入った呼出し先 41 種の内部 (depth 1) で、P の読込み・書込み・ABI 引数渡し・escape・indirect・spill は 0 件。全件 STEP_CAP 内。depth 2 への受渡し (`passed-other`) は 13 件 (§4 範囲外)。`0x1046a30`・`0x128f9e0` (先頭 60 命令で rax を参照しない 2 種) も cfg で終端まで追った。
  - C12: 絶対アドレス (base 無しの disp・即値) による 0x15e26a0・0x193fa10 の参照は 0 件 (`.text` 全体の線形走査)。
- **ネガティブコントロール N1 (kill を外す)**: レジスタ kill を無効にすると HIT が 8 件に増える
  (`0x104cc4e`・`0x128d273`・`0x12900d7`・`0x129040f`・`0x1290427`・`0x12a458d`・`0x12ab83d`・`0xfb2707`)。
  kill を外すと再代入後も P を持ち続けるため、増えた分は偽陽性になる。例えば `0x104cc47 mov rax,[rip+0x593f82]` は別のセルで rax を再代入するので、`0x104cc4e mov [rax],1` は P への書込みではない (確認済み。残り 5 件は個別には確認していない)。
  kill の有無で結果が変わる (= 検出器が再代入を見ている) ことを示す。
- **独立検算 (窓法・別アルゴリズム)**: 起点から線形に 40 命令だけ見て、`base == 読込んだレジスタ` の書込みを数える (kill なし・分岐無視)。
  HIT 20 種 (distinct な書込み VA)・HIT-PART 4 種・OFF 6 種が出る (過検出)。cfg の HIT 2 件 (0x12900d7・0x12a458d) は窓法の HIT に含まれる (包含)。
  窓法の余分な HIT 18 件は kill が無いための偽陽性。代表 0x128a41f (`add dword ptr [rax],1`) は 0x128a418 `mov rax,[rip+0x356f51]` (別セル) の後の書込みで、P への書込みではない。
- 他の経路 (表セル以外) の確認: `pe_rip_refs.py 193fa10` は 6 件 (0x12c1967・0x12c198d・0x12c2f5b・0x12c592f・0x12c6082・0x12c6224)、全て読込み (`movsxd`・`cmp`)。
  `.data` (file 上のセクション) 内で値 `0x193fa10` を持つ qword は表セル `0x15e26a0` の 1 件だけ。絶対アドレスによる参照は C12 の 0 件。

## 4. 検証範囲 / 範囲外

- 範囲: 表セル 0x15e26a0 の読込み 247 起点から、レジスタ・フレーム slot を経由する P の流れ。
  ABI 引数レジスタ (rcx/rdx/r8/r9) で P を渡す call/jmp は 1 件。P を rax (ABI 外) に残したまま call/jmp する箇所は 107 件で、呼出し先 41 種の depth 1 の内部は C11 で検査した (0 件)。
- 範囲外 (弱める):
  - ABI 外のレジスタ経由の受渡しの depth 2 以降: depth 1 の内部からも、P を rax (または非引数レジスタ) のまま call/jmp する箇所が 13 件ある。script (C11) はその先を解析していない (U4)。したがって「P を引数で渡す call は 1 件」は引数レジスタの意味であり、rax 経由で P が呼出し先に渡る可能性は depth 1 までしか script では見ていない。
    - PR レビュー時の手作業の閉包確認 (script 外・再現コードは本 PR に含まない): rax = P の呼出しを再帰的に辿ると、呼出し先は depth 1 の 41 種から計 53 種になる。その内部で store・read・escape・spill・ABI 引数渡し・間接 jmp は 0 件。passed-other は 18 件 (depth 1 で 13、depth 2 で 5)。そのうち `0x409410` 内の `call qword ptr [rip+IAT]` (0x40941e) は、後で rax が上書きされ P を使わない。
  - 間接 call: `indirect` は間接 jmp と間接 jcc だけを数える (script の `call` 分岐は間接 call を `indirect` に数えない)。間接 call は呼出し時点の状態で `passed`・`passed-other` の判定だけ受ける。表 (§2) の `indirect 0 件` は間接 jmp・間接 jcc の件数。
  - P を引数として受け取った callee の内部の書込み: 1 件 (0x1182d30) は先頭の rcx 再代入で P を使わないことを C5 で確認。
  - ヒープや構造体を経由する別ポインタ経由の書込み: 解析していない (表セル以外に値 0x193fa10 を持つ `.data` の qword が無いことと、RIP 参照が全て読込みであること、絶対アドレス参照が 0 件であることだけ確認)。
  - `.bss` の初期値 (ファイルに無い。0 の前提)。
  - 書込み値の値域 (0x12900d7 の idx = 0..0x1f5 は PY-198 の既存結論。0x12a458d の eax は未確定 → U1)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U1: 0x12a458d が書く `[rbp+0x3c]` の値 (V1、または 0x12a4438 で書いた `eax` = `idiv` の剰余 + 1 (0x12a43f5)) の値域 | 0x193fa10 の値域 | PM agent の判断待ち: 0x12a458d が書く `[rbp+0x3c]` の値域を本 issue に含めるか・既定案: PY-198 の残件として PY-198 側に戻す |
| U2: 0x128f9e0 の `edx` (idx) の上流 (60 件の直接 call) と、6 呼出し元の引数の上流 | 0x12900d7 の書込み値・0x12a4450 の ecx | 既存の子 [PY-203] #3476 (PY-198 §5 の起票先) |
| U3: 表セル以外 (ヒープ・構造体) を経由する別ポインタの P への書込み | 0x193fa10 の書込みの網羅 | PM agent の判断待ち: 解析の限界として §4 に明記するか・既定案: 明記のみで起票しない |
| U4: rax (ABI 外) 経由で渡った P の depth 2 以降 (depth 1 の内部からの nested call 13 件を含む) | rax 経由で P に書く箇所の網羅 (§4 の閉包確認は script 外の手作業で、script の C11 は depth 1 まで) | PM agent の判断待ち: 本 issue で depth 2 以降を script で解析するか・既定案: §4 の手作業確認を記載し、解析の限界として §4 に明記したうえで起票しない |

## 6. 再現の注意

- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` (アーカイブ内は `extracted/block00031_PE.bin`。`FL_WIN64_DIR=<展開先>` で参照する)。
- 窓法の HIT 20 種・OFF 6 種は、kill を持たない検算の過検出 (結論には使わない)。
