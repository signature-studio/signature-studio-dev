# MILESTONES.md — マイルストーン状態表 (全 12 段)

最終更新: 2026-10-10 (OTT 継行 subagent M7/M8 完了 — E2E 化 + value-flow 接続, HEAD=9dd2f47 ベース)
定義元: `analysis/strategy.md` §4 (全 11 段 — 判定原則: 各段の完了条件が満たされたとき次段へ)

| 段 | 状態 | 実測 / 証拠 |
|---|---|---|
| M1 | [x] 完了 | toolchain version pin (emsdk 6.0.12 / RetDec 5.0 / Ghidra 12.1.4)、`tools/m1/m1.sh` で E2E 再実行可能化、定型フラグ独立ファイル化。x64 ELF / PE32+ → RetDec → emcc → wasm → node の出力 3-way 一致 (`hello from e2e, answer=42`) |
| M2 | [x] 完了 | FLEngine 解析の機械化。mac x86_64 slice 抽出 **31,637,920B** (`__text` 17,656,574B)、関数境界合意 **Ghidra 59,009 vs .pdata 57,816 → delta 2.02%** (mac: LC_FUNCTION_STARTS 99.5% Jaccard)、EasyFLAC `_FLAC__crc8` wasm 化 **bit-exact 6/6**、Delphi 品質インベントリ + shim 照合 (`tools/m2/REPORT.md`) |
| M3 | [ ] 部分達成 | 純計算 4 関数 (`_FLAC__crc8` / `_FLAC__crc16` / `_FLAC__bitmath_silog2` / `_FLAC__bitmath_extra_mulbits_unsigned`, EasyFLAC slice 由来) の wasm 化は **bit-exact 50/50 PASS** (`bash tools/m3/m3.sh`, exit=0)。性能比記録済: 同一 lifted IR native(-O2) vs wasm/node = **crc8 1.44x / crc16 1.33x** (10x 未満 → route 再評価は不要; silog2+mulbits は i64 FFI BigInt オーバーヘッド支配で約 36x — 本体計算の指標ではない)。**未達**: (1) 中規模 dylib 丸ごと wasm 動作 — FastMM/Delphi closure 677 関数 IR は ft7.ll:4281 (constexpr 残存 187 件) で emcc コンパイル未通過、(2) lift-down IR pass 1 本 + 性能影の定量化、(3) Delphi try-finally 実測、(4) VMT 間接呼の lift 欠落 (M2 既知 (d) 同型) の対策確認 (`tools/m3/REPORT.md`) |
| M4 | [x] 完了 | Win32 shim コア `tools/shim/` (timer/file/thread/heap, fail-fast)。**53 export API** を MT(pthread)/ST 両ビルドで **node 単体テスト 5/5 PASS** (4 スレッド×10k 排他 / TLS 分離 / byte-faithful file I/O 検証済)。shim 未対応要求の fail-fast 動作も実装 |
| M5 | [ ] 部分達成 | Delphi Mini-PoC: 純計算 2 関数 (waveshaper/distortion) lift IR→wasm が実機 x86 機械語と **bit-exact 8/8** (`m5_compare.mjs`)。FastMM×shim heap 結合 **3/3 PASS** (alloc/free 1,000/1,000・double-free fail-fast・underflow リーク検知)。A9 命令化 lift で mm closure 677 関数の constexpr 残存 **187→2** 件 (合法 inttoptr×2) になり **emcc 通過 + node instantiate 成功**。try-finally (0x409fe0) は finally 経路整合まで達成、ParamCount off-by-one が既知課題 (`tools/m5/REPORT.md`, commit 4aa68a2)。未達: FLEngine 部分的 wasm 起動 (オーディオなし) 全体 |
| M6 | [ ] 部分達成 | OTT DSP 継行 — SIMD helper 接続 (c46bd30/48fe75f) → **1 コマンド E2E 化** `tools/m7/m6_e2e.sh` (50c4ccf, 検収 805110b) → **f32 引数接続 PoC** (`ir7_argpass.py`, m7) → **value-flow 接続** (`ir8_valueflow.py`: accessor 誤訳修復 + SVF xmm1 2-arg 化 16 callsite, `ir7_argpass_fixed.py` idx_store32 正本差分, missing 10 stub `m8_rt.c` bit-exact leaf 19/19) — commit 9dd2f47。t1 が qNaN 不応答 constant から **param/入力応答を回復** (T1SVF=1: param diffs 192 / input diffs 225)。**未達**: bit-exact 512/512 (出力スケール junk — SVF 係数 ramp 上流・obj+584 分岐他方・bit-exact 参照実装は M9 引継), broken-lift OOB 2 (c38c8 family), undefined 残 47 種 (`tools/m6/REPORT.md`, `tools/m7/`, `tools/m8/REPORT.md`) |
| M7 | [ ] 未着手 | GUI フレーム転送 → 操作可能 HUD (SAB → OffscreenCanvas/WebGL2, 30fps 以上) |
| M8 | [ ] 未着手 | オーディオパス (AudioWorklet + SAB ring, 128f master, underrun-free) |
| M9 | [ ] 部分達成 | OTT 出力スケール修復 — **部分達成** (commit a3eaaf6): SVF 係数 ramp ([F3] resume 再構成 + obj+0x2ac gate box loop) + 出力 copy deref ([F7] ir9_outcopy) + band filter f0 係数化 ([F8] C port) + tablebase 10進即値 remap ([F9]) で t1 出力が junk 定数から **param/入力応答に回復** (`tools/m9/m9_e2e.sh` exit 0, checks 6/0, 非zero 190/256, census 132/205/175, \|max\| 1.67e20)。m8_e2e 併走で M8 水準維持 (192/225)。**残課題** (M10 引継): band IIR 係数 pole (≈2..4) / 18011efb0 per-sample 分岐 / bit-exact 参照 (本研究 π̂ bits ~6 ulp 不一致候補) / trace pass 群再作成 (`tools/m9/REPORT.md` §5, 修正 77b368d)。原本設定の「プロジェクト入出力 (.flp) + FL 純正プラグイン in-process 動作」は M10 以降に吸収予定 |
| M10 | [ ] 未着手 | 性能・安定性チューニング (SIMD, memory growth, GC 緩和) |
| M11 | [ ] 未着手 | E2E 統合 + FL 追従プロセス + EULA/非再配布運用固定化 |
| M12 | [ ] 未着手 | ホストデプロイ + `agent-browser` による E2E 検証 — **R2 バケット (カスタムドメイン+Transform Rules で COOP/COEP 注入 → SAB 有効)** + Cloudflare Access 保護 (Self-hosted App, Worker 不要)。「URL を開くと FL が立ち上がる」を自動検証。GitHub Pages はヘッダ設定不可ゆえ不採用。Workers は動的エンドポイントが必要になった場合のみ追加 |

## 各段の検証条件と実測 (要点)

### M1 (完了)
1. toolchain version 固定 — [x] emsdk 6.0.12 / RetDec 5.0 / Ghidra 12.1.4 を flags.sh に pin
2. E2E 再実行スクリプト化 — [x] `tools/m1/m1.sh` (1 コマンド)
3. 定型フラグ独立ファイル化 — [x] `tools/m1/flags.sh`
4. 出力一致 — [x] node 出力 3-way 一致 (ELF / PE32+ / wasm)

### M2 (完了, `tools/m2/REPORT.md`)
1. 関数境界 ±5% — [x] **2.02%** (win), mac 99.5% Jaccard
2. shim export 一覧自動生成 — [x] `SHIM_INVENTORY.md` (libwinbridge)
3. 副モジュール 1 個の IR化→wasm 動作 — [x] EasyFLAC `_FLAC__crc8` (299KB slice→wasm **bit-exact 6/6**)
4. Delphi 品質確認 (§5.7 観点) — [x] `delphi_inventory.md` (VMT/RTTI/FastMM/SEH; try-finally は .pdata 観点の静的記録まで)
5. delphi_inventory.md 機械生成 — [x]
6. import 面 diff — [x]

### M3 (部分達成, `tools/m3/REPORT.md`)
1. 対象 wasm bit-exact — **[部分]** 純計算 4 関数 50/50 (EasyFLAC 由来)。中規模全体 (677 関数 Delphi closure) は未通過
2. 性能比記録 — **[x]** (本検証で測定; >10x → route 再評価: データ主導の crc 系は 1.3〜1.5x で適用不要)
3. lift-down pass + 定量化 — **[未]** pass 数は ir_patch.py の stage 計上として出力 (A1〜A9/B1/B2/C1の13 pass, mm 677 関数では B1 280 件実改変) するが、性能影の定量化未

### M4 (完了, `tools/shim/`)
1. shim 単体テスト — [x] file/thread/heap/timer 計 5 系統全 PASS
2. M3 wasm からの shim 呼出 (モジュール連結) — [x] (src/runtime ローダ経由のスモークは M2 時点で実績)
3. 未対応要求の fail-fast — [x]

### M5 (部分達成, `tools/m5/REPORT.md`, commit 4aa68a2)
1. Delphi 純計算 bit-exact — [x] waveshaper/distortion 8/8 (m5_compare.mjs, native VA敷設参照)
2. FastMM→shim heap 短絡化 — [x] 3/3 PASS (alloc/free 1,000, double-free fail-fast, underflow リーク検知)
3. try-finally 実測 — **[部分]** finally 経路整合のみ、ParamCount off-by-one 既知
4. FLEngine 部分 wasm 起動 (オーディオなし) — [未] M7 以降へ引継

### M6 (部分達成, `tools/m6/REPORT.md`, commits 2607a2e / c46bd30 / 48fe75f)
1. OTT DSP クロージャ wasm 化 — **[部分→着手]** lift→IR pass→emcc ビルド通過 → **SIMD helper 接続** (宣言型駆動 153 種, `m6_simd_check.py` 0 mismatch) で署名不一致 12→0
2. bit-exact / 制約内一致 — **[未→着手]** t1 run complete 512 行・t3 三方照合 OK → f32 引数接続 PoC (commits 50c4ccf : 呼出 site bits 3rd arg 化 + dsm jump table 20 case 本体再生, m7 REPORT §3) と M8 value-flow 接続 (commit 9dd2f47 : `ir8_valueflow.py` accessor 誤訳 [F1] 修復 + SVF `function_1801260c0` dropped xmm1 16 callsite 2-arg 化 [F2] + `ir7_argpass_fixed.py` idx_store32 正本差分 + missing 10 stub `m8_rt.c` bit-exact leaf 19/19)。**t1 param/入力応答を回復** (T1SVF=1: param 0.5→0.9 diffs 192 / 入力 +0.3 diffs 225, M7 まで 0/0)。**未達**: bit-exact 512/512 — 出力は巨大値 junk (SVF 係数 ramp 上流 / obj+584 路 / L-R copy 未接続) で M9 引継。検収: `bash tools/m8/m8_e2e.sh` exit 0 (undefined 57→47 種, trap8 OK 14/FAIL 5)
3. 1 コマンド E2E 化 — **[x]** `bash tools/m7/m6_e2e.sh` (lift→pass 鎖→build→simd_check→t1/t3/trap 直列化+数値照合, signature mismatch 0 / undefined 57 種 / t1 2-run SHA 一致) — commit 50c4ccf, 検収 805110b

### M7〜M11 (状況, `analysis/strategy.md` §4)
M9 (commit a3eaaf6, 検収修正 77b368d): SVF 係数 ramp ([F3] resume 再構成 + obj+0x2ac gate box loop 復元) + 出力 copy deref 修復 ([F7] ir9_outcopy) + band filter f0 係数化 ([F8] C port) + tablebase 10進即値 remap ([F9]) で t1 出力が junk 定数から param/入力応答に回復 (`m9_e2e.sh` exit 0, checks 6/0, 非zero 190/256, census 132 zero/205 通常/175 junk, |max| 1.67e20)。
M10 (commit 959a60d, 検収修正 9a159e7): band filter C port の真の破れ 4 点修復 (mulsd C1⁴ / mulsd 4W2² / mulsd ×6.0 + π̂/2π̂ 実ビット転記 0x4009249249249243) で band 8 states × 10 係数 dsm register-exact **bit 突合 maxdev=0.0** (f0=88.3/2500 両系)。`m10_e2e.sh` exit 0, checks 7/0; m9_e2e 併走 PASS。bit-exact 512/512 は junk 残存で不成立 → tolerance 判定を e2e スクリプト化。junk census ([0x248]=0) は m9 と同値で band 修復と独立に存続 — 出生 cause は band-IIR pole ではなく **exp/log chain** (±2^65/±2^-63 EXACT, trace 6 本で裏取り)。

### M11 進行中 (`tools/m11/`, FLEngine_x64.dll 部分起動 PoC)
FLEEngine_x64.dll 部分起動 PoC 進行中: DllMain → 初期化 closure lift → emcc → wasm → Node, FastMM heap 初期化完走 + Win32/CRT stub (tools/shim 継承 pattern)。**M11 引継 (M10 REPORT §5 より)**: (1) [0x248]=0 exp chain 修復 — junkHi 175 の真正原因 (outcopy 前段の box state [0x200..0x218] per-sample 破れ; ±2^65/×1.0043 系列); (2) [0x248]=1 経路 per-sample 破れ点 — x cell denormal (3e-41) 入力 deref 欠落 ([F7] 型修復の 0x18011e* 適用, y ~×1.5/sample 増大); (3) 0x2a8 ring 周期性の統一ハーネス化 — [0x250]/[0x258] 6+8 rings per-cell 追跡 (pointermanager qword stride)。bit-exact 512/512 判定は junk-free 確保後に実施 (native poly tan ulp マージ留保)。
