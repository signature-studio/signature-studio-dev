# IPP-9 (#276): `ippsVectorSlope_64f` / `_32f` の bit 再現 — 実 DLL の生成算法を解明 (2026-10-12)

既知類型との関係: `docs/DEFECTS.md` 該当なし (lift ではなく自前 C 実装の算法同定)。親: #263 (§13-5 の未解決の解消)。

> **更新 (IPP-11 #473)**: 本 REPORT §4 の未解決 (misaligned 出力先) は、実 DLL のカーネルを逆アセして head peel (`ポインタ & 15`) を特定し、`--mis K=0..16` の全てで bad_cases=0 になった。算法・検証・残課題は `REPORT_IPP11.md`。以下は IPP-9 時点の記録として残す。

## 結論

実 `dsp_ippv2_x64.dll` の VectorSlope は **ブロック累積** で値を生成しており、算法を同定して実装した。
**ISA 経路 (cpu mask 0x1/0x3/0x7/0xf/0x1f/0x3f の 6 通り) に依らず出力は同一**。
出力先が **64 バイト境界に揃った場合 (aligned)** は 64f・32f とも bit-exact。
**出力先がずれた場合 (misaligned) は未解決** (§4)。

| | 64f | 32f |
|---|---|---|
| ブロック幅 W | 8 | 16 |
| レーン k の初期値 | `o+k*s` (k=0..4,6)、k=5: `o+(3s+2s)`、k=7: `o+((3s+2s)+2s)` | k=4g+j: `o + (j*s に 4s を g 回加算)` |
| ブロック間更新 | 各レーンに `step=W*s` を加算 | 同左 (float 演算) |
| 端数 (len % W) | 先頭 = 次ブロックのレーン0 の累積値、以降は 直前要素 + s の直列加算 | 同左 |

積と加算は融合しない (`-ffp-contract=off` 必須。FMA 版は 14 通りの総当たりで不一致)。
実装: 64f = `impl/ipp_sig_fill3.c`、32f = `src/ipp_min.c` (`VSLOPE==0`)。

## 1. 同定の過程 (実測)

プローブ: `shim/test/vslope64_probe.c` (実 DLL の出力 bit をダンプ)。探索スクリプトは `tools/ipp/work/fill7/` (gitignore)。

- 純粋な `o+i*s`・`fma(i,s,o)`・正しく丸めた厳密値はいずれも不一致 (offset=1.0, slope=-1/3 の n=7 で 4 要素、n=4097 で 3,896〜3,899 要素が不一致)。
- W ∈ {1,2,4,8,16} × 累積器数 U ∈ {1..8} × 初期化 4 種 × step 2 種を総当たり → W×U=8 の `mul_add` + `step=8*s` が最良 (1,200 要素中 11 要素のみ不一致)。残りは全て lane 7 (インデックス 7 mod 8)。
- lane 5/7 の式を 600〜1,500 ケースで総当たり: lane5 = `o+(3s+2s)` (600/600)、lane7 = `o+((3s+2s)+2s)` (1,500/1,500。`o+(5s+2s)` は 1,470/1,500)。
- 端数: 直列加算 `prev+s` が 10,200 要素中 10,200 一致。端数の先頭要素だけは直列でなく「次ブロックのレーン0 の累積値」(2,400/2,400)。
- 32f は同様の総当たりで W=16 が最良 (不一致 166/7,680 → lane 7,9,10,11,13,14,15 が `o+k*s` と不一致)、`o+(a·s+b·s)` 形の探索で lane 4g+j の初期値式を確定 (各 lane 1,500/1,500)。

## 2. 検証 (コミット済み HEAD `61ff6c2` を ws-276 worktree で実行)

| 検査 | 結果 (実測) |
|---|---|
| `bash shim/test/fill3_oracle_run.sh` (§13-4 と同コマンド) | `SUM {"fns":61,"cases":727,"st_mis":0,"case_diff":0,"byte_diff":0}`、`dump records=297`、`wasm replay: records=297 mismatch=0 -> PASS`。所要 1.18 秒 (load average 1.37、並列 1) |
| 同 VectorSlope_64f 行 | `cases=9 st_mis=0 case_diff=0 byte_diff=0` (変更前: `case_diff=7 byte_diff=4757`)。エラー格子 `errgrid=10 mismatch=0` |
| `shim/test/vslope_verify.c` (実 DLL vs 自前、64f+32f、乱数ケース、mask 6 通り × 400) | `cases=4800 elements=1,347,350 bad_cases=0 bad_elements=0` (3 回とも。各 0.02 秒) |
| native と wasm (scalar / simd128) の自前出力の一致 (`shim/test/vslope_hash.c`、FNV-1a) | 3 者とも `ea554c7ef72ae86e` |
| 既存 `ref/ipp_ref cmp` (VectorSlope_32f、216 ケース / 2,665,224 要素、位置ずれ 0/1/3 含む) | 不一致 15,641 要素 / 47 ケース → **2,593 要素 / 23 ケース** (**未解決の残りは misaligned のみ**、§4) |

数え方: 要素 = 出力 1 個 (64f と 32f を別計上)。`bad_elements` は実 DLL との byte 単位不一致の要素数。

### ネガティブコントロール

| 破壊 | 検出結果 |
|---|---|
| `vslope_verify --neg` (自前出力の末尾 1 要素を 1 ULP ずらす) | `bad_cases=1109 bad_elements=2218`、exit 1 |
| 64f 実装のブロック更新を累積から `offset+i*s` の直接積に差替え (`shim/impl/ipp_sig_fill3.c` のコピー) | オラクル `case_diff=5 byte_diff=4752` (正規実装は 0/0) |

## 3. 再現

```sh
export IPP_DLL=<fl-win64 の extracted/block24356_PE.bin> EMSDK_DIR=<emsdk>   # 既定は従来パス
bash tools/ipp/shim/test/fill3_oracle_run.sh
gcc -O1 -ffp-contract=off -fno-fast-math -I tools/ipp/src -I tools/ipp/shim/test -o vslope_verify \
  tools/ipp/shim/test/vslope_verify.c tools/ipp/ref/pe_load.c tools/ipp/shim/impl/ipp_sig_fill3.c tools/ipp/src/ipp_min.c -lm
./vslope_verify "$IPP_DLL"            # 期待: bad_cases=0。--neg で exit 1、--mis K で出力先をずらす
```

素材: `fl-win64.tar.zst` (`extracted/block24356_PE.bin`) のみ。他の素材は不要。

## 4. 未解決 (範囲外)

実 DLL は **出力先のアライメントで出力が変わる** (同一入力で 64f: 要素 2 個 = 16B 単位、32f: 要素 4 個 = 16B 単位の位相が違うと別の値)。
`vslope_verify --mis K` の実測 (K = 64B 境界からのずれ要素数、`bad_cases`/4,800):

| K | 64f/32f 合算 bad_cases |
|---|---|
| 0, 4, 8, 16 | 0 |
| 1, 5 | 1,312 |
| 2, 6 | 1,032 |
| 3, 7 | 643 |

64f では K が偶数 (16B 揃い) のとき aligned と同一 (別途 240 ケースで確認)、奇数で不一致。
前置きの peel (先頭の非 aligned 要素を直列に処理し、残りをブロック化) という仮説で、ブロックの「ブロック → 直列」境界が
`p + W*floor((n-p)/W)` (p = peel 要素数) になる所までは観測と一致したが、**peel 部とブロック部の値の対応は未検証** (時間切れ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 出力先が 16B 境界に揃わない場合の bit 再現 (64f: 8B オフセット、32f: 4/8/12B オフセット) | ずれた出力先でのみ ULP 差 (ipp_ref の既存ハーネスでは 23/216 ケース)。FL の実呼出で出力先が 16B 揃いかどうかは未計測 (推定: バッファ先頭は揃いが多いが根拠なし) | 新規子チケット (親 #276・#263。番号は PM が採番。起票案は本 PR 本文) |
| 範囲外: VectorSlope_32s (stub のまま)、NaN/inf 入力 (実 DLL の特殊値挙動は未検証) | — | 同上の新規子チケットに含める |

「検証範囲」: aligned (64B 境界) 出力の 64f/32f、n=1..4097、mask 6 通り。「範囲外」: misaligned 出力、32s、特殊値入力。
