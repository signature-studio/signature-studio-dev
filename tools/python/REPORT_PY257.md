# PY-257 REPORT (#3816): r8d 判定の未確認ビットの分岐先の作用

親: #2034 (PY-65)。前段: `REPORT_PY41.md` の「r8d 判定箇所」節 (ビットの意味は未確定)・`analysis/py53_dispatch.py` (逆アセンブル)・`analysis/py60_objdump_check.py` (objdump 照合)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。issue が参照する「PY-65 節」は `REPORT_PY41.md` に無いため、本 REPORT を新設した。

## 1. 結論

- 判定箇所は **173 件** (`test eax, M` の全件・`mov eax, [rbp+0x5c0]` の直後)。PY-53 の「174 件」は `and dword ptr [rbp+0x5c0], 0xffffffdf` の 1 件を含む数。
- issue の対象 13 マスク (0x4・0x10・0x14・0x10000・0x8000・0x8a1・0x240・0x200・0x1000・0x2000・0x2800・0x4000・0x3c0) は **63 件** (0x4 が 27 件・0x10 が 17 件・0x14 が 3 件・0x10000 が 7 件・残り 9 マスクが各 1 件)。
- 受入 1〜3 (立ち側と落ち側の書込み・呼出し・早期 exit の有無を VA つきで記録): **達成** (§3)。作用は §2 の「直線経路」の定義で記録する。
- 受入 4 (objdump 照合で mismatch 0): **達成**。173 判定 × 2 側 = 344 行を capstone と objdump (intel) で独立に計算し、一致 344・不一致 0 (exit 0)。負の対照 (1 箇所の `je` 先を変えた入力) では mismatch 1・exit 1 になることを確認した。
- 0x4 の落ち側 17 件 (issue の記載どおり) は、同一ブロック `0x104a9ec` に入る (30 命令・書込み 2 件 (`rbp+0x320`)・呼出し 3 件・終端 `jmp 0x104caae`)。0x10 の落ち側 1 件も同じブロックに入る。
- 対象 63 判定の全 126 側で、経路上の jcc/jmp に **早期 exit (0x104cc72 への辺) は 0 件**。
- `[rbp+0x5b8]` への書込みは対象 63 判定のうち 0x10000 (0x104a810) と 0x4 (0x104be10) の 2 判定の経路にだけ現れる (§3 の表)。
- 共通後半 0x104caae 以降で `[rbp+0x5b8]` を読む命令は 2 件 (§4)。

## 2. 測定条件・定義

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` から `block00031_PE.bin` (22,227,016 B) を展開 (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py65 --wildcards '*block00031_PE.bin'`・2.2 秒)。`work/` は gitignore。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py65/extracted/block00031_PE.bin work/py65/py53` → `fn=4664 dispatch=13 r8d_tests=174`。
- 測定: `python3 analysis/py65_r8d_bits.py work/py65/extracted/block00031_PE.bin work/py65/py53/fn.txt work/py65` → `tail_reads_5b8=0x104caec,0x104cc65`・`sites=173 rows=344 objdump_rows=344 mismatch=0`・exit 0。実時間 0.074 秒 (load average 0.06・測定直前の `uptime`)。
- 測定 commit: `a35d4a31e` (解析スクリプトを入れた commit。以後の commit は本 REPORT と DOC_MAP のみ)。`git diff a35d4a31e HEAD -- tools/python/analysis` の出力は 0 行。
- e2e: 対象外 (解析スクリプトのみ・wasm 出力に影響しない)。製品 KPI: 対象外 (起動・GUI に関わらない)。
- 判定の定義: 判定箇所の直後の分岐で両側の入口を決める。`je` は分岐先が落ち側 (M の全ビットが 0)・fall-through が立ち側。`jne` はその逆。判定 173 件のうち 171 件は `je`/`jne` (342 側)。残る 2 件 (`0x104a821` の `test eax, 0xffffffdd`・`0x104a835` の `test eax, 2` は、いずれも直後が `setne`) は jcc ではないため側を定義せず、対象外で表にも入らない。
- 「作用」の定義 (直線経路): 入口から fall-through だけで辿り、jmp・ret・共通後半 0x104caae・0x104cc72 (fall-through で入った場合) で止める。経路上の jcc の分岐先は TSV の `edges` 列に記録し、そこからは辿らない。書込み = 先頭オペランドがメモリの命令 (cmp・test・push・call・jmp・lea・ucomi* を除く)。呼出し = call 命令。早期 exit = 経路上の jcc/jmp の分岐先が 0x104cc72。
- 検算: capstone の結果 (`load` は `analysis/py64_branch_regions.py` を流用) と objdump (`-M intel`・`-b binary`) の結果を、判定箇所 (VA・mask・jcc・分岐先) と各側の (入口・命令数・終端・書込み・呼出し・辺・早期 exit) で行ごと照合した。

## 3. 対象 13 マスクの判定箇所ごとの作用

表の読み方: 各側は `入口 / 経路の命令数 / 終端 / 書込み数 (うち [rbp+0x5b8] の VA) / 呼出し数`。書込み・呼出しの VA 全件と経路上の辺は TSV (`work/py65/r8d_sites.tsv`・生成物) にある。

| 判定 | mask | jcc | 立ち: 入口 / 命令 / 終端 / 書込み ([rbp+0x5b8] の VA) / 呼出し | 落ち: 同じ |
|---|---|---|---|---|
| 0x1046dc4 | 0x8a1 | je | 0x1046dcb / 139 / jmp:0x1047062 / 13 (-) / 9 | 0x1046e05 / 126 / jmp:0x1047062 / 12 (-) / 8 |
| 0x1046dde | 0x10000 | jne | 0x1046e05 / 126 / jmp:0x1047062 / 12 (-) / 8 | 0x1046de5 / 133 / jmp:0x1047062 / 13 (-) / 9 |
| 0x1046e23 | 0x240 | je | 0x1046e2e / 120 / jmp:0x1047062 / 9 (-) / 8 | 0x1047424 / 15 / jmp:0x104c2a6 / 0 (-) / 0 |
| 0x1046e50 | 0x8000 | jne | 0x1046e6c / 107 / jmp:0x1047062 / 9 (-) / 7 | 0x1046e57 / 111 / jmp:0x1047062 / 9 (-) / 8 |
| 0x1046ef6 | 0x4000 | jne | 0x1046f28 / 65 / jmp:0x1047062 / 4 (-) / 5 | 0x1046efd / 74 / jmp:0x1047062 / 6 (-) / 5 |
| 0x1046f2e | 0x2000 | jne | 0x1046fb9 / 35 / jmp:0x1047062 / 2 (-) / 2 | 0x1046f39 / 62 / jmp:0x1047062 / 4 (-) / 5 |
| 0x104710b | 0x1000 | jne | 0x104711f / 21 / jmp:0x104718c / 1 (-) / 2 | 0x1047112 / 23 / jmp:0x104718c / 2 (-) / 2 |
| 0x10472b5 | 0x2800 | jne | 0x10472e1 / 81 / jmp:0x104c2a6 / 10 (-) / 6 | 0x10472bc / 7 / jmp:0x10472f0 / 2 (-) / 2 |
| 0x104730d | 0x200 | je | 0x1047318 / 71 / jmp:0x104c2a6 / 8 (-) / 6 | 0x1047424 / 15 / jmp:0x104c2a6 / 0 (-) / 0 |
| 0x1047515 | 0x14 | jne | 0x1047520 / 9 / jmp:0x104755d / 2 (-) / 0 | 0x104751c / 2 / jmp:0x1047522 / 0 (-) / 0 |
| 0x1047785 | 0x10 | je | 0x1047790 / 56 / jmp:0x104a9ec / 3 (-) / 6 | 0x1047851 / 22 / jmp:0x104a9ec / 1 (-) / 3 |
| 0x1047857 | 0x4 | je | 0x1047862 / 19 / jmp:0x104a9ec / 1 (-) / 3 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x10479d3 | 0x10 | je | 0x10479de / 57 / jmp:0x104a9ec / 3 (-) / 6 | 0x1047a9f / 23 / jmp:0x104a9ec / 1 (-) / 3 |
| 0x1047aa5 | 0x4 | je | 0x1047ab0 / 20 / jmp:0x104a9ec / 1 (-) / 3 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1047d08 | 0x4 | je | 0x1047d13 / 16 / jmp:0x104a9ec / 1 (-) / 3 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1047e53 | 0x4 | je | 0x1047e5e / 21 / jmp:0x104a9ec / 1 (-) / 4 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x10480c9 | 0x4 | je | 0x10480d4 / 17 / jmp:0x104a9ec / 0 (-) / 4 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x104822a | 0x10 | je | 0x1048235 / 64 / jmp:0x104a9ec / 0 (-) / 5 | 0x1048329 / 19 / jmp:0x104a9ec / 0 (-) / 1 |
| 0x1048487 | 0x10 | je | 0x1048492 / 41 / jmp:0x1048543 / 1 (-) / 1 | 0x10485c7 / 8 / jmp:0x104865b / 0 (-) / 1 |
| 0x1048661 | 0x10 | je | 0x104866c / 81 / jmp:0x104a9ec / 3 (-) / 10 | 0x1048702 / 52 / jmp:0x104a9ec / 2 (-) / 6 |
| 0x104879b | 0x4 | je | 0x10487a6 / 23 / jmp:0x104a9ec / 1 (-) / 4 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x104892f | 0x4 | je | 0x104893a / 22 / jmp:0x104a9ec / 1 (-) / 4 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1048c1e | 0x4 | je | 0x1048c29 / 16 / jmp:0x104a9ec / 0 (-) / 4 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1048d61 | 0x4 | je | 0x1048d6c / 16 / jmp:0x104a9ec / 1 (-) / 3 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1048f14 | 0x4 | je | 0x1048f1f / 16 / jmp:0x104a9ec / 1 (-) / 3 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x10490a3 | 0x4 | je | 0x10490ae / 16 / jmp:0x104a9ec / 1 (-) / 3 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1049222 | 0x4 | je | 0x104922d / 24 / jmp:0x104a9ec / 2 (-) / 4 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x104949e | 0x4 | je | 0x10494a9 / 8 / jmp:0x1049524 / 0 (-) / 0 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1049732 | 0x10 | je | 0x104973d / 7 / jmp:0x104a9ec / 0 (-) / 1 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1049892 | 0x4 | je | 0x104989d / 11 / jmp:0x104990a / 0 (-) / 0 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x1049d28 | 0x4 | je | 0x1049d33 / 8 / jmp:0x1049e2b / 0 (-) / 0 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x104a002 | 0x4 | je | 0x104a00d / 17 / jmp:0x104a9ec / 1 (-) / 3 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x104a207 | 0x10 | je | 0x104a212 / 35 / jmp:0x104a3a7 / 0 (-) / 3 | 0x104a29b / 9 / jmp:0x104a3a7 / 0 (-) / 0 |
| 0x104a5bc | 0x14 | je | 0x104a5c7 / 30 / jmp:0x104a65e / 0 (-) / 1 | 0x104a6d9 / 20 / jmp:0x104a9ec / 1 (-) / 3 |
| 0x104a6df | 0x4 | je | 0x104a6ea / 17 / jmp:0x104a9ec / 1 (-) / 3 | 0x104a9ec / 30 / jmp:0x104caae / 2 (-) / 3 |
| 0x104a810 | 0x10000 | jne | 0x104a967 / 52 / jmp:0x104caae / 6 (0x104a999,0x104a9c7) / 5 | 0x104a81b / 63 / jmp:0x104a9cd / 9 (0x104a876,0x104a8a3,0x104a95f) / 5 |
| 0x104aa54 | 0x3c0 | je | 0x104aa5f / 9 / jmp:0x104caae / 0 (-) / 3 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104ac4b | 0x10000 | je | 0x104ac52 / 15 / jmp:0x104ace3 / 1 (-) / 1 | 0x104ac9a / 16 / jmp:0x104ad34 / 2 (-) / 2 |
| 0x104ad3a | 0x14 | je | 0x104ad45 / 44 / jmp:0x104caae / 1 (-) / 4 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104ad4b | 0x10 | je | 0x104ad56 / 41 / jmp:0x104caae / 1 (-) / 4 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104aeb9 | 0x10000 | jne | 0x104aecd / 2 / jmp:0x104aed3 / 0 (-) / 0 | 0x104aec0 / 5 / jmp:0x104aed3 / 0 (-) / 0 |
| 0x104b09f | 0x10 | je | 0x104b0aa / 61 / jmp:0x104caae / 2 (-) / 6 | 0x104b17d / 22 / jmp:0x104caae / 1 (-) / 3 |
| 0x104b183 | 0x4 | je | 0x104b18e / 19 / jmp:0x104caae / 1 (-) / 3 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104b24a | 0x10000 | jne | 0x104b25e / 2 / jmp:0x104b264 / 0 (-) / 0 | 0x104b251 / 5 / jmp:0x104b264 / 0 (-) / 0 |
| 0x104b5b6 | 0x10 | je | 0x104b5c1 / 64 / jmp:0x104caae / 3 (-) / 8 | 0x104b65d / 36 / jmp:0x104caae / 1 (-) / 5 |
| 0x104b663 | 0x4 | je | 0x104b66e / 33 / jmp:0x104caae / 1 (-) / 5 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104b797 | 0x10000 | jne | 0x104b7ab / 2 / jmp:0x104b7b1 / 0 (-) / 0 | 0x104b79e / 5 / jmp:0x104b7b1 / 0 (-) / 0 |
| 0x104b95a | 0x10 | je | 0x104b965 / 22 / jmp:0x104bafb / 1 (-) / 1 | 0x104bba0 / 35 / jmp:0x104bcbd / 0 (-) / 3 |
| 0x104bba6 | 0x4 | je | 0x104bbb1 / 32 / jmp:0x104bcbd / 0 (-) / 3 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104bdb5 | 0x10000 | jne | 0x104bdc9 / 2 / jmp:0x104bdcf / 0 (-) / 0 | 0x104bdbc / 5 / jmp:0x104bdcf / 0 (-) / 0 |
| 0x104be10 | 0x4 | je | 0x104be17 / 53 / jmp:0x104c000 / 3 (0x104bebf) / 4 | 0x104be56 / 43 / jmp:0x104c000 / 3 (0x104bebf) / 2 |
| 0x104c006 | 0x10 | je | 0x104c00d / 37 / jmp:0x104c1ef / 0 (-) / 3 | 0x104c06c / 17 / jmp:0x104c1ef / 0 (-) / 0 |
| 0x104c072 | 0x4 | je | 0x104c07d / 14 / jmp:0x104c1ef / 0 (-) / 0 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104c3fc | 0x10 | je | 0x104c403 / 31 / jmp:0x104caae / 1 (-) / 5 | 0x104c423 / 25 / jmp:0x104caae / 1 (-) / 4 |
| 0x104c429 | 0x4 | je | 0x104c430 / 22 / jmp:0x104caae / 1 (-) / 4 | 0x104c48f / 6 / jmp:0x104caae / 0 (-) / 1 |
| 0x104c495 | 0x10 | je | 0x104c4a0 / 3 / jmp:0x104caae / 0 (-) / 1 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104c579 | 0x10 | je | 0x104c580 / 38 / jmp:0x104caae / 3 (-) / 5 | 0x104c5a0 / 32 / jmp:0x104caae / 3 (-) / 4 |
| 0x104c5a6 | 0x4 | je | 0x104c5b1 / 29 / jmp:0x104caae / 3 (-) / 4 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104c775 | 0x10 | je | 0x104c77c / 75 / jmp:0x104caae / 6 (-) / 12 | 0x104c79c / 69 / jmp:0x104caae / 6 (-) / 11 |
| 0x104c7a2 | 0x4 | je | 0x104c7ad / 66 / jmp:0x104caae / 6 (-) / 11 | 0x104c89b / 25 / jmp:0x104caae / 1 (-) / 4 |
| 0x104c8a1 | 0x4 | je | 0x104c8ac / 22 / jmp:0x104caae / 1 (-) / 4 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |
| 0x104c9f2 | 0x10 | je | 0x104c9f9 / 36 / tail:0x104caae / 2 (-) / 5 | 0x104ca34 / 25 / tail:0x104caae / 1 (-) / 4 |
| 0x104ca3a | 0x4 | je | 0x104ca41 / 22 / tail:0x104caae / 1 (-) / 4 | 0x104caae / 0 / tail:0x104caae / 0 (-) / 0 |

主な所見:
- 0x4 (27 件): 落ち側は 17 件が `0x104a9ec` (同一ブロック・30 命令)、7 件が `0x104caae` (共通後半に直接入る)、残り 3 件が個別の本体 (`0x104be56`・`0x104c48f`・`0x104c89b`)。立ち側は 0x104a9ec 行きが 14 件 (`0x1047862` 他)、残りは個別の本体・共通後半。
- 0x10 (17 件): 落ち側 1 件が `0x104a9ec`。0x104a9ec ブロックの書込みは `rbp+0x320` の 2 件で、`[rbp+0x5b8]` は含まない。
- 0x10000 (7 件): 判定 `0x104a810` の立ち側は書込み 6 件 (うち `[rbp+0x5b8]` が `0x104a999`・`0x104a9c7` の 2 件)、落ち側は書込み 9 件 (うち `[rbp+0x5b8]` が `0x104a876`・`0x104a8a3`・`0x104a95f` の 3 件)。他の 6 判定は経路 2〜16 命令 (`0x1046dde` は 126・133 命令) で、`[rbp+0x5b8]` への書込みを含まない。
- 0x4 の `0x104be10` (立ち・落ち): 両側とも経路上で `[rbp+0x5b8]` に `0x104bebf` で 1 回書く。
- 0x8000・0x8a1・0x240・0x200・0x1000・0x2000・0x2800・0x4000・0x3c0 (各 1 判定): 早期 exit なし。0x3c0 の落ち側は `0x104caae` に直接入る (§4)。

## 4. 共通後半 0x104caae 以降の読み

- 対象 63 判定のうち、入口または終端が共通後半 0x104caae である側は 14 側 (`0x104aa54`・`0x104ad3a`・`0x104ad4b`・`0x104b183`・`0x104b663`・`0x104bba6`・`0x104c072`・`0x104c495`・`0x104c5a6`・`0x104c8a1`・`0x104c9f2`・`0x104ca3a` など。TSV の `entry`・`end` 列)。
- 共通後半 (0x104caae〜0x104cc71・91 命令) で `[rbp+0x5b8]` を読む命令は 2 件のみ:
  - `0x104caec` `mov r9d, dword ptr [rbp+0x5b8]` (読んだ値の以後の使途は本 REPORT の範囲外)。
  - `0x104cc65` `mov eax, dword ptr [rbp+0x5b8]` → `0x104cc6b` で `[rbp+0x584]` へ書く (戻り値の経路。REPORT_PY41 の PY-60 節と一致)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 経路上の条件分岐の先 (TSV `edges` 列) と、終端 jmp の先 (`0x1047062`・`0x104a9ec`・`0x104c2a6`・`0x104c1ef` など) の 2 段目の本体 | 立ち/落ち側の 2 段目以降の書込み・呼出し・早期 exit は未確定。本表は直線経路の範囲 | #2034 (PY-65) に残す |
| `[rbp+0x5b8]` への書込み (`0x104a876`・`0x104a8a3`・`0x104a95f`・`0x104a999`・`0x104a9c7`・`0x104bebf` の 6 VA) の値の式 | 書込みの値は未確定 | #2874 (PY-99)・既存 (式の確定は本 PR の範囲外) |
| 対象外 110 判定 (0x1・0x2・0x20・0x40・0x80・0x100・0x800・0xffffffdd) | 本 REPORT の表には出さない (同じ式で TSV には出る) | 対象外 (issue の範囲外) |

## 6. 再現

```
cd tools/python
python3 analysis/py53_dispatch.py work/py65/extracted/block00031_PE.bin work/py65/py53
python3 analysis/py65_r8d_bits.py work/py65/extracted/block00031_PE.bin work/py65/py53/fn.txt work/py65
```

出力: `work/py65/r8d_sites.tsv` (判定箇所ごとに両側の行)・`work/py65/r8d_scope.md` (本 §3 の表)。
