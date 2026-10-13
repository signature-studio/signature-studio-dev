

## 10. PERF-P9 (#168) ④: closure の最適化 variant 別 build (LTO 効果)

検証起点: `origin/main` 36edc993 + 本節。環境: Actions runner (4 vCPU, load 0.6〜1.3)、素材 `fl-win64` + `toolchain-emsdk`。
同一 lift 産物 (`fle_lift.sh`: 7,018 関数 / 340,761 命令 / unsup 0) を variant 別に emcc link (`fle_lto.sh`)。

| variant | wasm (B) | emcc 所要 (s) |
|---|--:|--:|
| -O0 (既定) | 27,639,303 | 19.1 |
| -O2 | 13,705,498 | 87.4 |
| -O2 -flto | 11,122,894 | 108.8 |

実行確認 (`fle_lto_bench.mjs`: _UStrAsg 0x4133f0 + Move 0x409c80 の 2 関数を 7 種の n で反復、出力メモリの SHA-256 を取る):
20,000 反復 × 3 回の p50 (µs)。署名は 3 variant・3 回すべて一致 (`533e70fd7efebaa0`)。

| variant | 1 回目 | 2 回目 | 3 回目 |
|---|--:|--:|--:|
| -O0 | 0.450 | 0.341 | 0.290 |
| -O2 | 0.091 | 0.131 | 0.141 |
| -O2 -flto | 0.140 | 0.121 | 0.100 |

判定: **サイズと build 時間は実測で確定、実行時間は 2 関数の微小測定のみ**。-O2 系は -O0 の約 1/3〜1/4 の時間を示すが、
-O2 と -O2 -flto の差は回ごとに入れ替わり、LTO の効果は本測定では判定できない。
M11 級 (boot 連鎖) の closure 全体での実行時間は未測: boot closure の lift は RAM 上限で完走しない (`boot/REPORT_APPENDIX.md`, #918 = FLE-7)。
