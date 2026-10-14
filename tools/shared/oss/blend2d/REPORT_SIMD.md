# Blend2D wasm `-msimd128` 試験 — 実測の詳細 (T-SH-02, #146)

> **正本**: 本ファイル (実測の詳細・未解決の起票先)。結論と索引は `tools/shared/REPORT.md` §3.3。
> 再現: `cd tools/shared && bash oss/blend2d/simd_bench.sh` (env: `SS_EMSDK_ENV` 既定 `/opt/emsdk/emsdk_env.sh`, `RUNS` 既定 3, `BENCH` 既定 300)。
> 検証起点: `5f4b1cb` (スクリプト強化コミット)。§1 の数値はこの HEAD のクリーン worktree (`git status` 空、生成物は gitignore の `tools/shared/work/`) で実行した値。

## 1. 最新の実測 (検証起点 5f4b1cb)

- 環境: GitHub Actions runner (nproc=4)、emcc 6.0.12、node v22.23.3、native g++ -O2。ソースは blend2d `fc827d5`・asmjit `029075b` (build.sh と同一)。
- 素材: `toolchain-emsdk` を `$ARTIFACTS_DIR` で実在確認 (`toolchain-emsdk.tar.zst` 532,513,899 B) → `/opt/emsdk` 展開済みを使用。
- フォント: DejaVuSans (`FL_MAC_DIR` が未展開のため OpenSans が無く fallback)。hash `f701c63bcdbcab67` は DejaVu 版の値 (OpenSans 版 `e467bd5b7dbcd277` とは不一致が正常)。
- 所要: 一括 109 s (wall, build 含む、`date +%s` 差)。load average (1 分/5 分/15 分): run 開始直前 0.04 0.17 0.09 → bench 直前 2.91 1.19 0.47 → bench 後 2.91 1.19 0.47。
- 終了コード: `rc=0`。`simd_sse2` の想定ビルド失敗は rc に含めず、比較対象からも外す。
- 再現 (検証起点 `5a7f765`、同じ runner・クリーン worktree で `bash oss/blend2d/simd_bench.sh` を 1 回): rc=0、wall 89 s (build 含む)、load average 2.66 1.20 0.47 (bench 前後とも)。native no-JIT 0.142–0.145 ms/frame、base 0.448–0.454、simd 0.391–0.460 (n=3 each)。画素 base・simd とも PASS (pixel_hash f701c63bcdbcab67)。negctl FAIL (differing bytes=1/230415)。同じく `simd_sse2` のみ想定どおりビルド失敗。

| 構成 | 画素 (vs native no-JIT) | ms/frame min–max (n=3, 中央値) | native 中央値比 | test.wasm / libblend2d.a |
|---|---|---|---|---|
| native no-JIT (g++ -O2) | — | 0.172–0.187 (中央値 0.173) | 1.0x | — |
| wasm32 no-JIT (base) | **PASS** (320×240, 230,400 B payload 全一致) | 0.454–0.524 (中央値 0.461) | 2.7x | 1,199,061 B / 2,789,016 B |
| wasm32 no-JIT + `-msimd128` | **PASS** (同上) | 0.408–0.488 (中央値 0.438) | 2.5x | 1,323,273 B / 2,911,480 B |
| wasm32 no-JIT + `-msimd128 -msse2` | **ビルド失敗 (想定結果)**: `math_p.h:198:19: error: expected namespace name`、`Vec4xF32` 未定義 | — | — | — |

- 中央値の比較: simd 0.438 / base 0.461 = 0.95 (−5%)。base と simd のレンジ (0.454–0.524 / 0.408–0.488) は重なる。n=3 のため統計検定はしておらず、「有意な高速化は確認できない」とだけ述べる。
- bench は 1 run あたり 300 iter (native 約 52 ms、wasm 約 140 ms 相当) の短時間計測。ノイズに敏感な点は未解決として §4 に残す。

**ネガティブコントロール** (判定の正しさの確認): `native.ppm` の末尾 1 byte (payload 最終画素の B 成分) を XOR 0xFF した `negctl.ppm` に `cmp -s` を掛けると不一致 = FAIL (期待どおり)。`cmp -l` の差分は **1 / 230,415 B** (ファイル全体。内訳はヘッダ 15 B + payload 230,400 B)。スクリプトは `negctl` が一致扱いになった場合 rc=1 にする。

## 2. 前版の実測 (検証起点 96c3a8f, 旧スクリプト, 2 スクリプト実行 × 各 3 / 5 回 = n=8)

PR #462 の初版 (`c8e52a6` 時点) で記録した値。旧スクリプトは失敗伝播・空ファイル判定・ネガティブコントロールを持たなかったため、参考値として残す。

- 環境は §1 と同じ runner (nproc=4, emcc 6.0.12, node v22.23.3, DejaVuSans)。bench 前後の load average (1 分値) 2.92–3.58、build 直後の同一ホストで測定。

| 構成 | 画素 (vs native no-JIT, 320×240 全 230,400B) | ms/frame min–max | native no-JIT 比 | test.wasm |
|---|---|---|---|---|
| native no-JIT (g++ -O2) | — | 0.209–0.216 (n=8) | 1.0x | — |
| wasm32 no-JIT (base) | **PASS 一致** | 0.586–0.738 (n=8) | 2.7–3.5x | 1,199,061B |
| wasm32 no-JIT + `-msimd128` | **PASS 一致** | 0.516–0.769 (n=8) | 2.4–3.7x | 1,323,273B |
| wasm32 no-JIT + `-msimd128 -msse2` | **ビルド失敗** (`math_p.h:198 expected namespace name` / `Vec4xF32` 未定義: Blend2D の SSE2 経路は x86 intrinsics 前提の simd 層を要求し emscripten の SSE 互換層とは噛み合わない) | — | — | — |

前版の結論 (要旨): `-msimd128` (自動ベクトル化のみ) は画素を変えないが、レンジが base と重なり**有意な高速化は確認できない**。Blend2D 側に wasm SIMD 用の simd バックエンドを足さない限り SIMD 化の効果は出ない、と推定 (推定: 固定パイプラインの inner loop が x86 SSE2/AVX 専用に書かれているため。未検証)。§1 の再測定でも同じ傾向 (中央値 −5%、レンジ重複) を確認した。

## 3. レビュー側の独立再実行 (c8e52a6, RUNS=3)

- oc-reviewer が head `c8e52a6` を detached worktree で再実行 (emcc 6.0.12・node v22.23.3・nproc=4・load 3.29)。
- 画素: base・simd とも native no-JIT と一致。別アルゴリズム (Python で PPM を直接解析し payload の sha256) でも一致 (`2149a392fa46cd4e`・230,400 B)。payload 末尾 1 byte の XOR は不一致 = FAIL で検算は機能。
- 速度 (n=3): native 0.170–0.176 / base 0.442–0.561 / simd 0.451–0.536 ms/frame (§1 より低いが runner 差と判断)。
- `simd_sse2` のビルド失敗はログで確認 (`math_p.h:198:19: error: expected namespace name`、`Vec4xF32` 未定義)。

## 4. 未解決・範囲外 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL 実描画経路の画素比較 (fl-win64 素材が必要。本 runner は FL 本体を展開していない) | 実 FL 描画経路での一致は未確認 | #146 (受入条件に残存・既存 issue) |
| Agg2D glue (`AggCreateInstance`、規模は `REPORT_AGG2D.md` §14) の lift or C++ 再実装 | glue 未実装のため wasm 本採用は未達 | #146 (受入条件に残存。lift/再実装の方針決定は人判断) |
| native JIT 比の再測定 (本 runner は native JIT を build していない) | 「wasm は JIT 比 約 4–5x」(`tools/shared/REPORT.md` §3.3 の既存値) を本 runner で再確認できていない | **起票依頼 (PM 判断)**: #146 へ追記 or 子 issue |
| `-msse2` 併用は Blend2D simd 層がビルド失敗 (`math_p.h:198` / `Vec4xF32` 未定義) | SSE2 経路を wasm で有効化する手段が未確定 | **起票依頼 (PM 判断)**: #146 へ追記 or 子 issue |
| `-msimd128` で速度差が出ない理由 (推定: 固定パイプラインの inner loop が x86 SSE2/AVX 専用に書かれているため。**未検証**) | SIMD 化の効果を得るには Blend2D 側に wasm SIMD 用 backend が必要かもしれない | **起票依頼 (PM 判断)**: 性能最適化の子 issue (#146 の「既知の問題として後で最適化」の範囲) |
| bench が 1 run 約 52〜140 ms と短い (n=3) | レンジ幅が実行環境の負荷に左右される | 上記の性能子 issue に含める (PM 判断) |
