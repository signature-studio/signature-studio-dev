# tools/ipp/shim/fft — IPP FFT (ippsFFT*_R_32f/64f) の pffft 差替え (CAB-139)

再現: `bash tools/ipp/shim/fft/fft_e2e.sh` (exit 0。所要 約 2 分)。公式回帰 `bash tools/ipp/shim/shim_e2e.sh` (10 checks PASS も同時維持、§6)。数値はすべて実測。

## 0. 結論

| 項目 | 結果 |
|---|---|
| 実装 | FFT family **28 関数すべてを実装** (旧 PoC 14 + stub 14)。stub は FFT では 0 になった (420 名全体では 92 実装 / 328 stub — CAB-136 分も含む) |
| 性能 (wasm simd128, 差替え前後を同一条件で実測) | **32f 6.4〜18.9 倍 / 64f 4.1〜9.7 倍**。32f N=4096 Fwd: 旧 39,072ns → 新 3,686ns (**10.6 倍**; 実 IPP native 比は旧 約 32〜50 倍遅 → 新 約 3 倍遅まで短縮, 実測値は §4) |
| 精度 (実 IPP との NRMS, native オラクル 3,658 ケース) | 単一変換 **32f 最大 2.06e-7 / 64f 最大 3.94e-16**。往復 32f 2.71e-7 / 64f 5.38e-16。golden 48 ケース (wasm): 32f 1.90e-7 / 64f 3.63e-16 — **64f は旧 PoC 水準 (6.6e-16) を上回って維持、32f は 1e-7 台維持 (旧 1.5e-7 に対し +37%, 理由は §3)** |
| status/エラー格子 | 実 IPP 実測に鏡像: order<0→-17, flag 不正 (1/2/4/8 以外)→-18, NULL→-8, buf=NULL 許容。格子 3,658 ケースで**不一致 0** (既知の意図的差分 1 種のみ, §5) |
| SIMD | upstream 同梱の WASM SIMD バックエンド (`pf_wasm_float/double.h`, `<wasm_simd128.h>`) を採用。simd128 ビルドの pffft TU に **v128 命令 2,177 個** (scalar ビルド 0) を確認 |

## 1. 実装選択: なぜ pffft (wasm 向け実装の理由)

| 候補 | 判定 |
|---|---|
| **pffft (marton78/pffft @ aa16fd3)** | **採用**。(1) upstream に **WASM SIMD (simd128) バックエンドが公式に入っている** (jpommier 本家 2024-11 "Enable WASM SIMD support" をフォークが取り込み。float は `<wasm_simd128.h>` 直書き, double は v128×2 に 4 double パック) — `-msimd128 -DPFFFT_ENABLE_WASM` を付けるだけで有効化でき, SSE→simd128 変換 (`-msse2`) や自前 simd128 ポートが不要。(2) **float/double 両対応** (pffft + pffft_double, 同一 API 形状)。(3) 2^a·3^b·5^c 対応で 2 冪は全部カバー, O(N log N) の実績ある実装。(4) C99・依存なし・小ささ (本体 約 4,700 行)。(5) BSD 系 (FFTPACK/UCAR) ライセンスで vendoring 可 |
| KISS FFT | float/double 両対応だが SIMD 無し。32f の SIMD 性能要件を満たさないため不採用 |
| PocketFFT (C++ header) | 高精度だが C++17・ヘッダオンリーで simd128 は自動ベクトル化頼み。shim が C 前提なのとベクタ化の確実性で不採用 |
| 実 IPP の arm64 版 lift | IPP 本体 lift は `tools/ipp/REPORT.md` で「不要」判定済み (arm64 版は 0.4MB の別実装だが lift コストと EULA 面 (事実整理済み) から方針「upstream からビルドできるものはビルド」に従い pffft) |

pffft の制約と対処: **最小変換サイズが REAL で 2·simd² (=32)** — ため order 1〜4 (N=2,4,8,16) は旧 PoC の倍精度基数 2 実装を「naive フォールバック」エンジンとして同梱し、Init 時にエンジン選択を spec に記録する (ticket 記載の「小 order 用フォールバック」)。なお 64f は scalar wasm ビルドに限り pffftd の最小サイズが 2 になるため N≥2 で pffftd を使う (実行時に `pffftd_min_fft_size()` で判定, ソース共通)。

## 2. 実装構成 (`shim/fft/`)

| パス | 内容 |
|---|---|
| `ipp_fft_pffft.c` `.h` | IPP FFT 28 関数の実装。宣言は `data/ipp_sigs.json` から機械転記し `test/fft_proto_check.c` で `gen/ipp_proto.h` と同一性を毎回検査 |
| `pffft/` | vendored pffft (取得元・コミット・改変箇所は **`PROVENANCE.md`**, ライセンスは `pffft/LICENSE.pffft.txt`) |
| `test/fft_oracle.c` | ネイティブ・オラクル: 実 IPP DLL (pe_load) vs 本実装を 28 関数 × order 0..16 × flag 4 種 × buffer あり/なしで比較 (NRMS + status 格子) |
| `test/fft_wasm_ext.mjs` | wasm 規模拡張テスト (thunk 経由): order 0..16 × flag × 全 Run 系 × in/out-of-place × buffer あり/なし = **3,784 checks** |
| `test/fft_proto_check.c` | 署名突合 TU |
| `test/probe_ipp_sem.c` | 実 IPP の意味採取プローブ (エラーコード・読み書き長の根拠, §5) |
| `bench/` | 差替え前後ベンチ (`build_bench.sh` は旧実装を git 履歴 — 削除済み `src/ipp_fft.c` の最終 touch コミットの親 — から取得して同フラグでビルド。HEAD 参照だと本チケットの削除コミット後に取得できないため検収時に修正) |
| `fft_e2e.sh` | 上記全部を直列実行する 1 コマンド |

設計の要点:

- **spec は IPP 契約どおり呼出し側バッファ内**に構築 (`pffft_new_setup_into` を vendored pffft に追加; upstream は内部 malloc で, IPP に Free 系 API が無いためリークになる)。`FFTGetSize` はその必要バイト数 + Run 用 work を返す (意味ある戻り値, 自己整合)。
- 形式: Pack=N 語 `[X0, X1.re, X1.im, …, X_{N/2}]`, CCS=N+2 語 (in-place も N+2 語書込), Perm=N 語 (pffft unordered; RToPerm↔PermToR の対で使用する不透明形式)。Pack/CCS/Perm の意味は実 IPP 実測で確認 (旧 `ipp_fft_ref.c` + 本 probe)。
- スケール flag (1/2/4/8) は pffft が無スケール (backward 生値 = N·IDFT) なので旧実装の `scale_of` をそのまま適用。往復合成ゲインは flag 1/2/4 で x, flag 8 で N·x (解析値)。
- Run の work: 32f は pBuffer (GetSize の pBufSize=2N 語) を `work/tmp` に使用, NULL なら内部確保。**64f は pffft_double が 32B 整列を要求する (IPP の保証は 16B) ため、ユーザーポインタを pffft に渡さず** pBuffer 内で 32B 切り上げして in/tmp/out を staging する (pBufSize=64+3N 語)。
- エンジン共通の 1 箇所で spec magic 検査 (防御; 実 IPP では未定義動作)。

ビルド接続: `gen_shim.py` の実装検出と `build_native.sh` / `build_wasm.sh` / `shim_e2e.sh` が `fft/*.c` + `fft/pffft/*.c` を拾うようにした (src/ipp_fft.c は削除 — 実体は fft/ へ移設)。`-msimd128` 時は `-DPFFFT_ENABLE_WASM` を build_wasm.sh の基本フラグに入れた済みで scalar ビルドは自動で scalar バックエンドに落ちる。emscripten の assert が wasi import を持ち込むため wasm ビルドのみ `-DNDEBUG` (native の検証ビルドでは assert 有効)。

## 3. 精度 (実測)

| 測定 | 32f | 64f |
|---|---|---|
| native オラクル 単一変換 vs 実 IPP (3,658 ケース, order 0..16 × flag × Pack/CCS/Perm × in/out) | **最大 2.06e-7** | **最大 3.94e-16** |
| 同・往復 (Fwd→Inv, 誤差二重化) | 最大 2.71e-7 | 最大 5.38e-16 |
| wasm golden 48 ケース (scalar/simd128 同値, shim_e2e S8) | 1.90e-7 | 3.63e-16 |
| wasm 規模拡張 3,784 checks (往復の解析的整合 + Pack↔CCS 一致 + in-place==out bit 一致) | gate 内 0 失敗 | gate 内 0 失敗 |

旧 PoC (倍精度計算→float 丸め) の 1.5e-7 に対し 32f が 2.06e-7 (+37%) の理由: 旧実装は倍精度で計算するため「実 IPP (float SIMD) 自身の誤差」との差だけだったが、pffft は float SIMD で計算するため**独立な 2 つの float 実装の誤差の合成 (√2 倍程度)**になるため。float eps (6e-8) の約 3 倍で同水準であり、回帰 gate (golden 5e-6) に対し 26 倍の余裕。64f は旧水準 6.6e-16 を**上回る**精度。fp-contract 等のビルドフラグは shim 既存の方針 (`-ffp-contract=off -fno-fast-math`) を踏襲。

## 4. 性能 (差替え前後を同一条件で実測)

条件: 同一 node (v24.19.0, emsdk 同梱)・同一入力・同一 iteration (min 3 回の最速値)・同一 emcc フラグ (`-O2 -DNDEBUG -ffp-contract=off -fno-fast-math` ± `-msimd128`)。旧実装は git 履歴 (削除前の `tools/ipp/src/ipp_fft.c`) をそのままビルド (`bench/build_bench.sh`)。pBuffer=NULL で統一 (旧実装は内部 malloc、新実装は内部 scratch)。単位 ns/call。**再現: `fft_e2e.sh` step 6**。

| ケース | 旧 (scalar) | 新 (scalar) | 旧 (simd128) | 新 (simd128) | speedup (simd128) |
|---|---|---|---|---|---|
| 32f N=256 Fwd | 1,765 | 549 | 1,900 | **297** | **6.4×** (buf あり 8.6×) |
| 32f N=1024 Fwd | 8,031 | 2,413 | 7,754 | **969** | **8.0×** |
| 32f N=4096 Fwd | 40,632 | 10,475 | 39,072 | **3,686** | **10.6×** |
| 32f N=16384 Fwd | 276,904 | 47,958 | 274,875 | **16,941** | **16.2×** |
| 32f N=65536 Fwd | 1,442,436 | 205,724 | 1,413,942 | **75,836** | **18.6×** |
| 64f N=4096 Fwd | 39,387 | 11,604 | 39,034 | **6,456** | **6.0×** |
| 64f N=65536 Fwd | 1,422,968 | 258,287 | 1,375,849 | **141,452** | **9.7×** |

範囲全体: **simd128 で 32f 6.4〜18.6 倍 / 64f 4.1〜9.7 倍** (Inv/in-place/CCS/Perm も同程度, `work/bench/*.json`)。チケットの動機だった「実 IPP (AVX-512 native) 比 32〜50 倍遅」は 32f N=4096 で **実 IPP 1,238ns (PoC 実測) vs 新 3,686ns = 約 3.0 倍遅**まで短縮 (native vs wasm の比較である点に注意)。Perm (pffft unordered 直行) は Pack と同程度の時間。

## 5. 実 IPP との意味合わせ (`test/probe_ipp_sem.c` の実測に基づく)

- `FFTGetSize/Init`: **order<0 → -17, flag は 1/2/4/8 のみ有効 (0 や 3,9,12,16 など組合せは -18), order=0 (N=1) は有効**, hint 0/1/2 は全部受理 (order 8 では 3 種とも同サイズ)。GetSize は spec/init/work の 3 出力 (order≥12 では実 IPP も init/work>0; サイズ値自体は不透明で、自己整合を確認)。
- NULL: Run は spec/src/dst NULL で **-8**, pBuffer NULL は 32f では許容。
- **既知の意図的差分 (1 種)**: 64f の Run で pBuffer=NULL のとき実 IPP は **-8 (buffer 必須)** を返すが、本実装は内部確保して成功 (0) を返す。既存回帰 `ipp_shim_wasm.mjs` が 64f でも pBuffer=0 で成功することを要求するため。呼出側が GetSize の pBufSize に従って buffer を渡す限り挙動は同一。
- order 27 以上: 実 IPP は本環境の native 実行で GetSize が SEGV する (order ≥21 で確認) ため突合を 17 までに限定。本実装は order ≤26 (pffft の上限 2^26) を受理、27+ は -17。
- in-place CCS は N+2 語を書込む (実 IPP と同一。呼出側は N+2 語の容量を保持する必要あり — 実 IPP 同様の契約)。

## 6. 回帰

- **`shim_e2e.sh` 10 checks 全 PASS** (S1..S9, scalar/simd128 含む; FFT 48 ケース 32f 1.90e-7 / 64f 3.63e-16、typed thunk 92 = 旧 43 + 本チケット 14 + CAB-136 進行中 35)。
- `fft_e2e.sh` 6 step 全緑 (proto 突合 / native オラクル / golden 48 / 規模拡張 3,784×2 / v128 確認 / ベンチ)。
- 併せて shim_e2e.sh の 2 点を改修: (1) fft ソースの追加 (本チケット), (2) **step 5b (shimx 結合) が `impl/*.c` をリンクしていなかった既存の穴**を修正 (CAB-136 の実装追加で顕在化したもの)。`shim_selftest.c` の実装数ピン (43/377) はハードコードをやめ `sigs_summary.json` と突き合わせる方式に変更 (実装追加のたびの更新が不要になり, CAB-136 との競合も回避)。
- **検収時修正 (2026-10-10)**: 本チケットのコミット後は `src/ipp_fft.c` が HEAD に存在しなくなるため `git show HEAD:` が exit 128 で step 5/6 が落ちる → `build_bench.sh` を「最終 touch コミットの親」参照に変更。修正後 `fft_e2e.sh` 全 6 step exit 0 を再確認。

## 7. 未解決・制約

- 32f の NRMS 2.06e-7 は float SIMD 化の構造的な置換コスト (§3)。これ以上は 32f を倍精度計算に戻すしかなく SIMD 性能とトレード。
- 64f の 16B 整列バッファに対する互換動作は staging (内部コピー 1 回) で確保しており、理論上 N 分のコストが残る (実測上は誤差範囲, §4)。
- 実 FL (FLEngine lift) との結合試験は未実施 (スコープ外)。呼出側が GetSize→ippMalloc→Init→Run の IPP 流であれば変更不要。
- `tools/ipp/shim/gen/`, `data/*.json` の再生成物は本コミットに含めない (CAB-136 の impl 追加状態を含むため。実行時に毎回再生成される。CAB-136 が実装と一緒にコミットする想定)。

## 8. 次タスク提案 (下流)

1. **CAB-136**: 引き続き impl/ 拡充 (本チケットと競合しない。gen_shim.py / build 3 本 / selftest は動的化済み)。
2. **ipp-profile / m11 結合**: FLEngine の FFT 呼出が GetSize→Init→Run 流であることを STRICT モード + `ipp_shim_stub_first()` で実機確認 (FFT は stub 0 なので FAIL-fast で踏まれない)。
3. ** 性能の残り差 (実 IPP 比 3 倍) が必要になったら**: pffft の relaxed-simd (FMA) 有効化 (`-mrelaxed-simd`; pf_wasm*.h が対応済み) の実測を次のチケット候補とする。
