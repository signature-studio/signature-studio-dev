# tools/ipp STATUS

状態: **完了** (評価 + 最小実装 PoC)。`bash tools/ipp/ipp_e2e.sh` が exit 0 / 12 checks PASS。詳細は REPORT.md。

- 結論: IPP 本体 (win 39.9MB / mac 33.8MB) の lift は不要。FL 自身が arm64 mac で 0.4MB の別実装を出荷。ただし IPP **API** は全 platform で ~239 関数必要 → 案C (必要関数のみ C 自前→emcc) を推奨。
- 実装済 43 関数 (24 を実 Intel IPP と差分: 21 bit-exact [NaN ペイロード差は除く] / FFT は NRMS 32f≤1.5e-7・64f≤6.6e-16) + 420 名 lookup 表 (未実装は fail-fast stub)。wasm 46KB。
- 未着手: 残 ~190 関数、呼出規約 thunk (MS x64 ABI xmm 引数)、FFT の pffft 化、動的実使用の採取、VectorSlope の bit 再現。
