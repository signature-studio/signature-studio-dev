# REPORT 付録 (#5077 KH-138): Delay `(ulonglong)dVarN` 98 行の機械語分類

#3836 (KH-71) の分割。受入 1 のみを扱う: Delay の decompile C の `(ulonglong)dVarN` 98 行を、機械語と突き合わせて「ビット再解釈」か「数値変換」かに分類する。分類は後続の `dbitcast` 規則変更 (#3836 受入 2) の入力になる。

#### 5077-1. 結論
- 98 行を機械語へ対応づけた。**93 行はビット再解釈** (機械語がビット列を整数演算・ビット論理・整数ロードで読む)。**5 行は要確認** (対応づけた機械語が、式の別の演算に属する可能性を消せない。下の表と未解決を参照)。
- **受入 1 は部分達成**。98 行すべての分類は完了していない。`Refs #5077`。
- 数値変換 (`CVT*`・`(double)(int)`) と判定した行は 0 件。`(double)(int)` は別経路 (`INT2FLOAT`) で、`(ulonglong)` の 98 行には現れない。

#### 5077-2. 環境 (repo 外。`$RUNNER_TEMP` のみ・`work/` は使わない)
- 素材 `plugins-kilohearts`: `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。
- [GHIDRA] 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921.zip`・sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。[JDK21] `temurin-21-jdk-amd64`。
- 対象 8 関数の decompile: `DecompEach.java` で **8/8 OK** (`analyzeHeadless` wall 34.2 s・load 1.29 0.77 0.33)。

#### 5077-3. 方法
1. `MapLines.java` (`tools/targets/kilohearts/scripts/ghidra/`) で、decompile の変数トークン (`dVarN`・`dStackN`) ごとに、p-code op (`ClangVariableToken.getPcodeOp()`) の seqnum から機械語 (`getInstructionAt`) を引き、C 行 → 機械語の TSV を出す。`DisassembleCommand` で対象関数を先に逆アセンブルしておく必要がある。
2. `classify_ulonglong.py` で、C 行に `(ulonglong)dVarN` を含む行を抜き、同じ行の変数トークンの機械語がビット演算 (AND/OR/XOR/CMP/SHR/MOVDDUP 等) なら「ビット再解釈」、それ以外は「要確認」とする。
3. 要確認の 5 行は `objdump -d -M intel` の前後の機械語で確認した (下の注)。

既知の制約: 対応づけは p-code op の seqnum に依存する。1 行の中に複数の演算がある場合 (外側の float 演算の命令が出る場合) は、トークンの機械語が式の別の部分になりうる。前 run の HighVariable 経由の probe (`REPORT_APPENDIX_3836.md` ⑤) と同じ問題で、本 run の p-code 経由は 98 行中 93 行で対応が得られた。

#### 5077-4. 分類表 (98 行・関数別の C 行番号)
分類 `ビット再解釈` は、同行の変数トークンが上記のビット演算に対応した行。`要確認` は対応づけた機械語の種類が決められなかった行。

| 関数 | C 行 | C の式 (抜粋) | 対応する機械語 | 分類 |
|---|---|---|---|---|
| 180fc4590 | 37 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 40 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 43 | `if ((_DAT_182280c10 & (ulonglong)dVar9 & _DAT_182280c30) != 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 50 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 53 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 59 | `if ((double)((ulonglong)_DAT_182280bd0 & (ulonglong)dVar12) != _DAT_182280bd0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 65 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 68 | `if ((_DAT_182280c10 & (ulonglong)dVar9 & _DAT_182280c30) != 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 74 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) goto code_r0x000180fc59d5;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 122 | `dVar11 = (double)((ulonglong)dVar9 & _DAT_182280c90);` | VANDPD XMM0,XMM0,xmmword ptr [0x182280c90] | ビット再解釈 |
| 180fc4590 | 171 | `FUN_180fdb6e0(dVar12,param_2,(ulonglong)dVar21 \| (ulonglong)dStack_88,_DAT_182280bac);` | CALL 0x180fdb6e0, VORPD XMM0,XMM0,xmmword ptr [RSP + 0x50] | ビット再解釈 |
| 180fc4590 | 191 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) goto code_r0x000180fc59d5;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 192 | `if ((_DAT_182280c08 & (ulonglong)dVar12) == 0) goto LAB_180fc58f0;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 194 | `if ((longlong)((ulonglong)dVar12 & _DAT_182280c08) < (longlong)_DAT_182280bf8) {` | AND R9,qword ptr [0x182280c08] | ビット再解釈 |
| 180fc4590 | 210 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R10,RAX | ビット再解釈 |
| 180fc4590 | 229 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) goto code_r0x000180fc59d5;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 244 | `if ((_DAT_182280be0 & (ulonglong)dVar12) != _DAT_182280be0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 246 | `auVar16._0_8_ = _DAT_182280c08 & (ulonglong)dVar12;` | AND RAX,RDX | ビット再解釈 |
| 180fc4590 | 250 | `if ((_DAT_182280c10 & (ulonglong)dVar12) != 0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 252 | `dVar15 = (double)((ulonglong)dVar12 \| _DAT_182280c30);` | XOR RAX,RAX | ビット再解釈 |
| 180fc4590 | 257 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R10,RAX | ビット再解釈 |
| 180fc4590 | 267 | `if (((ulonglong)dVar21 & (ulonglong)_DAT_182280bd0) != 0) {` | AND R10,qword ptr [0x182280bd0] | ビット再解釈 |
| 180fc4590 | 271 | `if (((ulonglong)dVar15 & (ulonglong)_DAT_182280bd0) != 0) {` | AND R10,qword ptr [0x182280bd0] | ビット再解釈 |
| 180fc4590 | 275 | `FUN_180fdb6e0(dVar12,param_2,(ulonglong)dVar9 \| _DAT_182280c30,_DAT_182280ba0);` | CALL 0x180fdb6e0, OR R11,qword ptr [0x182280c30] | ビット再解釈 |
| 180fc4590 | 304 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R10,R8 | ビット再解釈 |
| 180fc4590 | 313 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 316 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 319 | `if ((_DAT_182280c10 & (ulonglong)dVar9 & _DAT_182280c30) != 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 326 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 329 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 335 | `if ((double)((ulonglong)_DAT_182280bd0 & (ulonglong)dVar12) != _DAT_182280bd0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 341 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 344 | `if ((_DAT_182280c10 & (ulonglong)dVar9 & _DAT_182280c30) != 0) {` | AND R9,RAX | ビット再解釈 |
| 180fc4590 | 350 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) goto LAB_180fc4f60;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 357 | `dVar21 = (double)(int)(((ulonglong)dVar9 >> 0x34) - _DAT_182280d10);` | CVTDQ2PD XMM6,XMM3, PSRLQ XMM3,0x34 | ビット再解釈 |
| 180fc4590 | 358 | `dVar15 = (double)((ulonglong)dVar9 & (ulonglong)DAT_182280d00);` | PAND XMM2,xmmword ptr [0x182280d00] | ビット再解釈 |
| 180fc4590 | 361 | `dVar15 = (double)((ulonglong)dVar15 \| (ulonglong)_DAT_182280d60) - _DAT_182280d60;` | POR XMM2,xmmword ptr [0x182280d60], SUBSD XMM2,qword ptr [0x182280d60] | ビット再解釈 |
| 180fc4590 | 362 | `dVar12 = (double)((ulonglong)dVar15 & (ulonglong)DAT_182280d00);` | PAND XMM2,xmmword ptr [0x182280d00] | ビット再解釈 |
| 180fc4590 | 363 | `dVar21 = (double)(int)((uint)((ulonglong)dVar15 >> 0x34) - _DAT_182280e00);` | CVTDQ2PD XMM6,XMM5, PSUBD XMM5,xmmword ptr [0x182280e00] | ビット再解釈 |
| 180fc4590 | 366 | `uVar5 = ((ulonglong)dVar12 & _DAT_182280c78) + ((ulonglong)dVar12 & _DAT_182280c80) * 2;` | AND R8,qword ptr [0x182280c78], AND R9,qword ptr [0x182280c80] | ビット再解釈 |
| 180fc4590 | 368 | `dVar15 = (double)((ulonglong)dVar15 \| (ulonglong)DAT_182280d70);` | POR XMM2,xmmword ptr [0x182280d70] | ビット再解釈 |
| 180fc4590 | 406 | `dVar11 = (double)((ulonglong)dVar10 & _DAT_182280c90);` | ANDPD XMM0,xmmword ptr [0x182280c90] | ビット再解釈 |
| 180fc4590 | 456 | `FUN_180fdb6e0(dVar15,dVar12,(ulonglong)dVar21 \| (ulonglong)dStack_88,_DAT_182280bac);` | CALL 0x180fdb6e0, ORPD XMM0,xmmword ptr [RSP + 0x50] | ビット再解釈 |
| 180fc4590 | 476 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) goto LAB_180fc4f60;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 477 | `if ((_DAT_182280c08 & (ulonglong)dVar12) == 0) goto LAB_180fc4eb0;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 479 | `if ((longlong)((ulonglong)dVar12 & _DAT_182280c08) < (longlong)_DAT_182280bf8) {` | AND R9,qword ptr [0x182280c08] | ビット再解釈 |
| 180fc4590 | 495 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R10,RAX | ビット再解釈 |
| 180fc4590 | 517 | `if ((_DAT_182280be0 & (ulonglong)dVar12) == _DAT_182280be0) goto LAB_180fc4f60;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 524 | `dVar9 = (double)(_DAT_182280c08 & (ulonglong)dVar12);` | AND RAX,RDX | ビット再解釈 |
| 180fc4590 | 534 | `if ((_DAT_182280be0 & (ulonglong)dVar12) != _DAT_182280be0) goto LAB_180fc4675;` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 536 | `if ((_DAT_182280c10 & (ulonglong)dVar12) != 0) {` | AND R9,RDX | ビット再解釈 |
| 180fc4590 | 542 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R10,RAX | ビット再解釈 |
| 180fc4590 | 569 | `if ((_DAT_182280c10 & (ulonglong)dVar9) == 0) {` | AND R10,R8 | ビット再解釈 |
| 180fcce40 | 17 | `if ((ulonglong)_DAT_182282840 < (ulonglong)dVar2) {` | JA 0x180fcceff | ビット再解釈 |
| 180fcce40 | 18 | `if ((ulonglong)_DAT_1822828a0 <= (ulonglong)dVar2) {` | CMP RCX,qword ptr [0x1822828a0] | ビット再解釈 |
| 180fcce40 | 28 | `dVar2 = (double)((ulonglong)dVar2 ^ _DAT_182282770);` | XORPD XMM0,xmmword ptr [0x182282770] | ビット再解釈 |
| 180fcce40 | 32 | `if ((ulonglong)dVar2 < (ulonglong)_DAT_182282898) {` | CMP RCX,qword ptr [0x182282898] | ビット再解釈 |
| 180fcce40 | 33 | `if ((ulonglong)_DAT_182282890 <= (ulonglong)dVar2) {` | CMP RCX,qword ptr [0x182282890] | ビット再解釈 |
| 180fcce40 | 43 | `if ((ulonglong)dVar2 < (ulonglong)_DAT_182282840) {` | CMP R9,qword ptr [0x182282840] | ビット再解釈 |
| 180fcce40 | 44 | `if ((ulonglong)_DAT_1822828b0 < (ulonglong)dVar2) {` | JA 0x180fcd390 | ビット再解釈 |
| 180fcce40 | 70 | `if ((ulonglong)dVar2 < (ulonglong)_DAT_1822828a0) {` | CMP R9,qword ptr [0x1822828a0] | ビット再解釈 |
| 180fcce40 | 101 | `((param_2 - ((double)((ulonglong)dVar4 & _DAT_182282830) - dVar2)) * dVar5 +` | VANDPD XMM7,XMM1,xmmword ptr [0x182282830], VFMADD231SD XMM7,XMM4,XMM5, VSUBSD XMM4,XMM7,XMM0 | ビット再解釈 |
| 180fcce40 | 102 | `dVar5 * (double)((ulonglong)dVar4 & _DAT_182282830) + _DAT_1822828c8) + dVar5;` | VANDPD XMM7,XMM1,xmmword ptr [0x182282830], VFMADD213SD XMM7,XMM2,XMM5, VFMADD213SD XMM7,XMM5,qword ptr [0x1822828c8] | ビット再解釈 |
| 180fcce40 | 111 | `return (double)((ulonglong)dVar4 ^ (ulonglong)param_1 & _DAT_182282770);` | VXORPD XMM0,XMM0,XMM1 | ビット再解釈 |
| 180fcd690 | 21 | `if ((ulonglong)dVar2 < (ulonglong)_DAT_1822829b8) {` | CMP R10,qword ptr [0x1822829b8] | ビット再解釈 |
| 180fcd690 | 32 | `if ((ulonglong)dVar2 < (ulonglong)_DAT_1822829c0) {` | CMP R10,qword ptr [0x1822829c0] | ビット再解釈 |
| 180fcd690 | 39 | `if (0xf < (longlong)(((ulonglong)dVar2 >> 0x34) - ((ulonglong)ABS(dVar5) >> 0x34))) {` | SHR R9,0x34, SHR RCX,0x35 | ビット再解釈 |
| 180fcd690 | 47 | `if ((ulonglong)_DAT_1822829d0 <= (ulonglong)dVar2) {` | CMP R10,qword ptr [0x1822829d0] | ビット再解釈 |
| 180fcd690 | 78 | `if ((ulonglong)_DAT_1822829b8 <= (ulonglong)dVar2) {` | CMP R9,qword ptr [0x1822829b8] | ビット再解釈 |
| 180fcd690 | 79 | `if ((ulonglong)dVar2 < (ulonglong)_DAT_1822829d0) {` | CMP R9,qword ptr [0x1822829d0] | ビット再解釈 |
| 180fcd690 | 80 | `if ((ulonglong)dVar2 < (ulonglong)_DAT_1822829c8) {` | CMP R9,qword ptr [0x1822829c8] | ビット再解釈 |
| 180fcd690 | 109 | `return (double)((ulonglong)dVar2 ^ uVar1 ^ (ulonglong)param_1 & _DAT_182282950);` | VXORPD XMM0,XMM0,XMM3 | ビット再解釈 |
| 180fce0d0 | 52 | `return (double)((ulonglong)dVar4 ^ uVar1);` | VXORPD XMM0,XMM0,XMM3 | ビット再解釈 |
| 180fce0d0 | 70 | `if ((ulonglong)_DAT_182282af8 <= (ulonglong)dVar2) {` | CMP R10,qword ptr [0x182282af8] | ビット再解釈 |
| 180fce0d0 | 71 | `if ((ulonglong)dVar2 < (ulonglong)_DAT_182282b00) {` | CMP R10,qword ptr [0x182282b00] | ビット再解釈 |
| 180fce0d0 | 78 | `if (0xf < (longlong)(((ulonglong)dVar2 >> 0x34) - ((ulonglong)ABS(dVar4) >> 0x34))) {` | SHR R9,0x34, SHR RCX,0x35 | ビット再解釈 |
| 180fce0d0 | 86 | `if ((ulonglong)_DAT_182282b18 <= (ulonglong)dVar2) {` | CMP R10,qword ptr [0x182282b18] | ビット再解釈 |
| 180fce0d0 | 114 | `if ((ulonglong)_DAT_182282af0 <= (ulonglong)dVar2) {` | CMP R10,qword ptr [0x182282af0] | ビット再解釈 |
| 180fce0d0 | 123 | `if ((ulonglong)_DAT_182282ae8 <= (ulonglong)dVar2) {` | CMP R10,qword ptr [0x182282ae8] | ビット再解釈 |
| 180fc6d70 | 59 | `(int)((double)((ulonglong)dVar23 & _DAT_1822822c0) * _DAT_182282300 + _DAT_1822822f0);` | VANDPD XMM1,XMM0,xmmword ptr [0x1822822c0] | ビット再解釈 |
| 180fc6d70 | 70 | `uVar20 = ((ulonglong)dVar23 >> 0x34) - 0x3ff;` | SHR R11,0x34 | ビット再解釈 |
| 180fc6d70 | 72 | `uVar12 = (ulonglong)dVar23 & 0xfffffffffffff \| 0x10000000000000;` | SHR RCX,0xc | ビット再解釈 |
| 180fc6d70 | 147 | `(double)(~(ulonglong)dVar16 & _DAT_1822822b0 ^` | VANDNPD XMM1,XMM5,xmmword ptr [0x1822822b0] | ビット再解釈 |
| 180fc6d70 | 148 | `(ulonglong)dVar23 ^` | VXORPD XMM0,XMM0,XMM3 | ビット再解釈 |
| 180fc6d70 | 200 | `if ((ulonglong)dVar16 < (ulonglong)_DAT_1822823c8) {` | CMP R10,qword ptr [0x1822823c8] | ビット再解釈 |
| 180fc6d70 | 209 | `if (0xf < (longlong)(((ulonglong)dVar16 >> 0x34) - uVar11)) {` | SHR R9,0x34 | ビット再解釈 |
| 180fc6870 | 44 | `(int)((double)((ulonglong)dVar14 & _DAT_182282240) * _DAT_1822821b0 + _DAT_1822821a0);` | VANDPD XMM1,XMM0,xmmword ptr [0x182282240] | ビット再解釈 |
| 180fc6870 | 75 | `auVar5._0_8_ = (double)((ulonglong)dVar2 ^ (uVar1 + 1 >> 1) << 0x3f);` | VXORPD XMM0,XMM0,XMM3 | ビット再解釈 |
| 180fc6870 | 85 | `return CONCAT44((int)((ulonglong)dVar2 >> 0x20),(float)dVar2);` | VCVTSD2SS XMM0,XMM0,XMM0 | 要確認 |
| 180fc6870 | 91 | `return CONCAT44((int)((ulonglong)dVar2 >> 0x20),(float)dVar2);` | VCVTSD2SS XMM0,XMM0,XMM0 | 要確認 |
| 180fc6870 | 102 | `else if ((ulonglong)dVar2 < (ulonglong)_DAT_182282220) {` | CMP R10,qword ptr [0x182282220] | ビット再解釈 |
| 180fc6870 | 111 | `if (0xf < (longlong)(((ulonglong)dVar2 >> 0x34) - uVar1)) {` | SHR R9,0x34 | ビット再解釈 |
| 180fcd400 | 38 | `return ((double)((ulonglong)dVar3 & 0xffffffff00000000) * dVar2 + _DAT_1822828c8 +` | MULSD XMM0,XMM3 | 要確認 |
| 180fcd400 | 39 | `(param_2 - (dVar2 - param_1)) * (double)((ulonglong)dVar3 & 0xffffffff00000000)) * dVar3` | AND RAX,RCX, MULSD XMM0,XMM4, SUBSD XMM1,XMM6 | ビット再解釈 |
| 180fcd400 | 40 | `+ (double)((ulonglong)dVar3 & 0xffffffff00000000);` | AND RAX,RCX | ビット再解釈 |
| 1802ed7f0 | 292 | `auStack_118._12_4_ = (int)((ulonglong)dVar29 >> 0x20);` | MOVDDUP XMM3,XMM2 | ビット再解釈 |
| 1802ed7f0 | 296 | `auStack_128._12_4_ = (int)((ulonglong)dVar29 >> 0x20);` | DIVSD XMM3,XMM2 | 要確認 |
| 1802ed7f0 | 301 | `auStack_138._12_4_ = (int)((ulonglong)dVar29 >> 0x20);` | MULSD XMM3,XMM0 | 要確認 |

注 (要確認 5 行)
- `180fc6870` 85・91: `return CONCAT44((int)((ulonglong)dVar2 >> 0x20),(float)dVar2)`。`(ulonglong)dVar2 >> 0x20` は上位 32 bit の読出しで、同関数の `movq rdx,xmm0` (`180fc68a1`) が bit 転送に当たる。対応づけた `VCVTSD2SS` は外側の `(float)dVar2` の命令で、`>> 0x20` の命令とは別。
- `180fcd400` 38: `((double)((ulonglong)dVar3 & 0xffffffff00000000) * dVar2 …`。`& 0xffffffff00000000` の機械語は、対応づけた `MULSD` ではなく式の AND に当たるはずだが、同行の AND の命令を確定できなかった。
- `1802ed7f0` 296・301: `auStack_128._12_4_ = (int)((ulonglong)dVar29 >> 0x20)`。対応づけた `DIVSD`・`MULSD` は外側の式。上位 32 bit の読出しは `MOVDDUP` (`1802edf73`・`1802edf8a`) に続く store に見えるが、読出し命令を 1 対 1 で確定していない。

#### 5077-5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 98 行のうち要確認 5 行 (上の注) の機械語の確定 | 規則の正しさの根拠が 5 行分不足。5 行とも数値変換と判定した根拠は無く、ビット再解釈の見込みが高いが未確定 | #5077 に残す (`Refs #5077`・次 run で `objdump` の逆アセンブルと突合して確定) |
| 対応づけの方法 (p-code seqnum 経由) の 98 行全体の検証 | 93 行の対応の正しさは機械語との目視一致で確認したが、全 98 行の独立な二重確認は未実施 | #5077 に残す |
| `dbitcast` 規則の適用と Delay の 1000 trial 突合 | 分類結果を規則に反映していない | #3836 (受入 2) と #3073 [KH-41] |

#### 5077-6. 検証
- 測定 commit: 本 PR の最後のコード変更 commit (下のコミット hash)。`classify_ulonglong.py` を commit 済み HEAD のツリーから実行し、98 行・93/5 の内訳を再現した (出力は下の再現コマンド)。
- 再現手順: (1) 上記 `DecompEach` (8 関数) → `out/<va>.c`、(2) `MapLines.java` (`-postScript MapLines.java <dir> <va…>`) → `tokens.tsv`、(3) `python3 tools/targets/kilohearts/ghidra_route/classify_ulonglong.py tokens.tsv out` で表を出す。
