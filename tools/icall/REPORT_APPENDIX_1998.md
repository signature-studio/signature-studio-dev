# 付録: icall #1998 (ICALL-54) — BLK+0 (0x36319008) 上書きの書き込み元

> 親: #1899 (ICALL-50) の付録 `REPORT_APPENDIX_1899.md` §4 の未解決 1 件。本付録は子 issue #1998 の測定結果を記録する。

## 1. 結論

- **書き込み元の IR store を特定した (IR 行まで)**: `function_181057d20` (`oi.flat.ll` 行 19132・19134)。
  - 行 19132: `store i64 %1, ptr inttoptr(909217800)` = 書込み先 `0x36319008` (trap が読む番地)。値 `%1` = `0x63736d65` ("emsc")。
  - 行 19134: `store i64 %1, ptr inttoptr(909217808)` = 書込み先 `0x36319010` (BLK+0x10 側)。
- **値 "emsc" の出所は線形メモリの address 0 (null ページ)**。行 18807–18813 の load chain: `%23 = load [%1+8]` = `0x400000004` → `%25 = load [0x400000004]` = 0 → `%29 = load [0]` = "emsc" (§2)。
- **emscripten のヌルページ sentinel**: 空の emscripten モジュール (main が 0 を返すだけ) でも address 0 から `65 6d 73 63` が見える。つまり "emsc" は route が敷設したデータではなく emscripten runtime 自身が置く値。
- **分類 (暫定)**: 書込み命令 (store) は **lift 側** (lift が生成した IR の store)。ただし値は **null ページを指すポインタ chain** を経由する。ポインタ値 `0x400000004` の由来 (どの store が誤ったポインタを作ったか) は未特定。route 側 (data 敷設) は否定 (§3)。
- **受入条件の充足状況**:
  - [x] BLK+0 への store 命令を IR 行まで特定 (行 19132)。
  - [ ] wasm オフセットまでの対応は未取得 (IR 行 → wasm オフセットの変換は未実施)。
  - [ ] route 側 / lift 側の最終分類 (値 `0x400000004` の生成元が未特定のため暫定)。
  - [x] `fa_sweep.sh 8 60` の集計を実測 (§4)。

## 2. 追跡 (実測)

測定: `fa_wc.py` の IR 監視 (全 5526 store に `__wchk` を挿入) + `ott_run` を `181057b38` に対して 8 入力で実行。全 8 入力で trap (memory access out of bounds)。

| 段階 | 観測 | 根拠 |
|---|---|---|
| instantiate 直後 | 線形 address 0 に `65 6d 73 63` | `scan.cjs` (`after-instantiate` total=1, BLK 範囲 0) |
| `ott_data_install` 後 | 変化なし (address 0 のみ、BLK 範囲 0) | `scan.cjs` `after-data-install` |
| `ott_run` 中の BLK+0 書込み | 行 19132 (`function_181057d20`) が `0x63736d65` を BLK+0 へ書く | `fa_wc` WC 行 |
| 値の源 | 行 18807–18813 の load chain (`DBG` 行): `load [%1+8]`=0x400000004 → `load [0x400000004]`=0 → `load [0]`="emsc" | `dbg.ll` (`__dbgv` 挿入) |

行 18819 (`store %29 → 0x36319010`) が最初に BLK 範囲へ "emsc" を書き (BLK+0x10)、行 19132 (`→ 0x36319008`) がトラップ番地を "emsc" にする。時系列は `run181b.err` で確認済み。

## 3. 否定できたこと

- **data 敷設 (route 側) は否定**: `ott_data_install` が書くのは `0x310c4000`・`0x3125c000`・`0x31354000` の 3 範囲 (`fa_data.c`)。BLK (`0x36319000`) を含まず、DLL の `.rdata/.data/_RDATA` に `65 6d 73 63` のバイト列は無い (raw DLL 検査 count 0)。
- **wasm data segment の "emsc" は関係しない**: wasm 内の `emsc` 出現は `emscripten_*` の import/export 名 (関数名) で、データではない。

## 4. 測定 (`tools/icall/diff/fa_sweep.sh 8 60`)

| 項目 | 値 |
|---|---|
| 測定 commit | `a350632c` (本 run の起点・コード変更は本 PR の新規ファイルのみ) |
| 素材 | `fl-win64`・`plugins-freshair` (fetch.sh: win 17 files, factory .epf 8)・`toolchain-retdec`・`toolchain-emsdk`・`work-icall`・`work-liftlib` |
| `tools/ott/native/build.sh` | OK |
| `tools/icall/fa_route_build.sh` | OK、5.2 s |
| `tools/icall/diff/fa_sweep.sh 8 60` | 131 関数、69.8 s、load 0.08 (開始時 `uptime`) |
| 区分 | bit 一致 47 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 9 (合計 131) |

注: 付録 1899 の測定 (bit 一致 46 / 値の不一致 10) とは 1 件ずつ違う。`wasm のみ err` は 9 件で一致し、対象 2 件 (180c8b280・181057b38) は両方とも wasm のみ err のまま。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 値 `0x400000004` を作る store (null ページを指すポインタの生成元) の特定 (`-DWVAL` 絞り込みの再実行では WCV 0 件で未取得) | BLK+0 が "emsc" に化ける原因。wasm のみ err 2 件 (本付録 §1) | #1998 (本 PR は Refs。残りは同 issue で継続) |
| IR 行 19132 → wasm 命令オフセットの対応 | 受入条件「wasm オフセットか IR 命令まで」の wasm 側 | 同上 |
| 引数付き lifted 関数の dispatch table 登録規則 | abort 6 件 (1852 付録 §2) | #1897 (ICALL-49) 既存 |

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

範囲外: 値 `0x400000004` の生成元は本付録では未特定。IR 行から wasm オフセットへの変換も未実施。`diff/fa_wc_drv.cjs` は work/ の drv.cjs と同一 (引数: `<fa_wc.cjs 絶対パス> <VA>`)。`diff/fa_wc_drv.cjs` は work/ の drv.cjs と同一 (引数: `<fa_wc.cjs 絶対パス> <VA>`)。
