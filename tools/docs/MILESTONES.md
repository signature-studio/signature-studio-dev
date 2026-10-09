# MILESTONES.md — マイルストーン状態表 (全 12 段)

最終更新: 2026-10-10 (M6b SIMD helper 接続 + 独立検証 48fe75f 時点, HEAD=c46bd30/48fe75f ベース)
定義元: `analysis/strategy.md` §4 (全 11 段 — 判定原則: 各段の完了条件が満たされたとき次段へ)

| 段 | 状態 | 実測 / 証拠 |
|---|---|---|
| M1 | [x] 完了 | toolchain version pin (emsdk 6.0.12 / RetDec 5.0 / Ghidra 12.1.4)、`tools/m1/m1.sh` で E2E 再実行可能化、定型フラグ独立ファイル化。x64 ELF / PE32+ → RetDec → emcc → wasm → node の出力 3-way 一致 (`hello from e2e, answer=42`) |
| M2 | [x] 完了 | FLEngine 解析の機械化。mac x86_64 slice 抽出 **31,637,920B** (`__text` 17,656,574B)、関数境界合意 **Ghidra 59,009 vs .pdata 57,816 → delta 2.02%** (mac: LC_FUNCTION_STARTS 99.5% Jaccard)、EasyFLAC `_FLAC__crc8` wasm 化 **bit-exact 6/6**、Delphi 品質インベントリ + shim 照合 (`tools/m2/REPORT.md`) |
| M3 | [ ] 部分達成 | 純計算 4 関数 (`_FLAC__crc8` / `_FLAC__crc16` / `_FLAC__bitmath_silog2` / `_FLAC__bitmath_extra_mulbits_unsigned`, EasyFLAC slice 由来) の wasm 化は **bit-exact 50/50 PASS** (`bash tools/m3/m3.sh`, exit=0)。性能比記録済: 同一 lifted IR native(-O2) vs wasm/node = **crc8 1.44x / crc16 1.33x** (10x 未満 → route 再評価は不要; silog2+mulbits は i64 FFI BigInt オーバーヘッド支配で約 36x — 本体計算の指標ではない)。**未達**: (1) 中規模 dylib 丸ごと wasm 動作 — FastMM/Delphi closure 677 関数 IR は ft7.ll:4281 (constexpr 残存 187 件) で emcc コンパイル未通過、(2) lift-down IR pass 1 本 + 性能影の定量化、(3) Delphi try-finally 実測、(4) VMT 間接呼の lift 欠落 (M2 既知 (d) 同型) の対策確認 (`tools/m3/REPORT.md`) |
| M4 | [x] 完了 | Win32 shim コア `tools/shim/` (timer/file/thread/heap, fail-fast)。**53 export API** を MT(pthread)/ST 両ビルドで **node 単体テスト 5/5 PASS** (4 スレッド×10k 排他 / TLS 分離 / byte-faithful file I/O 検証済)。shim 未対応要求の fail-fast 動作も実装 |
| M5 | [ ] 部分達成 | Delphi Mini-PoC: 純計算 2 関数 (waveshaper/distortion) lift IR→wasm が実機 x86 機械語と **bit-exact 8/8** (`m5_compare.mjs`)。FastMM×shim heap 結合 **3/3 PASS** (alloc/free 1,000/1,000・double-free fail-fast・underflow リーク検知)。A9 命令化 lift で mm closure 677 関数の constexpr 残存 **187→2** 件 (合法 inttoptr×2) になり **emcc 通過 + node instantiate 成功**。try-finally (0x409fe0) は finally 経路整合まで達成、ParamCount off-by-one が既知課題 (`tools/m5/REPORT.md`, commit 4aa68a2)。未達: FLEngine 部分的 wasm 起動 (オーディオなし) 全体 |
| M6 | [ ] 部分達成 | OTT DSP クロージャ wasm 化+実行検証着手 — emcc 通過 (commit 2607a2e) のち **SIMD helper 接続** (c46bd30): `msimd6_core.h` 補完 (211 行) + 宣言型駆動 153 種 helper (`m6_simd_check.py` 3 重照合 0 mismatch) で wasm-ld 署名不一致 **12→0 種** / undefined symbol **218→57 種** (`__asm_*` 由来 0)。実行検証 (独立検証 48fe75f 済): t1.mjs **run complete** (512 行, 2 回実行 determinism bit 一致)、t3.mjs **0x2DDFA232 三方照合 OK** (IR literal = DLL `.data` 実測; 旧期待値 0x2DEB8762 は誤値確定)、trap_test OK 6 / FAIL 13 (= missing 11 意図的 fail-fast + broken-lift OOB 2; 対象 7 中 6 解消)。**未達**: bit-exact 512/512 — RetDec closure lift の f32 (xmm) 引数失落 (setter 2-arg 化) は M8 必須前提、broken-lift OOB 2 (c38c8 family, ir6_shift 未対応の算術合成 base)、m6.sh 1 コマンド E2E 化 (M7 引継) (`tools/m6/REPORT.md`, commits 2607a2e→c46bd30→48fe75f) |
| M7 | [ ] 未着手 | GUI フレーム転送 → 操作可能 HUD (SAB → OffscreenCanvas/WebGL2, 30fps 以上) |
| M8 | [ ] 未着手 | オーディオパス (AudioWorklet + SAB ring, 128f master, underrun-free) |
| M9 | [ ] 未着手 | プロジェクト入出力 (.flp) + FL 純正プラグイン 1 個 in-process 動作 |
| M10 | [ ] 未着手 | 性能・安定性チューニング (SIMD, memory growth, GC 緩和) |
| M11 | [ ] 未着手 | E2E 統合 + FL 追従プロセス + EULA/非再配布運用固定化 |
| M12 | [ ] 未着手 | ホストデプロイ + `agent-browser` による E2E 検証 — R2+Workers (COOP/COEP ヘッダ注入 → SAB 有効) + Cloudflare Access 保護。「URL を開くと FL が立ち上がる」を自動検証。GitHub Pages はヘッダ設定不可ゆえ不採用 |

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
2. bit-exact / 制約内一致 — **[未]** t1 run complete 512 行・t3 三方照合 OK まで到達。f32 引数失落 (setter 2-arg 化) = M8 必須前提 ([P2] 引数接続 IR pass)
3. 1 コマンド E2E 化 — [未] M7 引継 (build 鎖は m6_build.sh 内の memfix/extract まで内蔵済、lift 前段 m6_lift.sh も含めた直列化が必要)

### M7〜M11 (未着手)
各完了条件は `analysis/strategy.md` §4 を参照。M7 (FLEngine 部分wasm起動) 突入にあたり M6b 検証完了済 — helper 接続は解消済で M7 の技術的前提は満たす。M7 範囲: m6.sh 1 コマンド E2E 化 (mismatch 0 / undefined 57 種の数値照合組込, t1_out.hex 固定パス化) を subtask 1 とし、main としては unused symbol 57 種 (Win/CRT API 24) を shim/populate で接続する段階相当前に module 結合方針を確定する。
