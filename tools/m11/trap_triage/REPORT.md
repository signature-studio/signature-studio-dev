# M11 survey trap 個別原因切り分け (#130) — tools/m11/trap_triage/

**判定: 部分達成 (trap 83 → 66、目標 < 20 は未達)**。halt0 48 unit の発生源を wasm スタックで全数特定し、
最大の原因 `function_417b70` (System.DynArraySetLength) の 1 段 deref 脱落を C 転記 (`m11_ov.c`) で修正した。

## 1. 実測 (HEAD `36494d0`、`bash tools/m11/m11_e2e.sh`、16.2 s、load average 0.38)

| 項目 | 修正前 | 修正後 |
|---|--:|--:|
| survey ok | 812 | **829** |
| survey trap 計 | 83 | **66** |
| └ oob / halt0 / abort | 34 / 48 / 1 | 44 / 21 / 1 |
| reached_stage / units_run (通常起動) | 4/6 / 17 | 4/6 / 17 (不変) |
| wasm-ld signature mismatch / undefined | 0 / 0 | 0 / 0 |

`node tools/m11/trap_triage/survey_units.mjs <out.json>` (同 HEAD、0.51 s): `SURVEY_UNITS {"ok":829,"oob":44,"halt0":21,"miss":46,"abort":1,"noproc":1}`。

unit 遷移 (per-unit JSON 比較): halt0→ok 16 / **halt0→oob 11** / oob→ok 1。halt0→oob の 11 件は、
修正で Halt0 を抜けて先へ進み、次の欠陥 (下記 §3-2) に当たったもの。trap 総数の減少は 17 (= 83−66)。

## 2. halt0 48 unit の原因 (`survey_units.mjs` の Halt0 例外スタックから全数集計)

48 件全てが `Error(reOutOfMemory/reInvalidPtr)` = `function_409730` (または 412a60 経由) → `Halt0` の経路。
CAB-129 REPORT §5 の「GetLocaleInfoW / LoadStringW 相関」は不採用 (halt0 unit が呼ぶ stub は 3 件のみ)。

| Error() 呼出元 | unit 数 | 内容 |
|---|--:|---|
| `417b70` DynArraySetLength | 17 | 引数 `a` と `lengths` の 1 段 deref (`mov rax,[rax]`) が IR で脱落。lengths(スタック addr) が配列長になり GetMem が失敗 |
| `409410` GetMem (内側 `417b70` 経由) | 14 | 上記の波及 (巨大 size 要求 → `VirtualAlloc` が calloc 失敗 → NULL → Error(1))。unit 87 で 559 MB, 245 で 178 MB を要求 |
| `40a1c0` | 6 | 未調査 |
| `416db0` / `4159e0` | 3 / 3 | 未調査 |
| `411d20` (→ `411e80` → `814d30` / `45a2a0`) | 4 | 未調査 |
| `409470` ReallocMem | 1 | 未調査 |

`417b70` の転記後、17 + 14 のうち **16 unit が ok、11 unit が OOB** になった (残りは別経路の Error で halt0 のまま)。

## 3. 修正と残存

1. **`function_417b70` を C 転記** (`m11_ov.c`、逆アセンブル 417b70..417fa2 と突合)。
2. **`function_409470` (ReallocMem) の転記は revert**: 同じ 1 段 deref 脱落 (`cmp [rbx],0` / `mov rcx,[rbx]`) と
   4094da の `llvm.trap` 化けを確認し転記したが、boot 中の unit 884 (`1268010` → `12df090` → `409470`) が
   戻らなくなり survey が完走しなかった (60 s 超でハング。原因は未特定)。転記は採用せず revert。
   → 原因は 409470 ではなく 410320 の脱落 (#418 `REPORT_418.md`) と 5c0270 の deref 脱落 (#474 `REPORT_474.md`)。#474 で再採用済み。
   `5c03d0` の通知 call (`5c0437`) の脱落は #482 `REPORT_482.md` で復元 (survey の分類は不変)。
   `409470` 経由の OOB 11 unit (`409470 → 408040 → 407e20`) は残っている。
3. 残 OOB 44 の最上位 frame: `8cc190` ×9 (#130 §6 の通り上流 `8c5cc0` のポインタ破壊)、`414bb0` ×5、`904190` ×4、
   `4fb090`/`410730` ×3、`47d460` ×4 ほか (unit 一覧は `annotate.py` 出力)。個別原因は未調査。

## 4. 再現手順

```sh
# 前提: bash tools/m11/m11_e2e.sh 済み (work/m11_boot.cjs, work/m11_image.bin)
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/after.json    # 942 unit の per-unit JSON (kind / frames / stub / va_mb)
python3 tools/m11/trap_triage/annotate.py tools/m11/work/trap_triage/after.json [unit...]   # export 名で注釈・halt0 の Error() 呼出元集計
python3 tools/m11/trap_triage/disasm_fn.py 417b70 ...   # PE (.pdata 区間) の capstone 逆アセンブル
```

環境変数: `SV_ONLY=884` (unit 限定)・`SV_SKIP=114,...` (unit を飛ばし `hang` で記録 §8.2)・`SV_TRACE_AT=884` (その unit 以降を trace。#495 で結果を変えないよう透過化済み `REPORT_495.md`)・`SV_PROG=1` (進捗を stderr)・`SV_STK_FILL=ff` (各 unit 直前に SP 下を埋める)。
`capstone` / `pefile` (pip) が要る。`disasm_fn.py` は `tools/shared/paths.py` の `FL_WIN64_DIR`
(`docs/REFERENCES.md` `[WIN64]`、Actions での展開は `docs/WORKFLOW.md` §11) 配下の `extracted/block00031_PE.bin` を読む
(`LD_M11_PE` で PE を直接指定も可)。`m11_e2e.sh` など既存スクリプトは作業 VM の固定パスを前提にするため、
この runner では `[WIN64]` と repo の checkout をそのパスへ symlink して実行した (PR #301 の方法)。

## 5. 未解決 (下流)

- halt0 残 21 (`40a1c0` 6 / `416db0` 3 / `4159e0` 3 / `411d20` 4 ほか) の個別原因。
- `409470` ReallocMem の転記でハングする原因 (unit 884) と、`409470 → 408040/407e20` OOB 11 unit。 → ハング原因は解決 (#474 `REPORT_474.md`)。
- OOB 44 の個別原因 (`8cc190` 系 9 unit は上流 `8c5cc0`/`8c7a10`)。
- 完了条件 (trap < 20) は未達 (66)。

## 6. halt0 残 20 unit の原因特定 (#417)

前提: #414 マージ後の `main` (`64e617f`) の上 (旧 PR #447 は base `130-m11-survey-trap` が #414 の merge で消え自動 close。同ブランチを main に merge して再測定)。
base (`main` 64e617f) を build した `survey_units.mjs` の実測は ok 830 / oob 44 / halt0 **20** / abort 1
(PR #414 本文は「halt0 21」。`m11_e2e.sh` は PE (fl-win64) が runner に無く実行できなかったため、差 1 の原因は未確認)。
分類は `halt0_classify.py` (Error() 呼出元で集計)、呼出経路は `survey_units.mjs` の wasm frame を `annotate.py` で名前解決して実測した。

### 6-1. base の 20 unit の分類 (Error() 呼出元別) と結果

| Error() 呼出元 | unit | 原因 (逆アセンブルと IR の突合) | 結果 |
|---|---|---|---|
| `40a1c0` (FP 例外送出) | 162/184/185/190/370/888/905 (7) | `function_40a3b0` (GetMXCSR: `stmxcsr [rsp]; pop rax; ret`) の IR が `__asm_stmxcsr(0); ret 0` で **pop rax 脱落**。MXCSR マスクが 0 = 全 FP 例外アンマスク扱いになり送出 | `m11_ov.c` で 0x1f80 を返す: 6 unit が ok、190 は OOB へ前進 |
| `4159e0` InitializeArray | 232/492/616 (3) | 型 kind バイト `movzx rcx,[rax]` の load 脱落で kind=0 固定 → default 分岐 `Error(2)` | C 転記: 232/616 は ok、492 は次の `410630` で停止 |
| `416db0` CopyArray | 86/357/496 (3) | 同上 (+ kind 12 の `call [mem]` (416720) が脱落 = D15 型) | C 転記: 3 unit とも ok |
| `411d20` raise | 22/245/279/509/647 (5) | 例外送出。呼出元 `814d30` が `arg3&1` の分岐から `Exception.Create(...)` を呼ぶ。同関数の IR 定数は `inttoptr i64 <10進 VA>` で LVA 未変換 (§6-2) | 未修正 |
| `409470` ReallocMem | 189 (1) | §3-2 の deref 脱落 (転記はハングで revert) | 未解消 |
| `410630` | 493 (1) | `GetCurrentThreadId` と `[obj+8]` の不一致 → `Error(0x19)` (CheckSynchronize 系) | 原因未特定。493 は他修正後に `411d20` 系へ移り、代わりに 492 が `410630` で止まる |

類型対応 (`docs/DEFECTS.md`): GetMXCSR / InitializeArray / CopyArray は RetDec が pop / load を落とす **deref・load 脱落** (§3-1 の 417b70 と同族)、
CopyArray kind 12 は **D15** (メモリ間接 call 脱落)。`411d20` 系は **D11** (PE VA リテラルの座標未変換) の変種の疑い。
DEFECTS.md への採番は PM に委ねる (本 PR は触らない)。

最終 HEAD の halt0 残 8 (`halt0_classify.py`): `411d20` 6 (22/245/279/493/509/647)、`409470` 1 (189)、`410630` 1 (492)。

### 6-2. 10 進 inttoptr 命令形の VA→LVA 未変換 (D11 変種の疑い)

`m11_passes.py` の M2 は `inttoptr i64 0x… to ptr` (16 進) だけを remap する。RetDec は絶対アドレスを `%x = inttoptr i64 <10進> to ptr` でも出し、
`boot_allfx.ll` に 4449 件、うち VA 範囲 (0x400000..0x1ac0000) が **4364 件**残る。`814d30` の `inttoptr i64 200376` / `154720` は LVA ではなく VA 側の値。
`pass_m2p_dec_inttoptr` を実装し 4364 件を全て remap して再 build すると:
- 単体実行 (`SV_ONLY=<unit>`, 25 s timeout): unit 22 / 509 は ok、189/245/279/647 は oob、492/493 は halt0 のまま (最終 HEAD の halt0 8 unit のうち ok 化は 2 件のみ、4 件は oob に変わる)
- 全 unit の survey は **unit 503 でハング** (300 s タイムアウト)、503 を除いても 200 s 以内に完走しなかった

全件 remap は副作用が大きく、どの定数が VA のままで正しいか (例: Delphi の RTTI/VMT ポインタ) の仕分けが要るため、`M11_M2P=1` の opt-in とし **既定は OFF**。
本 PR の数値 (§6-3) は M2p OFF のビルド。ハング原因と仕分けは未調査。

### 6-3. 実測 (コミット済み HEAD `bb261ba` = main `64e617f` を merge した後、M2p OFF)

`bash tools/m11/m11_build.sh` (全再生成 base 9.1 s / HEAD 9.4 s) 後に `node tools/m11/trap_triage/survey_units.mjs` (0.54–0.56 s, n=5) と `node tools/m11/m11_survey.mjs` (0.48–0.49 s, n=5)。
1 並列・4 コア runner・load average 0.4–0.6。`m11_e2e.sh` は PE 無しだと前提チェックで止まり、チェックを外しても `gen_ir2` (ldfix が skip され IR が別物) と
`m11_data_gen`/`m11_image_gen` (PE 必須) が走るため使えない。e2e 後半と同じ build → `m11_run.mjs` (0.36–0.39 s) → `m11_survey.mjs` → `m11_judge.py` (reached_stage 4/6) を work スナップショットで個別実行した:

| 項目 | base (main 64e617f) | 本 PR |
|---|--:|--:|
| ok | 830 | **841** |
| trap 計 (oob + halt0 + abort) | 65 | **54** |
| └ halt0 | 20 | **8** |
| └ oob | 44 | 45 |
| └ abort | 1 | 1 |

unit 遷移 (per-unit JSON 比較): halt0→ok 11 / halt0→oob 1 (unit 190)。`m11_survey.mjs` も ok 841 / trap 54 (oob 45 / halt0 8 / abort 1)。
wasm-ld signature mismatch 0 / undefined 0。

**ネガコン** (HEAD の `m11_ov.c` から該当 override だけ `static nc_*` に改名して無効化 → 再 build → survey。実測):

| 無効化 | ok | oob | halt0 |
|---|--:|--:|--:|
| なし (HEAD) | 841 | 45 | 8 |
| GetMXCSR (`40a3b0`) のみ | 835 | 44 | 15 |
| InitializeArray + CopyArray (`4159e0`/`416db0`) のみ | 836 | 45 | 13 |

いずれも無効化で halt0 が増え (+7 / +5)、有効化で復帰する。

### 6-4. 再現

```sh
bash tools/m11/m11_build.sh
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/head.json
python3 tools/m11/trap_triage/halt0_classify.py tools/m11/work/trap_triage/head.json   # survey 直後に実行 (wasm index は build 依存)
```

M2p の opt-in 検証は `M11_M2P=1 python3 tools/m11/m11_passes.py work/boot_allfx.ll work/boot_final.ll --init-list work/inits_text.txt` の後に
`m11_genstubs.py` と `m11_gen_ir2.sh` 末尾の dotfix を同条件で適用し、`rm work/boot_final3.ll work/obj/boot.o` で再 build する。

## 7. 未解決 (#417 後)

- halt0 残 8: `411d20` 系 6 (§6-2 の座標未変換と M2p のハング)、`409470` 1 (unit 189)、`410630` 1 (unit 492)。
- OOB 45 (unit 190 が halt0→oob で +1)。
- 完了条件 (trap < 20) は引き続き未達 (54)。

## 8. OOB 分類 (#419): 最多分類 `8cc190` 系の調査と現 HEAD の実測

> **分割・注記**: 合流前 (`fa918df`・`c7061c6` 基準) の修正試行・旧 ON 構成 (410360 + 8cbda0/8cbce0) の詳細は `REPORT_419.md` に無変更で移動した (250 行上限)。
> §8.2 が現 HEAD (`c6b24ec`、コードは merge `51075ef` = PR head + main `0183e74` 取込み) の実測。PR 本文の検証結果表も同じ値。

素材: work-m11 スナップショット + `m11_build.sh` + `survey_units.mjs` (PE 無しで実行可。逆アセンブルは PE の代わりに
`work/m11_image.bin` を読む `disasm_img.py`)。ベースライン = #414 HEAD `fa918df` の m11_ov.c を build し直した survey:
ok 830 / oob 44 / halt0 20 / abort 1 / miss 46 / noproc 1 (§1 の 829/66 とは halt0 21→20・ok 829→830 が 1 unit 違う。原因未調査)。

### 8.1 最上位 frame 別の分類 (合流前 `fa918df` 基準、OOB 44。現基準の分類は §8.2)

※ #663: 下表は旧 frames 基準で**無効**。修正後の値は trap_triage/REPORT_663.md §2-1。

| 最上位 frame | unit 数 | 原因の状態 |
|---|--:|---|
| `8cc190` (←`8c7a10`←`8c5cc0`) | 11 (53 54 56 58 59 60 61 62 63 307 311) | **原因特定 (合流前、`REPORT_419.md` §A)**: TObject.Create の VMT 間接 call 脱落 |
| `410730` (←`4fb8a0`/`4fb910`) | 6 (101 291 296 304 555 923) | 未調査 |
| `414bb0` (←`652500`←`653660`←`6539e0`) | 5 (144 149 158 280 659) | 未調査 |
| `904190` | 4 (477 484 513 520) | 未調査 |
| `409470` ReallocMem | 4 (830 884 898 936) | §3-2 (転記でハング) |
| `47d460` (←`92d4f0`) | 4 (876 880 891 935) | 未調査 |
| 各 1 unit | 10: `446400`(17) `5b53f0`(95) `407e20`(138) `8674a0`(275) `8dfd70`(314) `96ef10`(365) `417fc0`(503) `6664c0`(547) `407a50`(745) `40ffe0`(895) | 未調査 |

(名前付き 6 グループ 34 + 各 1 unit 10 = OOB 44 / 最上位 frame 16 種。abort 1 = unit 114 `EnterCriticalSection` shim_unimplemented は OOB ではない。)

### 8.2 現 HEAD の実測 (`c6b24ec`。コードは merge `51075ef` = PR head + main `0183e74` 取込み)

**測定の基準 (採用)**: `m11_e2e.sh` と同じ手順で IR・data・image を**再生成**し、PE (fl-win64 素材) を揃えた状態。
ldfix は `PE` と capstone/pefile の両方が揃った時だけ走るため、`uv run --with capstone --with pefile` と PE パスの差替え (一時コピー、コミットしない) で実行した。
work-m11 スナップショットの IR / data は古い生成物で、現 main の生成手順と一致しない (下表 (c) と (a) の差) ため採用しない。
※ #663 訂正: 本節の「OOB 最上位 frame」集計 (下の段落と §8.1 の表) は**旧 frames 基準 (oob の最上位を 1 段捨てていた) で無効**。修正後の値は基準 (a) で trap_triage/REPORT_663.md §2-1、基準 (c) での再測定は未実施 (REPORT_663 §5)。

| IR 生成条件 | 対照 (main の m11_ov.c) / OFF | ON (`M11_OV_CLASSCREATE=1`, 410360 のみ) | ok 退行 |
|---|---|---|---|
| (a) スナップショット (旧生成物) | ok 818 / oob 21 / halt0 56 / miss 46 / noproc 1 (trap 77) | ok 813 / oob 23 / halt0 55 / miss 50 (trap 78) | 5 |
| (b) 再生成・PE 無し (ldfix・qstore skip) | ok 827 / oob 14 / halt0 54 / miss 46 / noproc 1 (trap 68) | ok 822 / oob 16 / halt0 53 / miss 50 (trap 69) | 5 |
| **(c) 再生成・PE 有り (ldfix・qstore 適用) ← 採用** | **ok 828 / oob 13 / halt0 54 / miss 46 / noproc 1 (trap 67)** | **ok 823 / oob 13 / halt0 54 / miss 51 / noproc 1 (trap 67)** | **5** |

採用基準 (c) の詳細 (942 unit、`survey_units.mjs` → `survey_diff.py`):
- **ネガコン (OFF vs 対照)**: 差 0。kind 遷移は全て同種、ok 退行 0、kind 以外を含む差分 unit 0、icall の site / target 差 0。
- **ON**: 遷移は ok→ok 823 / ok→miss 5 / halt0→halt0 54 / miss→miss 46 / oob→oob 13 / noproc→noproc 1。**halt0→ok は 0 件、trap 67→67**。
- **ok 退行 5 件**: 15・42・45・138・415 が全て ok→miss。miss 先は 15 = 0x1007000、42 = 0x1c130、415 = 0x5b4b00、45・138 は新規 miss 先なし。
- **unit 114**: OFF・ON とも halt0 で完走 (hang なし)。**`SV_SKIP=114` は不要**。
- **icall**: ON で site `0x41037d` (410360 の `call [rbx-0x50]`) が全 unit 合計 ok 23,053,861 / miss 9 (OFF は 0)。
- **決定性**: ON を 2 回測定し kind 以外を含め差 0。
- **所要**: スナップショット基準の OFF survey 17.2 s / ON 17.8 s (load average は 0.5 前後)。(c) の build・survey は時間未計測。

**OOB 最上位 frame (基準 (c)、旧 frames 基準で無効 — #663)**: OFF 13 件 = `4f9ff0` ×5 (291 296 304 555 923)、`414bb0` ×4 (149 158 280 659)、各 1 件 (95 `536da0`、275 `80e040`、477 `904190`、895 `40ffe0`)。ON は 304 が `4fb090` になるのみ。

**旧最多分類 `8cc190` 系 11 unit (53 54 56 58–63 307 311)**: 基準 (c) の OFF では 56 のみ halt0、他 10 件は **ok**。ON で遷移 0。
スナップショット基準では 56・58–63 (7 件) が OOB だったが、再生成で解消した (基準 (b) でも 10 件 ok)。PR の前提 (「最多分類 11 が OOB」) は現 main の生成手順では成立しない。

**e2e (`m11_e2e.sh` の PE パス差替え、既定 OFF、基準 (c))**: reached_stage 4 (DllMain attach 完走、longjmp 経路)、units_run 22/942、survey ok 864 / trap 31 (oom 1) / miss 46 / noproc 1、clobber 0。
所要: 基準 (b) の e2e run は wall 16.7 s (07:56 UTC、ldfix 無し IR)。基準 (c) の e2e は時間未計測。

**受入条件の判定 (現 HEAD、基準 (c))**
1. OOB 分類表: 達成。§8.1 は合流前 `fa918df` 基準の 44 件。現基準の 13 件は上表。
2. 最多 1 分類の修正で trap 減 + ネガコン: **未達**。ON は trap 67→67 (減少 0)、halt0→ok 0、ok 退行 5。最多分類は現基準で OOB 0 件のため、修正対象が残っていない。ネガコン (OFF = 対照 差 0) は成立。
3. #307 との関係: 未検証のまま (§8.3)。部分達成。

**起票依頼 (PM 判断。本 PR の範囲外)**
- (a) 410360 ON ブロックの扱い (現基準で trap 増減 0、ok 退行 5。削除候補)。
- (b) ok 退行 5 件 (15 42 45 138 415) の原因。miss 先 0x1007000 / 0x1c130 / 0x5b4b00。
- (c) OOB 13 件の個別調査 (`4f9ff0` ×5 / `414bb0` ×4 ほか)。
- (d) icall site `0x41037d` の hit 数 (全 unit 合計 ok 23,053,861) の妥当性の確認 (原因未調査)。
- (e) 測定基準の固定: work-m11 スナップショットの IR は古く、OFF の数値が 818/21 ↔ 828/13 と変わる。以後の数値は再生成 IR (基準 (c) の手順) で取る運用にするか。

**再測定手順** (`SV_SKIP` は ON で不要。hang する unit を飛ばす時だけ使う。PE 依存工程は `PE=<fl-win64>/extracted/block00031_PE.bin` と `uv run --with capstone --with pefile` で通す):
```
cd tools/m11
bash m11_build.sh && node trap_triage/survey_units.mjs out_off.json
M11_OV_CLASSCREATE=1 bash m11_build.sh && node trap_triage/survey_units.mjs out_on.json
python3 trap_triage/survey_diff.py out_off.json out_on.json
```
`SV_SKIP=<unit,...>`: 列挙した unit を実行せず `kind: "hang"` で記録する。`M11_OV_CLASSCREATE` は env で渡し、`work/ov_classcreate.stamp` で `work/obj/ov.o` を無効化する (値判定、`=0` は OFF)。

### 8.3 #307 (liftdiff OOB 222) との関係

liftdiff は hybrid closure の per-case 採点 (#307 は `414ad0` 系 68 が最多)、本調査は m11 の 942 unit survey で最多は `8cc190` 系 11。
**`414ad0` は m11 survey の OOB 最上位 frame に現れない** (最上位 frame は上表 16 種)。 ※ #663 で訂正: 旧 frames は oob の最上位を捨てていたため、修正後は `414ad0` が最上位 (unit 149/158/280/659)。REPORT_663 §2-1。重なるのは 410360 カスケード
(liftdiff `results/cascade_410360.md`: innermost `f_410360` 573 case、`f_410360<40f9e0` 100 case) と本件の根因 (410320/410360 の VMT 間接 call 脱落) で、
**同一欠陥の別症状である可能性が高い (未検証)**。ただし両者の trap 件数は比較軸 (case と unit) が違うため数値の突合はしていない。
