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
- **分類 (暫定)**: 書込み命令 (store) は **lift 側** (lift が生成した IR の store)。ただし値は **null ページを指すポインタ chain** を経由する。ポインタ値 `0x400000004` の由来は §6 で i32 2 本の 8B 読みと特定 (残は元の機械語との突合)。route 側 (data 敷設) は否定 (§3)。
- **受入条件の充足状況**:
  - [x] BLK+0 への store 命令を IR 行まで特定 (行 19132)。
  - 未達は子 issue へ移した (PM 判断で #1998 の範囲を縮小): wasm オフセット・route/lift の最終分類 → #2310 (ICALL-72)、値 `0x400000004` の生成元 → #2311 (ICALL-73)。
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

**WC 行 (測定に使った HEAD `1fff0e4f` で 2026-10-14 に再実行・`fa_wc_drv.cjs` の stderr。コード差分 0)**: 168 行 (21 IR 行 × 8 入力)。BLK 窓 (`0x36319000`–`0x36319020`) への書込みは 21 IR 行 (`0x36319008` 56 件・`0x36319010` 56 件・`0x36319018` 56 件)。入力 `work/fa_route/oi.flat.ll` は 25805 行・store 5526・`function_181057d20` 参照 88 で、`fa_wc.py instr` は `store total=5526 instrumented=5526 unhandled=0`。"emsc" (`63736d65`) を含む WC 行:

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
| コードを変えた最後の commit | `7273b6ac` |
| 測定に使った HEAD | `1fff0e4f` (REPORT 文言のみの差。`git diff 7273b6ac 1fff0e4f -- tools/icall` は本付録 `REPORT_APPENDIX_1998.md` のみ (+40 / −12)。コード差分 0) |
| 素材 | `fl-win64`・`plugins-freshair` (fetch.sh: win 17 files, factory .epf 8)・`work-icall`・`toolchain-emsdk` ([EMSDK])。`toolchain-retdec` は `fa_route_build.sh`・`fa_sweep.sh` では未使用 |
| `tools/ott/native/build.sh` | OK (`work/libottnative.so`) |
| `tools/icall/fa_route_build.sh` | OK、12.3 s |
| `tools/icall/diff/fa_sweep.sh 8 60` (1 回目) | 131 関数、70.8 s、load (1 分平均) 0.98 → 1.21 (`uptime`、開始 1.55)。`bit一致 47 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 9` |
| 同 (2 回目・同一 HEAD) | 131 関数、70.7 s、load (1 分平均) 0.98 → 1.11。関数単位で 1 回目と完全一致 (`sweep.jsonl` の `diff` 0 件) |
| 同 (負荷下・3 回目) | 4 コアに busy loop 5 本をかけた状態 (load 6.46)。86.6 s。`bit一致 47 / 66 / 9 / 9`、関数単位で 1 回目と完全一致 |

**REPORT の旧数値 (46 / 66 / 9 / 10) について**: 旧値は `REPORT_APPENDIX_2009.md` の OFF 行の数値 (`_ott_data_install` あり) で、今回の HEAD の実測では再現しなかった。HEAD で 3 回測り、関数単位で 47 が 3 回とも同じ判定になったため、本付録の数値は 47/66/9/9 とする。2009 の「47→46 の関数は未確定」は、`0x181065928` が HEAD で単体 `fa_cmp.py` 実行が SIGSEGV (`rip=0x1810806a0`) で bit 一致の候補にならないことから、この 47→46 の議論は今回の実測で解消した (2009 自体は未編集。未解決表の該当行は本付録の §4 で置き換える)。環境差 (負荷・パス) が原因かは、負荷下 (load 6.46) でも 47 だったため、負荷は原因ではないと判断する。

**判定 47 の関数別内訳 (HEAD 実測)**: bit 一致 47 関数は `sweep.jsonl` の `match == n` かつ `mismatch == 0` で数えた (`status`・`wasm_err`・`native_err` が無い行)。wasm のみ err 9 (`0x1803b5500`・`0x1803fb6f0`・`0x18040c950`・`0x180ca1480`・`0x180da5f20`・`0x181057b38`・`0x181057d20`・`0x18106632c` は 8 入力 err、`0x180c8b280` は 2 入力 err)。値の不一致 9: `0x1803de190`・`0x180829c20`・`0x180c98240`・`0x180c99430`・`0x180da4030`・`0x181055400`・`0x181056a4c`・`0x181056aa0`・`0x18105d9fc`。

`fa_cmp.py` の `mod._ott_data_install()` は `009c77bd` (測定 commit `7273b6ac` より前) で入っており、本測定はこれを含む。

`wasm のみ err` の 9 件: `0x1803b5500`・`0x1803fb6f0`・`0x18040c950`・`0x180c8b280`・`0x180ca1480`・`0x180da5f20`・`0x181057b38`・`0x181057d20`・`0x18106632c`。`0x180c8b280` (2 入力 err)・`0x181057b38` (8 入力 err) を含む。

値の不一致 9 件: `0x1803de190`・`0x180829c20`・`0x180c98240`・`0x180c99430`・`0x180da4030`・`0x181055400`・`0x181056a4c`・`0x181056aa0`・`0x18105d9fc` (いずれも 8 入力全不一致)。

注: 本測定の前に `tools/ott/native/build.sh` を実行した (未実行だと `libottnative.so` 無しで全件 crash_or_timeout になる)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 値 `0x400000004` の生成元は §6 で特定 (i64 store は 0 件。`function_181057b38` の隣接 alloca 2 つに入る `store i32 4` 2 本の 8B 読み)。残: 元の機械語との突合 (SlateCore 未展開)、alloca 配置が RetDec 由来か元の stack frame 由来かの切り分け | BLK+0 が "emsc" に化ける原因。wasm のみ err 2 件 (本付録 §1) | #2311 (ICALL-73) 残件 |
| IR 行 19132 → wasm 命令オフセットの対応・route/lift の最終分類 | 受入条件「wasm オフセットか IR 命令まで」の wasm 側 | #2310 (ICALL-72) |
| 引数付き lifted 関数の dispatch table 登録規則 | abort 6 件 (1852 付録 §2) | #1897 (ICALL-49) 既存 |
| 監視の対象外: `llvm.memcpy` / `llvm.memset` 等の intrinsic、`cmpxchg` / `atomicrmw`、C 側 (`oi.*.c`・`rt/*.c`)、emscripten libc の書込み。集成体型 (`[N x T]`・`{...}`) の store は `fa_wc.py` が挿入せず件数を出す (`unhandled`) | 上記の書込みは BLK 窓への書込みを見逃しうる。`fa_wc.py` は `work/fa_route/oi.flat.ll` の 5526 store 中 5526 件を挿入 (未対応 0) で、この集合には該当しない | 本付録 (監視の限界として明記) |

## 6. 再現

```
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FA_DL=$RUNNER_TEMP/plugins-freshair RETDEC_ROOT=$HOME/retdec TMPDIR=$RUNNER_TEMP
# 素材展開 (WORKFLOW.md §11): work-icall は tools/icall/work/ へ、fl-win64 は FL_WIN64_DIR へ
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .
mkdir -p "$FL_WIN64_DIR" "$FA_DL" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$FL_WIN64_DIR"
tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$FA_DL"
bash tools/targets/freshair/fetch.sh   # SlateCore.core_64 等を work/win/ に作る (無いと fa_route_build.sh は exit 2)
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_wc_build.sh          # 監視付き wasm (work/fa_wc/fa_wc.cjs)
node tools/icall/diff/fa_wc_drv.cjs $PWD/tools/icall/work/fa_wc/fa_wc.cjs 181057b38 2>err.txt
grep '^WC line=19132' err.txt                  # BLK+0 への書込み (IR 行 19132)
bash tools/icall/diff/fa_sweep.sh 8 60
```

範囲外: IR 行から wasm オフセットへの変換は未実施 (#2310)。`diff/fa_wc_drv.cjs` の引数は `<fa_wc.cjs 絶対パス> <VA>`。

## 6. 値 `0x400000004` の生成元 (ICALL-73 #2311)

測定: `fa_wc_build.sh` を再ビルド (`$RUNNER_TEMP/emsdk` の `emsdk_env.sh` を使用)。`fa_wc_drv.cjs <fa_wc.cjs> 181057b38` の 8 入力。`fa_wc_rt.c` の監視条件を追加: 値 `0x400000004` の 64bit store と、`0x104af3c0`–`0x104af400` (値の読み元の窓)。

| 観測 | 結果 |
|---|---|
| 値 `0x400000004` の 64bit store | **0 件** (8 入力。前回 #2382 の 0 件と一致) |
| 行 18908 `store i32 4` (`stack_var_-56`) → `0x104af3e0` (4B) | 8 入力で 1 件ずつ (`WCV`) |
| 行 18909 `store i32 4` (`stack_var_-52`) → `0x104af3e4` (4B) | 同上 (`WCV`) |
| 行 18970 `store &stack_var_-52` → `0x36319010` (BLK+0x10) | 値 `0x104af3e4` (8 入力で 1 件ずつ) |
| 行 18973 `store &stack_var_-24` → `0x36319018` (BLK+0x18) | 値 `0x104af3d8` (8 入力で 1 件ずつ) |

- 値の作られ方: `function_181057b38` (IR 18881–18882) の alloca `stack_var_-56` (`0x104af3e0`) と `stack_var_-52` (`0x104af3e4`) に `store i32 4` を 2 本書く。下位 4B=4、上位 4B=4 なので、この 8B を i64 で読むと `0x400000004`。
- 読み元: `function_181057a90` (IR 18807–18813) は `%1` = `load [0x36319018]` = `&stack_var_-24` (`0x104af3d8`)。`load [%1+8]` が `0x104af3e0` の 8B を読み、`0x400000004` を得る。`load [0x400000004]` = 0、`load [0]` = "emsc"。
- つまり "emsc" は address 0 の sentinel を、この 8B 読みの連鎖で指している。

**未確定**: (a) 元の x86 の機械語でも同じ 2 本の 4B store か (`SlateCore.core_64` 未展開のため未突合)、(b) alloca の配置が RetDec 由来か元の stack frame 由来か。(a) の突合は `fetch.sh` 実行後に行う。
