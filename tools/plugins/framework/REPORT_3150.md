# #3150 REPORT — `Runtime error 203 at 0x1` の書込み元は未特定 (IR 上の候補と観測欠陥 2 件を特定) [PLG-P0b-31]

- 担当 issue: #3150 `[PLG-P0b-31]` (親 #3120)。前回の作業は PR #3152 (枝 `3120-plg-p0b-29-stage2-smoke`・open・未 merge)。本 PR は main (`8d8d0e6a`) 起点の枝 `3150-plg-p0b-31-blk-writers` で、#3152 には積み上げていない。
- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし (REPORT_3120 §0 と同じ)。

## 0. 結論 (1 行)

main 起点で stage-1 を再生成して stage-2 を再現すると REPORT_3120 と同じ `Runtime error 203 at 0000000000000001` (InitUnits 中・smoke.log 27 行目) で FAIL した。203 を書く定数 store は IR に 0 件で、書込み元は未特定 (受入 1・2 は未達)。after-exit の情報値 0 の原因は `fw_stage2.sh:209` の `EXIT_RUNTIME=1` と特定 (受入 3)。加えて `fw_smoke_check` の `runerr` 判定が今回の失敗を数えていない (正規表現の不一致) ことを確認した。

## 1. 測定

- 測定 commit: **`8d8d0e6a`** (origin/main・枝 `3150-plg-p0b-31-blk-writers` の起点。パイプラインのコードは変更していない)。
- 素材: `work-fw-stage1`・`work-liftlib` を展開。`fl-win64` は member 2 本 (`extracted/block18983_PE.bin`・`extracted/block00031_PE.bin`) のみ `$RUNNER_TEMP/fl-win64` へ展開。
- 実行環境: runner 4 vCPU・RAM 15 GiB。

| 手順 | 結果 | 所要 (real) | load (1 分値) |
|---|---|---|---|
| `fw_prep.py` | rc 0・landmark は表示の末尾 8 件を確認 (FastMM_mmgr のみ matched=False) | 37.7 秒 | — |
| `icall_rewrite.py` (BLK は `8a1000`) | rewrote 11,736 funcs / 6,159 sites・`errors {}`・section +5,924,861 B | 26.5 秒 | — |
| `fw_lift.sh` (stage-1・RetDec 8 chunk) | rc 0・`fw_all.restored.ll` 11,939 defines | 8 分 24 秒 | — |
| `fw_stage2.sh --fresh` | rc 1・`entry_fix r8=1 r9=1`・`_StartLib hinst=0x400000 reason=1`・`Runtime error 203 at 0x1`・`fw_smoke_check` FAIL | 14 分 3 秒 | 開始 0.91 → 終了 2.34 |

- `fw_smoke_check`: `init_reach got=13 expect=288` で FAIL。`runerr got=0` と表示されるが、これは §4 の観測欠陥による誤判定 (ログには `Runtime error 203` が 1 件ある)。`ff=0` は OK。
- 所要は REPORT_3120 (lift 5 分 50 秒・stage-2 9 分 30 秒) より長い。同じ手順・同じ素材で、負荷の差による。

## 2. 再現ログ (smoke.log)

- 27 行目: `[fw][MessageBoxA] Error: Runtime error 203 at 0000000000000001` (REPORT_3120 §2 と同じ行)。直前の 26 行目は `[dispatch] site=0x40701e -> target=0x405670` (`FastMM_GetMem`)。
- 以降は InitUnits が続き、`[fw][RestoreContext] SEH unwind 到達` で終了。

## 3. IR 上の BLK 書込み (受入 1・未達)

対象 `tools/plugins/work/fw/fw_flat4_canon3.ll` (1,934,620 行)。集計は `tools/plugins/framework/fw_blk_writers.py` (本 PR で追加)。

- BLK+0x8 (9048072)・BLK+0x10 (9048080) を指す inttoptr 経由の store: 71,904 件。
- **定数 `i64 203` の出現は 0 件**。203 は定数 store では書かれていない。実行時に計算された値 (または読込んだ値) が BLK+0x10 に入る。
- 定数 `1` の store: BLK+0x8 が 15 件、BLK+0x10 が 487 件。237 関数に分散しており、BLK は全関数共通のスクラッチとして使われる。単一の書込み元には絞れない。
- エラーコード格納先 `7155720` (BLK+0x10 の値を読んで格納するのは `function_4072b0`・10041 行。REPORT_3120 §4 の静的読み)。`function_40e420` (39490 行〜) は `%arg1` を格納して `function_40e400` を呼ぶ (39512 行)。
- 動的 trace の直前に呼ばれた `function_405670` (`FastMM_GetMem`・2384〜3202 行) の BLK store は 14 件。値は全て計算結果で、定数ではない。候補 (未検証): 2716 行 (`and %157, 4294967295` → BLK+0x10)・3118 行 (`zext i32 %342` → BLK+0x10)・2883/3169 行 (`and %11, 536870911` → BLK+0x10)。どれが 203 を運ぶかは、実行時に値をダンプするまで確定できない。

## 4. 観測欠陥 2 件 (受入 3 の原因・判定の誤り)

| 欠陥 | 箇所 | 影響 |
|---|---|---|
| after-exit の情報値 0 | `tools/plugins/framework/fw_stage2.sh:209` の `-sEXIT_RUNTIME=1`。`RestoreContext` の後に main が戻ってランタイムが終了し、その後の `fw_dispatch_count`・`fw_va_calls`・`fw_alloc_count`・`fw_ff_count` の呼出しが `called after runtime exit` で assert して 0 になる | `dispatch / va / heap / ff` の情報値が使えない (受入 3 の答え)。修正は `NO_EXIT_RUNTIME` 系 (子 issue) |
| `runerr` の判定漏れ | `tools/plugins/framework/fw_smoke_check.py:33` の `RUNERR_RE` が `Error: Runtime (\d+) at` で、実ログの `Runtime error 203 at` に一致しない | 今回の RunError を `runerr=0` と数える。REPORT_3120 は `runerr=1` と記している。今回の main の checker は 0 を出すため、判定の根拠が違う |

## 5. 切り分け (受入 2・未実施)

- 2 つの素材の差 (BLK 配置 #2584・stage-1 再生成・`66a3dbe1` の entry fallback) を 1 つずつ戻す stage-2 は、1 本 14 分かかる。本 run の時間内では実施できなかった。子 issue へ移す。

## 6. 受入条件の状態 (issue #3150)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. BLK+0x10=203・BLK+0x8=1 の書込み元 (IR 行・番地) | 未達 | §3 (定数 203 は 0 件・候補のみ) |
| 2. #2584・stage-1・`66a3dbe1` の切り分け | 未達 | §5 (未実施) |
| 3. after-exit で情報値が 0 になる原因 | 達成 | §4 (`fw_stage2.sh:209` の `EXIT_RUNTIME=1`) |
| 4. 受入 1 の修正 (別 issue) | 該当なし | 修正は行っていない |

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 203・1 の動的な書込み元 (§3 の候補を実行時にダンプ) と、§5 の 1 変更ずつの切り分け | 受入 1・2 | #3187 `[PLG-P0b-33]` (`親: #3150`) |
| `fw_smoke_check` の `RUNERR_RE` 修正 (§4 の 2 件目) と、`EXIT_RUNTIME` の情報値取得 (§4 の 1 件目) | 判定の誤り・情報値 0 | #3186 `[PLG-P0b-32]` (`親: #3150`) |

## 8. 再現手順

```sh
git worktree add ../ws-3150 -b 3150-plg-p0b-31-blk-writers origin/main
cd ../ws-3150
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
D=$RUNNER_TEMP/fl-win64; mkdir -p $D && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $D extracted/block18983_PE.bin extracted/block00031_PE.bin
echo '{}' > tools/plugins/work/fw_hash_counts.json
FL_WIN64_DIR=$D python3 tools/plugins/framework/fw_prep.py
cd tools/plugins/work/fw && python3 ../../../icall/icall_rewrite.py --pe $D/extracted/block18983_PE.bin --funcs F.ranges --out fw_icall.dll --map fw_map.json
cd ../../../.. && FL_WIN64_DIR=$D bash tools/plugins/framework/fw_lift.sh
FL_WIN64_DIR=$D TMPDIR=$RUNNER_TEMP bash tools/plugins/framework/fw_stage2.sh --fresh   # rc 1
python3 tools/plugins/framework/fw_blk_writers.py tools/plugins/work/fw/fw_flat4_canon3.ll
python3 tools/plugins/framework/fw_blk_writers.py tools/plugins/work/fw/fw_flat4_canon3.ll --fn function_405670
```

## 9. コード差分 (測定 commit 以降)

測定 commit `8d8d0e6a` 以降に追加するのは解析スクリプト `tools/plugins/framework/fw_blk_writers.py` のみ。パイプライン (`fw_*.sh`・`icall_rewrite.py`) は参照しない。

```sh
git diff 8d8d0e6a HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'
#  A tools/plugins/framework/fw_blk_writers.py   (解析専用・stage-1/2 の出力に影響しない)
```
