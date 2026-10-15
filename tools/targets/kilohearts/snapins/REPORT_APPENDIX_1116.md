# snapins REPORT 付録: #1116 (kh_heap_alloc 0 返却規約) の e2e 実測

測定 commit: 0735b3b89 (ネガコン追加。コード変更はこれが最後)。環境: ホスト x86_64 / 4 vCPU / 15GB。
素材: `fl-win64` `plugins-kilohearts` (Windows HeartCore.core_64 を `extract_installer.sh` で抽出) `toolchain-emsdk` `toolchain-retdec` を展開。
`run_all.sh` は TRIALS=200 SEED=1、`TMPDIR=$RUNNER_TEMP`。

## 結果

| 対象 | 結果 | 備考 |
|---|---|---|
| ネガコン `harness/heap_negctrl.py` | 8/8 PASS (`RESULT PASS`, exit 0) | 2MB・巨大要求で 0、cursor 不変、既存ブロック保持 |
| `heap_alloc_diff.py` | total=32 mismatches=0 (PR #1211 で実測) | |
| Path B (s0) matrix / gain / haas / clipper / gate / quickeq / resonator / stereo / disperser / formant | 各 200/200 bit-exact | 10 本 |
| Path B phaser / delay / limiter | **未達**: emcc RSS cap 超過 (peak 11124 / 11140 / 11043 MB, cap 11000 MB) | lift の結果ではなく資源上限。既定 cap は変えず |
| Path A 対照 matrix / gain / haas | 各 200/200 bit-exact | |
| Path A clipper | 0/200 (calls 37/1095) | run_all.sh の注記どおり「負の対照」(消失コードで不可能) |
| libm qemath / qebig | 50/50・4800/4800、200/200・4800/4800 | |
| khbase (s0) | **未達**: emcc RSS cap 超過 (peak 11122 MB) | khm* はこの mod に依存するため未実行 |
| khmrel / khmaster / khmring | **未実行** | khbase 未生成のため |

## 未実施と理由

- phaser / delay / limiter / khbase の emcc は RSS 11.0GB を超える。機材 RAM 15GB のため、cap を上げると runner 全体が落ちるおそれがあり上げていない。
- 一覧表 (`make_table.py`) と ABLATE は未実行。
- 呼び出し側 (`op_new` → HeapAlloc) の NULL 判定は HeartCore の逆アセンブルが要るため未確認。
- wasm sha の変化は、上の 0 返却規約での新 wasm を基に記録する (本 run では全体 sha の差分比較は未実施)。
