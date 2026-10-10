# batch_plan.md — Fruity プラグイン 141 種 lift バッチ計画

根拠データ: `PLUGIN_MATRIX.json/.md` (実測), `ABI.md`, `lift/` (パイプライン雛形), `work/batch/status*.csv` (T0/T1 バッチ実測)。
工数は**推定**(人日, P0 確立後の 1 本あたり。実測の裏取りが済むまで±50%)。

## 1. 構造上の発見 (計画の前提)

1. **Delphi プラグイン 133 本は同一の約 1.6 MB framework を静的リンク**: 関数 11,3xx 個がハッシュ一致 (13 DLL 以上で一致 = 11,266 種, 130 以上 = 5,449 種; 検収の独立ハッシュでは 10,836 / 6,332 種 = 正規化方式で ±15%)。ただし「同一」は 130/133 本 (Balance の framework 関数バイトの 80% 以上が一致、中央値 96%) で、Dashboard / Wave Traveller / Fruity Envelope Controller の 3 本は 44% のみ (別構成; P0a で個別確認)。プラグイン固有部 (Delphi 本体モジュール) は 12 KB〜(巨大 3 本を除き)約 1.4 MB、中央値 71 KB (132 本; FLEX/FL Mobile 等の巨大モジュール含めて最大 10 MB)。→ **framework (FP_DelphiPlug+RTL+VCL) を 1 回だけ lift して共有**し、プラグインは固有閉包 (中央値 T0 6 KB / 17 関数, T1 22 KB / 60 関数) だけ lift する構成にする。
2. **DSP の実体は共有 SIMD kernel 表**: Fruity Balance の Eff_Render は 4 本の ramp + 関数ポインタ経由 1 本 (mix kernel 0x5dee90) + peak 計測 のグルーのみ。表は framework 初期化 `0x5e19f0` が代入する **45 変数 / 80 実装 / 10.9 KB** (35 変数は 2 実装から選択)。T0 エフェクトの Eff_Render は (サンプル 12 本の実測) 8〜105 命令・呼出 1〜10 回の glue でこの表を呼ぶ (最大は Blood Overdrive 246 命令/FP 58)。
3. 非 Delphi の **MSVC 14.29 C++ DLL 42 本** (engine/単体 41 + FL Mobile bridge 1; engine を持つプラグインは 39 本) は framework 無し・CRT のみで独立 (固有部 100〜800 KB, 一部 2〜3 MB)。 C++ のため lift 難度は Delphi より低い見込み (ただし未検証)。
4. 例外クラス: `Fruity Wrapper` ×2 (VST/AU ホスト), `ReWired`, `MIDI Out`, `Razer Chroma`, `Control Surface`, `Video Player` は **ホスト機能統合** が主 (scope=host, 9 本)。 巨大第三者エンジン (DirectWave/FLEX/ZGE/FL Mobile×3) は scope=big3p (6 本)。

## 2. フェーズ

| Phase | 内容 | 規模 | 出口条件 | 推定 |
|---|---|---|---|---|
| **P0a** | `FP_DelphiPlug` framework の **headless lift** (エディタ/VCL 生成経路は到達させない: Dispatcher ID0 ShowEditor を呼ばない) + 共有 wasm モジュール化 | ~1.6 MB / 11k 関数 (直接参照面は T0: 283 関数 53 KB, T0+T1: 660 関数 132 KB) | `CreatePlugInstance`→ctor→`GetName`/`ProcessParam`/`Eff_Render` が node で完走 | 20 |
| **P0b** | **Host shim** (TFruityHost 46 slot + Dispatcher 上位 30 ID) + Win32/CRT shim (tools/shim 継承) | ID 上位 30 で識別可能サイトの 87% | 全 T0 プラグインが ctor 完走 | 5 |
| **P0c** | **DSP kernel 表 80 本** の lift (未了: 25/80 の IR に x87/f80 → f80 lowering pass 要; 機械語に x87 命令を持つのは 28/80) | 10.9 KB | 差分試験 (native ms_abi 機械語) で全 kernel bit-exact | 5 |
| **P1** | **T0 バッチ (42 本)** | 閉包 305 KB / 781 関数 (41 閉包; Wasp/Wasp XT は同一 block。 計測済: 41/41 が RetDec+pass 鎖→`emcc -c` 通過) | 各プラグイン Render test .flp が自己無矛盾で走る + 差分試験 | 0.5×42=21 |
| **P2** | **T1 バッチ (45 本)** | | 同上 | 1.5×45=67 |
| **P3** | **T2 バッチ (34 本)** engine 分離型 (C++ engine は別トラック可) | | | 4×34=136 |
| **P4** | **T3 (20 本)** 個別チケット (§5) | | | ~300 (推定; 大半は第三者エンジン) |
| (並行) | **GUI**: VCL/Blend2D エディタ → フレーム転送 (M7 路線) | plugin 共通 | HUD 表示 | 別チケット |

## 3. バッチ駆動

```
tools/plugins/
  build_all.sh                         実測 → PLUGIN_MATRIX.{json,md} を 1 コマンドで再生成
  lift/plugin_closure.py [block...]    DSP エントリ (vtable override) から固有閉包 + framework frontier を算出
  lift/lift_ranges.sh PE ranges outdir name   RetDec(select-ranges) → pass 鎖 → SIMD helper C
  lift/batch_lift.sh <block...>|--tier T0     閉包 → lift → emcc -c → work/batch/status.csv
  lift/passes/                         tools/m2,m5,m6,m7,m8,m11 の参照コピー + 本作業で追加した 5 pass (SOURCES.txt)
  lift/t0_balance/t0_e2e.sh            T0 実証: lift→wasm→node ⟷ native 機械語の bit 比較 (1 コマンド)
```

pass 鎖 (`lift_ranges.sh`): `ir_normalize`(m2) → `ir5_patch`(m5) → **`fix_regparam_alloca`** → **`fix_asm_stores`** → `fix_orcond_xnor`(opt-in) → **`fix_dup_decls`** → `m11_asmfix` → `m11_passes`(global→linear VA) → `m11_simd2`(署名駆動 SIMD helper 生成)。太字は本作業の追加 (§4)。

バッチ実行の流れ (プラグイン 1 本):
1. `plugin_closure.py <block>`: 固有閉包と frontier (framework 呼出点) を JSON 化
2. `lift_ranges.sh` で固有閉包を lift (framework は P0a の共有 lift に委譲; frontier は wasm 内 direct call または import で接続)
3. wasm 化 (`t0_balance/build_wasm.sh` 同型) → 共有 framework + Host shim とリンク
4. 検証 (§6)

## 4. lift パイプラインの既知欠陥 (差分試験で実測)

| ID | 欠陥 | 発見 | 対処 | 状態 |
|---|---|---|---|---|
| R1 | RetDec が引数レジスタ r9 を未初期化 alloca と誤認 (`mov r10,r9; movups xmm7,[r10]`) | mix kernel: 165/357 で一致 | `fix_regparam_alloca.py` (汎用) | 解決 |
| S1c | 64bit 部分 store (`movlps [mem],xmm`) が helper 呼出のまま (store 無し) | 同: 313/357 | `fix_asm_stores.py` | 解決 |
| S1d | 128bit store が i64 経由 sext に化ける (上位 64bit 破壊) | 同: 325/357 | `fix_asm_stores.py` | 解決 |
| C1 | RetDec 最適化が `A && B` を `icmp eq i1 A,B` (XNOR) に誤畳み込み (`or.cond`) | 同: 357/357 | `fix_orcond_xnor.py` (**opt-in**: 無差別適用不可。差分試験で検出した関数のみ) | 解決(局所) |
| D1 | 同一 `declare` の重複 (clang "invalid redefinition") | T0 バッチ 5/42 | `fix_dup_decls.py` | 解決 |
| F80 | SSE スカラ変換が `x86_fp80` を生む → wasm バックエンドで libcall 無し | DSP kernel 80 本中 25 本 (IR; 機械語 x87 は 28 本) | **未解決** (f80→f64 lowering pass 要) | 未 |
| ARG | float 引数 (xmm3/スタック) の脱落 (例: ramp 0x5dfef0) | Balance Eff_Render | m7/m8 `ir7_argpass`/`ir8_valueflow` 系の再適用 | 未 |
| IND | 関数ポインタ変数 `.bss` (0x71e4f0 等) 経由の呼出 / VMT 仮想呼出 | Balance | init `0x5e19f0` の静的解決で direct 化 | 未 |

**差分試験を各プラグインの出口条件にする** (RetDec 欠陥は静的には検出困難; 上表 4 件は全て差分試験で初めて露見した)。

## 5. T3 (20 本) 個別チケット方針

| 本 | メモ |
|---|---|
| Sytrus, Harmor | 巨大 Delphi 本体 (固有 223/364 KB で T3 扱いは synth-big 規則)。 framework 共有後なら T2 相当の可能性あり (要再評価) |
| Kepler, Kepler Exo, Transistor Bass, Fruity Slicer 2, Fruity Delay 3, Multiband Delay, Frequency Splitter | engine DLL 1.2〜3.4 MB (MSVC C++; Kepler/Exo 2.65, Transistor Bass 1.59, Slicer 2 2.67, Delay 3 1.2, Multiband Delay 3.09, Frequency Splitter 3.35)。 engine は C++ なので別トラック |
| DirectWave, FLEX | 第三者級エンジン (win: DirectWave 本体 1.1 MB + editor 6.0 MB / FLEX 殻 5.1 MB + engineV2 7.9 MB + engine 5.5 MB)。 sampler/scripting を含む。最後 |
| ZGameEditor Visualizer | OpenGL/Python/NDI/Spout — scope=big3p。 ブラウザでは WebGL 再実装/別方針が妥当 |
| FL Studio Mobile ×3 | FLM エンジン (sqlite/ffmpeg 等) |
| Newtone | zplane 製 engine (5.0 MB, ws2_32)、**第三者ライセンス** — EULA 事実整理は別途 |
| GMS, Morphine, Soundfont Player, Fruity Envelope Controller | 固有 1.0〜1.4 MB。 GMS/Morphine は FP 演算命令 5.6〜5.7 万 (大規模展開 DSP またはテーブル); Soundfont Player/Envelope Controller は 1.1〜1.2 MB — 内訳要精査 |

## 6. 検証戦略 (3 層)

1. **kernel 層 (実証済)**: native 参照 = 実 DLL を VA 敷設して MS x64 ABI で直接実行 (`native_ref.c`)。 wasm(lifted) と同一入力で bit 比較。 Fruity Balance の mix/peak kernel で **1,071/1,071 (3 seed × 357) bit-exact**。
2. **plugin 層**: `Eff_Render` を合成 `this` オブジェクトで native/wasm 両方実行 (this+0xcc 等のコンテキスト、SIMD 表初期化を共通化)。 Render tests (`Data/System/Render tests/*.flp` 82 本, マトリクス `RT` 列) は FLP 経由のエンドツーエンド入力。
3. **FLEngine 統合**: FLP 読込 → CreatePlugInstance → 10 秒レンダ → 出力 hash (FLEngine lift の進捗に依存)。 参照音源は FL 実行環境が無いため **native 機械語 (Linux ms_abi) による自己参照** で代用する。

## 7. 下流チケット (Linear 起票済み; CAB-12 の子)

141 本を重複なく 13 チケットに分割 (ファミリ = PLUGIN_MATRIX §5 を基に、multi-fx→F6, other-fx/audio-editor/gui-fx→F8, DirectWave→G4, ZGE→X)。 推定は **Tier 規則の est_days 合計** (PLUGIN_MATRIX §0。 P0 確立後の 1 本あたり; 計 524.5)。 旧版のファミリ見積 (括弧内) は合計が 416 で Tier 規則と不整合だったため置換。

| チケット | Linear | 内容 | 本数 | 推定 (人日) | 旧見積 |
|---|---|---|--:|--:|--:|
| PLG-P0a | CAB-194 | FP_DelphiPlug framework headless lift (共有 wasm) | 1 | 20 | (20) |
| PLG-P0b | CAB-195 | Host shim (46 slot / Dispatcher 30 ID) + CreatePlugInstance E2E | 1 | 5 | (5) |
| PLG-P0c | CAB-196 | DSP kernel 表 80 本 (f80 lowering, ARG pass 再適用, 差分試験) | 80 kernels | 5 | (5) |
| PLG-F1 stereo-util | CAB-197 | Balance, Center, Mute 2, Phase Inverter, PanOMatic, Send, Stereo Enhancer/Shaper, Spreader | 9 | 5.5 | (6) |
| PLG-F2 eq-filter | CAB-198 | 7 Band EQ, Parametric EQ (1/2), EQUO, Filter, Free Filter, Fast LP, Bass Boost, Low Lifter, Emphasizer, Frequency Splitter(T3) | 11 | 24 | (12) |
| PLG-F3 dynamics | CAB-199 | Compressor, Limiter, Multiband Compressor, Maximus, Soundgoodizer, Transient Processor, Emphasis | 7 | 14.5 | (18) |
| PLG-F4 reverb-delay | CAB-200 | Delay, Delay 2/3/Bank, Reeverb 1/2, LuxeVerb, Convolver, Multiband Delay | 9 | 38.5 | (25) |
| PLG-F5 modulation | CAB-201 | Chorus, Flanger, Flangus, Phaser, Hyper Chorus, Vintage Chorus/Phaser, Frequency Shifter | 8 | 16.5 | (16) |
| PLG-F6 distortion + multi-fx | CAB-202 | Fast Dist, Blood Overdrive, Soft Clipper, WaveShaper, Squeeze, Distructor, Hardcore, Effector, Love Philter | 9 | 16 | (14) |
| PLG-F7 pitch-time | CAB-203 | Pitch Shifter, Pitcher, Newtime/Newtone(zplane), Vocoder, Vocodex, Gross Beat, Scratcher | 8 | 32 | (40) |
| PLG-F8 controller/vfx/gui-only/visual/他 | CAB-204 | NoteBook×3, X-Y(Z), Peak/Formula/Envelope/Keyboard/Voltage Controller, VFX×7, dB meter, Spectroman, Wave Candy, Big Clock, Tuner, Control Surface, Dashboard, Edison, LSD, Transmitter, Transporter | 28 | 56 | (25) |
| PLG-G1 synth-simple/drum-synth | CAB-205 | 3x Osc, Wasp, Wasp XT, Plucked!, DX10, Dance, BeepMap, MiniSynth, SimSynth, Fruit Kick, BassDrum, DrumSynth Live, Drumaxx, Drumpad | 14 | 33 | (30) |
| PLG-G2 synth | CAB-206 | Autogun, BooBass, Harmless, Kepler/Exo, Morphine, Ogun, PoiZone, Sakura, Sawer, Toxic Biohazard, Transistor Bass, Wave Traveller, FL Slayer | 14 | 90 | (70) |
| PLG-G3 sampler | CAB-207 | FPC, FL Keys, Fruity Slicer 1/2, Slicex, Granulizer, GMS, Soundfont Player | 8 | 57.5 | (50) |
| PLG-G4 big | CAB-208 | Sytrus, Harmor, DirectWave, FLEX | 4 | 60 | (80+) |
| PLG-X host/big3p | CAB-209 | Fruity Wrapper×2, Patcher×2, ReWired, MIDI Out, Razer Chroma, Video Player, ZGE, FL Mobile×3 (列挙は 12 本; 旧版の「13」は誤記) | 12 | 81 | (別方針) |

本数計 141 / F+G+X の推定計 524.5 (+ P0 30 = 554.5)。 既存ファミリチケットとの対応: CAB-29→F1,F3 / CAB-41→F2 / CAB-39→F4 / CAB-42→F5,F6 / CAB-27→F7 / CAB-32→F8,X / CAB-28→F8(visual),X / CAB-44→G1,G2(小型) / CAB-30→G2,G4 / CAB-40→G3,G4 (いずれも blockedBy P0a/b/c)。
