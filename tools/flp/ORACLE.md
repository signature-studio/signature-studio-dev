# ORACLE.md — wasm FLEngine 比較オラクル設計

状態: 設計 + 実装済みの部品 (`src/wav.ts`, `src/stft.ts`, `src/flpdiff.ts`, `cli/wavcmp.ts`, `cli/flpdiff.ts`, `corpus/*`) / 最終更新 2026-10-10
前提: **ネイティブ FL は動かせない** → 「正解 WAV」は存在しない。したがって「正解との一致」ではなく
**複数の独立した相対オラクルの積み上げ** で wasm FLEngine の正しさを判定する。外部 golden (§7) が得られれば最上位層として追加する。

## 0. 層構成と受入ゲート

| 層 | 問い | 基準 | 状態 |
|---|---|---|---|
| T0 | パーサ/ライタは FL ファイルを無損失に扱えるか | 9,740 ファイル byte-exact + typed 往復 100% | **達成** (`flp_e2e.sh`) |
| T1 | wasm FLEngine の load→save は情報を落とさないか | FLP イベント差分 (§5) | 設計 (`cli/flpdiff.ts` 実装済み) |
| T2 | render は決定論的か | 同一入力 N 回で SHA-256 一致 (§2) | 設計 |
| T3 | 既知 DSP 単体が原本機械語と一致するか | bit-exact / ULP 許容 (§3) | M5/M10 に先行実績 |
| T4 | プロジェクト render が不変条件を満たすか | 不変条件 + self-golden (§6) | 設計 |
| T5 | ネイティブ FL の実 render と近いか | 許容誤差クラス A–D (§4) | **素材待ち** (§7 ユーザ依頼) |

ゲート: wasm FLEngine の「起動可」= T0+T1 / 「音が出る」= +T2 / 「プラグイン単位で正しい」= +T3 / 「曲が正しい」= +T4 (+T5)。

## 1. 本ディレクトリが提供する素材 (全て実測)

- `corpus/manifest.json`: 164 projects (Demo 45 / Template 35 / **Render tests 82** / system 2)。tempo, 小節数, `renderSeconds`, 使用プラグイン, sample 参照 (1,243 件中 factory 参照 1,105、実在 1,100 = 99.5%)。
- **Render tests (82 本)**: FL 同梱の「ネイティブ plugin 1 つ + 0–12 ノート / 0.25–2 小節 / 120–140 BPM / render 1.71–4 s」のプロジェクト (長さが取れた本の合計 165 s; ノート無しの 1 本は長さ不明)。80 種の plugin を 1 本ずつ検証できる最小単位で、**plugin 優先順位表 (`corpus/plugins.json`) と同じ粒度**。参照 WAV は同梱されていない。
- `corpus/fst_manifest.json`: 9,576 presets (plugin-state 8,306 / channel-state 643 / insert-state 18 / score 609)。plugin 状態 (event 213) の load→save 往復テストに使う。
- **近似 ground truth としての「FL ≥ 25.2 保存ファイル」163 件**: FL 26.1.7 エンジンの書込 ID 集合 (`corpus/engine_event_ids.json`) で 129 ID 中 126 を説明できる。wasm 版 FLEngine が保存した FLP は、揮発 ID を除けばこれらと同形になるはず (§5)。

## 2. (a) render 出力の決定論性チェック (T2)

目的: wasm 化で混入しうる非決定性 (未初期化メモリ, 時刻, スレッド, 浮動小数点環境) を、正解が無くても検出する。

手順 (各 Render test + 代表 Demo 5 本):
1. 固定条件で offline render → 32-bit float WAV (`SR=48000`, dither off, 補間 = プロジェクト設定のまま)。
2. 同一条件で **N=3 回** (うち 1 回は別プロセス/新規 wasm instance) → `data` チャンク SHA-256 が全一致 = PASS (`cli/wavcmp.ts` が各 WAV のハッシュを出す)。
3. 派生チェック (不一致は plugin 毎の分類として記録し、即 FAIL にはしない):
   - **block size 不変性**: 128 / 480 / 4096 frames で render。DET-1 = bit 一致 (線形/状態変数のみ), DET-2 = クラス B 以内 (ブロック境界で係数更新があるもの)。
   - **スレッド**: ミキサ並列 ON/OFF (shim は `thread=1` 固定モードを持たせる)。加算順が変わるため差はクラス B で判定。
   - **ホスト環境**: Chrome/Node, wasm SIMD ON/OFF, `memory.grow` 有無。
4. 非決定性の既知要因と対処 (shim 側レバー): ① 未初期化メモリ (native は不定値、wasm はゼロ初期化 → `heap` shim をゼロ/0xCD パターン双方で走らせ差が出れば lift 漏れ), ② `GetTickCount/QPC` → 仮想クロック固定, ③ RNG → seed 固定/シード由来を trace, ④ denormal → MXCSR FTZ/DAZ 相当を明示 (wasm は常に denormal を保持するので x86 FTZ 前提コードは差になる), ⑤ x87 80bit 経路 (Delphi の Extended) → lift 時に検出して個別扱い。
5. 不一致の切り分け: 全 insert solo render で bisect → plugin 単位 → T3 へ。

## 3. (b) 既知 DSP 単体の bit-exact / tolerance 比較 (T3)

3 者比較で wasm 化由来の誤差だけを分離する:

| 記号 | 実体 | 役割 |
|---|---|---|
| X | **原本機械語を VA 通りに MAP_FIXED 敷設してネイティブ実行** (`tools/m5/native_fx.c` 方式, MS x64 規約) | 実機 oracle (純計算関数に限る) |
| L | lifted LLVM IR を native clang でコンパイル | lift の正しさ (X との比較) |
| W | 同一 IR → wasm | toolchain の正しさ (L との比較) |

判定: **L = W は常に bit-exact** (同一 IR; 崩れたら NaN 正規化 / `-ffp-contract=off` 漏れ / libm 差 = toolchain バグ)。**X = W は関数クラスで決定**: 四則のみ → クラス A (bit-exact), libm 超越関数 (tan/exp/log/pow/sin) 経由 → クラス B。
刺激 (決定論的、seed 固定 xorshift): インパルス / 階段 / DC / 1 kHz −6 dBFS / 対数スイープ / 白色雑音 / 無音 / フルスケール矩形 / denormal 尾 × ブロック長 {1, 64, 128, 480, 4096, 素数長} × パラメータ格子 (OTT なら depth, time, in/out gain, 3 バンド各 ratio)。
先行実績: M10 は OTT バンドフィルタ 8 states × 10 係数を **dsm register-exact で maxdev = 0.0** (`tools/m10/REPORT.md`) — この粒度 (係数 → 状態 → 出力) で 3 段階に分けて判定する。M5 は waveshaper/distortion を X=W **8/8 bit-exact**。
OTT の残課題 (exp/log 連鎖の junk) は T3 のクラス B 判定で追跡し、**bit-exact 512/512 は junk-free 確保後** (M10 REPORT §5 と同じ留保)。

## 4. (c) WAV 出力の許容誤差ルール

### 4.1 正規化 (比較前に必ず適用)
- 形式: 32-bit float WAV 同士で比較 (PCM は float へ無損失変換; 16/24-bit 比較は同一量子化・dither off が条件)。`parseWav` は PCM8/16/24/32, float32/64, WAVE_FORMAT_EXTENSIBLE を扱う。
- 形状: **サンプルレート, チャンネル数, フレーム数が完全一致**を要求 (不一致 = 即 FAIL)。例外: 末尾 ≤ 1 ブロック (≤ 4096 f) の差で超過分が −90 dBFS 未満の無音なら WARN に降格。
- NaN / ±Inf が 1 つでもあれば全クラスで FAIL。レイテンシ補正 (PDC) は 0 に揃えて render し、**位相合わせの自動シフトはしない** (ずれ自体を不具合として検出)。

### 4.2 許容クラス (数値根拠)
float32 の 1 ULP (フルスケール近傍) = 2^-23 ≈ 1.19e-7 (−138.5 dBFS)。24-bit PCM の 1 LSB も同値。16-bit LSB = 3.05e-5 (−90.3 dBFS)。

| クラス | 判定式 (`judge()` 実装済み) | 適用対象 |
|---|---|---|
| **A-exact** | 全サンプル bit 一致 | 四則/biquad/ゲイン/パン/ミキサ和/ディレイ(整数) |
| **B-ulp** | `maxUlp ≤ 4` かつ `maxAbs ≤ 1e-6` (−120 dBFS ≈ 8 LSB24) | libm 超越関数経由 (tanh, exp, tan, pow, sin LFO 表生成), ミキサ加算順差 |
| **C-statistical** | `rmsDiff/ref ≤ −80 dB` かつ ピーク差 ≤ 0.01 dB かつ `maxAbs ≤ 1e-4` | 長い帰還系 (リバーブ/フランジャ), 補間 (sinc 表由来) |
| **D-spectral** | `rmsDiff/ref ≤ −60 dB` かつ ピーク差 ≤ 0.1 dB **かつ** STFT 判定 (§4.4) | 乱数変調 (RNG 非共有), granular, ランダム位相 |

B の導出: libm 1 呼出 ≤ 1–2 ULP、1 サンプル経路に 2–3 回、その後の線形段で拡大しない前提で 4 ULP; 絶対上限 1e-6 は 4 ULP を 8 LSB24 相当まで緩めた安全側。C/D の閾値は **暫定** (ネイティブ golden 入手後に実測分布で再校正; §7)。

### 4.3 出力レポート
`cli/wavcmp.ts a.wav b.wav <class>` が JSON (`a/b{frames,ch,rate,bits,sha256}, metrics{bitExact,maxAbs,maxUlp,rmsDiffDb,snrDb,peakDiffDb,…}, spectral{lufs*,truePeak*,stft{…,first,worst}} (D のみ), firstDiff, verdict{pass,why}`) を出し、PASS で exit 0。CI は Render test 毎に呼ぶ。
**最初の差分位置** (`firstDiff`, `firstViolation()`): A = 最初に bit が異なる sample, B = 最初に ULP>4 または |差|>1e-6 の sample, C = 最初に |差|>1e-4 の sample (いずれも `{channel, frame, timeSec, a, b, absDiff}`; frame 優先・同一 frame は ch 順), D = 最初に STFT 許容外となったビン `{channel, frame (STFT), startSample, timeSec, bin, freqHz, refDb, testDb, diffDb}`。shape 不一致 / NaN 時は null。`verdict.why` にも D の first 位置を載せる。

### 4.4 D クラスの STFT 判定 (実装済み — `src/stft.ts`, `judgeWav()`; #108)
Hann 4096 / hop 1024、ピーク −60 dB 以内のビンで |振幅差| ≤ 0.1 dB、BS.1770 LUFS-I ±0.1 LU、true-peak ±0.1 dB。D-spectral の合格 = 上記 §4.2 の時間領域条件 **かつ** 次の 3 つ全て:

- **STFT**: 周期 Hann 4096 / hop 1024 / 全チャンネル対。窓は全て full window (末尾は終端に揃えた 1 窓で覆い、ゼロ詰め窓は使わない; 4096 f 未満の信号のみゼロ詰め 1 窓)。比較対象ビン = 参照側の全フレーム・全 ch の最大ビン振幅から −60 dB 以内のビン。1 ビンでも `|20log10(test/ref)| > 0.1 dB` なら FAIL。参照が完全無音なら test も完全無音のときのみ PASS。
- **LUFS-I**: BS.1770-4 K-weighting (任意 fs の bilinear 係数) + 400 ms ブロック / 75 % 重なり / −70 LUFS 絶対ゲート / −10 LU 相対ゲート (400 ms 未満は 1 ブロック扱い)。`|ΔLUFS-I| ≤ 0.1 LU`。5 ch 以上は Ls/Rs に 1.41 を掛け LFE を除外。
- **true-peak**: 4× (fs<96k) / 2× (<192k) オーバーサンプル、16 tap Kaiser(β=8) sinc を位相ごとに DC 正規化 (BS.1770 Annex 2 の 48 tap FIR そのものではなく同等の近似; fs/4 付近までの正弦で誤差 ≤ 0.001 dB)。`|ΔTP| ≤ 0.1 dB`。
- `judge(m, 'D-spectral')` は `SpectralMetrics` が無いと **fail-closed**。`judgeWav(a, b, cls)` が compare → STFT/LUFS/TP → judge を一括で行う。
- 閾値は §4.2 と同じく **暫定** (§7 のネイティブ golden 入手後に再校正)。

## 5. FLP load/save 忠実度 (T1)

1. FL ≥ 25.2 保存ファイル (163 件) を wasm FLEngine で load→save → `cli/flpdiff.ts orig.flp saved.flp`。
2. 揮発 ID を除外: 199 (FlVersion), 159 (FlBuild), 0xC0000101 ("FL Studio x.y"), 200 (Licensee), 237 (Timestamp)。
3. 期待: **26.1.0.5528 で保存された唯一のファイル** (`Templates/Minimal/Basic with limiter`) は `identical = true` (ID 列も一致)。25.2.x は FL 26 のスキーマ更新ぶんのみ差 (差の ID を許可リスト化して固定)。
4. 追加ゲート: 保存した全イベント ID ∈ `ENGINE_WRITTEN_IDS ∪ {0, 226, 227}` (src/id_sets.ts)。範囲外 ID を書いたら lift/shim 不具合。
5. 不動点: save(load(save(load(x)))) = save(load(x))。
6. FST: `corpus/fst_manifest.json` の plugin-state 8,306 件を plugin 毎に load→save し event 213 を比較 (plugin 優先順は `corpus/plugins.json`)。

## 6. プロジェクト render の不変条件 (T4)

無音テスト (全ミュート → 全サンプル 0.0) / 線形性 (マスター −6.0206 dB でサンプル半減, 線形経路のみ B) / 長さ (`renderSeconds` ± 1 ブロック) / NaN・Inf 無し / DC ≤ 1e-7 / モノ互換 (L=R の入力 → L=R) / 時間シフト不変 (1 小節ずらして render → 波形同一)。
**self-golden**: T3 合格後の最初の render の SHA-256 を `golden/` に登録し以降の変更は説明必須 (「正解」ではなく回帰検出)。

## 7. ユーザ依頼事項 (T5)

可能なら Windows/mac ネイティブ FL 26.1.7 で次の WAV を書き出して提供: **Render tests 82 本** (File → Export → WAV, 48 kHz, 32-bit float, dither off, 「Disable max plugin delay compensation」既定, 補間 = プロジェクト設定) + 代表 Demo 3 本。これで C/D 閾値を実測で確定し、plugin → クラス割当を表で固定できる。未提供でも T0–T4 は進められる。

## 8. 限界

- X (機械語直接実行) は純計算関数のみ。GUI/OS 依存を含む経路は不可 → T2/T4 の相対判定に頼る。
- FL 内蔵リサンプラ/PDC/並列ミキサの挙動は未解析。T5 まで「近い」の絶対基準は無い。
- 乱数・時間依存 plugin はシード/クロックを shim で固定した場合のみ A/B 判定が成立 (そうでなければ D)。
