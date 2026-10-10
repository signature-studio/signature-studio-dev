# tools/ipp STATUS

状態: **完了** (評価 + 最小実装 + 優先 stub 充填 + FFT pffft 化 + Resize/GetBufSize 実測式)。`bash tools/ipp/ipp_e2e.sh` が exit 0 / 12 checks PASS、`bash tools/ipp/shim/shim_e2e.sh` が exit 0 / **12 checks PASS** (S10/S11 は CAB-245 オラクル)、`bash tools/ipp/shim/fft/fft_e2e.sh` が exit 0。詳細は REPORT.md / shim/REPORT.md / shim/fft/REPORT.md。

- 結論: IPP 本体 (win 39.9MB / mac 33.8MB) の lift は不要。FL 自身が arm64 mac で 0.4MB の別実装を出荷。ただし IPP **API** は全 platform で ~239 関数必要 → 案C (必要関数のみ C 自前→emcc) を推奨。
- 実装済: **型付き thunk 99 関数** (CAB-134 43 = ipp_min 29 + FFT PoC 14 / CAB-139 FFT pffft 化 28 名 stub 0 / CAB-136 優先上位 35 / CAB-245 ippiResizeSqrPixel_8u ×3 + GetBufSize 実測式 2 + 125 モジュール群 4) + 420 名 lookup 表 (未実装 321 は fail-soft stub)。FFT 32f NRMS 2.06e-7 / 64f 3.94e-16、simd128 で旧比 6〜19 倍。CAB-245 はオラクル 80,256 ケースで status 全一致・GetBufSize 74,468 ケース完全一致 (shim/REPORT.md §12)。
- 未着手: 残 stub 321 (使用集合 239 中 159) — 上位は interp 5/7 カーネル完全再現 (CUBIC2P 系, shim/REPORT.md §12-4) / `ippsRealToCplx_32f`・`ippsCplxToReal_32fc` (61) / `ippsCopy_8u` (55) / `ippsZero_32s` (51)。M11 結合 (thunk 経路の実機確認) と ipp-profile 採取。
