# M6 REPORT — OTT (Xfer) VST2 win64 DSP コア lifter → wasm PoC

- 日付: 2026-10-10。HEAD 基点: 901ce24。
- 本 REPORT は M6 成果物 (tools/m6/, work/ を除く) に対する独立検証の実行結果を含む。
- 検証環境: node v26.10.0 / emcc 6.0.12 / Python 3.14.8 / RetDec (lift) / wabt (wasm-objdump, wasm2wat)。

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
  生成 (`msimd6.c`)。**ただし `msimd6_core.h` が空ファイル (0 byte) で、現状の
  msimd6.c は単独ではコンパイル不可**。

## 5. wasm build 実測 (m6_build.sh, 本検証で 1 回実行)

- **exit code 0**。成果物 `work/ott_test.cjs` (172,136 B) + `work/ott_test.cjs.wasm` (825,248 B)。
  - emcc 6.0.12、STACK=8MB、GLOBAL_BASE=256MB、initial/max memory=0x36000000 (864MB)、
    `-sERROR_ON_UNDEFINED_SYMBOLS=0`、`-sEXPORTED_FUNCTIONS` は closure 関数群の全エクスポート。
  - 関数 533 (imports 含む)、exports **224** (closure 関数 + m6_rt shim + `__asm_*` helper)。
  - **`warning: undefined symbol`: 218 種** (未解決 declare 関数、ランタイムで fail-fast)
  - **`wasm-ld: warning: function signature mismatch`: 12 種** (§7 root cause 参照)。

### m6_build.sh は現状 m5/msimd.c にフォールバックしている

- `m6_build.sh` は `MSIMD_SRC=../m5/msimd.c`。しかし ott_lift.ll では helper 呼出が
  RetDec の rax 返り値型 (i64) で出ており:
  `call i64 @__asm_movsd__2(i128 …)` 157 回、`@__asm_movss__17` 78 回、`@__asm_movaps` 59 回、
  `@__asm_movq__6` 17 回、`@__asm_movdqa` 15 回、`@__asm_vmovq` 14 回、`@__asm_movdqu` 3 回、
  `@__asm_movapd` 1 回 (計 ~344 site)。m5/msimd.c の提供 signature (`u128 (u128)`) とは
  型不一致。gen_msimd6.py 生成の `msimd6.c` は正しい signature を提供するはずだが、
  `msimd6_core.h` が空でこのままでは使えない。

## 6. wasm 実行検証 (node, 本検証)

### (b-1) work/t1.mjs — **FAIL: RuntimeError: unreachable**

- 構成: `ctor → setParameter(0..18, 0.5) → resume → processReplacing`
  (OBJ/IN/OU/BUF は VA 0x30000000 base の work area; N=256 sample × 2ch)。
- 結果: **fctor (function_18011d400) の最初の helper 呼出で即 wasm trap**。
  trace: wasm func[237] (signature `(i64,i64)→i64`、body は単一 `unreachable`) →
  caller wasm func[387] = `function_18011d400` (ctor)。対応 IR 呼出:
  `%1 = xor i128 0, 0; %3 = call i64 @__asm_movaps(i128 %2)` が、§5 の signature mismatch で
  lld が自動生成した **unreachable stub (wasm funcs 231–242 の 12 個)** に飛び即死する。
  processReplacing はこの先のため検証不能。
- よって **t1_out.hex は未生成**。bit-exact 検証 0 対象 (試行: 256 sample × 2ch = 512 値)。

### (b-2) work/t3.mjs — **FAIL: unreachable**

- probe: `function_1801bf664(BigInt(0))` → unreachable (missing-function 系)。
- 敷設観察値 (m6_data_install 後):
  - `mem[0x30260ce0..] = 0x32 0xA2 0xDF 0x2D` (LE: **0x2DDFA232**) — t3.mjs コメントの
    期待値 `769630770 = 0x2DEB8762` と不一致 (RetDec の型取り違え判断を要確認)。
  - `mem[0x3026c388..] = 0x00 0x00 0x00 0x00` (0)。

### (b-3) work/trap_test.mjs — **OK 0 / FAIL 21**

- 未解決 declare と hand stub への probe 起動の結果:
  - `Aborted(missing function: …)` — **14** 関数 (function_1801bfab4 / 1801c0ac8 /
    1801c1438 / 1801c17e0 / 1801c17fc / 1801c24d0 / 1801c33e0 / 1801c6744 / 1801c67a0 /
    1801c6a04 / 1801c721c + `SetLastError`) — closure 外 CRT/Win API 依存
    (DSP 経路外 fail-fast。m6_stubs.c / m6_rt.c が意図的に fail-fast とする declare 系)
  - `native function … called with 1 args but expects 0` — **3** 関数
    (function_1801b4610 / 1801b4900 / 1801b4e30) — hand stub (m6_stubs_hand*.c) と
    export wrapper の arg 数不整合
  - BigInt 変換異常 — **4** 関数 (export 宣言の型不定による JS wrapper 不一致)。

### (b-4) native 参照 (bit-exact / tolerance 検証) — **未実施**

- m5 の `native_fx.c` / `build_native_fx.sh` 方式 (x86 native メモリ実行) は M6 のこの段階で
  接続まだなし。よって bit-exact/tolerance の実測値は本コミットには存在しない (N/A)。

## 7. 既知の課題 (残存 stub / 未解決一覧)

1. **m6 helper set 完全化** (最優先; t1 unreachable の直接解消対象): `msimd6_core.h` の
   生成を完了 (現状空 0 byte) し、msimd6.c を build に接続する。対象は RetDec の
   i64 返り値 signature の `__asm_*` helper ~344 site
   (movsd__2 / movss__17 / movaps / movq__6 / movdqa / vmovq / movdqu / movapd)。
2. **関数 signature mismatch 12 種** (wasm-ld): `__asm_movaps/dqa/dqu/ss/ups` 5 種 +
   `function_1801a2a00 / a30b0 / a3ad0 / be668 / be6bc / cfa6c / cfcfc` 7 種。1 の対応後に
   lld stub (funcs 231–242) は消える。hand stub (m6_stubs_hand*.c) の arg 署名のうち
   修正未了も同時調整。
3. **unresolved 218 種**: closure 外 CRT / Windows API で m6_stubs.c が意図的に fail-fast 化
   している分が大半。IR 内 `0x30260ce0` の型取り違え (t3.mjs コメント対象) の整合は
   m6_data_install 後の DLL 実データと IR 値の照合で要確認。
4. **m6.sh 1 コマンド E2E はまだ実装なし**。現在は `m6_lift.sh` (RetDec + ir5 系),
   `m6_build.sh` (emcc), t1 / t3 / trap_test.mjs (node 実行) を手動で段階実行。
   M7 で `m6.sh` として統合化する。
5. **m6_rt.c の var 名 typo: `function_18003c0丫1` (CJK 文字)** — コンパイルは通るが、正式名称
   (`function_18003c0???` 等正体確認) に差替推奨。同ファイル内 `m6_failmsg` の fprintf 引数
   欠損も修正推奨。

## 8. M7 / M8 への引継ぎ

- **M7 (他 plugin format / 他エンジン側への展開)**:
  - `ott_match*.py` の flow (win64 `.pdata` 走査 + mac nm 符号 + 命令列フィーチャスコア) は
    `OTT_vst3_win64.dll` / `OTT_aax_mac_x86_64` / `OTT_au_mac_x86_64` へそのまま適用可能
    (ottlib.py `Bin/Dis` 抽象化)。
  - `ott_map.json` (9 class) と `ott_vtables.json` (152 slot 実測一致) は host 境界未解決・
    class 配線検証へ流用可能。
- **M8 (bit-exact / tolerance / 実性能)**:
  - まず課題 1 (m6 helper set 完全化) を完了して t1.mjs (256 sample × 2ch × 19 param) を
    通過させること。それが取れたら、m5 `native_fx.c + build_native_fx.sh` 方式による
    native 参照側との bit-exact (F32 bit 完全一致, ±0 bit 除外) / tolerance
    (`|w - n| <= 1 ULP (float32)`、M5 REPORT の規約) を計測する。
  - `m6.sh` 1 コマンド E2E (lift → IR passes → emcc → node 実行 → bit-exact check) を
    M8 の成果物として提供する。

## 9. 本検証の再現コマンド

```bash
# (a) build (m6_lift.sh は RetDec 重い; 本検証は build のみ実施)
bash tools/m6/m6_build.sh
# (b) node 実行検証
node tools/m6/work/t1.mjs
node tools/m6/work/t3.mjs
node tools/m6/work/trap_test.mjs
# (c) IR pass 再現
python3 tools/m6/ir6_pass.py  work/ott_lift.ll  /tmp/p1.ll
python3 tools/m6/ir6_shift.py /tmp/p1.ll        /tmp/sh.ll
python3 tools/m6/ir6_gdata.py /tmp/sh.ll        /tmp/gd.ll  # ≒ work/ott_shift3b.ll
```
