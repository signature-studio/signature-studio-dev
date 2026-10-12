# tools/m7/REPORT.md — M7 準備 (m6.sh 1 コマンド E2E 化 + f32 引数接続 PoC)

> **参照専用 (LIFTLIB-1 / #224)**: 本 dir の lift IR pass・スクリプトは新規実行・改変しない。IR pass の正本は `tools/liftlib` (対応表: `tools/liftlib/README.md`「旧 dir pass → liftlib 対応表」)。既存 e2e 成果物・本 REPORT は歴史として残置し、旧成果物に対する既存 e2e (`tools/m7/m6_e2e.sh`・m8/m9/m10 の `*_e2e.sh`) が引き続き PASS することは `tools/liftlib/REPORT.md` §15 で実測。

- 日付: 2026-10-10。HEAD 基点: 188479b。M6b 検収 (wasm 署名不一致 0 / undefined 57 種 /
  t1 run complete / t3 OK / trap_test OK 6 FAIL 13) を前提に subagent 実行。
- 成果物: `tools/m7/` 配下のみ。`tools/m6/` / `tools/m5/` / `tools/shim/` は読取のみ
  (work/ 直下の未管理再生成物を除く; tools/m6 スクリプト自体の改変は 0 行)。
- `docs/REFERENCES.md` `[STRATEGY]` (repo 外) は本 tree に存在しない (find で確認)。M7 の完了条件は
  `docs/REFERENCES.md` `[STRATEGY]` §4 と tools/m6/REPORT.md §8 を根拠に代読。
- 検証環境: node v26 / emcc 6.0.12 / Python 3.14 / RetDec 5.0 / llvm-as 21.1.8 (parse 検証)。

## 0. 結論

| 項目 | 結果 |
|---|---|
| (1) m6.sh 1 コマンド E2E 化 | **達成** — `bash tools/m7/m6_e2e.sh` (exit 0)。m6_lift.sh (既設手順) → ir6 pass 鎖 (ir6_pass/ir6_shift/ir6_gdata) → m6_build.sh (memfix/extract 内蔵) → m6_simd_check → node t1/t3/trap_test 直列化。検収数値の数値照合組込 + e2e_result.json 出力。lift 再実行の非決定性 artifact (`add i64 0, i64 %X` 系 / 重複 declare) への lift 直後 fixup を内蔵し、再 lift 後も検収数値が bit まで再現 (t1_out.hex SHA 一致) |
| (2) missing 11 分類表 | **作成** — (11 種 → hand C stub 7 種 / no-op 1 種 / Win API 参照値 2 種 / 既存方針 (lock, caller broken-lift 待ち) 1 種; DSP 数値経路外確認)。2026-10-12 の再編で報告内容は本節に吸収しファイルは削除 |
| (3) f32 引数接続 IR pass PoC | **PoC 達成 (pattern B 接続 + pattern A 本体再生成)** — tools/m7/ir7_argpass.py が (i) closure lift の setParameter 2-arg 本体退化・签名失失を検出し (ii) 呼出 site の xmm2 bits (呼出直前 `__asm_movss(i32)` で IR 上に回収可能なまま捨てられている) を 3rd arg 化し (iii) dsm から jump table 20 case (store slot / clamp 定数 / flag 群) を機械抽出して本体 define を再生成する。駆動実測: value bits → member slot (obj+0x2dc/0x2d8) と param chunk (`[obj+0x138] + sext(i32 obj+0x28)*108` → 0x108cd890) へ bit 保存まで接続確認。index 19 = 0 (flag byte 0x326 をクリア) で `processReplacing` が rc 0 に復帰し、t1 出力が baseline の 9 種 denormal 群 `{0, 0x19DEE8xx…}` から実数値 `{0, -6.0f (0xffc00000)}` へ変化 (2 run bit-determinism ✓)。bit-exact 512/512 は未達 — 理由は §3-(d) |

## 1. (1) m6.sh 1 コマンド化 — m6_e2e.sh

- 配置: `tools/m7/m6_e2e.sh` (新規)。tools/m6 側スクリプトは一切改変なし (直列化のみ)。
- 直列化内容:
  1. `m6_lift.sh` (RetDec select-ranges → ir_normalize → ir5_patch; `--full` で完全再生、
     既定は work 産物再利用)
  2. lift 直後 fixup (tools/m7 内蔵; RetDec 再実行の非決定性に対応):
     - `add i64 0, i64 %X` → `add i64 %X, 0` (数学等価; 実測 4 件/lift 再実行毎 0〜4 件)。
       ir5_patch.py:459 コメントの既知の parse error 系 lift 出力瑕疵に相当。
     - 重複 `declare` の dedupe (実測 2 件)。
  3. ir6_pass.py → ir6_shift.py → ir6_gdata.py (既存 3 pass 鎖; ott_shift3b.ll 正本へ反映, 旧正本は .prev 待避)
  4. `m6_build.sh` (m6_memfix → m6_full_extract → emcc; 出力 tee → build_e2e.log)
  5. 数値照合 (elicit 組込): signature mismatch 0 種 / undefined symbol 57 種
     (内訳: function_18xx 33 / `__asm_*` 0 / Win,CRT API 24) / m6_simd_check.py の
     実数検出 (decl def mismatch 0 / callsite mismatch 0)
  6. node t1/t3/trap_test 直列実行
- 固定パス化: t1 出力は **tools/m6/work/t1_out.hex に固定** (script 内で必ず
  tools/m6/work に cd してから node 起動する絶対位置方式; t1.mjs の `'./t1_out.hex'`
  が cwd 依存である点は M6 REPORT §9 に既記載だが、m6 側 file は改変していない)。
- 検収判定 (全項目 OK/NG 判定, exit code に反映):
  ```
  [OK] signature mismatch 種: 0
  [OK] undefined symbol 種: 57      (function_18*: 33 / __asm_*: 0 / Win・CRT API: 24)
  [OK] simd decl def mismatch: 0 / simd callsite mismatch: 0
  [OK] t1_out.hex 行数: 512 + determinism bit 一致 (2 run, SHA256)
  [OK] t3 [OK] 検出 1 (= mem[0x30260ce0] == 0x2DDFA232)
  [OK] trap_test OK 6 / FAIL 13
  ```
  実測: **全 OK (exit 0)**。`t1_out.hex` SHA = f34a6a46798b0a65cb0709def7e87367970c5fa5a9188…、
  新鮮 lift で再生した鎖でも semantically-bit 一致 (lift_fixup 後)。

## 2. trap_test 検収の再現と missing 11 の分類

- e2e 中 trap_test 実測: OK 6 / FAIL 13 (missing 11 = wasm import "missing function"
  fail-fast abort + broken-lift OOB 2 = function_1801c69cc / c91cc, ir6_shift が
  算術合成 base を remap できずの OOB のまま — M6 REPORT §7-6)。
- 分類表 (2026-10-12 の再編で本節に吸収済み)。要点:
  - runtime 到達 missing 11 は **すべて DSP 数値経路外** (CRT lock / UCRT
    invalid-parameter 報告 / PE app-policy (GetModuleHandleW) / locale・wide 変換
    (MultiByteToWideChar) / module refcount 管理 (lock inc/xadd))。
  - 対応量推定: **hand C stub 7 種 (#2/4/5/7/9/10/11 — うち wmemcmp・bit 演算・状態判定
    leaf 4 種 #2/4/5/7 は bit-exact 検証可能, #9/10/11 は lock/refcount 演算) +
    no-op stub 1 種 (#3, UCRT 報告系) + Win API 参照値 stub 2 種 (#1/8)** = 新規実装
    10 種 + 既存方針 1 種 (#6 — caller broken-lift OOB のため本体と並行で対処) = 全 11 種
    (m6_rt.c / m6_stubs.c 既存規模の延長; buyer-stub-for-OK 運用)。
  - FLEEngine (Delphi) 部分 wasm 起動に向けて: Delphi RTL 初期化面が ucrt 初期化
    連鎖に乗るため、上記 lock/app-policy/refcount 群が起動直後到達し得る →
    M8 前の shim 不足面は (i) CRT lock 群 no-op (m6 hand stub 規模) (ii) UCRT
    app-policy 参照値 0 返し (iii) wide 変換の M4 file API 外挿 (JS 側 UTF-16 変換層)。

## 3. [P2] f32 引数接続 IR pass PoC — tools/m7/ir7_argpass.py

M6 REPORT §7-5 (最重要課題) に対する最小修正 PoC。tools/m5/m6 の pass は import せず
tools/m7 配下で独立実装 (pass 鎖実行は m6 スクリプトを復用)。

### (a) 3 pattern の解析 (機械的に特定した証拠)

| pattern | 実物の証拠 | 機序 | 本 PoC の扱い |
|---|---|---|---|
| **A: closure lift signature 推定ミス + 本体退化** | `define i64 @function_180120af0(i64 %arg1, i64 %arg2)` で本体は `%1 = xor i64 0,0; ret` の 3 行 (dsm 実体は MS x64 ABI `(rcx=obj, edx=idx, xmm2=value)` の jump table 20 case) | RetDec が `--select-ranges` で xmm 引数を decode から落とし、かつ jump table 分岐の本体 lift に失敗した | **代替補償**: dsm から 20 case の store 組を機械抽出して本体を再生成 (§3-(b)) |
| **B: 呼出 site の xmm drop (IR 上回収可能)** | ctor 19 件の呼 site で `%324 = call i128 @__asm_movss(i32 %323)` 直前 → `%325 = call i64 @function_180120af0(i64 %arg1, i64 %rdi.10.reload)` と 2-arg で call。**xmm2 値 bits (i32 %323) は IR 上に存在するのに捨てられている** | RetDec は xmm を `__asm_movss(i32)` 疑似 call で表現するため、call 面のみ arg 修正すれば値が渡せる | **採用 (本 PoC の主修正)**: 呼出直前 movss の値 bits を 3rd arg 化 |
| **C: full lift も f32 型引数を持たない** | `grep 'define.*f32 %arg' full_t1.drc.ll` = **0 件** (全 define で f32 引数型が一度も出現しない; 検収再計測 2026-10-10 時点 full_t1.drc.ll 8788 define / f32 型引数 0 件 — define 総数は lift 産物世代に依存。4-arg 形でも arg3/arg4 は GP レジスタ割当) | RetDec ABI 推定は GP レジスタ列のみ; xmm 位置の引数は一律 `__asm_movss(i32)` 疑似呼叫 (i32 raw bits) 表現に落ちる | **概念化に留める**: f32-typed signature への普遍変換は IR 全体を変える重作業のため, i32 raw-bits のまま値流を接続する路線で M8 引継 |

### (b) ir7_argpass.py の作用

- 入力: `work/ott_memfix1.ll` (+ `work/full_t1.drc.dsm`)、出力: `work/ott_argpass.ll`
  (emcc 入力) + `work/argpass_report.json` (pattern 検出 + 20 case 分類)。
- (1) 検出: target の closure define signature/本体退化 (pattern A) と、直前 movss
  + result 未使用の 2-arg call site (pattern B) を報告。実測: callsite 1 / patched 1。
- (2) 本体再生成: dsm から `cmp edx,0x13` + `ja` + `lea r10,[rip - 0x120b0f]` +
  `mov r8d,[r10+rax*4+0x120cb4]` を機械抽出し jump table RVA 20 case を読み出す。
  case slice を 4 文型に自動分類して IR 化:
  - TAIL_AB (4 case): `[rcx+D1]` / `[r9+D2]` 双 store → tail call `function_18011de50` (実機 `jmp` に対応)
  - TAIL_IDX (3 case) / TAIL_IDX_x2 (3 case): `movsxd rax, edx` の index 依存 store
    (x2 版は `addss xmm2,xmm2` → 別 slot `[rcx+idx*4+0x218]` を fadd 転写)。
    検収で 1 件偏差 (2026-10-10): ir7 の idx_store32 は disp を scale 前に加算
    (`(idx+d)<<2`, d=0x20c/0x218) するため member mirror store 先が機械語
    (`[rcx+rax*4+d]`, dsm 0x180120c01) に対し idx≠0 でずれる。chunk store
    (`[r9+idx*4]`, disp 0) は正しく、本 PoC の chunk/flag/TAIL_AB member 結論には
    影響なし (修正は M8 引継 — §3-(d) 5)。
  - CLAMP (2 case): comiss による clamp 分岐。rip 相対定数を linear memory load
    (m6_data install 後の .rdata 実数値: A=0.5f @0x301ee808 / B @0x301fde90 /
    C=1.0f @0x301ee818) で bitcast 参照し `(v > A) ? (v-A)*B+C : v+v` を
    fcmp ugt (comiss+jb の CF/unordered 語義を含む) / fsub / fmul / fadd で転写
  - FLAG (8 case): `ucomiss` (xorps 0.0) → flag byte store — `(unordered || v != 0) ? 1 : 0`
    (jp/jne 両 path を 1 支線に統合) を fcmp uno/une + zext i8 で転写
  - 想定外 instr は assert で落とす (無黙って変えない)
- (3) 呼出書替: `%apz0 = zext i32 %323 to i64` を挿入し 3-arg 化。合成 signature:
  `define i64 @function_180120af0(i64 obj, i64 idx, i64 xmm2bits)`

### (c) 検証 (m7_build.sh + node 実行, すべて fresh lift 鎖上)

- `bash tools/m7/m7_build.sh` — m6 と同一 emcc 引数 + `-sEXPORTED_RUNTIME_METHODS`
  追加、出力 tools/m7/work/ott_argpass.cjs → 成功 (mismatch 0 / undefined 57 種の
  link 状態は e2e と同等)。合成 IR は `llvm-as` parse 検証済み。
- **bits→store 接続確認** (t1_dbg.mjs 実測):
  - `fsetparam(obj, 0, 0.5)`: obj+0x2dc = 1.0 → **0.5** ✓ (member store)
  - param chunk `r9 = [obj+0x138] + sext([obj+0x28])*108` → mem[chunk+0] = **0.5** ✓
    (chunk store; heap 実体アドレスは build/実行毎に変動 — 本書記載 0x108cd890 /
    検収再実行 2026-10-10 0x108cd770)
  - flag bytes (obj+0x248 / obj+0x326 等): `(unordered || v != 0)` 値付きで付与 ✓
  - ctor 自身の 19 呼出 (patched callsite) も defaults 表 (@global_var_3025f530 =
    `[1.0, 0.5, …]`) の bits を正しく通過し member slot に値が入る ✓
- **t1 変化** (t1_argpass.mjs / t1_sel.mjs; 各 2 run bit-determinism ✓):
  - baseline (m6 無修正): 9 種 unival `{0x00000000, 0x00000080, 0x19DEE8xx 系列 7, 0xB194C940}` — denormal ~4.3e-9 以下の無音近似
  - argpass build (idx 0..18 全数 0.5): **全 512 出力 0.0** + process rc は pointer 相当値
    (検収再実測 0x108cd420; 実行・build 毎に変動)。機序: processReplacing 冒頭が `obj+806 (0x326)` の flag byte
    (`idx19` case) を load → `!= 0` なら "dirty → param cascade" branch
    (dec_label_pc_1801207f1) に入り, その path 深部で diverge。
  - **idx19 を 0.0 で明示** (t1_sel T1SET=0..19 + T1Z=19 — T1Z は setIdx に含まれる
    index のみ零化する構成のため T1SET に 19 の列挙が要る): flag=0 → process rc **0 に復帰**
    (baseline 同値) + 出力が `{0x00000000 ×258, 0xffc00000 (-6.0f) ×254}`
    (unival 9 種 → 2 種; denormal 群から実数値 -6.0 の出現)。ただし出力は
    param 値 (0.5/1.0/0.1 sweep) と入力に不応答の constant → DSP 末端 stage
    broken-lift 残存が限界 (PoC 範囲外として記録)。

### (d) bit-exact 512/512 未達の事由 (ir6 diff とともに M8 引継)

1. ir7 の IR 変更差分は δ2 点のみ (`define i64 @function_180120af0(i64,i64,i64)` の
   20 case 合成 + ctor 呼出 1 site の 3rd arg 化) — それ以外の ir6 適用 IR は 0 行差分。
2. M6 REPORT §6-(b-1) (ii) の "cpu feature 系 hand stub 迂回" に加えて、
   **pattern C (xmm 引数は全 IR で i32 raw-bits + `__asm_*` helper 経由)** の
   type-flow が解消されていないため、DSP 中間 stage (係数計算群) の値流が
   broken-lift / missing-f32 接続のまま — member slot の値は確実に obj/chunk に
   記録されるが、それを後段が消費する係数変換経路がまだ正しくない。
3. -6.0 const 出力の source 特定 (processReplacing 深部の store site 追跡) は M8
   引継 (pattern C 解消の次手)。
4. bit-exact 参照実装 (JS 移植版 or m5 の native_fx 式 unit 分割) が未整備 — M6
   REPORT §8 (ii) のまま。
5. (検収 2026-10-10 追記) ir7_argpass.py `idx_store32` の disp 前加算偏差 (§3-(b)):
   TAIL_IDX / TAIL_IDX_x2 6 case の member mirror store 先が機械語に対し idx≠0 で
   ずれる。chunk store / flag store / TAIL_AB member store は実機一致で検収済み。
   修正自体は小 (shl 後に disp を加算する形への 1 式変更) だが、IR 産物・PoC 実測の
   一括再検証が要るため M8 冒頭で処理。

### (e) M8 引継事項 (まとめ)

1. pattern C の解消: `__asm_movss(i32)` 偽経路を value-flow graph に一律接続する
   type-flow pass (DSP 係数計算群) を次の一手とする。
2. param cascade path (obj+806 flag) と index 19 / processReplacing 冒頭分岐を
   bit 精密で追跡 (t1_sel T1SET=0..19 + T1Z=19 と baseline 対観; 出力 t1_out_argpass.hex 参照)。
3. -6.0 const 出力の source 特定 (中間 stage 係数計算群 — §3-(d) 3)。
4. bit-exact 参照: JS 参照実装 (M5 式) か native unit bit-exact 分割 (SEH 依存の
   部分を除く) かを M8 冒頭で決定 (M6 REPORT §8 (ii) 踏襲)。
5. missing 11 対応 (hand C stub 9 種) は m6_rt.c 追補 1 単位として M8 bit-exact
   評価前に実施可 (分類表の内容・本節に吸収済み)。

## 4. コミット内容と検証手法

- 変更 file (すべて新規):
  - `tools/m7/m6_e2e.sh` — (1) E2E 直列化 + 検収数値 elicit 組込
  - `tools/m7/m7_build.sh` — (3) PoC build (emcc 引数 m6 一致 + EXPORTED_RUNTIME_METHODS)
  - `tools/m7/ir7_argpass.py` — (3) f32 引数接続 IR pass (PoC)
  - `tools/m7/t1_argpass.mjs` — (3) t1 相当 harness (3-arg setParameter + 固定パス)
  - `tools/m7/t1_sel.mjs` — (3) index/value 提出 harness (T1SET/T1Z/T1VAL 環境変数)
  - `tools/m7/t1_dbg.mjs` — (3) store 接続観測 harness
  - (2) 分類表 (本 REPORT §3 に吸収済み・独立ファイルは 2026-10-12 に削除)
  - `tools/m7/REPORT.md` — 本書
- 検証手法: m6_lift → ir6 → m6_build → m6_simd_check → node 3 系統を tools/m7 の
  wrapper から再実行し、exit code + 行数/ SHA 数値の自動判定で記録 (生成物は
  tools/m7/work/ に集約; t1_out_argpass.hex のみ harness の HERE 直下 tools/m7/ に
  書出される; work/, __pycache__, t1_out_argpass.hex は commit から除外)。
- tools/m6 のファイルは読取のみ (work/ 直下の re-生成物は commit に含めない)。

## 5. 相互作用と注意点

- ir7_argpass は `work/ott_memfix1.ll` → `work/ott_argpass.ll` に分離出力する。
  m6_e2e で ott_shift3b を再生成しても、tools/m6/work/t1.mjs は ir7 適用前の
  m6 build を使う (**m6 側 baseline 不変** PoC 適用は tools/m7 側 build のみ)。
  baseline bit 一致は e2e 毎回自動確認 (determinism 2 run)。
- lift 再実行の nondeterminism (add i64 0, i64 / 重複 declare) は e2e 内蔵 fixup
  で解消済み。fixup 後 fresh lift でも t1_out SHA が f34a6a46… と baseline 一致
  (旧 lift 産物との bit 一致を本実行で確認済み)。

## 6. 検収再実行 (2026-10-10, 独立検収)

- `bash tools/m7/m6_e2e.sh` (既存 IR 再利用): **exit 0 / 数値全一致** — signature
  mismatch 0 / undefined 57 種 (function_18*: 33 / __asm_*: 0 / Win・CRT API: 24) /
  simd 0-0 / t1 512 行 (2 run SHA256 一致 f34a6a46798b0a65…cf7c835) / t3
  mem[0x30260ce0]==0x2DDFA232 / trap_test OK 6 FAIL 13 (= missing-function abort 11 +
  broken-lift OOB 2, missing11 11 関数名と FAIL 一致)。再実行後 `git status`
  管理下差分 0 (work/ 系未追跡のみ)。
- `--full` (RetDec 再 lift鎖 全再生) も **exit 0**: lift_fixup 実測 `add i64 0, i64`
  → 4 件 / 重複 declare → 2 件 (本書記載値どおり) で、t1_out SHA は baseline
  f34a6a46… と bit 一致。
- PoC 再現 (m7_build.sh 再 build exit 0 → link 状態 e2e と同一 57 undefined set、
  ott_argpass.ll は BaseIR 差分 δ2 点のみ (()3-arg 化 + 本体 20 case 合成)):
  - t1_dbg: obj+0x2dc 1.0 → 0.5 / chunk (obj+0x138 基点) store 0.5 / process rc
    pointer 相当値 ✓ (heap アドレスは実行毎変動)。
  - t1_argpass 2 run: 同一 SHA b944d027…, 全 512 = 0x00000000, unival 1 ✓。
  - t1_sel T1SET=0..19+T1Z=19 2 run: 同一 SHA feae94b6…, process rc 0, 出力
    {0x00000000 ×258 / 0xffc00000 ×254} ✓ (**T1Z のみでは setIdx (既定 0..18) に
    19 が含まれず零化されない** — §3-(c) 通りの結果には T1SET=0..19 の列挙が必要)。
- 例外発見 (既知化): idx_store32 の member mirror store 先偏差 6 case (§3-(b), §3-(d) 5)。
  process rc の pointer 実体値・chunk アドレスは build 毎変動 (本書 §3 の固定 hex 値は
  参考記録)。
