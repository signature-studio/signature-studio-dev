# Kilohearts (HeartCore 2.4.6 / release 132102) インストーラ解析 + snap-in lift 可否 (target 事前解析)

> **付録**: §10-7b・§10-7c の全文は `tools/targets/kilohearts/REPORT_APPENDIX.md`。

- 解析日: 2026-10-10 / 担当 dir: `tools/targets/kilohearts/` (抽出物・大物は `work/`, gitignore)
- 素材: `~/ダウンロード/Kilohearts Offline Installer.zip` (3,833,108,300 B) / `.dmg` (3,841,525,745 B)
- 1 コマンド再現: `bash tools/targets/kilohearts/run_all.sh` (約 30 秒 + 初回抽出; `RUN_GHIDRA=1` で Ghidra クロスチェック)

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| 製品数 | **45 製品** (index.json) = 効果 snap-in **42** + snap-in ホスト 2 (Multipass / Snap Heap) + Phase Plant。ほか shell のみ 2 (kHs Group / Host Proxy)、コンテンツ bank 41、HeartCore 本体 1。**kHs ONE / Bite は本インストーラに含まれない** |
| フォーマット | VST2 / VST3 / AAX (Win x64), + AU (mac)。**CLAP なし**。`.snapin` は専用ファイルでなく index の format フラグ + stub の `KiloheartsSnapinMain` export |
| 構造 | **47 本の 247KB 薄い stub (Win) が 1 枚の `HeartCore.core_64` (76.6MB, 全 47 製品の DSP+GUI を静的内包) を LoadLibrary** し `VSTPluginMain_<id>` 等へ転送。lift 対象 = HeartCore 1 本 |
| FW 判定 | **JUCE ではない**。自社 FW (`SnapinDsp<Model>` / `SnapinMasterDsp<Dsp,Model>` / Controller / EditorModel / Editor 7 分割) + Skia (CPU raster, SkSL) + boost + libcurl + PACE iLok(Eden) + FLAC/libpng/zlib/libjpeg-turbo |
| 認証 blocker | **あり** — HeartCore に **PACE iLok/Eden のライセンスクライアントが静的リンク** (RTTI `pace` 313 / `license_services` 154 クラス, activation.paceap.com / ilokcloud.com, WS2_32+libcurl+WinVerifyTrust) + Kilohearts 独自 LicenseManager (購読 `ksub`, Splice, Slate, trial, key 入力)。ただし **DSP closure にライセンス/ネット系の参照は無く、共通基盤 188 関数を除く固有コードで Win32 import を呼ぶのは 3 本のみ** (§5)。wasm 同梱時の扱いはユーザ判断事項 (§7) |
| .text 規模 | HeartCore `.text` 20,576,428 B / .pdata **111,666** 関数 (sweep 120,856 関数・5,067,653 命令・19.38MB = 94.2%)。**効果 42 本の DSP 固有コードは計 287,610 B (=.text の 1.4%)**、共通基盤 (≥8 snap-in が共有) 188 関数 53,010 B |
| lift 難度 | 最易: **Channel Mixer(554B) < Gain(1.7KB) < Haas < Clipper < Gate < 3-Band EQ < Resonator < Stereo < Disperser**。最難: Carve EQ / Snap Heap / Multipass / Phase Plant (§4) |
| **PoC** | **kHs Gain `gain::GainDsp::process` (VA 0x1804b0380, 609B/137 命令) を RetDec→IR pass→emcc で wasm 化し、実機 x86 機械語 (ImageBase 敷設・ms_abi 直接実行) と 6/6 ブロック bit-exact** (354 sample×2ch + 状態 0xA0B + 通知)。RetDec 生出力は **0/6** (silent miscompile 2 種を発見・修復, §6) |

## 1. インストーラ構成

### 1.1 共通: 自作インストーラ + content-addressed payload
- zip = `Kilohearts Installer.exe` (15,595,736 B, PE32+ v1.1.69, Authenticode 署名, 同 FW (Skia/PACE/curl) の自製 GUI) + `payload.dat` (3,817,512,248 B)。
- dmg = bzip2 UDIF → HFS+ (4,160,751,616 B) → `Kilohearts Installer.app` (Mach-O universal `Installer` 23,203,872 B, v1.1.69, min macOS 10.10) + `.payload` (3,818,694,003 B)。7z は末尾で "Unexpected end of archive" を出すが抽出物は完全 (zip central dir 正常・nested unzip エラー 0)。
- `payload.dat` / `.payload` は **zip 形式 (stored) の 179 エントリ**: `index.json` + `<名前>.zip/<16hex hash>` の content-addressed blob (名前付きディレクトリ + 実体 1 個)。win と mac は **`windows.zip`(55,114,108 B) ⇄ `mac.zip`(56,293,015 B) のみ差** (payload 内エントリはどちらも stored、中身はさらに zip: win 143 files 112.4MB / mac 2,491 エントリ 159.2MB に展開)。残る **89 エントリ (index.json + 88 blob) は名前・サイズ・CRC32 (central directory) が全一致** (3.8GB 全体の CRC 再読出しは未実施)。

| payload 分類 | blob 数 | payload 内サイズ |
|---|--:|--:|
| 製品バイナリ (`windows.zip` / `mac.zip`) | 1 | 55.1MB / 56.3MB |
| factory_{samples,wavetables,lfos,curves,remaps,shapes,spectrum_profiles} | 7 | 884,319,020 B |
| factory-presets (製品別 40) | 40 | 247,970,198 B |
| content bank (`kilohearts.cb**.bank`, 41; 外部アーティスト) | 41 | 2,630,026,210 B |

- `index.json`: release **version 132102**, date 1773152315 (2026-03-10), plugins 87 項 (製品 45 + core 1 + bank 41)。各製品に `id`(4 文字), `fileName`, `formats`, `dependencies`(factory_*), `keyMessage`(SHA-1 hex 40 桁), `packageWindows/Mac/Presets`。banks 5 件が `hideWhenUnlicensed`。

### 1.2 製品一覧 (効果 snap-in 42; id / ns)
ksbc Bitcrush / ksch Chorus / kscf Comb Filter / kscc Compactor / kscp Compressor / ksco Convolver / ksdl Delay / ksdf Nonlinear Filter(dirtyfilter) / kdsp Disperser / ksdt Distortion / ksdd Dual Delay / ksot Dynamics / ksqe 3-Band EQ(quickeq) / ksge Carve EQ(graphiceq) / kpeq Slice EQ(equalizer) / kfat Faturator / ksfi Filter / ksft Filter Table / ksfl Flanger / ksfs Frequency Shifter / ksgn Gain / ksgt Gate / ksha Haas / ksla Ladder Filter / kslt Limiter / kscm Channel Mixer(matrix) / kspd Phase Distortion / ksph Phaser / ksps Pitch Shifter / ksre Resonator / ksrv Reverb / ksrr Reverser / ksrm Ring Mod / kssr Shaper / ksst Stereo / ksts Tape Stop / kstg Trance Gate / kstr Transient Shaper / ksun Ensemble(unison) / ksvf Formant Filter(vocalfilter) / ksws Shaper Table(waveshaper) / kclp Clipper。
ホスト: kmup Multipass(`multipass`) / kmic Snap Heap(`micropass`)。シンセ: kphp Phase Plant(`phaseplant`, snapin format なし)。shell のみ: `snapingroup`(kHs Group) / `hostproxy`(kHs Host Proxy) — index 外、Win のみ。
bank 41: Laffitte, Oblivion Engine, Omen, … (Expressive E 系 5 件は `hideWhenUnlicensed`)。全リスト: `work/blobs/index.json`。

## 2. バイナリ表 (実測)

| 種別 | 形式 / arch | 数 | サイズ | 備考 |
|---|---|--:|--:|---|
| Win VST2 `*.vst2_64` | PE32+ DLL x64 | 47 | 247,296 B 全同 (md5 は全て異なる = ID パッチ) | .text 159,204 B / 818 .pdata / 署名なし |
| Win VST3 `*.vst3_64` | 同上 | 47 | 247,296 B | VST2 と**同一コードを別拡張子** |
| Win AAX `*.aaxplugin/Contents/x64/` | 同上 + Authenticode | 47 | 45 本 265,816〜265,832 B (stub + 署名 18,520〜18,536 B; Gain で本体差分がヘッダ 7 byte のみと確認), Group/Host Proxy は署名なし 247,296 B | PACE wrap なし (署名のみ) |
| **Win `HeartCore.core_64`** | PE32+ DLL x64 (ts 2026-03-10) | **1** | **76,642,304 B** | .text 20,576,428 / .rdata 21.8M / .data(raw 1.8M) / **.pdata 111,666 関数** / .rsrc 30.3M(ent 7.59) / export 144 |
| mac VST/VST3/AU/AAX stub | Mach-O universal (x86_64+arm64) | 45×4 | 206,192 / 206,208 B | AAX のみ `__Pace_Eden.bundle` 付属。Group/HostProxy は mac に無い |
| **mac `HeartCore.core`** | Mach-O universal | 1 | 86,089,568 (x86_64 slice 43,101,664 / arm64 42,966,880) | `__text` 21,543,856 B。**ローカル symbol なし** (export 1,551、typeinfo 名 626 は残存) |

- stub export (14): `VSTPluginMain, GetPluginFactory, InitDll, ExitDll, ACF{Startup,Shutdown,GetSDKVersion,RegisterComponent,RegisterPlugin,GetClassFactory,CanUnloadNow}, KHSAudioUnitFactory, KHSAudioUnitLegacyEntryPoint, KiloheartsSnapinMain`。stub 文字列に `.core_64` / `HeartCore` / `VSTPluginMain_xxxx` — **製品 ID を埋め込み HeartCore の `VSTPluginMain_<id>`/`GetPluginFactory_<id>`/`ACFRegisterPlugin_<id>` へ委譲**。HeartCore export は 47×3 + `KHSUnlock` + ACF 6。import は stub: KERNEL32/USER32(MessageBoxA)/SHELL32(SHGetKnownFolderPath)/ole32 のみ。
- AU: type `aufx`, manufacturer ` kHs`, subtype = 製品 ID, factory `KHSAudioUnitFactory`, version 132102。
- `.snapin`: 専用バイナリは payload に無い。index の `formats:[…,"snapin"]` と stub export `KiloheartsSnapinMain` が対応 (Installer による配置形式は静的には未確認 = 推定)。

## 3. フレームワーク / 保護 判定

- **RTTI (MSVC) 6,923 TypeDescriptor / 6,764 COL / 6,307 vtable** を `scripts/rtti_walk.py` で復元。各 snap-in = ns 1 個 (例 `gain::`) に `XDsp / XMasterDsp / XDspModel / XEditorModel / XController / XEditor / UIX` 規則的 7〜8 クラス。mac typeinfo も `SnapinMasterDsp<gain::GainDsp,gain::GainDspModel>` / `SnapinDsp<gain::GainDspModel>` で一致 → **共通基底テンプレート**が `process` ラッパ・param 管理を提供。
- GUI: **Skia (SkCanvas/SkPath/SkRasterPipeline/SkSL 134 文字列) の CPU ラスタ → Win は GDI `SetDIBitsToDevice`、OpenGL/D3D import なし**。mac は Metal.framework を import。M7 の「フレーム転送 HUD」方式と相性良い。
- 静的リンク OSS: Skia, boost, Apache Thrift (PACE 用), libcurl, libpng, zlib, libjpeg-turbo, FLAC 1.4.3, (戦略: upstream から wasm 再ビルド・lift しない)。
- **copy protection / 認証 (事実)**:
  - PACE iLok: `pace::{Ilok1/2Commander, ILokCert, LicenseDb…}` 313 クラス、`license_services::LsEntity{License,Authorization,MachineBinding,TimeLimit,CertificateChain,…}` 154 クラス (RTTI)、`https://activation.paceap.com/InitiateActivation`, `activation.ilokcloud.com`, SETUPAPI (USB iLok 列挙), CRYPT32 証明書チェーン, WinVerifyTrust, WS2_32 + libcurl。
  - Kilohearts 層: `LicenseManager`, `PaceLicenseHelper`, 購読 (`Kilohearts Subscription`/`ksub`), Splice レンタル, Slate All Access Pass, trial ("N days left of your trial"), "Enter key", `https://cloud.kilohearts.com`, `download.kilohearts.com`, index.json の `keyMessage`(製品別 SHA-1)。UI 文言: *"You do not have a license for this plugin. It will still work as part of this preset, but can not be edited."* / "Editing disabled" / "Invalid license. Click to open product page." 。Disperser/Faturator は旧式の `LicenseInfo` クラスと serial/evaluate 用 PNG を持つ。
  - **パッキング/暗号化はない**: `.text` entropy 6.40 (通常コード)、全 .pdata 関数を capstone で 94.2% 復号できた。AAX は Authenticode のみ。
  - **未検証**: 無ライセンス時の実際の音声挙動 (muting 等) は未実行ゆえ不明 (Windows 実機での確認が必要)。

## 4. DSP コアサイズ見積と lift 難度ランキング

方法 (`scripts/`): `callgraph.py` (全 .text を .pdata+leaf 発見で capstone sweep、直接 call/jmp 辺・SIMD 種別・IAT/間接 call を記録) → `closures.py` (root = `<ns>::{Dsp,MasterDsp,DspModel}` の全 vtable slot ≈ 26 個/ns、直接辺で到達集合、**≥8 snap-in が到達する関数を「共通基盤」として分離**) → `simd_census.py`。**間接 call は辿らない = 固有コードは下限見積**。

| 集計 | 値 |
|---|---|
| 全体 sweep | 120,856 関数 / 5,067,653 命令 / 19,382,119 B |
| SIMD 命令 (全体) | SSE スカラ 82,605 / 移動・論理 316,709 / packed FP 23,015 / packed int 19,914 / **VEX-128 7,964 / VEX-256 13,511 / FMA 1,390 / AVX-512 4,860**、cpuid 関数 10 (**snap-in closure 内は 0**; JSIMD_FORCEAVX2 文字列あり = jpeg 等 GUI 側と推定) |
| 共通基盤 (≥8 snap-in 共有) | 188 関数 / 53,010 B (うち **VEX-128+FMA の数学ライブラリ 12 関数 ≈ 22KB, 0x180fc3640 他, 無条件使用 = FMA3 前提**) |
| 効果 42 本 固有 | 計 287,610 B (中央値 ≈ 4.7KB/本)、SIMD 命令計 38,965、**mnemonic 83 種が OTT 用 m6 helper 未被覆** (census は共通基盤を除く固有 closure 対象。共通基盤 188 関数側にも未被覆 31 種があり、うち 7 種は固有側に無く、合算で 90 種) |
| ホスト | Snap Heap 50,021 B (間接 call 140) / Multipass 64,338 B (146) / Phase Plant 153,382 B (169) — **間接辺未追跡のため過小** |

VEX-256 は 344 関数 189,611 B 中 **closure 内は 6 関数のみ** (Convolver / Filter Table が各 40 命令)、**AVX-512 の 44 関数 66,171 B は closure 内 0**。VEX-128 は 359 関数中 20、FMA は 137 関数中 16 が closure 内 (数学 lib 領域 0x1802de490〜0x180fdc660)。

難度スコア = 固有 KB + SIMD 命令/100 + 未被覆 mnemonic×0.3 + 間接 call・IAT・AVX の罰則 (`make_tables.py`, `work/ranking.md` 全 45 行)。

| # | snap-in | 固有 B | SIMD | 未被覆種 | AVX/FMA | 評価 |
|--:|---|--:|--:|--:|--:|---|
| 1 | Channel Mixer (kscm) | 554 | 36 | 8 | 0 | **最小**。純 L/R マトリクス |
| 2 | **Gain (ksgn)** | 1,727 | 111 | 2 | 0 | **PoC 完了 (bit-exact)** |
| 3 | Haas (ksha) | 2,379 | 141 | 3 | 0 | 遅延 ring のみ |
| 4 | Clipper (kclp) | 2,526 | 238 | 7 | 0 | |
| 5 | Gate (ksgt) | 4,162 | 257 | 3 | 0 | |
| 6 | 3-Band EQ (ksqe) | 2,509 | 395 | 7 | 0 | biquad 3 本 |
| 7 | Resonator / 8 Stereo / 9 Disperser | 2.7K/2.8K/3.6K | 278/280/358 | 12/12/8 | 0 | |
| 10 | Formant Filter | 1,016 | 247 | 19 | 63 | FMA 数学 lib 依存 |
| 11-13 | Compressor / Reverser / Comb Filter | 3.5K/2.6K/1.8K | 366/248/425 | 9/19/16 | 26/0/0 | |
| 14-24 | Trance Gate, Phaser, Reverb, Limiter, Chorus, Ensemble, Dynamics, Dual Delay, Tape Stop, Freq Shifter, Delay | 2.8〜5.9K | 358〜1033 | 10〜28 | 0〜63 | 中位 |
| 25-35 | Transient Shaper(IAT 6), Bitcrush, Ring Mod, Compactor, Flanger, Shaper, Shaper Table, Distortion, Convolver(AVX 346), Filter, Pitch Shifter | 3.2〜10.8K | 606〜2222 | 14〜27 | 0〜346 | SIMD 量大 (Convolver の VEX-256/AVX 346 は畳込み kernel と推定) |
| 36-41 | Phase Dist., Nonlinear Filter(IAT 6), Faturator, Ladder, Slice EQ, Filter Table | 7.8〜19.2K | 1413〜2804 | 16〜43 | 0〜427 | 重い (固有コード大・SIMD 多) |
| 42 | Carve EQ | 50,109 | 2,032 | 41 | 145 | 127 関数・IAT 19 (用途未調査) |
| 43-45 | Snap Heap / Multipass / Phase Plant | 50K/64K/153K | 3.3K/4.4K/15.4K | 46/48/62 | 145〜177 | ホスト/シンセ。最難 |

## 5. 認証 blocker の切り分け (DSP 側)
- **共通基盤 188 関数を除いた**全 42 効果の固有 closure の **IAT (Win32 import) call 数**: 0 が 39 本。非 0 は Transient Shaper 6 / Nonlinear Filter 6 (SRWLock + 条件変数) / Carve EQ 19 (+ Semaphore / FormatMessageW / WideCharToMultiByte)、ホスト 3 種は各 7。**共通基盤側 (188 関数) は CRT/アロケータ/例外処理由来の Win32 import 25 種・51 call** (HeapAlloc/HeapFree, GetLastError, FLS, UnhandledExceptionFilter, RaiseException, LoadLibraryExW/GetProcAddress 等) を持ち、vector 再確保 callee `0x18004cf20` 経由で Gain の process からも到達する (wasm では malloc/abort 置換で吸収する想定 = 推定)。ライセンス/ネット系 import (WS2_32/WINTRUST/CRYPT32/SETUPAPI) は DSP closure に無い。**Gain の process 本体 (609B) は IAT 0・直接 call は 0x18004cf20 の 1 本のみ**、ライセンス/ネット参照なし。native では `HeartCore` を ImageBase に敷設しただけで **ライセンス層を一切通さず process が実行できた** (§6)。
- ゆえに「DSP カーネルの lift」と「ライセンス層の扱い」は分離可能。後者 (PACE/Eden 組込 or 非組込、ライセンス検証の方針) は法務・方針事項でありユーザ判断 (§7)。助言はしない。

## 6. PoC: `gain::GainDsp::process` → wasm (tools: `poc_gain/`)
- 対象: VA `0x1804b0380`, 609 B / 137 命令 / SSE スカラ 49・packed FP 5。仕様 (逆アセンブル): per-sample 直線 ramp ゲイン (`a+(b-a)*pos*inc`), mode==1 で 2×param, L/R 乗算, 一極 meter (x² 平滑) ×2, 変更通知 `vector<int>` push。
- パイプライン: RetDec `--select-ranges` (HeartCore 全体 PE 入力, **44.8s**, dsm 547MB は削除) → `ir_normalize`(m2)→`ir5_patch`(m5; A2/A6/A7/R1/S1a 等継承) → **`ir_kh_p1.py`** → **`ir_kh_f7.py`** → `emcc -O1 -msimd128` + `kh_simd_gain.c` (declare 駆動 14 helper 手書き) → wasm **17,355 B**。参照コピー: `poc_gain/ref/` (m2/m5/m6 から read-only コピー)。
- **発見した RetDec silent miscompile 2 種** (差分ハーネスで検出・修復):
  1. **[P1] `ucomisd` の CF が無関係な前段 cmp (this+0x78 の first-flag byte) に誤結線** → `jae` 分岐が常に同方向。fcmp で再構成 (m6 `ir6_pass.py [P1]` と同型)。
  2. **[F7] `mov r9,[r8]` の deref 欠落** → ch0 配列として `AudioBuffer*` 自体を走査 (ch1 側 `[r8+8]` は正常)。出力が 1.0 倍のブロックでは偶然一致し **meter 状態のみ破損**で顕在化。`load i64, ptr %arg3` を復元 (M9 [F7] と同型)。
- 検収 (`poc_gain.sh`): native 参照 `native_ref.c` は HeartCore の x86-64 機械語を **ImageBase 0x180000000 に VA 敷設し ms_abi 直接実行** (m5 `native_fx` 方式)。6 ブロック (first-init, ramp, 無変化, mode1+n=129, n=0, n=33) の `outL/outR/self[0xA0]/P/Q/通知 vector` が全一致 → **6/6 PASS**。
- 負の対照 (`poc_gain_negctl.sh`): 修復なし **0/6** / P1 のみ適用 (F7 欠) **0/6** / F7 のみ適用 (P1 欠) **1/6** / 両方 **6/6** (= P1 だけ外すと 1/6, F7 だけ外すと 0/6)。差分ハーネスが修復の必要性を判別できる。
- 未リフト callee: `0x18004cf20` (std::vector<int> realloc) は fail-fast stub (テストは踏まない)。DLL 実データ: abs mask `0x1813d6fc0`(16B) と定数 2 個を C/IR に転記。
- **Ghidra クロスチェック** (`RUN_GHIDRA=1`): `-noanalysis` import (76MB PE, 数分, -Xmx16g) + 範囲指定 `createFunction`+decompile で、Gain は **deref(`*param_3`) も ucomisd 比較 (`_DAT_18147d390 <= (double)fVar7`) も正しく**復元 (`work/ghidra/gain_decomp.txt`)。Delay `0x1802ed7f0` (3,291B) は 470 行。**RetDec の 2 種のバグは Ghidra decompile では発生せず、第二の oracle/代替フロントとして有用**。

## 7. ブロッカー / ユーザ依頼
1. **[方針] ライセンス層の扱い**: wasm 版に PACE iLok/Eden 認証・Kilohearts LicenseManager を載せるか、DSP カーネルのみ抽出して自前ホスト層に載せるかの決定が必要 (本報告は事実整理のみ)。外部通信 (activation / cloud.kilohearts.com) は対象外原則に従い非対象。
2. **[確認依頼]** 無ライセンス時の挙動 (muting/editing disabled の範囲)、および所有ライセンス種別 (iLok/アカウント) の共有 — Windows 実機での確認があれば難度判断が確定する。
3. 技術: (a) 未被覆 SIMD mnemonic 83 種の helper (packed FP / movddup / hadd / rcp/rsqrt / VEX-128+FMA)、(b) RetDec silent miscompile の汎用検出、(c) 共通基盤 188 関数 (53KB) と数学 lib の lift が全 snap-in 共通律速。
4. 未調査: 間接 call (vtable) 経由の closure 拡張、ホスト 3 種の IAT 7 call の用途、mac arm64 の NEON 経路比較、Installer.exe/配置先パスの動的確認。

## 8. 下流チケット案
| ID | 内容 | 規模 |
|---|---|---|
| KH-1 | **Tier-S snap-in 一括 lift**: Channel Mixer, Haas, Clipper, Gate, 3-Band EQ, Stereo の `process` を poc_gain 方式で wasm 化 (native 差分ハーネスを ctx-fuzz に汎化) | 中 |
| KH-2 | **SIMD helper declare 駆動ジェネレータ** (名称接尾 `__N` に依存しない mnemonic×型表): closure 内 SIMD mnemonic 184 種 (ホスト含む; 効果 42 本では OTT m6 helper 未被覆 83) を網羅 + VEX-128/FMA | 中 |
| KH-3 | **RetDec silent-miscompile 検出器**: capstone の memory operand / ucomis→jcc と IR の load/fcmp を関数単位照合し P1/F7 を自動修復・警告 | 中 |
| KH-4 | **SnapinMasterDsp 基底 closure (188 関数/53KB) + 数学 lib 12 関数 (≈22KB) の lift** → prepare/reset/process/param dirty 通知まで含む snap-in ホストハーネス (wasm) | 大 |
| KH-5 | Ghidra decompile (C) 経由ルートを RetDec-IR ルートと 3 snap-in で比較 (正確性/ビルド性/工数) | 小〜中 (**実施済み = §10**) |
| KH-6 | Tier-M 〜 H: Delay/Reverb/Limiter/Compressor → Ladder/Slice EQ/Filter Table/Carve EQ、最後に Snap Heap/Multipass (間接 call 追跡含む) | 大 |
| KH-7 | UI: Skia CPU ラスタ → M7 フレーム転送 HUD への接続可否 (Skia は upstream 再ビルド、HeartCore の Editor 層は別途) | 大・低優先。**評価済み (#59): 接続形は成立・shim/フォント側に未達あり → `ui_eval/REPORT.md`** |
| KH-8 | ライセンス方針決定後: LicenseManager/PACE 層の置換設計 | 要判断 |

## 9. 成果物 (§10 = `ghidra_route/` は §10 末尾)
`ghidra_route/` (KH-5, §10), `scripts/{extract_installer.sh,pe_info.py,rtti_walk.py,callgraph.py,closures.py,simd_census.py,make_tables.py,ghidra/DecompAt.java}`, `poc_gain/{native_ref.c,ir_kh_p1.py,ir_kh_f7.py,kh_simd_gain.c,poc_gain.sh,poc_gain_negctl.sh,poc_gain_compare.mjs,ref/}`, `run_all.sh`。`work/` (gitignore): `ranking.md, closures.json, simd_census.json, tables.txt, rtti_vtables.json, ghidra/gain_decomp.txt, blobs/index.json` ほか。

## 10. KH-5 (#58, 2026-10-13): Ghidra decompile→C→emcc ルート vs RetDec→kh_lower ルート (Gain / Haas / Gate)
- 再現: `bash tools/targets/kilohearts/ghidra_route/run_all.sh 1000 7` (HeartCore 抽出済み・`[GHIDRA]` (12.1.4)・`[RETDEC]`・`[EMSDK]` (いずれも `docs/REFERENCES.md` のエントリ ID)・pefile/capstone が前提)。両ルートとも**同一の ctx-fuzz ベクタ** (`snapins/harness`, 1000 trial / seed 7, 実機 x86 機械語を ImageBase 敷設して ms_abi 直接実行) を `compare.mjs` で**全バイト strict 突合**。実測環境: GitHub runner 4 vCPU・RAM 15GB。
- **結論**: 3 本 (スカラ・単純 leaf) では Ghidra ルートも **1000/1000 bit-exact に到達**するが、**修復なし (型 shim + グローバル実データ + callee stub のみ) では 1 / 17 / 0 (Gain/Haas/Gate, /1000) で FAIL** し、修復は機械書換え 4 種 + 手パッチ規則 (`assoc`) 4 行が要る。RetDec ルートは修復を run 内の pass が自動で行い 3 本とも 1000/1000。**主ルートは RetDec→kh_lower を維持し、Ghidra は第二の oracle (仕様の突合・RetDec が誤る箇所の独立確認) に留める**。理由は §10-4 (SIMD/128bit/独自 ABI の関数では C 化の手作業が増える) と §10-2 (silent 類型が Ghidra 固有に 5 種)。

### 10-1. 3 snap-in の実測 (1000 trial, seed 7)
| snap-in | Ghidra 素の出力 | Ghidra + 全修復 | wasm | RetDec→kh_lower | wasm |
|---|---|---|---|---|---|
| Gain (1 関数) | 1/1000 | **1000/1000** (4999/4999 call) | 15,161 B | **1000/1000** (4999/4999) | 23,054 B |
| Haas (5 関数) | 17/1000 | **1000/1000** (5500/5500) | 16,878 B | **1000/1000** (5500/5500) | 35,967 B |
| Gate (3 関数) | 0/1000 | **1000/1000** (4999/4999) | 17,367 B | **1000/1000** (4999/4999) | 45,754 B |

- 「素の出力」= §10-2 の `修復なし` 行 = 常時入れる最小限 (Ghidra 型名 shim・`_DAT_` の PE 実データ定義と C 型推定・callee stub) だけで build し `--fix` 規則は 0 件。build は通るが数値が狂う (silent)。なお型推定を入れる前の最初の試行 (全グローバルを float 扱い) は `uint & float` の型エラーで 3 本とも emcc 失敗した。
- wasm サイズは非対称な比較: RetDec 側は SIMD helper・globals 窓・stubs・96MB メモリ前提の共通部品を含む。Ghidra 側は C 1 本のみ。

### 10-2. 修復の要否 (ablation: 全修復 / 1 種外し / なし。数字 = bit-exact trial 数 / 1000)
| 構成 | Gain | Haas | Gate |
|---|---|---|---|
| 全修復 | 1000 | 1000 | 1000 |
| 修復なし | 1 | 17 | 0 |
| −bitcast | 30 | 140 | 0 |
| −intload | 7 | 1000 | 1000 |
| −assoc | 162 | 759 | 68 |
| −concat | 1000 | 330 | 1000 |
| −stackpair | 1000 | 1000 | 644 |
- **すべて silent miscompile (build は通り数値だけ狂う)**。類型 (RetDec の P1/F7 とは**別の類型**。Ghidra では P1 (ucomisd 条件の誤結線)・F7 (`mov r9,[r8]` の deref 欠落) は 3 本とも発生しなかった = §6 の Ghidra クロスチェックの再確認):
  - **bitcast**: abs マスク `(float)((uint)x & MASK)` を C の数値変換として書く (実際はビット再解釈)。グローバル `0x1813d6fc0` を float/uint のどちらに型付けするかも Ghidra は一定でなく、C 化側の型推定 (`infer_type`) が要る。
  - **intload**: float フィールドを `(int **)p)[1]` で読み `(float)` で包む (数値変換になる)。
  - **concat**: `CONCAT44(hi, fVarN)` の float 引数が数値→uint 変換になる (ビット連結の意図が崩れる)。
  - **assoc**: 浮動小数の積の結合括弧を印字で落とす (`a*(b*c)` が `a * b * c` = C では左結合 `(a*b)*c` → 1 ulp ずれる)。**実機の演算順を逆アセンブルで確認しないと直せない** (Gain 1804b0473..0485 の ramp、Gate 1804c3494..34a7 の smoothstep)。native との差分ハーネスが無いと発見不能。
  - **stackpair**: 連続した 2 スタック変数 (`lStack_e8/e0`) を配列として渡す呼出 (Gate の look-ahead ペア) が `&lStack_e8` 1 個になる。
- **手作業の実績** (`patches.py` の規則行 = 手作業 1 件): `assoc` 規則 4 行 (Gain 1・Haas 1・Gate 2。ramp 形の正規表現 1 本が Gain 1・Haas 2・Gate 1 の計 4 site、Gate の smoothstep 1 site を覆う = 計 5 site)。機械書換え 4 種 (bitcast/intload/concat/stackpair, `ghidra_to_c.py --fix`)。人手の所要時間は計測していない (推定は書かない)。比較用の実測は各段の実測秒 (§10-3)。
- 修復の**発見**には RetDec stage-0 + kh_lower ルート (比較相手。`snapins/REPORT.md` §0・§2) と同じ native 差分ハーネスが不可欠 (Ghidra の出力が正しいかの判定は読むだけでは付かない = RetDec と同じ条件)。

### 10-3. 実測秒 (コミット済み HEAD c4841f4 で `run_all.sh 1000 7` を連続 n=3 回, min–max。runner 4 vCPU・run_all.sh は逐次実行。c4841f4 以降の差分は REPORT.md のみ)
| 段 | 実測 wall (min–max) | load (1/5/15 分) の min–max |
|---|---|---|
| Ghidra import (76MB PE, `-noanalysis`) + 10 関数 decompile (lift 対象 9 = Gain 1 + Haas 5 + Gate 3、stub 化する callee 1 = `0x18004cf20`) | 23.2–38.2 s | 1.14–1.50 / 0.64–1.07 / 0.31–0.56 |
| 同 (census 対象 10 関数 = snap-in process 7 + libm 3, §10-4) | 24.1–24.9 s | 1.31–1.51 / 0.83–1.19 / 0.41–0.66 |
| Ghidra 出力 → C 化 → emcc → 突合: Gain / Haas / Gate | 0.7–1.3 / 0.8–1.1 / 1.0–1.4 s | 1.13–1.50 / 0.64–1.07 / 0.31–0.56 |
| RetDec stage-0 (冷間) + kh_lower + emcc + 突合: Gain / Haas / Gate | 13.6–13.9 / 13.8–14.0 / 14.2–14.4 s (うち RetDec 取得 11.5–11.6 s) | 1.11–1.59 / 0.71–1.15 / 0.35–0.63 |
- 3 回とも exit 0。判定は 3 回とも同一: Ghidra 全修復 1000/1000 ×3 (wasm 15,161 / 16,878 / 17,367 B)・RetDec 1000/1000 ×3 (23,054 / 35,967 / 45,754 B)・§10-2 の ablation 21 構成は全値一致。
- 変動が大きい: Ghidra import の最大値 38.2 s は 1 回目 (23.7 s / 23.2 s が 2・3 回目。原因は未検証)。前版の n=1 値 (Ghidra 18.8 s・RetDec 10.1〜10.6 s, HEAD bc62138) は本表で置換した。別 runner での検収 run (PR #475 の review, HEAD 63b145d) の値は Ghidra 25.0 / 25.8 s・RetDec 13.3 / 13.5 / 13.9 s で、前版より長い。
- `[wall … | load …]` 行の取得場所: [4] の RetDec 側と [3] の C 化は console に出る。[2] と [5] (Ghidra 2 段) は `run_all.sh` が `> run.log 2>&1` で束ねるため console に出ず、`work/ghidra/run.log` (lift 対象 decompile)・`work/ghidra/run2.log` (census) の末尾に入る。
- Ghidra は時間が import (PE 読込) に支配される。decompile 本体は関数ごとの `decomp_sec` の合計が lift 対象 0.26 s・census 0.92 s (3 回目の `work/ghidra/out/summary.tsv`・`out_simd/summary.tsv`, n=1)。RetDec 取得は Gain (1 範囲)・Haas (5 範囲)・Gate (3 範囲) で 11.5–11.6 s と差が見えない。素材取得なしの同一 runner での値。

### 10-4. SIMD / 128bit / ABI の扱い (census 対象 10 関数 = snap-in process 7 [Resonator / Stereo / Delay / Phaser / Limiter / 3-Band EQ / Channel Mixer] + libm 3 [powf / sincos_a / k_dfdb0] の decompile、`census.sh`。**C 化・ビルドは未実施 = 構文の有無のみ**)
- Ghidra は 10 関数すべて decompile 完了 (関数ごとの decompile 0.01〜0.24 s は 3 回目の `out_simd/summary.tsv` の値で n=1、53〜470 行は `census.sh` の `wc -l`)。ただし C として意味を持たない構文が残る:
  - **SIMD 疑似関数**: Resonator `rcpps(in_XMM2, …)`・Stereo `rsqrtps(in_XMM3, …)` (各 1)。C に等価物が無く、`snapins/REPORT.md` §13 の実機近似表移植 (bit-exact 化) が別途要る。
  - **128bit 整数演算**: k_dfdb0 (Payne-Hanek) `SUB168(auVar2 * auVar4,8)` 等 3、Phaser 4・Limiter 2・Delay 1。C の `__int128` 化が要る。
  - **レジスタ渡しで引数なしの呼出** (`FUN_xxx()` / `func_0x…()`): Delay 4・Phaser 5・sincos_a 4・powf 1。MS x64 ABI でない独自呼出規約の libm 部品で、**引数・戻りを手で復元**しないと C にならない。sincos_a は `extraout_XMM0_Qa` を 6 個持つ (戻り値以外のレジスタ値の受け渡し)。
- RetDec→kh_lower はこれらを既に処理済み (`snapins/REPORT.md` §15: 13 snap-in + khbase (共通基盤) の計 14 本が 1000 trial / seed 7 で全件 bit-exact。上記 census の 10 関数のうち snap-in process 7 本はこの 13 snap-in に含まれ、libm 3 本は 3-Band EQ の lift 対象 = `snapins/snapins.json` の quickeq.lift)。Ghidra ルートで同じ範囲を C 化するには 3 本の実績より桁違いに手作業が増える見込みだが、**実ビルドはしていないので推定**。
- 未解決 (Resonator / Stereo / Delay の Ghidra 実ビルド・突合 = `rcpps` 表・128bit・ABI 復元の規則化が前提) は §10-6。

### 10-5. 判断への含意
- **フロント選択**: 主ルート = RetDec→kh_lower (維持)。Ghidra→C は (a) 3 本程度の単純 leaf では全修復後に同等の bit-exact を達成でき、(b) RetDec の P1/F7 を誤らない独立実装として**第二 oracle に有用** (今回 3 本で再確認)。一方、(c) 修復のための silent 類型 5 種 (bitcast/intload/concat/assoc/stackpair。うち手作業が要るのは assoc のみ) は Ghidra 固有で、(d) SIMD/128bit/独自 ABI の関数では C 化の手作業が要る。
- **KH-3 (検出器) の優先度**: Ghidra を主ルートにしない限り KH-3 の対象は RetDec 側 (D14〜D16 / 既存検出器) のまま。Ghidra を第二 oracle に使う場合は、capstone の演算順/型と C 式の照合 (assoc・bitcast 類型) が要る — ただしこれは oracle 用途なら不要 (native 差分で検出できる)。**優先度の変更は提案しない**。決定は PM。
- 成果物: `ghidra_route/{ghidra_to_c.py,patches.py,ghidra_shim.h,build_cmp.sh,ablate.sh,census.sh,run_all.sh}`, `scripts/ghidra/DecompEach.java`。`work/` (gitignore): `ghidra/out{,_simd}/`, `gr/<name>/`。

### 10-6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Resonator の emcc 失敗 (128bit レーン・rcpps 近似表・プロトタイプ・stub) | 受入条件 1〜4 (実ビルド・突合・ネガコン・結論) が全て未達 | #556 (本 PR は `Refs #556`) |
| Stereo / Delay の Ghidra 実ビルド・突合は未実施 (rsqrtps・sincos_a の引数なし呼出・k_dfdb0 の 128bit 演算。`rcpps` 表・128bit・ABI 復元の規則化が前提)。§10-4 の「手作業が桁違いに増える」は census (構文の有無) に基づく推定のまま | 受入条件 1〜4 未達 | #556 (OPEN)。子チケット案 `[KH-5b]` の親は #58 (CLOSED) のため、親の付け替えは PM 判断。起票は PM |
| 人手の所要時間 (Ghidra ルートの修復工数) は未計測。記録したのは手パッチ規則の件数 (§10-2) と各段の実測秒 (§10-3) のみ | #58 受入条件「工数」を人手時間では比較できていない (#58 は 2026-10-13 に CLOSED) | #556 (OPEN) に追跡を付け替え。再 open の要否は PM 判断 |
| KH-3 優先度とフロント選択の決定 | 材料は §10-5 のみ。決定が無いため PR は `Closes` でなく `Refs #556` (`#58` は CLOSED) | PM 判断 (追跡先は PM 指定) |

### 10-7. KH-12 (#556) 途中経過: Resonator / Stereo / Delay の Ghidra 実ビルド (部分)
- 環境: Ghidra 12.1.4 = GitHub release `Ghidra_12.1.4_build` の `ghidra_12.1.4_PUBLIC_20260921.zip` (570 MB, sha256 `ddac49f9…d2db`)、JDK 21、`GHIDRA_HOME` で指定。素材 `plugins-kilohearts` は Installer (zip/dmg) で、`scripts/extract_installer.sh` が HeartCore を抽出 (3m34s)。
- 関数集合 (`snapins.json` の `lift` 値 + `extra` の和): Resonator 7 / Stereo 8 / Delay 141 (= lift 値の一意アドレス数 `len(set(lift.values()))`。Delay は 142 キーのうち `proc` と `f_1802ed7f0` が同一アドレス `1802ed7f0` で重複 1)。`DecompEach.java` で 156 関数を decompile し **156 件 OK** (summary.tsv の status 集計 = OK 156・失敗 0)。3 snap-in 合計の decompile は headless import 込みで 31.3 s (n=1)。
- Resonator の C 化 (`ghidra_to_c.py resonator`、修復なし) は **ビルド未成功 (emcc 失敗)**。エラー 21 件以上・先頭 10 件の種類: 128bit レーン参照 `_8_8_`/`_4_12_`/`_0_8_` が V128 に無い 3 種、`rcpps` 未実装、`FUN_180fcf904` の引数不一致、`func_0x000180fbdef4` 未定義 stub 等。このため突合・ablation・ネガコンは未実施。
- 未実施 (理由: 128bit レーン・rcpps/rsqrtps 近似表 (`snapins/scripts/approx_tables.b64`) の C 移植・プロトタイプ整合・stub 追加が未完)。
- `run_all.sh` (Gain/Haas/Gate) は本 PR では再実行していない。値は §10-3 (c4841f4, n=3) を引用。

#### 10-7b・10-7c (#556 2 回目・3 回目 run の経緯) は付録 `REPORT_APPENDIX.md` §10-7b・§10-7c へ分割移動 (250 行上限)。

#### 10-7d. #1215 (KH-23) 1 単位: V128 の 128bit レーン型を shim で解消
- 環境: Ghidra 12.1.4 = GitHub release `Ghidra_12.1.4_build` の zip (sha256 `ddac49f9…d2db` 一致)、JDK 21。素材は `plugins-kilohearts` の Installer zip → payload.dat → windows.zip → HeartCore.core_64。emsdk は `[EMSDK]` (6.0.12)。
- 変更: `ghidra_shim.h` の `V128` に `_0_8_`・`_8_8_` (uint64) と `_4_12_` (12 byte) のレーンを追加 (commit は本 PR)。
- emcc (resonator, 修復なし, `-ferror-limit=0`, 同一条件): 旧 shim 22 行 (`_8_8_`/`_4_12_`/`_0_8_` 由来 8 件) → 新 shim 18 行 (そのレーン由来 0 件)。
- 残件 (emcc): (a) テーブル `UNK_182280000`・`UNK_182280020` が未定義 (`pe_bytes` は 1 グローバル 16 byte しか読まない)、(b) 未関数化 callee `func_0x000180fd648c`・`func_0x000180fd6498`・`func_0x000180fd662c`・`func_0x000180fbdfcc`・`func_0x000180fbdef4`・`FUN_180fe5f40`・`FUN_180fd3144`、(c) `rcpps` の 2 引数形 (戻り値形の helper を生成。突合は REPORT_APPENDIX §10-7o)、(d) 引数なし呼出の `param_1` 不足 (件数の正本は REPORT_APPENDIX §10-7o を参照)。
- Resonator のビルドは**依然失敗**。突合・ablation・ネガコンは未実施。
- 回帰確認 (新 shim・同一 HEAD): Gain 1000/1000 (wasm 15,161 B)・Haas 1000/1000 (16,878 B)・Gate 1000/1000 (17,367 B)。wasm サイズは §10-3 の値と一致。Ghidra decompile は 10 関数すべて OK。突合の実測秒は未計測 (emcc 0.2〜0.3 s)。

#### 10-7e. #1215 (KH-23) run: UNK 表の byte 領域化と callee 追加 (部分)
- 素材: `plugins-kilohearts` (Installer zip) → payload.dat → windows.zip/1ccb1df8c8f10745 → HeartCore.core_64 (手展開)。Ghidra 12.1.4 = `Ghidra_12.1.4_build` の zip, sha256 `ddac49f9…d2db` 一致、JDK 21 (Temurin)。emsdk 6.0.12。
- 変更 (`ghidra_route/ghidra_to_c.py` のみ): (1) `&UNK_<va>` を参照する範囲 (`0x182280000`〜) を `gt_<base>` の byte 配列として PE `.rdata` から読み、参照を `((unsigned char*)gt_<base> + off)` に書換える。従来の 16 byte 単位の `_UNK_` 定義では表が uint 1 個として展開され、`UNK_182280000` が未定義だった。(2) `resonator.also` に 4 件を追加 (`0x180fd6498` `0x180fd662c` `0x180fe5f40` `0x180fd3144`)。計 16 件。
- Ghidra decompile (Resonator + also 16 件 = 17 関数): 17 件すべて OK (summary.tsv, import 込み 31.7 s wall, n=1)。
- emcc (resonator, 修復なし, `-ferror-limit=0`): **依然失敗**。`UNK_182280000`・`UNK_182280020` は消えた。残件は下表 (件数は 1 run の実測)。

- 残件の内訳と件数は REPORT_APPENDIX §10-7k の 1 箇所に置く (本節の値は古い基準のため採らない)。起票先は #1405。
- `func_0x…6498`・`func_0x…662c` は 10-7e で `also` に追加した callee。残件の `func_0x` 表記は、converter (`ghidra_to_c.py`) が `func_0x` 呼出名を書換える処理を持たないことから、呼出名が未解消のまま残っていると読める。定義側 (`FUN_<va>`) との名前の一致は実測していないため未確認。

- 回帰確認 (同一 HEAD・同一 shim): Gain 1000/1000 (wasm 15,161 B, emcc 0.75 s)・Haas 1000/1000 (16,878 B, 0.65 s)・Gate 1000/1000 (17,367 B, 0.66 s)。`compare.mjs` の結果は `bit-exact` 3 件とも全件一致。Gain/Haas/Gate の decompile は `--fix bitcast,intload,stackpair,assoc,concat` で C 化し直した (別 decompile 集合 `out_reg`)。
- Resonator の突合・ablation・ネガコンは未実施 (emcc 未通過のため)。
- 起票: 残件 → #1405 [KH-25]。Stereo / Delay → #1216 [KH-24]。

#### 10-7f. #1405 (KH-25) run: 残件の再現と callee 閉包の試行 (未達・コード変更なし)
- 再現 (main 851c342e・`resonator` 修復なし・`-ferror-limit=0`): emcc error 28 件 (#1405 表と一致)。素材 `plugins-kilohearts` → Installer zip → payload.dat → windows.zip → HeartCore.core_64、Ghidra 12.1.4 (sha256 一致)、emsdk 6.0.12 は素材の `toolchain-emsdk`。
- 試行: `also` に `FUN_180fd4f30`・`FUN_180fd51cc`・`FUN_180fd2d38` を追加 → decompile 20 件 OK (error 件数は未集計)。さらに `FUN_180fd2c90`・`FUN_180fd2c10`・`FUN_180fd1ac4`・`func_0x…e5c6c`・`func_0x…b6c0c` を追加 → decompile 25 件 OK、error 38 件 (`grep -c error:`)。新たに未解決 `func_0x…1f84`・`1f30`・`FUN_180fd2f20`・`FUN_180fd1b00`・`LOCK`/`UNLOCK`・`HeapAlloc`/`HeapFree` が出現。閉包は収束しなかったため、converter の変更は破棄 (コミットなし)。
- 逆アセンブル (capstone, IAT 判定): `func_0x…81e4`・`81ec` は `jmp [rip+…]` の IAT thunk (Win API 経由)。`func_0x…bdfcc`・`648c`・`662c`・`bdef4` は通常の関数先頭。`func_0x…1f84`・`1f30` は `movsxd` で始まる通常関数。thunk は関数名の書換えでなく Win API stub として扱う必要がある。
- 結論: callee を Ghidra 出力どおり `also` に足す方式は閉包が広がるだけで、emcc は改善しない。次 run は (a) IAT thunk を stub 化する規則、(b) `LOCK`/`UNLOCK`・`MXCSR` の意味付け、の 2 点を先に決める。

#### 10-7g. #1215 (KH-23) 再 run: 呼出名 `func_0x…` の統一 (部分)
- 結論: `ghidra_to_c.py` の呼出名統一で emcc error 31 → 25 件。Resonator は依然未通過。Gain/Haas/Gate 1000/1000 bit-exact (回帰なし)。詳細と実測は付録 `REPORT_APPENDIX.md` §10-7g。
- #1405 (KH-25) の 1 単位: `rcpps` 代入形の固定と converter ガード、`GetLastError`/`SetLastError` の stub。Resonator は依然未通過。Gain/Haas/Gate 1000/1000 bit-exact。件数・実測・測定 commit は付録 `REPORT_APPENDIX.md` §10-7o。

#### 10-7q. #3072 (KH-40) run: Delay の Ghidra 変換 (型名・LOCK・Win API stub・thunk 正規化) (部分)
- 結論: Delay の lift 141 関数 decompile OK。thunk 正規化を列 0 の定義行だけに限定 (本体の自己呼出しを解消、旧版は 1 関数で発生)。emcc clang 診断 **601 件** (測定 commit `7d1d0e2e`。旧記載の 526 は再現せず)。LOCK/UNLOCK は no-op (単一スレッド)、Win API 21 件は fail-fast stub。Gain/Haas/Gate 1000/1000 bit-exact (回帰なし)。残件 601 件の内訳と起票先は付録 `REPORT_APPENDIX.md` §10-7q。
