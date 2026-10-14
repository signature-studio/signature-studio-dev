# #2566 REPORT — stage-1 を修正後の icall_rewrite で再生成し、入口 `_StartLib` の hinst を直す [PLG-P0b-21]

- 担当 issue: #2566 `[PLG-P0b-21]` (親 #2510)。前提 #2565 は CLOSED、修正 PR #2584 は 2026-10-14 15:56Z に merge 済み。#2604 は PM 判断 (既定方式 (c)) に従い、この前提で実施。
- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし (RetDec が memory-ABI の BLK slot を constant 化する類型は REPORT_2510 §6 の D24 候補)。

## 0. 結論 (1 行)

stage-1 の再生成 (RetDec 8 chunk) は 5 分 42 秒で完走し、BLK と再配置範囲の交差は 1 件 → 0 件になった。入口 `_StartLib` の hinst は 0 → `0x400000` に直った。stage-2 smoke は `Runtime error 203 at 0x1` (InitUnits 中) で FAIL のまま。受入 1・3・4 と 2・5 の残りは子 issue へ移す。

## 1. 検証起点と測定 commit

- 起点: `origin/main` `8fd940bb`。修正 commit (測定 commit): **`66a3dbe1`** (`fix(plugins): bind the DllMain spill to %arg1/%arg2 when BLK is zero-filled (#2566)`)。worktree `../ws-2566`・branch `2566-plg-p0b-21-relift`。
- 素材: `work-fw-stage1` を `tools/plugins/work/fw/` に、`work-liftlib` を `tools/liftlib/work/` に展開 (gitignore)。`fl-win64` は member 2 本だけを `$RUNNER_TEMP/fl-win64/extracted/` に展開 (`block18983_PE.bin`・`block00031_PE.bin`、各 2.5 秒以下)。`toolchain-retdec`・`toolchain-emsdk` は runner 既存の `[RETDEC]`・`[EMSDK]` (`docs/REFERENCES.md` §4) を使用。`plugins-ott` は未使用。
- 補助物: `fw_prep.py` が読む `tools/plugins/work/fw_hash_counts.json` は `{}` で代用 (framework 統計の出力のみに影響し、`F.ranges` は全 Balance 関数から作られるため件数は不変。確認: 11,736 件 = 旧 `fw_map.json` の `nfuncs`)。
- 実行環境: nproc 4・RAM 15 GiB。load average は今回のステップでは未計測。

## 2. 実測 (n=1)

| 手順 | commit | 結果 | 所要 (real) |
|---|---|---|---|
| `fw_prep.py` (F.ranges 再生成) | `8fd940bb` | 11,736 ranges | 21 s |
| `icall_rewrite.py` (main 版・#2584 を含む) | `8fd940bb` | rewrote 11,736 funcs / 6,159 sites・blk `8a1000`・`errors {}` | 24 s |
| `fw_lift.sh` (icall は再利用・RetDec 8 chunk・restore・merge) | `8fd940bb` | rc 0・`fw_all.restored.ll` 11,939 defines | 5 分 42 秒 |
| `fw_stage2.sh --fresh` (初回) | `8fd940bb` | rc 1 `entry_fix` の件数不一致 (`r8=0 r9=1`) | 9 分 09 秒 |
| `fw_stage2.sh` (修正後・増分) | **`66a3dbe1`** | `entry_fix r8=1 r9=1`・`_StartLib hinst=0x400000 reason=1`・`Runtime error 203 at 0x1`・`fw_smoke_check` FAIL (`init_reach` 未到達) | 40.8 秒 |

- 初回の `--fresh` は手順 1 の merge が `r2/r3` を先に要求するため rc 1 で止まった。旧 `r2/r3` を仮置きして再実行し、手順 2 で新 `r2/r3` に置き換えた (旧版は `tools/plugins/work/fw_pre2566/` に退避)。
- `fw_run.mjs` の `SMOKE PASS (Halt0/RestoreContext 到達)` 行は、`RestoreContext` 到達で通る経路の表示。判定の正は `fw_smoke_check.py` で、その結果は FAIL。

## 3. BLK 重なりの検査 (受入 1 の前段)

`fw_map.json` の `func_range_new` と `[blk, blk+0x280)` の交差 (REPORT_2510 §3.2 と同じ式)。

| artifact | blk | 交差 | section_size | nderef |
|---|---|---|---|---|
| 旧 (2026-10-10 生成・`tools/plugins/work/fw_pre2566/`) | `0x8a1000` | **1** (`0x494cf0` → `[0x8a0fe0, 0x8a1271)`) | `0x560e8d` | 12,658 |
| 再生成 (`66a3dbe1` の icall) | `0x8a1000` | **0** | `0x5a67fd` | 12,661 |

- 注意: セクションが `+0x45970` B 伸びた。これは #2584 の `place()` だけの効果とは断定できない。`tools/icall/icall_rewrite.py` は 10-12・10-13・10-14 に `4708059e` (jump table 展開) などで変わっており、旧 artifact との差はそれも含む。切り分けは未実施 (子 B)。

## 4. 入口関数の観測

| 項目 | 旧 IR (`fw6.restored.ll`) | 新 IR (`fw6.restored.ll`) |
|---|---|---|
| `ptrtoint ([2 x i8]* @1 to i32)` の行数 (受入 2 の 123 行) | **123** | **0** |
| `@global_var_8a10*` (BLK slot の constant global) | **4** | **0** |
| `load i64, i64* inttoptr (i64 90480xx ...)` (BLK 直読み) | 1,139 | 4,517 |

- 新 IR では BLK slot が定数 global にならず、BLK 直読みの `load` として残る。`"$"` 番地の fold が消えたのは、BLK 域を 0 埋めで再配置した結果と見られる。**機構 (なぜ RetDec が constant にしなくなったか) は未確認** (受入 5 → 子 B)。
- 入口 `function_6c13a0` (DllMain): 新 IR の spill は `store i64 %0, ptr %ce21` (`%0` = BLK+0x08 の load) と `store i64 %arg2` (reason)。C 側の引数 `%arg1`/`%arg2` を使わず BLK 経由で読むため、smoke harness (`fw_run.mjs`: `entry(IMAGE_BASE, 1, 0, 0)`・BLK 先頭 0x100 を 0 クリア) では `hinst=0x0` になった (修正前の観測)。
- 修正: `fw_entry_fix.py` に新形 fallback を追加 (r8 の spill の定義が `inttoptr 9048088` (BLK+0x18) なら値を `%arg1` に差し替える)。旧形の経路は変えない (旧 IR では `n8=1` が先に立つ)。修正後の `hinst=0x400000`・`reason=1` を smoke.log で確認。

## 5. 受入条件の状態 (issue #2566 の 5 項目)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. smoke `runerr=0 ff=0 init_reach=288` PASS | **未達** | §2: `fw_smoke_check` FAIL (`runerr 0`・`ff 0` は OK、`init_reach` 未到達)。InitUnits 中に `Runtime error 203 at 0x1` (原因未特定) → 子 A |
| 2. 入口分岐の `"$"` 定数式の消失と 123 行の内訳 | **部分** | 新 IR で 123 → 0 行 (§4)。消えた 123 行を BLK 由来と他由来に分けた内訳は未実施 → 子 B |
| 3. `init_reach` の直接呼出の計測 | **未達** | smoke が InitUnits まで進んでいないため計測不能 → 子 A |
| 4. n≥3 の実測 | **未達** (n=1 のみ) | §2 の 1 回のみ。n≥3 は受入 1 の PASS 後に測る → 子 B |
| 5. RetDec が BLK slot を constant にする機構 | **部分** | 観測 (§4): constant global は消え BLK 直読みになった。機構は未特定 → 子 B |

- 負のコントロール: 修正前 PE 由来の stage-2 は REPORT_2571 §3 で main 上 FAIL (`runerr=1`・`init_reach=16`) と測定済み。本 run では再測定していない (時間上限のため)。BLK 交差の旧 artifact 1 件 (§3) は本 run で再確認した。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| InitUnits 中の `Runtime error 203 at 0x1` (smoke FAIL の原因) と受入 1 (`init_reach=288`) | smoke PASS 不可 | 子 **A** = #3120 (本 issue の子・`親: #2566`) |
| 受入 2 の 123 行の内訳・受入 3 (init_reach 直接呼出)・受入 4 (n≥3)・受入 5 (constant 化の機構)・section 伸び `+0x45970` の切り分け | 修復の効果の確定 | 子 **B** = #3121 (本 issue の子・`親: #2566`) |
| `fw_prep.py` の `fw_hash_counts.json` 依存 (本 run は `{}` で代用) | 再現時に framework 統計が変わる | 子 B の本文に記載 |

## 7. 再現手順

```sh
git worktree add ../ws-2566 -b 2566-plg-p0b-21-relift origin/main
cd ../ws-2566 && tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
D=$RUNNER_TEMP/fl-win64; mkdir -p $D && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $D extracted/block18983_PE.bin extracted/block00031_PE.bin
echo '{}' > tools/plugins/work/fw_hash_counts.json
FL_WIN64_DIR=$D python3 tools/plugins/framework/fw_prep.py
cd tools/plugins/work/fw && python3 ../../../icall/icall_rewrite.py --pe $D/extracted/block18983_PE.bin --funcs F.ranges --out fw_icall.dll --map fw_map.json
cd ../../../.. && FL_WIN64_DIR=$D bash tools/plugins/framework/fw_lift.sh      # 5 分 42 秒
bash tools/plugins/framework/fw_stage2.sh --fresh                                # 初回は r2/r3 を仮置きして再実行 (§2)
python3 tools/plugins/framework/fw_smoke_check.py --log tools/plugins/work/fw/smoke.log --wasm tools/plugins/work/fw/fw_route.wasm --size 0
```

## 8. コード差分 (測定 commit 以降)

測定 commit `66a3dbe1` 以降のコード変更は無し (本 PR の追記は REPORT と DOC_MAP のみ)。

```sh
git diff 66a3dbe1 HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'   # 空 = 実行コード差分 0
```
