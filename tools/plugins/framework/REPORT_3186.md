# #3186 REPORT — smoke 判定の RunError 正規表現と after-exit の情報値 [PLG-P0b-32]

- 担当 issue: #3186 (親 #3150)。測定 commit: **`f58467d6`** (コードを変えた最後の commit。以降の差分は本 REPORT だけ)。
- 修正前の基点: `150a83fa` (測定時の origin/main) と `8d8d0e6a` (#3150 の起点)。

## 0. 結論

- `RUNERR_RE` は `Runtime error N at ADDR` を数える。#3150 の 27 行目の原文を fixture にして runerr=1 を確認。規則を壊すと落ちるテストを追加 (§2)。
- `fw_stage2.sh` の emcc を `EXIT_RUNTIME=0` にした。ただし本素材では情報値は修正前も非 0 で、after-exit の assert は観測されなかった。修正の効果は実測で示せていない。
- #3150 の実再現 (`Runtime error 203 at 0000000000000001`・情報値 0) は、本測定の素材 (`work-fw-stage1`) では再現しなかった。実ログでの受入 1・2 は未達 (§4)。

## 1. 測定

素材: `work-fw-stage1` と `work-liftlib` を展開。`fl-win64` は member 2 本 (`extracted/block18983_PE.bin`・`extracted/block00031_PE.bin`) のみ `$RUNNER_TEMP/fl-win64` へ展開。stage-1 は素材の成果物 (`fw[0-7]`・`r2`・`r3`・`fw_icall.dll`・`fw_map.json`) をそのまま使い、`fw_lift.sh` では再生成していない。
実行環境: runner 4 vCPU・RAM 15 GiB。

| 記号 | 基点 | 構成 | 手順 | 所要 (real) | load (1 分値 開始→終了) | rc | RunError (smoke.log) | runerr | init_reach | dispatch / units / va / heap / ff |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | `150a83fa` (修正前) | 素材の stage-1 + stage-2 を全部再生成 | `fw_stage2.sh --fresh` | 534 秒 | 0.52 → 2.76 | 1 | `Runtime 268436792 at 0000000010000710` (29 行) | 1 | 16 | 38 / 0 / 1 / 1 / 0 |
| A1 | `f58467d6` (修正後) | B1 の中間物を共有し emcc 以降を再生成 | `fw_stage2.sh` (増分) | 18 秒 | 0.79 → 0.85 | 1 | 同上 | 1 | 16 | 38 / 0 / 1 / 1 / 0 |
| B2 | `8d8d0e6a` (#3150 の起点・修正前) | `git archive 8d8d0e6a tools` + 素材の stage-1 | `fw_stage2.sh` (非 fresh) | 275 秒 | 0.72 → 2.61 | 1 | 同上 | 1 | 16 | 38 / 0 / 1 / 1 / 0 |
| A2 | `8d8d0e6a` + 修正 2 ファイル | B2 の中間物を共有 | 増分 | 17 秒 | (未記録) | 1 | 同上 | 1 | 16 | 38 / 0 / 1 / 1 / 0 |

- `rc 1` は全件 `init_reach` 不一致 (期待 288) による FAIL。`init_reach` の期待値 288 は未達のまま (本 issue の範囲外)。
- B2 は非 fresh。`r2`・`r3` (RetDec の decode 結果) は素材の stage-1 成果物を再利用し、RetDec を再実行していない。
- 修正後 (A1・A2) の stderr には `warning: emscripten_force_exit cannot actually shut down the runtime, as the build does not have EXIT_RUNTIME set` が 1 行出る。判定と情報値は変わらない。修正前 (B1・B2) には出ない。

### 比較 (#3150 の値との違い)

`REPORT_3150.md` §1 (`8d8d0e6a`・stage-1 を `fw_lift.sh` で再生成) は `Runtime error 203 at 0x1`・`init_reach=13`・情報値 0 だった。本測定の B2 (同じ `8d8d0e6a`・素材の stage-1) は `Runtime 268436792 at 0000000010000710`・`init_reach=16`・情報値 非 0 で、一致しない。stage-1 の入力が違うため、#3150 の失敗形は本素材では再現しない。

## 2. 修正 (`f58467d6`)

| ファイル | 変更 |
|---|---|
| `tools/plugins/framework/fw_smoke_check.py` | `RUNERR_RE` を `Runtime (?:error )?(\d+) at ...` に。`Runtime error 203 at` と旧形 `Runtime 268436792 at` の両方を数える |
| `tools/plugins/framework/fw_stage2.sh` | emcc の `-sEXIT_RUNTIME=1` → `=0`。理由を 2 行の注釈で書く |
| `tools/plugins/framework/tests/test_fw_smoke_check.py` (新規) | 7 項目。再現行 (`REPORT_3150.md` §2 の原文) で runerr=1、旧形も数える、無関係な行は数えない、runerr=0 期待で FAIL、EXIT_RUNTIME=0 の guard |

- テストは修正後の 2 ファイルで 7/7 PASS。修正前の 2 ファイル (`origin/main`) に対しては 4 件 FAIL (規則を壊すと落ちる)。
- `EXIT_RUNTIME=1` の影響は、RestoreContext 後に `exit(0)` の経路へ入ったときに情報関数が 0 を返すこと (`REPORT_3150.md` §4)。本素材の B1・B2 はこの経路に入らず (`called after` は 0 件・終端は `Aborted(... corrupted its heap ...)`)、情報値は元から非 0。

## 3. 受入条件の状態

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. `RUNERR_RE` が `Runtime error N at ADDR` を数え、#3150 の再現行で runerr=1 | 部分 | fixture (`REPORT_3150.md` §2 の原文) と `test_fw_smoke_check.py` で確認。実ログの 27 行目は本素材で再現せず (B1・B2 は旧形の `Runtime N at`) |
| 2. EXIT の影響を外し、`dispatch / va / heap / ff` が 0 でない値で出る | 部分 | `EXIT_RUNTIME=0` に変更 (A1・A2)。dispatch 38・va 1・heap 1 は修正前も非 0。`ff=0` は実測値 (fail-fast 0 件・ゲートの期待値 0)。after-exit の 0 は本素材で再現せず、修正の効果は未確認 |
| 3. 修正後も `init_reach` を変えない | 達成 | B1=A1=16、B2=A2=16 |
| 4. 所要・load average・PASS/FAIL を実測値で記録 | 達成 | §1 |

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `fw_lift.sh` で stage-1 を再生成し、stage-2 の 27 行目 `Runtime error 203 at 0x1` と情報値 0 を実ログで確認する (RetDec の stage-1 約 8 分 + stage-2 約 9 分) | 受入 1・2 の実ログ確認 | #3186 (open のまま残す。再測定のため子 issue は起票しない) |

## 5. 再現手順

```sh
git worktree add ../ws-3186 -b 3186-smoke-runerr-info origin/main
cd ../ws-3186
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
D=$RUNNER_TEMP/fl-win64; mkdir -p $D && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $D --occurrence extracted/block18983_PE.bin extracted/block00031_PE.bin
echo '{}' > tools/plugins/work/fw_hash_counts.json
FL_WIN64_DIR=$D python3 tools/plugins/framework/fw_prep.py
FL_WIN64_DIR=$D TMPDIR=$RUNNER_TEMP bash tools/plugins/framework/fw_stage2.sh --fresh       # B1 (修正前 = 150a83fa 側の版)
python3 tools/plugins/framework/tests/test_fw_smoke_check.py                                  # 修正後の規則テスト
rm -f tools/plugins/work/fw/fw_route.cjs tools/plugins/work/fw/fw_route.wasm
FL_WIN64_DIR=$D TMPDIR=$RUNNER_TEMP bash tools/plugins/framework/fw_stage2.sh                 # A1 (増分: emcc と smoke のみ)
```

B2 は `git archive 8d8d0e6a tools | tar -x -C $RUNNER_TEMP/base8d` で作った木に素材を展開し、非 fresh で `fw_stage2.sh` を実行した。

## 6. コード差分

```sh
git diff 150a83fa f58467d6 --stat -- tools/plugins/framework
#  tools/plugins/framework/fw_smoke_check.py                    |  4 +-  (RUNERR_RE・docstring 1 行)
#  tools/plugins/framework/fw_stage2.sh                         |  4 +-  (EXIT_RUNTIME と注釈 2 行)
#  tools/plugins/framework/tests/test_fw_smoke_check.py         | 54 ++++ (新規・規則テスト)
git diff f58467d6 HEAD -- tools/plugins/framework ':!*.md'
#  (空: 測定後に変わったのは本 REPORT と docs/DOC_MAP.md だけ)
```
