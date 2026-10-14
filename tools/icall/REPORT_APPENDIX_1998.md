# 付録: icall #1998 (ICALL-54) — BLK+0 (0x36319008) 上書きの書き込み元

> 親: #1899 (ICALL-50) の付録 `REPORT_APPENDIX_1899.md` §4 の未解決 1 件。本付録は子 issue #1998 の測定結果を記録する。

## 1. 結論

- **BLK+0 (`0x36319008`) への書込み元 (全 store 計装後の実測)**: 行 18686・18724・18782・18817・18940・18967・19132 の 7 行 (`function_181057a10`/`a90`/`b38`/`d20`)。`0x36319008` を書く store は 1 入力あたり 7 件で、8 入力では 56 件。
  - **"emsc" (`0x63736d65`) を `0x36319008` に書くのは行 19132 の 1 件のみ** (8 入力全て)。他 6 行の値は `5`・`4`・`0x104af3e8` 等でポインタ/小整数。
  - 行 19132: `store i64 %1, ptr %ce31n11_function_181057d20` = 書込み先 `0x36319008`。値 `%1` = `0x63736d65` ("emsc")。
  - 行 19134: `store i64 %1, ptr %ce32n11_function_181057d20` = 書込み先 `0x36319010`。
  - 行 19124 `store i64 %1, ptr %13` は任意アドレスへの "emsc" 書込み (`WCV`、BLK 範囲外の `0x104af4d8` 等 8 件)。"emsc" の発生源は行 19124 の `%1` で、これが 19132・19134 の値になる。
- **値 "emsc" の出所は線形メモリの address 0 (null ページ)**。行 18807–18813 の load chain: `%23 = load [%1+8]` = `0x400000004` → `%25 = load [0x400000004]` = 0 → `%29 = load [0]` = "emsc" (§2)。
- **emscripten のヌルページ sentinel**: 空の emscripten モジュール (main が 0 を返すだけ) でも address 0 から `65 6d 73 63` が見える。つまり "emsc" は route が敷設したデータではなく emscripten runtime 自身が置く値。
- **分類 (暫定)**: 書込み命令 (store) は **lift 側** (lift が生成した IR の store)。ただし値は **null ページを指すポインタ chain** を経由する。ポインタ値 `0x400000004` の由来 (どの store が誤ったポインタを作ったか) は未特定。route 側 (data 敷設) は否定 (§3)。
- **受入条件の充足状況**:
  - [x] BLK+0 への store 命令を IR 行まで特定 (行 19132)。
  - [ ] wasm オフセットまでの対応は未取得 (IR 行 → wasm オフセットの変換は未実施)。
  - [ ] route 側 / lift 側の最終分類 (値 `0x400000004` の生成元が未特定のため暫定)。
  - [x] `fa_sweep.sh 8 60` の集計を実測 (§4)。

## 2. 追跡 (実測)

測定: `fa_wc.py` の IR 監視 (`fa_wc_build.sh` の入力 `work/fa_route/oi.flat.ll` の全 5526 store に `__wchk` を挿入、未対応 0) + `fa_wc_drv.cjs` で `181057b38` に対して 8 入力を実行。全 8 入力で trap (memory access out of bounds)。`store` 行数 `grep -cE '^\s*store\b'` = 5526、挿入 `call void @__wchk` = 5526 (一致)。

**測定入力 (IR の出所)**: `work/fa_route/oi.flat.ll` = `tools/icall/fa_route_build.sh` の出力 (25805 行)。`work-icall` 成果物の `work/rt_freshair-core/after.0.restored.ll` (31464 行・store 5514・`function_181057d20` 定義 1 件) から、`fa_route_build.sh` の中で生成される。`work-icall` 成果物の `work/route/oi.flat.ll` (67462 行・store 14081) は別経路 (ott 系の route) の IR で、`fa_wc_build.sh` の入力ではない。成果物の `work/lift/oi.flat.ll` (store 12546) も同様に本測定の入力ではない。

| 入力 (IR) | 行数 | store | `function_181057d20` 参照 |
|---|---|---|---|
| `work/rt_freshair-core/after.0.restored.ll` (成果物) | 31464 | 5514 | 2 |
| `work/fa_route/oi.flat.ll` (本測定の入力、HEAD で再生成) | 25805 | 5526 | 88 |
| `work/route/oi.flat.ll` (成果物・別経路) | 67462 | 14081 | 0 |

`fa_wc.py instr` の出力: `store total=5526 instrumented=5526 unhandled=0`。`fa_wc_build.sh` の出力の `__wchk` 挿入は 5527 行 (宣言 1 行を含む)。

**WC 行 (HEAD `e1655883`・`fa_wc_drv.cjs` の stderr)**: 168 行 (21 IR 行 × 8 入力)。BLK 窓 (`0x36319000`–`0x36319020`) への書込みは 21 IR 行。"emsc" (`63736d65`) を含む WC 行:

| IR 行 | 関数 (`fn.json`) | 書込み先 | 値 | 件数 |
|---|---|---|---|---|
| 18819 | `function_181057a90` | `0x36319010` | `63736d65` | 8 |
| 19132 | `function_181057d20` | `0x36319008` | `63736d65` | 8 |
| 19134 | `function_181057d20` | `0x36319010` | `63736d65` | 8 |
| 19124 | `function_181057d20` | 任意 (`0x104af4d8` 等 8 アドレス) | `63736d65` | 8 (各 1 回ずつ・計 8) |

`fn.json` で `19132` → `function_181057d20` を確認 (`fa_wc.py` の `OUT.ll.fn.json`)。行 19132 の IR は `store i64 %1, ptr %ce31n11_function_181057d20, align 8`。

| 段階 | 観測 | 根拠 |
|---|---|---|
| instantiate 直後 | 線形 address 0 に `65 6d 73 63` | `scan.cjs` (`after-instantiate` total=1, BLK 範囲 0) |
| `ott_data_install` 後 | 変化なし (address 0 のみ、BLK 範囲 0) | `scan.cjs` `after-data-install` |
| `ott_run` 中の BLK 窓 (`0x36319000`–`0x36319020`) への書込み | 168 WC 行 (21 IR 行、8 入力)。`0x36319008`/`0x36319010`/`0x36319018` へ各 56 件 | `fa_wc_drv.cjs` の stderr (`WC line=`) |
| "emsc" の BLK 窓への書込み | 行 18819 (→ `0x36319010`)・行 19132 (→ `0x36319008`)・行 19134 (→ `0x36319010`) の 3 行。各入力で同じ | 同上 |
| 値の源 | 行 19124 `store i64 %1, ptr %13` が任意アドレスへ "emsc" を書く (`WCV` 8 件、BLK 窓外 `0x104af4d8` 等)。行 18807–18813 の load chain (`DBG` 行): `load [%1+8]`=0x400000004 → `load [0x400000004]`=0 → `load [0]`="emsc" | `WCV` と `dbg.ll` (`__dbgv` 挿入) |

行 18819 (`store %29 → 0x36319010`) が最初に BLK 窓へ "emsc" を書き (BLK+0x10)、行 19132 (`→ 0x36319008`) がトラップ番地を "emsc" にする。時系列は `run181b.err` で確認済み (旧測定)。

## 3. 否定できたこと

- **data 敷設 (route 側) は否定**: `ott_data_install` が書くのは `0x310c4000`・`0x3125c000`・`0x31354000` の 3 範囲 (`fa_data.c`)。BLK (`0x36319000`) を含まず、DLL の `.rdata/.data/_RDATA` に `65 6d 73 63` のバイト列は無い (raw DLL 検査 count 0)。
- **wasm data segment の "emsc" は関係しない**: wasm 内の `emsc` 出現は `emscripten_*` の import/export 名 (関数名) で、データではない。

## 4. 測定 (`tools/icall/diff/fa_sweep.sh 8 60`)

| 項目 | 値 |
|---|---|
| 測定 commit | `e1655883` (HEAD。コードを変えた最後の commit は `7273b6ac`。`git diff 7273b6ac HEAD -- tools/icall` は本付録 `REPORT_APPENDIX_1998.md` のみ) |
| 素材 | `fl-win64`・`plugins-freshair` (fetch.sh: win 17 files, factory .epf 8)・`work-icall`・`toolchain-emsdk` (`/opt/emsdk`)。`toolchain-retdec` は本測定 (`fa_route_build.sh`・`fa_sweep.sh`) では未使用 |
| `tools/ott/native/build.sh` | OK (`work/libottnative.so`) |
| `tools/icall/fa_route_build.sh` | OK、7.3 s |
| `tools/icall/diff/fa_sweep.sh 8 60` (実測 1 回目) | 131 関数、70.8 s、load 0.65 → 0.89 (`uptime`)。`bit一致 47 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 9` |
| 同 (2 回目・同一 HEAD) | 131 関数、関数単位で 1 回目と完全一致 (`diff` 0 件)。非決定性は無い |

**REPORT の旧数値 (46 / 66 / 9 / 10) との差**: 実測は 47 / 66 / 9 / 9。差は 1 関数 (bit 一致 +1、値の不一致 −1)。どの関数かは未確定 (前回測定の数値を引き継いだため、旧測定の関数別 `sweep.jsonl` が無い)。`REPORT_APPENDIX_2009.md` §3 が既に「bit 一致から外れた関数の未確定」として記録している問題と同種で、本付録では数値を 47/66/9/9 に置き換えた。

`fa_cmp.py` の `mod._ott_data_install()` は `009c77bd` (測定 commit `7273b6ac` より前) で入っており、本測定はこれを含む。

`wasm のみ err` の 9 件: `0x1803b5500`・`0x1803fb6f0`・`0x18040c950`・`0x180c8b280`・`0x180ca1480`・`0x180da5f20`・`0x181057b38`・`0x181057d20`・`0x18106632c`。`0x180c8b280` (2 入力 err)・`0x181057b38` (8 入力 err) を含む。

値の不一致 9 件: `0x1803de190`・`0x180829c20`・`0x180c98240`・`0x180c99430`・`0x180da4030`・`0x181055400`・`0x181056a4c`・`0x181056aa0`・`0x18105d9fc` (いずれも 8 入力全不一致)。

注: 本測定の前に `tools/ott/native/build.sh` を実行した (未実行だと `libottnative.so` 無しで全件 crash_or_timeout になる)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 値 `0x400000004` を作る store (null ページを指すポインタの生成元) の特定 (行 19124 の `%1` が "emsc" を運ぶ。`%1` の起点は未特定) | BLK+0 が "emsc" に化ける原因。wasm のみ err 2 件 (本付録 §1) | #1998 (本 PR は Refs。残りは同 issue で継続) |
| IR 行 19132 → wasm 命令オフセットの対応 | 受入条件「wasm オフセットか IR 命令まで」の wasm 側 | 同上 |
| 引数付き lifted 関数の dispatch table 登録規則 | abort 6 件 (1852 付録 §2) | #1897 (ICALL-49) 既存 |
| 監視の対象外: `llvm.memcpy` / `llvm.memset` 等の intrinsic、`cmpxchg` / `atomicrmw`、C 側 (`oi.*.c`・`rt/*.c`)、emscripten libc の書込み。集成体型 (`[N x T]`・`{...}`) の store は `fa_wc.py` が挿入せず件数を出す (`unhandled`) | 上記の書込みは BLK 窓への書込みを見逃しうる。`fa_wc.py` は `work/fa_route/oi.flat.ll` の 5526 store 中 5526 件を挿入 (未対応 0) で、この集合には該当しない | 本付録 (監視の限界として明記) |

## 6. 再現

```
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FA_DL=$RUNNER_TEMP/plugins-freshair RETDEC_ROOT=$HOME/retdec TMPDIR=$RUNNER_TEMP
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_wc_build.sh          # 監視付き wasm (work/fa_wc/fa_wc.cjs)
node tools/icall/diff/fa_wc_drv.cjs $PWD/tools/icall/work/fa_wc/fa_wc.cjs 181057b38 2>err.txt
grep '^WC line=19132' err.txt                  # BLK+0 への書込み (IR 行 19132)
bash tools/icall/diff/fa_sweep.sh 8 60
```

範囲外: 値 `0x400000004` の生成元は本付録では未特定。IR 行から wasm オフセットへの変換も未実施。`diff/fa_wc_drv.cjs` は work/ の drv.cjs と同一 (引数: `<fa_wc.cjs 絶対パス> <VA>`)。
