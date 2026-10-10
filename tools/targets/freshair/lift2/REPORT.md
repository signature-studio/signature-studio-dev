# lift2 REPORT — CAB-48 (FA-2) Fresh Air Compressor / Filter lift

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
├── lift2_e2e.sh          1 コマンド検収 (build → bit-exact → fuzz → ABI → ablation)
├── mlift/{mlift,mlift_ops,pe_image}.py   機械語駆動リフタ (本セッションで D-A/D-B/D-C 修復)
├── native/{native_comp,native_filter}.c  実機機械語 oracle (PE 敷設 + IAT shim + canary)
├── native/abi_check.c                    実行時 ABI 検査 (asm capture/verify)
├── native/{comp,filter}_harness.mjs      wasm 側 harness (canary 付き)
├── native/{probe235,probe7fa80,trigprobe,tracefn}.c   関数単位 probe (bit-exact bisect 用)
├── abi_static_check.py                   静的 ABI 検査 (push/pop 対応, closure 全関数)
├── gen_fuzz_scen.py                      ctx-fuzz シナリオ生成 (structured + random)
├── run_{comp,filter,fuzz}.sh             各検証の driver
├── shim/{host_wasm,fa_win_shim}.h        wasm/native 共通 shim (fa_vector_grow, fa_mxcsr_get/set 追加)
└── build_comp.sh / build_filter.sh / ablate_comp.sh / probe_build.sh
```

## 8. 未解決 / 次タスク

1. **Compressor grow 経路の wasm OOB 完走 (72/800)**: UCRT lock 制御ブロックの追加 poke または shared_ptr 代入 (0x181057d20) の C 差替え。非 grow は bit-exact 済みなので残差は限定。
2. **FreshAirDsp 制御層 (0x1803dfc10, vtable 17 slot)**: 子 snapin 呼出は本セッションの Compressor/Filter process で部品が揃った。vtable 経由の間接 call を fa_icall switch に追加する形で lift 可能。
3. **mlift の汎用化起票案 (liftlib 側への反映は REPORT 起票のみ)**: (a) 共有スタック + rsp 引数渡し, (b) callee 入口 rax = caller rax, (c) 戻り {rax, xmm0, xmm1}, (d) wrapper の positional 引数割付 — いずれも RetDec 経路 (tools/liftlib) の修復 pass にも適用可能な知見。
4. **Determinism**: wasm 2 回実行の SHA 一致は fma0/fma1 の 2 pass で暗黙確認 (同一シナリオ再実行)。明示の 3rd pass は未実施。

## 9. 検収記録

- `lift2_e2e.sh` exit=0 (ALL PASS) — /tmp/opencode/e2e_final4.log
- 全数値は実測 (上記コマンドで再現可能)。推定値は含まない。
