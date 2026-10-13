# #985 REPORT — hs_e2e 判定の是正 (Phase B 例外 = FAIL) と RTL fold deref の現状

- 担当 issue: #985 `[PLG-P0b-1]` (親 #196)。部分達成のため `Refs #985`。
- 起点: `origin/main` a5adb2fc。素材 `work-fw-stage1` / `toolchain-emsdk` / `toolchain-retdec` / `fl-win64` を展開して実測 (worktree `ws-985`)。
- 本 REPORT は `tools/plugins/framework/REPORT.md` §15 の続き。数値は本 run の実測。

## 1. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | Phase B で `plug != 0` を実測 | **未達** (`plug=0x0`・Phase B は `memory access out of bounds`)。子 issue へ (§4) |
| 2 | Phase B 例外時は FAIL | **達成**。`hs_e2e.mjs` に `exc` を保持し、例外時は `fails` に積む (実測 §2) |
| 3 | REPORT に実測 (所要時間・load・PASS/FAIL) | **達成** (本ファイル §2・§3) |

## 2. 実測

環境: 素材は `docs/WORKFLOW.md` §11 の手順で取得し、`work-fw-stage1` を `tools/plugins/work/fw/` に展開 (`work/` は gitignore 対象で commit しない。`fw_stage2.sh` の標準的な使い方)。toolchain は `[EMSDK]` (emcc 6.0.12)・`[RETDEC]` (RetDec v5.0) を既存配置のまま使用 (`docs/REFERENCES.md` §1)。
Python `pefile` / `capstone` は導入済み (判定 `import` OK)。

| 手順 | 結果 | 所要時間 | load (終了時 1/5/15 分) |
|---|---|---|---|
| `bash tools/plugins/framework/fw_stage2.sh` (stage-1 再利用) | exit 0・smoke `dispatch=38 units_done=0 va=1 heap=1 ff=0` PASS・`fw_smoke_check PASS` | 6 分 55.8 秒 (real) | 未採取 (実行中に計測していない) |
| `hs_e2e.sh` (判定変更前 = 元の `hs_e2e.mjs`) | exit 0 / `E2E PASS` (**誤判定**: Phase B 例外のまま PASS) / `status=0xffffffff plug=0x0 rec=7` | 2 分 37.5 秒 (real) | 1.10 / 1.66 / 1.02 |
| `hs_e2e.sh` (判定変更後 = 本 PR) | exit 1 / `E2E FAIL: 1 項目 — Phase B 例外: memory access out of bounds` | 0.63 秒 (real) ※ emcc 増分無し | 0.66 / 1.50 / 0.98 |

- 変更前の PASS は REPORT §15 の指摘 (`hs_e2e.mjs` が例外時に PASS) を再現したもの。
- 変更後は emcc を再実行していない (`hs_route.cjs` は変更前の同一ビルド)。判定ロジックのみの差分。
- 記録 (両 run 共通): `rec[0..6]` = ID 0x47,0x56,0x0d,0x2e,0x47,0x1d (+ slot6 ×1)。GOLDEN 序列は一致。Phase A は `dispatch=38 ff=0` で PASS。

## 3. 判定変更の内容

`tools/plugins/framework/hostshim/hs_e2e.mjs` (Phase B):

- `_hs_e2e_run()` の例外メッセージを `exc` に保持する。
- 判定節の先頭で `if (exc !== null) fails.push('Phase B 例外: ' + exc);` を積む。
- 既存の prefix 判定 (`plug === 0` 分岐) は変更しない。例外時は `fails` が必ず 1 件以上になり、E2E は FAIL。

## 4. 未達 (受入 1) と残作業

- 原因は REPORT.md §6・§7.1 と同じ: RTL ハッシュ表 `0x52cf40` / 名前検索 `0x40b930` 周辺の fold deref による OOB。
  既存の fail-soft override (`fw_hostfix.py`・`hs_utl.c`) では塞ぎ切れていない。
- 次段 (子 issue): OOB の**最初の trap site** を特定 → その関数の引数復元 (RetDec 定数畳み込み) か override を入れる → `plug != 0` まで進める。
- 起票先: 子 issue (親 #985 → #196)。番号は PR 本文・issue コメントに記載。
