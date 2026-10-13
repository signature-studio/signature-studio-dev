# REPORT_595 — `M11_OV_CLASSCREATE=1` (ON) の ok 退行 5 件の原因と修正 (#595, 親 #419 / PR #446)

結論: ON の ok 退行 5 件 (15 42 45 138 415) のうち **4 件は 2 つの C 転記 (`41c130` / `413060`) で解消**。
残る 1 件 (unit 415) は ON で新たに呼ばれる closure 外関数 `9b4b00` が miss になるためで、ok→miss の分類変化 (§4)。
Issue 記載の unit 85/719 の退行・unit 114 のハングは、**現 main (#474/#503 後) の ON では再現しない** (§3)。
**受入条件 2 (ON でも退行 0) は未達 (1 件残)**。既定 OFF は維持し ON を既定にしない。

素材: work-m11 スナップショット + `/opt/emsdk` (PE 無し)。手順: `bash m11_build.sh` / `M11_OV_CLASSCREATE=1 bash m11_build.sh` →
`node trap_triage/survey_units.mjs out.json` → `python3 trap_triage/survey_diff.py a.json b.json`。942 unit。
ベース = PR #446 head `5ff73ff` (main `0865903` を含む)。逆アセンブルは `disasm_img.py` (capstone は venv に導入)。

## 1. 測定 (build と survey は各構成 1 回ずつ。load average 0.4〜0.9。build 6.5 s (増分) / survey 17.3 s)

| 構成 | コード | ok | oob | halt0 | miss | ok 退行 |
|---|---|--:|--:|--:|--:|---|
| main 対照 (`origin/main` の `m11_ov.c`) | `0865903` | 818 | 21 | 56 | 46 | — |
| 既定 OFF | `5ff73ff` | 818 | 21 | 56 | 46 | 対照と unit 単位で差 0 (kind / frames / icall 差 0) |
| ON (旧) | `5ff73ff` | 813 | 23 | 55 | 50 | 5: 15 42 45 138 415 |
| ON + `41c130` | `fc3f2af` | 816 | 21 | 56 | 48 | 2: 15 415 |
| ON + `41c130` + `413060` | `bf5d84f` | 817 | 21 | 56 | 47 | 1: 415 |
| 既定 OFF (修正後) | `bf5d84f` | 818 | 21 | 56 | 46 | main 対照と差 0 (ネガコン) |

`bf5d84f` の ON は 2 回測って unit 単位で一致。OFF → ON (最終): ok→miss 1 (415)、他は kind 不変 (oob→oob 21, halt0→halt0 56)。
trap (oob+halt0) は OFF 77 / ON 77 で不変 (ON は halt0→ok を一つも作らない = 現 main では ON の利得が無い)。
ネガコン (修正が効いていることの裏取り): 上表の段階的な退行数 5 → 2 → 1 が、各転記を足す前後の同一 survey での実測。

## 2. 原因 (unit 単位の実測)

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
修正: `function_413060` を逆アセンブルから C 転記 (ON 時のみ)。unit 15 は ok に戻った (`bf5d84f`)。

### 2.3 unit 415: ON で呼ばれる closure 外関数が miss (§4)
`410360` の呼出し先が `0x9b4b00` (AfterConstruction 相当のスロット実体。`410070` → `481790` → `9b5450` → `4133f0`/`412d60` を呼ぶ 144 byte)。
boot closure 外 (`boot_fns.json` に無い) ため `m11_icall` が miss → unit 415 の kind が ok → miss。**機能退行ではなく、OFF では AfterConstruction 呼出し自体が
脱落していた (D15) ため miss が見えなかった**と読める (「ok」だった OFF は呼ばずに終わっていた)。`9b4b00` は `9b5450` (`boot_final3_sigs.h` に無い) も呼び、転記範囲が広いため本 PR では未転記。
unit 745 (`0x125720` を miss するが kind は halt0 のまま) と 304 (oob の frame が変わるが oob のまま) も差分 unit だが kind は不変。

## 3. Issue 記載の unit 85 / 719 / 114 は現 main では再現しない
Issue (#595) の退行 5 件 (85 719 42 45 415) とハング (114) は #446 の古い tree (#474/#503 前) での値。現 main (`0865903`) + #446 head の ON では:
- unit 85: OFF ok → ON ok。unit 719: OFF halt0 → ON halt0 (退行ではない、`growMemory` 失敗は OFF から同じ)。
- unit 114: OFF halt0 → ON halt0 (ハングではない。`SV_SKIP` 不要、survey は 17 s で完走)。unit 114 のハング原因は REPORT_474.md が `5c0270` の D4 と特定済み (本 run では再検証していない)。
- 退行は元の 5 件のうち 42 45 415 + 新たに 15 138 の組 (上 §2)。同じ unit が毎回同じ原因とは限らない点に注意。
`409470` 経由の 85 / `409410` 内 `407a50` の 719 は、#474 後の main でどちらも ok / halt0 のまま変わらず、現 main の ON では退行として現れない (どの変更で解消したかは未特定)。

## 4. 未解決 (PM に起票を依頼)
1. unit 415 (ON で ok→miss): `9b4b00` (ユーザクラス AfterConstruction) の closure 外 miss。転記するか、miss を kind=ok 扱いにしない方針の決定。
2. `413060` の D4 は **OFF の IR にも存在する** (ON/OFF で同じ関数)。OFF での実害 (`Q(inst)` 破壊の有無) は未測定。既定 ON にするかは別 issue で OFF の survey 差を測って決める。同型の `412d60(&old)` 呼びを持つ他関数の洗い出し。
3. ON の利得は現 main では無い (trap 77 → 77)。ON にしない根拠は「利得 0・残退行 1」。`410360` / `410320` の ON 経路は `8cc190` 系 (§8.2) の再調査後に再評価。
