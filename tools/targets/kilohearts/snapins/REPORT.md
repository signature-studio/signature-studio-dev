# Kilohearts snap-in 9 本目までの lift (CAB-53 完走 + CAB-224 / CAB-225) + KH-2b / KH-1c (§9, §10)

- 解析日: 2026-10-10 / 担当 dir: `tools/targets/kilohearts/snapins/` (大物は `work/`, gitignore)
- 1 コマンド再現: `bash tools/targets/kilohearts/snapins/run_all.sh` (10 本 + libm 単体 qemath/qebig。キャッシュ有り 1〜2 分 / 初回 + RetDec 約 3 分)
- 本報は CAB-224 (Resonator / Stereo = 許容誤差判定) と CAB-225 (Disperser = bit-exact) の追試。既存 6 本の詳細 (§2〜§5 旧版) は前版 (git log 9e65bb7) を参照。

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| CAB-225 (Disperser) | **bit-exact 200/200 trial・999/999 call (seed 1) + 1000/1000 trial・4999/4999 call (seed 7)**。7 段 biquad オールパス + 段数ランプ crossfade + jumptable (biquad type switch) + memmove shim 込み。wasm 188,379 B / undefined import 0 |
| CAB-224 (Resonator) | **許容誤差判定 200/200・999/999 + 1000/1000・4999/4999 (exceed 0)**。liftlib gate (相対誤差 ≤ 1.6·2⁻¹², `tools/liftlib/liftlib/simd/simdtest.py` と同一式) を state 領域に厳格適用 (200+1000 trial で 1 回も超過せず、観測差は 1〜2 ulp = ~1e-7 相対)。音声経路は gate + 絶対誤差フロア 1e-3 (§3 の構造的増幅の実測根拠付き)。wasm 65,787 B |
| CAB-224 (Stereo) | **許容誤差判定 200/200・999/999 + 1000/1000・4999/4999 (exceed 0)**。rsqrtps + Newton 1 段 → 音声経路最大相対誤差 1.5e-4 / state は bit-exact 水準。wasm 97,316 B |
| 判定基準の位置づけ | native oracle = **実機 CPU (AMD Ryzen 9 9950X)** の rcpps/rsqrtps 近似表。wasm 側は IEEE の 1/x・1/√x (仕様内) → 差は CPU 依存で、**bit-exact の定義自体が CPU 依存** (他 CPU 上の本物とは一致しない)。再現時は本 REPORT の gate 式と floor 値をそのまま使える |
| 新規 lift 欠陥 | **D14**: `sincos_a` の Payne-Hanek 経路 (\|x\| ≥ 5e5) が O(1) 誤差 (`k_dfdb0` = 128bit mul/adc/bsr/可変 shift 連鎖)。**\|x\| < 5e5 は bit-exact 480/480** (`DEFECTS.md`) |
| 既存 6 本 | **無変更で維持** (run_all.sh 全緑: matrix/gain/haas/clipper/gate/quickeq 200/200 bit-exact + Path A 対照 + qemath 4800/4800) |
| 未達 | Resonator の高Q体制 (利得 →1) での許容誤差拡大は構造的 (§3)。sincos 大角度経路は未修復 (§6)。両方とも下流チケット案 |

## 1. 全 9 本の一覧表 (実測, Path B, 200 trial seed 1 — 上 6 行 = 前版から無変更で維持)

| snap-in (id) | process VA | process B | lift fn数 / 合計B | wasm B | undefined import | trial | call | 判定 | 必要な修復 (発火数) | shim / 未lift stub |
|---|---|--:|--:|--:|--:|--:|--:|---|---|---|
| Channel Mixer (kscm) | 0x1804f41a0 | 257 | 3 / 275 | 23206 | 0 | 200/200 | 1149/1149 | bit-exact | mov128×3, flags×1, merge×2 | 0 / 0 |
| Gain (ksgn) | 0x1804b0380 | 609 | 1 / 609 | 23054 | 0 | 200/200 | 999/999 | bit-exact | merge×2, flags×1, store128×1, callret×2 | 0 / 1 |
| Haas (ksha) | 0x1804d0280 | 1175 | 5 / 1606 | 35967 | 0 | 200/200 | 1100/1100 | bit-exact | store128×4, merge×5, flags×5, storelow×1 | 0 / 0 |
| Clipper (kclp) | 0x180884b30 | 1683 | 3 / 1743 | 37457 | 0 | 200/200 | 1100/1100 | bit-exact | mov128×10, merge×8, flags×10, store128×4, callret×1 | 0 / 0 |
| Gate (ksgt) | 0x1804c2f50 | 1703 | 3 / 2532 | 45754 | 0 | 200/200 | 999/999 | bit-exact | callret×12, mov128×11, flags×9, merge×2, store128×1 | 2 / 1 |
| 3-Band EQ (ksqe) | 0x18035fb10 | 1754 | 24 / 11512 | 186285 | 0 | 200/200 | 999/999 | bit-exact | mov128×43, flags×30, merge×13, store128×11, callret×49, jumptable×1 | 2 / 6 |
| Resonator (ksre) | 0x180743390 | 2020 | 7 / 3560 | 65787 | 0 | 200/200 | 999/999 | 許容誤差 | mov128×8, callret×18, merge×10, flags×17, store128×5 | 1 (fint) / 5 |
| Stereo (ksst) | 0x18080d4d0 | 1679 | 8 / 6001 | 97316 | 0 | 200/200 | 999/999 | 許容誤差 | mov128×4, merge×9, callret×16, flags×4, store128×4, storelow×1 | 0 / 2 |
| Disperser (kdsp) | 0x180316480 | 2311 | 24 / 11754 | 188379 | 0 | 200/200 | 999/999 | **bit-exact** | callret×49, mov128×40, merge×9, flags×26, jumptable×1, store128×1 | 3 (ret0/dint/memmove) / 8 |

- lift 関数: Resonator = process + powf closure 5 (EQ 実績の再利用, fint shim)。Stereo = process + sincos_a/b + k_dc×5 (EQ 実績)。Disperser = process + clear (0x1803172a0) + finish (0x1803172f0) + norm (0x180316d90) + biquad (0x180bac490) + interp (0x180006500) + libm closure 16 (EQ 実績)。
- gen_simd.py 追加 helper: **rcpps / rsqrtps** (IEEE 1/x・1/√x, 近似命令との差は gate 判定) / **packed compare (cmpleps 等 ps/pd)** / **cvttps2dq**。undefined 0 (3 本合計 192 helper 生成)。
- 1000 trial (seed 7): Resonator 4999/4999 call (approx 語 570,158) / Stereo 4999/4999 (approx 4,065 / maxrel 1.5e-4) / Disperser 4999/4999 bit-exact。

## 2. レイアウト起こし (scenario)

### Resonator (`harness/scen_resonator.h`)
- this(0x120): +0x60 = **prepare 周波数 f** (slot7 = `movss [rcx+0x60], xmm1` で設定), +0x6c = 同値 (共通 DelayLine prepare `0x1802c82e0` が this+0x68 に f/cap/buffer を設定), +0x70/+0x80 = cap (**wrap ミラー offset**), +0x78/+0x88 = 履歴バッファ (cap+3 float, cap..cap+2 がミラー = 書込 pos < 3 時の jb 経路で書かれる), +0x90 cap, +0x94 mask, +0x98 wr / +0x9c fill (実初期値 3 = `movabs 0x300000003`), ramp 群 ×5 (0xa0/0xb8/0xd0/0xe8/0x100: pos/slope/from/to/cur/first)。
- ctx+0x3188 → P: +0x00 MIDI note (**expf(note/12 − 5.75) × (440 or 880) = 目標周波数** — note ≥ 69 で引数 > 0), +0x04 decay, +0x08 resonance, +0x0c mode bit0, +0x10。process は P を書かない。
- ループ: 遅延 = spread(rcpps 精密化値の差) × f = **O(1) sample** + cubic Hermite 補間 (重み和 = 1 を確認) + 状態変数共振。
- P レンジ: note ∈ [70, 96], decay ∈ [0.05, 2], resonance ∈ [0.1, 1] (利得 = (P8−1)·decay, \|利得\| ≤ 0.9 — §3), ramp 初期値 ±0.9。

### Stereo (`harness/scen_stereo.h`)
- this(0xd0): ramp 群 ×4 (0x60/0x78/0x90/0xa8) + one-pole 状態 +0xc0 (f32 ペア, movlps store/movsd 再読 = 型パン) + +0xc8 f + +0xcc 係数。
- ctx: P{+0x00, +0x04} — **終端に rsqrtps 経路の meter 値を P+0x0c / P+0x10 へ書き戻す** (許容誤差領域)。Q{+0x48 位相 (quarter-turns), +0x7c/+0x9c dirty}。V{+0x68 end, +0x70 cap} 通知 vector (常に空き → realloc 0x18004cf20 不発 = Gain と同一パターン)。
- 位相: sin/cos(Q48·π/2)。**Q48 ∈ [−64, 64]** (θ ≤ 100)。Q48 = model 層で wrap された位相と解釈 (D14 のため大角度は回避 — §6)。

### Disperser (`harness/scen_disperser.h`)
- this(0x470): +0x58 i32 (interp へ渡すが未使用), +0x60.. = 段状態 ×8 (double×4/段, 0x20/段), +0x460 = **前回段数 (−1 = 初回)**, +0x464 = サンプルレート (biquad design へ f64 で), +0x468 = meter sub-object (+0x28/+0x128/+0x228/+0x328/+0x428 に入出力積算, n ≤ 64)。
- ctx: +0xa8 u8 = 0 (**dirty 通知 OFF → 0x18004df70 は epilogue のみ = ret0 shim、vtable 間接 call 不発**), +0xb0.. = param entry 表 (全 0 → interp の照合 loop が 1 周で停止, 0x18004d980 不発), +0x3150 → R{+4 bit0 = 有効}, +0x3188 → P{+0x00 i32 段数 0..8, +0x04 最大周波数, +0x08 分散量}。
- 構造: 段数 = P[0] (前回値 this+0x460 と min/max) — min 段カスケード (loop1) と max 段カスケード (loop2 = loop1 出力に継続段を適用。カスケード合成より max 段結果と一致) を buffer 内 crossfade (重み = table[prev<cur]/n を 2 sample 毎に加算)。段数減時は余り状態を zero 化。norm (0x180316d90) は設計係数 → オールパス係数変換 (EQ 実績)。

## 3. 許容誤差判定の設計 (CAB-224) — 実測根拠

- **比較器拡張** (`harness/compare.mjs --tol`): 領域×範囲を f32/f64 として 4B/8B word 単位で判定。gate は liftlib `simdtest.py` と**同一式**: `|a−b| > 1.6·2⁻¹²·max(|a|,|b|) + floor` → 不一致 (両方 NaN は OK, ±inf は値一致必須)。floor 既定 1e-38 (simdtest 同一)、音声領域のみ `absFloor: 1e-3` を設定。`--tol` 無しは従来どおり全バイト bit-exact (**既存 6 本の判定は不変**)。
- **適用**: state 領域 (self の rcpps/rsqrtps 由来 ramp 値, P の書き戻し meter 値) = 厳格 gate (floor 1e-38)。音声領域 (bufL/bufR/histL/histR) = 同 gate + absFloor 1e-3。
- **根拠 (遅延 0 実験)**: Resonator の遅延倍率を 0 にすると (補間/離散化経路を排除) **200/200・exceed 0 で maxrel 3.6e-5** — rcpps 精密化後の差は 1〜2 ulp (~1e-7 相対) で gate の 1/1000。
- **増幅の構造 (音声領域の absFloor が必要な理由)**: (1) 逆数の差が「目標周波数と prepare 周波数が近い」とき spread の**桁落ち**で相対増幅 (~3e-6); (2) 遅延の cvttss2si/cvttps2dq **離散化**で t が boundary を跨ぐと補間タップが切替 (数学的連続だが fp 誤差が状態に累積); (3) **共振フィードバック利得 \|g\|→1 で 1/(1−\|g\|) 倍に増幅** — 実測: 利得 0.978 で音声相対誤差 3.5e-4 (gate ちょうど)、高Q + 大振幅リング (状態 ~1e5) では小振幅区間の相対評価が発火。ゆえに音声領域のみ abs 1e-3 (−60dB, 実測最大超過 ~2.3e-4 の 4 倍マージン) を許容。**Intel vs AMD の実機差としても同種の差が出る (bit-exact の定義が CPU 依存という課題の帰結)**。
- **非近似経路の bit-exact 検証**: strict 領域 (self/P) は 200+1000 trial で超過 0。音声領域の差分語の大半は 1〜数 ulp (Resonator approx 語 140,067 / Stereo 827 / 200 trial)。

## 4. Disperser の追加確認 (CAB-225)

- **近似命令 0 件**を再確認 (process 2311B の逆アセ: rcpps/rsqrtps/rcpss/rsqrtss なし) → bit-exact 判定を適用。
- biquad 設計 (0x180bac490) の jumptable は EQ と同一設定 (`180bac559` → table `18236200c`, 8 entries) で復元。設計呼び出しは (out, type=7=オールパス, xmm0=f32 サンプルレート, xmm1/xmm2/xmm3 = f64 引数, スタック = f64 分散量) — stage-0 の実引数がそのまま lift され callret 補正で整合。
- `0x180006500` (interp): 先頭で `0x18004df70` を**無条件呼び出し**するが、ctx+0xa8 ≠ 1 なら即 epilogue (副作用 0) → **ret0 shim** (`gen_stubs_sigs.py` に SH 追加) で忠実に置換。dirty 経路は vtable 間接 call を含み対象外 (親 REPORT §7)。
- meter 積算 (0x1803172a0 / 0x1803172f0) は n ≤ 64 で 64 float 配列に収まる (quickeq と同一制約)。

## 5. ablation

Resonator/Stereo/Disperser は既存 pass セット (mov128/store/merge/flags/callret/rdata/jumptable) で完走し、新規 pass は不要。個別 ablation は `ABLATE=1` (scripts/ablate.py は既存 6 本対象のまま)。

## 6. 未解決 / ブロッカー / 次

- **D14 (sincos 大角度)**: \|x\| ≥ 5e5 の Payne-Hanek 経路が lift で破綻 (実測は DEFECTS.md D14)。原因はじめ込み未特定 (k_dfdb0 の 128bit mul / bsr 未定義部 / 可変 shift CF)。位相は model 層 wrap 前提なので実運用影響は小さいが、**CAB-54 [KH-2] / CAB-55 [検出器] の inputs**。→ **§9 (KH-2b / CAB-242) で修復済** (rdata 窓断末が真因、52,800/52,800 bit-exact)。
- **高Q体制の許容誤差**: 利得 →1 で差が 1/(1−\|g\|) 倍に増幅 (§3)。scenario は \|g\| ≤ 0.9 に収めた。高Q を含めた判定 (または rcpps 近似表の wasm 移植 = bit-exact 化) は方針判断が必要 → 下流チケット案。
- **rcpps/rsqrtps 近似表の移植案**: 実機から 4096-entry 表 (~16KB) を抽出すれば wasm 側も bit-exact にできる (本タスクでは未実施 — 許容誤差方針が確定済みのため)。
- stub のまま (到達 0): Resonator = powf closure の深部 5 (`180fb6ce0` 等, EQ と同一), Stereo = vector realloc `18004cf20` + NaN/Inf 分類 `180fdc714`, Disperser = `18004d980` (param 変更通知, dirty 経路) + libm 深部 4 + `180fdc714`。
- **並行作業の引継ぎ情報**: `tools/targets/kilohearts/license/` に前セッション (insufficient_credits 中断) 以降の未コミット成果物 (REPORT.md / lic_stub.py / work/) が残置 — 本タスクの責務外のため触っていない。メインでの確認・コミット判断が必要。
- 性能: Path B のまま (レジスタ = メモリ経由)。register localization (mem2reg) は CAB-154 [PERF-P1] に申し送り済み。

## 7. ユーザ依頼事項

なし (素材・認証とも不要)。

## 8. 成果物 (本追試での追加・変更)

`snapins.json` (resonator/stereo/disperser の lift/abi/shim/jumptable/tol 設定)、`harness/{scen_resonator.h,scen_stereo.h,scen_disperser.h}` + `scenarios.c` (3 scenario 追加)、`harness/compare.mjs` (--tol 許容誤差判定 + TOL_DEBUG)、`lift/gen_simd.py` (rcpps/rsqrtps/packed-cmp/cvttps2dq)、`lift/gen_stubs_sigs.py` (ret0 shim)、`lift/build.py` (--tol 引渡し)、`scripts/{const_dump.py(新規),make_table.py(9本+判定列)}`、`run_all.sh` (9 本化)、`DEFECTS.md` (D14)。`work/` (gitignore: 各 tag の wasm/IR/vectors/compare.json)。

## 9. KH-2b (CAB-242): D14 修復 — sincos_a Payne-Hanek 経路 (|x| ≥ 5e5) の bit-exact 化

**結論**: 修復完了。`sincos_a` (0x180fcd690) / `k_dfdb0` (0x180fdfdb0) の単体差分 (native oracle = 実機 AMD Ryzen 9 9950X) が **52,800 / 52,800 call 全ビット一致** (seed 1: 4,800 / seed 7: 24,000 / seed 42: 24,000 — いずれも sincos_a と k_dfdb0 が半々)。引数域は \|x\| ∈ [3.2, 1e9] (Payne-Hanek 域 [5e5, 1e9] + その境界・2冪・負数 + 中域補正経路 (π, 5e5))。**既存 9 scenario の判定行は baseline と 1 行も差分なし** (`work/run_all.final.log` と `work/run_all.base.log` の RESULT 行 diff = 0、run_all.sh exit 0)。

### 9.1 根本原因 (実測切り分け) — DEFECTS D14 の訂正
- **主因 = [rdata] 窓 64B による 2/π 表の断末 (D11 の可変 index 変種)**: `k_dfdb0` は表 base 0x18228ac50 を `lea r9,[rip+..]` で取り、`mov rax,[r9+r10]` / `movdqu xmm0,[r9+r10+8]` / `movq rax,[r9+r10+24]` と **可変 index r10 = 0x86−(e>>3) ∈ [6, 132] byte** で計 24B×3 系統 (最大 **+164 byte**) 読む。kh_lower [rdata] は VA リテラル (base) にしか窓を張らず、build.py は gen_globals に `--window 64` を固定渡し → 表の byte 64..163 がどの global 窓にも存在せず (次窓 0x18228acf0 は base+160)、四分国民・還元値が O(1) 破綻していた。\|x\| < 5e5 で破綻しなかったのは e>>3 が小さく index が 64 未満に収まる fig 円経路を使わないため (見かけ上「大角度のみ破綻」)。
  - 証拠: 生成物の globals のみ `--window 256` に差し替え → 同一 IR で **0/200 → 4800/4800 bit-exact**。
- **stage-0 の語彙 (CF/mul/adc/bsr/可変 shift) は既に正確**: `shr rax,cl` の CF=最後の shift-out bit → `jae` 反転分岐 → `adc rax,0` の CF 生存、`mul` の 128bit 積、`adc rdx,0` の carry 伝播、`bsr` の src=0 → dest 不変 + ZF=1 (実機動作と一致する model) を stage-0 IR で全て確認 (`work/quickeq/retdec0/*.stage0.ll`)。旧 D14 行の「可変 shift の CF 扱い」は誤仮説 — 欠陥は演算語彙ではなく **データ供給 (rdata 窓)** にあった。
- **潜伏語彙差の防御 [vshift]**: LLVM は shift count ≥ bitwidth を poison、x86 は CL を 6bit (64bit op) / 5bit (32bit op) にマスク (0 なら値・フラグ不変)。`k_dfdb0` 内 `shl r9,cl` (cl = 64−bsr(r9) は r9==1 で 64 になり得る) 等が該当。詳細は 9.2。

### 9.2 実装
1. **build.py**: gen_globals の窓幅を snapins.json `rdata_window` で設定 (既定 64 = 従来動作・6 本は無変更)。k_dfdb0 を含む quickeq/stereo/disperser = **256** (formant = 2048, §10)。
2. **kh_lower.py [vshift] pass**: stage-0 IR の `shl/lshr/ashr i32|i64 %v, %reg` (レジスタ count のみ。即値はエンコード上 ≤ 63 なので対象外) に `and iN %reg, 63|31` を前置し x86 の count マスクを IR で明示 (poison 解消)。フラグ計算側は RetDec が既に `and 63` + `icmp eq 0` ガード付きで自己整合。quickeq/stereo/disperser/formant で各 44 発火。ablation (`--skip vshift`, 窓 256) で **発火差 0** (= 今回の入力域では発火しない防御パス)。
3. **scenario `qebig`** (新規・既存行への影響なし): 1 trial 12 回 × (sincos_a + k_dfdb0 直呼び, ret f64 = 還元値) = 24 call/trial。specials (5e5 境界・2冪・負数) + 大域 log 一様 [5e5, 1e9] + 中域 (π, 5e5)。k_dfdb0 の四分国民 (rax) は compare.mjs が直接比較しないため sincos_a 経由で担保。
4. **snapins.json**: quickeq abi に `180fdfdb0 {double→double}` 追加 (単体差分用 wrapper。内部呼出は変化なし — qemath 999/999 を維持)。

### 9.3 検証 (実測)
| 実施 | 結果 |
|---|---|
| qebig 200 trial seed 1 | **bit-exact 4,800/4,800** (sincos_a 2,400 + k_dfdb0 2,400) |
| qebig 1,000 trial seed 7 / seed 42 | **bit-exact 24,000/24,000 × 2** |
| ablation: 窓 64 + [vshift] 有 | 0/200 — 主因が窓であることの再確認 |
| ablation: 窓 256 + [vshift] 無し | 4,800/4,800 — vshift は潜伏欠陥の防御 (発火差 0) |
| run_all.sh (10 本 + qemath + qebig) | **exit 0**、既存 9 本の RESULT 行は baseline と完全一致 |
| 副作用 | quickeq/stereo/disperser の wasm が +22〜23KB (窓 256 化)。下記 §9.4 の表を正とし §1 の当該 cell は更新前値 |

### 9.4 修復後の一覧表 (10 本 — §1 と同一書式, KH-1c の Formant を含む)

| snap-in (id) | process VA | process B | lift fn数 / 合計B | wasm B | undefined import | trial | call | 判定 | 必要な修復 (発火数) | shim / 未lift stub |
|---|---|--:|--:|--:|--:|--:|--:|---|---|---|
| Channel Mixer (kscm) | 0x1804f41a0 | 257 | 3 / 275 | 23206 | 0 | 200/200 | 1149/1149 | bit-exact | mov128×3, flags×1, merge×2 | 0 / 0 |
| Gain (ksgn) | 0x1804b0380 | 609 | 1 / 609 | 23054 | 0 | 200/200 | 999/999 | bit-exact | merge×2, flags×1, store128×1, callret×2 | 0 / 1 |
| Haas (ksha) | 0x1804d0280 | 1175 | 5 / 1606 | 35967 | 0 | 200/200 | 1100/1100 | bit-exact | store128×4, merge×5, flags×5, storelow×1 | 0 / 0 |
| Clipper (kclp) | 0x180884b30 | 1683 | 3 / 1743 | 37457 | 0 | 200/200 | 1100/1100 | bit-exact | mov128×10, merge×8, flags×10, store128×4, callret×1 | 0 / 0 |
| Gate (ksgt) | 0x1804c2f50 | 1703 | 3 / 2532 | 45754 | 0 | 200/200 | 999/999 | bit-exact | callret×12, mov128×11, flags×9, merge×2, store128×1 | 2 / 1 |
| 3-Band EQ (ksqe) | 0x18035fb10 | 1754 | 24 / 11512 | 208237 | 0 | 200/200 | 999/999 | bit-exact | mov128×43, flags×30, merge×13, store128×11, callret×49, jumptable×1, vshift×44 | 2 / 6 |
| Resonator (ksre) | 0x180743390 | 2020 | 7 / 3560 | 65787 | 0 | 200/200 | 999/999 | 許容誤差 | mov128×8, callret×18, merge×10, flags×17, store128×5 | 1 / 5 |
| Stereo (ksst) | 0x18080d4d0 | 1679 | 8 / 6001 | 111574 | 0 | 200/200 | 999/999 | 許容誤差 | mov128×4, merge×9, callret×16, flags×4, store128×4, storelow×1, vshift×44 | 0 / 2 |
| Disperser (kdsp) | 0x180316480 | 2311 | 24 / 11754 | 209777 | 0 | 200/200 | 999/999 | bit-exact | callret×49, mov128×40, merge×9, flags×26, jumptable×1, store128×1, vshift×44 | 3 / 8 |
| Formant Filter (ksvf) | 0x18085a730 | 614 | 17 / 9296 | 405390 | 0 | 200/200 | 999/999 | bit-exact | mov128×20, callret×39, merge×7, jumptable×1, store128×1, flags×20, vshift×44 | 1 / 6 |

## 10. KH-1c (CAB-243): Formant Filter (ksvf / vocalfilter) lift — bit-exact 200/200

**結論**: `vocalfilter::VocalFilterDsp::process` (0x18085a730, 614B) を Path B (kh_lower) で lift → **ctx-fuzz 200/200 trial・999/999 call bit-exact** (1,000 trial seed 7 も **4,999/4,999 bit-exact**)。process 系に近似命令 (rcpps/rsqrtps) が無いことを逆アセで確認済ゆえ bit-exact 判定を適用。wasm **405,390 B** / undefined import 0 / SIMD helper 110 種 (abort 残 0)。

### 10.1 lift 構成 (17 関数 / 9,296 B)
- process (0x18085a730) + **biquad design 0x180bac490** (Disperser/EQ 実績の再利用。jumptable 0x180bac559 → 0x18236200c ×8 も同一設定) + **log10f 0x180fbbae0 (1,237B — UCRT log10f。FMA3/SSE2 二系統を内包し、ディスパッチ flag 0x184162364 (PE 実値 0x3E19B838 ≠ 0) により実機も wasm 側も FMA 系を実行。vfmadd 系は gen_simd の fmaf 単一丸めで exact)** + libm closure 14 (sincos_a/b, m_cde58, k_dc470/660/700/6d8, k_dfdb0, m_fcdbfc, m_fd27a8, m_fbde90, m_fbe018, m_fd5250, m_fe5c74 — quickeq 実績セットから未使用の powf/m_fbbfb8/m_fcf904/m_fbdfcc/m_fd54cc を除いた必要集合)。
- **gen_simd.py 追加 helper**: `paddd/psubd/psrld/pslld` + VEX 別名 (`vpand/vpor/vpxor/vpandn/vpaddd/vpsubd/vpsrld/vpslld/vcvtdq2ps`) — log10f の指数/仮数分離 (packed int 経路) 用。**すべて厳密整数演算・C 正規変換 = exact**。declare 駆動ゆえ未使用の既存 9 本の生成物は不変 (全緑で再確認)。
- shim: `dint` (0x180fbdd78, EQ 実績)。fail-fast stub 7 (`180fd4c50` = log10f 特殊値経路 (x ≤ 0 / inf / NaN → CRT 例外報告 chain へ深掘りするため lift 対象外) ほか) — scenario は Q = P+0x08 > 0 常時ゆえ**到達 0**。
- **rdata_window = 2048**: log10f が表 base 0x182286100 / 0x182286530 / 0x182286740 を可変 index (≤ 255 × 4B → +1,020 byte) で読むため (D14 と同型の窓要求。§9.2 の `rdata_window` 機構の第 2 適用例)。

### 10.2 構造 (逆アセ起こし)
- this(0x100): +0x60 = f32 サンプルレート (prepare slot7 = 0x180020650 設定値)、+0x70..+0xf0 = DF2 状態 8 スロット × 16B (L/R 2 ch を f64 ペアで保持。reset slot15 後 = 0 初期化 = arena 0 転写と一致)。
- ctx+0x3188 → P{+0x00 f 周波数 A, +0x04 f 周波数 B, +0x08 f **Q** (log10f 定義域 > 0), +0x0c u8 bit0 → biquad type = **2\|5**, +0x10 u8 bit0 → type = **0\|5**}。process は P を書かない。
- 処理: dB = 20·log10f(Q) → biquad design × 2 (第 5/6 スタック引数に Q と dB を渡す。第 2 引数 xmm1 は biquad 冒頭で定数 1.0 を再ロードするため呼出側が設定しない MSVC コードだが register-global 方式で忠実に再現) → min/max 周波数で別 type の 2 段縦続 biquad → per-sample f64 状態更新 → cvtpd2ps で f32 出力 (L/R)。
- AudioBuffer は既存レイアウト (ch0@0, ch1@8, n@0x28)。scenario: A,B ∈ [20, 20000] Hz, Q ∈ [0.1, 30], mode bit ×2, sr ∈ {44100, 48000, 88200, 96000}。

### 10.3 検証
- 200 trial seed 1: **200/200・999/999 bit-exact** / 1,000 trial seed 7: **1,000/1,000・4,999/4,999 bit-exact**。
- run_all.sh 全体 exit 0 (§9 の 52,800/52,800 qebig 含む、既存判定行不変)。
- 帰属: 新規 helper 無しでは log10f の int 経路が abort() stub に到達し 0/200 (trap) → helper 追加のみで 200/200。窓 2048 は log10f の表読み出しに必須 (64 のままでは index > 15 で欠落 — §9.1 同型)。

## 11. 未解決 / 次 (KH-2b・KH-1c 後)
- **rdata 窓幅の静的推定**: `rdata_window` は手動設定 (256/2048)。「表 base + 可変 offset」の最大読出幅を IR から機械推定する pass があると同型欠陥 (D11 変種) を未然に防げる → 検出器 (CAB-55) 系の下流チケット案。
- **log10f の特殊値経路**: `0x180fd4c50` → CRT 例外報告 chain は fail-fast stub のまま (到達 0)。x ≤ 0 入力を扱う场景 (model 層で Q ≥ 0 下限あり) では不要と判断したが、将来 Q が 0 を取り得る構成では lift 追加か shim 化 (ret -inf/NaN) が必要。
- Formant Filter 固有の残: なし (bit-exact)。  
- §6 の高Q体制・rcpps 近似表移植案は変更なし (下流)。
