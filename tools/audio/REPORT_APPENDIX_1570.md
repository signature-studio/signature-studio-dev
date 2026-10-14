# tools/audio REPORT 付録 (AU-21 #1570 切り分け 1〜3)

> **ナビゲーション**: 本ファイルは `tools/audio/REPORT_AU10.md` の分割移動節の付録 (§16.5〜§16.7)。
> 正本の索引は `REPORT_AU10.md`。250 行上限 (`docs/DOC_MAP.md` §1) のため移した。内容は削除していない (Git 履歴にも残る)。

### 16.5 AU-21 (#1570) 追加切り分け: head `60932d35` (main, コード変更なし)

測定 commit: `60932d35` (origin/main 起点、本 run は `tools/audio/REPORT_AU10.md` のみ変更)。環境: GitHub runner 4 core / 15 GiB, headless google-chrome, `bash tools/audio/build.sh` 直後、[EMSDK] (emcc 6.0.12) 既存を使用。`toolchain-emsdk` 展開は不要。生ログ・JSON は `tools/audio/work/soak10/` (gitignore)。

| 試行 | 結果 | 所要 / load (start → end) |
|---|---|---|
| `--soak 10` 1 回目 | **FAIL (exit 1)**: underruns 1, silence 7,680 f, ramp mismatches 427,520 / 481,024 f, cb_max 174,074 µs, T=1024 (21.3 ms), dev_fill min 0 / avg 888 / max 1280, lat_changes 2 | 43.3 s / 0.27 → 0.64 |
| `--soak 10` 2〜5 回目 | 4/4 PASS: underruns 0, silence 0, ramp 0 / 480,512〜481,024 f, lat_changes 0, dev_fill min 1024, cb_max 70 / 80 / 370 / 405 µs | 各 63〜64 s / 0.09〜0.64 |
| `--soak30` (1800 s, 無負荷) 1 回目 | **PASS (exit 1 完了)**: underruns 0, silence 0, ramp 0 / 86,408,192 f, workletErrors 0, cb 337,534 回 late 0, **cb_max 475 µs**, T=1536, dev_fill 1024/1329/1536, **clock_jumps 2 / clock_jump_frames 0**, lat_changes 0, secs_wall 1800.18 | 1802 s / 0.07 → 0.00 |

判定:
- 10 秒ソーク FAIL は今回 1/6 回で再現 (通算 head `57519ca`〜`60932d35` で 2/21)。FAIL 試行の特徴 (T が 1024〜1280、dev_fill min 0、lat_changes ≥ 1、underrun 1) は前回の FAIL (T=1280、dev_fill min 0) と同一形。**原因は未特定**。FAIL 試行の `T`・dev_fill・underrun・lat_changes は採取済み (上表)。ただし発生源 (ラッチ直後の initial fill か、ワーカ起床の遅延か) を切り分けるデータは無い。
- 30 分ソーク (無負荷 1 回) では ms 級 spike は未再現 (cb_max 475 µs)。10 秒ソーク FAIL 試行では cb_max 174 ms を記録しており、FAIL との関係は未調査。
- `clock_jumps` は 30 分で 2 件 (試行ごとに 2 / 4 / 14 と変動)。`clock_jump_frames` は通算 0 のまま。ramp は全フレーム bit-exact のため実スキップの証拠は無い。発生源 (worklet `currentFrame` の非連続が実スキップか計測タイミングか) は未特定。
- 未解決: 10 秒 FAIL の原因、clock_jumps の発生源、10 秒 FAIL 試行の cb_max 174 ms と FAIL との関係。

### 16.6 AU-21 (#1570) 追加切り分け 2: head `5229fe5f` (main, コード変更なし)

測定 commit: `5229fe5f` (origin/main 起点、本 run は `tools/audio/REPORT_AU10.md` のみ変更)。環境: GitHub runner 4 core / 15 GiB, headless google-chrome, `bash tools/audio/build.sh` 直後 (emcc 6.0.12, [EMSDK] 既存)。JSON は `tools/audio/results/soak_10.json` / `soak_1800.json` (本 run の上書き分は未コミット)。コミット済みの同名 JSON は 2026-10-13 の旧 run のもので、本 run の値とは比較していない。

鮮度の証跡 (docs/WORKFLOW.md §6): 測定 commit `5229fe5f` → HEAD `fcb1e0a9` の `git diff --stat -- tools/audio`:

```
 tools/audio/REPORT_AU10.md | 15 +++++++++++++++
 1 file changed, 15 insertions(+)
```

`git diff --stat 5229fe5f HEAD -- tools/audio ':!tools/audio/REPORT_AU10.md'` の出力は 0 行 (REPORT 以外の差分 0)。よって現 head での再測定は不要。

| 試行 | 結果 | 所要 / load (start → end) |
|---|---|---|
| `--soak 10` 1〜5 回目 | 5/5 PASS: underruns 0, silence 0, ramp 0 / 480,512〜481,024 f (全 5 回), workletErrors 0, lat_changes 0, clock_jumps 0 (全 5 回)。cb_max 100 / 64 / 864 / 74 / 94 µs。dev_fill min 256 (1 回目, T=1024) / 1024 (2〜5 回目, T=1536) | 各 61〜73 s / 0.49 → 0.04 |
| `--soak30` (1800 s, 無負荷) 1 回目 | PASS (exit 1 完了): underruns 0, silence 0, ramp 0 / 86,403,968 f, workletErrors 0, cb 337,513 回 late 0, **cb_max 344 µs**, T=1536, dev_fill 1024/1308/1536, **clock_jumps 8 / clock_jump_frames 0**, lat_changes 0, secs_wall 1800.07 | 1802 s / 0.01 → 0.00 |

判定:
- 10 秒ソーク FAIL は今回 0/5 回。通算 (head `57519ca`〜`5229fe5f`) で 2/26。原因は**未特定**。FAIL 試行の採取データは §16.5 の 1 回のみ。
- 30 分ソーク (無負荷) の ms 級 spike は今回も未再現 (cb_max 344 µs)。無負荷 30 分の通算は 4 回 (`d7d91d2`・`12586095`・`60932d35`・`5229fe5f`) で、cb_max は 184 / 169 / 475 / 344 µs (いずれも 1 ms 未満)。
- `clock_jumps` は 30 分で 8 件 (通算 2 / 4 / 14 / 8 件と変動)、`clock_jump_frames` は通算 0 のまま。ramp は全フレーム bit-exact で実スキップの証拠は無い。発生源は未特定。
- 負荷下の 30 分ソークは本 run では未実施 (§16.2 が最新)。

### 16.7 AU-21 (#1570) 追加切り分け 3: head `c2f67568` (main, コード変更なし)

測定 commit: `c2f67568` (origin/main 起点の worktree `ws-1570`、本 run は `tools/audio/REPORT_AU10.md` のみ変更)。環境: GitHub runner 4 core / 15 GiB, headless google-chrome, `pnpm install --frozen-lockfile` 後に `bash tools/audio/build.sh` (OK, emcc 6.0.12, [EMSDK] 既存)。生ログ・JSON は `tools/audio/work/soak10/` (gitignore)。

| 試行 | 結果 | 所要 / load (終了時 1 分平均) |
|---|---|---|
| `--soak 10` 1〜5 回目 | 5/5 PASS: underruns 0, silence 0, ramp 0 / 480,512〜481,024 f (全 5 回), workletErrors 0, exit=1 完了 | 各 64 s / 0.26・0.13・0.05・0.04・0.04 |
| `--soak30` (1800 s, 無負荷) 1 回目 | PASS (exit=1 完了): underruns 0, silence 0, ramp 0 / 86,405,376 f, workletErrors 0, cb 337,519 回 late 0, **cb_max 385 µs**, T=1536, dev_fill 1024/1304/1536, **clock_jumps 4 / clock_jump_frames 0**, lat_changes 0, secs_wall 1800.098 | 1802 s / 終了時 0.00 |

判定:
- 10 秒ソーク FAIL は今回 0/5 回。通算 (head `57519ca`〜`c2f67568`) で 2/31。FAIL 試行の採取データは §16.5 の 1 回のみで、原因は**未特定**。今回は FAIL が出ず、新しい採取データは無い。
- 30 分ソーク (無負荷) の ms 級 spike は今回も未再現 (cb_max 385 µs)。無負荷 30 分の通算は 5 回 (`d7d91d2`・`12586095`・`60932d35`・`5229fe5f`・`c2f67568`) で、cb_max は 184 / 169 / 475 / 344 / 385 µs (いずれも 1 ms 未満)。
- `clock_jumps` の件数 (`public/worklets/fl-audio-worklet.js` L92-94) は通算 2 / 4 / 14 / 8 / 4 件と変動。**`clock_jump_frames` は通算 0 のまま**。ただし加算は `frame - prevFrame - Q` の符号付き差で、正負のジャンプが打ち消し合うと合計 0 になりうる。現行の計測では「欠落フレーム 0」を断定できない (絶対値の合計を別カウンタで持たない限り切り分け不能)。ramp は全フレーム bit-exact で、実スキップの証拠は無い。発生源は未特定。
- `dev_frames` の連続性と `clock_jump_frames` の符号付き合計を組み合わせた切り分けは、コード変更 (絶対値カウンタの追加) を伴うため本 run の範囲外。
- 負荷下の 30 分ソークは本 run では未実施 (§16.2 が最新)。

鮮度の証跡 (docs/WORKFLOW.md §6): 測定 commit `c2f67568` → HEAD の `git diff --stat c2f67568 HEAD -- tools/audio` は REPORT_AU10.md のみ (下記 PR 作成時点で確認)。

