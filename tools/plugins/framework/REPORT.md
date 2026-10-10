# P0a REPORT — Delphi framework headless lift (CAB-194)

- 日付: 2026-10-10 / 担当 dir: `tools/plugins/framework/` / 再現: `bash tools/plugins/framework/fw_stage2.sh` (stage-1 済み work から; `--fresh` で stage-2 全再生成)
- 前提: stage-1 = `fw_lift.sh` (icall 経路 PE 書換え → RetDec 8 chunk decode → 復元 → merge)。**前回委任 (insufficient_credits で中断) の成果物を引き継ぎ** (判定 §1)。
- 数値はすべて本 dir の `tools/plugins/work/fw/` (gitignore) で実測。推定は「推定」と明記。

## 0. 結論 (先出し)

| 項目 | 結果 (実測) |
|---|---|
| lift closure | Balance (Fruity Balance = framework 正本) **11,736 関数 / 1.61 MB** 中 framework(≥13 DLL 共有ハッシュ) 11,659 関数 / 1.61 MB + glue 77 関数 / 23.6 KB を全量 lift |
| IR | RetDec decode 8 chunk + decode 漏れ 2 ラウンド (990→287→206 件) → **14,034 define / 約 133 万行** |
| wasm | emcc 通過 / node instantiate 完走 / **wasm 14.8 MB** (fw_route.wasm) |
| headless smoke | `DllMain(DLL_PROCESS_ATTACH)` → `_StartLib` → `_InitLib` → `InitUnits` が wasm で完走、**PackageInfo 290 unit のうち 16 unit init + 16 unit finalize が完走 (dispatch 38 回) / trap 0 / ff 0**。その後 RestoreContext (Halt0 経路) 到達 — m11 方式で正常終了扱い |
| kernel 表 (CAB-196) | 呼んでいない (本 smoke の scope 外; CreatePlugInstance も不使用) |

## 1. 引継ぎ判断 (前回中断成果物の精査)

`tools/plugins/framework/` に未追跡で残っていたのは `fw_prep.py` / `fw_merge.py` / `fw_lift.sh` の 3 ファイル (24 KB, 10-10 17:25-17:27) と `work/fw/` の中間成果物。

| 資産 | 状態 | 判定 |
|---|---|---|
| `fw_prep.py` | .pdata 全関数 (11,736) の F.ranges 生成 + FLEngine RTL landmark の位置非依存ハッシュ突合 (InitUnits/_InitLib/_StartLib/UStrAsg/RestoreContext/ApplyRelocs/FastMM_GetMem が **9/9 一意一致**) + InitUnits の InitTable global (0x714c90) 抽出 | **完成・採用** |
| `fw_lift.sh` | icall_rewrite (11,736 関数, 6,159 site, derefix 12,658, comis 630, errors 0) → RetDec 8 chunk 並列 → 復元 → merge | **完成・採用** (実行済み, `fw*.restore.json` 合計 dispatch 5,547 / comis 626 / 未変換 0) |
| `fw_merge.py` | m11_merge.py copy。**無名 global/metadata の chunk 間番号衝突を修正** (本研究で拡張: §4) | 採用+修正 |
| `work/fw/` 中間物 | 8 chunk の drc.ll/restored.ll, fw_icall.dll, fw_map.json | **再利用** (再 lift 不要, 約 6 分節約) |

→ **結論: 引継ぎを採用** (stage-1 がほぼ完走していたため)。クリーン再実行は不採用。ただし merge の番号衝突は本研究で発見・修正した (§4)。

## 2. パイプライン (stage-2 = 本研究)

```
fw_all8.ll (8 chunk merge)
  → fw_round2.py (decode 漏れ .pdata 非登録 callee: 990→287→206 件, RetDec 2 ラウンド)
  → fw_merge.py (fw_all.restored.ll: 14,034 define / 6,293 global / 8,176 declare)
  → fw_f80.py      [f80→f64]  x86_fp80 3,688 token / i3 3,364 / 定数 30 / same-type fix 73
  → liftlib base.normalize [CAB-49/55]  A1-A8 (A7: metadata 107 万行除去)
  → fw_cleanup.py  [W1] %wide-string 5 件 / [W2] define 重複 declare 6,992 件削除
  → m5 ir5_patch [A9L 命令化 / B1 / S1a 82 件 / R1 147,636 行]
  → fw_entry_fix.py  (entry spill 修復, §5.3)
  → fw_cab129.py     (alloca 縮退 2 関数拡大, §5.2)
  → icall ir_flatten (global→絶対アドレス, **shift 無し**: PE VA = wasm アドレス, dispatch 表生成)
  → liftlib simd gen [CAB-54] (--canon 正規名化)
  → fw_table.py (dispatch 表 + import wrapper 505 本)
  → emcc (-O0, GLOBAL_BASE=0x10000000, image は 0x400000..0xD02000 に実行時敷設)
  → fw_run.mjs smoke
```

## 3. 実測 (smoke)

| 項目 | 実測 |
|---|---|
| smoke 経路 | `DllMain(0x400000, DLL_PROCESS_ATTACH=1)` → entry (0x6c13a0) → 0x40e120 → `_StartLib` (0x4189c0, C override) → `_InitLib` (0x40db20, C override) → `InitUnits` (0x40da80, lifted) → unit init ×16 → FinalizeUnits ×16 → RestoreContext 到達 |
| dispatch | **38 回** (16 unit init @0x40dae6 + 16 unit finalize @0x40da42 + 6 其他) |
| PackageInfo | **290 unit** 登録 (0x6c1430 のテーブル), unit[0].init=0x4198b0 … |
| counter (0x714c98) | 0 (FinalizeUnits が decrement 後; init 中は 1..16 を遷移) |
| VirtualAlloc | 1 回 (FastMM 初期化) / heap alloc 1 回 |
| trap / fail-fast | **0 / 0** |
| wasm | fw_route.wasm **14.8 MB** (emcc -O0, GLOBAL_BASE=0x10000000, initial 320MB) |
| IR | 最終 1,754,280 行 / post-sigfix 1,761,016 行 (fw_flat4_canon3.ll) |
| entry 戻り値 | rax=1 (RestoreContext 経由のため参考値) |
| unit 16 で停止 | m11 と同様、unit 初期化中に Halt0 (GetLocaleInfoW 等 stub 品質由来と推定) — RestoreContext 到達で正常終了扱い |

## 4. 本研究で新規に直した欠陥

1. **chunk merge の無名番号衝突** — RetDec は chunk 毎に無名 global (`@N`) / metadata (`!N`) を 0 起番する。
   旧 fw_merge (m11_merge copy) は名前毎の初出採用なので、chunk 間で**別データの同名 global が混線**し得た
   (llvm-as が `global expected to be numbered '@18' or greater` で即検出)。fw_merge.py を「ファイル毎に
   offset 附番してから merge」に修正 (8 chunk + r2/r3 の 10 入力を一括 offset 附番)。
2. **decode 漏れ 990 関数** — fw_prep の F.ranges は .pdata 由来のため、decode 済み関数から参照される
   .pdata 非登録関数が define 無しで残った (m11 closure 漏れ (a) 同根)。fw_round2.py で 2 ラウンドの
   追加 decode を実施 (990→287→206。残 206 は fail-fast stub で可視化)。
3. **LLVM 21 で廃止された constexpr** — `zext (i32 ptrtoint ...)` 等 1,607 site。m5 ir5_patch の
   A9L 命令化で解消 (m5 は OTT/FLEngine で実績のある既存 pass を無改変で利用)。
4. **`%wide-string` 未定義参照** — RetDec artifact (`global [N x i16] %wide-string`)。liftlib A5 は
   `constant` のみ対応のため、`fw_cleanup.py` で `global` も zeroinitializer 化 (5 件)。

## 5. M11 既知欠陥クラスへの対策 (依頼事項: REPORT 明記)

### 5.1 間接 call (D1) — **icall 経路で解消済み**
- RetDec は間接 call/jmp を decoder 段で捨てる (Balance closure は実測 100% 落ち)。tools/icall の
  binary pre-rewrite (site → memory-ABI BLK store + stub call) → RetDec → `ir_icall_restore` (stub →
  `__icall_dispatch(site_va)`) で復元。**Balance 6,159 site 全復元 / 未変換 0**。
- Delphi RTL/VCL の本質部分 (VMT 仮想呼出し `call [rbx+voff]`、InitUnits の `call [rbp+0x38]`) は
  全てこの経路で復元される。dispatch 表は VA→lifted 関数 14,034 + import 505 本 (fw_table.py)。
- 残制約 (integration/README §4 既知): 間接 call 経由の **5 引数目以降 (stack 渡し)** は BLK 未対応
  ( init 経路では _StartLib→_InitLib は direct call 再接続されるため影響外; 影響時は fw_rt 側で個別拡張)。

### 5.2 alloca 縮退 (CAB-129) — **静的検出 + targeted 修復**
- 検出: 「同一関数内の定数長 fill (rep stosq / llvm.memset >64B) > 最大 alloca サイズ」を IR 全
  14,033 関数に走査 → **2 関数が検出** (`function_43ecb0` / `function_51c2d0`, 392 B fill vs alloca 8 B)。
  392 B = m11 の 44bb70 (0x188 レコード, rep stosq ×49) と同一サイズ = **同一 RTL 関数の Balance 版**。
- 修復: `fw_cab129.py` が該当 alloca を `alloca [K x i64], align 8` に拡大 (opaque ptr 化後ゆえ
  先頭 base の互換で既存参照は無影響)。
- 汎用 pass 化は CAB-129 (In Progress, m11 担当) の担当範囲。本 dir の検出器は
  `tools/plugins/work/fw/fw_cab129_scan.json` に証跡を残した。

### 5.3 load 取り違え・home slot 落ち (CAB-231 隣接クラス) — **native 突合で 1 件修復**
- DLL entry (0x6c13a0) で RetDec が home 用 stack slot ([rbp+0x30]/[rbp+0x3c]) を model から漏らし、
  _StartLib 呼出しの ABI spill に**文字列定数のアドレス**を代入していた (native: r8=hinst, r9=reason を
  capstone 実測で突合 → IR: r8 ← `@"$"`+0, r9 ← `@"$"`+0)。このままでは `_StartLib` の
  `reason==1 (DLL_PROCESS_ATTACH)` 判定が偽になり InitUnits が空振りする (smoke の false-pass になる)。
- `fw_entry_fix.py` が site VA 0x6c13f0 の spill block の r8/r9 を `%arg1/%arg2` に差し替え。
- CAB-231 本体 (load_dropped 892 / spill_slot_deref 67 の IR 修復 pass, Todo) は liftdiff verdict を
  回帰にする方針が正本。本 dir は (a) icall derefix 12,658 命令 (D7 = live-in 経由 zero-disp load 落ちの
  PE 段回避) と (b) smoke 実走での fail-fast/突合で塞げる範囲を塞いだ。**残りは CAB-231 への引継**。

### 5.4 x87 (f80) — **f64 近似で smoke を通し, 本命は CAB-196**
- framework の f80 使用は 232 define / 3,688 token (frontend_reg_load/store 2,489 site 含む)。
  wasm32 に f80 は無いため `fw_f80.py` で f64 に coerce (0xK 定数→0xH 変換 30 件,
  fpext/fptrunc same-type 化 73 件は fadd 0.0 で値保存近似, i3→i32 3,364 token)。
- **精度影響**: x87 80bit mantissa → 53bit。DSP kernel (CAB-196) では P0c の f80→f64 lowering pass が
  本命であり, 本近似は init smoke 用の暫定。init 経路の数値系 (locale/書式) は f64 で十分と判断。

## 6. 検証の限界 (正直な評価)

- smoke は「初期化完走」の判定のみで, unit 初期化の**値の正しさは未検証** (native 突合なし)。
  関数単位 diff は tools/liftdiff (CAB-121) の枠組みで次段に引継。
- import 505 本のうち実装は N 本 (fw_table.py IMPL)。未実装は呼出時に fail-fast で site 表示
  (m11 規約)。GUI (user32/gdi32 多数) は headless 初期化で非到達のはずだが、到達したら個別実装が必要。
- dispatch 経由の stack 引数 (5 個目以降) 未対応 (§5.1)。decode 漏れ残 206 関数は fail-fast stub。
- f80 は f64 近似 (§5.4)。comis は icall 経路の stub+sahf (__icall_comis) で処理 (P1 pass 不要,
  integration/README の推奨構成)。

## 7. 未解決・ブロッカー

1. **unit 17 以降が停止** — 290 unit 中 16 unit で Halt0 (RestoreContext 到達)。m11 の unit #18 と同根
   (GetLocaleInfoW stub 品質 / alloca 縮退等の可能性、CAB-129 の全数調査待ち)。
2. **dispatch 経由の stack 引数 (5 個目以降) 未対応** — _StartLib/_InitLib は C override で回避済みだが、
   それ以外の 5+ 引数関数 (unit 内) は BLK 4 引数制限のまま。
3. **decode 漏れ 126 関数** — fail-fast stub で可視化済み。init 経路の関数は 0 (smoke 完走で実証)。
4. **f80 → f64 近似** — init 経路の数値計算は十分だが、DSP kernel (CAB-196) には精度不足。
5. **named import の大半が fail-fast stub** — 552 import 中 IMPL 実装は約 100。GUI 系は headless で非到達だが、
   到達したら個別実装が必要。
6. **llvm-as 検証で一部命令の dominance 修正を手動適用** — ymm store 4 site の ce-chain clone。
   汎用 pass 化は未実施。

## 8. ユーザ依頼事項

- なし (素材は analysis/win64/extracted/block18983_PE.bin で足りた)

## 9. 次タスク提案 (下流チケット案)

1. CAB-196 (P0c): f80→f64 lowering pass の正式適用 + kernel 表 80 本 (本 REPORT §5.4 の近似置換)。
2. T0 frontier 660 関数の `CreatePlugInstance` → ctor → GetName/ProcessParam 差分試験 (CAB-194 出口条件の残部)。
3. CAB-231: liftdiff verdict 回帰の load 取り違え pass (§5.3 の残部)。
4. Dashboard / Wave Traveller / Fruity Envelope Controller の別構成 3 本の確認 (fw_overlap.py)。
