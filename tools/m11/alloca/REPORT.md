# M11 alloca 縮退修正 REPORT (CAB-129) — tools/m11/alloca/

**判定: 部分達成**。RetDec 集成体ローカル縮退 (`alloca i64` 8B に潰れる) の機械検出+拡幅 pass を新設し、
closure 全 7,421 定義を走査して **63 alloca / 56 関数**を拡幅した (rep stos 定数長 4 サイト = 44bb70/59b100/
95b400/ade4d0 は全て 8→392B で正式修正)。回帰は全て不変 (m11_e2e stage 4/6・survey ok 812/trap 83・
shimx 純リンク 17unit は同等以上)。**shimx 純リンク起動の unit 17 破壊 (GetVersionExW 284B→8B) は本修正で
解消** (偽の dllmain_done が消え unit 18 到達)。一方で **survey の OOB/halt0 は 1 件も変化しなかった** —
残存 trap の原因は alloca ではなく load 系 lift 欠陥 (CAB-231) と FastMM/スタブ品質であることを per-unit
実測で特定した。survey OOB 41→0・trap<20 は **未達** (到達値は下表)。

再現: `bash tools/m11/alloca/e2e.sh` (前提 `bash tools/m11/m11_e2e.sh` 1 回; 約 3 分。`ab_baseline.sh` で
修正前 A/B も再現可)。常時 exit 0。

## 1. 実測サマリ (修正前 → 修正後, 全数実測)

| 項目 | 修正前 | 修正後 |
|---|---|---|
| mainline reached_stage (m11_judge) | 4/6 | **4/6 (不変)** |
| mainline 通常起動 units_run / total | 17 / 942 | **17 / 942 (不変)** |
| mainline survey (m11_survey.mjs) ok/trap | 812 / 83 | **812 / 83 (不変)** |
| └ trap 内訳 oob / halt0 / abort | 34 / 48 / 1 | 34 / 48 / 1 |
| mainline survey (survey_trace 手順) ok/oob/halt0 | 800 / 50 / 44 | 800 / 50 / 44 |
| shimx --fix survey ok/oob/halt0 | 800 / 41 / 53 | 800 / 41 / 53 |
| shimx **純リンク** survey ok/oob/halt0 | 807 / 44 / 44 | 807 / 44 / 44 |
| shimx 純リンク起動 (run_trace) units_run | 17 (**偽完走**: dllmain_done=true, init_count_var=0 破壊) | **17 (実完走)** → unit 18 で EnumCalendarInfoW table index (既知, cb_adapt 対象) |
| └ init_count_var | 0 (shadow stack 破壊) | **18** |
| wasm サイズ | 6,008,101 B | 6,008,690 B (+589) |
| build (wasm-ld) signature mismatch / undefined | 0 / 0 | 0 / 0 |

trap 計 (oob+halt0+abort, shimx --fix survey) は 95 → **95**。目標 trap<20・OOB 41→0 は未達
(§4 の理由)。alloca 修正の効果は survey 集計ではなく **(a) 純リンク unit 17 の破壊解消** と
**(b) 縮退サイト全数の構造修正** として効いている (§3)。

## 2. pass (`m11_alloca.py`) の仕様と検出実測

`boot_final.ll` (closure 全定義 7,422 = `function_*` 7,421 + `entry_point` / うち alloca 保持 6,087 関数) を走査し、
**alloca 実体積 < 使用箇所の要求サイズ** の場合だけ `alloca T` → `alloca [K x i64]` に書換える (ptr 値・他の IR は不変, idempotent —
再実行は byte-identical, `llvm-as` 通過確認済)。

| 規則 | 証拠 | 検出サイト | 拡幅 |
|---|---|---|---|
| R1 | `__asm_rep_stos{b,w,d,q}_memset(dst,v,N)` 定数 N | 4 | **4** |
| R2 | `__asm_rep_movs{b,w,d,q}_memcpy(dst,src,N)` 定数 N | 5 | 5 |
| R3 | `function_40d210` = Delphi FillChar(dst,len,..) 定数 len | 16 | 16 |
| R4 | llvm.memset/memcpy/memmove 定数 len | 0 | 0 |
| R5 | Win32 出力パラメータ表 (GetVersionExW 284B 等, shimx_link/fix_alloca.py と同表) | 24 | 18 |
| R6 | Win32 (buf,count) 表 — count 定数なら buf ≥ count×要素幅 (GetLocaleInfoW cch×2 等) | 12 | 11 |
| R7 | 直接 store の型幅 > alloca 実体積 (i128 store 等) | 39,017 走査 | 9 |
| **計** | | | **63 alloca / 56 関数, 追加 stack +269,874 B (最大 1 件 188,408 B @408b60)** |

- **R1 の 4 サイトがチケットの対象そのもの**: `44bb70` / `59b100` / `95b400` / `ade4d0` が全て
  `alloca i64` + `rep stosq ×49` (=392B) で、ネイティブ逆アセンブル (`sub rsp,0x1b8` + `lea rdi,[rbp+0x28]`,
  boot0.drc.dsm 0x44bb70) と突合済み。**8→392B で正式修正** (shimx_link/fix_alloca.py の計測用回避を正式化)。
- R6 が新規に拾った代表例: `446370` の `GetLocaleInfoW(.., buf, 256)` → buf `alloca i64` 8B を **512B に拡幅**
  (shimx の機能実装 GetLocaleInfoW が 8B alloca に書くと frame を破壊する)。
- dst/%bc の解決は bitcast 連鎖を辿る。GEP / ptrtoint+add 経由の参照は closure 実測 **0 件** (pass が
  発生時に警告する機構付き, 実行時警告 0)。
- shimx_link/fix_alloca.py (24 alloca / 23 関数) に対し本 pass は 63/56 — API 表 + rep stos に加え
  FillChar / rep movs / count-buf / 広 store を一般化した上位互換 (R5 のみ同表継承)。

## 3. 効果の実測

1. **shimx 純リンク起動の unit 17 破壊が解消** (§1 表): 修正前は unit 17 (`function_454090`) の
   `GetVersionExW` が 284B を 8B alloca に書き InitUnits のローカルを破壊 → **偽の dllmain_done**
   (shimx_link REPORT §3-#2 の「偽の DllMain 完走」)。修正後は 17 unit を破壊無しで通過し unit 18 に到達
   (init_count_var 0→18)。残る unit 18 の `table index is out of bounds` は EnumCalendarInfoW コールバック
   変換 (cb_adapt / shimx T2) の管轄で、--fix 付きビルドでは従来どおり 17 unit + #18 OOB まで到達。
2. **mainline/survey が不変の理由 (実測)**: 修正前 survey では縮退 alloca への定長超過書込みが
   survey の 942 unit のどの outcome も変えていなかった (per-unit 差分 0 件を 3 ビルドで確認)。
   survey の OOB は残存 load 系欠陥・FastMM・スタブ由来 (§4)。

## 4. unit #18 OOB の残存原因 (alloca 修正でも完走しないことの検証)

* **通常起動 (full run)**: `455790 → 44bb70 → 446400 → 4133f0 (_UStrAsg, m11_ov C override)` で OOB。
  トレース実測では最終呼出は `UStrAsg(dest=0x10a96158, src=0)`、OOB は **旧値 `Q(dest)` が garbage** なため
  `D(old-8)` 参照で発生。dest は 44bb70 record (拡幅済 392B) の +16 で、**memset(392B) 後に別の lifted 呼出し
  (447860/4473f0/447510 → 447e30/450540 系) が record+16 へ garbage を書いている** = liftdiff (CAB-121) が
  特定した load 取り違え系と同系統 (CAB-231 対象)。446400 自体の UStrAsg site は +0..+56 の 7 件のみ。
* **survey (隔離実行)**: unit #18 は **44bb70 に到達する前**の `455790 → 455100 → 41a510 → 41a530 →
  GetMem(16) → 407a50 (FastMM_GetMem)` 内で OOB (wasm 関数 index 突合)。unit 1〜17 は全て ok なので
  前段 unit の破壊ではなく FastMM lift / survey 状態の固有問題。修正前後で同一 (per-unit 差分 0)。
* 「44bb70 を 392B 配列で C 転記すると survey OOB 34→33」(m11 REPORT §4) は本 pass では**再現しなかった**
  (survey 差分 0)。実験の詳細 (転記範囲・併用修正) は未コミットのため検証不能 — 記録として相違を明記する。

## 5. halt0 53 unit × GetLocaleInfoW 相関 (チケット任意項目) — **相関は否定**

shimx --fix survey の per-unit shim 呼出実測:

* halt0 53 unit 中 **GetLocaleInfoW を呼んだ unit は 0 件** (GetLocaleInfoW を呼ぶ unit は closure 全体で
  unit #18 のみ, kind=oob)。** halt0 の実態は Delphi の unit 初期化が失敗して `Halt(0)` する経路**:
  42/53 unit が `MessageBoxA 'Runtime error 0 at 0x…'` を出し、発生アドレスは 2 箇所に集約
  (0x1027A4B0 ×17 / 0x112C03xx クラスタ ×25)。
* 直前 shim 呼出 unit 数の最頻は `TlsGetValue` 52/53, `MessageBoxA` 42, `LoadStringW` 22 —
  ロケール API ではなく **LoadStringW=0 (リソース未接続) と TLS/ランタイム初期化の失敗系** が halt0 の主因候補。
  → 対応は shimx/hostbridge (LoadStringW のリソース provider 接続) と load 系欠陥修復 (CAB-231) の両方が必要。

## 6. 8cbcb0 系 OOB (チケット任意項目) — 本体は忠実な lift, 原因は上流

`8cbcb0` の IR は逆アセンブルと**意味一致** (rax=[rcx+8]; 0 なら 0; else rax=[rax-8]×2; 0 なら 4; call 8cbb00)。
OOB は引数 `rcx` の指す [rcx+8] / [rax-8] が garbage なためで、呼出元 `8cc190 ← 8c7a10 ← 8c5cc0` の
生成するポインタ不正 (load 系欠陥) が原因。8cbcb0 単独の修正対象ではない (CAB-231 へ)。

## 7. disable 化した欠陥リスト (本チケットで対処せず保持, 実測の根拠付き)

| # | 欠陥 | 影響 (実測) | 行先 |
|---|---|---|---|
| 1 | load 取り違え系 (`load_dropped` 892 / `spill_slot_deref` / 4133f0・409c80・4123c0) | survey OOB の主体。unit #18 full-run OOB (record+16 の garbage 旧値) も同系統 | **CAB-231** |
| 2 | survey unit #18 の FastMM `407a50` GetMem OOB (455100→41a530 経路) | survey oob 1 件 (44bb70 前段で発生) | CAB-231 + FastMM 単体検証 |
| 3 | halt0 53 unit (Runtime error 0, 発生点 2 箇所集約) | trap 計 95 の 53/95。LoadStringW=0・TLS 系 | shimx LoadStringW リソース接続 + CAB-231 |
| 4 | EnumCalendarInfoW コールバックが table index で trap (純リンク unit 18) | 純リンク起動の停止点 | shimx T2 (cb_adapt の正式化) |
| 5 | VirtualAlloc 巨大要求 355MB×2 (unit #18, サイズ算出の未初期化値) | full run で 711.7MB 確保 | 未着手 (m11 REPORT §4 からの残置) |
| 6 | `ucomisd/comisd` flag 未反映 (fcmp 0 件) | FPU 比較分岐の意味未保証 | 未着手 (m6 [P1] 未移植) |
| 7 | sigfix の不足引数 0 詰め (callsite_arg_drop 312) | 意味未保証 | CAB-231 / 別 pass |

## 8. 再現手順

```sh
bash tools/m11/m11_e2e.sh          # 前提: lift 成果物 (初回は --full)
bash tools/m11/alloca/e2e.sh       # pass 適用 → mainline build/実行 → shimx 純リンク + survey → 集計表
bash tools/m11/alloca/ab_baseline.sh  # 修正前 IR での純リンク A/B (survey) 再現
python3 tools/m11/alloca/m11_alloca.py IN.ll OUT.ll --report r.json   # pass 単体
```

注意: `e2e.sh` は `work/boot_final.ll` を in-place 改変する (素 IR は `work/boot_final.prealloca.ll` に退避)。
`m11_e2e.sh --full` で素の IR に戻るため、その後は `alloca/e2e.sh` の再実行で再適用する。

## 9. 成果物 (tools/m11/alloca/)

| ファイル | 役割 |
|---|---|
| `m11_alloca.py` | 縮退検出+拡幅 pass (R1〜R7, idempotent, GEP/ptrtoint 警告付き) |
| `e2e.sh` | 1 コマンド検収 (pass 適用 → mainline → shimx 純リンク → 集計) |
| `ab_baseline.sh` | 修正前 IR での shimx 純リンク A/B 再現 |
| `summarize.py` | baseline 比較表 (`results/summary.json`) |
| `results/alloca_report.json` | pass の全拡幅サイト (function/alloca/was→now/規則) |
| `results/baseline/`, `results/run/`, `results/survey/` | 修正前後の実測生データ (survey per-unit JSON 含む) |

`work/` (gitignore) に一時物。`tools/m11` 既存ファイル・`tools/shimx` は**無改変** (git diff 0 行)。

## 10. 下流チケット案

1. **CAB-231 (既存): load 取り違え IR 修復 pass** — 本 REPORT §4/§7-1 の通り unit #18 完走と survey OOB
   掃滅の最優先。回帰判定は liftdiff `batch` verdict と本 e2e の survey 差分で機械化可能。
2. **halt0 53 unit の起動失敗トリアージ**: `Runtime error 0` 発生点 2 箇所 (0x1027A4B0 / 0x112C03xx) の
   静的対応付け → LoadStringW リソース接続 (shimx hostbridge) との切分け。
3. **survey の FastMM OOB (#18, 407a50)**: FastMM_GetMem を liftdiff の boot-state 移送付きで単体差分し、
   survey 状態での破れ点を特定。
4. **cb_adapt (EnumCalendarInfoW) の正式化**: 純リンク起動が unit 18 で止る最後の shimx 側要素。
