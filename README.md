# WebStudio

FL Studio 26.1.7 をブラウザ上で完全に動作させることを目標とするプロジェクト。

## 戦略 (第一目標)

**デコンパイル → 最小変更で wasm 化**

- FL Studio 本体 (FL64.exe / macOS Mach-O) を解析し、ソース復元→Emscripten 等で WebAssembly 化する
- ネイティブ依存 (DirectSound / ASIO / ALSA / Win32 FS / ウィンドウシステム等) は **shim 層** でブラウザ API (Web Audio API / Emscripten FS / WebGL キャンバス) に吸収する
- FL 側のソース変更は最小限に留め、upstream の変更を追跡可能にする

詳細な解析レポート: `/home/ubuntu/work/analysis/win64/REPORT.md`, `/home/ubuntu/work/analysis/mac/REPORT.md`

## 進捗フェーズ

1. [x] FL Studio 26.1.7 インストーラ解析 (win64 exe / mac dmg)
   - [x] mac dmg: 展開→分析完了 (`analysis/mac/REPORT.md`)。核心は `FLEngine_x64.dylib` (64MB, universal2)
   - [x] win64 exe: NSIS+Image-Line 独自拡張を自作パーサで抽出→分析完了 (`analysis/win64/REPORT.md`)。実体は `FLEngine_x64.dll` (22.27MB, Delphi)、FL64.exe は薄いランチャ
2. [x] ブラウザ実行戦略の設計と技術選定 (shim 一覧付き)
   - [x] 調査完了 (`analysis/strategy_survey.md`)。lifter (RetDec/mcsema) → LLVM IR → wasm が現実解
   - [x] ツールチェイン整備 + E2E PoC 成功 (`analysis/toolchain_setup.md`)。x64 ELF / x86_64 PE → RetDec → emcc → wasm で出力一致
   - [x] 戦略文書確定 (`analysis/strategy.md`)。技術選定・実行パイプライン・shim 12 行・マイルストーン M1〜M11・リスク/工数 (2〜4人年)・EULA 制約。プラグイン路線: プロプライエタリ製品 (Serum 2 / Massive X / OTT 最重視 / Fresh Air / Kilohearts) をデコンパイル→lifter→wasm 化して同梱
3. [ ] webstudio リポジトリへの段階的実装
   - [x] 最小ハーネス雛形: Vite + 全画面 Canvas + AudioWorklet (128f) + SharedArrayBuffer リングバッファ、COOP/COEP 有効化。`pnpm dev` / `pnpm build` 検証済 (commit ff5d727)
   - [x] M1: 極小 PE→wasm PoC の自動化 (`tools/m1/m1.sh`)。ELF/PE32+ → RetDec → main 抽出 → emcc (定型フラグ) → wasm → node 出力一致を 1 コマンドで検証・再生産可能化 (`tools/m1/README.md`)
   - [x] wasm ローダ glue: `src/runtime/loader.ts` (fail-fast import フォワーダ `src/runtime/imports.ts` 付き)。`pnpm typecheck`/`pnpm build` + node スモーク (M1 wasm をロードし出力照合) 検証済 (commit fe2f442)
   - [x] M2: FLEngine 解析の機械化 (`tools/m2/m2.sh`)。mac x86_64 スライス抽出 (31,637,920B / `__text` 17,656,574B)、関数境界合意検証 (win: Ghidra 59,009 vs .pdata 57,816 → delta 2.02%、mac: LC_FUNCTION_STARTS 99.5% Jaccard)、Delphi 品質インベントリ生成 (`delphi_inventory.py`, VMT/RTTI/FastMM/SEH)、shim 自動照合 (`SHIM_INVENTORY.md`)。EasyFLAC `_FLAC__crc8` (299KB → wasm) は **bit-exact 6/6**、RetDec による Delphi (embarcadero 36.0) 検知確認 (`tools/m2/REPORT.md`, commit 7e72717)
   - [ ] M3: 中規模 lifting → wasm **(部分達成)**: 純計算 4 関数 (EasyFLAC) を bit-exact **50/50** で wasm 化 (`tools/m3/m3.sh`)、性能比記録済 (同一 IR native vs wasm: crc8 1.44x / crc16 1.33x, 10x 未満)。中規模 Delphi closure (677 関数) は RetDec 産 constexpr 残存 (`ft7.ll:4281`) で emcc 未通過 — **A9 命令化 lift が次の要 IR pass** (`tools/m3/REPORT.md`, commit 7afa0fd)
   - [ ] M5: Delphi Mini-PoC **(部分達成)**: 純計算 2 関数 (waveshaper/distortion) の lift IR→wasm が実機 x86 機械語と **bit-exact (8/8)**、FastMM lift を shim heap に結合し alloc/free 1,000/1,000・double-free fail-fast 検知・underflow リーク検知を実証。A9 命令化 pass で Delphi closure 677 関数の constexpr 残存 187→**2**件に圧縮し **677 関数 closure 全体が emcc 通過**。try-finally lift 実測は finally 経路整合 (ParamCount off-by-one は既知課題) (`tools/m5/REPORT.md`, commit 4aa68a2)
   - [x] M4: Win32 shim コア `tools/shim/` (timer/file/thread/heap, fail-fast)。53 export API を MT(pthread)/ST 両ビルドで node 単体テスト全 PASS (4スレッド×10k 排他/TLS 分離/byte-faithful file I/O 検証済, commit 1c49c61)
   - [ ] M6: プラグイン路線 PoC — OTT (Xfer) VST2 win64 DSP クロージャ 166 関数の RetDec lift→IR pass (**部分達成**, commit 2607a2e): ir5 継承 pass (A9 残存 5 件) + comis 修復 18 + VA remap 38 + DLL 実データ化 global 400 件を経て **emcc ビルド通過** (wasm 825KB / 関数 533)。実行検証は未達 — m6 helper 156 種の `msimd6_core.h` が空のため `__asm_*` 署名不一致 12 種 → lld が unreachable stub を生成し ctor 即 trap。**helper 接続が次の最優先課題**。m6.sh 1 コマンド E2E 化は M7 引継。(`tools/m6/REPORT.md`)

## デプロイと E2E 検証 (指揮要件)

- **目標**: 任意のホスト URL を開くと FL が立ち上がる状態。E2E 検証は `agent-browser` で自動化する (メインセッションの指揮範囲に含む)。
- **ホスティング**: Cloudflare R2 + Workers (`cf` / `bunx wrangler` 導入済み)。Cloudflare Access による保護を前提とする。
- **Secure Context の制約** (GitHub Pages 不採用の根拠): SharedArrayBuffer は cross-origin isolation (COOP/COEP レスポンスヘッダ) が必須。GitHub Pages はカスタムヘッダを設定できないため SAB が無効化される。→ Workers 側で COOP/COEP ヘッダを注入し、R2 から配信する構成を採る。
- 実配信はアプリが動作する段階 (M7 以降) で着手。先行の Node/ローダ検証はローカルで継続。

## 開発

```sh
pnpm install
pnpm dev
```
