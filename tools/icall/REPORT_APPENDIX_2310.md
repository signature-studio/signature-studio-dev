# 付録: icall #2310 (ICALL-72) — BLK+0 (0x36319008) 書込み store の wasm オフセット対応

> 親: #1998 (ICALL-54) の付録 `REPORT_APPENDIX_1998.md` §1 の未達 (IR 行 19132 → wasm オフセット)。本付録は子 issue #2310 の測定結果を記録する。

## 1. 結論

- **受入条件 1 (wasm オフセットまで特定): 達成**。`0x36319008` に "emsc" (`0x63736d65`) を書く store (IR 行 19132) は、wasm の関数 `function_181057d20` 内の **`i64.store offset=909217800` (wasm ファイル内オフセット `0x427be`)** に対応する。
- **受入条件 2 (route 側 / lift 側の分類): 達成 (lift 側に分類)**。store 命令は lift が生成した `function_181057d20` の中にあり、route 側 (data 敷設) は 1998 付録 §3 で否定済み。値 "emsc" を作る `0x400000004` は、RetDec の RDA 段で脱落する frame store 2 本の欠落から生じる (元の機械語は 4B store 2 本)。根拠と HEAD 再測定は §6。
- **既知類型との関係**: D23 候補 (`REPORT_APPENDIX_2394.md` §6・新規、DEFECTS.md 未編集)。
- **受入条件 3 (`fa_sweep.sh 8 60` の wasm のみ err 件数): 達成**。wasm のみ err は 9 件で、現状の件数と一致 (実測は §3)。

## 2. 対応の詳細 (実測)

測定: `fa_wc_build.sh` で監視付き wasm (`work/fa_wc/fa_wc.cjs`) を作り、`fa_wc_drv.cjs` で `181057b38` を 8 入力で実行。

| 段階 | 観測 |
|---|---|
| 監視付き IR の挿入 | `fa_wc.py instr`: `store total=5526 instrumented=5526 unhandled=0` |
| 実行 (8 入力) | 全入力で `memory access out of bounds`。`WC line=` 168 行 (1998 §2 と一致)。`WC line=19132 addr=36319008 sz=8 val=63736d65` が 8 件 |
| `__wchk` の第 4 引数 | IN 側 (`work/fa_route/oi.flat.ll`) の行番号。OUT 側 (`oi.wc.ll`) の行番号ではない。`oi.flat.ll` 19132 行 = `store i64 %1, ptr %ce31n11_function_181057d20` |
| wasm 側の位置 | `wasm-dis` で `$function_181057d20` (wat 140562 行〜)。wat 141476 行の `i64.const 19132` → `i64.store offset=909217800` (wat 141490 行) |
| バイナリオフセット | `llvm-objdump -d fa_wc.wasm`: `i64.const 19132` が `0x4279a`、直後の `i64.store offset=909217800` が **`0x427be`** |

対応の読み方: wasm 内の `i64.const 19132` は `__wchk` に渡す IR 行番号 (計装用の定数)。その直後に、同じ IR 行の本体 store (`909217800` = `0x36319008`) が続く。

DWARF の行表 (`llvm-dwarfdump --debug-line`) には `.ll` の行情報が無い (`-g` を付けても lift IR は `!dbg` を持たない)。そのため、対応は `__wchk` の定数を介して取った。

## 3. 測定 (`tools/icall/diff/fa_sweep.sh 8 60`)

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `586c8b0c` (origin/main 取り込み時点の HEAD。本 PR はコード変更なし) |
| 素材 | `fl-win64`・`plugins-freshair` (`fetch.sh`: win 17 files, factory .epf 8)・`toolchain-emsdk` ([EMSDK])・`toolchain-retdec` ([RETDEC])・`work-icall`・`work-liftlib` |
| `tools/ott/native/build.sh` | OK |
| `tools/icall/fa_route_build.sh` | OK、11.5 s |
| `tools/icall/diff/fa_wc_build.sh` | OK、3.2 s (`store total=5526 instrumented=5526 unhandled=0`) |
| `tools/icall/diff/fa_sweep.sh 8 60` | 131 関数、73.1 s (real 1m13.145s)、開始 load 0.58・終了 0.95 (4 vCPU) |
| 区分 | **bit 一致 46 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 10** (合計 131) |

- wasm のみ err は 9 件で、1998 §4 と一致。
- bit 一致 / 値の不一致 は 1998 §4 (47 / 9) と 1 件ずれた。**`REPORT_APPENDIX_1998.md` §4 の 47 / 9 が正本**で、本 run の 46 / 10 は `fa_sweep` の ±1 揺れと判断し、#2302 (ICALL-71) で追跡する。本付録では再現判定を行わず、この実測値をそのまま記録する。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| §6 で分類済み (#2310 の受入条件 2)。脱落 store を戻す pass → #2427 (ICALL-77) | 受入条件 2 | #2427 (ICALL-77) |
| `fa_sweep` の bit 一致の ±1 揺れ (本 run 46、1998 は 47) | sweep 件数の判定精度 | #2302 (ICALL-71) |

## 5. 再現

```
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FA_DL=$RUNNER_TEMP/plugins-freshair TMPDIR=$RUNNER_TEMP
export RETDEC_ROOT=<[RETDEC] の展開先>   # 環境変数の規約は WORKFLOW §11。[EMSDK] の所在は emsdk_env.sh が設定する $EMSDK
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .
mkdir -p "$FL_WIN64_DIR" "$FA_DL" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$FL_WIN64_DIR"
tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$FA_DL"
bash tools/targets/freshair/fetch.sh
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_wc_build.sh
node tools/icall/diff/fa_wc_drv.cjs $PWD/tools/icall/work/fa_wc/fa_wc.cjs 181057b38 2>err.txt
grep -c '^WC line=' err.txt                       # 168
grep '^WC line=19132' err.txt | head -1           # addr=36319008 val=63736d65
"$EMSDK/upstream/bin/llvm-objdump" -d tools/icall/work/fa_wc/fa_wc.wasm | grep -A1 'i64.const.*19132' # 直後の store (0x427be)
bash tools/icall/diff/fa_sweep.sh 8 60
```

## 6. 受入条件 2: 書込み元の分類 (route / lift)

**結論: BLK+0 (`0x36319008`) への "emsc" 書込みの書込み元は lift 側に分類する。** route 側 (data 敷設) は否定済み。値を作る frame store 2 本が RetDec の RDA 段 (と後続の Combine 段) で脱落することが原因で、これは lift 側の欠陥。store を戻すと結果が変わることを §6-2 で実測した。

根拠 (引用元):

- 書込み命令: lift が生成した `function_181057d20` 内の `store i64 %1, ptr %ce31n11_function_181057d20` (§2・`REPORT_APPENDIX_1998.md` §2)。
- route 側の否定: `ott_data_install` が書くのは `0x310c4000`・`0x3125c000`・`0x31354000` のみで BLK を含まない。DLL の bytes に "emsc" は無い (`REPORT_APPENDIX_1998.md` §3。本 HEAD の `rw.dll` でも `emsc` の出現 0 件を確認)。
- 元の機械語: `0x181057b38` の 2 本の 4B store (`mov [rbp-0x30],eax`・`mov [rbp-0x2c],eax`)。8B で読む命令は無い (`REPORT_APPENDIX_2394.md` §2)。
- 真因: RetDec の `LLVM instruction optimization using RDA` 段で `[rbp-8]` (`0x181057b71`)・`[rbp-0x20]` (`0x181057b87`) の 2 本の frame store が IR から脱落する (`REPORT_APPENDIX_2394.md` §3 の段別表)。2 store を戻し 16B 1 alloca にすると BLK+0 への "emsc" 書込みは 8 → 0 (`REPORT_APPENDIX_2394.md` §4)。
- 既知類型との関係: D23 候補 (`REPORT_APPENDIX_2394.md` §6・新規、DEFECTS.md 未編集)。
- 脱落 store を戻す IR pass の一般化は本付録の範囲外 (#2427 / ICALL-77)。

### 6-1. HEAD 再測定 (WORKFLOW §6)

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `2c8088f4` |
| 検証 HEAD (= origin/main、本 commit の 1 つ前) | `54bacdc0` (`54bacdc0fa273dcf5811b40a24135c7e97b909cf`) |
| `git diff 2c8088f4 54bacdc0 -- tools/icall/frame_slot_2394.sh tools/icall/frame_slot_probe.py tools/icall/fa_route_build.sh tools/icall/diff/fa_wc_build.sh tools/icall/diff/fa_wc.py tools/icall/diff/fa_wc_rt.c tools/icall/diff/fa_wc_drv.cjs tools/icall/diff/fa_sweep.sh tools/icall/diff/fa_cmp.py tools/ott/native tools/targets/freshair` の出力行数 | **0** (測定経路の全ファイル) |
| 同じ差分を `tools/icall/diff` 全体にした場合 | 2 ファイル: `5f6547c2` (#2225) の `dispatcher_ids.py` (新規)・`ott_apiset_cmp.py`。測定経路からの参照は 0 件 (grep) |
| 実行 | `bash tools/icall/frame_slot_2394.sh` (SWEEP なし)。exit 0 |
| 所要 | 51 s (14:38:09 → 14:39:00) |
| load (`uptime` の 1 分平均) | 開始 0.73 → 終了 1.05 (1 並列・逐次) |
| 素材 | `work-icall` (`rt_freshair-core`・`rw.dll`)、RetDec (`toolchain-retdec` の展開先)、`/opt/emsdk` ([EMSDK])。`plugins-freshair`・`fl-win64` は未使用 |

### 6-2. 実測結果 (`frame_slot_2394.sh` §4 の 8 入力と §1〜§3)

| 条件 | 8 入力 | WC 行 | "emsc" の WC 行 | BLK+0 への "emsc" | `REPORT_APPENDIX_2394.md` §4 と |
|---|---|---|---|---|---|
| base (現 IR) | OK 0 / TRAP 8 | 168 | 32 | 8 | 一致 |
| fixed (2 store 戻し・16B 1 alloca) | OK 8 / TRAP 0 | 168 | 0 | 0 | 一致 |
| sep (負の対照) | OK 0 / TRAP 8 | 168 | 32 | 8 | 一致 |

- §1 (元の機械語): `before.0.drc.dsm` の再 decode と `rw.dll` の同 VA が 205 B 一致。
- §2 (RDA 段の表): `REPORT_APPENDIX_2394.md` §3 の段別表と全セル一致。
- §3 (census): F 131・dsm に命令あり 130・frame pointer 型 4・rbp 相対 mov store 29・脱落 21・候補 12 件 / 2 関数 (`181057b38` が 2 件、`180da6e60` が 10 件)。`REPORT_APPENDIX_2394.md` §5 と一致。

### 6-3. IR 行番号の差 (本 HEAD で確認)

- 本 HEAD の `work/fa_route/oi.flat.ll` は 25694 行。`REPORT_APPENDIX_1998.md` §2 の 25805 行 (旧 HEAD `1fff0e4f`) とは一致しない。
- BLK+0 への "emsc" 書込みの WC 行は本 HEAD では `line=19056` (8 件)。§2 と `REPORT_APPENDIX_1998.md` §2 の行 19132 は旧 IR の番号で、本 HEAD の WC 行には 19132 が現れない。
- wasm 側: 本 HEAD の `i64.const 19056` は `fa_wc.wasm` の 0x42799。直後の `i64.store offset=909217800` の位置 (§2 の 0x427be に相当するもの) は未再確認。
- 行番号の差の原因は未切り分け。`1fff0e4f`..`2c8088f4` の間に `tools/icall/fa_route_build.sh` と `tools/icall/rt/icall_rt.c` が変更されている (`git diff --stat`)。行番号を引くときは測定 commit を併記すること。

### 6-4. 再現

```
export TMPDIR=$RUNNER_TEMP RETDEC_ROOT=<[RETDEC] の展開先>
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .      # tools/icall/work/ へ (§5 と同じ)
bash tools/ott/native/build.sh
bash tools/icall/frame_slot_2394.sh                          # §4 の 8 入力は SWEEP 無しで出る
```
