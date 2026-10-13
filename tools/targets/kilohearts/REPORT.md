# Kilohearts (HeartCore 2.4.6 / release 132102) インストーラ解析 + snap-in lift 可否 (target 事前解析)

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
| KH-5 | Ghidra decompile (C) 経由ルートを RetDec-IR ルートと 3 snap-in で比較 (正確性/ビルド性/工数) | 小〜中 |
| KH-6 | Tier-M 〜 H: Delay/Reverb/Limiter/Compressor → Ladder/Slice EQ/Filter Table/Carve EQ、最後に Snap Heap/Multipass (間接 call 追跡含む) | 大 |
| KH-7 | UI: Skia CPU ラスタ → M7 フレーム転送 HUD への接続可否 (Skia は upstream 再ビルド、HeartCore の Editor 層は別途) | 大・低優先。**評価済み (#59): 接続形は成立・shim/フォント側に未達あり → `ui_eval/REPORT.md`** |
| KH-8 | ライセンス方針決定後: LicenseManager/PACE 層の置換設計 | 要判断 |

## 9. 成果物
`scripts/{extract_installer.sh,pe_info.py,rtti_walk.py,callgraph.py,closures.py,simd_census.py,make_tables.py,ghidra/DecompAt.java}`, `poc_gain/{native_ref.c,ir_kh_p1.py,ir_kh_f7.py,kh_simd_gain.c,poc_gain.sh,poc_gain_negctl.sh,poc_gain_compare.mjs,ref/}`, `run_all.sh`。`work/` (gitignore): `ranking.md, closures.json, simd_census.json, tables.txt, rtti_vtables.json, ghidra/gain_decomp.txt, blobs/index.json` ほか。
