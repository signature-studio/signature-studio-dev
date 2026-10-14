# PY-159 REPORT (#3086): 65 件の書込み式の全件表と手計算表との突合

親: #2874 (PY-99)。前段: PY-88 (#2788)・PY-64 (#2033) (`REPORT_PY41_APPENDIX.md` の PY-64 / PY-88 節)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。

## 1. 結論

- 受入 1 (65 件の式・書込み VA・未確定印の表): **達成**。§3 の 65 行。読む値・書く値の数値は静的には確定しない。表の「書く値の式」が書く値で、式中の `ACC?⚠合流` (書込み前の `[rbp+0x5b8]`・分岐の合流を越える) と `SLOT[rbp+X]?` (合流を越えた frame 変数) が読む値の未確定部分。
- 受入 2 (手計算突合を PY-64 の 6 件を超えて・mismatch 0): **達成 (7 件)**。65 件のうち SLOT? を含まず VCALL でもない 7 件 (CALL 4・rint 3) を機械語から手で読み、機械スライスと一致 (mismatch 0)。PY-64 の 6 件とは別集合で、合計 13 件。残り 58 件は未照合 (§5)。ただし 7 件の一致は「`ACC?⚠合流` を ACC と同一視した式の形の一致」であり、書く値の一致ではない (ACC の値は未確定)。
- 受入 3 (ネガティブコントロールの数値): **達成**。手計算 1 件 (0x1047719 の r8d) を 1 だけ変えると mismatch=1・exit 1 (§4)。
- 機械スライスの件数は PY-88 と同じ (直接式 49・CALL 7・rint 6・VCALL 3)。ACC 合流 30 件も PY-88 と一致する。SLOT? の 55 件は PY-88 の内訳 (直接式 49・CALL 3・rint 3) の和。

## 2. 測定条件

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` の `block00031_PE.bin` (22,227,016 B)。`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py159 --wildcards '*block00031_PE.bin'` (2.8 秒) で `work/py159/extracted/` へ展開。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py159/extracted/block00031_PE.bin work/py159/py53` → `fn=4664 dispatch=13 r8d_tests=174` (0.10 秒)。入力は `work/py159/py53/fn.txt`。
- 対象: `analysis/py88_writes.py` の既定 (0x1047497・0x104aa87 の到達範囲の一意な `mov dword ptr [rbp + 0x5b8], reg` 65 件)。
- 測定 commit: `19bf08b2` (`analysis/py159_check_hand.py` に `--negctl` の値検査を入れたコード commit。ここで全測定を再実行した)。REPORT は後続 commit で書いた。`git diff 19bf08b2 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (後続 commit は REPORT・DOC_MAP・付録のみ)。
- e2e: 対象外。解析スクリプトだけの変更で wasm 出力に影響しない。素材は逆アセンブルの入力にのみ使う。

## 3. 65 件の全件表

未確定印 (`analysis/py88_writes.py` の `category`): `SLOT?` = 合流を越える frame 変数 (値は経路で異なり得る)。`ACC?⚠合流` = 書込み前の `[rbp+0x5b8]` (読む値) が分岐の合流を越える。`call で clob` = 途中の呼出しで caller-saved が壊れる。手計算突合の列の ✓ は §4 の 7 件 (一致)。

生成: `python3 analysis/py159_table.py work/py159/py53/fn.txt` (exit 0・出力 65 行)。

内訳 (未確定印ごと): 直接式 + SLOT? 29・直接式 + SLOT?,ACC?⚠合流 20・CALL + ACC?⚠合流 4・CALL + SLOT?,ACC?⚠合流 2・CALL + SLOT?,ACC?⚠合流,call で clob 1・VCALL 3・rint + ACC?⚠合流 3・rint + SLOT? 3。計 65。SLOT? を含むのは 55 件、ACC?⚠合流 を含むのは 30 件。SLOT? を含まないのは 10 件 (CALL 4・rint 3 は ACC?⚠合流 のみ・VCALL 3 は印なし)。このうち VCALL を除く 7 件が §4 の突合対象。

| # | 書込み VA | 命令 | 書く値の式 (機械スライス) | 未確定印 | 手計算突合 |
|---:|---|---|---|---|:---:|
| 1 | `0x1047719` | `mov dword ptr [rbp + 0x5b8], eax` | `CALL[0x10469f0](ecx=ACC?⚠合流@0x1046dbe, edx=0, r8d=0x3200)@0x1047714` | CALL[未知の関数] の戻り値 + 未確定: ACC?⚠合流 | ✓ |
| 2 | `0x1047779` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e0]?@0x10476f2 +4]` | 直接式 + 未確定: SLOT? |  |
| 3 | `0x1047969` | `mov dword ptr [rbp + 0x5b8], eax` | `CALL[0x10469f0](ecx=ACC?⚠合流@0x104777f, edx=0, r8d=0x3200)@0x1047964` | CALL[未知の関数] の戻り値 + 未確定: ACC?⚠合流 | ✓ |
| 4 | `0x10479c7` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4d8]?@0x1047942]` | 直接式 + 未確定: SLOT? |  |
| 5 | `0x1047c18` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x1508] +0x3b8] + rint(((f64(ACC?⚠合流@0x10479cd) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x1508] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x1508] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 6 | `0x1047c92` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4c8]?@0x1047bbe +((SLOT[rbp+0x564]?@0x104756f - 2)*4) +0xc]` | 直接式 + 未確定: SLOT? |  |
| 7 | `0x1047d98` | `mov dword ptr [rbp + 0x5b8], eax` | `CALL[0x10469f0](ecx=ACC?⚠合流@0x1047c98, edx=0xffffed40, r8d=0x12c0)@0x1047d93` | CALL[未知の関数] の戻り値 + 未確定: ACC?⚠合流 | ✓ |
| 8 | `0x1047e09` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x174]` | 直接式 + 未確定: SLOT? |  |
| 9 | `0x1047f42` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xa80] +0x3b8] + rint(((f64(ACC?⚠合流@0x1047e0f) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xa80] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xa80] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 10 | `0x1047f9c` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x180]` | 直接式 + 未確定: SLOT? |  |
| 11 | `0x104802e` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x9c0] +0x3b8] + rint(((f64(ACC?⚠合流@0x1047fa2) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x9c0] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x9c0] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 12 | `0x1048094` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x1f0]` | 直接式 + 未確定: SLOT? |  |
| 13 | `0x1048152` | `mov dword ptr [rbp + 0x5b8], eax` | `SLOT[rbp+0x5c0]?@0x1046d71` | 直接式 + 未確定: SLOT? |  |
| 14 | `0x104821e` | `mov dword ptr [rbp + 0x5b8], eax` | `M8[SLOT[rbp+0x4e8]?@0x10474d8 +0x32e]` | 直接式 + 未確定: SLOT? |  |
| 15 | `0x10483d3` | `mov dword ptr [rbp + 0x5b8], eax` | `rint((f64(ACC?⚠合流@0x1048224) * M64[G[0x104cce0]]))` | rint(xmm0) (call 0x40c660) + 未確定: ACC?⚠合流 | ✓ |
| 16 | `0x1048445` | `mov dword ptr [rbp + 0x5b8], eax` | `SLOT[rbp+0x348]?@0x1048438` | 直接式 + 未確定: SLOT? |  |
| 17 | `0x1048655` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x258]` | 直接式 + 未確定: SLOT? |  |
| 18 | `0x1048894` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xc40] +0x3b8] + rint(((f64(ACC?⚠合流@0x104865b) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xc40] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xc40] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 19 | `0x10488fa` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x2c4]` | 直接式 + 未確定: SLOT? |  |
| 20 | `0x1048a7d` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xd00] +0x3b8] + rint(((f64(ACC?⚠合流@0x1048900) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xd00] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xd00] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 21 | `0x1048ae3` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x2d0]` | 直接式 + 未確定: SLOT? |  |
| 22 | `0x1048b83` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xc48] +0x3b8] + rint(((f64(ACC?⚠合流@0x1048ae9) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xc48] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xc48] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 23 | `0x1048be9` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x21c]` | 直接式 + 未確定: SLOT? |  |
| 24 | `0x1048cea` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xe40] +0x3b8] + rint(((f64(ACC?⚠合流@0x1048bef) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xe40] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0xe40] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 25 | `0x1048d2c` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x220]` | 直接式 + 未確定: SLOT? |  |
| 26 | `0x1048e36` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x1048] +0x3b8] + rint(((f64(ACC?⚠合流@0x1048d32) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x1048] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x1048] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 27 | `0x1048ed3` | `mov dword ptr [rbp + 0x5b8], eax` | `rint(f64(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x1048] +0x3bc]))` | rint(xmm0) (call 0x40c660) + 未確定: SLOT? |  |
| 28 | `0x1048ffd` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x860] +0x3b8] + rint(((f64(ACC?⚠合流@0x1048ed9) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x860] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x860] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 29 | `0x104906e` | `mov dword ptr [rbp + 0x5b8], eax` | `rint(M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x2e4])` | rint(xmm0) (call 0x40c660) + 未確定: SLOT? |  |
| 30 | `0x1049178` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x1130] +0x3b8] + rint(((f64(ACC?⚠合流@0x1049074) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x1130] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +0x1130] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 31 | `0x10491ed` | `mov dword ptr [rbp + 0x5b8], eax` | `rint((M64[SLOT[rbp+0x4e8]?@0x10474d8 +0x324] * M64[G[0x104cce8]]))` | rint(xmm0) (call 0x40c660) + 未確定: SLOT? |  |
| 32 | `0x10493bf` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x14a8] +0x3b8] + rint(((f64(ACC?⚠合流@0x10491f3) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x14a8] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x14a8] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 33 | `0x1049469` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x460]?@0x1049365 +((SLOT[rbp+0x564]?@0x104756f - 0x10)*4)]` | 直接式 + 未確定: SLOT? |  |
| 34 | `0x104968b` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0xae8] +0x3b8] + rint(((f64(ACC?⚠合流@0x104946f) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0xae8] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0xae8] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 35 | `0x1049719` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[M64[SLOT[rbp+0x4e8]?@0x10474d8 +0x358] +(SLOT[rbp+0x580]?@0x1049632*4) +8]` | 直接式 + 未確定: SLOT? |  |
| 36 | `0x10497e2` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x418] +0x3b8] + rint(((f64(ACC?⚠合流@0x104971f) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x418] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) +0x418] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 37 | `0x104985d` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +(SLOT[rbp+0x580]?@0x10497f3*4) +0x200]` | 直接式 + 未確定: SLOT? |  |
| 38 | `0x1049b31` | `mov dword ptr [rbp + 0x5b8], eax` | `CALL[0x10469f0](ecx=ACC?⚠合流@0x1049863, edx=0, r8d=(CALL[0x7a0c20](ecx=M64[SLOT[rbp+0x520]?@0x1047556 +(SLOT[rbp+0x564]?@0x104756f*8) -0x3a8], edx=clob@0x1049b08, r8d=clob@0x1049b08)@0x1049b18 - 1))@0x1049b2c` | CALL[未知の関数] の戻り値 + 未確定: SLOT?,ACC?⚠合流,call で clob |  |
| 39 | `0x1049b7f` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[SLOT[rbp+0x530]?@0x1049ae2 +0x3b8] + rint(((f64(ACC?⚠合流@0x1049b39) * M64[G[0x104ccd8]]) * f64((M32[SLOT[rbp+0x530]?@0x1049ae2 +0x3bc] - M32[SLOT[rbp+0x530]?@0x1049ae2 +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 40 | `0x1049cbe` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x2e0]` | 直接式 + 未確定: SLOT? |  |
| 41 | `0x1049cd6` | `mov dword ptr [rbp + 0x5b8], eax` | `(M32[SLOT[rbp+0x4e8]?@0x10474d8 +0x2b4] + 2)` | 直接式 + 未確定: SLOT? |  |
| 42 | `0x1049cf3` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x4e8]?@0x10474d8 +(SLOT[rbp+0x580]?@0x1049b90*4) +0x2ac]` | 直接式 + 未確定: SLOT? |  |
| 43 | `0x1049f24` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +((SLOT[rbp+0x570]?@0x1049ea5 + 0x500)*8) -0x1378] +0x3b8] + rint(((f64(ACC?⚠合流@0x1049cf9) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +((SLOT[rbp+0x570]?@0x1049ea5 + 0x500)*8) -0x1378] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +((SLOT[rbp+0x570]?@0x1049ea5 + 0x500)*8) -0x1378] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 44 | `0x1049fb8` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[&SLOT[rbp+0x4e8]?@0x10474d8 +(shl(SLOT[rbp+0x56c]?@0x1049e9f, 2)*8) +0x1b0 +(SLOT[rbp+0x570]?@0x1049ea5*4)]` | 直接式 + 未確定: SLOT? |  |
| 45 | `0x104a13b` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[SLOT[rbp+0x520]?@0x1047556 +(((SLOT[rbp+0x564]?@0x104756f - 0x600) + 0x600)*8) -0x1ab0] +0x3b8] + rint(((f64(ACC?⚠合流@0x1049fbe) * M64[G[0x104ccd8]]) * f64((M32[M64[SLOT[rbp+0x520]?@0x1047556 +(((SLOT[rbp+0x564]?@0x104756f - 0x600) + 0x600)*8) -0x1ab0] +0x3bc] - M32[M64[SLOT[rbp+0x520]?@0x1047556 +(((SLOT[rbp+0x564]?@0x104756f - 0x600) + 0x600)*8) -0x1ab0] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 46 | `0x104a1de` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x440]?@0x104a0cf +0x30]` | 直接式 + 未確定: SLOT? |  |
| 47 | `0x104a1fb` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x438]?@0x104a0e1 +(SLOT[rbp+0x570]?@0x104a096*4) +0xd0]` | 直接式 + 未確定: SLOT? |  |
| 48 | `0x104a494` | `mov dword ptr [rbp + 0x5b8], eax` | `CALL[0x10469f0](ecx=ACC?⚠合流@0x104a201, edx=neg(M32[M64[G[0x15e44c8]] +(SLOT[rbp+0x56c]?@0x104a3f1*4)]), r8d=M32[M64[G[0x15e44c8]] +(SLOT[rbp+0x56c]?@0x104a3f1*4)])@0x104a48f` | CALL[未知の関数] の戻り値 + 未確定: SLOT?,ACC?⚠合流 |  |
| 49 | `0x104a4e2` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[SLOT[rbp+0x420]?@0x104a41f +0x3b8] + rint(((f64(ACC?⚠合流@0x104a49c) * M64[G[0x104ccd8]]) * f64((M32[SLOT[rbp+0x420]?@0x104a41f +0x3bc] - M32[SLOT[rbp+0x420]?@0x104a41f +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 50 | `0x104a5b0` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[&M64[SLOT[rbp+0x4e8]?@0x10474d8 +0x330] +(&shl(SLOT[rbp+0x56c]?@0x104a3f1, 2) +(shl(SLOT[rbp+0x56c]?@0x104a3f1, 2)*4)*8) +0x198 +(SLOT[rbp+0x570]?@0x104a3f7*4)]` | 直接式 + 未確定: SLOT? |  |
| 51 | `0x104a876` | `mov dword ptr [rbp + 0x5b8], eax` | `rint((f64(ACC?⚠合流@0x104a5b6) * M64[G[0x104cd00]]))` | rint(xmm0) (call 0x40c660) + 未確定: ACC?⚠合流 | ✓ |
| 52 | `0x104a8a3` | `mov dword ptr [rbp + 0x5b8], eax` | `VCALL[qword ptr [rax + 0x30]]@0x104a8a0` | VCALL (vtbl 呼出しの戻り値) |  |
| 53 | `0x104a95f` | `mov dword ptr [rbp + 0x5b8], eax` | `VCALL[qword ptr [rax + 0x30]]@0x104a95c` | VCALL (vtbl 呼出しの戻り値) |  |
| 54 | `0x104a999` | `mov dword ptr [rbp + 0x5b8], eax` | `rint((f64(ACC?⚠合流@0x104a967) * M64[G[0x104cd00]]))` | rint(xmm0) (call 0x40c660) + 未確定: ACC?⚠合流 | ✓ |
| 55 | `0x104a9c7` | `mov dword ptr [rbp + 0x5b8], eax` | `VCALL[qword ptr [rax + 0x30]]@0x104a9c4` | VCALL (vtbl 呼出しの戻り値) |  |
| 56 | `0x104aba9` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[M64[G[0x15e3ac8]] +(shl(SLOT[rbp+0x574]?@0x104aacd, 2)*8) +8] +0x3b8] + rint(((f64(ACC?⚠合流@0x104a9cd) * M64[G[0x104ccd8]]) * f64((M32[M64[M64[G[0x15e3ac8]] +(shl(SLOT[rbp+0x574]?@0x104aacd, 2)*8) +8] +0x3bc] - M32[M64[M64[G[0x15e3ac8]] +(shl(SLOT[rbp+0x574]?@0x104aacd, 2)*8) +8] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 57 | `0x104ad2e` | `mov dword ptr [rbp + 0x5b8], eax` | `M8[M64[&M64[G[0x15e06a0]] +(imul(SLOT[rbp+0x578]?@0x104aabe)*8) +0x134c +(SLOT[rbp+0x574]?@0x104aacd*8)] +0x148]` | 直接式 + 未確定: SLOT? |  |
| 58 | `0x104af7f` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[M64[M64[G[0x15e3ac8]] +(shl(SLOT[rbp+0x574]?@0x104aacd, 2)*8) +0x18] +0x3b8] + rint(((f64(ACC?⚠合流@0x104ad34) * M64[G[0x104ccd8]]) * f64((M32[M64[M64[G[0x15e3ac8]] +(shl(SLOT[rbp+0x574]?@0x104aacd, 2)*8) +0x18] +0x3bc] - M32[M64[M64[G[0x15e3ac8]] +(shl(SLOT[rbp+0x574]?@0x104aacd, 2)*8) +0x18] +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 59 | `0x104b093` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[M64[&M64[G[0x15e06a0]] +(imul(SLOT[rbp+0x578]?@0x104aabe)*8) +0x134c +(SLOT[rbp+0x574]?@0x104aacd*8)] +0x138]` | 直接式 + 未確定: SLOT? |  |
| 60 | `0x104b305` | `mov dword ptr [rbp + 0x5b8], eax` | `CALL[0x10469f0](ecx=ACC?⚠合流@0x104b099, edx=0, r8d=0x3e80)@0x104b300` | CALL[未知の関数] の戻り値 + 未確定: ACC?⚠合流 | ✓ |
| 61 | `0x104b5aa` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[SLOT[rbp+0x3e0]?@0x104b2de +(SLOT[rbp+0x580]?@0x104b2aa*8) +0x394]` | 直接式 + 未確定: SLOT? |  |
| 62 | `0x104b843` | `mov dword ptr [rbp + 0x5b8], eax` | `CALL[0x10469f0](ecx=ACC?⚠合流@0x104b5b0, edx=M32[&SLOT[rbp+0x5c0]?@0x104a8a9 +&G[0x1549cb4] +(SLOT[rbp+0x570]?@0x104aa97*8)], r8d=M32[&&SLOT[rbp+0x5c0]?@0x104a8a9 +&G[0x1549cb4] +&G[0x1549cb4] +(SLOT[rbp+0x570]?@0x104aa97*8)])@0x104b83e` | CALL[未知の関数] の戻り値 + 未確定: SLOT?,ACC?⚠合流 |  |
| 63 | `0x104b94e` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[&M64[G[0x15e06a0]] +(imul(SLOT[rbp+0x578]?@0x104aabe)*8) +0x384 +(SLOT[rbp+0x580]?@0x104b744*4)]` | 直接式 + 未確定: SLOT? |  |
| 64 | `0x104bebf` | `mov dword ptr [rbp + 0x5b8], ecx` | `(M32[SLOT[rbp+0x3b0]?@0x104bd61 +0x3b8] + rint(((f64(ACC?⚠合流@0x104b954) * M64[G[0x104ccd8]]) * f64((M32[SLOT[rbp+0x3b0]?@0x104bd61 +0x3bc] - M32[SLOT[rbp+0x3b0]?@0x104bd61 +0x3b8])))))` | 直接式 + 未確定: SLOT?,ACC?⚠合流 |  |
| 65 | `0x104bffa` | `mov dword ptr [rbp + 0x5b8], eax` | `M32[&&M64[G[0x15e06a0]] +(imul(SLOT[rbp+0x578]?@0x104aabe)*8) +0x1d4 +((shl(SLOT[rbp+0x568]?@0x104bd49, 4) + SLOT[rbp+0x568]?@0x104bd49)*8) +(SLOT[rbp+0x580]?@0x104be66*4)]` | 直接式 + 未確定: SLOT? |  |

## 4. 手計算突合 (7 件) とネガティブコントロール

手計算は呼出し直前の機械語を読んだ式 (`analysis/py159_check_hand.py` の HAND)。突合の規約は PY-64 と同じ (ACC?⚠合流 は ACC と同一視・+ と · は可換)。CALL は ecx/edx/r8d を別々に式木にして比較する。

| 書込み VA | 手計算の式 (読んだ箇所) | 判定 |
|---|---|---|
| 0x1047719 | `CALL[0x10469f0](ecx=ACC, edx=0, r8d=0x3200)` (0x1047706 `mov ecx,[rbp+0x5b8]`・0x104770c `xor edx,edx`・0x104770e `mov r8d,0x3200`) | 一致 |
| 0x1047969 | `CALL[0x10469f0](ecx=ACC, edx=0, r8d=0x3200)` (0x1047956・0x104795c・0x104795e) | 一致 |
| 0x1047d98 | `CALL[0x10469f0](ecx=ACC, edx=0xffffed40, r8d=0x12c0)` (0x1047d82・0x1047d88・0x1047d8d) | 一致 |
| 0x104b305 | `CALL[0x10469f0](ecx=ACC, edx=0, r8d=0x3e80)` (0x104b2f2・0x104b2f8・0x104b2fa) | 一致 |
| 0x10483d3 | `rint(f64(ACC) · *(0x104cce0))`。K は rip 相対: 0x10483c6 `mulsd` の次命令 0x10483ce + disp 0x4912 = 0x104cce0 | 一致 |
| 0x104a876 | `rint(f64(ACC) · *(0x104cd00))`。0x104a869 `mulsd` の次 0x104a871 + 0x248f = 0x104cd00 | 一致 |
| 0x104a999 | `rint(f64(ACC) · *(0x104cd00))`。0x104a98c `mulsd` の次 0x104a994 + 0x236c = 0x104cd00 | 一致 |

- 測定: `python3 analysis/py159_check_hand.py work/py159/py53/fn.txt` → `# n=7 mismatch=0`・exit 0。
- ネガティブコントロール: `python3 analysis/py159_check_hand.py work/py159/py53/fn.txt --negctl r8d` → `0x1047719: 不一致` (`r8d: hand=('num', 12801) mach=('num', 12800)`)・他 6 件は一致・`# n=7 mismatch=1`・exit 1。未知の値 (`--negctl foo`) と値なし (`--negctl`) は usage を出して exit 2 (測定: 両方 exit 2・比較は行わない)。
- 突合していない 3 件 (VCALL 0x104a8a3・0x104a95f・0x104a9c7): 呼出し先は `*(*([rbp+0x410]) + 0x30)` と手で読めるが、機械スライスは VCALL の呼出し先と引数 (edx の `[rbp+0x570]`・r8d の ACC・r9d の定数または `[rbp+0x5c0]`) を式に出さないので、突合の対象にしない。
- 回帰: PY-64 の 6 件 `python3 analysis/py64_check_expr.py work/py159/py53/fn.txt` → `n=6 mismatch=0`・exit 0 (PY-88 節と同じ)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 合流を越える frame 変数 `SLOT[rbp+X]?` を含む 55 件の経路別の式 (`[rbp+0x520]`・`[rbp+0x4e8]` などの store の先行経路ごとの値) | 受入 1 の読む値・書く値の数値が決まらない | #2874 (PY-99) |
| 書込み前の ACC の先行経路別の値 (`ACC?⚠合流` 30 件) | 同上。ACC の値は分岐入口の `[rbp+0x5b8]` に依存 | #2874 (PY-99) |
| 手計算突合の残り 58 件 (SLOT? 55 件・VCALL 3 件) | mismatch 0 は 7 件のみ。残りは機械側が式を解けていないので突合の対象外 | #2874 (PY-99) |
| VCALL 3 件 (`call qword ptr [rax + 0x30]`) の呼出し先と引数 | 3 件の式 | #2874 (PY-99) |

## 6. 再現

```
python3 analysis/py53_dispatch.py work/py159/extracted/block00031_PE.bin work/py159/py53
python3 analysis/py159_table.py work/py159/py53/fn.txt > table.md
python3 analysis/py159_check_hand.py work/py159/py53/fn.txt
python3 analysis/py159_check_hand.py work/py159/py53/fn.txt --negctl r8d   # exit 1 が正
python3 analysis/py64_check_expr.py work/py159/py53/fn.txt
```

`work/` は gitignore。素材の展開先は §2 の通り。
