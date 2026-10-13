# ildsp (`block24360_PE.bin`) 規模調査

自動生成ではない。再現コマンドは下記。親: #161 (T-SH-15) / 本件: #791 (T-SH-19)。

## 再現

```
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/scripts/ildsp_survey.py
```

- 入力: `$FL_WIN64_DIR/extracted/block24360_PE.bin` (win64 PE, 4,197,376 B)
- 依存: `capstone`・`pefile` (`uv venv` + `uv pip install capstone pefile`)
- 出力: 表を標準出力へ、JSON を `tools/shared/work/raw/ildsp_survey.json` (gitignore)
- 所要: 実測 `real 0m3.620s` (Python 3.14 / capstone 5.0.7 / pefile 2024.8.26、入力 sha256 f4b23b0f…、HEAD 検証時)

## 1. 全体 (実測)

| 項目 | 実測 |
|---|---:|
| `.text` 命令数 (線形走査・仮想サイズ) | 362,280 |
| `.pdata` 関数数 (生データ読み) | 2,622 |
| 直接 call / 間接 call | 5,898 / 848 |
| 間接 call 比 | 12.6% |
| `IPPCODE` 命令数 | 129,192 |
| `IPPCODE` SIMD 比 | 70.0% |
| `.text` SIMD 比 | 48.68% (176,373 / 362,280) |

上表は HEAD の script 出力 (JSON: `text_instructions` 362280 / `simd_ratio` 0.4868 / `ippcode_instructions` 129192) と一致することを実測で確認済み。

### 未解決: `.text` SIMD 比の定義

旧 libreverb REPORT §6 にあった 111,346 (30.7%) を再現する定義は見つからなかった。試した定義と件数:

- `xmm`/`ymm`/`zmm` を含む全命令: 176,373
- 同上から GPR↔XMM の move を除外: 168,168 / 140,996 (スカラー ss/sd を除外)
- `simd_stats.py` の分類 (avx512 / avx_256 / avx_128 / sse_packed / sse_scalar): 176,373 (`sse_other` 除く 175,346)
- `.pdata` 関数の範囲に限定: 260,600 / 464,542 (56.1%)
- packed 演算のみ (`*ps`/`*pd`): 125,570

いずれも 111,346 とは一致しない。REPORT の値の出典 (別の母集団・別の定義) を特定できていない。定義を推測で作ることはしない。**起票先: #161 継続 (REPORT §6 の SIMD 比の出典を確認)**。

## 2. export 単位 closure 規模表

closure = export entry の関数 (`.pdata` 境界) から、直接 call と直接 jmp (別関数への tail) を辿った到達集合。間接 call は辿らず件数のみ数える。

| export | entry | 関数数 | 命令数 | SIMD 比 | 直接 call | 間接 call | 間接比 |
|---|---|---:|---:|---:|---:|---:|---:|
| GeneralPitchShifter_CreateInstance | 0x1aa290 | 8 | 238 | 8.8% | 14 | 4 | 22.2% |
| LimiterLite_CreateInstance | 0x1aa540 | 10 | 417 | 5.0% | 18 | 5 | 21.7% |
| Limiter_CreateInstance | 0x1aafd0 | 11 | 858 | 8.5% | 67 | 5 | 6.9% |
| LowFreqEnhancer_CreateInstance | 0x1ab3d0 | 140 | 10,307 | 4.2% | 540 | 61 | 10.2% |
| PSOLA_CreateInstance | 0x1ab540 | 8 | 238 | 8.8% | 14 | 4 | 22.2% |
| Shimmer_CreateInstance | 0x1ab810 | 44 | 1,765 | 2.3% | 155 | 37 | 19.3% |
| StereoEnhancer_CreateInstance | 0x1abca0 | 139 | 9,925 | 4.0% | 501 | 61 | 10.8% |
| TransientLooper_CreateInstance | 0x1abe00 | 9 | 289 | 0.0% | 24 | 6 | 20.0% |
| Transmitter_CreateInstance | 0x1ac260 | 12 | 1,020 | 8.9% | 101 | 64 | 38.8% |
| WaveformColouring_CreateInstance | 0x1ac470 | 10 | 762 | 27.4% | 17 | 4 | 19.1% |

- 最小: GeneralPitchShifter と PSOLA が同率 238 命令 (8 関数)。両者のバイト列は一致しない (sha1 713ff04f… / 0391d052…)。
- 規模の大きい 2 つ (LowFreqEnhancer 10,307 / StereoEnhancer 9,925 命令) は 140 / 139 関数。残り 8 件は 8〜44 関数。
- closure は間接 call を辿らないため、実到達はこの表より大きい可能性がある。
- 注意: `.pdata` 先頭でない entry は `owner()` で含む関数の先頭に正規化してから辿る。export の 10 件はすべて `.pdata` 先頭に一致した。

## 3. 次の子 issue の起票案 (PM が起票)

最小 instance は **PSOLA_CreateInstance** (または GeneralPitchShifter_CreateInstance)。どちらも 238 命令・8 関数で、lift と差分テストの初回対象に向く。ただし closure の間接 call 比が 22.2% あるため、間接 call の解決方法 (テーブル or 実行時 dispatch) を先に決める必要がある。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.text` SIMD 比 30.7% の定義・出典 | 旧 libreverb REPORT §6 の数値が再現できない | #161 継続 |
| closure の間接 call 先の解決 | 表の命令数は下限 | 起票案 (PSOLA lift) で扱う |
| ildsp の lift 本体 | #161 後半未達 | #161 継続 |
