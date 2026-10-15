# REPORT 付録 (#3801 KH-65): Delay の型不一致 187 件の規則

`REPORT.md` と `REPORT_APPENDIX*.md` の行数上限のため、本付録に分けた (`docs/DOC_MAP.md` §1)。上位の経緯は `REPORT_APPENDIX_3075.md` §10-7p-3 (census の正本)。

#### 10-7x. #3801 (KH-65): Delay の型不一致 — `_DAT_<va>` グローバルの型規則 13 件 (部分・187 → 119)
- 結論: 型不一致 187 件のうち **68 件** を、整数マスクとして使われる `_DAT_<va>` グローバル 13 件の C 型規則 (`patches.py` の `GTYPE`・`ghidra_to_c.py --fix gtype`) で解消した。残り **119 件** は分類し、子 issue #3837 [KH-72] (pointer⇔整数 87 件) と #3849 [KH-80] (32 件) へ移した。Delay の型不一致 0 件は未達。Gain/Haas/Gate の `.o` は 3 本とも不変。
- 測定 commit (コードを変えた最後の commit): `fe5fa8215` (2 回目の main 取り込みの merge)。規則 `4f9eb85a9`・再現スクリプト `gtype_census.sh` は `bd1b7a297` で追加し、`patches.py` のコメント 1 行 (`182280c30` の `0x800` → `0x0008000000000000 (bit 51)`) は `981efaa44` で直した。`git diff fe5fa8215 HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins tools/targets/kilohearts/scripts` の出力は 2 ファイル: `ghidra_to_c.py` の docstring 1 行 (`gtype` 行の字下げ 5 → 4 空白) と、`gtype_census.sh` (FX を環境変数で上書きできるようにした・既定値は不変、ヘッダに基点・併用の実行例を追記)。docstring を除く `ast.dump` が `fe5fa8215` と一致し、既定の FX も変わらないため、census の入力は変わらない。
- 環境: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B、手展開)・`toolchain-emsdk` (emcc 6.0.12)・Ghidra 12.1.4 (zip sha256 `ddac49f9…d2db` 一致、repo 外)・JDK 21 (temurin 21.0.12.1)。すべて repo 外の `_temp` で作業。n=1。

- **main 取り込み後の再測定 (測定 commit `fe5fa8215`)**: `origin/main` を 2 回取り込んだ (`079067e79`、その後 `b201ce387`。2 回目は #3852 (#3802) が `ghidra_to_c.py` を変えた)。1 回目の競合は `ghidra_to_c.py` の `--fix` 説明文の 1 箇所だけで、`gtype` と `lanes` (#3094) の両行を残した (コード側は独立)。2 回目は競合なし。測定 commit (コードを変えた最後の commit): `fe5fa8215` (merge)。`git diff bd1b7a297 fe5fa8215 -- tools/targets/kilohearts/ghidra_route --stat` は `3 files changed, 129 insertions(+), 8 deletions(-)` (main 側の変更を含む)。取り込み前 (`bd1b7a297`) の『再測定は不要』は、この main 側の変更で成り立たなくなった (`bd1b7a297` 時点の census は下の表で『取り込み前』と明記)。`fe5fa8215` 以降の `ghidra_route`・`snapins`・`scripts` の差分は docstring 1 行と census スクリプトの環境変数化だけ (既定の変換は不変。上の『測定 commit』の行)。
- 再測定 (`gtype_census.sh <work> <origin/main の ghidra_route>`・HEAD `fe5fa8215`・decompile 151/151 OK)。main 単独 (`--fix` に gtype・lanes なし) は 529 → 507。#3852 で未定義 identifier 17 → 2・未関数化 callee 5 → 0・その他 2 → 0 (main 側の変更で、本 PR の差分ではない)。

| 測定 (`emcc -c` の error 行を `emcc_census.py` で分類) | `gtype_census.sh` の FX (環境変数) | 型不一致 | 合計 |
|---|---|---|---|
| 規則なし・基点 (`b201ce387` の converter と同じ。gtype 分岐だけが差) | `FX=bitcast,intload,stackpair,assoc,concat` | 187 | 507 |
| HEAD `fe5fa8215` (gtype 単独・既定) | 未指定 (`…,concat,gtype`) | **119** | **439** |
| HEAD `fe5fa8215` (gtype・lanes 併用) | `FX=bitcast,intload,stackpair,assoc,concat,gtype,lanes` | 119 | 418 |
| 規則なし・lanes のみ | `FX=bitcast,intload,stackpair,assoc,concat,lanes` | 187 | 486 |

- 再現: 各行は `FX=<上の列> bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>` の `delay emcc error 行` と census 出力 (`<work>` は repo 外)。上の表の数値は作者の実測 (`fe5fa8215`)。本 run では Ghidra と素材の展開をしていないため、再実行はしていない。
- 基点行の converter は PR の `ghidra_to_c.py` で、`b201ce387` からの差分は gtype 分岐 (`if 'gtype' in fixes:`) と docstring 1 行だけ (`git diff b201ce387 HEAD -- …/ghidra_to_c.py`)。gtype を外せば `b201ce387` と同じ規則になる。

- 併用の確認: gtype の効果 (型不一致 187 → 119 = 68 件) と lanes の効果 (レーン 191 → 170 = 21 件) は、同じ `delay.c` で両方有効にしたときも独立に出る。Gain/Haas/Gate の `.o` は HEAD `fe5fa8215` で旧規則と `cmp` 一致 (gain 1,435 B・haas 3,217 B・gate 3,756 B)。

**census・取り込み前の値 (`bd1b7a297` 時点・未再測定。現行の値は上の表)** (`emcc -c -ferror-limit=0`・`emcc_census.py`・排他的)

| 測定 | 型不一致 | 合計 | 他 (レーン・引数・SIMD・未定義・未関数化・その他) |
|---|---|---|---|
| origin/main `ffb17f14d` (規則なし) | 187 | 556 | 5・191・108・46・0・0・17・187・2 (`code` 間接呼出し 0) |
| HEAD `bd1b7a297` (`--fix bitcast,intload,stackpair,assoc,concat,gtype`) | **119** | **488** | 5・191・108・46・0・0・17・119・2 |

- 注: `REPORT_APPENDIX_3075.md` の 577 件は `code` 間接呼出し 21 件を含む旧 shim (`typedef void code;`) の値。#3096 の `26b003692` (`REPORT_APPENDIX_3096.md` §10-7t) で shim を直して 556 件になり、上の origin/main 行はその値。本付録の HEAD と同じ shim で比べた。
- decompile: 151 関数 (起点の式の内訳: delay・stereo の lift 一意 142 + gain・haas・gate の 9 VA、昇順・10 進引数) → **151/151 OK** (`summary.tsv`、analyzeHeadless wall 32.1 s)。

**規則 13 件 (`GTYPE`)**。下の表の件数はすべて **151 関数の窓内の件数 (重複除去後)**。根拠は実機 `HeartCore.core_64` の逆アセンブル (初版は capstone、件数の再計数は objdump)。件数の集計: 単位 = グローバルを RIP 相対で参照する命令 (命令アドレスで重複除去)・分母 = 起点 151 関数 (`snapins/snapins.json` の delay・stereo の lift 値 + `gtype_census.sh` の gain/haas/gate の 9 VA) それぞれの先頭から 0x1800 バイトの窓・除外 = 窓の外の命令。再計数コマンド: `for s in <起点>; do objdump -d -M intel --no-show-raw-insn --start-address=$s --stop-address=$((s+0x1800)) HeartCore.core_64; done | grep -E '^ +[0-9a-f]+:.*# 0x(182280be0|182280c10|182280c30|182280c68|182280c70|182280ce0|182281e70|182282780|18141d060|1813d1a80|181422a10|182280bc0|182280bc8)$' | sort -u | grep -oE '# 0x[0-9a-f]+$' | sort | uniq -c`。初版の『件数は参照の数で重複あり』は窓ごとの和で、`1813d1a80` は 27・`18141d060` は 46 だった (同じ命令が複数の関数の窓に入るため)。重複除去の値は `1813d1a80` 11・`18141d060` 14 (xorps 12・movsd 2)。他の 11 行は窓の和と重複除去が一致した。起点 151 の生成 (`gtype_census.sh` の VAS と同じ式。出力は件数 `151`・窓の計数に渡す列は `print(*sorted(s))`): `python3 -c "import json;d=json.load(open('tools/targets/kilohearts/snapins/snapins.json'));s={int(v,16) for k in ['delay','stereo'] for v in d[k]['lift'].values() if isinstance(v,str)}|{int(x,16) for x in ['0x1804b0380','0x1804d0280','0x1804d0180','0x1804cff00','0x1804cff90','0x1804d0720','0x1804c2f50','0x180295f20','0x180020e70']};print(len(s))"`。

| VA | C 型 | 参照命令と幅 (件数) | PE 上の 8 byte (メモリ順の 16 進) | Ghidra の使い方 (C の式の例) |
|---|---|---|---|---|
| `182280be0` | `ulonglong` | cmp/mov qword (54) | `000000000000f07f` (0x7ff0000000000000) | `(_DAT & (ulonglong)dVar12) == _DAT` |
| `182280c10` | `ulonglong` | mov qword (18) | `ffffffffffff0f00` (0x000fffffffffffff) | `_DAT & (ulonglong)dVar9` |
| `182280c30` | `ulonglong` | and/or qword (22) | `0000000000000800` | `(… & _DAT_182280c30) != 0` |
| `182280c68` | `ulonglong` | mov qword (2) | `ffffffffffff0f00` | `_DAT >> (…) & uVar5` |
| `182280c70` | `ulonglong` | mov qword (2) | `0000000000001000` | `_DAT >> (…) & uVar5` |
| `182280ce0` | `ulonglong` | cmp/mov qword (4) | `000000000000f07f` | `_DAT \| (ulonglong)dStack_88` |
| `182281e70` | `ulonglong` | mov qword (2) | `0000000000000000` | `_DAT \| (ulonglong)dStack_88` |
| `182282780` | `ulonglong` | andpd xmm・下位 8 byte (1) | `ffffffffffffff7f` (0x7fffffffffffffff) | `(ulonglong)param_1 & _DAT` |
| `18141d060` | `ulonglong` | xorps・movsd・下位 8 byte (14: xorps 12・movsd 2) | `0000000000000080` (0x8000000000000000) | `SUB84(…) ^ _DAT` |
| `1813d1a80` | `uint` | xorps/pxor/movaps・下位 4 byte (11) | `0000008000000080` (下位 4 byte = 0x80000000) | `(uint)fVar26 ^ _DAT` |
| `181422a10` | `uint` | minps/movaps・下位 4 byte (8) | `0000803f0000803f` (下位 4 byte = 1.0f) | `_DAT & -(uint)(… == 0.0)` |
| `182280bc0` | `longlong` | cmp r10,qword (4) | `000000000000e043` | `_DAT < (longlong)(…)` |
| `182280bc8` | `longlong` | cmp r10,qword (2) | `000000000000003c` | `(longlong)(…) < _DAT` |

- 規則の置き場: 型の上書きなので ABI 表ではなく `patches.py` の `GTYPE` (型表)。`ghidra_to_c.py --fix gtype` を付けたときだけ効く (既定は OFF)。規則が使われなければ `assert` で停止する (下の NC2)。
- 限界: 幅 (4 byte か 8 byte か) は emcc では検出できない (下の NC1)。幅の根拠は上の逆アセンブル表が担う。C 本体の数値 (Delay の native 突合) は未実施 (#3073 [KH-41])。`181422a10` の `uint` は 16 byte の 1 lane の値だけを C が表す (他 lane は census の対象外)。`181422a10` の 8 件 = delay 4 + gate 4。『整数マスク』と言える範囲は、delay 関数の 6 KiB 窓内の 4 参照 (`andps`・ビット演算) だけ。窓の外の delay 参照は未確認。gate 側の 4 参照は float 算術 (`look`・検収で確認) で、gate は GTYPE の対象外 (gate.c は不変)。残りの範囲の確認は #3849 で規則を決めるときに行う。

**ネガティブコントロール (現行の再測定・測定 commit `fe5fa8215`・census 入力は HEAD と同じ)**。素材: `plugins-kilohearts` → Installer zip → payload.dat → windows.zip/1ccb1df8c8f10745 → `HeartCore.core_64` (76,642,304 B)。Ghidra 12.1.4 は `docs/REFERENCES.md` の取得元 (`ghidra_12.1.4_PUBLIC_20260921.zip`・sha256 `ddac49f9…d2db` 一致) から取得。JDK 21 (`temurin-21`) で実行。デコンパイル 151/151 OK。各検査は `ghidra_route/` を複製した作業コピーで行い、repo 内のファイルは変えていない。

| 検査 | 結果 (現行・`fe5fa8215` の census 入力) |
|---|---|
| 基準 (NC0 相当): `FX=bitcast,intload,stackpair,assoc,concat` (`--fix gtype` を外す) | 合計 **507**・型不一致 **187** (`delay` の `emcc` error 行 507) |
| 正の基準: `FX=…,gtype` (規則あり) | 合計 **439**・型不一致 **119** (規則の効果 = 68 件) |
| NC1: `182280c10` を `uint` と誤記 | 合計 **439**・型不一致 **119** (件数は正の基準と同じ。`delay.c` の内容は正の基準と異なる (`diff` で差あり)。**emcc は幅の誤りを検出しない**。幅の根拠は逆アセンブル表) |
| NC2: 存在しない VA `1` を登録 | `AssertionError: gtype rule not used (global not in delay): 1` (exit **1**) |

- 基点 census の再現: 現行の `gtype_census.sh` は `$HERE` (作業ツリーの `ghidra_route`) 固定で、第 2 引数は `.o` 比較にしか使わない。よって基点 (規則なし) は『`FX` から `gtype` を外す』行で、作業ツリーの `ghidra_route` を使って再現する (507・187)。`origin/main` 側の `ghidra_route` で回した census (529・187 と記されていた値) は再現していない (未測定。`origin/main` を取り込むと基準が変わるため、取り込み時に §6 で再測定する)。
- 旧表 (`bd1b7a297` 時点の 556・488) は、取り込み前の値として上の『census・取り込み前の値』節に残す。現行の値は本表。

**Gain/Haas/Gate の `.o` 不変**: 旧 converter (`ffb17f14d`) と HEAD の converter で生成した C の本体 (2 行目のヘッダ comment を除く) は 3 本とも差分 0 行。`emcc -c` の `.o` は `cmp` で一致 (gain 1,435 B・haas 3,217 B・gate 3,756 B)。`gtype_census.sh` の第 2 引数で同じ比較を再現できる。

**再現**: `bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work> <旧 ghidra_route dir>` (`<work>` は repo 外。下に `win/HeartCore.core_64`・`emsdk/`・`ghidra/ghidra_12.1.4_PUBLIC/` を置く)。

**残件 119 件の分類と起票先** (型不一致の総数 119 は `fe5fa8215` の表と同じ。内訳は `bd1b7a297` 時点で、未再測定。`emcc_census.py` の「演算・代入・ポインタの型不一致」の内訳。P 番号は本付録の分類)

| 分類 | 件数 | 例 (delay.c の行) | 規則案 | 起票先 |
|---|---|---|---|---|
| P5 関数引数の pointer⇔整数 | 73 | `FUN_180fd8aac(((unsigned char*)gt_1813a3a80 + 0xee30d0), …)` | 同ビットの明示キャスト (呼出元の機械語の引数レジスタで確認) | #3837 [KH-72] |
| P6 代入の pointer⇔整数 | 14 | `param_1[1] = ((unsigned char*)gt_1813a3a80 + 0xed7778);` | 代入先の型か、キャストで揃える | #3837 [KH-72] |
| P1 関数ポインタ global | 9 | `(*_DAT_1813a1d40)(param_1, …);` | 型の割当ては未決 (PE 値は画像内の番地 0x1813e3850。実行時に設定される値の可能性) | #3849 [KH-80] |
| P3 Win API の戻り値・handle | 9 | `lVar2 = HeapAlloc(_DAT_184162a70,0,param_1);`・`GetCurrentProcess()`・`RtlPcToFileHeader`・`RtlLookupFunctionEntry` | 戻り値型の stub (意味は実装せず、到達時 abort) | #3849 [KH-80] |
| P2 void 戻り値の値扱い・double の cast | 7 | `puVar2 = (undefined8 *)FUN_180f87cac(lVar5);`・`(double)FUN_180fc4590(…)` | 呼出元の機械語 (rax) で戻り値を確認し ABI 表へ | #3849 [KH-80] |
| P4 BINOP 残件 | 7 | `(uint)fVar26 ^ _DAT_1813d1a80`・`SUB84(_DAT_182286968,0) ^ _DAT_18141d060` | `(uint)` が float のビット再解釈か数値変換かを機械語で確認。`(uint)`/`(ulonglong)` の再解釈は #3836 [KH-71] (別 run) と重なる | #3849 [KH-80] |

- 他の census 区分の起票先 (変更なし): レーン 191 = #3094 [KH-42] 系、SIMD・AVX 46 = #3095 [KH-43] 系、引数の過不足 108 = #3800 [KH-64]、未定義 identifier 17 = #3802 [KH-66]、未関数化 callee 5・その他 2 = #3802 [KH-66] 系。
- 同時期に別 run が起票した Delay の子: #3835 [KH-70] (LAB・PTR__ 17)・#3836 [KH-71] (double のビット再解釈)・#3808 [KH-67] (AVX 512bit レーン 106)・#3809 [KH-68] (混在型レーン 11)・#3821 [KH-69] (Stereo の未関数化 callee)。本付録の分類とは区分が違うため、件数は重ねていない。
