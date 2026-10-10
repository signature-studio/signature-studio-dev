# lift2 REPORT — CAB-48 (FA-2) + FA-2c Fresh Air Compressor / Filter / 制御層 lift

- 日付: 2026-10-10 / 前担当セッション (ses_edb7a86fbffeejSNjIJr4iKuNf) の残骸 (lift2/, コミット 0 件) を引継ぎ・再開
- 再現: **`bash tools/targets/freshair/lift2/lift2_e2e.sh`** (1 コマンド, 約 25 秒 — lift→emcc→wasm→native oracle 比較→fuzz→ABI→ablation 直列)
- 正本: `SlateCore.core_64` (Win x64, 36.3MB) の実機機械語を ImageBase 0x180000000 に MAP_FIXED 敷設し ms_abi で直接実行
  (IAT スロットは shim C 実装に差替え)。lift 側 (wasm) と非循環。

## 0. 方針決定: 残骸の mlift + IAT patch 方式 vs liftlib 標準ハーネス

残骸評価の結果, **mlift (機械語駆動自作リフタ) + IAT patch 方式を採用**した。根拠:

| 観点 | liftlib 標準ハーネス | mlift (残骸→修正) |
|---|---|---|
| RetDec 依存 | RetDec → 修復 pass (P1/F7/F2) が必要 | **不使用** (capstone で機械語 1 命令ずつ直接 IR 化) |
| SSE スカラ脱落 (P1/F7/F2 類型) | 修復 pass で対処 | **構造的に発生しない** (全 GPR/XMM を一律保存する uniform signature) |
| IAT 呼出を含む関数 | **native 実行不可 (既知限界)** — Compressor は `std::vector` grow (0x1803ded20) 経由で HeapAlloc/HeapFree を IAT call するため対象外になる | **native も wasm も実行可** (native: IAT スロットを shim C 実装へ差替え / wasm: `win_kernel32_*` 外部関数) |
| FA-2 の対象関数 | 選定で回避する必要 (grow を stub 化 → bit-exact の減点) | そのまま lift 可 |
| 実績 | FA Gain 400/400 (CAB-49/54/55) | **Compressor/Filter を本セッションで bit-exact 化 (下表)** |

Compressor の closure は grow (HeapAlloc/HeapFree) を含み, liftlib 制約「IAT 呼出なし」に抵触するため,
liftlib ハーネスでは native oracle が構成できない。逆に mlift の欠点 (RetDec 欠陥類型の検出器が無い) は,
ablation による故障注入で「どの意味論が必須か」を実測して補完した (§6)。liftlib 自体は無改変 (読取のみ)。

## 1. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| Filter process (0x180b6f050, closure 114 関数 / 42,532B) | **bit-exact 400/400** (200 シナリオ × fma0/1, native 実機機械語 vs wasm) |
| Compressor process (0x180775220, closure 49 関数 / 11,291B) | **非 grow 経路 bit-exact 206/206** + grow 経路 122/194 (72 scenario-call で wasm OOB, §5) |
| ctx-fuzz | **4800 比較すべて bit-exact** (構造化 200 + 乱数 1000 試行) × {comp, filter} × {fma0, fma1}, canary 違反 0 |
| ABI 検査 | 静的 (push/pop 対応, closure 54+58 関数) **0 違反** / 実行時 (asm capture/verify, callee-saved GPR 8 本) **0 違反** / canary (メモリ閉込) **0 違反** |
| wasm サイズ | comp 2.43MB / filter 2.98MB (emcc -O1, ALLOW_MEMORY_GROWTH) |
| mlift 修復 | 残骸に **3 根源欠陥**を特定・修復 (§3)。修復前は Filter 100/100 不一致 → 修復後 0/100 |

## 2. 残骸の状態 (引継ぎ時)

- `lift2/` 丸ごと未追跡。Compressor は mlift で lift 済み (fma0/1 800/800 bit-exact の成果物あり), **Filter は lift 済みだが 100/100 不一致 (全シナリオで wasm が NaN)** で停止していた。
- 前担当の最終 reasoning: 「native_comp.c で IAT を VA マップでパッチ … Win32 host 関数を libc 等価で実装する ms_abi shim を設計中」— 設計は実装済みで動作していた。
- lift2 内のツール: mlift (955 行 machine-code lifter), native_* (PE 敷設 oracle), gen_*_scen (シナリオ生成), ablate_comp (故障注入)。

## 3. mlift の根源欠陥 3 件と修復 (本セッションの主要成果)

残骸の mlift は「関数ごとに独立した alloca フレームを rsp に据える」設計で, 以下が顕在化:

| # | 欠陥 | 症状 | 修復 |
|---|---|---|---|
| **D-A** | **callee の rsp が caller のスタック引数を見えない**: 関数ごとに独立 alloca。Filter の係数設計 `0x180b7fa80` が callee 側 `[rsp+0xf0..]` で Q/gain/sr を読む → 未初期化 (ほぼ 0) を読む → div-by-zero → NaN カスケード | Filter 100/100 不一致 | **共有マシンスタック `@fa_stack` (1MB)** を導入し, call で caller の rsp を引数渡し (callee 入口で -8 = retaddr push を再現)。caller のスタック引数 `[rsp+0x20..]` が callee から見える |
| **D-B** | **callee 入口の rax を 0 初期化**し after_call で caller の rax を上書き: `__security_check_cookie` (0x18100c1e0, void) 越しに戻り値 (stage 数) が消滅 | 多段係数設計 `0x180d235b0` が ret=0 を返す (native は 1..10) | callee 入口 rax = caller の rax を引数渡し (実機: void call でも caller の rax は温存される) |
| **D-C** | **戻り構造体が {rax, xmm0} のみ**: `0x18105d170` (tan の多項式カーネル) が struct{double,double} を xmm0+xmm1 で返す — caller は xmm1 を読む → caller の旧値 (0) のまま | tan fma=1 で 12/34 入力が ±1ULP | 戻り構造体を {rax, xmm0, xmm1} に拡張し after_call で両者を伝搬 |

追加修復: wrapper (fa_root_*) の引数割付を **MS x64 の positional 規則**に修正 (int→GPR[k], float→XMM[k], 5 番目以降→スタック)。
実機検証: `probe235` (42/42), `probe7fa80` (48/48), `trigprobe` (tan/log fma0/1 全入力 bit-exact) で各関数単位に確認。
fma primitive 自体は emcc libm 実装が native vfmadd と **200,000/200,000 入力で bit 一致** (work/fmatest) を確認。

## 4. bit-exact 実測

| 対象 | 経路 | シナリオ | fma0 | fma1 |
|---|---|---|---|---|
| Filter process 0x180b6f050 | 型 0-7 × order 0-5 × 周波数/Q/gain × n=1..64 × 1-5 call (crossfade 状態遷移含む) | 200 | **200/200** | **200/200** |
| Compressor process 0x180775220 | 型/周波数/mode/sidechain/vector push (vcap 0-64: grow 含む) × n=0..128 | 400 | 非grow 206/206, grow 122/194 | 同左 |
| ctx-fuzz (comp) | 構造化 200 + 乱数 1000 (境界値: ±0, 非正規, 巨大/極小, n=1..128, 複数 call) | 1200 | **1200/1200** | **1200/1200** |
| ctx-fuzz (filter) | 同上 (n=1..64) | 1200 | **1200/1200** | **1200/1200** |

- 比較対象: 状態ブロック (S+0x98.., P+0x9f70.., vector begin/end/cap 相対値) + L/R 出力の全バイト。
- NaN/Inf 入力は除外 (x86 と wasm の NaN payload 差 — liftlib と同一の方針)。
- grow 経路 (vcap<16) の 72 fails は §5 の既知限界。

## 5. 既知限界: Compressor grow 経路の wasm OOB (72 scenario-call)

`vcap < 16` のシナリオで vector が grow し, lift 済み grow 呼出鎖 (0x1803ded20 → 0x1803de3e0 → CRT heap lock 0x18106632c の `lock inc [rcx+0x10]`) で wasm OOB ("memory access out of bounds")。native 側は正常。对应的処置:

- grow + アロケータ (0x1803ded20/0x1803de3e0) を C 等価 (`fa_vector_grow`: 1.5 倍ポリシ, 4B 要素, 3 部 copy, 旧 buffer free) に差替え (`--map`)。 stmxcsr/ldmxcsr も `fa_mxcsr_get/set` に差替え。
- 残る OOB は **shared_ptr 制御ブロック代入 (0x181057d20 → 0x18106632c `lock inc`) の CRT 状態依存**: harness が与える最小オブジェクトでは CRT lock 制御ブロックが未初期化。対処には UCRT 起動時状態の追加 poke (0x1813073xx 領域) または shared_ptr 代入の C 差替えが必要 → 次タスク。
- 非 grow 経路 (206/206) と grow 単独 (122/194) は分離集計 (`run_comp.sh` が split 表示)。

## 6. ablation (mlift 意味論の故障注入 → 実測)

`ablate_comp.sh` — mlift の意味論から 1 つずつ欠落させ, native との不一致シナリオ数を実測 (200 scenarios, fma0):

| inject | 不一致 | 意味 |
|---|---|---|
| comis_noflags | 200/200 | comisd 後の分岐再構成が必須 (RetDec P1 類型の対応物) |
| xmm_args_drop | 200/200 | callee 入口 xmm0-3 の保存が必須 (RetDec F2 類型) |
| xmm_ret_drop | 200/200 | xmm0 戻り伝搬が必須 |
| icall_drop | 104/200 | 間接 call の VA switch が必須 (host vtable `0x7F000001`) |
| cmov_drop | 172/200 | cmov の select 化が必須 |

すべての意味論が load-bearing であることを機械的に実証。RetDec を使う場合も同類型の修復 pass が必須であることを示す。

## 7. 成果物

```
lift2/
├── lift2_e2e.sh          1 コマンド検収 (build → bit-exact → fuzz → ABI → ablation → 制御層)
├── mlift/{mlift,mlift_ops,pe_image}.py   機械語駆動リフタ (D-A/D-B/D-C + E-1..E-5 修復)
├── native/{native_comp,native_filter,native_ctrl}.c   実機機械語 oracle (PE 敷設 + IAT shim + canary)
├── native/{comp,filter,ctrl}_harness.mjs  wasm 側 harness (canary 付き, 同一契約)
├── native/{probe235,probe7fa80,trigprobe,tracefn,entry_probe}.c  関数単位 probe / VST 入口観測点
├── native/abi_check.c                    実行時 ABI 検査 (asm capture/verify)
├── build_{comp,filter,ctrl}.sh           lift + emcc (ctrl は 2 段 lift + icall_extra 自動 seed)
├── run_{comp,filter,ctrl,fuzz}.sh        各検証の driver (ctrl は ctrl_norm.py で厳密判定)
├── gen_{comp,filter,ctrl}_scen.py        シナリオ生成 (ctrl: 先頭 8 本 = factory .epf)
├── icall_extra.py / ctrl_norm.py / gen_win_stubs.py   icall seed 自動列挙 / 厳密判定 / import 既定実装
├── abi_static_check.py                   静的 ABI 検査 (push/pop 対応, closure 全関数)
├── shim/{host_wasm,fa_win_shim,am_host}.{h,c}   wasm/native 共通 shim (fa_heap_zero / audioMaster 応答表)
└── ablate_comp.sh                        故障注入 (ablation)
```

## 8. 未解決 / 次タスク

1. **Compressor grow 経路の wasm OOB 完走 (72/800)**: UCRT lock 制御ブロックの追加 poke または shared_ptr 代入 (0x181057d20) の C 差替え。非 grow は bit-exact 済みなので残差は限定。
2. **FreshAirDsp 制御層 (0x1803dfc10, vtable 17 slot)**: 子 snapin 呼出は本セッションの Compressor/Filter process で部品が揃った。vtable 経由の間接 call を fa_icall switch に追加する形で lift 可能。
3. **mlift の汎用化起票案 (liftlib 側への反映は REPORT 起票のみ)**: (a) 共有スタック + rsp 引数渡し, (b) callee 入口 rax = caller rax, (c) 戻り {rax, xmm0, xmm1}, (d) wrapper の positional 引数割付 — いずれも RetDec 経路 (tools/liftlib) の修復 pass にも適用可能な知見。
4. **Determinism**: wasm 2 回実行の SHA 一致は fma0/fma1 の 2 pass で暗黙確認 (同一シナリオ再実行)。明示の 3rd pass は未実施。

## 9. 検収記録

- `lift2_e2e.sh` exit=0 (ALL PASS) — /tmp/opencode/e2e_final4.log
- 全数値は実測 (上記コマンドで再現可能)。推定値は含まない。

## 10. FA-2b 追記: Compressor grow 経路完走 (CAB-257, commit 本節参照)

**結論: grow (vcap<16) を含む Compressor 全 scenario が bit-exact 400/400 (fma0/fma1)。wasm ERR 72 → 0。**
§5 の「UCRT lock 状態 / shared_ptr 制御ブロック」仮説は不成立 — 真の根因は harness 側で, poke も shared_ptr 差替えも不要だった。

### 10.1 根因 (実測で特定)

1. **harness (comp_harness.mjs) の vbuf 規約違反**: vbuf を canary 付き `al()` (内部ポインタ base+64) で取得していた。
   grow は machine 側が旧 buffer を `HeapFree` (shim: `free`) するため, `free(begin)` に**内部ポインタ**が渡り,
   dlmalloc が chunk header (canary 0xa5a5a5a5 を size と誤読) から遠方アドレスへ書込み → wasm OOB。
   stack trace `wasm-function[51]=free ← [37]=fa_vector_grow ← [2]=process` で特定。
   native (native_comp.c) は当初から vbuf を plain calloc (先頭ポインタ, canary 検査外) にしており**規約が不一致**だった。
2. **C 差替え fa_vector_grow 自体の容量計算バグ** (潜在的): `vec+16` は cap END **ポインタ**なのに, その値を
   容量 (float 数) と混同し `newcap = ptr + ptr/2` を計算。実機 0x1803ded6c..ded8f は `(cap_end-begin)>>2` を容量に 1.5 倍
   (`mov rcx,[rcx+0x10]; sub rcx,rdx; sar rcx,2` → `lea rbx,[rdx+rcx]`)。free クラッシュが先に起きるため未顕在化だった。
   → C「等価」差替えは意味論を正確に写像しないと新たな破れを生む (教訓として shim に記載, 関数は削除)。
3. **§5 仮説の不立証**: UCRT lock 状態 (0x1813073xx) の追加 poke なし, 0x181057d20 (shared_ptr 代入) の差替えなしで完走。
   0x181057d20 は closure に静的に含まれる (0x18103fd60 経由) が, 本 scenario 群の実行経路には現れず
   (全 comp 1,200 scenario + fuzz 2,400 比較で trap 0)。

### 10.2 修正方式

| 変更 | 内容 |
|---|---|
| `native/comp_harness.mjs` | vbuf を native と同一規約へ (plain malloc + zero 初期化)。GUARD 集計からも除外 (native の `+ 0` と同一) |
| `build_comp.sh` | `--map 0x1803ded20=fa_vector_grow` を**廃止** — machine grow 鎖 (0x1803ded20 → 0x1803de100 → 0x1803de3e0 → operator new/delete → HeapAlloc/HeapFree shim) を lift 済みコードのまま実行 |
| `shim/host_wasm.c` | fa_vector_grow (C 等価実装) を削除 (上述の欠陥 + machine lift で不要). fa_mxcsr_get/set は 0x18103fd60 系で使用中ゆえ維持 |
| `run_comp.sh` | 合否判定を grow 込み 400/400 に強化 (旧: non-grow のみ exit 判定) |

### 10.3 検証結果 (全て実測)

- `lift2_e2e.sh` **exit=0 ALL PASS** (/tmp/opencode/e2e_fa2b_final.log, 最終コード状態で再実行済): comp **400/400** (non-grow 206 + grow 194) × fma0/1, ERR 0
- **別 seed での汎化**: seed 0x1234 → 400/400 (grow 196/196), seed 0xBEEF → 400/400 (grow 201/201) — 計 3 seed × 400 × fma0/1
- 回帰不変: Filter **400/400**, ctx-fuzz **4,800 全 bit-exact** (GUARD 0), ABI 静的 **0 違反** / 実行時 **violations=0**
- ablation の純化: 旧数値は grow OOB 由来の偽 ERR (39 scenario) を含んだ。純化後: comis_noflags 200/200, xmm_args_drop 200/200,
  xmm_ret_drop 200/200, **icall_drop 80/200** (§6 の 104 から変化 — 旧値は ERR 混入を含む), cmov_drop 172/200。意味論が load-bearing という結論は不変
- ablation 構成 (grow を map せず lift したまま) で trap 0 — **machine grow 自体が wasm で bit-exact 動作**することの裏取り

### 10.4 残限界

- `run_fuzz.sh` (gen_fuzz_scen.py) は vcap=64 固定で grow 経路を直接 cover しない (grow 網羅は run_comp.sh の vcap<16 460 scenario / 3 seed が担う)。
- 0x181057d20 (shared_ptr 代入) 経路は本 closure の scenario では未発火。FreshAirDsp 制御層 (§8-2) 拡張時に CRT/lock 状態が表に出る可能性は残る (その際は §5 の poke 案が再燃する)。
- malloc/free は emcc dlmalloc (wasm) と glibc (native) の差があるが, 比較は相対値 (end-begin/cap-begin) + 内容のみでアドレス値非依存。

## 11. FA-2c 追記: FreshAirDsp 制御層 lift + factory .epf 8 本駆動検証 (CAB-260, commit 9b420bd)

**結論: 制御層 (0x1803dfc10, vtable 17 slot) は lift 完走し、factory .epf 8 本 + 小規模 structured で
native 実機機械語と wasm (mlift) が bit-exact 一致 (`bash lift2_e2e.sh` = ALL PASS)。**
Compressor 400/400 (grow 込)・Filter 400/400・ctx-fuzz 4,800 は不変。closure は 305 関数 / 228,582 B / 44,208 命令。

### 11.1 残骸の評価 (引継ぎ時)

- Compressor/Filter (FA-2/2b) はコミット済みで検収可能。制御層は vtable 17 slot の lift + ctrl harness が
  **途中まで**あったが、native は `__chkstk` の gs read (Linux は gs_base=0) で必ずクラッシュ、wasm は
  未解決 icall (`jmp rax` CFG stub) で trap —— **両側とも完走していなかった**。
  旧 `run_ctrl.sh` は「片側クラッシュ → 双方 0 byte → mismatch 0 → 空 PASS」する脆弱性を持ち、
  実際に成果物 0 byte が PASS と判定される状態だった。

### 11.2 修正した 5 件の根本欠陥 (すべて実測で特定・修正)

| # | 欠陥 | 症状 | 修正 |
|---|---|---|---|
| E-1 | `__chkstk` の gs read (`mov r11, gs:[0x10]`) が Linux で SIGSEGV (gs_base=0) | native が ctor 入口で必ず停止 | `xor r11,r11` + nop に差替え (StackLimit=0 → probe skip)。wasm の @fa_teb=0 と同値 |
| E-2 | FreshAirDspModel ctor (0x1803ba840) の arg2 (rdx) は**非 NULL 必須** (`[arg2+4]` を M+0xa088 に写す)。前担当は 0 を渡し SIGSEGV | native が ctor 途中で停止 | 両側で同一の 0 初期化 32B ダミーを渡す |
| E-3 | `h_rep_stos` が**初期 rcx を毎回読み直さない** | model ctor 内 `rep stosb` が rcx0>1 で無限ループ → wasm OOB | ループ頭で `%R_rcx` をロード (ループ持ち回し変数化) |
| E-4 | `fa_icall` switch が icall_targets のみ解決 | vtable slot / 引数受け回しの関数ポインタが host trap | **lift 済み全関数**に拡大 + CFG stub (`jmp rax`) の rax0 再ディスパッチ。未 seed は `icall_extra.py` が自動列挙 (closure 内 lea 参照 + 制御層領域 RVA 0x3d0000..0x3f0000) |
| E-5 | 共有マシンスタック @fa_stack 1MB 不足 (深い入れ子 + 0x5cc0 フレーム) | guard violation 25,344 (stack 溢出) | 8MB (host stack と同値) に |

補助: `fa_heap_zero` (未初期化 heap の環境依存残留値ダンプ差分を除去)、`ctrl_norm.py` (ポインタ値マスク +
行数/ERR 一致の厳密判定)、`gen_win_stubs.py` (PE import 表の weak 既定実装)。

### 11.3 検証結果 (すべて実測・exit 0)

| 対象 | シナリオ | 結果 |
|---|---|---|
| **制御層 (FA-2c)** | factory .epf 8 本 (Clap Lifter / Hat Lifter / Mixbus Polish / Mixbus Sparkle / Presence Pop / Shiny / Vocal Air / Vocal Bus Presence) + structured 2 + random 5 × fma0/1 | **15/15 bit-exact** (1 scenario は native/wasm **同一の** ERR — 実機側でも同じ fail-fast) |
| Compressor (不変) | 400 × fma0/1 (non-grow 206 + grow 194) | **400/400** |
| Filter (不変) | 200 × fma0/1 | **400/400** |
| ctx-fuzz | 2,400 × 2 target × 2 fma | **4,800/4,800** |
| ABI / canary | 静的 + 実行時 + メモリ閉込 | **0 違反 / 0** |
| ablation | 5 類型 | load-bearing (icall_drop 80/200) |

### 11.4 検証の到達範囲 (境界の明記)

- 成功: .epf 8 本 → 制御層 slot[12] → 子 snapin リスト走査 → `0x180c9d700(child,id,value)` マクロ設定 →
  各子 `0x180ca0d50(child, ctx)` → 子 DSP process の全経路が native とバイト一致
  (macro 値・子 DSP state・L/R 出力・vector grow 相対値)。
- 既知限界: structured/random の**大規模**シナリオ (200+1000) は、シナリオ生成が `W+0x70` (カウント)・
  `P+0x9e54` (型 enum)・`C+0x5e8` (種別) など**意味フィールドへランダム値を注入**するため、
  **実機機械語側でも OOB 書込が起きる** (native も `malloc(): corrupted top size` / SIGSEGV で停止
  = lift の問題ではない)。検収範囲は epf 8 本 + 小規模 structured (既定 `run_ctrl.sh 2 5`) とした。

### 11.5 未解決 / 次タスク (FA-4 / CAB-50 への引き継ぎ)

1. シナリオ生成の値域を plugin 仕様 (型 enum / カウント / 種別) に丸めれば structured/random も完走可能。
2. VST2 エントリ群: AEffect wrapper ctor (0x180dace80) は native で作動確認済 (magic 'VstP' / thunk 群
   (0x180dac610 dispatcher, 0x180dace60 setParameter, 0x180dacbd0 getParameter, 0x180dacda0
   processReplacing, 0x180dacd80 processDoubleReplacing) / numPrograms=1 / numParams=3 / numInputs=1 /
   numOutputs=2 / flags=0x10 / ioRatio=1.0 / uniqueID=0x4e6f4566 / version=1)。framework 経路
   (`VSTPluginMain_FrAr` → 0x180c7d400 → 0x180c7c030) は locale/TLS 依存が深く native oracle
   未成立 — host 呼出 (audioMaster) の差替えが次タスク (`entry_probe.c` を観測点として残置)。
3. GUI/エディタ層は対象外 (CAB-52 と同方針)。
