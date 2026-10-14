# REPORT — OTT-T5 (CAB-138): CRT 初期化の等価置換 + override 4 件の実機械語 lift 置換

親チケット: CAB-7 (Done) / 前提: CAB-137 (entry lift 85/85, In Review) / 関連: CAB-135 (AVX/FMA unsup — 引継 §6)

## 0. 結論 (先出し)

- **判定: 要件を満たす。** `bash tools/ott/crtinit/crt_e2e.sh` = **PASS**。
  - 新 scenario **9 本** (float formatter 13 param × 4 値 sets / op34 effGetOutputProperties / op7 dispatcher / DSP params 全 0 の数学エラー経路 3 本) が **native 実機械語と全突合項目一致** (文字列 buffer / rax / obj 0x328B 全 qword / HeapAlloc alog / audioMaster 呼出回数)。FAIL 0。
  - 既存 entry **85 scenario** を CRT 初期化版 build で全数再突合 = **85/85 PASS** (旧 build では native が crash していた float 経路も含め nat_crash 0)。
  - 既存 DSP e2e **89 scenario・全 cell bit-exact (正本 `tools/ott/REPORT.md`)** の継続 PASS と entry e2e (旧 build 全 85) PASS
    (旧 build — 改変は lifter の mxcsr 1 点のみ, §4)。
- **ICALL-76 訂正 (§10)**: api-set 表は **34 entry** (0x110 B)。旧記載「32 entry」と `APISET_N 32` は誤りだった。修正後も判定 (crt_e2e PASS・9 本 / 85 件) は不変。
- **CRT 初期化は (b) C 等価置換を採用** (DllMain / `_CRT_INIT` / `_initterm*` は実行しない):
  UCRT が `__security_cookie` で encode する関数ポインタ表 (**api-set 表 0x18026c9f0** ほか 4 slot) を
  `enc(NULL) = cookie` に事前初期化 + `__FlsIndex` 設定 + loader 系 import 4 種 (LoadLibraryExW /
  GetProcAddress / FreeLibrary / GetModuleHandleW) を両側で提供すれば、**DLL 自身の遅延解決機械語
  (0x1801c38c8) と getptd / locale / stdio-format が実行され、native と wasm が同一状態に収束する**。
  (a) 実 lift (XI 971 entry + closure) は不要と判断 — 根拠 §2。
- **float formatter 系が native と突合できた** (CAB-137 の未達 §2.3 を解消): 実測出力は
  param 既定で `"100" / "0.0" / "--"`、値 mix で `" 0" / "998" / "-48" / "19.1" / "-20.0" / "BYPASS"`、
  op34 で `"OTTOut 1" / "OTTOut 2"` — native/wasm byte 一致。
- **override 4 件を置換** (実機械語 lift に): 実は旧 4 件は 89/85 matrix で**一度も実行されていなかった**
  (cov_all / cov_entry に 0x1c8c00 等が無い実測 — 防御的暫定実装)。置換後、`_handle_error(double)`
  (0x1801c8c00) は新 scenario err_zero_* で**実行され native と bit 突合**。handle_error_f / sqrt_d/f は
  lift 済み・未実行 (§5)。
- **陰性対照**: `OTT_CRTINIT=0` で native **SIGSEGV (CFG dispatch 0x1801d2750 `jmp rax`, rax=
  0xae64b77e88c8000 = ror(cookie,50))** / wasm **`ott_unlifted` 同一 garbage VA** — 旧 fail-fast が
  両側で bit レベル同一に再現 (ret も native 0x1801c3e06 / wasm 0x301c3e06 で対応)。
- lift 集合: 207 関数 / 13,690 命令 (CAB-137 のコミット済み scenario からの再現値) → **258 関数 / 16,374 命令** (+51 関数: CRT 解決・getptd・
  vsnprintf・数学エラー経路)。native coverage 実測は **91 関数 / 5,974 命令** (entry 比 +35 関数)。
  数え方 (再計算: `python3 tools/ott/accept/acc_lift_set.py`): 関数 = `work/crtlift/lift_meta.json` の `functions` 配列長
  (override 対象 8 件は lift しないため除外)。命令 = `ninsn`。native coverage = `cov_crt.json` の `insn` を `.pdata` 関数境界で
  マップした関数数 / `insn` の要素数 (実装報告時の「90 関数 / 5,949 命令」は誤記・検収 REPORT §4.1)。
  ※ 実装報告時の 260/16,378 は、coverage の `getp_range` が idx 25..30 まで実行された状態 (uncommitted) で採られたもの。
  差は +2 関数 (0x180126310 / 0x180126320) / +4 命令で、いずれもコミット済み `entry_scen.py` の `getp_range` (idx 0..19)
  からは到達しない getParameter の idx 25..30 case。詳細は tools/ott/ACCEPTANCE_CAB137_CAB138.md §3.1。

## 1. 成果物 (tools/ott/crtinit/)

| パス | 役割 |
|---|---|
| `crt_e2e.sh` | 1 コマンド検収 (coverage → lift → 新 matrix → 85 再突合 → 陰性対照 → 既存 e2e 継続確認) |
| `crt_native.c` | native 参照ハーネス。`entry/entry_native.c` (→ `native/ott_native.c`) を**無改変 include** し、encoded slot 初期化 + loader 系 IAT 差し替え (`ott_crt_init_tables` / `ott_crt_patch`) を追加 |
| `ott_crt.c` | wasm 側の等価実装: `ott_crt_init_tables` (guest data に enc(NULL) 書き込み) + `imp_LoadLibraryExW/GetProcAddress/FreeLibrary/GetModuleHandleW/Tls*/...` + trampoline override 6 件 (`ovr_fls_*` ほか) |
| `crt_roots.py` | entries.json 生成 (DSP cov + entry cov + CRT cov + roots 55 + override 8) |
| `crt_scen.py` | 新 scenario 定義 9 本 (entry_scen.py の step 形式を流用) |
| `crt_nat.py` | native scenario runner (entry_nat.py を runner として再利用, SO 差し替え + CRT init, `OTT_CRTINIT=0` で陰性対照) |
| `crt_wasm.mjs` | wasm scenario runner (entry_wasm.mjs 由来 + `_ott_crt_init_tables` 呼び出し, `OTT_CRTINIT=0` で陰性対照) |
| `lift_crt.sh` | lift → C → emcc。override は **旧 4 件を外し** trampoline 6 + editor_null + am_shim の 8 件 |
| `run_matrix.py` | オーケストレーション (entry 版と同型, native 側だけ crt_nat.py) |

生成物は `tools/ott/work/crtlift/` (gitignore)。判定は `entry/cmp_entries.py` を再利用 (schema 共通)。

## 2. CRT 初期化経路の特定と (a)/(b) 判断

### 2.1 実行した CRT 経路 (実測 — DllMain は不使用)

```
[静的状態]  .data: api-set 表 0x18026c9f0 (34 entry, 全 0) / __security_cookie 0x180260ce0 = 0x2b992ddfa232 (静的既定)
            / __FlsIndex 0x1802610e4 = -1 / _matherr hook 0x18026cb88 = 0
[formatter 呼出]  effGetParamDisplay(0x18011e770) → fmt dispatch(0x18011e250) → snprintf(0x180105320)
            → vsnprintf(0x1801aaf5c) → __acrt_getptd(0x1801c20c8)
[解決]  getptd → FlsGetValue/FlsSetValue wrapper (0x1801c3d80/0x1801c3dc8)
            → api resolver 0x1801c38c8: decode(table[idx]) = ror(entry ^ cookie, cookie & 0x3f)
              ・decode == 0  → LoadLibraryExW("api-ms-win-core-fibers-l1-1-1" ほか) → GetProcAddress
                              → encode(rol(fn, 64-(cookie&0x3f)) ^ cookie) を表に書き戻す
              ・decode == -1 → 永久 unavailable (Tls fallback)
            → CFG dispatch 0x1801d2750 (`jmp rax`) で解決済み fn を呼ぶ
[PTD]  calloc(1, 0x3c8) → 0x1801c1cb8 で init (errno=0, C locale pointer, _matherr=NULL) → FlsSetValue に保存
[数学エラー]  log(0) → _handle_error(0x1801c8c00) → __math_err(0x1801c1584)
            → __control87_2(0x1801c1ae0) [stmxcsr で読むのみ] → errno 0x21/0x22 設定 (0x1801c5064)
```

### 2.2 未初期化時の fail-fast (両側同一・実測)

table 生値 0 を decode すると `ror(0 ^ 0x2b992ddfa232, 50) = 0xae64b77e88c8000` (非 0) になり
「解決済みポインタ」と誤解される。native は CFG dispatch で garbage jump → **SIGSEGV** (rip=0x1801d2750,
ret=0x1801c3e06)、wasm は `ott_dispatch(0xae64b77e88c8000)` → **`ott_unlifted` fail-fast** (ret=0x301c3e06)。
CAB-137 で「wasm も同一 fail-fast」と記録されていた現象の正体。陰性対照はこの状態を再現する (§6)。

### 2.3 (a) 実 lift でなく (b) C 等価置換とした根拠

1. **観測される初期状態の差分が小さい**: 実行経路が参照する CRT 状態は「encoded 表が enc(NULL) で
   埋まっている」「__FlsIndex が有効値」「PTD が実機械語で作られる」だけ (§3 の列挙)。いずれも
   C 数行で等価に作れる。
2. **(a) は肥大する**: `_initterm_e` の XI 表は **971 entry** (0x1801e2c20..0x1801e4a80 実測)。closure に
   stdio / locale / heap 初期化が波及し、unsup AVX (CAB-135) に触れる恐れが大きい。対して本置換で
   実行が始まった CRT 機械語は lift 集合 +51 関数に収まり、うち実行は 35 関数。
3. ** __isa_available を DLL 静的値 0 (SSE2) に保てる**: 実 DllMain 経路は `__isa_available_init`
   (cpuid/xgetbv) を通る。ホスト CPU が AVX2 の場合 CRT 数学が FMA 経路に分岐し、lift 未対応 (CAB-135)
   の VEX 命令に落ちる。(b) なら両側 SSE2 固定 = bit-exact 実績のある経路。FMA 経路は CAB-135 に引継。
4. **DllMain 実行の副次効果が不要**: GUI / TLS callback / atexit 表 / `_environ` は実行経路に現れない
   (coverage 実測: `_initterm*` / XC 初期化子 7 種 / stdio CS init は 1 つも実行されず)。

## 3. CRT 初期化で初期化される状態の列挙と DSP への影響 (要件 3)

| 状態 | 実 CRT での初期化 | 本置換での扱い (native = wasm) | DSP/表示結果への影響 (実測) |
|---|---|---|---|
| api-set 関数ポインタ表 0x18026c9f0 (34 entry) | enc(NULL) 埋め → 遅延解決 | `ott_crt_init_tables` が enc(NULL)=cookie を書く → 解決は DLL 自身の機械語 | getptd が成立し errno/locale が参照可能に。**無いと fail-fast** |
| 個別 encoded slot 0x18026c028 / c388 / cb40 / **cb88 (_matherr hook)** | 同上 | 同上。cb88 = 0 decode → **user _matherr なし** が確定 | `__math_err` が clean path (errno 設定のみ) を通る。hook あり経路は未実行 |
| `__FlsIndex` 0x1802610e4 | `__acrt_initialize_thread_local_storage` (0x1801c2194) = FlsAlloc の返値 | **1 を直接設定** (FlsAlloc 第 1 返値相当; 以降の FlsAlloc は 2 から) | 未設定だと native 実測で **formatter call 毎に 968 B PTD が漏出** (11 call → 11 個)。設定で 1 個に収束し alog が両側一致 |
| PTD (0x3c8 B, HeapAlloc) | calloc + `__acrt_...init` 0x1801c1cb8 | **実機械語のまま実行** (両側) | errno 初期 0 / **C locale (小数点 `.`)** / `_matherr=NULL`。`%f` 表示の小数点と errno 0x21/0x22 設定はここから来る |
| **MXCSR (浮動小数点制御語)** | 既定 0x1f80; `__control87_2` が保存/復元 | software shadow `ott_mxcsr` (= 0x1f80) を stmxcsr/ldmxcsr で読み書き | 実測: 実行された `__control87_2` は **stmxcsr (読み) のみ** で set (0x1801caf80) は未実行 → 丸めモード変更は発生しない (round-nearest 維持 = lift の仮定と一致) |
| `__security_cookie` 0x180260ce0 | `__security_init_cookie` で乱数化 | **乱数化しない** (静的既定 0x2b992ddfa232 のまま) | encoded 値・stack cookie が両側で決定論的に一致する効果。実機では毎プロセス変わるが観測される表示/DSP 値には現れない |
| `__isa_available` / `__use_fma3` | `__isa_available_init` (cpuid/xgetbv) | **実行しない** → 静的値 0 (SSE2) 固定 | CRT 数学が SSE2 実装を選ぶ = lift済み機械語と一致。FMA 分岐は未到達 (CAB-135) |
| locale (setlocale / XI 表) / `_environ` / stdio FILE | `_initterm_e` (971) + `_initterm` (7) | **未実行**。locale は PTD init が C locale 静的表を直接指す | 実行経路は vsnprintf (FILE なし) のみで参照せず (coverage 実測)。stdio FILE 初期化 (0x1801a0ec8) も未実行・未参照 |

## 4. 既存ファイルへの差分 (最小)

| ファイル | 差分 | 理由 |
|---|---|---|
| `lift/x64c.py` | `i_ldmxcsr` (fail-fast → `ott_mxcsr = LD32(ea)`) / `i_stmxcsr` (定数 0x1f80 store → `ST32(ea, ott_mxcsr)`) + VEX 別名 (`i_vldmxcsr`/`i_vstmxcsr`) | `__control87_2` 経路の mxcsr 読み書きを lift するため。shadow は既定 0x1f80 で DSP 経路の意味は不変 (実測: set は未実行) |
| `rt/ott_cpu.h` | `extern uint32_t ott_mxcsr;` 宣言を追加 | 同上 |
| `rt/ott_cpu.c` | `uint32_t ott_mxcsr = 0x1f80u;` 定義を追加 | 同上 (旧 build も link する共有ファイルゆえこちらに定義) |

`tools/ott/entry`・`native/`・`diff/`・`ref/` は**改変 0 行** (entry 側 runner は import して再利用)。
旧 build (`ott_e2e.sh` / `entry_e2e.sh`) は本チケットの回帰基準として無改変で併走。

## 5. override 置換表 (要件 1)

| VA | 旧 override (C 実装) | 新 | 検証状態 |
|---|---|---|---|
| 0x1801c8c00 `_handle_error(double)` | `ovr_handle_error_d` (返値 = xmm1) | **実機械語 lift** (0x1801c1584 `__math_err` まで一式) | **実行 + native bit 突合** (err_zero_svf / err_zero_pers / err_zero_disp の 3 scenario, params 全 0 → log(0)) |
| 0x1801c8cb8 `_handle_errorf(float)` | `ovr_handle_error_f` | 実機械語 lift | lift 済み・**未実行** (float 版エラー経路に到達する scenario は未構築 — §7) |
| 0x1801a9a6c `sqrt(double)` wrapper | `ovr_sqrt_d` | 実機械語 lift (x<0 → -nan(ind) 経路含む) | lift 済み・**未実行** (DSP/entry の実行 coverage に元々無し — sqrt wrapper は通常経路でも未使用) |
| 0x1801a9b38 `sqrtf` wrapper | `ovr_sqrt_f` | 実機械語 lift | 同上 |

注記: 旧 override 4 件は DSP 89 matrix (cov_all) / entry 85 (cov_entry) の**いずれでも実行実績が無かった**
(実測: coverage に関数が現れない)。よって置換が既存 matrix の結果に影響する経路は構造的に存在せず、
実際 DSP e2e (89 scenario・全 cell bit-exact・正本 `tools/ott/REPORT.md`) と 85/85 は無改変のまま維持された。
残る override は surrogate 系 8 件 (`ovr_editor_null` / `ovr_am_shim` と CRT api-set trampoline 6 件 —
後者 6 件は CRT 初期化の置換面そのもの, §2)。

## 6. 回帰と陰性対照 (実測)

| 項目 | 結果 |
|---|---|
| 新 scenario (crt build) | **9/9 PASS** (文字列 / rax / obj / alog / am counter 全一致) |
| entry 85 scenario (crt build で再実行) | **85/85 PASS** (nat_crash 0 — 旧 build では float 経路が nat_crash 対象だった) |
| DSP e2e (`ott_e2e.sh`, 旧 build) | **89 scenario / 全 cell bit-exact / max_ulp 0 / state 差 0 PASS** (正本 `tools/ott/REPORT.md`) |
| entry e2e (`entry_e2e.sh` 全 85, 旧 build) | **PASS** (matrix 85/85 突合; §9 再現コマンド) |
| 陰性対照 native | `OTT_CRTINIT=0` → **SIGSEGV st=95** (rip=0x1801d2750, rax=0xae64b77e88c8000) — 旧 fail-fast 再現 |
| 陰性対照 wasm | `OTT_CRTINIT=0` → **`ott_unlifted 0xae64b77e88c8000`** — native と同一 garbage VA / 対応 ret |
| 性能 | node 24.19, 256f×2000 block (`diff/perf.mjs`; load average 2.2〜2.8・5 回実測の範囲): crt build **217.4〜229.0 µs/blk (26.7〜25.3x)**。単発値 186.3 µs/blk (31.2x) は本検収の実測範囲の下限より低く、共有 16 コアの負荷差と snapshot の 2 関数差分に依存するため **実測レンジで記載** (規則 38)。bit-exact build のまま | (再計算: `MOD=<cjs> REPEAT=7 node tools/ott/accept/acc_perf.mjs`) |

## 7. 未解決・制約

1. `_handle_errorf` / `sqrt` wrapper 2 件は lift 済みだが実行 coverage が無い (float エラー経路・sqrt(<0)
   に至る入力が未構築)。lift fidelity の検証は他の 35 新規関数と同水準だが、**経路としては未突合**。
2. AVX/FMA unsup は lift 集合拡大で 64 種/473 箇所 → **75 種/約 560 箇所** (新規: `mov:segment` 1,
   `pshuflw` 1, `pcmpistri` 2 ほか VEX 増分)。すべて未実行経路で、実行されれば `ott_unsup` fail-fast。
   **→ CAB-135 へ引き継ぎ (§8)**。
3. `__math_err` の user `_matherr` hook あり経路 (0x1801c1460 → 0x1801ce384 の hook 呼出) は hook=NULL
   のため未実行。OTT が `_matherr` を定義している場合の挙動は未検証 (DLL 内に user 定義は見つかっていない)。
4. FlsAlloc の thread-detach callback (0x1801c1d88) は登録のみで未呼出 (単 thread / FlsFree なし)。
5. `GetSystemTimePreciseAsFileTime` は決定論固定 (0) — 時刻参照経路が実行された場合の native 実時刻との
   差は未検証 (現 coverage では未実行)。

## 8. CAB-135 (AVX/FMA unsup 72種) への引き継ぎ

- **unsup 現状**: 75 種 / 約 560 箇所 (crt build lift 集合 258 関数時点)。内訳は AVX/VEX 系が大半 +
  `rcr` 6 (0x1801bc890) + `int` 3 (fail-fast 経路) + `pcmpistri` 2。
- **mxcsr は本チケットで解消済み**: stmxcsr/ldmxcsr (VEX 含む) は software shadow で lift 可能になった。
  0x1801bc890 (vldmxcsr/vstmxcsr/rcr を含む FP 制御切替の大きい関数) 自体は依然未実行。
- **`__isa_available` の方針決定が必要**: 本チケットは「DLL 静的値 0 = SSE2 固定」で固定した。
  FMA 経路を lift する場合は (1) `__isa_available_init` の lift (cpuid/xgetbv 相当を C で inject) か
  (2) harness からの強制書き換え (既存資産 `diff/fma_sens.py` が 0x18026c50c を書く仕組み) で
  native/wasm を同時切替すること。SSE2↔FMA の出力差は実測 0 ulp (12 case / 18,432 cell) ゆえ、
  切替しても bit-exact 判定は維持される見込み (全入力域の保証ではない)。
- CRT 深い経路 (0x1801bc890 等) に VEX が出現する位置は特定済み — CAB-138 の coverage JSON
  (`work/crtlift/cov_crt.json`) と `lift_meta.json` の unsup 集計を起点に使える。

## 9. 再現

```sh
# 前提: ANALYSIS_DIR に analysis-ott-binaries を展開 (plugins/ott/binaries/OTT_vst2_win64.dll)
bash tools/ott/native/build.sh                    # 先に libottnative.so を作り直す (古い work/ の .so は ott_enc_slots を持たず [1/6] が落ちる)
bash tools/ott/crtinit/crt_e2e.sh                 # 全工程 (§10 実測: 2 分 49 秒)
CRT_COV_SKIP=1 CRT_LIFT_SKIP=1 bash tools/ott/crtinit/crt_e2e.sh   # 再利用
OTT_CRTINIT=0 python3 tools/ott/crtinit/crt_nat.py --out /tmp/n.json --scen tools/ott/work/crtlift/scen_crt.json --only flt_disp_def   # 陰性対照 (native)
OTT_CRTINIT=0 MOD=$PWD/tools/ott/work/crtlift/ottl_crt.cjs SCEN=$PWD/tools/ott/work/crtlift/scen_crt.json NAME=flt_disp_def OUT=/tmp/w.json node tools/ott/crtinit/crt_wasm.mjs  # 陰性対照 (wasm)
bash tools/ott/ott_e2e.sh                          # DSP 89 scenario (旧 build, 無改変)
bash tools/ott/entry/entry_e2e.sh --quick          # entry 85 (旧 build, 無改変)
# 前提: tools/ott/ott_e2e.sh が PASS する環境 (python3 capstone/pefile, gcc, emsdk 6.0.12, node ≥22)
```

## 10. ICALL-76 訂正: api-set 表は 34 entry (APISET_N 32 → 34)

- **根拠**: CRT 初期化 0x1801c43a4 の `rep stosq` 個数 (`and ecx, 0x22`) = 34。表は 0x18026c9f0〜0x18026cb00 (0x110 B)。
  `python3 tools/icall/diff/dispatcher_ids.py <OTT_vst2_win64.dll> 0x1801c38c8 0x18026c950 0x18026c9f0 0x18021e500` の
  T2 function_id 即値の最大は 29 (call site 30 件・distinct 21)。
- **修正**: `ott_crt.c` と `crt_native.c` の `APISET_N` を 34 に。native 基準側も同じ 32 だったため両方直した (片側だけだと両側の初期状態が食い違う)。
- **index 32・33 は実行されない (直接確認)**: 解決 (§2.1) は解決時に表 entry へ encode 値を書き戻す。よって実行された entry は初期値 enc(NULL)=cookie から変わる。修正後 build (`7eaf9d46`) で scenario を 1 本ずつ実行し、各実行後に guest メモリの表 0..33 を読んだ (読み出しは `crt_wasm.mjs` に末尾で足した作業用コピーで、コミットしていない)。
  - 実行: crt 新 9 本 + `entrylift/scen.json` 86 本 = **95 run・全 run 成功** (scen.json は name 重複が 1 件あり、一意な scenario は 85 件 = matrix85 と同数)。
  - 結果: 初期値から変わった index は **{5, 6} のみ** (§2.1 の FlsGetValue / FlsSetValue wrapper に対応し、dispatcher 静的解析の call site id 5・6 と一致)。**32・33 は 95/95 で cookie のまま = いずれの scenario でも解決されていない。**
  - 補助 (静的): call site が渡す function id の最大は 29 (32・33 を渡す直接 call は無い)。
  - 修正前の帰結: 修正前は両側とも 32・33 が生値 0 だった。生値 0 は decode すると 0xae64b77e88c8000 (非 0) になり、解決済みとして CFG dispatch され fail-fast する (§2.2)。修正前の 94 scenario が全 PASS だったことも、32・33 の未 decode と整合する。
  - 限界: 観測は上記 95 scenario の範囲。将来 32・33 を解決する経路が実行されれば、表への書き戻しとして同じ方法で検知できる。
- **初回 run の FAIL (環境起因)**: `tools/ott/work/` の snapshot にあった `libottnative.so` は古く `ott_enc_slots` を持たない。[1/6] が落ちて native 側が古い coverage のまま動き、94 件が FAIL した。`bash tools/ott/native/build.sh` で作り直すと PASS (§9)。
- **測定** (`crt_e2e.sh` 全工程):

| 項目 | 修正前 `54bacdc0` | 修正後 `7eaf9d46` (測定 commit) |
|---|---|---|
| `crt_e2e.sh` 総合 | PASS (2 分 55 秒, 14:36:55〜14:39:50) | PASS (2 分 49 秒, 14:41:53〜14:44:42) |
| 新 scenario 9 本 | PASS 9 / FAIL 0 | PASS 9 / FAIL 0 |
| 既存 entry 85 再突合 | PASS 85 / FAIL 0 | PASS 85 / FAIL 0 |
| 陰性対照 native SIGSEGV / wasm ott_unlifted | OK / OK | OK / OK |
| `ott_e2e.sh` (DSP) / `entry_e2e.sh --quick` | PASS / PASS | PASS / PASS |
| lift 集合 (x64c) | 260 関数 / 16,378 命令 | 260 関数 / 16,378 命令 |

- load average (1 分): 修正後 run は開始 0.24 / 終了 1.44 (4 コア)。修正前 run は未採取。
- **測定 commit から HEAD までのコード差分**: `git diff 7eaf9d46 HEAD -- tools/ott/crtinit/*.c tools/ott/crtinit/*.py tools/ott/crtinit/*.sh tools/ott/crtinit/*.mjs` は 0 行 (測定後にコードは変えていない。以降の変更は本 REPORT のみ)。
- **未解決 (本 PR 外)**: `tools/ott/accept/acc_crt_table.py` の `N = 32` (検収用の読み取りスクリプト) と `tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 は PM 判断のため未修正。
