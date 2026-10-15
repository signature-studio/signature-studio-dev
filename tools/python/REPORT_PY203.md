# PY-203 (#3476): 0x12a4450 の呼出し元の残りの引数と、0x128f9e0 の edx 60 箇所の setter

親: #3442 (PY-198)。前段: `tools/python/REPORT_PY198.md` §2 (6 呼出し元の ecx 式)・§5 (未解決表)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- **0x128f9e0 の直接呼出し 60 箇所は、edx の直前の setter を全件確定した**。分類は IMM 7 / COPY 7 / MEM 38 / AMBIG 8 (合計 60、ENTRY 0、UNKNOWN 0)。COPY・MEM の基底と AMBIG の合流元の上流は未追跡 (子 [PY-221] #3617)。
- **0x1192f80 の ecx の入力**: `ecx = sgn(edi − esi)`。`edi` = `[rbp+0x54]` の上位 16bit、`esi` = 下位 16bit。`[rbp+0x54]` への書込みは 0x1192f99 の `mov [rbp+0x54], r8d` の 1 箇所で、直接呼出し 1 件 (0x11fbc44) の `r8d` は `[[rbp+0x140]+0x20]`。`[rbp+0x140]` の上流は未追跡。
- **0x12ab710 の r9d (第 4 引数)**: 直接呼出し 1 件 (0x12ac257 in 0x12ac210) の前に r9 への書込みは無く、0x12ac210 の第 4 引数のまま。0x12ac210 の直接呼出しは 0 件で、上流は未確定 (子 [PY-220] #3616)。
- **0x12ab520・0x12acb70・0x1021670 の rdx・eax の上流は未確定**。3 関数とも直接 E8 呼出し 0 件・RIP 相対参照 0 件・即値参照 0 件で、関数ポインタまたは仮想呼出しのみと見られる (子 [PY-220] #3616)。0x12ab520 の 4 バイトは `.text` のデータ島 (file 0xe796bb、VA 0x127a2bb) に現れ、直後に ShortString `TFXForm` がある。Delphi 風 VMT の推定 (推定)。
- **0x1046a30 の ecx (0x10485aa) の入力は未確定**。`[rbp+0x5b8]` は 0x1046a30 内で 74 件書込まれる経路依存の状態変数 (0x10485bb→0x104850f の入口がある)。`[rbp+0x4e8]` は 0x10474d8 の 1 件 (rax = `[rax+rcx*8]`、0x10474d4)。(子 [PY-219] #3615)
- **0x45c290 の戻り値 eax**: 0x45c8c8 で `[rbp+0x3c]` を返す。`[rbp+0x3c]` への書込み 36 件は、call 24 件 (0x40f540 14・0x45c040 4・0x45c170 3・0x45c1c0 1・再帰 0x45c290 2) か、`[rax (+off)]` の読出し 12 件のどちらか。値の意味は未確定 (子 [PY-221] #3617)。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) から `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` を展開 (2.8 秒)。
- 検証起点 commit: `2f0bd0aa5` (PR 作成時の origin/main)。main 取り込み後の測定 commit は §4。
- 逆アセは `pe_callgraph.py` の線形走査 (int3 の直後を関数先頭とみなす)。直接 E8 のみを数え、間接 call (`call reg`・`call [mem]`) と `jmp` 経由は数えない。

## 1. 受入 1: 6 呼出し元の残りの引数の上流 (0x12a4450 の呼出し元)

| 呼出し元 (call VA) | 上流が必要な入力 | 確定した範囲 | 未確定 |
|---|---|---|---|
| 0x1192f80 (0x1193c45) | ecx = sgn(edi − esi) | edi = `[rbp+0x54]>>16`、esi = `[rbp+0x54]&0xffff`、`[rbp+0x54]` = 第 3 引数 r8d (0x1192f99、1 書込み) | 呼出し元 0x11fbc44 の r8d = `[[rbp+0x140]+0x20]` の `[rbp+0x140]` |
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

- `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py203_probe.py` → 27/27 PASS、終了 0。
- `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py203_edx_sites.py` → 終了 0。直接 call の集合は `pe_callgraph.py callers` と照合する。
- ネガティブコントロール (数値): `[rbp+0x54]` の読みも数えると 9 件 (書込み 1 件・読出し 8 件)。edx の `--ablate merge` で AMBIG 8 → 0。
- 測定 commit: `ab3d2d992` (main 取り込みのマージ。前回の測定 commit `0ad96b77d` の後に main が `analysis/flapi/` の 3 ファイル (`pe_k_struct_probe.py`・`pe_mixer_wrappers.py`・`pe_va_read.py`) を変えたため、マージ後のコードで測定し直した)。
- 実測 (`ab3d2d992`・fl-win64 の展開 1.6 秒・load 0.2): probe 27/27 PASS・終了 0・84 秒。`pe_py203_edx_sites.py` 終了 0・23 秒、IMM 7・COPY 7・MEM 38・AMBIG 8 (60 行)。`--ablate merge`・`--ablate copy` は共に COPY 15・AMBIG 0。直接 call 60 箇所は `pe_callgraph.py callers 0x128f9e0` (60 箇所) と箇所の集合が一致。
- 本 REPORT は後続の docs commit。`git diff ab3d2d992 HEAD -- tools/python/analysis/flapi` の出力は 0 行。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1046a30 の `[rbp+0x5b8]` (経路依存・74 件書込み) と `[rbp+0x4e8]` の上流 | 0x10485aa の ecx (受入 1) | [PY-219] #3615 |
| 0x12ab520・0x12acb70・0x1021670・0x12ac210 の呼出し元 (関数ポインタ・VMT 経由)、0x12ab520 の VMT 推定の検証 | 受入 1 の rdx 2 件・eax・r9d | [PY-220] #3616 |
| 0x45c290 の戻り値の意味、0x128f9e0 の edx の MEM 38・COPY 7・AMBIG 8 の上流、0x1192f80 の `[rbp+0x140]` | 受入 1 の eax・受入 2 の残り | [PY-221] #3617 |
