# INTEGRATION — 実 FLEngine への GUI shim 結合手順書 (CAB-173 向け; 準備: CAB-156)

実 FLEngine の結合そのもの (CAB-173) は CAB-5 (m11 完走) 後。ここは「結合時にやること・守る ABI 制約・結果の見方」と、実 FLEngine 無しで検証済みの準備物をまとめる。
数値はすべて `bash tools/gui/e2e.sh` / 各スクリプトの実測。

## 1. 準備物 (すべて tools/gui/ 配下)

| 物 | 場所 | 役割 | 検証 |
|---|---|---|---|
| 到達 API ログ | `src/gui_reach.c` + 生成 `build/gui_reach_tab.c` / `gui_wrap_i64.c` | どの shim API が何回・どの順で呼ばれたか。`GUI-REACH` 行を console/LOG リングへ、`gui_reach_json()` で JSON | `test/reach_test.c` 11, e2e 6d (36 API 到達を host console で確認) |
| 署名 adapter 生成 | `integ/gen_adapt.py` → `build/gui_adapt_w32.c` | m11 IR の wasm32 署名 → shim の int64 ABI (突合表 `integ/INTEGRATION_XCHECK.md`) | `integ/sigprobe.sh`: 177 declare で wasm-ld 署名不一致 **0** (陰性対照 177)、`test/adapt_test.c` 28 |
| コールバック hook | `gui_set_icall_hook()` (`src/gui_core.c`) | lpfnWndProc/TIMERPROC/EnumProc の VA 解決を `m11_icall` へ委譲 | selftest 「icall hook」5 |
| 結合用 .o 出力 | `integ/build_objs.sh <outdir> [--reach]` | m11 の `work/obj/*.o` に足せる形 (改名・`GUI_NO_K32`・-pthread) | 7 オブジェクト・未解決 import 0 |
| fnmap / WNDPROC 自動化 | `integ/lift_fnmap.py` ← `lift/gui_lift_post.py` | RetDec C 経路の `--wndproc` 手指定を廃止、fnmap 生成を汎用化 | `e2e.sh` 3/6 が `--wndproc` 無指定で ALL PASS、`lifted.c` は手指定時とバイト一致 |
| 結果解析 | `integ/reach_report.py` | `GUI-REACH` ログ → 実装必須 stub / 昇格候補 / 未到達 P0 | e2e が `build/e2e/reach.log` を出力 |

## 2. リンク手順 (CAB-173 で実施)

前提: m11 が `work/boot_final3.ll` → `work/obj/*.o` → `emcc work/obj/*.o` の流れ (`tools/m11/m11_build.sh`)。m11 は変更せず、**結合用ビルドスクリプトを CAB-173 側にコピーして**次を足す。

1. **オブジェクトを作る** (m11 と同じ `-pthread` で揃える; §4-3)
   ```
   bash tools/gui/integ/build_objs.sh <m11>/work/obj_gui --reach --ir <m11>/work/boot_final.ll   # 到達ログ付き。通常は --reach 無し
   ```
   shim 本体 (`gui_core/gdi/stubs`) は `gui_rename.h` で `gui_impl_<Name>` に改名され、公開名は `gui_adapt_w32.o` が **IR の署名で**定義する。
   kernel32 級 5 名 (ExitProcess/GetModuleHandle[AW]/OutputDebugString[AW]) は `-DGUI_NO_K32` で除外済み (shimx が提供)。
2. **m11_winstubs から GUI 名を除外**: `llvm-nm --defined-only <m11>/work/obj_gui/*.o` の定義名を m11 の `work/defined_c.txt` に追記してから `m11_genstubs.py` を回す (`M11_EXCLUDE`)。`build_objs.sh` が `exports.txt` に出力。
   (shimx の weak 9 本の重複解消は CAB-171 の担当。本 shim 側に要求は無い。重複したら `gui_adapt_w32.o` の名前と shimx の名前が衝突する — その場合は REPORT に記す)
3. **emcc リンクに `work/obj_gui/*.o` を追加**し、export に `_gui_shared_ptr,_gui_shared_size`(+ `_gui_reach_dump,_gui_reach_json,_gui_reach_distinct`) を足す。`-sGLOBAL_BASE` は ≥ 0x10000 (m11 の 0x10000000 で可)。
4. **icall hook を起動前に 1 回設定**:
   ```c
   extern unsigned long long m11_icall(unsigned long long t, unsigned long long, unsigned long long, unsigned long long, unsigned long long,
                                       unsigned long long, unsigned long long, unsigned long long, unsigned long long);
   static unsigned long long gui_icall(unsigned long long t, unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d)
   { return m11_icall(t, a, b, c, d, 0, 0, 0, 0); }
   /* 起動時: gui_set_icall_hook(gui_icall); */
   ```
   `m11_icall` は VA→trampoline (8×u64 統一署名) で、WNDPROC の引数個数が 4 でなくても `call_indirect` 署名不一致を起こさない。miss 時は 0 を返し `m11_icall_miss` を加算するだけなので、
   結合側で WNDPROC 呼出前後の miss 増分を見て fail-fast するとよい。`WNDCLASS.lpfnWndProc` の定数アドレス: `python3 tools/gui/integ/lift_fnmap.py --ir <m11>/work/boot_final.ll` が現 IR の `RegisterClassW` 呼出点 (例 `function_52a7f0` → WNDCLASS 0xfbe810) を列挙する。
   **リソース供給 hook** (`LoadStringW`/`LoadBitmapW` 用; CAB-159): shimx 側のリソース供給 (`shimx_set_resource_provider` / FindResource 系) を同様に 1 回接続する。
   ```c
   static int gui_res(unsigned long long hinst, unsigned type, unsigned id, const void **data, unsigned *size);   /* RT_STRING=6 は (id>>4)+1 のブロック, RT_BITMAP=2 は DIB */
   /* 起動時: gui_set_resource_provider(gui_res); */
   ```
5. **ブラウザ host**: `GuiHost.attach({canvas, memory: Module.wasmMemory, base: Module._gui_shared_ptr(), ...})` (README)。FL は**ワーカ上**で動かす (§4-4)。
6. **到達 API ログの回収**: ExitProcess 経路 (`GUI_NO_K32` では shimx の exit hook から `gui_reach_dump()`) / fail-fast 時 (自動) / 任意時点で `Module._gui_reach_dump()`。host の `GuiHost.logs` に `GUI-REACH` 行が溜まる。
   `python3 tools/gui/integ/reach_report.py <ログ>` で「到達した stub = 実装必須」「P2/P3 の昇格候補」「未到達 P0」を出し、IMPORTS.md の P 分類を更新する (CAB-173 の完了条件)。
7. 突合表の再生成: `python3 tools/gui/integ/gen_adapt.py --ir <m11>/work/boot_final.ll` (lift 範囲拡大で declare が増えたら再実行; (c) 署名不一致 0 が条件。`--refresh-fixture` で fixture も更新)。

## 3. 署名/コールバックの扱い

- IR の GUI declare 署名 (`ptr`=i32, WPARAM/LPARAM=i32, `i1`, `i16`, `%tagPOINT` 値渡し) は adapter で int64 化 (変換表は `INTEGRATION_XCHECK.md` §2): ptr=zero-extend / i32=sign-extend / i16,i8,i1=zero-extend / ≤8B struct=int64 詰め。
- 現 IR の GUI declare 177 名の内訳: 実装済み **153** / fail-fast stub **24** (CAB-159 の P1 50 名実装で 132/45 から改善; 残る stub は P2/P3 = メニュー・ImageList 等) / 署名不一致 0 / shim 不在 0。残り 251 名は IR に未出現。
- コールバック: `gui_call4`(WNDPROC/TIMERPROC)・`gui_call2`(EnumWindows 系) が hook 経由。hook 未設定時は `GuiFnMap` ({VA, fn}) 経由 (RetDec C 経路; `gui_register_fnmap`)。
- RetDec C 経路 (テスト PE): WNDPROC 候補は `RegisterClass*`/`SetWindowLong*` を呼ぶ関数が VA 定数で取得する関数を自動検出 (`[post] auto-detected WNDPROC: ...`)。VCL の `MakeObjectInstance` 等、データ表経由で渡る WNDPROC は静的検出不能 → m11_icall 経路が前提。

## 4. ABI 制約チェックリスト (結合前に全項目確認)

| # | 項目 | 理由 / 実測根拠 | 確認方法 |
|---|---|---|---|
| 1 | `-sGLOBAL_BASE` ≥ 0x10000 (テストは `1048576`) | shim は `< 0x10000` のポインタ値を atom/MAKEINTRESOURCE/単一文字と解釈。RegisterClass が fail-fast して発覚 (REPORT §4-7) | リンク行 |
| 2 | **ハンドルは 31bit 内**: 発行値 = gen(7bit)<<24 \| type(4bit)<<20 \| idx(20bit) < 2^31。ストック/カーソル/アイコン (0x7F000000+, 0x7E000000+)・DeferWindowPos (0x7DEF0000) も < 2^31 | lifter が HWND/HDC を int32 に潰しても同一値 (REPORT §4-6)。wasm の ptr(i32)/sign-extend でも不変 | `adapt_test` が WND/DC×2/BMP/BRUSH/PEN/FONT/RGN/PAL/stock×2/CURSOR/ICON/DEFER の 14 種が正の 31bit 値であることを assert |
| 3 | 全 TU を `-pthread` (atomics + shared memory) で揃える | shim は futex 待機・SAB を使う。ST ビルドはブロック箇所で fail-fast。atomics 無し TU が混ざると wasm-ld が `--shared-memory` を拒否 (m11 は現状 node 向け非 pthread → 結合時に再ビルド) | `build_objs.sh` 既定 / リンクログ |
| 4 | FL の GUI スレッドは**ワーカ** (`-sPROXY_TO_PTHREAD` か専用 worker)。host (`gui.ts`) だけがメインスレッド | `gui_sh()` が host_ready を futex 待機 (≤30 s、超過で fail-fast)。メインスレッドでは `Atomics.wait` 不可 | e2e の `crossOriginIsolated`/`sab` assert |
| 5 | **wasm メモリ上限 < 2 GiB** (m11 の MAXMEM 0x72000000 は可) | IR の LPARAM/WPARAM は i32。ポインタを LPARAM に載せる API (`WM_SETTEXT` 等) は adapter で sign-extend されるため、≥2^31 のアドレスは壊れる | リンク行 `--max-memory` |
| 6 | `ALLOW_MEMORY_GROWTH` 可。ただし host/worker は `memory.buffer` を都度取り直す | grow 変種 e2e (初期 3 MiB → 3.8 MiB) で全一致を確認済み | `e2e.sh` 6b |
| 7 | GuiShared (100,672 B) は静的データ領域。`gui_shared_ptr()` で基点取得、オフセットは `_Static_assert` 固定 | `include/gui_proto.h` ↔ `src/runtime/gui_proto.ts` | tsc + e2e |
| 8 | UI スレッドのスタックは余裕を (Delphi の深い WndProc 連鎖 + 入れ子 SendMessage)。pthread 既定 64 KiB は不足し得る → `-sDEFAULT_PTHREAD_STACK_SIZE=1048576` 以上 | テストは `-sSTACK_SIZE=1048576`。FL 実機での必要量は**未実測** | CAB-173 で実測 |
| 9 | 構造体は Win64 レイアウト (ポインタ 8B スロット) | lifted メモリ上の WNDCLASS/PAINTSTRUCT 等と一致させるため (`include/gui_win32.h`) | selftest |
| 10 | 同名シンボル重複: `ExitProcess`/`GetModuleHandle[AW]`/`OutputDebugString[AW]` は `GUI_NO_K32`、GUI 名は winstubs から除外 (§2-2) | wasm-ld duplicate symbol | `llvm-nm` |
| 11 | `m11_icall` hook 設定漏れ = 未解決 VA を関数ポインタ扱い → 即クラッシュ。`< 0x10000` のみ fail-fast | `gui_resolve_fn` | 起動時に設定 |
| 12 | 到達ログの有無で性能が変わる (adapter 経由 1 呼出 ≈ atomic add 1 回) | 計測は未実施 (推定) | 通常ビルドは `--reach` 無し |

## 5. テスト PE ハーネスの FLEngine 形状への拡張方針

現状ハーネス (`test/gui_app.c` → mingw PE32+ EXE → RetDec → emcc) は **EXE 形・1 TU・WNDPROC=コンパイラ直接参照・アプリが main スレッド**。FLEngine_x64.dll との差を段階的に埋める:

| 段 | 追加するテスト PE の形状 | 検証対象 | 備考 |
|---|---|---|---|
| H1 | **DLL 形**: `-shared` + `DllMain(DLL_PROCESS_ATTACH)` + export `InitUI`/`Run`。host 側ドライバが DllMain → InitUI → メッセージ pump を呼ぶ | DLL entry からの GUI 初期化、`gui_register_fnmap` を DLL 内関数に対して使う経路 | m11 の `m11_boot_enter` 相当をドライバ側に模す |
| H2 | **WNDPROC をデータ表/ヒープ thunk 経由で保持** (VCL `MakeObjectInstance` 風: クラス登録は共通 thunk、実体は `SetWindowLongPtr(GWLP_WNDPROC)` でサブクラス化) | 自動検出不能な WNDPROC → `gui_set_icall_hook` 経路のみで動くこと | selftest の icall hook で原理は検証済み。PE 版は `lift/` に hook 差込口を追加 |
| H3 | **署名の違う WNDPROC** (引数 1〜3 個に縮んだ lift 結果) を trampoline (8×u64) 越しに呼ぶ | `m11_icall` 相当グルーで署名不一致 trap が出ないこと | テスト用 `icall` を 5 行で再現可能 |
| H4 | **別スレッド**から PostMessage/SendMessage (FL のオーディオ/ワーカ) と WM_TIMER 競合 | 他スレッド同期 SendMessage の wasm 版 (native では selftest 済み) | `PTHREAD_POOL_SIZE` を 2 → 4 に |
| H5 | **wasm32 IR 署名**で GUI API を呼ぶ lifter 経路 (RetDec x64 ではなく m11 の wasm32 型 IR を生成) | 実機の呼び方 (`ptr`=i32, `%tagPOINT` 分解) と adapter の整合を**実行時**に確認 | 現状 sigprobe は署名検査のみ (実行は native wiring まで) |
| H6 | FL 実リソース: `LoadStringW`・ビットマップ資源 (`LoadBitmapW`)、アイコン資源 (`LoadImageW`/`CreateIconIndirect` は GUI-2) | `gui_set_resource_provider` に m11/shimx のリソース供給を接続 (§2-4) | ユーザ素材は触らない |
| H7 | 既定ウィンドウクラス (BUTTON/EDIT 等 comctl32) と DPI/複数モニタ API の実呼出順 | 到達ログで確定 | CAB-173 の入力 |

優先は H1→H2→H3 (結合直後に必ず踏む)。各段で `e2e.sh` のゴールデン比較 (差 0) を維持し、到達 API ログを必ず付ける。

## 6. 未検証・限界 (推定は推定と明記)

- adapter の 32bit 化 (zero/sign-extend) は wasm-ld の**型検査**と native wiring で確認。wasm 上で実際に IR 署名の呼出を実行する検証は H5 待ち。
- 到達ログの性能影響は未計測。LOG リング (2048 レコード, 1 行 ≈ 2〜3 レコード) は producer 側が満杯時に host の drain を待つ設計 (落とさないがブロックする)。
  到達名が数百に及ぶ FL 実機では dump 中に host の消費待ちが入る → host が動いている状態で呼ぶこと。大量時は `gui_reach_json()` を使う。
- m11 の実 WNDCLASS 内容 (VA) は m11 完走後でないと確定しない。
