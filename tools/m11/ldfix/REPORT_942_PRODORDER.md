# REPORT_942_PRODORDER — 本番の IR 生成順を snapshot に当てた boot / survey の A/B と、unit 56 の切り分け (#942 受入 1・2・3)

既知類型との関係: unit 56 (`function_8c5eb0`) は DEFECTS.md の **D19** (件数 0 のループで本体が 1 回以上実行される・機械語の入口ガードが IR から脱落) と同型。修復は既存の `tools/m11/guard699/m11_guard699.py` (本番 `m11_build.sh` に組込み済み) を使う。unit 17 は alloca 縮退 (REPORT_942_ALLOCA)、unit 87 は refcount 系 (REPORT_942_QSTORE と同じ観測)。新規類型は判定しない。DEFECTS.md は変更しない。

## 0. 結論

- ldfix_e2e の入力 (snapshot `boot_final3.ll`) は本番の IR 生成順より前にある。本番の後段 (qstore → alloca → guard699 → guard4fa210) と ld108・ld115・src412770 を snapshot に当てると、**通常 boot は完走する** (units_run 17 → 109・threw なし・`DllMain attach 完走` の Halt0 経路で終了)。
- 同じ順で ldfix 無し (base) と ldfix 有り (fix) を比べると、boot は両方とも完走し結果は同じ。**boot threw は ldfix 起因ではなく、既存の欠陥 (unit 17 の alloca 縮退・unit 56 の D19・unit 87 の refcount 系) が本番の修復を経ていない snapshot に残っていたため**。
- unit 56 (VA 0x16fde0) の原因: `8c5eb0` の入口ガード (`cmp idx, count-1; jg`) が IR から脱落し、件数 0 で本体が 2 回回る。2 回目に基底 0 + 8 の要素番地 `0x8` を読み、`0x670067` (UTF-16 "gg") を `function_8c6530` に渡して trap。guard699 で消える。
- 本番順の survey は trap 22 件 (OOB 14・halt0 8)。元の 9 件のうち 17・53・56・87・138・158 は trap 一覧から消え、144・149 (OOB) と 114 (halt0) が残る。ldfix の効果は unit 895 の 1 件 (OOB → halt0) のみ (r8b を含まない chain での判定。§1 の注)。

## 1. 測定 (測定 commit `c9d365465`。以後のコード差分は §6)

測定コマンド (すべて `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP`・load は各コマンド終了直後):

| コマンド | 所要 | rc | 結果 |
|---|---|---|---|
| `bash tools/m11/ldfix/ldfix_e2e.sh` | 61 秒 | 0 | judge PASS。stage4 units 17/942・threw OOB (base = fix)。survey ok 136 / trap 9 (base = fix)。load 0.93 / 0.93 / 0.73 |
| `bash tools/m11/ldfix/alloca_ab_942.sh` | 41 秒 | 0 | raw / alloca / only44bae0 の A/B (§2) |
| `bash tools/m11/ldfix/prod_order_942.sh fix` | 51 秒 | 0 | 本番順 (ldfix → ld108 → ld115 → src412770 → qstore → alloca → guard699 → guard4fa210) |
| `bash tools/m11/ldfix/prod_order_942.sh base` | 51 秒 | 0 | 同じ後段を ldfix 無しの snapshot に当てる (base) |
| `probe_alloca_942.py` → `stage4.sh probe_alloca` → `trap56_probe_942.mjs` | 12 秒 (読出し) | — | unit 56 の記録 (§3) |

| 変種 | 入力と追加した段 | units_run | threw | 完走 (Halt0 経路) | survey ok / miss / trap (OOB・halt0) |
|---|---|--:|---|---|---|
| raw | `boot_final3.ll` | 17 | OOB | なし | 136 / 14 / 9 (8・1) |
| alloca | raw + alloca (`m11_alloca.py`) | 52 | OOB | なし | 868 / 47 / 26 (19・7) |
| only44bae0 | raw の `function_44bae0` の `stack_var_-88` だけ拡幅 | 17 | なし | Halt0 (`Runtime error 0` 表示あり・完走ではない) | 136 / 14 / 9 (7・2) |
| **prod base** | raw → qstore → alloca → guard699 → guard4fa210 | **109** | なし | **Halt0 (`DllMain attach 完走`・Runtime error 表示なし)** | 872 / 47 / 22 (15・7) |
| **prod fix** | ldfix_fixed → ld108 → ld115 → src412770 → qstore → alloca → guard699 → guard4fa210 | **109** | なし | **Halt0 (`DllMain attach 完走`・Runtime error 表示なし)** | 872 / 47 / 22 (14・8) |

- 本番順の変種は、本番の pass を weak 化の前の IR に当てる前提を再現する。snapshot は post 済み (weak 付き) のため、照合対象 4 関数 (`8c5eb0`・`8ca670`・`4fa210`・`666a60`) の define 行だけ一時的に weak を外し、チェーン末尾で戻す (`prod_order_942.sh` の `unweak`・`reweak`)。
- 「本番順」は、測定 commit `c9d365465` の `m11_gen_ir2.sh` の段 (ldfix → ld108 → ld115 → src412770) と後段 (qstore → alloca → guard699 → guard4fa210) の順。`fix_r8b815050.py` は含まない。測定 commit の `m11_gen_ir2.sh` に無く、main では `5c43ea98a` (#1448) で後から入り既定で適用される。r8b を含めた本番順の判定は #3608 (項目 3)。
- 完走の確認: M11_TRACE=1 の run で `[m11][longjmp] Halt0 -> RestoreContext: DllMain attach 完走として JS 例外で巻き戻す` を確認。`Runtime error` の表示は無い (only44bae0 では同じ経路で Runtime error が出ていた)。`dllmain_done=True` は Halt0 経路も含むため、完走の判定はこの行で行う。
- 本番の m11_build.sh 全体 (m11_post・argrecover・計測専用の instr 段・m11_ov.c の C 上書き) は走らせていない。本測定は再現 chain の範囲。

## 2. alloca 変種 (参照・REPORT_942_ALLOCA の再測)

- boot の trap は unit 56 (0x16fde0・`function_8c6530`・IR 版)。unit 17 は alloca で消える (boot は 52 units まで進む)。
- alloca 変種の survey trap 26 件中、unit 56 の最内 frame は `function_8c6530`。chain は `function_8c6530 ← function_8c5eb0 ← function_56fde0 ← m11_tr_function_56fde0 ← m11_icall`。

## 3. unit 56 の切り分け (alloca 変種・`probe_alloca_942.py`)

- x86 (`tools/m11/ldfix/pe_disasm_va.py` で 0x8c5eb0 を逆アセンブル): `0x8c5f0c mov ebx,[rcx+0x14]` (件数) → `0x8c5f0f sub ebx,1` → `0x8c5f15 cmp [rbp+0x4c],ebx; 0x8c5f18 jg 0x8c6066` (入口ガード。件数 0 では本体を飛ばす) → 末尾 `0x8c605b sub ebx,1; 0x8c605e test ebx,ebx; jne 0x8c5f23`。
- IR (alloca 変種) の `dec_label_pc_8c5ef5` は件数を読んで無条件に `dec_label_pc_8c5f23` へ `br` する (ガード脱落)。末尾の `%66 = add nuw nsw i64 %rbx, 4294967295` は残り回数が 0 にならない限り続く。
- probe の記録 (`trap56_probe_942.mjs`・trap 時点・ring 32 件): `function_8c7450(obj, idx)` の呼出しは unit 56 で 2 回。

| 回 | idx | `[obj+20]` (件数) | `[obj+8]` (基底) | 要素番地 | 戻り値 |
|---|--:|--:|--:|---|---|
| 1 | 0 | 0 | 0 | `0x0` | `0x4bdb50` (OK) |
| 2 | 1 | 0 | 0 | `0x8` | `0x670067` (UTF-16 "gg") → `function_8c6530` の `arg2` で trap |

  - `obj = 0x10bc4e40`。件数 0 で本体が 2 回回る。32 bit の残り回数は 0 → -1 (`0xFFFFFFFF`) となり、IR は `icmp ne` で継続する。
  - `function_8c6530` の probe (同じ run): `arg1 = 0x10b698c0`・`arg2 = 0x670067`・`arg3 = 0x67006f`。
- 修復: guard699 (`icmp sle i32 %9, 0` の分岐を復元する IR pass) を足すと unit 56 の trap は消える (作業変種・参考: boot は 83 units まで進み、次の trap は unit 87 の `function_418190` (C))。本番順の変種では guard699 を含み、boot は完走。

## 4. 本番順の残 trap (fix 変種・22 件)

`tools/m11/ldfix/work/prod942_fix/trap_units.json` を `m11_wasmnames.py` で IR 名に戻したもの (最内 frame ← 呼出し元 1 段)。halt0 は Halt 呼出し (trap ではない)。

| unit | VA | 種別 | 最内 IR 関数 @ wasm 位置 | 呼出し元 |
|---|---|---|---|---|
| 114 | 0x223840 | halt0 | — | — |
| 144 | 0x25c540 | OOB | `function_44aeb0` @0x1746aa | `function_44f040` ← `function_653660` |
| 149 | 0x264260 | OOB | `function_412e40` @0x6b6cd | `function_653660` ← `function_6539e0` |
| 245 | 0x333090 | halt0 | — | — |
| 275 | 0x40e170 | OOB | `function_864fe0` @0x93804 | `function_80e040` ← `function_80e140` |
| 279 | 0x4136d0 | halt0 | — | — |
| 280 | 0x416010 | OOB | `function_6cefb0` @0x21d80a | `function_815050` ← `function_815e10` |
| 314 | 0x4e48a0 | halt0 | — | — |
| 368 | 0x5810f0 | halt0 | — | — |
| 477 | 0x6bfd60 | OOB | `function_903d20` @0x2771d4 | `function_904190` ← `function_abfd60` |
| 484 | 0x6d0680 | OOB | `function_903e00` @0x27722d | `function_904190` ← `function_ad0680` |
| 492 | 0x6d5700 | OOB | `function_4133f0` (C) @0x35305f | `function_4473f0` ← `function_446400` |
| 509 | 0x739ca0 | halt0 | — | — |
| 513 | 0x7654c0 | OOB | `function_903e00` @0x27722d | `function_904190` ← `function_b654c0` |
| 520 | 0x776bf0 | OOB | `function_903e00` @0x27722d | `function_904190` ← `function_b76bf0` |
| 647 | 0x897ac0 | halt0 | — | — |
| 659 | 0x8eaa30 | OOB | `function_6cefb0` @0x21d80a | `function_815050` ← `function_815e10` |
| 745 | 0xabb3b0 | OOB | `function_407e20__lifted` @0x13d731 | `function_407e20` ← `function_409440__lifted` |
| 830 | 0xcd50d0 | OOB | `function_10c7cd0` @0xb240d | `function_10d50d0` ← `m11_tr_function_10d50d0` |
| 880 | 0xe63540 | OOB | `function_125da90` @0xea5d5 | `function_1263540` ← `m11_tr_function_1263540` |
| 895 | 0xeddfe0 | halt0 | — | — |
| 923 | 0xf6c660 | OOB | `function_410b10` @0x355403 | `function_410730` ← `function_4fb910` |

- base 変種との差: unit 895 のみ (base = OOB 最内 `function_40ff70`・fix = halt0)。他の unit は wasm 関数 index のずれ (ldfix で関数が増減するため) を除き同一。
- 注 (r8b): 残 trap 280・659 の chain は `function_6cefb0 ← function_815050` で、r8b の対象 (`function_815050` の 6cefb0 第 3 引数) と重なる。r8b を含めた chain では、この 2 件と unit 895 の判定が変わり得る (未測定)。
- 元の 9 件 (ldfix_e2e の trap 一覧) との対応: 17・53・56・87・138・158 は本番順の一覧に無い。144・149・114 は残る。

## 5. 受入への反映

- 受入 1 (trap 9 件の原因): **部分**。元の 9 件のうち 17 (alloca 44bae0・単独で確認)・56 (D19・guard699 で単独で確認)・53/87/138 (qstore 系・本番順で消える。個別の寄与は未切り分け)・158 (本番順で消える。寄与は未切り分け) は本番順で消えた。残る 144・149 (OOB) と 114 (halt0) の引き金は未確定。
- 受入 2 (boot threw の原因): **達成** (判定: ldfix 起因ではない)。ldfix_e2e の base/fix は同じく threw。本番順の base と fix は両方とも完走 (units 109・Halt0 完走)。原因は既存の pass の未適用 (alloca・guard699・qstore 系)。ただし本測定は再現 chain の範囲で、本番 `m11_build.sh` 全体は未実行。
- 受入 3 (件数反映): **部分**。ldfix_e2e の snapshot 測定は base = fix (変化なし)。本番順では survey の ok は両方 872、trap は両方 22 で、ldfix の効果は unit 895 (OOB → halt0) の 1 件だけ (r8b を含まない chain での値)。現 main の判定は #1292 / #1469 で別に実施済み。

## 6. 差分 (`docs/WORKFLOW.md` §6)

- 測定 commit: `c9d365465` (trap56 プローブの読出し修正の commit。この commit までで測定に使うコード・スクリプトは固定)。
- 差分 (測定経路): `git diff --stat c9d365465 -- tools/m11/ldfix/ldfix_e2e.sh tools/m11/ldfix/alloca_ab_942.sh tools/m11/ldfix/prod_order_942.sh tools/m11/ldfix/stage4.sh tools/m11/ldfix/run_stage4.mjs tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/trap_units.mjs tools/m11/m11_build.sh tools/m11/alloca tools/m11/guard699 tools/m11/guard4fa210 tools/m11/qstore tools/m11/ldfix/fix_ld108.py tools/m11/ldfix/fix_ld115.py tools/m11/ldfix/fix_src412770.py tools/m11/ldfix/ldfix.py` の出力は `tools/m11/ldfix/prod_order_942.sh` の 1 件だけ (ヘッダのコメント 2 行の追加・1 行の変更)。実行行の差分は 0 (`diff <(git show c9d365465:tools/m11/ldfix/prod_order_942.sh | grep -vE '^\s*#') <(grep -vE '^\s*#' tools/m11/ldfix/prod_order_942.sh) | wc -l` → 0)。測定 commit 以後にリポジトリ全体で変わったのは、本 REPORT・`docs/DOC_MAP.md`・`prod_order_942.sh` (コメント)・`boot_trap_942.mjs` (診断スクリプトの削除。測定の表には無い) だけ (`git diff --stat c9d365465 -- .`)。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 本番順の survey 残 trap 22 件のうち 144・149 (OOB)・114 (halt0) の引き金 | 受入 1 | #3608 ([CI-171]) |
| 53・138・158 の消失の寄与が qstore / ld108 / ld115 / src412770 のどれか (段ごとに切り分けていない) | 受入 1 の帰属 | #3608 ([CI-171]) |
| ldfix_e2e の入力 (snapshot = 本番順より前) を本番順に替えるか (base/fix の基準が変わる) | 測定の基準 | 決定 (PM 判断): 替えない。現行の入力のまま (本番順は `prod_order_942.sh` で別に測定済み)。戻す場合は `ldfix_e2e.sh` の入力を差し替えて再測定 |
| 本番 `m11_build.sh` 全体 (m11_post・argrecover・instr 段・C 上書き) での boot 再確認 | 受入 2 の範囲 (本測定は再現 chain) | #3646 ([CI-172]・親: #942)。決定 (PM 判断): 本 PR の範囲外として子 issue に起票 |
| work-m11 の IR と現 main の不一致 | 測定の母体 | PM agent の判断待ち: 追跡先 (#680 は closed で、対応する open issue が無い)・既定案: 新規の子は起票せず本表に残す (測定の母体は測定 commit で固定) |
| F3c 関数の件数の変化 (旧 33 → 現 43) の出所 | 受入 3 | #3608 ([CI-171]・項目 4)。現 43 の出所は下の再測定の出力行。同じ入力での 33 → 43 は REPORT_1325 §6 にも記録 |

F3c 件数の再測定 (測定 commit `c9d365465` の `ldfix.py`・入力 `tools/m11/work/boot_final3.ll`): `cd tools/m11 && python3 ldfix/ldfix.py work/boot_final3.ll out.ll --pe <block00031_PE.bin> --report out.json` (約 41 秒・rc 0) の出力行は `F1=0 F1v=0 F2=0 F3a=2 F3b=0 F3c=43 F3d=0 F4=10 (errors=0)`。旧 33 は REPORT_942 の測定時点の値。

## 8. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP   # 素材展開後
bash tools/m11/ldfix/ldfix_e2e.sh                               # 修復段 (work/ldfix_fixed.ll) と base/fix
bash tools/m11/ldfix/alloca_ab_942.sh                           # raw / alloca / only44bae0 (work/ab942/alloca.ll)
bash tools/m11/ldfix/prod_order_942.sh fix                      # 本番順 (ldfix 有り)
bash tools/m11/ldfix/prod_order_942.sh base                     # 本番順 (ldfix 無し)
python3 tools/m11/ldfix/probe_alloca_942.py tools/m11/ldfix/work/ab942/alloca.ll tools/m11/ldfix/work/ab942/probe_alloca.ll
bash tools/m11/ldfix/stage4.sh tools/m11/ldfix/work/ab942/probe_alloca.ll probe_alloca
S4_NAME=probe_alloca S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap56_probe_942.mjs
```
