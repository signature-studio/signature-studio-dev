# REPORT 付録 (#5506 KH-167): Delay 要確認 14 行の CAST 単位の判定と objdump 突合

#5077 (KH-138) の残件。98 行の分類表・結論は `REPORT_APPENDIX_5077.md` が正本。本付録は、要確認 14 行を **CAST トークン単位** で見直した結果と、CAST の objdump 突合の結果だけを書く。

#### 5506-1. 結論
- 要確認 14 行のうち **7 行は、CAST の機械語が C 式のビット操作と一致して「ビット再解釈」と確定した** (357・361・363・101・102・38・39)。`dbitcast` 規則の入力として使える。
- 363 行は、CAST の `>> 0x34` の命令が `psrlq xmm5,0x34` (180fc4ae1) と確定した。`psubd` (180fc4ae6) は後段の整数減算 `(uint)(… ) - _DAT_182280e00` で、CAST ではない。前 run の「`PSUBD` と確定」は誤りだった。
- 38 行は、C の `& 0xffffffff00000000` が `and rax,rcx` (180fcd57c) に対応し、マスクの値 (`movabs rcx,0xffffffff00000000` 180fcd565) を確認した。`mulsd` は後段の積。ビット操作と確定。
- 17・44 行は、CAST の位置が `cmp` の比較対象 (`btr rcx,0x3f` で符号を外した値との整数比較)。`ja` ではなく比較の入力側。ビット操作 (符号除去) を経た値の比較の入力側と読める。浮動小数点の数値演算かどうかは判定を保留 (注参照)。
- 252 行の `dVar12` の対応先 `xor rax,rax` (180fc5b20) は誤対応。C は `(double)((ulonglong)dVar12 | _DAT_182280c30)` で、定数 `0x182280c30` を `or` する命令は範囲内に複数ある (180fc4cfd 等)。本 run では対応する 1 箇所を確定できなかった。未確定。
- 85・91・296・301 行は、C の `>> 0x20` に対応する shift 命令が範囲内 (`shr`/`psrlq` で 0x20) に見当たらない。Ghidra の対応先 (`vcvtsd2ss` 180fc6bc1・`divsd` 1802edf6f・`mulsd` 1802edf7d) は、objdump 上の命令と一致するが、CAST の真の命令ではない疑いが強い。未確定。
- CAST の objdump 突合 (5506-3) は 107 件すべて一致 (`check_cast_objdump.py`)。ただし、Ghidra の記録と objdump が**同じアドレスで一致する**ことしか見ていない。上記の 363 行・252 行のような「対応づけは一致するが命令の意味が違う」ケースは検出できない。

#### 5506-2. 要確認 14 行の CAST 単位の判定 (入力: 5077 と同じ `tokens.tsv`・objdump の番地の読み)

| 関数 | C 行 | CAST の対象 | 機械語 (objdump で確認) | 判定 |
|---|---|---|---|---|
| 180fc4590 | 357 | `(ulonglong)dVar9` | `psrlq xmm3,0x34` (180fc467c) | ビット再解釈 (CAST 部分)。`cvtdq2pd` は CAST ではない int→double |
| 180fc4590 | 361 | `(ulonglong)dVar15` | `por xmm2,[0x182280d60]` (180fc4ac0) | ビット再解釈 (CAST 部分)。`subsd` は CAST ではない |
| 180fc4590 | 252 | `(ulonglong)dVar12` | 対応先 `xor rax,rax` (180fc5b20) は誤対応。`or` の定数 `0x182280c30` を参照する命令群 (180fc4cfd 等) に対応がある | **未確定** |
| 180fc4590 | 363 | `(ulonglong)dVar15 >> 0x34` | CAST の命令は `psrlq xmm5,0x34` (180fc4ae1)。`psubd xmm5,[0x182280e00]` (180fc4ae6) は後段の整数減算 `(uint)(…) - _DAT_182280e00` | **ビット再解釈** (CAST 部分。前 run の `PSUBD` 確定は誤り) |
| 180fcce40 | 17 | `(ulonglong)dVar2` | `btr rcx,0x3f` (180fcce6b) で符号を外した値と `cmp rcx,[0x182282840]` (180fcce70) の比較。CAST はこの比較の入力側 | 未確定 (ビット操作後の整数比較の入力側と読めるが、分類規則の確定は保留) |
| 180fcce40 | 44 | `(ulonglong)dVar2` | 同上 (180fcd0f2 の `cmp` 系) | 未確定 (同上) |
| 180fcce40 | 101 | `(ulonglong)dVar4` | `vandpd xmm7,xmm1,[0x182282830]` (180fcd2f7) | ビット再解釈 (CAST 部分)。`vsubsd`/`vfmadd` は CAST ではない |
| 180fcce40 | 102 | `(ulonglong)dVar4` | 同上 (180fcd2f7) | ビット再解釈 (CAST 部分) |
| 180fc6870 | 85・91 | `(ulonglong)dVar2 >> 0x20` | Ghidra の対応 `vcvtsd2ss` (180fc6bc1)。範囲内に `>> 0x20` の shift 命令が見当たらない | **未確定** (対応づけの誤りの疑い) |
| 180fcd400 | 38 | `(ulonglong)dVar3 & 0xffffffff00000000` | `and rax,rcx` (180fcd57c)。`rcx = 0xffffffff00000000` (180fcd565) | **ビット再解釈** (AND のマスク。Ghidra の `mulsd` (180fcd5a3) は後段の積) |
| 180fcd400 | 39 | `(ulonglong)dVar3 & 0xffffffff00000000` | `and rax,rcx` (180fcd594)。`rcx` は 180fcd565 で同じマスク値 | **ビット再解釈** (AND) |
| 1802ed7f0 | 296・301 | `(ulonglong)dVar29 >> 0x20` | Ghidra の対応 `divsd` (1802edf6f) / `mulsd` (1802edf7d)。範囲内に `>> 0x20` の shift 命令が見当たらない | **未確定** (対応づけの誤りの疑い) |

判定の数: ビット再解釈 7 行 (357・361・363・101・102・38・39) / 未確定 7 行 (252・17・44・85・91・296・301)。計 14 行。

注: 17・44 行は、CAST の比較対象を確定しただけで、規則上は「ビット再解釈」とも「数値変換」とも断定しない。分類は未確定のまま残す。

#### 5506-3. CAST の objdump 突合
- 測定: `tools/targets/kilohearts/ghidra_route/check_cast_objdump.py`。入力は `MapLines.java` の `tokens.tsv` と `HeartCore.core_64` (repo 外)。
- 結果: 98 行の範囲の CAST トークン 107 件 = **OK 107・NG 0・NA 0** (命令のオペランドは、objdump の `[rip+…] # 0x…` を `[0x…]` に正規化して比較)。
- 関数別件数: 180fc4590 61・180fcce40 12・180fc6870 6・180fc6d70 7・180fcd690 8・180fce0d0 7・180fcd400 3・1802ed7f0 3 (計 107)。
- 前回 5077-3 の「CAST 103 件」とは件数が違う (本測定は CAST p-code かつ範囲内の `dVar` トークンの数)。どちらが正しいかは未確定。
- 注: 上の 107 件 OK は「Ghidra の記録 = objdump の命令」のみを示す。363 行 (`psubd` の対応) と 252 行 (`xor` の誤対応) は、いずれも objdump と一致して OK になるが、意味は誤っている。

#### 5506-4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未確定 7 行 (252・17・44・85・91・296・301) の真の命令の特定 | `dbitcast` 規則に入れられない | #5506 に残す (`Refs #5506`) |
| CAST 件数 (103 と 107) の不一致 | 突合の母数が定まらない | #5506 に残す |
| ビット再解釈 7 行の `dbitcast` 規則への反映 | 規則未変更 | #3836 (受入 2) |
| Delay の 1000 trial 突合 | 規則の効果が未確認 | #3073 [KH-41] |

#### 5506-5. 環境と再現
- 素材 `plugins-kilohearts` (`docs/REFERENCES.md` の `plugins-kilohearts` 行。取得は `docs/WORKFLOW.md` §11・7.6 GB) → `Kilohearts Offline Installer.zip` → `payload.dat` (7z で `windows.zip/1ccb1df8c8f10745` だけ抽出) → `HeartCore.core_64` (76,642,304 B)。展開先は `$RUNNER_TEMP/kh5506` (repo 外)。
- [GHIDRA] 12.1.4 = GitHub release `Ghidra_12.1.4_build` の `ghidra_12.1.4_PUBLIC_20260921.zip` (sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。JDK 21 (`temurin-21-jdk-amd64`)。
- 手順: `DecompEach.java` で 8 関数 (`out/*.c`)、`MapLines.java` で `tokens.tsv` 1,183 行、`check_cast_objdump.py` で突合 (`ok=107 ng=0 na=0`)。wall: DecompEach 35.7 s。
- 本付録の判定 (5506-2) は、上記の tokens と objdump の番地の読みに基づく。判定の根拠は表の各行の機械語。
