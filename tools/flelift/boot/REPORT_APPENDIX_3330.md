# tools/flelift/boot — REPORT 付録 (PERF-P22 #3330: boot 停止時点の出力メモリの sha256 を 3 変種で比較)

> 正本: この付録 (測定値)。親 #970 (PERF-P14) の受入 3 の残り。`REPORT_APPENDIX_970.md` §F の未解決 1 件を扱う。
> 測定 code: 本 commit の `tools/flelift/boot/{fle_boot.mjs,build.sh,outmem_compare.py,outmem_variants.sh}`。作業ツリーで測定し、その内容をそのまま commit した (測定後の code 差分 0)。

## A. 結論

- **PE の書込み可能セクション** (`.data`・`.bss`・`.idata`・`.didata`) の sha256 は、3 変種 (plain = -O0 / o2 = -O2 / o2lto = -O2 -flto) × 2 run の **6 本すべてで一致** (`891b29801d1bd50a`)。guest 側の書込み可能な状態はこの範囲で変種間一致。
- **ネガコン (`FLE_IPP=0`) では、この範囲の sha256 は変わらない** (同じ `891b29801d1bd50a`)。よって、この範囲は「shim 有無」という出力を変える入力に対して判別力が無い。ネガコンが変えるのは線形メモリ全体と C スタックを除く範囲 (`no_cstack`) だけ。
- **線形メモリ全体 (`full`) と `no_cstack` は、変種間でも同一変種の run 間でも一致しない**。原因は 4 節 (C 側の data レイアウト・C heap の数ページ) で、guest の状態ではない。
- 結論の範囲: 「PE 書込み可能セクションは 3 変種で一致」は n=2 で確かめた。「出力メモリ全体が一致」は**言えない**。ネガコンの判別力は `no_cstack` でのみ確かめた。

## B. 測定条件と出力領域の定義

- 工程: `outmem_variants.sh build` (gen-A → lift (closure 2・root 0x6a7b70・shard 8) → plain (-O0) → o2 ∥ o2lto) → `outmem_variants.sh boot` (`variant_boot.sh` で shim 有 `FLE_IPP=1`・各 n=2 → ネガコン `FLE_IPP=0` 1 run → `outmem_compare.py`)。
- 作業場: `$RUNNER_TEMP/boot3330` (repo 外)。素材: `fl-win64` (`extracted/block00031_PE.bin` のみ展開)・`toolchain-emsdk` (emcc 6.0.12)。
- 出力領域 (boot 停止時点・`_fle_boot_enter` が exit で抜けた後):
  - `full` = 線形メモリ全体 (864 MiB 固定。`-Wl,--initial-memory` = `--max-memory`)。
  - `no_cstack` = `full` から emscripten の C スタック `[stack_end, stack_base)` を除いた範囲 (スタックの残骸は C の最適化水準に依る)。
  - `image_writable` = PE の `IMAGE_SCN_MEM_WRITE` のセクションを guest VA `0x400000 + VirtualAddress` で連結した範囲 (`.data` 0xfa5000 / `.bss` 0x11e6000 / `.idata` 0x156f000 / `.didata` 0x1576000)。
- 計算: `fle_boot.mjs` (node:crypto) が JSON の `boot.outmem` に出し、`outmem_compare.py` が dump (`FLE_OUTMEM_DUMP`) を Python hashlib で読み直す。**両者の `full`・`no_cstack` が全 run で一致** (7 本)。`image_writable` は python 側のみ。

## C. 実測値

### C-1. build (wasm bytes・link 検査)

| 変種 | wasm (B) | link (mismatch / undefined / duplicate) |
|---|--:|---|
| plain (-O0) | 127,082,180 | 0 / 0 / 0 |
| o2 (-O2) | 64,684,605 | 0 / 0 / 0 |
| o2lto (-O2 -flto) | 62,606,025 | 0 / 0 / 0 |

- 壁時計: lift 直後の plain 1 本 (shard 8・-P3) = 100 s (lift 除く)、o2 ∥ o2lto = 823 s (初回・rss 木全体 peak 7,943 MB, cap 12,000 内)。再リンクのみ (driver の 2 回目) は o2 ∥ o2lto 517 s。build 秒は n=1 で参考値。

### C-2. boot と出力範囲 (shim 有 `FLE_IPP=1`・node・`--boot-only`)

| label | run | wall (s) | units_run | stopped | GetMem / FreeMem | ipp.called | rc |
|---|---|--:|--:|--:|---|---|--:|
| plain | 1 / 2 | 24.079 / 23.996 | 209 | 209 | 2,314 / 1,199 | ippsZero_8u × 2 | 3 (IPP 判定 NG・既知) |
| o2 | 1 / 2 | 4.641 / 4.675 | 209 | 209 | 2,314 / 1,199 | ippsZero_8u × 2 | 3 |
| o2lto | 1 / 2 | 4.656 / 4.594 | 209 | 209 | 2,314 / 1,199 | ippsZero_8u × 2 | 3 |

停止点は 3 変種とも unit 209 の後の `exit` (`MessageBoxA` → `ExitProcess`)。最初のウィンドウは未達。

### C-3. 出力範囲の sha256 (先頭 16 桁。全長は JSON)

| label | run | full | no_cstack | image_writable |
|---|---|---|---|---|
| plain | 1 | a406005e7e03a462 | c5bb402a656b1f4a | 891b29801d1bd50a |
| plain | 2 | 3ada1d0cd476b5a0 | 24cb3daf7ca8a6ad | 891b29801d1bd50a |
| o2 | 1 | c5e8a72417ae7f08 | 789f6b20852e51f2 | 891b29801d1bd50a |
| o2 | 2 | 1d737bf7f6c52603 | b65adb36048f4f6b | 891b29801d1bd50a |
| o2lto | 1 | 4a49733fc4b04ed6 | 192131960d098580 | 891b29801d1bd50a |
| o2lto | 2 | 9d89845dc97ccd8f | 230ce1255c66e6e1 | 891b29801d1bd50a |
| plain_negctl (`FLE_IPP=0`) | 1 | 7c3556c70490f2b7 | b84c6a83f89b7074 | 891b29801d1bd50a |

- スタック範囲 (`stack_end` / `stack_base`): plain `0x115bb260` / `0x11dbb260`、o2 `0x115ba360` / `0x11dba360`、o2lto `0x115b8f80` / `0x11db8f80`。
- `image_writable` の各セクション (`.data`・`.bss`・`.idata`・`.didata`) も 6 run で一致 (`outmem_compare.py` の出力)。

## D. 差分の所在 (dump のページ単位比較・Python)

- **plain r1 と r2 (同一変種)**: 4 KiB ページで 5 枚だけ異なる。アドレスは `0x11db5000`・`0x11db9000` (スタック範囲内)、`0x11dbe000`〜`0x11dc0000`・`0x11dc8000` (スタック上端 `0x11dbb260` より上 = C heap の先頭付近)。`image_writable` には現れない。**run 間の非決定はこの C heap 付近にある** (原因は未特定。時刻・乱数・ホストの値の書込みが候補)。
- **plain と o2 (変種間)**: 5,073 ページが 16 区間で異なる。最大の区間は `0x10000000`〜`0x1136e000` (約 20.4 MB)。これは C の data (GLOBAL_BASE 以降) で、guest イメージ (`0x400000`〜) の外。変種の data レイアウトの差と見られる (未確認)。guest イメージ内の差は 0。
- guest の書込み可能セクションの差は 0 (3 変種・6 run)。

## E. 検証範囲 / 範囲外

- 範囲内: 3 変種の boot 停止点までの線形メモリ (3 変種 × 2 run + ネガコン 1 run)。
- 範囲外: 変種ごとの n は 2 (min–max は未測定)。描画 (最初のウィンドウ) の同一性は #3060 が前提で未確認。LTO の shim (-O1 固定) の扱いは #672。unit 209 より先の状態は測っていない。

## F. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `image_writable` は `FLE_IPP=0` に対して判別力が無い (ネガコンの変化は `no_cstack` だけ)。受入 2 の「ネガコンで sha256 が変わる」は、guest の書込み可能セクションでは未達 | 「出力が一致」の強さが弱い (guest の heap 側の状態は見ていない) | #3330 (次 run: guest heap (FastMM の確保範囲) を出力範囲に加える案の検討) |
| `no_cstack` の run 間非決定 (plain r1/r2 で 5 ページ・C heap 付近) | `full`・`no_cstack` を厳密な一致判定に使えない | #3330 (非決定源の特定。時刻・乱数の書込み元を確かめる) |
| 変種間の C data レイアウトの差 (0x10000000〜約 20 MB) | `full` の変種間一致は得られない | #3330 (C 側の状態を比較対象から外す定義を採るかの判断) |
| n=2 (run 間 min–max 未測定) | 一致の強さが 2 run 分 | #3330 |

## G. 差し戻し 1 回目の修正と再測定 (測定 commit `1ca5989f6`)

- 修正 (`1ca5989f6`): (1) `outmem` を summary のトップレベルに出し、`boot` の外へ移した (署名 `variant_boot.sh` = boot + ipp に C heap の非決定を入れない)。(2) `outmem_compare.py` の rc は受入 1 (`image_writable` と各書込み可能セクションの変種間一致) と node 照合 (`full`・`no_cstack`) だけで決める。`full`・`no_cstack` の変種間一致は参考表示に格下げ。ネガコンは別行。(3) `outmem_variants.sh mutant` を追加 (比較器の検出力)。
- 測定 commit: `1ca5989f6` (コードを変えた最後の commit)。その後の code 差分: `git diff 1ca5989f6 HEAD -- tools/flelift/boot ':(exclude)*.md'` は空 (本節は md だけの変更)。旧測定 commit `09e7239c0` からの差分 (`git diff 09e7239c0 1ca5989f6 -- tools/flelift/boot`) は空でない = 上記 (1)〜(3) の修正 (m1)。
- 作業場 `$RUNNER_TEMP/boot3330` (repo 外)。素材は `fl-win64` (`extracted/block00031_PE.bin`) と runner 同梱の emsdk (emcc 6.0.12・REPORT §C-1 と同版)。

### G-1. 署名 (summary.tsv の `signature` 列 = boot + ipp の sha256 先頭 16 桁)

| label | run 1 | run 2 |
|---|---|---|
| plain (-O0) | 953e12a0e9aec56e | 953e12a0e9aec56e |
| o2 (-O2) | 953e12a0e9aec56e | 953e12a0e9aec56e |
| o2lto (-O2 -flto) | 953e12a0e9aec56e | 953e12a0e9aec56e |

6 本すべて同一。`outmem` を外したので、同一変種 2 run の署名が一致する (旧版では `full`・`no_cstack` の非決定が署名に入っていた)。

### G-2. 比較 (`outmem_variants.sh boot` の `outmem_compare.py` 出力そのまま・rc 0)

```
image_writable: 変種 plain,o2,o2lto の全 run で一致 = True (異なる値 1 件)
section .data: 一致 = True (異なる値 1 件)
section .bss: 一致 = True (異なる値 1 件)
section .idata: 一致 = True (異なる値 1 件)
section .didata: 一致 = True (異なる値 1 件)
参考 no_cstack: 変種 plain,o2,o2lto の全 run で一致 = False (異なる値 6 件)
参考 full: 変種 plain,o2,o2lto の全 run で一致 = False (異なる値 6 件)
negctl plain_negctl: image_writable が変種と異なる = False (受入 2 未達)
RESULT PASS
```

- 全 7 run で node 版と python 版の `full`・`no_cstack` が一致 (`# <label> r<i>: ... = True`)。
- `image_writable` の値 (全 6 run + ネガコン) = `891b29801d1bd50a`。ネガコンでも変わらない (受入 2 は未達のまま)。
- `full`・`no_cstack` は 6 run で 6 通り (C heap の run 間非決定と変種差。判定には使わない)。

### G-3. 比較器の検出力 (`outmem_variants.sh mutant`・rc 1)

- 操作: `plain r1` の dump の複製で線形アドレス `0x13a5000` (= `0x400000` + `.data` RVA `0xfa5000`・`.data` の先頭) の 1 byte を `0x00 → 0xff`。元の dump は変えない。
- dump 全体の sha256 先頭 16 桁: `a2ed2b27b81bdffd` → `ba4bddb3df6c5d17`。
- 比較器の出力: `plain r1` の `image_writable` = `891b29801d1bd50a` → `ea22cdb72f2c1b6a`。`image_writable: ... 一致 = False (異なる値 2 件)`、`section .data: 一致 = False (異なる値 2 件)`。`RESULT FAIL` / rc 1。
- 注: FAIL は `image_writable`・`.data` の不一致が理由。加えて `plain r1` は `full` が変わるので node 照合も False になる (両方が出る)。判別力は `image_writable` 側で確認できた。

### G-4. 所要・load・並列数 (m2)

| 工程 | 実測 (s) | 開始時 load (1 分) | 並列 |
|---|--:|--:|---|
| lift (closure 2・shard 8) | 86 | 0.04 | — |
| build plain (-O0) | 97 | 0.77 | FLE_CC_JOBS=3 |
| build o2 ∥ o2lto | 794 (rss 木全体 peak 8,081 MB、cap 12,000 内) | 2.08 | 2 本 × FLE_CC_JOBS=2 |
| boot plain r1 / r2 | 25.338 / 25.337 | 記録なし | 1 |
| boot o2 r1 / r2 | 6.024 / 6.030 | 記録なし | 1 |
| boot o2lto r1 / r2 | 6.191 / 5.998 | 記録なし | 1 |

- boot の load average は `variant_boot.sh` が出していない (未記録。未解決)。
- 3 変種の wasm (B): plain 127,082,180 / o2 64,684,605 / o2lto 62,606,025。link は 3 変種とも mismatch 0・undefined 0・dup 0 (build log)。§C-1 と一致。

### G-5. 容量 (m4)

- dump 7 本 = 905,969,664 B × 7 ≒ 6.0 GiB (`du` 6.0G)。作業前の `/` 利用可 80 GB → dump 書込み後 73 GB (`df -h`)。

### G-6. 製品 KPI (boot)

- units_run 209 / stopped 209 / exit (MessageBoxA → ExitProcess) は全 6 本 + 修正前と同じ。最初のウィンドウは未達のまま。

### G-7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `image_writable` が `FLE_IPP=0` に対して判別力が無い (受入 2 未達。G-2) | 出力の一致の強さが弱い (guest heap 側は未確認) | #3330 (次 run) |
| `full`・`no_cstack` の run 間非決定 (G-2 参考: 6 通り) | 厳密一致の判定に使えない | #3330 |
| 変種間の C data レイアウトの差 | `full` の変種間一致は未達 | #3330 |
| boot の load average 未記録 (G-4) | 所要の n=2 の条件が不完全 | #3330 |
| n=2 (run 間 min–max 未測定) | 一致の強さが 2 run 分 | #3330 |

- §C-3 の表は旧測定 (`09e7239c0` 相当) の値。`full`・`no_cstack` は run ごとに変わるため、新測定 (G-2) とは値が違う。`image_writable` は両方で `891b29801d1bd50a`。
