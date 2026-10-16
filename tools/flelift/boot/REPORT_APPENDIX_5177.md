# REPORT_APPENDIX_5177 — FLE-43 (#5177): 既定経路の出力 hash 非決定性と判定指標

測定 commit: `e5261de58` (origin/main 取込み時点・コードは `outmem_judge.py` のみ追加)。
工程: `fle6_measure.sh` (`FLE_BOOT_RUNS=default`・`FLE_EXTRA_ROOTS=`・`FLE_BOOT_TAG=fle43`) → 既定経路 boot 8 回 (`FLE_IPP` 未指定・`FLE_OUTMEM_DUMP`)。
素材: `fl-win64` (`$ARTIFACTS_DIR` から `extracted/block00031_PE.bin` のみ展開)。emsdk は `toolchain-emsdk` 素材が無いため、上流 `emsdk install 6.0.12` (`tools/m1/flags.sh` の pin) で repo 外に入れた (`docs/REFERENCES.md` の `[EMSDK]` 取得元欄)。

## 1. 結論

- 既定経路では `outmem.full` が毎回変わる (8 run で 8 通り)。原因の書込み元は未特定。
- 判定に使う指標は `image_writable` から非決定 9 バイトを除いた値 (`outmem_judge.py`)。run 間一致の確認は、マスク導出に使った 8 run (初版 build の値 `7aa20126d7f7898f`) と、マスク導出に使わない新規 10 run (§6・build 値 `f39730d3…`) の 2 組で行った。どちらも全一致。マスク外の 1 バイト変更で値が変わることも確認した (検出力あり)。ただし、8 run の一致はマスク導出の循環を含むため、根拠は §6 の新規 run。
- 受入条件「原因特定 または 判定に使わない指標の策定」: 後者 (`outmem.full` を使わず、非決定位置を除いた `image_writable` を判定に使う指標) を満たす。原因 (書込み元) の特定は未達で、本 issue に残す (§5)。

## 2. 測定

| 項目 | 値 |
|---|---|
| build (gen-A / lift / clang-plain) | 7 s / 83 s / 118 s。`fle6_measure.sh` rc 0・所要 218 s |
| boot 前の load | 2.11 (boot 開始時) |
| boot 結果 (全 run 同一) | units_run 895・units_total 942・boot_threw `exit`・IPP ok (`ptr_15F34A0=0x7f10001c`) |
| 線形メモリ | 905,969,664 B |
| 既定 boot 回数 | 8 (r1〜r8) |

full (線形メモリ全体) の sha256 は 8 run で 8 通り。先頭 16 桁は r1 `b85dfc5648982876`・r2 `cff28e2c5a5c8cef` (`outmem_compare.py` の表より)。

## 3. 非決定の所在 (8 run の和集合)

| セクション | 差分バイト | VA | 性質 (r1 ↔ r2 の値) |
|---|---|---|---|
| `.data` | 4 | `0x13a5010`〜`0x13a5013` | 時刻風 (`0x7b422f0` ↔ `0x7fbcf4e5`) |
| `.data` | 1 | `0x13e4d58` | カウンタ風 (`0x339` ↔ `0x342`) |
| `.bss` | 3 | `0x15f26e8`〜`0x15f26ea` | カウンタ風 (`0xb1443` ↔ `0xb3e27`) |
| `.bss` | 1 | `0x16bcbf0` | カウンタ風 (`0x5c6` ↔ `0x5bf`) |
| `.idata`・`.didata` | 0 | — | — |

r1 対 r2 で差が出た 4 KiB ページは 11 枚。image 内 4 枚 (`0x13a5000`・`0x13e4000`・`0x15f2000`・`0x16bc000`) と、image 外 7 枚 (`0x11dcc000`〜`0x11dda000` の 5 枚・`0x11f20000`・`0x12cfa000`)。image 外 7 枚が C スタック・C heap のどちらに属するかは未分類 (stack 範囲は [0x115d2110, 0x11dd2110))。

書込み元 (関数) は未特定。`0x13a5010` の時刻風の値が、`fle_boot.c`・`fle_imp_bridge.c` の時刻関連 import (`GetSystemTimeAsFileTime`・`QueryPerformanceCounter`・`GetTickCount`) の戻り値に由来する可能性がある。未確認。

## 4. 判定指標

- 指標: `image_writable` (PE の `IMAGE_SCN_MEM_WRITE` セクション) のうち NONDET 9 バイトを 0 にした連結の sha256。
- 検証 (`outmem_judge.py`・rc 0):
  - 8 run の指標は全て `7aa20126d7f7898f` で一致。
  - マスク外の `.data` 0x13a5020 の 1 バイトを反転すると指標が変わる (検出力)。
- マスク無しの `image_writable` は 8 通り (`fe251e79…`・`153a6592…` ほか)。よって判定にはマスク後の値を使う。
- dst buffer `0x12d677d0` (長さ 0x28) は候補 (未検証)。旧 8 run の 6 run 同一は全 8 run の比較ではない。判定には使わない。
- 限界: NONDET は 8 run の和集合。将来の build で別の位置が非決定になる可能性がある。その場合は `outmem_judge.py` の FAIL で分かるが、位置の再算出 (`NONDET` の更新) が必要。

## 5. 未達 (本 PR の残件)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 非決定 9 バイトの書込み元 (関数) の特定 | マスクの根拠が測定値だけで、なぜ非決定かは不明 | #5830 (FLE-48) |
| C heap / C スタックの非決定ページ (11 枚) の扱い | `full`・`no_cstack` は判定に使えない (従来どおり) | #5830 (FLE-48) |
| ~~shim 有 (`FLE_IPP=1`) 経路の同じ 8 run 測定~~ | 解消 (§7・#5865) | — |

受入条件は「原因特定 または 判定指標の策定」の選言で、本 PR は後者を満たす。原因特定は子 issue #5830 (FLE-48、親 #5177) に分離した。

## 6. 新規 10 run による検証 (循環の解消)

マスク (`NONDET`) の導出に使っていない新規 run で判定を再確認した。

- 手順: `fle6_measure.sh` (`FLE_BOOT_RUNS=default`・`FLE_EXTRA_ROOTS=`) で build (`fleboot_plain.cjs`) を作り、その build に対して既定経路 boot (`FLE_IPP`・`FLE_TOLERANT` 未指定) を 10 回 (r1〜r10) 実行。dump は repo 外 (`$FLE_BOOT_WORK`) の `outmem_boot_plain_r{1..10}.bin`。
- 結果 (10 run): units_run 895・boot_threw `exit`・IPP ok (全 run 同一)。`outmem_judge.py` rc 0・判定指標 `f39730d34b15e8c1` が 10 run 全一致・検出力 True (マスク外 0x13a5020 の反転で変化)・RESULT PASS。
- 新規 10 run だけで求めた `image_writable` の差分位置 (個別バイト照合): `0x13a5010`〜13・`0x13e4d58`・`0x15f26e8`〜e9・`0x16bcbf0` の 8 位置。既存 `NONDET` の部分集合で、既存に無い位置は 0。`0x15f26ea` は新規 10 run では出なかった (8 run の和集合にある)。
- 注記: 判定指標の絶対値は、この build (`f39730d3…`) と PR 初版の測定 build (`7aa20126…`) で異なる。build 間で一致する値ではない。判定は run 間一致と検出力で行う。
- dst buffer `0x12d677d0` (長さ 0x28): 新規 10 run で全 0 (同一)。全 8 run の比較は §4 のとおり未確認で、補助指標は「候補 (未検証)」扱い。
- `full` の sha256: 新規 10 run で 10 通り (従来どおり判定に使わない)。

## 7. shim 有 (`FLE_IPP=1`) 経路の 8 run 一致 (#5865)

測定 commit: `cf486ff00` (origin/main・コード変更なし。本 PR は REPORT と結果 JSON のみ)。コード差分 `git diff cf486ff00 HEAD -- tools/flelift` は REPORT / results の 2 ファイルだけ (`tools/flelift` 配下の code 差分 0)。
素材: `fl-win64` (`fl-win64.tar.zst` から `extracted/block00031_PE.bin` のみ展開)。emsdk は `[EMSDK]` の pin どおり上流から `emsdk install 6.0.12` → `emsdk activate 6.0.12` で repo 外に入れた (runner に既定の `[EMSDK]` 配置は無い)。

工程 (run の再現コマンド):

1. build: `FL_WIN64_DIR=<展開先> SS_EMSDK_ENV=<emsdk_env.sh> FLE_BOOT_TAG=fle5865rerun FLE_BOOT_RUNS=shim bash tools/flelift/boot/fle6_measure.sh`。shim 段が IPP 判定 NG で rc 3 を返したのは想定どおり (下記)。build は gen-A 7 s / lift 81 s / clang-plain 99 s で完了 (fleboot_plain.cjs を作る目的)。
2. boot: build の成果物 `work/boot/fleboot_plain.cjs` に対して `node tools/flelift/boot/fle_boot.mjs <絶対パス>/fleboot_plain.cjs <json> --boot-only` を `FLE_IPP=1`・`FLE_TOLERANT=0`・`FLE_DIAG_NULLFILL=0`・`FLE_BOOT_LOG_CAP=0`・`FLE_OUTMEM_DUMP=<repo 外>` で 8 回 (r1〜r8)。`fle6_measure.sh` は boot 段で rc 3 を返すため、8 run は手動 loop で実行した (`fle6_measure.sh` は 1 回で止まる)。
3. 判定: `python3 tools/flelift/boot/outmem_judge.py <dump dir> --pe <PE>`。

run 単位の結果 (全文は `results/outmem_judge_shim_fle5865_r1-8.json`):

| run | units_run | units_total | boot_threw | ipp `ptr_15F34A0` | IPP 判定 | dump sha256 (full) 先頭 16 桁 |
|---|---|---|---|---|---|---|
| r1 | 209 | 942 | `exit` (code 0) | 0x0 | NG (rc 3) | 4c1e212355cd380a |
| r2 | 209 | 942 | `exit` (code 0) | 0x0 | NG (rc 3) | 3bfa7cae237a3898 |
| r3 | 209 | 942 | `exit` (code 0) | 0x0 | NG (rc 3) | 1b7383b110c5e09f |
| r4 | 209 | 942 | `exit` (code 0) | 0x0 | NG (rc 3) | 9b42341eeb8b2e1a |
| r5 | 209 | 942 | `exit` (code 0) | 0x0 | NG (rc 3) | ff6e5678af4ad68e |
| r6 | 209 | 942 | `exit` (code 0) | 0x0 | NG (rc 3) | 0703aafb1ab9f708 |
| r7 | 209 | 942 | `exit` (code 0) | 0x0 | NG (rc 3) | 4dbf20df5081bb23 |
| r8 | 209 | 942 | `exit` (code 0) | 0x0 | NG (rc 3) | 685c4dac9acea0b7 |

`outmem_judge.py` の出力 (rc 0):

```
outmem_boot_plain_r1.bin 〜 r8.bin: 判定指標 891b29801d1bd50a (8 本全て)
判定指標: 全 8 run で一致 = True
検出力: マスク外 1 バイト (0x13a5020) の変更で指標が変わる = True
RESULT PASS
```

注記:

- 判定指標の絶対値は build ごとに違う (§4・§6 の `7aa20126…`・`f39730d3…` と別値)。run 間一致と検出力だけを根拠にする。
- 停止点 (units 209) は shim 有の既知の値で、本 PR で変えていない。既定経路の 895 units とは別経路 (shim 有は 209 で停止する)。
- 製品 KPI: 起動の進行 (FLEngine dispatch・通過 unit) は本 PR で変えていない。測定は shim 経路の再現で、既定経路の KPI は動かしていない。
- `full` (線形メモリ全体) は shim 有でも判定に使わない (従来どおり)。

注記:

- 判定指標の絶対値は build ごとに違う (§4・§6 の `7aa20126…`・`f39730d3…` と別値)。run 間一致と検出力だけを根拠にする。
- 停止点 (units 209) は shim 有の既知の値で、本 PR で変えていない。既定経路の 895 units とは別経路 (shim 有は 209 で停止する)。
- 製品 KPI: 起動の進行 (FLEngine dispatch・通過 unit) は本 PR で変えていない。測定は shim 経路の再現で、既定経路の KPI は動かしていない。
- `full` (線形メモリ全体) は shim 有でも判定に使わない (従来どおり)。
