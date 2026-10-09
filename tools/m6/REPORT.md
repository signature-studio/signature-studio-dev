# M6 REPORT — OTT (Xfer) VST2 win64 DSP コア lifter → wasm PoC

- 日付: 2026-10-10。HEAD 基点: 901ce24。**M6b (2026-10-10 追記)**: SIMD helper 接続
  (msimd6_core.h 補完) / wasm-ld signature mismatch 12→0 / t1 run-complete / t3 mem 照合
  / trap_test arg/BigInt 7 件解消。HEAD 基点 commit 2607a2e 時点から M6b 継续分を追記。
- 本 REPORT は M6 成果物 (tools/m6/, work/ を除く) に対する独立検証の実行結果を含む。
- 検証環境: node v26.10.0 / emcc 6.0.12 / Python 3.14.8 / RetDec (lift) / wabt (wasm-objdump, wasm2wat)。
- README (repo root) 掲示候補文言:
  - `tools/m6/` — OTT (win64 VST2) DSP コア lifter → wasm PoC。SIMD helper (msimd6_core.h,
    gen_msimd6.py → msimd6.c) は lift IR の declare 型そのまま。実行検証は
    `bash tools/m6/m6_build.sh && python3 tools/m6/m6_simd_check.py … && node tools/m6/work/{t1,t3,trap_test}.mjs`
    (詳細は tools/m6/REPORT.md §9)。bit-exact 判定は M8 引継 (REPORT §8)。

## 1. 目的

Xfer OTT VST2 win64 (DSP core ~20KB 公称) の DLL から DSP コア関数群を抽出し、
RetDec lift → IR pass (m5 の ir5_patch / A9 命令化を継承) → emcc → wasm 化する。
DLL の PE 実データを VA 一致で wasm 線形メモリに敷設し、OTT DSP の主要関数群
(ctor / setParameter / resume / processReplacing) を node 上で直接起動する。
最終目標は m5 の native メモリ実行方式との bit-exact / tolerance 検証と m6.sh 1 コマンド E2E。

## 2. 素材

抽出元: `Install_Xfer_OTT_137.exe` → `/home/ubuntu/work/analysis/plugins/ott/binaries/`

- **正本: `OTT_vst2_win64.dll`** — 関数境界 (`.pdata` RUNTIME_FUNCTION) 走査、RetDec lift、
  データ敷設すべてこの DLL が対象。
- **mac 参照: `OTT_vst2_mac_x86_64`** (符号あり Apple clang 生成) と nm log
  (`nm_ott_vst2_mac_x64.txt`) — win64 側のシンボル名は mac の C++ mangled 名から割付ける。
- 同フォルダに `OTT_vst3_win64.dll` / `OTT_aax_*` / `OTT_au_mac_x86_64` / `OTT_vst2_win32.dll`
  もあり (M7 の素材候補)。

## 3. 選択された関数群と選定根拠 (ott_match flow)

1. **m6_scan.py**: win64 DLL 全 `.pdata` 走査 → root 選定 (vftable / ctor 由来で確定した
   class のシード) → root から direct-call closure を計算し、
   `work/ott_closure.json` (fn_count / code_bytes / externs / 間接呼出) と
   `work/ott_ranges.txt` (RetDec `--select-ranges` 用 1 行 CSV) を生成。
2. **ott_match.py** (→ ott_match2/3/4.py): mac (符号あり) と win64 (符号なし) の x86_64
   関数を命令列フィーチャ一致 score (0..1) で対応づけ、win64 側に関数名を与える。
   `work/ott_match.json`: **21 関数** (score 0.686–1.0、うち 15 関数 ≥0.95)。
   主な一致: `TrapSVF::GetPPF` / `OTTProcessor::setParameter` (1.0)、
   `OTTProcessor::vendorSpecific` / `TrapSVF::Set` (0.998)、
   `EnvelopeDetector::setCoef` / `TrapHiShelf::Set` (0.995)、`TrapLowShelf::Set` (0.994)、
   `TrapPeak::Set` (0.991)、`TrapZBF::Set` (0.989)、`AttRelEnvelope::setRelease` (0.981)、
   `OTTProcessor::getParameter` (0.979)、`SimpleComp::process` (0.975)、`canDo` (0.968)、
   `convertParameterValueToString` (0.962)、…、`OTTProcessor::processReplacing` (0.686)。
3. **ott_map.json**: class 単位の整理 **9 class** (FIL_Linkwitz_Riley4, OTTProcessor,
   AudioEffectX, AudioEffect, MyVUMeter, OTTVST, EnvelopeDetector, AttRelEnvelope,
   SimpleCompRms)。
4. **closure 実数** (`ott_closure.json`): fn_count **166**、code_bytes **58,891 B (~57.5KB)**
   (DSP core 公称 ~20KB に対しては vftable / 例外 / CRT wrapper を含む実測値)、
   externs **51**、間接呼出 **32 種** (VST2 host 境界を含む)。
5. **vtable 整合** (`ott_vtables.json`, `ott_vt_slots.json/.txt`): mac 695 vtable、
   win 候補 447 → **152 slot 実測一致**。`ott_vtables.json` の `match` フィールドは
   現状 0 (名前の精確一致は ott_match flow 側で処理済み)。

## 4. lift + IR pass 結果

### RetDec lift (m6_lift.sh)

- `retdec-decompiler OTT_vst2_win64.dll --select-ranges work/ott_ranges.txt --select-decode-only`
  → `work/ott.drc.ll` (closure 166 関数分)。
  - `work/full_t1.drc.*` (8,788 defines): 全 DLL リフトの素材 (t1 経路全体の確認用)。
  - `work/ott2.drc.* / pr3.drc.* / miss13.drc.*`: 未解決 closure 追跡用の中間リフト
    (miss13 は 6 関数 defines; t3.mjs の未解決観察に対応)。命名由来の「unresolved 13」は
    未整理 (本 REPORT では実体 6 defines を記録)。
- 以後 `../m2/ir_normalize.py` → `work/ott_norm0.ll` → `../m5/ir5_patch.py` →
  `work/ott_lift.ll` (M5 継承)。

### IR pass (m5 継承, `work/ir5_report.json`)

- **stages A1, A2, A3, A4, A5, A6, A7, B1, A9L, S1, C8, C9, C1 実行完了**
  - **B1 修復 255 件 / S1 store 復元 7 件 (lane 切離し 0 件) / C8 xmm 異常 0 件**
  - **A9 residual constexpr = 5 件 (inttoptr 形)** — 残存は IR 内の型変換の inttoptr

### IR pass (m6 追加)

- **ir6_pass.py [P1] comis/UCOMISD flag 修復**: comis sites **94**、修復 insert **18**
  (br_cf 16 / br_zf 1 / or_cfzf 1 = 18 site。br_other 17 は別パターン、no_branch 66 で未対応)。
- **ir6_shift.py**: IR 内 VA 直値 0x180000000+RVA → 0x30000000+RVA への remap **38 件**。
- **ir6_gdata.py**: `@global_var_*` 全定義 **400 件** を DLL 実データ (V-shift 後) に差替
  (`[gdata] replaced: 400 added: 0`)。
- **再現性検証 (本検証)**: `ott_lift.ll → ir6_pass → ir6_shift → ir6_gdata` の直列を本環境
  で再実行した結果、出力 IR は手修正 (8→16 byte 定数 widening) を除けば現状の
  `work/ott_shift3b.ll` (25,337 行) とほぼ一致 — IR pass 鎖は本環境でも再現可能。
- **gen_msimd6.py**: ott_lift.ll の declare 記述から m6 用 helper (`__asm_*` **156 種**) を
  生成 (`msimd6.c`)。M6b で **v2 に改修** (declare 型駆動, msimd6_core.h 補完の上
  コンパイル通過; OLD: `msimd6_core.h` 空ファイル (0 byte) で単独コンパイル不可、
  ビルドは m5/msimd.c にフォールバック但し書き → 解消)。

## 5. wasm build 実測 (m6_build.sh, M6b 再ビルド後)

- **exit code 0**。成果物 `work/ott_test.cjs` (189,329 B) + `work/ott_test.cjs.wasm` (838,078 B)。
  - emcc 6.0.12、STACK=8MB、GLOBAL_BASE=256MB、initial/max memory=0x36000000 (864MB)、
    `-sERROR_ON_UNDEFINED_SYMBOLS=0`、`-sEXPORTED_FUNCTIONS` は closure 関数群の全エクスポート。
  - **`warning: undefined symbol`: 57 種** (整数 33 種 = closure 外 CRT 関数 + Win API 24 種。
    旧 218 種から大幅減。内訳: `__asm_*` helper 由来 0 種、`function_1801*` 33 種)。
  - **`wasm-ld: function signature mismatch`: 0 種** (旧 12 種 → M6b で 0)。
    検収: `python3 m6_simd_check.py work/ott_memfix1.ll msimd6.c` → declare / 定義 / 呼出 site
    3 重照合 mismatch 0。
- build 鎖 (m6_build.sh に内包): `ir6 適用済み work/ott_shift3b.ll` →
  `m6_memfix.py` (memmove/memset C 実装化) → `m6_full_extract.py` (closure declare-only
  実体の full-lift splice) → emcc。

### M6b で build に追加した IR 前処理パス

1. **msimd6_core.h 補完 (M6b の中核)**: 空ファイル (0B) だった core を作成。
   型 (u128/u64/u32/u8/i32/i256x/v4f/v2d/v4i/v16b), bit 転写素材 (lane0_*/set_*_lo/
   lane0*_set/asd/das/fas/asf), lane 演算 (_laneop32/64/c, _laneop64c2, _lanepd,
   _laneaddq/_lanesubq/_lanesubd, _overwrite_lo64/hi64), FMA 12 形 (_fma*_sd.f), SSE
   max/min (NaN=src2 規約), _round_pd, CMPSD mask (_cmpsd_mask + _cmpsd_pred) を収容。
   `gen_msmsd6.py → gen_msimd6.py` の v2 は **lift IR declare 型そのまま** の
   signature で 153 種 helper を実装生成 (旧版 156 declare 中 i256 3 種は exclude)。
2. **m6_memfix.py**: 破損 lift 2 define 除去 + C 実装 outcall 化
   (function_1801a2a20 = CRT memmove [(i64,i64,i64,i64)->i64] — IR 本体に i256 系
   helper (C は _BitInt(256) 不可で ABI 一致不能) と内部 0-arg call を含む破損出力,
   function_1801a30d0 = CRT memset [(i64,i32,i64)->i64] 同様)。加えて
   sqrt 報告 CRT 呼出 (function_1801a9a6c()/1801a9b38() = 0-arg 戻り値未使用 4 site)
   を削除 (これが ctor 前段で c1584→c20c8→...→c38c8 (broken lift body OOB) への
   展開源であったため)。m6_rt.c 側に memmove/memset/a14f0/be668/be6bc/cfa6c/cfcfc
   /126b30/126b50/125fe0/caf80/caf8a/ce35c/ce384 等 hand stub を実装
   (IR declare signature 完全一致; 手 port は full_t1.drc.ll 実体を参照)。
3. **m6_full_extract.py**: closure lift が declare-only にした runtime 到達関数の
   実体抽出 (full_t1.drc.ll から carve → typed pointer → ptr 変換 → helper 名
   signature-driver normalize → VA/global shift → memfix IR へ splice →
   closure 側 declare 行除去 + callsite ret 型 refit)。現状対象:
   `function_1801260c0 / 180126010 / 180126030` (processReplacing 内 1-arg 系)。
   戻り値が closure 内で捨てられているため ret 型 (i128) upsizing は安全。

### m6_build.sh は msimd6.c を使用 (旧: m5/msimd.c フォールバック)

- `m6_build.sh` の `MSIMD_SRC` は `msimd6.c` (未生成なら FATAL)。ott_lift.ll では
  helper 呼出 ~2,366 site (movaps__4 254 / movsd 171 / movsd__2 157 / ...)。
  RetDec の i64 返り値 signature (`call i64 @__asm_movsd__2(i128 …)` 157 回 等) と
  宣言型を完全一致させたため signature mismatch が構造的に消滅。

## 6. wasm 実行検証 (node, M6b 再検証)

### (b-1) work/t1.mjs — **OK (run complete; bit-exact は未達 → §6-(b-4))**

- 構成: `ctor → setParameter(0..18) → resume → processReplacing` (N=256, 2ch, 512 値出力)。
- M6b 変更: ctor の戻り値 (= new 先オブジェクト ptr, 実測 0x30310000) を以後の
  setParameter / resume / processReplacing の obj として使用 (旧 harness は
  OBJ 定数 area を渡していた)。setParameter は lift IR declare に従い 2-arg
  (`(obj, index)`) — f32 値 (xmm2) は RetDec closure lift で引数 decoded から
  落ちているため JS から渡せない (§7-5 参照)。
- 結果: **run complete** (旧: ctor 最初の `__asm_movaps` 呼出で wasm trap)。
  `t1_out.hex` 512 行生成、再実行 determinism OK (2 run bit 一致)。
  - helper fail-fast (`__asm_cmplesd` など) 0、memory OOB 0、trap 0。
  - processReplacing は DSP 数値としては**未正解** (out 値に 2e21 級の発散あり)。
    根因は (i) f32 引数閉流 (ii) cpu feature 系 hand stub 迂回 — bit-exact 判定
    512/512 は未達 (§6-(b-4), §7-5)。本 build で解決した「実行が trap せず
    processReplacing まで駆動する」状態が M6b の達成ライン。

### (b-2) work/t3.mjs — **OK (mem 値照合)**

- probe `function_1801bf664(0)` rc = mnemonic 程度 (CRT lock no-op 化のため RetDec
  部分 lift 状態の生戻り値; 照合対象外)。
- 敷設確認 (m6_data_install 後) — **M6b 検収値**:
  - `mem[0x30260ce0..] = 0x32 0xA2 0xDF 0x2D` (LE: **0x2DDFA232 = 769630770**)。
    IR 側 global_var literal (i32 769630770) と m6_data install は**一致** —
    **RetDec 型取り違え無し**。旧 t3.mjs コメントの期待値 0x2DEB8762
    (= 769756514, f32 2.6776e-11) は誤値 (実データ照合で判明; t3.mjs は M6b で
    検収ロジックに改修, 0x2DDFA232 一致で OK exit)。

### (b-3) work/trap_test.mjs — **OK 8 / FAIL 13**

- probe 引数を memfix IR declare の arity/形式に是正 (旧: 全 probe に BigInt(0
  を 1 arg で渡し 3 種が arg 数不整合・4 種が BigInt 型不定)。
- **解消 7 件**: arg 数不整合 3 (function_1801b4610 / b4900 / b4e30 — 0-arg 定義と
  probe 1-arg で assert 死) + BigInt 型不定 4 (function_1801c6a2c (4-arg BigInt),
  c6b44 (2-arg), c8a80 (2×i64 + i32), c91cc (ptr + 3×i64))。
  うち c6a2c / c6b44 / c8a80 / b4x3 = **OK (abort せず制御返答)**。
- 残 FAIL 13 = missing 11 (意図的 fail-fast: closure 外 CRT/Win API 依存群) +
  memory OOB 2 (function_1801c69cc / c91cc — 実体 body 内で broken-lift 状の
  table base 0x180001090 定数を内部 mul/add で持つ c38c8 family に到達;
  ir6_shift が拾えない算術合成 base のため OOB — §7-6)。

### (b-4) native 参照 (bit-exact / tolerance 検証) — **未実施 (実装判断: 停滞)**

- m5 方式 (native_fx: 実機 x86 で DLLを VA 敷設後, 目的関数だけ直接実行) は
  M6 の対象関数 (ctor / setParameter / processReplacing) では **軟着地点を欠く**:
  - OTT ctor は plugin 自身の CRT heap/SEH (RaiseException 0xE06D7363 = MSVC C++
    exception) を前提にし, Linux でそのまま実行すると SEH unwind が動かず即段落ち。
  - m6b で lift で到達した「math 報告 CRT (c1584/…/c38c8)」は, wasm 側では
    no-op 化したが, native 実機 (実 machine code) では SEH 依存のため bit-exact
    参照比較の前提 (同 control flow) が取れない。
  - mac AU arm64 参照: 検証対象 (win32 closure) と ABI/浮動小数の局所環境差が大きく
    (x64 SSE3 pack / FMA 差), 512 値の bit 一致判定は非自明素材。
- よって M6b の bit-exact 判定は **N/A とし, 理由付き未達を M7/M8 に引継**
  (M7: m6.sh E2E 整備 + t1 経路の RetDec 引数回収率改善, M8: native/JS 参照
  再突合)。現時点でも「run complete + determinism OK + helper 0 mismatch」が
  実行検証の観点では最低基準を満たす。

## 7. 既知の課題 (残存 stub / 未解決一覧, M6b 更新)

1. ~~m6 helper set 完全化~~ **解消 (M6b)**: msimd6_core.h 補完 + gen_msimd6.py v2
   (declare 型駆動, 153 種実装 / i256 3 種 skip)。153 headers:
   `EMSCRIPTEN_KEEPALIVE`、UNIMPLEMENTED 残 0 (cmpsd mask 形 (`cmplesd`/`cmpnltsd`
   等 4 種は predicate-name 駆動で実装済み; t1 経路で実使用あり)。
2. ~~関数 signature mismatch 12 種~~ **解消 (M6b = 0 種)**: `__asm_movaps/dqa/dqu/ss/ups`
   5 種は msimd6.c 宣言型一致化で解消、`function_1801a2a00 / a30b0 / a3ad0 / be668
   / be6bc / cfa6c / cfcfc` 7 種は (a) memmove/memset を IR define 削除 + C 実装化
   (a2a00/a30b0 は呼出消退滅), (b) hand stub の引数型を IR declare と一致 (be668/
   be6bc=(int), cfa6c=0-arg, cfcfc=(int), a3ad0=(i64,i64) fail-fast), (c)
   function_1801a2a20/1801a30d0 の破損 IR define を m6_memfix.py で除去で解消。
3. **unresolved 57 種**: closure 外 CRT 33 種 (m6_stubs.c の意図的 fail-fast 主体、
   DSP 経路外) + Win API 24 種。DSP 経路で実使用と判明した hand stub 実装 (: RaiseException/
   GetLastError/SetLastError no-op, 180126b30/b50 (class flag setter), 180125fe0
   (init block), 1801caf80/caf8a (MXCSR no-op), 1801ce35c/ce384 (CPU feature check
   — linear memory 直読みで m6 data install 値と一致))。
4. ~~m6.sh 1 コマンド E2E はまだ実装なし~~ (M7 引継。m6_build.sh は
   memfix/extract を内蔵して 1 コマンド化の前段完了)。
5. **RetDec closure lift の f32 引数失落 (M8 の最重要)**: setParameter
   (function_180120af0) 等の class method は x86 では (rcx, edx, xmm2=value) —
   closure lift は (i64,i64) で xmm を落とす → JS から float を渡せない。
   full lift (full_t1.drc.ll) では 4-arg 形で値を保持 → m6_full_extract.py の
   対象拡大 + closure 側 callsite 引数接続が M7/M8 の必須作業。
   同様に ctor 内の sqrt(2.0)=1.41421... 系初期値演算で RetDec が rax 返り値型
   で出す helper も signature 完全一致で再構築済み (movdqa__10 等 i128 形)。
6. **broken lift body の内部 OOB (trap_test の残 2)**:
   `function_1801c38c8` (その外の `function_1801c69cc`/`c91cc` probe から到達) は
   table base 0x180001090 / 0x180001070 を `mul / and / add` 算術合成で使い,
   ir6_shift.py (正規表現型 VA 直値向き) が remap できず OOB。
   対応案: ir6_shift に算術合成 base 検出を追加, または本期 memfix と同様
   full-lift 抽出の C 実装化 (vsnwprintf 等 CRT 文字列系を libc 寄せで)。

## 8. M7 / M8 への引継ぎ (M6b 更新)

- **M7 (他 plugin format / 他エンジン側への展開)**:
  - `ott_match*.py` の flow (win64 `.pdata` 走査 + mac nm 符号 + 命令列フィーチャスコア) は
    `OTT_vst3_win64.dll` / `OTT_aax_mac_x86_64` / `OTT_au_mac_x86_64` へそのまま適用可能
    (ottlib.py `Bin/Dis` 抽象化)。
  - `ott_map.json` (9 class) と `ott_vtables.json` (152 slot 実測一致) は host 境界未解決・
    class 配線検証へ流用可能。
  - m6_build.sh 既内蔵 (memfix/extract は含む) で `m6.sh` (lift → IR passes → emcc →
    node t1/t3/trap_test → bit-exact check) への 1 コマンド化は「m6_lift.sh と
    param 引数回収率改善 (below) が前提」。
- **M8 (bit-exact / tolerance / 実性能)**:
  - M6b の t1 run-complete が前提。bit-exact 判定に必要な最初の仕事は
    **RetDec closure lift の f32 (xmm) 引数回収率の改善** (setParameter など
    rcx/rdx/xmm2 形 class method) — full lift の 4-arg 形と closure 側を m6_full_extract.py
    スタイルで forward-v 接続する IR pass ([P2] の要否判定) が必須。
  - native 参照: m5 `native_fx.c + build_native_fx.sh` 方式は OTT 全体では SEH/CRT
    前提の Edge が多く, (i) 小関数 unit (c0c0 family 等, 計算のみ) 単位の
    bit-exact の分割検証, 或いは (ii) JS対象DSP model で OTT の processReplacing
    を移植した参照実装 (M5 の JS 参照実装スタイル踏襲) が現実解。
  - trap_test の残 2 OOB (c38c8 family, broken-lift table base 算術合成) で
    ir6_shift の算術合成 remap 対応がある未解决。

## 9. 本検証の再現コマンド (M6b 更新)

```bash
# (a) build (m6_lift.sh は RetDec 重い; 本検証は 既設手順の build を実施)
bash tools/m6/m6_build.sh            # memfix → extract → emcc を 1 本で実行
# (b) helper 整合検収 (declare / 定義 / 呼出 3 重照合; 0 mismatch が正)
python3 tools/m6/m6_simd_check.py tools/m6/work/ott_memfix1.ll tools/m6/msimd6.c
# (c) node 実行検証
node tools/m6/work/t1.mjs            # OK (run complete, t1_out.hex 512 行)
node tools/m6/work/t3.mjs            # OK (mem 0x2DDFA232 == DLL 実データ)
node tools/m6/work/trap_test.mjs     # OK 8 / FAIL 13 (missing 11 + broken-lift OOB 2)
# (d) IR pass 再現 (M5/M6 時点と同一)
python3 tools/m6/ir6_pass.py  work/ott_lift.ll  /tmp/p1.ll
python3 tools/m6/ir6_shift.py /tmp/p1.ll        /tmp/sh.ll
python3 tools/m6/ir6_gdata.py /tmp/sh.ll        /tmp/gd.ll  # ≒ work/ott_shift3b.ll
# (e) 一部手動 IR 前処理 (build 内に内包)
python3 tools/m6/m6_memfix.py      work/ott_shift3b.ll  work/ott_memfix0.ll
python3 tools/m6/m6_full_extract.py work/ott_memfix1.ll function_1801260c0 function_180126030 function_180126010
```
