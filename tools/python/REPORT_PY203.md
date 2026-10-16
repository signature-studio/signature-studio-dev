# PY-203 (#3476): 0x12a4450 の呼出し元の残りの引数と、0x128f9e0 の edx 60 箇所の setter

親: #3442 (PY-198)。前段: `tools/python/REPORT_PY198.md` §2 (6 呼出し元の ecx 式)・§5 (未解決表)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- **0x128f9e0 の直接呼出し 60 箇所は、edx の直前の setter を全件確定した**。分類は IMM 7 / COPY 7 / MEM 38 / AMBIG 8 (合計 60、ENTRY 0、UNKNOWN 0)。COPY・MEM の基底と AMBIG の合流元の上流は未追跡 (子 [PY-221] #3617)。
- **0x1192f80 の ecx の入力**: `ecx = sgn(edi − esi)`。`edi` = `[rbp+0x54]` の上位 16bit、`esi` = 下位 16bit。`[rbp+0x54]` への書込みは 0x1192f99 の `mov [rbp+0x54], r8d` の 1 箇所で、直接呼出し 1 件 (0x11fbc44) の `r8d` は `[[rbp+0x140]+0x20]`。`[rbp+0x140]` の上流は未追跡 (子 [PY-221] #3617)。
- **0x12ab710 の r9d (第 4 引数)**: 直接呼出し 1 件 (0x12ac257 in 0x12ac210) の前に r9 への書込みは無く、0x12ac210 の第 4 引数のまま。0x12ac210 の直接呼出しは 0 件で、上流は未確定 (子 [PY-220] #3616)。
- **0x12ab520・0x12acb70・0x1021670 の rdx・eax の上流は未確定**。3 関数とも直接 E8 呼出し 0 件・RIP 相対参照 0 件・即値参照 0 件で、関数ポインタまたは仮想呼出しのみと見られる (子 [PY-220] #3616)。0x12ab520 の 4 バイトは `.text` のデータ島 (file 0xe796bb、VA 0x127a2bb) に現れ、直後に ShortString `TFXForm` がある。Delphi 風 VMT の推定 (推定)。
- **0x1046a30 の ecx (0x10485aa) の入力は未確定**。`[rbp+0x5b8]` は 0x1046a30 内で 74 件書込まれる経路依存の状態変数 (0x10485bb→0x104850f の入口がある)。`[rbp+0x4e8]` は 0x10474d8 の 1 件 (rax = `[rax+rcx*8]`、0x10474d4)。(子 [PY-219] #3615)
- **0x45c290 の戻り値 eax**: 0x45c8c8 で `[rbp+0x3c]` を返す。`[rbp+0x3c]` への書込み 36 件は、call 24 件 (0x40f540 14・0x45c040 4・0x45c170 3・0x45c1c0 1・再帰 0x45c290 2) か、`[rax (+off)]` の読出し 12 件のどちらか。値の意味は未確定 (子 [PY-221] #3617)。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) から `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` を展開 (2.3 秒)。
- 検証起点 commit: `2f0bd0aa5` (PR 作成時の origin/main)。測定 commit は §4。
- 逆アセは `pe_callgraph.py` の線形走査 (int3 の直後を関数先頭とみなす)。直接 E8 のみを数え、間接 call (`call reg`・`call [mem]`) と `jmp` 経由は数えない。
- 範囲外・限界 (線形走査の限界):
  - 線形走査の命令境界に一致しない直接 jmp/jcc の飛び先は **101,337 件** (直接 jmp/jcc 429,417 件の 23.6%)。線形走査はデータ島や非境界の飛び先を含み得るため、§2 の窓 (所属関数先頭〜呼出し) は線形走査の再同期結果であり、命令境界の確定には使えない。
  - 60 箇所のうち 5 件に、`pe_py203_edx_sites.py` の TSV が注記を付けている (いずれも線形走査のずれ・データ島の疑い):
    - 0x1021826 (COPY・関数 0x1021670): 窓内の非境界の飛び先 0x1021733
    - 0x11d6c0c・0x11d6d77 (IMM・関数 0x11d55c0): 関数先頭からの素直な復号が 0x11d58b0 で失敗
    - 0x12a1b09 (MEM・関数 0x12a13c0): 先頭からの復号が 0x12a1a16 で失敗。非境界の飛び先 2 件 (0x12a1a1e・0x12a1ab8)
    - 0x12a9a1b (MEM・関数 0x12a93b0): 先頭からの復号が 0x12a9904 で失敗。非境界の飛び先 3 件 (0x12a9938・0x12a9958・0x12a9982)
  - 上の 5 件を含む 60 箇所の結論は、線形走査に頼らない前向き復号と飛び先の検算で補う (§4)。検算の対象は即値の直接 jmp/jcc のみで、間接 jmp・jump table・ret 経由の飛び込みは含まない。窓内の間接 jmp と、setter 後の窓内 call は 60 箇所とも 0 件 (rdx の保持を仮定する箇所は無い)。

## 1. 受入 1: 6 呼出し元の残りの引数の上流 (0x12a4450 の呼出し元)

| 呼出し元 (call VA) | 上流が必要な入力 | 確定した範囲 | 未確定 |
|---|---|---|---|
| 0x1192f80 (0x1193c45) | ecx = sgn(edi − esi) | edi = `[rbp+0x54]>>16`、esi = `[rbp+0x54]&0xffff`、`[rbp+0x54]` = 第 3 引数 r8d (0x1192f99、1 書込み) | 呼出し元 0x11fbc44 の r8d = `[[rbp+0x140]+0x20]` の `[rbp+0x140]` ([PY-221]) |
| 0x12ab520 (0x12ab58b) | rdx (第 2 引数) | 直接呼出し 0 件 | 関数ポインタ・VMT 経由の呼出し元 ([PY-220]) |
| 0x12acb70 (0x12acbe7) | rdx (第 2 引数) | 直接呼出し 0 件 | 同上 ([PY-220]) |
| 0x12ab710 (0x12ab911) | r9d (第 4 引数) | 直接呼出し 0x12ac257 (in 0x12ac210) に r9 書込み 0 件 | 0x12ac210 の第 4 引数 (直接呼出し 0 件 → [PY-220]) |
| 0x1046a30 (0x10485aa) | ecx = sgn([rbp+0x5b8] − [[rbp+0x4e8]+0x258]) | `[rbp+0x5b8]` の clamp 式 (0x1048403〜0x1048445)、`[rbp+0x4e8]` の書込み (0x10474d8) | `[rbp+0x5b8]` の経路依存の値 (74 件)・`[rbp+0x4e8]` の上流 ([PY-219]) |
| 0x1021670 (0x10219f8) | ecx = eax = 0x45c290 の戻り値 | 0x45c290 の戻り値の出どころ ([rbp+0x3c]) | 戻り値の意味 ([PY-221])・0x1021670 の直接呼出し 0 件 ([PY-220]) |

## 2. 受入 2: 0x128f9e0 の直接呼出し 60 箇所の edx

分類は `tools/python/analysis/flapi/pe_py203_edx_sites.py` (60 行の TSV を stdout に出す)。setter は線形窓 (所属関数先頭 〜 呼出し) の最後の edx/rdx 書込み。

| 分類 | 件数 | 内容 |
|---|---|---|
| IMM | 7 | `xor edx, edx` (値 0)。0xc4d157・0xd16328・0xfdc518・0x11d29f5・0x11d6c0c・0x11d6d77・0x1296d99 |
| COPY | 7 | `mov edx, reg` で複製元が確定 (例: 0x1021826 ← `[rbp+0x150]`、0x1193bf0 ← `and esi, 0xffff`、0x12e3b29 ← `[rax+0x258]`) |
| MEM | 38 | `mov edx, [reg+X]` (基底レジスタの上流は未追跡 → [PY-221]) |
| AMBIG | 8 | 合流 (setter を迂回する jcc/jmp) で複製元が経路依存: 0xfc820f・0x118a275・0x118a3f4・0x12abcd6・0x12acbc1・0x12c609e・0x12c6240・0x12e6abe |
| ENTRY | 0 | 関数の第 2 引数のまま渡る呼出しは無い |
| UNKNOWN | 0 | |

ネガティブコントロール (分類ロジックを 1 つ外す): `--ablate merge` で AMBIG 8 → 0 (COPY 7 → 15)。`--ablate copy` で COPY 7 → 15 (AMBIG 8 → 0)。合流判定を外すと AMBIG の 8 件が COPY に戻ることを確認した。

## 3. 受入 3: 0x45c290 の戻り値

- 戻り値は `[rbp+0x3c]` の最後の書込み (0x45c8c8 `mov eax, [rbp+0x3c]`、ret は 0x45c8d0 と 0x45c8ed の 2 箇所)。
- 書込み 36 件の直前命令は、`call 0x40f540` 14・`call 0x45c040` 4・`call 0x45c170` 3・`call 0x45c1c0` 1・`call 0x45c290` 再帰 2 (計 24) と、`movsx/movzx/mov` の `[rax]` / `[rax+8]` 読出し 12。型コード (word `[rax]`) の分岐で値を選ぶ構造に見える (推定)。
- 意味 (各フィールドと各 call の値) は未確定 (子 [PY-221] #3617)。

## 4. 検証

測定 commit: `c2bb306b0` (コードを変えた最後の commit。probe の check 名の修正と `pe_py203_linear_check.py` の追加)。以下は同一 commit で実行した値。

- probe: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py203_probe.py` → 27/27 PASS・終了 0 (3 回とも)。所要 115・114・115 秒 (n=3)。1 分 load は 0.6〜1.0。
- edx 分類: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py203_edx_sites.py` → 終了 0 (3 回とも 30 秒、TSV は 3 回とも同一)。IMM 7・COPY 7・MEM 38・AMBIG 8 (60 行)。直接 call の集合が想定の 60 箇所と違うと、スクリプトは終了 1 で止まる (内部の照合)。
- ネガティブコントロール: `--ablate merge` → AMBIG 8 → 0 (COPY 15)、`--ablate copy` → COPY 7 → 15 (AMBIG 0)。いずれも終了 0。
- 線形走査の限界の検算: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py203_linear_check.py $RUNNER_TEMP/py203/edx_sites.tsv` → 終了 0。
  - 直接 jmp/jcc (即値の飛び先) 429,417 件、境界に一致しない飛び先 101,337 件 (23.6%)。§0 の値と一致。
  - 60 箇所それぞれ、setter から site まで前向きに新規に復号する (線形走査の結果を使わない): 境界に整列 60/60、途中に jmp/jcc/call/ret なし 60/60。
  - (setter, site] に飛び先があり、飛び元が [setter, site) の外にある直接 jmp/jcc: 0 件 (該当 site 0/60)。
- 負の対照 (この検算が 0 件を自明に出すものでないことの確認): AMBIG 8 件の setter を関数先頭に置き換えた TSV で同じ検算を実行すると、終了 1。途中に分岐・call のある site は 8/60 (AMBIG 8 件すべて)、外からの飛び込みのある site は 3/60 (0x12acbc1・0x12c609e・0x12c6240)。
- 本 REPORT は後続の docs commit。`git diff c2bb306b0 HEAD -- tools/python/analysis/flapi` の出力は 0 行 (flapi の範囲は測定 commit から変わっていない)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1046a30 の `[rbp+0x5b8]` (経路依存・74 件書込み) と `[rbp+0x4e8]` の上流 | 0x10485aa の ecx (受入 1) | [PY-219] #3615 |
| 0x12ab520・0x12acb70・0x1021670・0x12ac210 の呼出し元 (関数ポインタ・VMT 経由)、0x12ab520 の VMT 推定の検証 | 受入 1 の rdx 2 件・eax・r9d | [PY-220] #3616 |
| 0x45c290 の戻り値の意味、0x128f9e0 の edx の MEM 38・COPY 7・AMBIG 8 の基底、0x1192f80 の r8d の呼出し元 `[[rbp+0x140]+0x20]` の `[rbp+0x140]` の上流 | 受入 1 の eax・edi/esi (ecx = sgn(edi − esi))・受入 2 の残り | [PY-221] #3617 |
| 線形走査の限界 (非境界の飛び先 101,337 件、5 件の注記の窓)、間接 jmp・jump table 経由の飛び込み | §0・§4 の範囲外。60 箇所の結論は前向き復号と飛び先の検算で確認済み。命令境界の全面的な再構成は PY-203 の受入外 | PM 判断待ち (未起票。親 #3476 は CLOSED) |
| PY-273 の残り (§6) | 0x128f9e0 の edx の MEM 38・COPY 7・AMBIG 8 の上流 (受入の残り) | #5407 (大域・rbx ENTRY・0x12b4)・#5408 (rbp スロット)・#5409 (COPY 7・AMBIG 8)。親 #4588 は CLOSED |

## 6. PY-273 (#3927): edx の基底 MEM 38 の 1 段上流

照合は `analysis/flapi/pe_py273_base.py` (MEM setter の基底レジスタの、setter 直前の値を `pe_py203_edx_sites.py` の `resolve` で 1 段分類) と `analysis/flapi/pe_py273_globals.py` (大域と rbp スロットの確認)。

- MEM 38 の基底レジスタの 1 段分類: rax 19・rbx 9・rbp 6・rsi 2・rdi 1・rdx 1。
  - rbp 6 件 (スタックスロット): `[rbp+0x2c]` 4 件、`[rbp+0x24]` 1 件、`[rbp+0x4508]` 1 件。直前 store が見つかるのは 4 件 (0xf699ff・0x128e8f2・0x12878f4・0x12a46bf)。残り 2 件 (`[rbp+0x2c]` の setter 0x12a1afe・0x12a1c16、関数 0x12a13c0・0x12a1be0 内) は関数内に直前 store が無い。
  - rax 19・rbx 9 の内訳は未整理 (rax は大域 3 種の RIP 相対読込み 12 件を含む。rbx は COPY 6・MEM 2・ARITH 1)。
- 大域 3 種 (0x15e26a0・0x15e2218・0x15e22d8) はいずれも `.data` の節にあり、`.text` 全体 (5,022,299 命令) で書込みは 0 件。内訳は次の通り。
  - RIP 相対: 読込み (`mov reg, [rip+X]`) のみ。読込みは 0x15e26a0 247 件・0x15e2218 1563 件・0x15e22d8 284 件。`mov` の書込み形は 0 件。
  - 即値 (アドレス直書き) 0 件、`lea` 0 件。
  - `.data` の初期値は 0x193fa10・0x16bafc8・0x16bd450。初期値はポインタに見えるが、読込み側の型は未確認。
  - 検査は `analysis/flapi/pe_py273_globals.py` の `rip_writes`・`imm_hits`・`lea` (3 種とも 0)。exit 0。
  - 含意: 大域は `.text` の中では値を入れられていない。`.data` の初期値をそのまま使うか、別の節 (`.bss`・`.idata`) からの書込みかの確認は未実施。
- COPY 7・AMBIG 8 の基底は、本 PR では分類していない。

### 6.1 2 段目 (`analysis/flapi/pe_py273_second.py`)

測定 commit: `50a96b5a7` (`pe_py273_second.py` を追加した最後のコード変更 commit)。以下の出力はこの commit で実行した値。`git diff 50a96b5a7 HEAD -- tools/python/analysis/flapi` は 0 行 (本節の REPORT 以外に変更なし)。

測定の中身: `pe_py273_second.py` (`pe_py273_base.py` の基底分類に 2 段目を足したもの)。

- MEM 38 の基底 setter ごとに、基底の直前値を `resolve` で追った (30 秒・終了 0・MEM 38 を全件処理)。
- **rax 19** の内訳: 大域 0x15e26a0 の RIP 相対読込み 11 件、0x15e2218 の読込み 1 件、`[rbp+0x28]` 1 件、`[rbp+0x4e8]` 1 件、`[rbp+0x30]` 3 件、`[rbp+0x520]` 1 件、`[rbx+0x968]` 1 件。
- **rbx 9** の内訳: 引数のまま (ENTRY) 5 件 (ecx 4 件 = 0xd5e753・0xd61608・0xd627e6・0x12e3b8e、edx 1 件 = 0x118586f)、`[rbx+0x12b4]` の複製 1 件 (0xf5c3a5 は COPY rsi)、`[rbx+0x12b4]` の読込み 1 件 (0xf5c3ea)、`[rbp+0x28]` 1 件、ARITH 1 件 (0xeaa555 `lea rbx, [rax+rcx*4+0x24]`)。
- **ENTRY の呼出し元**: 上の ENTRY 5 件の関数のうち、直接呼出し 0 件 (間接呼出しのみ・未追跡) は 4 件 (0xd5e6c0・0xd615a0・0xd626c0・0x1185840)。0x12e3a60 (ecx) は直接呼出し 2 件: 0x12e8487 (in 0x12e83a0、ecx = ENTRY 第 1 引数、さらに上流は未追跡)、0x12eebe2 (in 0x12ee510、ecx = `[rbp+0x150]`、同スロットの直前 store 0x12ee5cb `mov [rbp+0x150], rcx`)。
- **`[rbp+0x2c]` 2 件** (0x12a1afe・0x12a1c16): 直前の `call 0x12be230` が out 引数 (`[rbp+0x2c]` = rdx) に書く。0x12be230 は `[rdx] = ecx >> 22`、`[r8] = (ecx >> 16) & 0x3f` (純粋な復号)。入力 `ecx = [x+0x18] − 0x70000000` の上位 10 bit が `[rbp+0x2c]` になる。x は 0x12a13c0 で rsi (`mov rsi, rdx` 0x12a1ace)、0x12a1be0 で rdx (`mov ecx, [rdx+0x18]` 0x12a1bfd)。この 2 関数の直接呼出し元は 0 件 (`pe_callgraph.py callers`)。関数ポインタ経由と見られる (PY-220 #3616 と同類)。
- 大域 3 種は 6 節の通り `.text` で書込み 0 件 (`pe_py273_globals.py` 終了 0)。

### 6.2 未確定 (受入の残り)

- rax 19・rbx 9 の大域 3 種を埋める経路 (`.data` の初期値の読込み側の型と、`.bss`・`.idata` からの書込みの確認は未実施)。
- rbx の ENTRY 経路の呼出し元 (直接呼出し 0 件の関数は、間接呼出し元の追跡が要る)。`[rbx+0x12b4]` の上流。
- `[rbp+0x2c]` 2 件の x (rsi/rdx) の上流 (関数ポインタ経由)。
- COPY 7・AMBIG 8 の基底 (1 段目は 6.3)。

### 6.3 COPY 7・AMBIG 8 の複製元の基底 (`analysis/flapi/pe_py368_copy_ambig.py`)

測定 commit: `40b6621fa` (スクリプトを追加した commit)。同じ commit で 2 回実行し、TSV は一致 (終了 0・rows=15・36.6 秒)。

- COPY 7 (複製元を 1 段で分類):
  - ARITH 4: 0x1193bf0 (`and esi, 0xffff`)、0x127d0cc (`sub esi, 2`)、0x12a5868 (`sub eax, 2`)、0x12a86c9 (`add ebx, 1`)。基底は無し。
  - MEM (rbp スロット) 2: 0x1021826 (`[rbp+0x150]`)、0x12ab8e8 (`[rbp+0xa0]`)。直前 store は本測定の TSV に出ず未追跡 (0x10216ff は REPORT_PY269 §の既存記述のみ・本測定で未検証、0x12ab72f は出典なし)。
  - MEM (基底あり) 1: 0x12e3b29 ← `[rax+0x258]`、rax = `[rip+0x2fe749]` = VA 0x15e2218 (大域)。
- AMBIG 8 (主経路の複製元を 1 段で分類):
  - MEM 3: 0x118a275 ← `[rax+0x258]`、rax = `[rbp+0x38]` (0x118a241)。0x118a3f4 ← `[rax+0x130]`、rax = `[rbp+0x38]` (0x118a362)。0x12e6abe ← `[rax+rbx*4+0xdc]`、rax = `[rbp+0x20]` (0x12e6a22)。
  - ARITH 1: 0x12abcd6 (`add ebx, 1`)。
  - IMM 1: 0x12acbc1 (`mov eax, 1`)。
  - COPY 2: 0xfc820f (主経路 rax ← `movsxd rax, eax`、0xfc81bc)、0x12c6240 (主経路 rax ← `[rip+0x31c1ff]` = VA 0x15e22d8)。
  - AMBIG 1: 0x12c609e (主経路 `add eax, [rcx+0x94]` の合流が、さらに経路依存)。
- まとめ (終端の区別):
  - 値そのものが ARITH・IMM で終わる: 0x1193bf0・0x127d0cc・0x12a5868・0x12a86c9 (COPY)、0x12abcd6・0x12acbc1 (AMBIG 主経路)。
  - 値が `[rbp+X]` の直読みで終わる: 0x1021826・0x12ab8e8 (COPY)。rbp スロットの直前 store は本測定では未追跡 (TSV の `@0x10217c5`・`@0x12ab885` の load 位置までを確認)。
  - 値が大域の直読みで終わる: 0x12c6240 (AMBIG 主経路・大域 0x15e22d8)。0x12e3b29 は `[rax+0x258]` で、rax が大域 0x15e2218 の読込み。
  - 値が `[基底+X]` の読込みで、基底がさらに 1 段必要: 0x118a275・0x118a3f4・0x12e6abe (AMBIG 主経路)。基底 rax は `[rbp+0x38]`・`[rbp+0x20]` (rbp スロット) で、スロットの直前 store は未追跡。0xfc820f は主経路 COPY rax ← ARITH だが、合流元 0xfc81c2→0xfc81c7 の飛び元 rdi が AMBIG のまま。
  - 未確定: 0x12c609e (主経路は ARITH `add eax, [rcx+0x94]` まで届くが、合流元 0x12c6252 の分岐を未分類)。

**受入は部分達成** (COPY 7・AMBIG 8 は 1 段目の基底まで確定。大域 0x15e2218・0x15e22d8 と rbp スロットの直前値の上流は未追跡)。残りは #5407 (大域 0x15e2218・0x15e22d8)・#5408 (rbp スロットの直前値)・#5409 (COPY 7・AMBIG 8 の終端) の子として残す (親 #4588 は CLOSED)。

### 6.4 COPY 7・AMBIG 8 の終端 (`analysis/flapi/pe_py368_terminal.py`・#5409)

測定 commit: `4adefbe8f` (コードを変えた最後の commit。`store_value` の部分書込み分類 `e4aa7fd27` を含む)。同じ commit で 2 回実行し、TSV は一致 (終了 0・rows=7・34.1 秒・34.3 秒)。`git diff 4adefbe8f HEAD -- tools/python/analysis/flapi/pe_py368_terminal.py tools/python/analysis/flapi/pe_py368_copy_ambig.py tools/python/analysis/flapi/pe_py203_edx_sites.py tools/python/analysis/flapi/pe_py273_base.py` は 0 行 (本節の REPORT 以外に依存先の変更なし)。

対象は 6.3 の終端 7 箇所 (スロット `[rbp+X]` の直前 store と、AMBIG の合流元)。

- `[rbp+X]` を基底・複製元とする 5 件 (スロット直前 store の格納値):
  - 0x1021826 (COPY rax ← `[rbp+0x150]`): 直前 store 0x10216ff `mov [rbp+0x150], rcx`、rcx = ENTRY 第 1 引数 (ecx)。窓 111 命令、窓内の非境界の飛び先 1 件 (0x1021733) の注記あり。スクリプトはこの飛び先を「線形走査のずれの疑い」と判定する (窓は線形走査の再同期結果のため、この判定をそのまま採る)。
  - 0x12ab8e8 (COPY rax ← `[rbp+0xa0]` の movzx): 直前 store 0x12ab72f `mov word ptr [rbp+0xa0], r8w`。格納元の r8w は族 r8 の下位ビットで、r8 の直前書込みは ENTRY (第 3 引数 r8d) まで確定 (部分書込みの格納元を族に解決する 1 段を `store_value` に追加)。
  - 0x118a275 (AMBIG 主経路 `[rax+0x258]`、rax = `[rbp+0x38]`): 直前 store 0x118a241 の格納値は r8 ← ENTRY 第 3 引数 (r8d)。合流 2 件 (0x118a22b→0x118a24b・0x118a23f→0x118a24b) の注記あり。
  - 0x118a3f4 (AMBIG 主経路 `[rax+0x130]`、rax = `[rbp+0x38]`): 直前 store 0x118a362 の格納値は r8 ← ENTRY 第 3 引数 (r8d)。
  - 0x12e6abe (AMBIG 主経路 `[rax+rbx*4+0xdc]`、rax = `[rbp+0x20]`): 直前 store 0x12e6a22 の格納値は rcx ← ENTRY 第 1 引数 (ecx)。合流 1 件 (0x12e6a03→0x12e6a2d) の注記あり。
- AMBIG の合流元のみ 2 件 (スロットなし):
  - 0x12c609e: 合流 1 件 (0x12c6252→0x12c5fa8)。合流元 0x12c6252 の分岐は未分類。
  - 0xfc820f: 合流 1 件 (0xfc81c2→0xfc81c7)。飛び元の rdi は AMBIG のまま (主経路 `xor edi, edi` 0xfc81ae の注記あり)。

- まとめ: 7 件のうち、スロットの格納値まで分類できたのは 5 件 (0x1021826・0x12ab8e8・0x118a275・0x118a3f4・0x12e6abe)。0x12c609e と 0xfc820f は合流元の分類が残る。
  - 0xfc820f: 飛び元 0xfc81c2 の rdi は、主経路 `xor edi, edi` (定数 0) と、合流 0xfc81ac→0xfc81b0 からの `movsxd rdi, edi` (0xfc81a6) の 2 経路で、AMBIG のまま。
  - 0x12c609e: 合流 1 件 (0x12c6252→0x12c5fa8) の注記。主経路は `add eax, [rcx+0x94]` (0x12c5f86) を経由する AMBIG で、1 段では閉じない (terminal・edx_sites とも同じ 1 件)。
  - 0x12c6240 (edx_sites の注記): 合流 5 件 (`pe_py203_edx_sites.py` の `len(hits)`。注記に列挙されるのは先頭 3 件のみ)。主経路は `[rip+0x31c1ff]` (VA 0x15e22d8 の大域直読み、0x12c60d2・0x12c60f5)。0x12c6240 の数であり、0x12c609e の数ではない。
- 残り (受入の残り): 0x12c609e の合流元 0x12c6252 の分岐、0xfc820f の飛び元 rdi、スロット ENTRY 値 (ecx・r8d) の呼出し元 (間接呼出しのため未追跡)。

### 6.5 #5407: 大域 3 種の入り方・rbx ENTRY の呼出し元・`[rbx+0x12b4]` の上流

測定 commit: `c44281a3e` (`pe_py273_globals.py` に reloc・初期値の節を足した最後のコード変更 commit)。`git diff c44281a3e HEAD -- tools/python/analysis/flapi` は 0 行。素材は `fl-win64` の `block00031_PE.bin` (展開 3.3 秒)。

- **大域 3 種** (`pe_py273_globals.py` 終了 0・57 秒・load 1.35):
  - 3 種とも `.data` の 8 バイトスロットで、初期値は `.bss` (0x193fa10・0x16bafc8・0x16bd450) を指す。
  - 3 スロットとも base relocation の対象 (`reloc=True`)。ローダが load 時にアドレスを書く。`.text` の書込みは 0 件 (`rip_writes=0`)。
  - 含意: `.data` 初期値は `.bss` の実アドレスで、値の中身は `.bss` の実行時書込みで決まる。その書込み元は静的には未特定。
- **rbx ENTRY の呼出し元** (`pe_callgraph.py callers`): ENTRY 5 件のうち 0xd5e6c0・0xd615a0・0xd626c0・0x1185840 は直接呼出し 0 件。0x12e3a60 は直接呼出し 2 件 (0x12e8487・0x12eebe2、6.1 の通り)。`.text` 外の 8 バイト関数ポインタ参照は、この 4 関数について見つからなかった。このため間接呼出し元は未特定。
- **`[rbx+0x12b4]` の上流**:
  - `[rbx+0x12b4]` を読むのは関数 0xf5c340 (`mov rbx, rcx` で、rbx は関数の第 1 引数)。`[reg+0x12b4]` への store は静的に 0 件 (`store-to-0x12b4 count 0`)。
  - 0xf5c340 の直接呼出し元は 0xf5b101 (in 0xf5ae50) と 0xf5c6e8 (in 0xf5c5f0)。
  - 0xf5b101: rcx ← `rbx` (0xf5b0fe)。rbx の経路依存 (AMBIG、主経路 `MEM [rbx+0x7b4]` @0xf5b0eb)。
  - 0xf5c6e8: rcx ← `[rbp+0x28]` (0xf5c6e4)。rsi ← `MEM [rax+0x12b4]` (0xf5c6c1) まで確定。

**受入は未達** (#5407 の 3 項目のうち、大域 3 種の `.bss` 書込み元と ENTRY 4 件の間接呼出し元は未特定。`[rbx+0x12b4]` は 1 段の呼出し元まで確定)。残りは #5407 の受入の残りとして残す (親 #4588 は CLOSED)。

### 6.6 #5407: 大域 3 種が指す `.bss` 実アドレスへの直接参照

測定 commit: `30cefde35` (書込み判定を全ニーモニックに広げた commit)。`git diff 30cefde35 HEAD -- tools/python/analysis/flapi` は 0 行。素材は `fl-win64` の `block00031_PE.bin`。

`analysis/flapi/pe_py273_pointee.py` (終了 0・45.0 秒・load 0.99):

- `.bss` の範囲 0x15e6000-0x196ee9c で、宛先オペランドが RIP 相対で、メモリへ書く命令は 4,726 件 (`rip_writes_total=4726`)。書込みの判定は `writes_dest`: 第 1 オペランドが `[rip ...]` で、`cmp`・`test`・`call`・`push`・`bt`・`lea`・分岐・読込み専用の x87 演算・単一オペランドの `mul`/`imul`/`div`/`idiv` を除く (`lock` 接頭辞は外して判定)。内訳は `mov` 2,717・`movsd` 33・`movss` 37 と、`add` 940・`sub` 923・`or` 41・`fistp` 4・`cmpxchg` 16・`xadd` 5・`xchg` 3・`and` 4・`btr` 2・`cmpxchg16b` 1 (計 4,726)。前版の 2,787 は `mov` 系のみの数で、`mov` 系の件数として読むこと。
- 大域 3 種が指す `.bss` の実アドレスを、`.text` 内の RIP 相対参照で直接読み書きする件数:

| 大域の指す先 | 読込み | 書込み | 即値 | lea |
|---|---|---|---|---|
| G1 0x193fa10 | 6 | 0 | 0 | 0 |
| G2 0x16bafc8 | 0 | 0 | 0 | 0 |
| G3 0x16bd450 | 68 | 0 | 0 | 0 |

- 読みとしての含意: G2 は `.text` から直接参照されない。G1・G3 は直接読まれるが、書込みは 0 件。よって、`.bss` の値は大域スロット (`.data`) 経由の間接書込みで決まると見るのが妥当。この間接書込み元は未特定。
- 限界: 間接書込みを追う経路 (大域スロットへの書込みや、ポインタの複製) は本測定では見ていない。受入の「大域 3 種の入り方」は未達。

**受入は未達** (大域 `.bss` の間接書込み元と、ENTRY 4 件の間接呼出し元は未特定のまま)。残りは #5407 の受入として残す (親 #4588 は CLOSED)。

### 6.7 #5407: rbx ENTRY 4 件の取得経路 (`analysis/flapi/pe_py273_entry_lea.py`)

測定 commit: `60eb21311` (スクリプトを追加した commit)。`git diff 60eb21311 HEAD -- tools/python/analysis/flapi` は 0 行。素材は `fl-win64` の `block00031_PE.bin` (展開 2.8 秒)。exit 0・40.7 秒・load 0.99。

- 6.5 で「間接呼出しのみ・未追跡」とした ENTRY 4 件 (0xd5e6c0・0xd615a0・0xd626c0・0x1185840) は、`.data` の関数ポインタスロットでも `.rdata` の表でもない。`.text` 内の `lea` で番地を取り、直後の直接呼出しの引数に渡される。
  - 0xd5e6c0: `lea r8, [rip-0x142]` (0xd5e7fb) → 直接呼出し 0xd843d0
  - 0xd615a0: `lea r8, [rip-0xf8]` (0xd61691) → 直接呼出し 0xd843d0
  - 0xd626c0: `lea r8, [rip-0x1fe]` (0xd628b7) → 直接呼出し 0xd843d0
  - 0x1185840: `lea rax, [rip+0x18e77e]` (0xff70bb)。直後の `mov [rbx+0x1f4], rax` (0xff70c2) で構造体に格納され、次の直接呼出し 0x60a270 (0xff70ed、rcx = rbx) は引数として rax を渡していない。格納先の読み手は未確認。
- 絶対値の出現 (`.data`・`.rdata`・`.text` の合計、スクリプト修正後の値): 0x1185840 の 8 バイト 1 件・4 バイト 1 件 (いずれも .text 内)。他 3 件は 0 件。
- 含意: 0xd5e6c0・0xd615a0・0xd626c0 は、lea の後の呼出し 0xd843d0 の第 3 引数 (r8 → rdi) として渡される。0xd843d0 の呼出し元と、0x1185840 の格納先の読み手は未追跡。

**受入は未達のまま**: ENTRY 経路は「lea → 0xd843d0・0x60a270」まで確定。大域 3 種の `.bss` 書込み元と `[rbx+0x12b4]` の上流 (0xf5b101 AMBIG・0xf5c6e8) は未追跡。残りは #5407 の受入として残す (親 #4588 は CLOSED)。
