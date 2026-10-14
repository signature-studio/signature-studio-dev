# #1890 REPORT — Phase B icall 0x40d6e0 の fold deref 解消 (plug != 0) (部分達成・読解と再現)

> 注 (#2008 §8 で訂正): `0x710030`・`0x710038`・`0x710040` は FL 本体の export table ではなく Delphi RTL の例外フック (`0x40d6e0` = raise の参照先)。下記の「export table」前提の記述は誤りで、正本は `tools/plugins/framework/REPORT_2008.md` §8.1。

- 担当 issue: #1890 `[PLG-P0b-8]` (親 #1848)。受入 1 (0x710030 / 0x710040 の値確定と 0x40d6e0 経路の遮断)・受入 2 (`hs_e2e.sh --fresh` Phase B の `plug != 0`) は **未達**。受入 3 (Phase A 回帰 `dispatch=38 ff=0`) は **達成**。
- 起点: `origin/main` 576c4976。worktree `ws-1890`・branch `1890-plg-p0b-8-fold-deref`。コード変更なし (本 REPORT の追加のみ)。
- 素材: `work-fw-stage1` (repo ルート展開 → `tools/plugins/work/fw`・12 件)・`fl-win64` (`$RUNNER_TEMP/fl-win64` は未展開。fw_stage2 は `FL_WIN64_DIR` 指定で動作)・ツールチェーンは [EMSDK]・[RETDEC] で確認済み。

## 1. 実測

測定 commit: `576c4976` (コード差分 0)。`git diff 576c4976 HEAD -- tools/plugins/framework` は本 REPORT の追加のみ。load は各手順の開始・終了時の `uptime` 値。

| 手順 | 結果 | 所要時間 (real) | load (開始 / 終了) |
|---|---|---|---|
| `fw_stage2.sh --fresh` (stage-1 再利用・`r2`/`r3` 既存) | exit 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 9 分 28 秒 (**実測 n=1**) | 0.08 / 0.31 / 0.18 → 2.59 / 1.81 / 0.93 |
| `hs_e2e.sh --fresh` | exit 1。`[hs_irfix] 置換数不一致 (0 != 2)` で停止 (Phase A・B に到達せず) | 0.22 秒 (**実測 n=1**) | 2.19 / 1.75 / 0.92 |

- Phase A の回帰 `dispatch=38 ff=0` は stage-2 smoke で確認 (PASS)。Phase B の実測 (`plug`・`rec`) は取得できず。
- **n=1 の限界**: 上記は n=1 のため min–max レンジは未取得 (`docs/WORKFLOW.md` §5 の n≥3 に未達)。fw_stage2 1 回が約 9.5 分で、n=3 は本 run の上限に収まらなかった。再測定は #1935 で行う (§5)。
- 停止位置の再現 (1 本): `bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh 2>&1 | grep -F '[hs_irfix] 置換数不一致'` が `0 != 2` を出力すれば同じ停止位置。

## 2. 現行 IR で判明したこと (`fw_flat4_canon3.ll`)

- `hs_irfix.py` は `function_6bdde0` の定数 `@688`/`@689` を前提にするが、**現行の stage-2 IR には `@688`/`@689` の参照が無い** (定義行 774/775 のみ)。`function_6bdde0` の定数 store は `@395`/`@396`/`null` になっている。よって hs_irfix の置換前提が現行 lift と合わない。
- `function_40d6e0` の分岐 (現行 IR 33475〜33496 行 / 前回 REPORT の `hs_flat3.ll` 32558 行とは行番号が異なる):
  - `%9 = load i64, [0x710040]` → `%10 = icmp eq %9, 0`
  - `%ce5 = ptrtoint ptr @684 to i8` → `%cenh1547 = icmp ne i8 %ce5, 0` (定数 `@684` のアドレス下位 1 byte による判定)
  - `%brmerge = or %10, %cenh1547` → true なら `dec_label_pc_7b812a` (前回 REPORT の `0x40d807` 側)、false なら `dec_label_pc_7b8045`。
  - つまり `[0x710040] == 0` のときは必ず `dec_label_pc_7b812a` に進む。`[0x710040]` の値を変えない限りこの経路は塞がらない。
- `[0x710030]` の読出し (現行 IR 31078 / 31137 / 31193 / 31357 / 31418 / 31480 / 33536 行ほか) と store (72157 行 `store i64 4213760`) は前回 REPORT §3 と同じ構造。

## 3. 未達の理由

1. **受入 1 (値確定)**: `0x710030` / `0x710040` の正しい値は FL 本体 (FLEngine) の export function table 由来 (`fw_rt.c` 62-63 行)。FL 本体 (`fl-win64`) の PE から該当 table を読む作業が必要で、本 run の時間内では完了しなかった。
2. **受入 2 (plug != 0)**: `hs_e2e.sh` が `hs_irfix` の置換数不一致で停止し、Phase B に到達できなかった。`hs_irfix.py` を現行 lift の定数 (`@395`/`@396`/`@684`/`@685` 系) に合わせる修正が前提。
3. 受入 1・2 の残件は子 #1935 `[PLG-P0b-10]` に移管 (本 PR は `Refs #1890`)。

## 4. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst               # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh --fresh                  # exit 0・SMOKE PASS (約 9.5 分)
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh            # 現状は hs_irfix で停止 (置換数不一致)
```

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `hs_irfix.py` の定数前提 (`@688`/`@689`) が現行 lift と不一致。`hs_e2e.sh --fresh` が Phase B に到達しない | Phase B の `plug != 0` 実測ができない | #1935 `[PLG-P0b-10]` |
| `0x710030` / `0x710040` の正しい値 (FL 本体 export table からの確定) | `0x40d6e0` の `[0x710040] == 0` 経路を塞げない (受入 1) | #1935 `[PLG-P0b-10]` |
| fail-soft 3 件の戻り値の確定 | `0x52cf40` / `0x4e6060` / `0x4181e0` の 0 の意味が未確定 | `0x4181e0` は #1933 `[PLG-P0b-10]` (open)。`0x52cf40` / `0x4e6060` は #1891 が CLOSED (2026-10-14) のため起票先なし → PM に新規起票を依頼 |
| 測定が n=1 (変動値のレンジ未取得) | 所要時間・load の揺れ幅が不明。`fw_stage2.sh` 1 回 約 9.5 分で本 run 内に n=3 が収まらない | #1935 `[PLG-P0b-10]` (次回の検証で n≥3 のレンジを取得) |
