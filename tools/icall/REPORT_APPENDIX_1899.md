# 付録: icall #1899 (ICALL-50) — Fresh Air SlateCore の wasm out of bounds 2 件の trap 位置

> 親: #1852 (ICALL-44) の付録 `REPORT_APPENDIX_1852.md` §2 の未確定 2 件。本付録は子 issue #1899 の測定結果を記録する。

## 1. 結論

- **trap 位置は 2 件とも確定した** (wasm 命令オフセットまで)。
  - 181057b38: `181057b38 → 181057a90 → 181057d20 → 18106632c` の呼出し連鎖の末端 `18106632c` の wasm オフセット `0x2700e` (`i32.load`)。アドレスは `BLK+0` (`0x36319008`) の値 + 16。trap 時点で `BLK+0` は `0x63736d65` ("emsc") になっており、初期値 0 から書き換えられている。
  - 180c8b280: 入力 #3・#6 (seed 3) で、呼出し先 `function_180c8b310` (引数付き関数) の wasm オフセット `0x14475` (`i32.load`) が trap する。180c8b280 自身は引数無し・table 登録済みで、直接呼出し先が引数付きの 180c8b310。
- **分類は lift 側** (`REPORT_APPENDIX_2310.md` §6)。
- 本測定で 181057b38 は 8/8 入力、180c8b280 は 2/8 入力で trap する (再現性あり)。

## 2. trap 位置の詳細

測定: `tools/icall/work/fa_route/fa_route.cjs` を node で直接ロードし、`fa_cmp.py` と同じ入力 (seed 3 の `random.uniform(-4,4)` 8 個、`rcx..r9` = `_malloc(0x400)`) で実行。

| 対象 | 入力 | trap する wasm 関数 (オフセット) | 命令 | 実行時の状態 |
|---|---|---|---|---|
| 181057b38 | 全 8 入力 | `function_18106632c` (0x2700e) | `i32.load 0` (アドレス = `local1 + 16`、`local1 = i64.load [0x36319008]`) | 入力前 `BLK+0` = 0 → trap 時 `0x63736d65` ("emsc") |
| 180c8b280 | #3・#6 のみ | `function_180c8b310` (0x14475) | `i32.load 0` (アドレス = `local345 + 8`、`local345` は直前の `i64.load [mem+1056]`) | 入力 #0〜#2 は OK、#3 で trap、#4〜#5 は OK、#6 で trap、#7 は OK |

補足 (実測済み):
- 181057b38: trap 時の `0x36319000` 起点 64 byte は `"emsc"` (2 回) と `0x10_0000_0000 台` の値 (`a8f34a10`・`b0f34a10` 由来のポインタ様の値) を含む。`"emsc"` の由来は未特定。
- 181057b38 の BLK 書き換えは、`ott_data_install` (`fa_data.c`) が敷設する `0x310c4000`・`0x3125c000`・`0x31354000` (いずれも `0x36319000` を含まない) では説明できない。ただし `fa_data.c` 内の `"emsc"` 有無は未確認。
- 180c8b310 の 0x14475 の `i32.load` は、`local345` (直前の `i64.load offset=1056` の結果) + 8 を読む。`local345` の値は未取得で、`0x36319420` が基点かは未確認 (BLK 相対とは断定しない)。
- 180c8b310 の入力 #3 で trap する時点の `i64.load offset=1056` の基点は `local345` (引数付き関数の状態ポインタ) で、BLK (`0x36319000`) の直接の値ではない。

## 3. 測定

| 項目 | 値 |
|---|---|
| 測定 commit | `e5e3c7c2` (origin/main 取り込み後・コード変更なし。worktree `ws-1899`) |
| 素材 | `fl-win64`・`plugins-freshair` (`fetch.sh`: win 17 files, factory .epf 8)・`toolchain-retdec`・`toolchain-emsdk`・`work-icall`・`work-liftlib` を展開 |
| `tools/ott/native/build.sh` | OK、0.5 s |
| `tools/icall/fa_route_build.sh` | OK、9.7 s (`fa_route.cjs` 生成) |
| `tools/icall/diff/fa_sweep.sh 8 60` | 131 関数、73.3 s、load 0.01 (開始時 `uptime`) |
| 区分 | bit 一致 46 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 10 (合計 131) |

注意: 付録 1852 の測定 (141 関数・53 / 73 / 9 / 6) とは母数が違う (本 run の `map.json` の `func_map` は 131)。`wasm のみ err` は 9 件で一致し、対象 2 件 (180c8b280・181057b38) は両方とも wasm のみ err のまま。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 脱落 store を戻す pass (#2427 → #2514 で merge 済み。残件は #2508) | wasm のみ err 2 件 (本付録 §1)、分類は lift 側 (`REPORT_APPENDIX_2310.md` §6) | 分類 #2310 (完了) / 修復 #2427 (ICALL-77・CLOSED、実装 #2514) / 残件 #2508 (ICALL-78) |
| 引数付き lifted 関数を dispatch table に載せる規則 | abort 6 件 (1852 付録 §2) | #1897 (ICALL-49) 既存 |

> 注: route 側 = data 敷設 (`REPORT_APPENDIX_1998.md` §3 で否定)。memory shift・heap 配置は個別には測っていない。本表から memory shift の候補は消えている (`REPORT_APPENDIX_2310.md` §6)。

## 5. 再現

```
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FA_DL=$RUNNER_TEMP/plugins-freshair RETDEC_ROOT=$HOME/retdec
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
python3 tools/icall/diff/fa_cmp.py 181057b38 --n 8    # wasm_err 8
python3 tools/icall/diff/fa_cmp.py 180c8b280 --n 8    # wasm_err 2 (#3・#6)
```

trap 位置の取り方: `node` で `fa_route.cjs` を読み、`try/catch` で `e.stack` を出す。命令の特定は `wasm-dis` (関数名) と `llvm-objdump -d fa_route.wasm` (オフセット) を使う。
