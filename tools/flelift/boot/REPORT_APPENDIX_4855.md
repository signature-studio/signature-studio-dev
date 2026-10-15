# tools/flelift/boot 付録 (#4855): boot_e2e の shard 別 clang RSS と variant 実測

> 正本: 本ファイル。REPORT.md は 1 行索引のみ (REPORT.md は main の 250 行上限ちょうどのため。付録の索引は `docs/DOC_MAP.md`)。本付録は shard 別の全数値。測定 commit = HEAD `96723a2ed` (main `ceb5a0ba6` を取り込んだ後の本 PR の HEAD。コードを変えた最後の commit)。`boot_e2e.sh` を 1 回 (foreground・素材 `fl-win64` 展開・emsdk 6.0.12)。

## A. shard 別 clang の peak RSS (MB, cap 5,000MB/shard・超過 0 件)

| variant | s0 | s1 | s2 | s3 | s4 | s5 | s6 | s7 | 最大 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| plain | 2502 | 2579 | 2278 | 2370 | 2301 | 2147 | 2491 | 2415 | 2579 |
| strict | 2500 | 2579 | 2280 | 2370 | 2302 | 2148 | 2491 | 2415 | 2579 |
| nosx | 2500 | 2580 | 2280 | 2370 | 2299 | 2146 | 2491 | 2417 | 2580 |
| chk | 2825 | 2978 | 2577 | 2707 | 2627 | 2448 | 2847 | 2769 | 2978 |

全 variant の最大は 2978MB (RSS は実行ごとに数十 MB 揺れる)。

## B. shard 別 clang の秒 (elapsed)

| variant | s0 | s1 | s2 | s3 | s4 | s5 | s6 | s7 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| plain | 41 | 27 | 25 | 22 | 15 | 17 | 20 | 19 |
| strict | 40 | 27 | 25 | 16 | 22 | 15 | 21 | 19 |
| nosx | 43 | 22 | 21 | 18 | 20 | 22 | 17 | 23 |
| chk | 46 | 33 | 22 | 23 | 23 | 27 | 24 | 25 |

## C. 全 variant の結果 (`FLEBOOT_RESULT`・1 回)

| variant | units_run | GetMem / FreeMem | 停止 (boot_threw) | ipp.called |
|---|--:|--:|---|---|
| plain | 895 | 3,680 / 1,499 | exit | ippsZero_8u ×3 (0x67264d)・CreateCursorFromFont ×64 |
| strict | 93 | 1,224 / 332 | soft | なし |
| nosx | 0 | 0 / 0 | exit | なし |
| chk | 895 | 3,680 / 1,499 | trap `Maximum call stack size exceeded` | 同 plain |

- link (4 variant 共通): mismatch 0・undefined 0・duplicate 0 (`fleboot_{plain,strict,nosx,chk}.cjs`)。
- 最初のウィンドウ: 無し (`px6bbc20` の rect 呼出 0 件)。
- 結果 JSON (`results/boot_summary*.json`): 今回の実行で再生成されたがコミットしていない。コミット済みの版は units 209 の旧 route で、REPORT §10・§11 の記述の元。今回の値は本付録の表が正本。
- 測定の所要: lift + clang + link + boot の全体 `real 7m23s`・`user 13m38s`・`sys 1m59s`。load average は開始 0.31 / 終了 1.78 (4 vCPU)。
- 再現: `FL_WIN64_DIR=<展開先> bash tools/flelift/boot/boot_e2e.sh` (`toolchain-emsdk` = `docs/REFERENCES.md` の `[EMSDK]` を要する)。
