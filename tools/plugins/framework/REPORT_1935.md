# #1935 REPORT — hs_irfix の定数前提を現行 stage-2 IR に合わせ、Phase B の plug != 0 を実測 (部分達成)

- 担当 issue: #1935 `[PLG-P0b-10]` (親 #1890)。受入 1 のうち「`hs_irfix.py` の修正と停止位置の解消」は達成。受入 2 (`0x710030`/`0x710040` の値確定) と受入 3 (`plug != 0`) は **未達**。受入 4 (Phase A 回帰 `dispatch=38 ff=0`) は **達成**。
- 起点: `origin/main` 46faf265。worktree `ws-1935`・branch `1935-plg-p0b-10-irfix`。
- 測定 commit: `d5b737af` (hs_irfix.py の修正。以降のコード差分は本 REPORT の追加のみ)。

## 1. 実測 (n=1)

| 手順 | 結果 | 所要時間 (real) | load (開始 / 終了) |
|---|---|---|---|
| `fw_stage2.sh --fresh` (commit 46faf265・stage-1 再利用) | exit 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 8 分 36 秒 (07:56:45 → 08:05:21) | 0.94 / 0.64 / 0.27 → 2.72 / 1.83 / 0.94 |
| `hs_e2e.sh --fresh` (修正前・旧 hs_irfix.py) | exit 1。`[hs_irfix] 置換数不一致 (0 != 2)` で停止 | 0.21 秒 | 2.30 / 1.77 / 0.93 (開始) |
| `hs_e2e.sh --fresh` (修正後 d5b737af) | exit 1。Phase A PASS (`dispatch=38 ff=0`)。Phase B は例外終了 (`memory access out of bounds`・`plug=0x0`・`rec=8`) | 1 分 22 秒 | 0.51 / 1.30 / 0.84 → 0.87 / 1.23 / 0.85 |

- n=1 のため min–max レンジは未取得 (`docs/WORKFLOW.md` §5 の n≥3 に未達)。

## 2. 現行 IR で判明したこと

- 旧 `hs_irfix.py` の前提 `@689`(Host)/`@688`(Tag) は現行 `fw_flat4_canon3.ll` に無い。現行は `@396`(Host)/`@395`(Tag)。store 先 (BLK+0x08/+0x10/+0x18) と `ptrtoint` の位置は同一。
- 修正: Host/Tag の定数名を既知の組 `[(@689,@688),(@396,@395)]` から検出する。どちらも無ければ exit 1。置換数は 9 (旧版の前提と同じ構成)。
- `function_6bdde0` の body は現行 IR で 109 行 (`fw_flat4_canon3.ll` の 1733835〜1733943 行)。

## 3. Phase B の状態 (未達)

- `plug=0x0`・`status=0xffffffff`・`slotsCalled=0x0`。`CreatePlugInstance → ctor` の Dispatcher ID prefix は `0x47,0x56,0xd,0x2e,0x10000738,0x47,0x1d` で期待値と 1 件ずれる (5 件目 `0x10000738` が ID として呼ばれる)。
- `soft-miss indirect target 0x0` が多数発生 (`0x40d807`・`0x4e5fa6`・`0x415c3a` など)。FL export table 未設定 = 受入 2 の未解決と同じ原因。
- `fw_flat4_canon3.ll` の `function_40d6e0` は `[0x710040] == 0` のとき必ず `dec_label_pc_7b812a` へ進む (前回 REPORT_1890 §2 と同じ構造・未変更)。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x710030` / `0x710040` の正しい値 (FL 本体 export table からの確定) | `0x40d6e0` の経路を塞げず、`plug=0` のまま (受入 2・3) | #1935 (本 PR で `Refs #1935`) |
| Phase B `memory access out of bounds` と ID `0x10000738` の呼出 | ctor 連鎖が途中で落ちる (受入 3) | #1935 |
| 測定が n=1 | 所要時間・load のレンジ未取得 | #1935 |

## 5. 再現手順

```sh
export FL_WIN64_DIR=$HOME/artifacts/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst               # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh --fresh                  # exit 0・SMOKE PASS (実測 8 分 36 秒)
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh            # Phase A PASS・Phase B 例外 (実測 1 分 22 秒)
```

## 6. コード差分 (測定 commit 以降)

`git diff d5b737af HEAD -- tools/plugins/framework` は本 REPORT の追加のみ。
