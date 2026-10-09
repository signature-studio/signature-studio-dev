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
2. [ ] ブラウザ実行戦略の設計と技術選定 (shim 一覧付き)
3. [ ] webstudio リポジトリへの段階的実装

## 開発

```sh
pnpm install
pnpm dev
```
