# #1229 REPORT — Phase B の OOB 最初の trap site と fold deref 解消 (途中経過)

- 担当 issue: #1229 `[PLG-P0b-4]` (親 #985)。部分達成のため `Refs #1229`。
- 起点: `origin/main` 2b2faf52。worktree `ws-1229`・branch `1229-plg-p0b-4-fold-deref`。
- 素材: `fl-win64` / `toolchain-emsdk` / `toolchain-retdec` / `work-fw-stage1` を展開 (`$HOME/artifacts` 実在を ls で確認)。
  `work-fw-stage1` の tar は repo ルート相対 (`tools/plugins/work/fw/...`) で格納されているため、
  `tools/plugins/work/fw` へ展開するには **repo ルートで** `tar --zstd -xf` する (展開先を dir 指定すると二重になる)。

## 1. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | Phase B で `plug != 0` を実測 | **未達** (`plug=0x0`・Phase B は `memory access out of bounds`)。子 issue へ (§4) |
| 2 | OOB の最初の trap site を特定し、塞ぐ | **部分達成**。最初の trap site を特定し、fail-soft を 3 件追加。次の OOB が残る (§2・§3) |
| 3 | REPORT に実測 (所要時間・load・PASS/FAIL) | **達成** (§2) |

## 2. 実測

環境: 4 vCPU / 15 GiB。load は各手順の開始時 1 / 5 / 15 分の値。

| 手順 | commit | 結果 | 所要時間 (real) | load (開始時) |
|---|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用) | 2b2faf52 (未変更) | exit 0・smoke `dispatch=38 units_done=0 va=1 heap=1 ff=0` PASS・`fw_smoke_check PASS` | 7 分 26 秒 | 1.23 / 0.88 / 0.38 |
| `hs_e2e.sh` (ベースライン・変更なし) | 2b2faf52 | exit 1 / `E2E FAIL: Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` | 2 分 07 秒 | 1.95 / 2.12 / 1.13 |
| `hs_dbg.sh` (trace ビルド) | 2b2faf52 | trap 直前 `0x52ecc0 → 0x40bce0 → 0x40b3f0 → 0x40bce0 → 0x40bd20 → 0x52cf40 → 0x52ce00` で `memory access out of bounds` | 15.5 秒 | — |
| `hs_e2e.sh --fresh` (+ `0x52cf40` fail-soft) | 変更 1 | exit 1 / `Phase B 例外: Maximum call stack size exceeded` | 2 分 08 秒 | 0.25 / 1.18 / 0.99 |
| `hs_e2e.sh --fresh` (+ `0x4e6060` fail-soft) | 変更 2 | exit 1 / `Phase B 例外: memory access out of bounds` | 2 分 08 秒 | 0.53 / 0.98 / 0.96 |
| `hs_e2e.sh --fresh` (+ `0x4181e0` fail-soft) | 変更 3 (本 PR) | exit 1 / `Phase B 例外: memory access out of bounds` / `plug=0x0` | 2 分 08 秒 | 0.58 / 0.91 / 0.96 |

- ベースラインの記録 ID 序列 `0x47,0x56,0x0d,0x2e,0x47,0x1d` は全 run で不変 (GOLDEN 序列と一致)。
- Phase A (framework smoke) は変更 3 の実行 (`hs_e2e.sh --fresh`) の中で再確認: `[fw] Phase A (framework smoke): Halt0/RestoreContext dispatch=38 ff=0` (e2e4.log)。Phase A は PASS。

## 3. 修正内容と根拠 (`fw_hostfix.py`)

| # | 対象 VA | 根拠 (hs_dbg 実測) | 対処 |
|---|---|---|---|
| a | `0x52cf40` (RTL ハッシュ表) | 呼出 `0x40bce0` 経由で到達し、`[@24+56]` の u16 (name 長) を name ポインタとして `0x52ce00` (CRC32) に渡す → バイト読取が OOB | 「見つからない」= 0 の fail-soft |
| b | `0x4e6060` | `0x4e5fc0` から呼ばれる自己再帰。fold で停止条件が崩れ、40 段で "Maximum call stack size exceeded" | 0 を返す fail-soft |
| c | `0x4181e0` | `0x4e5f50` が戻り値 (`[BLK+0x80]`) を `+568` で deref。戻り値は fold 由来 | 0 を返す fail-soft |

- a〜c の戻り値の意味 (「該当なし」) は呼出側の読解で確定していない。`plug != 0` に届かない原因の切り分けにのみ使う。
- a の trap 位置は `0x52dba0` (既存 override) の内部呼出であり、`0x52dba0` 以外の経路からも到達する。

## 4. 未達と残作業 (起票先)

- 次の trap site: `0x40d6e0` → `__icall_dispatch(0x40d7ea)` (間接呼出先 `[0x710040]` の fold 値) 付近で `memory access out of bounds` (hs_dbg 実測)。`0x40e720` の既存 override 後に到達。
  → 子 issue (起票先: 親 #985 系列 / 本 issue の子)。
- Phase A (変更 a〜c の回帰) の再実行 → 同子 issue。
- `hs_e2e.mjs` の判定変更 (Phase B 例外時 FAIL) は #985 で達成済み。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
# 素材: work-fw-stage1 は repo ルートで展開する
tar --zstd -xf $HOME/artifacts/work-fw-stage1.tar.zst
bash tools/plugins/framework/fw_stage2.sh
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh   # FAIL (Phase B OOB) が期待値
bash tools/plugins/framework/hostshim/hs_dbg.sh           # trap 直前の到達点
```
