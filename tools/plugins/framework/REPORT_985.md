# #985 REPORT — Phase B の icall 間接呼出先 [0x710040] の実行時値計測 (途中経過)

- 担当 issue: #985 `[PLG-P0b-1]`。残作業は子 issue #1609 `[PLG-P0b-6]` (親 #1478) に移譲済み。
  本 run は #1609 の受入条件 1 (`[0x710040]` の実行時値計測) を実施した。
- 起点: `origin/main` 1e3ee7af。worktree `ws-985`・branch `985-plg-p0b-icall-slot`。
- 素材: `work-fw-stage1` (repo ルート展開 → `tools/plugins/work/fw`)・`fl-win64` (`$RUNNER_TEMP/fl-win64`)。
  `work-icall` は `tools/icall/work/` 配下 (2225 件) で、本 run の hs 系 (Phase B) では参照しなかった。
  `pefile` / `capstone` は導入済み。

## 1. 受入条件の達成状況

| 出典 | 受入条件 | 結果 |
|---|---|---|
| #1609 #1 | `[0x710040]` の実行時の値と書込み元を計測 | **部分達成**。実行時の値は trap 時点で 0 (§2)。書込み元は IR・image に無し (§3) |
| #1609 #2 | fold deref を塞ぎ `hs_e2e.sh --fresh` の Phase B で `plug != 0` | **未達** (§4) |
| #1609 #3 | fail-soft 3 件の戻り値の意味を確定 | **未達**。本 run では着手せず |
| #1609 #4 | REPORT に実測値・Phase A 回帰 `dispatch=38 ff=0` | **達成** (§2) |

## 2. 実測

環境: 4 vCPU。load は各手順の開始時の `uptime` 値。

| 手順 | commit | 結果 | 所要時間 (real) | load (開始時) |
|---|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用・`FL_WIN64_DIR` 指定) | 1e3ee7af (未変更) | exit 0・smoke PASS (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 7 分 12 秒 | 0.52 / 0.39 / 0.17 |
| `hs_e2e.sh --fresh` | 1e3ee7af (未変更) | exit 1 / Phase A `dispatch=38 ff=0` (回帰 OK) / `[hs] Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` / `E2E FAIL: 1 項目` | 2 分 37.6 秒 | 1.28 / 1.75 / 1.08 |
| `hs_dbg.sh` (trace ビルド) | 1e3ee7af (未変更) | exit 0 (`[dbg] EXC: memory access out of bounds`) | 18.8 秒 | — |
| probe (`hs_dbg.cjs` を読んで trap 時の linear memory を読む・一時スクリプト) | 1e3ee7af (未変更) | `run= EXC memory access out of bounds` / `mem[0x710030]=0` / `mem[0x710040]=0` | 数秒 | — |

- Phase A の回帰: `dispatch=38 ff=0` を stage2 と e2e の両方で確認。
- 記録 ID 列 `rec[0..6]` は `0x47,0x56,0x0d,0x2e,0x47,0x1d` で REPORT_1229 と一致 (前回と同じ)。

## 3. [0x710040] の値と書込み元

- 実行時: trap 時点の linear memory で `[0x710030]` = 0x0、`[0x710040]` = 0x0 (§2 probe)。`fw_image.bin` 上の `0x710040` も 0x0。
- IR (`tools/plugins/work/hs/hs_flat3.ll`) の読出し: `0x710040` は 32558 行 (`function_40d6e0` 内) の 1 箇所のみ。`0x710030` は 30146 / 30205 / 30261 / 30425 / 30486 / 30548 / 32604 行で読まれる。
- IR 内の書込み: `0x710040` への store は **無い**。`0x710030` への store は 70328 行 (`store i64 4213760 (= 0x404C00)`) の 1 箇所のみ。
- `framework/fw_rt.c` のコメント (62-63 行) は `0x710030` を FL 本体 (FLEngine) の export function table の VA と記す。したがって `[0x710040]` の正しい値は image 外の FL 本体側にあり、本 run の linear memory からは読めない。

## 4. 未達と残作業

- `0x40d6e0` の分岐: `[0x710040]` == 0 のとき `dec_label_pc_7b812a` (`0x40d807` の icall) に進み、`[0x710030]` を読む。実行上は `0x40d807` が target 0 の soft-miss を返して抜ける (e2e ログ)。その後 `0x40e720` (既存 override) を経由して trap。
- 残作業 A: `0x710030` / `0x710040` の値を FL 本体 export table から求めるか、呼出元 `0x40d820` の引数を復元して `0x40d6e0` の経路そのものを塞ぐ。どちらも FL 本体側の table 読解が必要で、本 run の時間内では完了しない。
- 残作業 B: fail-soft 3 件 (0x52cf40 / 0x4e6060 / 0x4181e0) の戻り値の読解 (#1609 受入 3)。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $HOME/artifacts/work-fw-stage1.tar.zst          # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh                      # exit 0・smoke PASS (7 分程度)
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh        # FAIL (Phase B OOB) が期待値
bash tools/plugins/framework/hostshim/hs_dbg.sh                # trap 直前の到達点 (0x40d6e0 → 0x40e720)
```
