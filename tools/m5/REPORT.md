# tools/m5/REPORT.md — M5 (Delphi lift → wasm E2E + native bit-exact)

> **参照専用 (LIFTLIB-1 / #224)**: 本 dir の lift IR pass・スクリプトは新規実行・改変しない。IR pass の正本は `tools/liftlib` (対応表: `tools/liftlib/README.md`「旧 dir pass → liftlib 対応表」)。既存 e2e 成果物・本 REPORT は歴史として残置し、旧成果物に対する既存 e2e (`tools/m7/m6_e2e.sh`・m8/m9/m10 の `*_e2e.sh`) が引き続き PASS することは `tools/liftlib/REPORT.md` §15 で実測。

独立検証 (subagent) が全テストを再実行し, ir5_patch の実測バグ 4 件を修正した上で
生成。メイン成果物は tools/m5/ 配下 (`work/` は実行成果物でコミット対象外)。

## 0. 結論

| 検証 | 結果 |
|---|---|
| (a) Delphi 純計算 2 関数 (SSE) の wasm bit-exact | **8/8 PASS** — wasm(lifted IR) = 実機 x86 機械語 (native_fx) = JS 参照実装, 32bit まで完全一致 |
| (b) FastMM lift → shim heap 結合 wasm | **3/3 PASS** — `mm_test_1000` (alloc=free=1000) / double-free fail-fast abort 検知 / underflow は IR 分岐で解放抑制+リーク検知 |
| (c) try-finally (0x409fe0) lift 実測 | **部分 PASS** — finally 経路 (末尾 412d60 liberate) の alloc/free 整合 ✓。ParamCount 戻り値は off-by-one (tokens-1) — 既知課題 §6 |
| [A9] constexpr 命令化 lift | **emcc 通過** — m3 ft7.ll (677 define / 残存 187) → 残存 2 (合法形のみ) → `a9_ft7.cjs` ビルド+instantiate 成功 |

## 1. 選択根拠

- **(a) SSE 純計算 2 本** — `scan_pure.py` が .pdata 境界 (M2 実測 57,816) を ground
  truth に capstone 特徴量走査し leaf (call 0/indirect 0) 878 件を抽出。
  このうち命令列が SSE 逐次演算のみで DLL 内定数 1 個 (+2.0f x4) 依存の
  `0x6a7540` (waveshaper) / `0x6a2fb0` (distortion) を選択
  (= bit-exact 照合の独立性が最も高い素材)。参照実装は JS (Math.fround で
  SSE 単精度逐次丸めを再現; lift IR と別実装のため非循環)。
- **(b) FastMM (0x412d60, 66B)** — M2 §3.2 の caller xref 15,505 の hot entry。
  FastMM ブロックレイアウト (refcount@+8/len@+12/payload@+16) は lift IR 実測
  (0x414ad0) と合致。heap は M4 shim (`../shim/src/heap.c`) を**読取のみ**で
  静的リンク (`git status` で shim 側無変更を確認済)。
- **(c) try-finally (0x409fe0, 123B, E+UHANDLER)** — M2 §3.1 #1 選択関数。
  table-SEH の unwind/handler は IR に残らない (M2 実測) ため wasm EH は
  不使用; finally は末尾の 412d60 呼出が通常 path で走る構造として lift。
- **[A9] 対象 = M3 ft7.ll (mm closure 677 define)** — M3 引継ぎ (残存 constexpr
  187 件) を M5 の A9L 命令化 lift で実際に潰す実証。

## 2. pipeline

```
FLEngine_x64.dll (PE32+ Delphi x64)
  → RetDec v5.0 --select-ranges --select-decode-only (l_*.ll 単関数抽出)
  → ir5_patch.py  (M3 継承 A1..A8, B1 + M5 追加 A9L/A9L2, S1, C8, C9, C1, C13)
      [A9L]  残存 constexpr → 命令化 (ptrtoint/inttoptr/算術/icmp; LLVM 17
             で廃止された function-local name 参照組を解消)
      [S1]   SSE __asm_* 疑似 call の store 復元 / lane 出入力 lower
      [C8]   xmm 引数の linear memory VA 取込 (呼出側が書込)
      [C9]   FastMM 内部 alloc/free → shim heap (mm_allocw/mm_free_inner) redirect
      [C13]  external global → 0 初期化定義 (wasm-ld リンク解決; DLL 実データ
             の取込は M6 に委ねる仮置き)
  → emcc -msimd128 (-O1; c は -O0 併用) → wasm → node (.mjs) 実行
  → native_fx (実機 x86 機械語を VA 通り mmap 敷設して直接実行) と照合
```

## 3. bit-exact 結果 (再実行: 2026-10-10, 本検証)

`node work/m5_compare.mjs` → **ALL PASS (rc=0)**:

| 構成 | ケース | wasm=ref | native=ref | wasm=native |
|---|---|---|---|---|
| a1 waveshaper (k=0/0.5/2/8/-3.25, n=20) | 5 | true | true | true |
| a2 distortion (seed=222/777/beef, n=24) | 3 | true | true | true |

- native 側は `build_native_fx.sh` で再ビルド済み (RC=0)。`FLEngine_x64.dll` の
  .text/.data/.rdata を VA 0x400000 起点に MAP_FIXED 敷設し MS x64 規約で直接実行 —
  lift IR/wasm に触れない非循環参照。
- a2 は DLL 内定数 g=2.0f を `work/a2g.c` で IR の @global_var_13e75a8 に一致
  させて供給 (= IR アドレス空間 == wasm linear memory モデルの再確認)。

## 4. (b) FastMM × shim heap + fail-fast 非対称性

- `build_b.sh` 再ビルド (RC=0) → `b_test.mjs` (mm_test_1000 alloc=free=1000, rc=0)
  → `run_fffail.sh` (**double-free fail-fast 疎通 OK, abort rc=1 + stderr 検知文**)
  → `b_underflow.mjs` (rc=0)。すべて RC=0。
- 非対称性の接続: double-free は **shim 層** (`mm_harness.c` の free-bit shadow +
  abort, 間接的に shim heap 2 重解放) で fail-fast。underflow (refcount<1) は
  **lift IR 側の分岐** (`v2 < 1 → exit`) が解放を抑制するため abort しない —
  こちらは事後の freed 状態確認でリーク検知 (設計どおりの非対称)。
- shim の fail-fast 面 (`../shim/src/failfast.c`: 未実装 Win32 API abort) も
  同一リンクに含まれる (tools/shim は読取のみ)。

## 5. [A9] constexpr 命令化 lift (a9_ft7_report.json 照合)

- 入力 `../m3/work/ft7.ll`: **677 define / 残存 constexpr 187**
  (add 5 / ptrtoint 119 / inttoptr 20 / bitcast 43 — 本検証で再計数・一致)。
- 適用結果: **constexpr 命令化 143 行 → 残存 2 (inttoptr ×2, `global ptr`
  初期化子のみ — LLVM 17 でも合法)**。`b1_fixed` 278 (未初期化 alloca の 0
  決定論化), s1_stores 31。
- `build_a9.sh` → **`work/a9_ft7.cjs` ビルド成功 (rc=0)** + node で instantiate
  成功 (677 関数 closure 全体が wasm に乗る)。export 0 は本段では通過実証が
  目的のため未 export (呼出実験は M6 で CLI/main 経路とともに)。
- 本検証で ir5_patch を 4 点修正 (改訂版で本結果を再生成):
  1. B1 が ptr 型 load を `xor ptr 0, 0` (不正) にしていた → `inttoptr i64 0 to ptr`
  2. cast lift のレジスタ採番が進まず同一定義重複 → cnt を SSA 風に前進させる
  3. A2 が配列型/関数型 pointer (`[3 x i8]*`, `i32 (ptr)*`) を opaque 化から漏れ
  4. icmp constexpr 未対応 + 幅不一致 (store i32 ptrtoint...to i64) + 型接頭辞
     付き即値の値化 — trunc/zext/inttoptr 補完と `_mat_sym` 共通化で解消

## 6. 既知課題

- **(P2) ParamCount off-by-one**: lifted `function_409ef0` (ParamStr 抽出) の
  戻り値/終端判定が 1 トークン短く出る (`c11.json` の部分修正では未解消)。
  finally 経路自体は整合。M6 で IR 精査のこと。
- **(P1) DLL データ実体の未取込**: [C13] は external global を 0 初期化で
  仮置き (FastMM 管理表 @1 は 256KB 後見)。実データ (VMT/RTTI/管理表初期値) の
  イメージ取込 pass が M6 の前提条件。
- **(軽微) `heap_shim_lazy.c` は 0 バイト** — 遺物プレースホルダ (未使用;
  build は shim/src/heap.c を直接リンク)。次回整理時に削除可。
- **(軽微) `__asm_*` SSE helper の委譲面** (`msimd.c`) が網羅でなく, 未実装
  helper は wasm-ld 警告 (ERROR_ON_UNDEFINED_SYMBOLS=0) のまま 0 挙動。
  (a9 通過時の警告一覧が M6 の helper 実装チェックリストになる)。
- RetDec 全体リフトは FLEEngine 規模で 2-3h/15GB (m2 REPORT §2 実測) —
  M6 以降は `--select-ranges` 運用を継続。

## 7. M6/M7 への引継ぎ

- **M6**: (1) DLL データセクション取込 pass (C13 の 0 初期化を正データに置換)
  (2) VMT 間接 call の direct 化 (m2 delphi_inventory.md §1 の class 表注入 —
  bx_cfg_* 48 関数抽出物が対象候補) (3) ParamCount off-by-one 修正
  (4) __asm_* helper 実装面の拡充 (5) a9 closure からの CLI/main 経路 export 実験。
- **M7**: (b) の FastMM×shim 統合をエンジン実行 path (CreateFruityInstance 側)
  に拡張。fail-fast 非対称性の設計 (shim 層 abort / IR 分岐抑制) は M5 実測の
  まま継続利用可。
- 引継ぎ物: `work/a9_ft7.ll` + `work/a9_ft7_report.json` (A9 実測),
  `work/work_mmfun.closure.json` (closure 選択), `work/xmm_a.json` (C8 侵入 VA),
  `work/c11.json` (レジスタ修復 cfg), `tools/m2/work/engine_win.drc.dsm`
  (decode 完了済み関数境界 70,018 — M6 の lift 対象一覧の正)。
