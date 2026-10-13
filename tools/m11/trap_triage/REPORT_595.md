# REPORT_595 — `M11_OV_CLASSCREATE=1` (ON) の ok 退行の原因と修正 (#595, 親 #419 / PR #446)

既知類型との関係: D4 (DEFECTS.md)・D15 (DEFECTS.md) に該当 (§2.2 が D4 の deref 脱落、§2.3 が D15 の AfterConstruction 呼出し脱落。番号は `docs/DEFECTS.md` の体系)。

結論: 旧ベース (`5ff73ff`) の ON の ok 退行 5 件 (15 42 45 138 415) のうち **4 件は 2 つの C 転記 (`41c130` / `413060`) で解消**。
本ベース (main `8d883c3` + 本 PR) の ON の ok 退行は **unit 415 の 1 件のみ** (§1)。415 は ON で新たに呼ばれる closure 外関数 `9b4b00` が miss になるためで、ok→miss の分類変化 (§2.3・§4)。
Issue 記載の unit 85/719 の退行・unit 114 のハングは、**現 main (#474/#503 後) の ON では再現しない** (§3)。
**受入条件 2 (ON でも退行 0) は未達 (1 件残)**。既定 OFF は維持し ON を既定にしない。

素材: work-m11 スナップショット + [EMSDK] (`docs/REFERENCES.md`)。PE 無し (fl-win64 未取得)。main `8d883c3` の `m11_build.sh` の qstore pass は PE が無いため 3 構成すべて skip (build log の WARNING で確認)。
手順: `bash m11_build.sh` / `M11_OV_CLASSCREATE=1 bash m11_build.sh` →
`node trap_triage/survey_units.mjs out.json` → `python3 trap_triage/survey_diff.py a.json b.json`。942 unit。
ベース = 本 PR の merge commit `8445b39` (main `8d883c3` を取り込み済み。#446 は `8d883c3` でマージ済み)。実行されるコードは `8445b39` と同一 (以降の変更は docs・`m11_ov.c` の注釈・`negctl_595.sh` の追加のみ)。旧ベース (`5ff73ff`・`0865903`) の値は §1 の旧ベース表だけに残す。逆アセンブルは `disasm_img.py` (capstone は venv に導入)。

## 1. 測定 (本ベース。build と survey は各構成 1 回ずつの単発。load average (1 分値) 0.54〜0.89 を計測中の `uptime` で記録)

build 5.3〜10.1 s、survey 12.4〜12.8 s (いずれも wall の単発。既定 OFF の build 10.1 s は m11_simd / winstubs / fnstubs / m11_ov の再 cc を含み、ON の build 5.3 s は ov.o の再 cc のみ)。並列数 1 (各構成・各工程を逐次実行。構成間の並列実行は無し)。

| 構成 | コード | ok | oob | halt0 | miss | noproc | ok 退行 |
|---|---|--:|--:|--:|--:|--:|---|
| main 対照 (既定 OFF) | `8d883c3` | 818 | 21 | 56 | 46 | 1 | — |
| 既定 OFF | `8445b39` | 818 | 21 | 56 | 46 | 1 | 対照と unit 単位で差 0 (kind / frames / icall 差 0) |
| ON | `8445b39` | 817 | 21 | 56 | 47 | 1 | 1: 415 |

分母は 942 unit = ok + oob + halt0 + miss + noproc (全行で一致)。`noproc` は `_m11_call_unit` が 0 を返した unit で、3 構成とも unit 941 (VA 0x0) の 1 件。

再実行 (同じ手順・単発・並列数 1。上表と同じ kind の結果を再現): 初回 (work-m11 展開直後で再 cc を含む) OFF build 8.0 s / survey 8.8 s、ON build 3.9 s / survey 9.0 s。commit `d8f0e5d` での再実行 (差分 build) OFF build 3.7 s / survey 8.9 s、ON build 3.7 s / survey 8.9 s。load average (uptime 1 分値) 0.12〜0.84。OFF 818 / 21 / 56 / 46 / 1、ON 817 / 21 / 56 / 47 / 1、ok 退行 415。

OFF → ON の遷移は ok→miss 1 (415) のみ。他は kind 不変 (oob→oob 21, halt0→halt0 56, noproc→noproc 1)。trap (oob+halt0) は OFF 77 / ON 77 で不変 (ON は halt0→ok を一つも作らない = 本ベースでも ON の利得が無い)。

旧ベースでの段階測定 (参考。`41c130` と `413060` は同じマクロ `M11_OV_CLASSCREATE` の下にあり、本ベースでは段階ごとの切替ができないため再測定していない。旧ベースの noproc は 942 との差から導出)。

| 構成 (旧ベース) | コード | ok | oob | halt0 | miss | noproc | ok 退行 |
|---|---|--:|--:|--:|--:|--:|---|
| main 対照 (旧) | `0865903` | 818 | 21 | 56 | 46 | 1 | — |
| 既定 OFF (旧) | `5ff73ff` | 818 | 21 | 56 | 46 | 1 | 対照と unit 単位で差 0 |
| ON (旧) | `5ff73ff` | 813 | 23 | 55 | 50 | 1 | 5: 15 42 45 138 415 |
| ON + `41c130` | `fc3f2af` | 816 | 21 | 56 | 48 | 1 | 2: 15 415 |
| ON + `41c130` + `413060` | `bf5d84f` | 817 | 21 | 56 | 47 | 1 | 1: 415 |

旧ベースの `bf5d84f` の ON は 2 回測って unit 単位で一致 (本ベースは単発)。
ネガコン (段階の寄与の裏取り): 旧ベースの退行数 5 → 2 → 1 は、各転記を足す前後の同一 survey での実測。OFF 側の経路に差分が出ないことは既定 OFF の行 (本ベース・旧ベースとも main 対照と unit 単位で差 0) で確認。

## 2. 原因 (unit 単位の実測。段階の切り分けは旧ベースの表で行った)

icall 表のキー = 生の値 + 0x400000 (VA)。本文の slot `0x1007000` は生の値で、表のキーは `0x1407000`。本文の他の番地 (`0x9b4b00`・`0x41c130`・`0x525720`) は VA 表記。

### 2.1 unit 42・45・138: `41c130` (TInterfacedObject.AfterConstruction) が closure 外 → miss
410360 を ON にすると `[vmt-0x50]` 経由の AfterConstruction 呼出しが現れる。既定実体 `410070` (= `ret`) は `m11_vcall` が直接処理するが、
TInterfacedObject 派生は `41c130` (`or eax,-1; lock xadd [rcx+8],eax; ret` = FRefCount を 1→0 に戻す) を引く。これは boot closure 外で miss になり、
`NewInstance` (`41c160`) が 1 にした FRefCount が戻らない。unit 42 は site `0x41037d` が `0x41c130` を 2 回 miss、138 は oob (`417fc0` 内)。
修正: `disp_find` に `41c130` を追加 (`tr_41c130`, ON 時のみ)。42・45・138 は ok に戻った (`fc3f2af`)。

### 2.2 unit 15: `413060` の D4 (deref 脱落) がオブジェクト先頭 8 byte を壊す
unit 15 の 2 件の AfterConstruction 呼出しは slot = `0x1007000` (コードではない値)。`410360(inst)` の `[inst]` (VMT) が `0x2f697` で、
`410320` 直後の値 `0x2f698` と 1 違う。`448ee0` を C に置いて測ると、`41c820(inst+8, msg)` の実行前後で `Q(inst)` が `0x2f698 → 0x2f697` に変わっていた (2 箇所とも)。
`41c820` → `413060` (dest=inst+8 の文字列代入) の機械語は `old := [rbx]` を stack に退避して最後に `412d60(&old)` で解放する。
RetDec は `mov rax,[rbx]` の deref を落とし (DEFECTS D4)、stack に dest **のアドレス自体** を入れた。`412d60` はそれを文字列ポインタと解釈し
`dest - 0x10 + 8 = inst + 0` の dword を refcount として 1 減らす。VMT ポインタ下位が 1 減り、`[vmt-0x50]` が壊れた値 (`0x1007000`) になる。
OFF でも `410320` は既定 ON (#474) で実オブジェクトを返すため同じ書込みは起きていると推定するが、OFF の `Q(inst)` は未測定。OFF の `410360` は `ret arg1` で `[inst]` を読まないため顕在化しない (未検証の推定)。
上記の `Q(inst)`・`[inst]`・slot の数値は `448ee0` を C に置いて測った計測 (未コミット・再現なし)。

再現 (commit `d8f0e5d` で実施): `bash trap_triage/negctl_595.sh` (`413060` の `u64 old = Q(dest);` だけを D4 の欠陥形 `(u64)(uintptr_t)dest` に戻して ON で survey。単発、総計 33 s 実測)。
- 転記どおり (on): ok 817 / oob 21 / halt0 56 / miss 47 / noproc 1
- 欠陥形 (d4): ok 816 / oob 21 / halt0 56 / miss 48 / noproc 1。ok→miss は unit 15 の 1 件のみ。unit 15 の icall `0x1407000` が miss 2 (on は 0)
→ 413060 の D4 が unit 15 の ok 退行の原因 (ネガコン)。

呼出し側 (IR `work/boot_final3.ll`): `413060` の呼出し 28 箇所のうち戻り値を読むのは 7 箇所 (5 は上位関数の `ret` へ素通し、2 は rax 変数へ格納)。計測 (未コミット・再現なし)。戻り値を `dest` とする転記が呼出し側に影響するかは未検証。

修正: `function_413060` を逆アセンブルから C 転記 (ON 時のみ)。unit 15 は ok に戻った (`bf5d84f`)。

### 2.3 unit 415: ON で呼ばれる closure 外関数が miss (§4)
`410360` の呼出し先が `0x9b4b00` (AfterConstruction 相当のスロット実体。`410070` → `481790` → `9b5450` → `4133f0`/`412d60` を呼ぶ 144 byte)。
boot closure 外 (`boot_fns.json` に無い) ため `m11_icall` が miss → unit 415 の kind が ok → miss。**機能退行ではなく、OFF では AfterConstruction 呼出し自体が
脱落していた (D15) ため miss が見えなかった**と読める (「ok」だった OFF は呼ばずに終わっていた)。`9b4b00` は `9b5450` (`boot_final3_sigs.h` に無い) も呼び、転記範囲が広いため本 PR では未転記。
unit 745 (icall 表のキー `0x525720` = survey JSON の `miss_new` の生の値 `0x125720` + 0x400000 を miss するが kind は halt0 のまま) と 304 (oob の frame が変わるが oob のまま) も差分 unit だが kind は不変 (本ベースでも同じ)。

## 3. Issue 記載の unit 85 / 719 / 114 は現 main では再現しない
Issue (#595) の退行 5 件 (85 719 42 45 415) とハング (114) は #446 の古い tree (#474/#503 前) での値。現 main (`8d883c3`) + 本 PR の OFF/ON では (§1 と同じ survey の unit 単位、単発):
- unit 85: OFF ok → ON ok。unit 719: OFF halt0 → ON halt0 (退行ではない、`growMemory` 失敗は OFF から同じ)。
- unit 114: OFF halt0 → ON halt0 (ハングではない。`SV_SKIP` 不要、ON の survey は 12.8 s で完走)。unit 114 のハング原因は REPORT_474.md が `5c0270` の D4 と特定済み (本 run では再検証していない)。
- 退行は元の 5 件のうち 42 45 415 + 新たに 15 138 の組 (旧ベース、§2)。本ベースの ON の退行は 415 のみ。同じ unit が毎回同じ原因とは限らない点に注意。
`409470` 経由の 85 / `409410` 内 `407a50` の 719 は、#474 後の main でどちらも ok / halt0 のまま変わらず、現 main の ON では退行として現れない (どの変更で解消したかは未特定)。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (1) unit 415 (ON で ok→miss): `9b4b00` (ユーザクラス AfterConstruction) の closure 外 miss。転記するか、miss を kind=ok 扱いにしない方針の決定 | §1 の旧表 (本ベース) の時点の ON 退行。§5 で再評価済み (415 は ON で ok、#704 の転記後) | #704 (完了) |
| (2) `413060` の D4 は **OFF の IR にも存在する** (ON/OFF で同じ関数)。OFF での実害 (`Q(inst)` 破壊の有無) は未測定。同型の `412d60(&old)` 呼びを持つ他関数の洗い出し | 推定: OFF でも同じ書込みが起きていれば既定 OFF の survey に影響しうる (未測定)。既定 ON にするかの判断材料 | #705 |
| (3) ON の利得は現 main では無い (trap 77 → 77)。`410360` / `410320` の ON 経路は `8cc190` 系 (`tools/m11/trap_triage/REPORT.md` §8.2) の再調査後に再評価 | §5 で再評価済み (#594・#596 の調査後)。ON は既定にしない | §5 |
| (4) unit 85 / 719 が現 main で退行しなくなった理由が未特定 (§3)。どの変更で解消したかが分からない | 受入条件 1 の残り (退行の原因一覧が完全でない)。ON 判断の材料が一つ欠ける | #595 (本 issue、Refs) |

## 5. 再評価 (#595 再着手。main `ca117e76`・IR は `m11_gen_ir2.sh` で再生成)

#594 (PR #664) と #596 (PR #675) の調査が merge 済みのため、(3) の保留を解く再測定を行った。#704 (415 の `9b4b00` 転記) と #705 は本 run の前提に含む。

- 素材: fl-win64 (PE 展開) / work-m11 / toolchain-emsdk。`m11_gen_ir2.sh` rc=0 (29 s、ldfix=applied、errors=0)。capstone・pefile は user install。
- 同一 IR・同一 HEAD で OFF / ON を各 1 回 build・survey (逐次、並列数 1、load average 0.96〜1.00)。
- build: OFF 18.9 s / ON 14.5 s (rc=0)。survey: OFF 7.0 s / ON 6.4 s (rc=0)。

| 構成 | ok | oob | halt0 | miss | other | noproc | ok 退行 |
|---|--:|--:|--:|--:|--:|--:|---|
| 既定 OFF | 869 | 16 | 8 | 47 | 1 | 1 | — |
| ON | 867 | 18 | 8 | 47 | 1 | 1 | 4: 101 190 291 296 |

- 遷移 (OFF→ON): ok→ok 865 / ok→oob 4 (101 190 291 296) / oob→ok 2 (304 555) / oob→oob 14 / halt0 8 不変 / miss 47 不変。
- trap (oob + halt0) は OFF 24 / ON 26 (+2)。内訳は ok→oob 4 件 (新規 trap) と oob→ok 2 件 (trap 解消) の差し引き。
- 利得: halt0→ok 0 件、oob→ok 2 件 (304 555)。ok 退行 4 件 (101 190 291 296) が残る。
- 415 は ON で ok (#704 の転記が効いている)。
- 退行 4 件 (101 190 291 296) の原因は `0x41037d` の新規 hit → `VA-big` oob。#912 ([M11-N49]) で追跡。
- `REPORT_704.md` の値 (OFF oob 17 / ON oob 19) と oob が各 1 件ずれる。IR 生成の差 (再生成ごとの差) の可能性があるが、本 run では切り分けていない。

結論: ON の利得は halt0→ok 0 件、oob→ok 2 件 (304 555)。trap 総数は +2 (新規 oob 4 件が上回る)。ok 退行 4 件 (101 190 291 296) が残るため差し引きで不採用。**既定 OFF を維持し ON は採用しない**。根拠はこの表。ON を採用するには #912 の解決が前提。
