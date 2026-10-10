# PROVENANCE — vendored pffft (tools/ipp/shim/fft/pffft)

## 取得元

| 項目 | 値 |
|---|---|
| リポジトリ | https://github.com/marton78/pffft (Julien Pommier の pffft — bitbucket.org/jpommier/pffft — の主要フォーク。double 対応と upstream 由来の WASM SIMD バックエンドを含む) |
| コミット | `aa16fd3db58de4ba5dae8b0438440bb9da46b6fa` (2026-09-29 "docs: missing rfftf1 comment") |
| 取得方法 | `git clone` (2026-10-10, 本 VM) |
| ライセンス | BSD 系 (FFTPACK v4/v5 ライセンス — UCAR の再配布条件 + Pommier 変更分は同一条件)。全文は `pffft/LICENSE.pffft.txt` (upstream の LICENSE.txt) |

## 同梱ファイル (upstream からの相対配置)

| 本リポジトリ | upstream | 用途 |
|---|---|---|
| `pffft/pffft.h` | `include/pffft/pffft.h` | float API |
| `pffft/pffft_double.h` | `include/pffft/pffft_double.h` | double API |
| `pffft/pffft.c` | `src/pffft.c` | float 実装 |
| `pffft/pffft_double.c` | `src/pffft_double.c` | double 実装 |
| `pffft/pffft_common.c` | `src/pffft_common.c` | 整列 malloc / ユーティリティ |
| `pffft/pffft_priv_impl.h` | `src/pffft_priv_impl.h` | 実装テンプレート (**CAB-139 パッチあり**) |
| `pffft/simd/pf_*.h` (13 ファイル) | `src/simd/pf_*.h` | SIMD バックエンド選択 (SSE1/AVX/SSE2/NEON/Altivec/Scalar/**WASM**) |
| `pffft/simd/sse2neon.h`, `pffft/simd/fmv.h` | `src/sse2neon.h`, `src/fmv.h` | ARM 上 SSE エミュレーション / x86 FMV (将来の arm64 mac lift 構成用に同梱) |

fftpack.c/h, pffastconv*, bench/tests 等は本 shim から使わないため同梱しない。

## CAB-139 による改変 (2 点, `PATCH (webstudio ...)` マーカー付き)

1. **`pffft_priv_impl.h`**: `FUNC_SETUP_BYTES` (spec 必要バイト数) と `FUNC_NEW_SETUP_INTO`
   (呼出し側が確保したメモリ内への setup 構築) を追加。
   理由: IPP の FFT API は spec (twiddle 含む) を**呼出し側バッファ内**に置く契約
   (`ippsFFTInit_R_*(ppSpec, order, flag, hint, pSpec, pSpecBuffer)`) で、upstream の
   `pffft_new_setup` は内部 malloc する。IPP 側に Free 系 API が無いため内部 malloc のままでは
   Init のたびにリークする。`pffft_new_setup` 本体・既存ロジックは変更していない
   (構築ループを同じ内容で in-place 版として複製)。
2. **`pffft.c` / `pffft_double.c`**: 上記 2 関数のマクロ名 (`pffft_setup_bytes` /
   `pffft_new_setup_into` / `pffftd_*`) を追加 (各 2 行)。

## wasm 向け実装選択 (REPORT.md 本文にも記載)

- 32f は upstream 同梱の **WASM SIMD バックエンド** (`simd/pf_wasm_float.h`, `<wasm_simd128.h>` 直書き,
  upstream jpommier の 2024-11 "Enable WASM SIMD support" 由来) を使用。有効化は
  `-msimd128 -DPFFFT_ENABLE_WASM` のみ (`__wasm_simd128__` が無ければ自動で scalar に落ちるため,
  scalar wasm ビルド・ネイティビルドは同じソースで成立する)。
- 64f は `pf_wasm_double.h` (v128 × 2 に 4 double をパック) を同様に使用。
- 検証: `fft_e2e.sh` が simd128 ビルドの pffft TU に v128 命令が実在すること (wasm-objdump) と,
  golden 48 ケースの NRMS を確認する。
