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
2. [ ] ブラウザ実行戦略の設計と技術選定 (shim 一覧付き)
   - [x] 調査完了 (`analysis/strategy_survey.md`)。lifter (RetDec/mcsema) → LLVM IR → wasm が現実解
   - [x] ツールチェイン整備 + E2E PoC 成功 (`analysis/toolchain_setup.md`)。x64 ELF / x86_64 PE → RetDec → emcc → wasm で出力一致
   - [ ] 戦略文書 (選定理由・制約・リスク・shim一覧) の確定
3. [ ] webstudio リポジトリへの段階的実装

## 開発

```sh
pnpm install
pnpm dev
```
