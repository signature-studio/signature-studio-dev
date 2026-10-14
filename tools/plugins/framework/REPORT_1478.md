# #1478 REPORT — Phase B の trap site の候補 0x40d6e0 (icall) と実測 (途中経過)

- 担当 issue: #1478 `[PLG-P0b-5]` (親 #1229 系列・#985)。部分達成のため `Refs #1478`。
- 起点: `origin/main` cb3a89a6。worktree `ws-1478`・branch `1478-plg-p0b-5-phase-b-trap`。
- 前提の経緯: `tools/plugins/framework/REPORT_1229.md` §2〜§4 (fail-soft 3 件の追加と次の trap の記録)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 / `work-fw-stage1` をリポジトリルートで展開 /
  `toolchain-emsdk`・`toolchain-retdec` は `[EMSDK]`・`[RETDEC]` の実在を確認。
  `plugins-ott` は未使用 (本 run の hs 系は framework の FL export 表だけで足りた)。

## 1. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | Phase B で `plug != 0` を実測 | **未達** (`plug=0x0`・Phase B は `memory access out of bounds`)。子 issue へ (§4) |
| 2 | 次の trap site を `hs_dbg.sh` で特定し、原因を塞ぐ | **部分達成**。trap site の候補を §3 で絞り込み (確定は未了)。原因の修正は未着手 (§4) |
| 3 | fail-soft 3 件 (0x52cf40 / 0x4e6060 / 0x4181e0) の戻り値の意味を確定 | **未達**。呼出側の読解は本 run で着手せず (§4) |
| 4 | REPORT に実測 (所要時間・load・PASS/FAIL)・Phase A 回帰 `dispatch=38 ff=0` | **達成** (§2) |

## 2. 実測

環境: 4 vCPU / 15 GiB。load は開始時の 1 / 5 / 15 分の値 (`uptime`)。

| 手順 | commit | 結果 | 所要時間 (real) | load (開始時) |
|---|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用・`FL_WIN64_DIR` 指定) | cb3a89a6 (未変更) | exit 0・smoke `dispatch=38 units_done=0 va=1 heap=1 ff=0` PASS・`fw_smoke_check PASS` | 7 分 04 秒 | — |
| `hs_e2e.sh --fresh` | cb3a89a6 (未変更) | exit 1 / `[fw] Phase A ... dispatch=38 ff=0` (回帰 OK) / `[hs] Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` / `E2E FAIL: 1 項目` | 2 分 28 秒 | 1.94 / 1.94 / 0.99 |
| `hs_dbg.sh` (trace ビルド) | cb3a89a6 (未変更) | exit 0 (実行は `[dbg] EXC: memory access out of bounds`) | 18 秒 | — |

- Phase A の回帰: `dispatch=38 ff=0` を stage2 と e2e の両方で確認 (e2e1.out 行 50)。
- 記録 ID 列 `rec[0..6]` は `0x47,0x56,0x0d,0x2e,0x47,0x1d` で REPORT_1229 と一致。

## 3. trap site の特定

`hs_dbg.sh` の trace 末尾 (trap 直前の末尾 6 件):

```
0x40bce0 → 0x40edb0 → 0x40bd20 → 0x40d820 → 0x40d6e0 → 0x40e720 → [EXC memory access out of bounds]
```

- `0x40d6e0` (`hs_flat3.ll` 行 32537) は `call void @__icall_dispatch(i64 4249578)` (= `0x40d7ea`) を含み、
  間接呼出先の参照元として `[0x710040]` (`inttoptr i64 7405632`, IR 行 32558 で load) を読む。
- `[0x710040]` は `fw_image.bin` 上で `0x0` (静的値)。IR 内に書込み箇所は無い。実行時の値は未計測。
- e2e の `soft-miss indirect target 0x0 at site VA 0x40d807` は別 site (`0x40d807`) で、`0x40d7ea` の soft-miss ではない。
- 隣接する `[0x710030]` (`inttoptr i64 7405616`) は IR の複数 define で load されるが、`0x40d6e0` 内では直接は使われていない。IR 70328 行で `store i64 4213760 (= 0x404C00)` の書込みがある。`0x710040` の書込み元は未特定。
- trace の最後の entry は `0x40e720` (既存 override・store と ret のみ) で、EXC はその entry の後に出る。trap の厳密な命令位置は trace 粒度では未確定。`0x40d6e0` の icall 周辺の可能性はあるが、断定しない。`0x40d820` の呼出側は未読解。

## 4. 未達と残作業 (起票先)

- 残作業 A: `0x710040` (icall 間接呼出先) の書込み元を特定し、fold deref の原因を引数復元か override で塞ぐ。
  受入条件 1・2 の残り。→ 子 issue `[PLG-P0b-6]` を起票 (親: #1478)。
- 残作業 B: fail-soft 3 件 (0x52cf40 / 0x4e6060 / 0x4181e0) の戻り値の意味を呼出側読解で確定する。
  受入条件 3。→ 同じ子 issue に含める。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $HOME/artifacts/work-fw-stage1.tar.zst          # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh                      # exit 0・smoke PASS
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh        # FAIL (Phase B OOB) が期待値
bash tools/plugins/framework/hostshim/hs_dbg.sh                # trap 直前の到達点 (§3)
```
