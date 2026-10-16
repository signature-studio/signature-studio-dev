# REPORT 付録 (#5506 KH-167): Delay 要確認 14 行の CAST 単位の判定と objdump 突合

#5077 (KH-138) の残件。98 行の分類表・結論は `REPORT_APPENDIX_5077.md` が正本。本付録は、要確認 14 行を **CAST トークン単位** で見直した結果と、CAST の objdump 突合の結果だけを書く。

#### 5506-1. 結論
- 要確認 14 行のうち **4 行は、CAST トークンの命令がビット演算と確定した** (残りの数値演算は CAST ではない別トークンの命令)。`dbitcast` 規則の入力として「ビット再解釈」に分類できる。
- **残り 10 行は未確定のまま** (対応づけの誤り・CAST トークンの命令が `JA` や未特定のもの)。起票先は下の 5506-4。
- CAST の objdump 突合 (5506-3) は 107 件すべて一致。ただし、Ghidra の記録と objdump が**同じアドレスで一致する**ことしか見ていない。`252` の誤対応のような「対応する命令そのものが違う」ケースは検出できない。

#### 5506-2. 要確認 14 行の CAST 単位の判定 (入力: 5077 と同じ `tokens.tsv`・objdump の番地の読み)

| 関数 | C 行 | CAST の対象 | 機械語 (objdump で確認) | 判定 |
|---|---|---|---|---|
| 180fc4590 | 357 | `(ulonglong)dVar9` | `psrlq xmm3,0x34` (180fc467c) | ビット再解釈 (CAST 部分)。`cvtdq2pd` は CAST ではない int→double |
| 180fc4590 | 361 | `(ulonglong)dVar15` | `por xmm2,[0x182280d60]` (180fc4ac0) | ビット再解釈 (CAST 部分)。`subsd` は CAST ではない |
| 180fc4590 | 252 | `(ulonglong)dVar12` | `xor rax,rax` (180fc5b20) | **未確定** (対応づけ誤り。真の命令は未特定) |
| 180fc4590 | 363 | `(ulonglong)dVar15` | Ghidra の対応は `psubd xmm5,[0x182280e00]` (180fc4ae6)。objdump の線形逆アセンブルが 180fc4ae3 以降でずれ、この番地の命令を確定できない | **未確定** (対応づけの誤りの疑い。命令境界の再確認が必要) |
| 180fcce40 | 17 | `(ulonglong)dVar2` | CAST トークンの番地 180fcce77 は `ja` (`cmp` は 180fcce70 の隣)。CAST の命令は未確定 | **未確定** (Jcc のみ。`cmp` との対応を確認していない) |
| 180fcce40 | 44 | `(ulonglong)dVar2` | CAST トークンの番地 180fcd0f9 は `ja` (`cmp` は 180fcd0f2)。CAST の命令は未確定 | **未確定** (同上) |
| 180fcce40 | 101 | `(ulonglong)dVar4` | `vandpd xmm7,xmm1,[0x182282830]` (180fcd2f7) | ビット再解釈 (CAST 部分)。`vsubsd`/`vfmadd` は CAST ではない |
| 180fcce40 | 102 | `(ulonglong)dVar4` | 同上 (180fcd2f7) | ビット再解釈 (CAST 部分) |
| 180fc6870 | 85・91 | `(ulonglong)dVar2 >> 0x20` | Ghidra の対応は `vcvtsd2ss` (180fc6bc1)。真の命令は未確認 | **未確定** (対応づけの誤りの疑い) |
| 180fcd400 | 38 | `(ulonglong)dVar3 & 0xffffffff00000000` | Ghidra の対応は `mulsd` (180fcd5a3)。`and` の位置を未確定 | **未確定** |
| 180fcd400 | 39 | `(ulonglong)dVar3 & ...` | `and rax,rcx` (180fcd594)。マスク定数 `rcx` の値は未確認 | **未確定** (AND は bit 系だが、マスク値の確認が未了) |
| 1802ed7f0 | 296・301 | `(ulonglong)dVar29 >> 0x20` | Ghidra の対応は `divsd` / `mulsd`。REPORT 5077 の見込みは `movddup` (1802edf73・1802edf8a) | **未確定** (対応づけの誤りの疑い) |

判定の数: ビット再解釈 4 行 (357・361・101・102) / 未確定 10 行 (252・363・17・44・85・91・38・39・296・301)。

#### 5506-3. CAST の objdump 突合
- 測定: `tools/targets/kilohearts/ghidra_route/check_cast_objdump.py` (本 PR で追加)。入力は `MapLines.java` の `tokens.tsv` と `HeartCore.core_64` (repo 外)。
- 結果: 98 行の範囲の CAST トークン 107 件 = **OK 107・NG 0・NA 0** (命令のオペランドは、objdump の `[rip+…] # 0x…` を `[0x…]` に正規化して比較)。
- 前回 5077-3 の「CAST 103 件」とは件数が違う (本測定は CAST p-code かつ範囲内の `dVar` トークンの数)。どちらが正しいかは未確定。
- 注: 上の一致は「Ghidra の記録 = objdump の命令」のみ。252 の `xor rax,rax` は objdump と一致しているが誤対応である。

#### 5506-4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未確定 10 行 (252・363・17・44・85・91・38・39・296・301) の真の命令の特定 | `dbitcast` 規則に入れられない | #5506 に残す (`Refs #5506`) |
| CAST 件数 (103 と 107) の不一致 | 突合の母数が定まらない | #5506 に残す |
| 6 行のビット再解釈の判定を `dbitcast` 規則へ反映 | 規則未変更 | #3836 (受入 2) |
| Delay の 1000 trial 突合 | 規則の効果が未確認 | #3073 [KH-41] |

#### 5506-5. 環境と再現
- 素材 `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。`$RUNNER_TEMP/kh5506` で展開 (repo 外)。
- [GHIDRA] 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。Java は **17** (`openjdk 17.0.20`)。REPORT 5077 の JDK 21 とは違う。
- `DecompEach.java` 8/8 OK。`MapLines.java` で `tokens.tsv` 1,183 行 (5077 と同じ行数)。`classify_ulonglong.py` の結果は 98 行・ビット再解釈 84・要確認 14 (5077 と一致)。
