# #4143 REPORT — 現行 main の stage-2 失敗は `203` ではなく `0x10000538` (7155712 への直接 store)・BLK+0x10 に 203 は書かれない [PLG-P0b-44]

- 担当 issue: #4143 `[PLG-P0b-44]` (親 #3187・元の親 #3150)。
- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし。

## 0. 結論

- 受入 1 の前提「BLK+0x10 へ `203` を書く store」は、現行 main の stage-2 では**存在しない**。動的ダンプ (BLK+0x10 の全 store 約 99 件・実行中の値) に `203` は 1 件も無く、IR 上の定数 store も 0 件 (`fw_blk_writers.py`・REPORT_3150 §3 と一致)。
- 現行の失敗 (`Runtime 268436792 at 0000000010000710`) の数値 `268436792` = `0x10000538` は、BLK+0x10 ではなく**番地 7155712 (`0x6d3000`) への `store i32` が 1 回書く値**。書込み元は `fw_flat4_canon3.ll` の 36405 行 (`function_40e400`・native ラベル `dec_label_pc_7bad20`)。値は `ptrtoint ptr @253 to i32` で、定数 `@253` が `0x10000538` に解決される。
- 7155720 (`0x6d3008`・`fw_blk_writers.py` の ERRCODE) へは `function_4072b0` の 9593 行が `@498` (`0x10000710`) を書く。
- よって REPORT_3150 §0 と #4143 本文の `203 at 0x1` は、stage-1 の旧測定 (`8d8d0e6a` 時点) の値で、現行 main の失敗形ではない。受入 1 は**未達** (対象が存在しない)。判定は PM に委ねる (§6)。

## 1. 測定

- 測定 commit: **`75a400c4f`** (origin/main・枝 `4143-plg-p0b-44` の起点。stage-2 のパイプラインのコードは変更していない)。
- 素材: `work-fw-stage1`・`work-liftlib`・`fl-win64` (block18983/00031) を `$HOME/artifacts` から展開。`fl-win64` のみ `$RUNNER_TEMP/fl-win64` へ展開。
- stage-1 (RetDec 8 chunk) は**再実行していない**。`work-fw-stage1` の `r2`/`r3.restored.ll`・`fw_icall.dll`・`fw_map.json` を再利用。`fw_stage2.sh` は `--fresh` なしで実行 (`fw_all8.ll` 等の merge 中間は素材に無いため再生成される)。
- 実行環境: runner 4 vCPU・RAM 15 GiB。load は stage-2 終了時点で 2.04 1.98 1.00。

| 手順 | 結果 | 所要 (real) | load (1 分値) |
|---|---|---|---|
| `fw_prep.py` | rc 0・landmark は FastMM_mmgr のみ matched=False (REPORT_3150 §1 と同じ) | 37.5 秒 | — |
| `fw_stage2.sh` (`--fresh` なし・stage-1 再利用) | rc 1・`fw_smoke_check` FAIL: `runerr=1`・`init_reach=16`・`ff=0` | 7 分 16 秒 | 終了時 2.04 |

- 基準との一致: `smoke.log` 29 行目 `[fw][MessageBoxA] Error: Runtime 268436792 at 0000000010000710`、`init_reach=16`。issue の基準 (main smoke) と一致。
- `203` の Error 行は出ていない。

## 2. 動的ダンプ (受入 1)

計装: `fw_blk10_probe.py` が `fw_flat4_canon3.ll` の整数・ポインタ store のうち、番地が BLK+0x10 (9048080)・7155712・7155720 のものの直前に `call void @fw_dbg_blk10(i64 V, i32 行)` を挿入する (挿入 34,596 件)。`fw_blk10_probe.c` が `[blk10] line=<IR 行> val=<値>` を stderr に出す。ビルドは `fw_stage2.sh` の emcc 行と同一フラグ (入力の .ll だけ差し替え)。baseline の `fw_route.*` は触らない。

| 項目 | 結果 |
|---|---|
| probe 挿入 | 34,596 件 (`probe_map.json` に IR 行・関数・native ラベル・store の原文) |
| probed wasm の build | rc 0・16 秒 |
| probed smoke | `Runtime 268436792 at 0000000010000710` (baseline と同じ)・`SMOKE PASS (Halt0/RestoreContext 到達)` の行は baseline と同じ・`[blk10]` 102 行 |
| BLK+0x10 へ書かれた値 (99 件) | すべて wasm アドレス (`0x10000xxx`・`0x100008b0` 等) か小整数。**`203` は 0 件** |
| 7155720 (ERRCODE) へ書かれた値 | `268437264` (=`0x10000710`・9593 行 `function_4072b0`) と `0` の 2 件 |
| 7155712 へ書かれた値 | `268436792` (=`0x10000538`) の 1 件 (36405 行) |

- 36405 行 (`function_40e400`・native `7bad20`): `%ce5n11_function_40e400 = ptrtoint ptr @253 to i32` → `store i32 %ce5n11_function_40e400, ptr inttoptr (i64 7155712 to ptr)`。直後に BLK+0x8 ← `@253`、BLK+0x10 ← `@252`、BLK+0x18 ← `@251` を格納して `function_40e270` (Halt) を呼ぶ。`function_40e400` は RunError の経路で、ここが失敗の書込み元。
- 最後の BLK+0x10 store (失敗直前): 35863 行 (`function_40e270`・native `7ba7a1`) の `@154` の番地 `0x10000460`。BLK+0x10 は失敗値の格納先ではない。

## 3. 受入条件の状態 (issue #4143)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. BLK+0x10 へ 203 を書く store の IR 行と native 番地 | **未達** (対象が無い) | §2: 実行中の BLK+0x10 の値に 203 は無く、IR の定数 store も 0 件。代わりに失敗コードの書込み元 (36405 行・native `7bad20`) を特定 |

## 4. 観測欠陥・注意

- `fw_blk_writers.py --fn function_405670` の 0 行 (REPORT_3150 §3) は、inline 形の store を数えていなかった集計の差と推定 (未確認)。実行時には `function_405670` (FastMM_GetMem) が BLK+0x10 へ `0x20000c8` (3469 行 `%ce81n11_function_405670`) を 1 回書く。これは失敗値ではない。
- `fw_smoke_check` の `runerr` 判定は現行 main で `runerr=1` を正しく数える (REPORT_3186 で修正済み)。
- 旧 REPORT_3150 §0・§3 の `203` の記述は現行 main と食い違う。修正は本 PR の範囲外 (下の未解決表)。

## 5. 再現手順

```sh
git worktree add ../ws-4143 -b 4143-plg-p0b-44 origin/main
cd ../ws-4143
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
D=$RUNNER_TEMP/fl-win64; mkdir -p $D && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $D extracted/block18983_PE.bin extracted/block00031_PE.bin
echo '{}' > tools/plugins/work/fw_hash_counts.json
FL_WIN64_DIR=$D python3 tools/plugins/framework/fw_prep.py
FL_WIN64_DIR=$D TMPDIR=$RUNNER_TEMP bash tools/plugins/framework/fw_stage2.sh     # rc 1 (baseline)
cd tools/plugins/work/fw
python3 ../../framework/fw_blk10_probe.py fw_flat4_canon3.ll --out probe.ll --map probe_map.json
cp ../../framework/fw_blk10_probe.c .
# emcc 行は fw_stage2.sh の 17 行目と同一フラグ。入力を probe.ll と fw_blk10_probe.c に差し替えて probe_route.cjs を作る
node ../../framework/fw_run.mjs $PWD/fw_image.bin $PWD/probe_route.cjs > probe_smoke.log 2>&1
grep '\[blk10\]' probe_smoke.log | grep 'val=268436792 '
```

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1 の前提 (BLK+0x10 の 203) が現行 main に無い。issue の基準・受入の書き換え、または #4143 の範囲縮小 | 受入 1 | PM 判断 (親 #3187) |
| 失敗コード `0x10000538` の書込み元は確定 (36405 行)。しかし、その値の流れ (`@253` の由来と RunError 経路の分岐) は未調査 | 次の失敗の原因特定 | PM 判断 (親 #3187 の子として起票するかどうか) |
| REPORT_3150 §0・§3 の `203` 記述の修正 | 文書の正確さ | 本 PR に含めない (REPORT_3150 は別作業で修正) |
