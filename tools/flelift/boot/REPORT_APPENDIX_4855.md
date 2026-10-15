# tools/flelift/boot 付録 (#4855): boot_e2e の shard 別 clang RSS と variant 実測

> 正本: `tools/flelift/boot/REPORT.md` §12。本付録は shard 別の全数値。HEAD `d956129eb` (測定 commit = コードを変えた最後の commit) で `boot_e2e.sh` を 1 回実行 (foreground・素材 `fl-win64` 展開・emsdk 6.0.12)。

## A. shard 別 clang の peak RSS (MB, cap 5,000MB/shard・超過 0 件)

| variant | s0 | s1 | s2 | s3 | s4 | s5 | s6 | s7 | 最大 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| plain | 2502 | 2579 | 2278 | 2370 | 2300 | 2147 | 2491 | 2415 | 2579 |
| strict | 2503 | 2579 | 2279 | 2369 | 2301 | 2148 | 2491 | 2417 | 2579 |
| nosx | 2500 | 2593 | 2280 | 2370 | 2302 | 2146 | 2491 | 2415 | 2593 |
| chk | 2795 | 2975 | 2577 | 2707 | 2628 | 2447 | 2846 | 2748 | 2975 |

## B. shard 別 clang の秒 (elapsed)

| variant | s0 | s1 | s2 | s3 | s4 | s5 | s6 | s7 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| plain | 44 | 23 | 23 | 23 | 22 | 21 | 18 | 23 |
| strict | 47 | 18 | 23 | 16 | 22 | 19 | 17 | 18 |
| nosx | 44 | 17 | 24 | 24 | 23 | 20 | 20 | 20 |
| chk | 55 | 24 | 24 | 26 | 18 | 18 | 24 | 21 |

## C. 全 variant の結果 (`FLEBOOT_RESULT`・1 回)

| variant | units_run | GetMem / FreeMem | 停止 (boot_threw) | ipp.called |
|---|--:|--:|---|---|
| plain | 895 | 3,680 / 1,499 | exit | ippsZero_8u ×3 (0x67264d)・CreateCursorFromFont ×64 |
| strict | 93 | 1,224 / 332 | soft | なし |
| nosx | 0 | 0 / 0 | exit | なし |
| chk | 895 | 3,680 / 1,499 | trap `Maximum call stack size exceeded` | 同 plain |

- link (4 variant 共通): mismatch 0・undefined 0・duplicate 0 (`fleboot_{plain,strict,nosx,chk}.cjs`)。
- 最初のウィンドウ: 無し (`px6bbc20` の rect 呼出 0 件)。
- 結果 JSON (`results/boot_summary*.json`): 今回の実行で再生成されたが、コミットしていない (コミット済みの版は units 209 の旧 route で、§10・§11 の記述の元。今回の値は本付録の表が正本)。
- 測定の所要: lift + clang + link + boot の全体 `real 7m38s`・`user 13m43s`・`sys 1m59s`。load average は開始 0.96 / 終了 2.05 (4 vCPU)。
- 再現: `FL_WIN64_DIR=<展開先> bash tools/flelift/boot/boot_e2e.sh` (`toolchain-emsdk` = `docs/REFERENCES.md` の `[EMSDK]` を要する)。
