# WebStudio

FL Studio 26.1.7 をブラウザ上で完全に動作させることを目標とするプロジェクト。

## 戦略 (第一目標)

**デコンパイル → 最小変更で wasm 化**

- FL Studio 本体 (FL64.exe / macOS Mach-O) を解析し、ソース復元→Emscripten 等で WebAssembly 化する
- ネイティブ依存 (DirectSound / ASIO / ALSA / Win32 FS / ウィンドウシステム等) は **shim 層** でブラウザ API (Web Audio API / Emscripten FS / WebGL キャンバス) に吸収する
- FL 側のソース変更は最小限に留め、upstream の変更を追跡可能にする

詳細な解析レポート: `/home/ubuntu/work/analysis/win64/REPORT.md`, `/home/ubuntu/work/analysis/mac/REPORT.md`

## 進捗フェーズ

1. [ ] FL Studio 26.1.7 インストーラ解析 (win64 exe / mac dmg)
   - [x] mac dmg: 展開→分析完了 (`analysis/mac/REPORT.md`)。核心は `FLEngine_x64.dylib` (64MB, universal2)
   - [ ] win64 exe: NSIS系インストーラを作成ツールで抽出中 (`analysis/win64/REPORT.md`)
2. [x] ブラウザ実行戦略の設計と技術選定 (shim 一覧付き)
   - [x] 調査完了 (`analysis/strategy_survey.md`)。lifter (RetDec/mcsema) → LLVM IR → wasm が現実解
   - [x] ツールチェイン整備 + E2E PoC 成功 (`analysis/toolchain_setup.md`)。x64 ELF / x86_64 PE → RetDec → emcc → wasm で出力一致
   - [x] 戦略文書確定 (`analysis/strategy.md`)。技術選定・実行パイプライン・shim 12 行・マイルストーン M1〜M11・リスク/工数 (2〜4人年)・EULA 制約。プラグイン路線: プロプライエタリ製品 (Serum 2 / Massive X / OTT 最重視 / Fresh Air / Kilohearts) をデコンパイル→lifter→wasm 化して同梱
3. [ ] webstudio リポジトリへの段階的実装
   - [x] 最小ハーネス雛形: Vite + 全画面 Canvas + AudioWorklet (128f) + SharedArrayBuffer リングバッファ、COOP/COEP 有効化。`pnpm dev` / `pnpm build` 検証済 (commit ff5d727)

## 開発

```sh
pnpm install
pnpm dev
```
