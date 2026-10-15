# REPORT 付録 (#3801 KH-65): Delay の型不一致 187 件の規則

`REPORT.md` と `REPORT_APPENDIX*.md` の行数上限のため、本付録に分けた (`docs/DOC_MAP.md` §1)。上位の経緯は `REPORT_APPENDIX_3075.md` §10-7p-3 (census の正本)。

#### 10-7x. #3801 (KH-65): Delay の型不一致 — `_DAT_<va>` グローバルの型規則 13 件 (部分・187 → 119)
- 結論: 型不一致 187 件のうち **68 件** を、整数マスクとして使われる `_DAT_<va>` グローバル 13 件の C 型規則 (`patches.py` の `GTYPE`・`ghidra_to_c.py --fix gtype`) で解消した。残り **119 件** は分類し、子 issue #3837 [KH-72] (pointer⇔整数 87 件) と #3849 [KH-73] (32 件) へ移した。Delay の型不一致 0 件は未達。Gain/Haas/Gate の `.o` は 3 本とも不変。
- 測定 commit (コードを変えた最後の commit): `bd1b7a297` (規則 `4f9eb85a9`・再現スクリプト `gtype_census.sh` の追加)。`git diff bd1b7a297 HEAD -- tools/targets/kilohearts/ghidra_route` の出力: 0 行 (本 commit 時点・本付録だけの commit)。
- 環境: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B、手展開)・`toolchain-emsdk` (emcc 6.0.12)・Ghidra 12.1.4 (zip sha256 `ddac49f9…d2db` 一致、repo 外)・JDK 21 (temurin 21.0.12.1)。すべて repo 外の `_temp` で作業。n=1。

**census (`emcc -c -ferror-limit=0`・`emcc_census.py`・排他的)**

| 測定 | 型不一致 | 合計 | 他 (レーン・引数・SIMD・未定義・未関数化・その他) |
|---|---|---|---|
| origin/main `ffb17f14d` (規則なし) | 187 | 556 | 5・191・108・46・0・0・17・187・2 (`code` 間接呼出し 0) |
| HEAD `bd1b7a297` (`--fix bitcast,intload,stackpair,assoc,concat,gtype`) | **119** | **488** | 5・191・108・46・0・0・17・119・2 |

- 注: `REPORT_APPENDIX_3075.md` の 577 件は `code` 間接呼出し 21 件を含む旧 shim (`typedef void code;`) の値。#3096 の `26b003692` (`REPORT_APPENDIX_3096.md` §10-7t) で shim を直して 556 件になり、上の origin/main 行はその値。本付録の HEAD と同じ shim で比べた。
- decompile: 151 関数 (delay lift 141 ∪ stereo lift 8 ∪ gain 1・haas 5・gate 3、昇順・10 進引数) → **151/151 OK** (`summary.tsv`、analyzeHeadless wall 32.1 s)。

**規則 13 件 (`GTYPE`)**。根拠は実機 `HeartCore.core_64` の逆アセンブル (capstone。151 関数の先頭から 6 KiB の線形逆アセンブルで、グローバルへの RIP 相対参照の命令と幅を数えた。件数は参照の数で重複あり)。

| VA | C 型 | 参照命令と幅 (件数) | PE 上の 8 byte | Ghidra の使い方 (C の式の例) |
|---|---|---|---|---|
| `182280be0` | `ulonglong` | cmp/mov qword (54) | `000000000000f07f` (0x7ff0000000000000) | `(_DAT & (ulonglong)dVar12) == _DAT` |
| `182280c10` | `ulonglong` | mov qword (18) | `ffffffffffff0f00` (0x000fffffffffffff) | `_DAT & (ulonglong)dVar9` |
| `182280c30` | `ulonglong` | and/or qword (22) | `0000000000000800` | `(… & _DAT_182280c30) != 0` |
| `182280c68` | `ulonglong` | mov qword (2) | `ffffffffffff0f00` | `_DAT >> (…) & uVar5` |
| `182280c70` | `ulonglong` | mov qword (2) | `0000000000001000` | `_DAT >> (…) & uVar5` |
| `182280ce0` | `ulonglong` | cmp/mov qword (4) | `000000000000f07f` | `_DAT \| (ulonglong)dStack_88` |
| `182281e70` | `ulonglong` | mov qword (2) | `0000000000000000` | `_DAT \| (ulonglong)dStack_88` |
| `182282780` | `ulonglong` | andpd xmm・下位 8 byte (1) | `ffffffffffffff7f` (0x7fffffffffffffff) | `(ulonglong)param_1 & _DAT` |
| `18141d060` | `ulonglong` | xorps・下位 8 byte (46 のうち) | `0000000000000080` (0x8000000000000000) | `SUB84(…) ^ _DAT` |
| `1813d1a80` | `uint` | xorps/pxor/movaps・下位 4 byte (27) | `0000008000000080` (下位 4 byte = 0x80000000) | `(uint)fVar26 ^ _DAT` |
| `181422a10` | `uint` | minps/movaps・下位 4 byte (8) | `0000803f0000803f` (下位 4 byte = 1.0f) | `_DAT & -(uint)(… == 0.0)` |
| `182280bc0` | `longlong` | cmp r10,qword (4) | `000000000000e043` | `_DAT < (longlong)(…)` |
| `182280bc8` | `longlong` | cmp r10,qword (2) | `000000000000003c` | `(longlong)(…) < _DAT` |

- 規則の置き場: 型の上書きなので ABI 表ではなく `patches.py` の `GTYPE` (型表)。`ghidra_to_c.py --fix gtype` を付けたときだけ効く (既定は OFF)。規則が使われなければ `assert` で停止する (下の NC2)。
- 限界: 幅 (4 byte か 8 byte か) は emcc では検出できない (下の NC1)。幅の根拠は上の逆アセンブル表が担う。C 本体の数値 (Delay の native 突合) は未実施 (#3073 [KH-41])。`181422a10` の `uint` は 16 byte の 1 lane の値だけを C が表す (他 lane は census の対象外)。

**ネガティブコントロール**

| 検査 | 結果 |
|---|---|
| NC0: `--fix gtype` を外す | 型不一致 187・合計 556 (規則の効果 = 68 件) |
| NC1: `182280c10` を `uint` と誤記 | 合計 488・型不一致 119 のまま (**emcc は幅の誤りを検出しない**。幅の根拠は逆アセンブル表) |
| NC2: 存在しない VA `1` を登録 | `AssertionError: gtype rule not used (global not in delay): 1` (exit 1) |

**Gain/Haas/Gate の `.o` 不変**: 旧 converter (`ffb17f14d`) と HEAD の converter で生成した C の本体 (2 行目のヘッダ comment を除く) は 3 本とも差分 0 行。`emcc -c` の `.o` は `cmp` で一致 (gain 1,435 B・haas 3,217 B・gate 3,756 B)。`gtype_census.sh` の第 2 引数で同じ比較を再現できる。

**再現**: `bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work> <旧 ghidra_route dir>` (`<work>` は repo 外。下に `win/HeartCore.core_64`・`emsdk/`・`ghidra/ghidra_12.1.4_PUBLIC/` を置く)。

**残件 119 件の分類と起票先** (HEAD `bd1b7a297`、`emcc_census.py` の「演算・代入・ポインタの型不一致」の内訳。P 番号は本付録の分類)

| 分類 | 件数 | 例 (delay.c の行) | 規則案 | 起票先 |
|---|---|---|---|---|
| P5 関数引数の pointer⇔整数 | 73 | `FUN_180fd8aac(((unsigned char*)gt_1813a3a80 + 0xee30d0), …)` | 同ビットの明示キャスト (呼出元の機械語の引数レジスタで確認) | #3837 [KH-72] |
| P6 代入の pointer⇔整数 | 14 | `param_1[1] = ((unsigned char*)gt_1813a3a80 + 0xed7778);` | 代入先の型か、キャストで揃える | #3837 [KH-72] |
| P1 関数ポインタ global | 9 | `(*_DAT_1813a1d40)(param_1, …);` | 型の割当ては未決 (PE 値は画像内の番地 0x1813e3850。実行時に設定される値の可能性) | #3849 [KH-73] |
| P3 Win API の戻り値・handle | 9 | `lVar2 = HeapAlloc(_DAT_184162a70,0,param_1);`・`GetCurrentProcess()`・`RtlPcToFileHeader`・`RtlLookupFunctionEntry` | 戻り値型の stub (意味は実装せず、到達時 abort) | #3849 [KH-73] |
| P2 void 戻り値の値扱い・double の cast | 7 | `puVar2 = (undefined8 *)FUN_180f87cac(lVar5);`・`(double)FUN_180fc4590(…)` | 呼出元の機械語 (rax) で戻り値を確認し ABI 表へ | #3849 [KH-73] |
| P4 BINOP 残件 | 7 | `(uint)fVar26 ^ _DAT_1813d1a80`・`SUB84(_DAT_182286968,0) ^ _DAT_18141d060` | `(uint)` が float のビット再解釈か数値変換かを機械語で確認。`(uint)`/`(ulonglong)` の再解釈は #3836 [KH-71] (別 run) と重なる | #3849 [KH-73] |

- 他の census 区分の起票先 (変更なし): レーン 191 = #3094 [KH-42] 系、SIMD・AVX 46 = #3095 [KH-43] 系、引数の過不足 108 = #3800 [KH-64]、未定義 identifier 17 = #3802 [KH-66]、未関数化 callee 5・その他 2 = #3802 [KH-66] 系。
- 同時期に別 run が起票した Delay の子: #3835 [KH-70] (LAB・PTR__ 17)・#3836 [KH-71] (double のビット再解釈)・#3808 [KH-67] (AVX 512bit レーン 106)・#3809 [KH-68] (混在型レーン 11)・#3821 [KH-69] (Stereo の未関数化 callee)。本付録の分類とは区分が違うため、件数は重ねていない。
