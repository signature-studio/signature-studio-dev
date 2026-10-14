# AU-29 (#3115) clock_jump の絶対時刻と cb 通し番号の記録 — tools/audio/

既知類型との関係: 該当なし (ランタイム shim の計測追加。`docs/DEFECTS.md` の類型には当たらない)。親: #1570 (AU-21)、REPORT は `REPORT_AU10.md` §16.10 の続き。

測定 commit: `7c5ee224` (コード変更の最後の commit)。REPORT 追記の commit までの差分は下記 (`git diff 7c5ee224 HEAD -- tools/audio public/worklets src/runtime` は本ファイルと DOC_MAP のみ)。

## 1. 変更

- worklet (`public/worklets/fl-audio-worklet.js`): clock_jump の port 通知に `ct` (`currentTime`)・`pn` (`performance.now()`、worklet で未定義なら −1)・`cb` (`Atomics.load(ctl.cb_count)` = producer の bufferSwitch 通し番号) を追加。既存の `ms` (`Date.now()`) は残す。
- shim (`src/runtime/audio-shim.ts`): `clockJumpLog` の型と受け取りに `ct`・`pn`・`cb` を追加。
- harness (`tools/audio/harness/run.mjs`): `clock_jump_log=` の表示に `ct`・`pn`・`cb` を出す。
- SAB のレイアウトは**変えていない** (cb は既存の ctl `cb_count`、jump ログは port 経由の JS 配列)。よって C 表 (`flaudio.c`)・TS 表 (`audio-layout.ts`) は無変更で、`verifyLayout` は既存の検査がそのまま通る (attach ログ `layout 66 fields OK`)。
- 検査 `tools/audio/test/worklet_jump_check.mjs` (新規): worklet の `run()` を `vm` で駆動し、`currentFrame` を飛ばして 3 件の jump の `d`・`frame`・`cb`・`ct`・`pn` を検査する。`performance` あり・なしの 2 経路。
  - 正の対照: 4/4 PASS (`node tools/audio/test/worklet_jump_check.mjs`)。
  - ネガティブコントロール: `cb: 0` に置換した版 (`tools/audio/work/nc/nc_cb0.js`) では cb の検査 2 件が FAIL (`cb=0`)。

## 2. 実測

環境: GitHub runner 4 core / 15 GiB (nproc 4)、headless google-chrome 154、`pnpm install --frozen-lockfile` 後 `bash tools/audio/build.sh` OK (emcc 6.0.12, [EMSDK] 展開済み)。生ログ・JSON は `tools/audio/work/` (gitignore)。

| 試行 | 結果 | 所要 (UTC) / load (開始→終了, 1 分平均) |
|---|---|---|
| `--soak 10` 初回 (build 直後) | **FAIL (exit 1)**: underruns 1, silence 256 f, ramp mismatches 425,984 / 480,512, T=1024, lat_changes 2, dev_fill min 0 / avg 896 / max 1280, cb_max 27,490 µs, jumps 0 | 22:20:56〜22:21:10 / 0.21 → 0.18 |
| `--soak 10` 反復 1〜5 | **5/5 PASS**: underruns 0, silence 0, ramp 0 / 480,512 f (全 5 回), T=1536, lat_changes 0, jumps 0 (全 5 回), cb_max 45 / 50 / 45 / 50 / 439 µs | 各 63.4〜63.5 s (host wall)、5 回目の終了 22:26:40 / load 1 分平均 0.13 → 0.01 (各回の start→end は `work/soak10/run_*.log` の host 行) |
| **`--soak30` (1800 s, 無負荷)** | **PASS (exit 1 完了)**: underruns 0, silence 0, ramp **0 / 86,408,192 f** (全一致), workletErrors 0, cb 337,543 回 late 0, cb_max 375 µs (cb_max_q 428), T=1536 固定 (lat_changes 0), dev_fill 1024/1298/1536, **clock_jumps 4** (skip 256 f = +128 × 2, dup 256 f = −128 × 2, 符号付き合計 0), secs_wall 1800.234 | 22:28:42〜22:58:44 / 0.01 → 0.00 (host wall 1801.6 s) |

soak10 の初回 FAIL は、`REPORT_AU10.md` §16.5 と同じ形 (T=1024・dev_fill min 0・lat_changes ≥ 1・underrun 1)。今回の変更は jump 発生時にしか動かず、この run の `clock_jumps` は 0 だった。よって変更の影響は無いと判断するが、原因は未特定のまま (#1570)。

### 2.1 30 分ソークの clock_jump 4 件 (`clock_jump_log`)

| # | q | d (frames) | frame (currentFrame) | ct (s) | cb | ms (Date.now) | pn |
|---|---|---|---|---|---|---|---|
| 1 | 65,718 | −128 (重複) | 8,425,344 | 175.528 | 32,859 | 1792017098877 | −1 |
| 2 | 65,719 | +128 (描画されなかった frame) | 8,425,600 | 175.533 | 32,859 | 1792017098877 | −1 |
| 3 | 177,562 | −128 (重複) | 22,741,376 | 473.779 | 88,781 | 1792017397127 | −1 |
| 4 | 177,563 | +128 | 22,741,632 | 473.784 | 88,781 | 1792017397127 | −1 |

読み取り (2 組の対応):
- 各組は隣接 (q と q+1)、同じ frame の process() が 2 回 (dup) の後に +256 進む (skip)。符号付き合計は各組 0。§16.10 の 3 組と同じ形。
- **cb は各組の両端で同じ値** (32,859・88,781)。つまり dup と skip の間に producer の bufferSwitch は 1 回も無い。producer のコールバックが遅れた・跳んだ、という形では説明できない。
- cb と ct の対応: `ct − cb × 256 / 48000` は 2 組とも **0.280 s** (cb 1 回 = 256 frame = 5.333 ms)。cb 総数 337,543 は 1800 × 48000 / 256 = 337,500 とほぼ一致 (+43)。cb の時刻そのものは記録していないので、この対応は cb 番号からの換算である (cb 0 の時刻 ct=0 を仮定すると ct ≈ cb × 256/48000 + 0.280 s)。
- `ms` (Date.now) と `ct` は、2 組の間隔 (298,250 ms と 298.251 s) で 1 ms 以内に一致。絶対時刻 (壁時計) と AudioContext 時刻の対応は取れている。
- `pn` は全件 −1。**worklet の `performance` は未定義** (Chrome 154 headless)。performance.now() の値は取れない → 2 の未解決へ。

## 3. 判定

- 受入条件 1 (絶対時刻と cb 番号): `ct`・`ms`・`cb` は取得済み。**`performance.now()` は worklet で取れない** (`pn=−1`)。shim の main thread 側での取得は子 issue へ (下表)。
- 受入条件 2 (表の同時更新と verifyLayout): SAB を変えていないので C 表・TS 表は無変更。verifyLayout は既存の検査が通過 (soak10・soak30 の attach ログ)。harness 表示は更新済み。
- 受入条件 3 (build と soak10): build OK。soak10 は初回 1 件 FAIL (既知の断続 FAIL と同形)、反復 5/5 PASS。通算 6 回中 5 回 PASS。
- 受入条件 4 (soak30 の記録): 実施済み (§2・§2.1)。

## 4. 検証範囲 / 範囲外

- 範囲内: headless google-chrome 154 (fake 出力シンク)、無負荷、30 分 n=1、soak10 n=6。jump の件数・位置・cb の対応は 1 試行 (4 件) のみで、再現性は未確認。
- 範囲外: 実機デバイス・Firefox・Safari、負荷下の 30 分 (#1570 の未解決)、`performance.now()` の値 (worklet では未取得)。
- 検査: `worklet_jump_check.mjs` は worklet の計上ロジックを mock で駆動する。実ブラウザの jump は soak30 でしか出ないため、実ブラウザの経路は §2.1 の 1 試行で確認した。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| worklet に `performance` が無く `pn` (performance.now()) が −1 | 受入条件の performance.now() 部分が未達。ct と ms で絶対時刻は取れるが、performance.now() の時間軸との対応は無い | [AU-31] #3157 (親: #3115) |
| 10 秒ソーク FAIL の原因 (本 run 初回 1 件。§16.10 までの通算 2/44 に本 run の 1/6 を加えて 3/50) | 30 分実測の信頼性。原因は未特定 | #1570 (再現時は cb・ct・clock_jump_log を採取) |
| 同一 frame の process() が 2 回呼ばれる条件 (ブラウザ内部の起床) | 無害の根拠は sample 照合のみ。cb は同一 (producer 起因でない) | #1570 |
| 負荷下 (load avg 10 超) の 30 分ソーク | 負荷下の clock・spike は未計測 | #1570 |
| cb の時刻そのもの (producer 側の時刻) を未記録 | cb ↔ ct は番号からの換算 (定数 0.280 s) | #1570 |
| soak30 (30 分) の HEAD 再測定は未実施 (§2 は `7c5ee224` の実測)。対象コードは差分 0 (§6) | 取込み後 HEAD での 30 分ソークの値は無い | PR #3159 の未解決表 (再測定のため子は起票しない) |

## 6. main 取込み後の再測定 (HEAD `c2cbf806`)

PR が main と競合したため main (`b34d93fe`) を取り込んだ (merge `c2cbf806`)。競合は `docs/DOC_MAP.md` の表 1 箇所のみ (AU-10 の行と新規 `REPORT_APPENDIX_1570.md` の行を両側が更新)。main 側の 2 行を残し、本 PR の `REPORT_AU29.md` 行を追加した。

測定 commit: `c2cbf806` (コード変更の最後の commit。以降は本ファイルと DOC_MAP のみ)。

コード差分 (`git diff 7c5ee224 c2cbf806 -- tools/audio public/worklets src/runtime --stat`):

```
 src/runtime/gui_hostcall.ts                |  23 ++-
 tools/audio/REPORT_APPENDIX_1570.md        |  63 +++++++
 tools/audio/REPORT_AU10.md                 |  91 ++++------
 tools/audio/REPORT_AU29.md                 |  66 +++++++
 tools/audio/REPORT_AU2_CI.md               |  33 ++--
 tools/audio/harness/run.mjs                |  15 +-
 tools/audio/results/au2/null_soak1800.json | 276 +++++++++++++++++++++++++++++
 7 files changed, 491 insertions(+), 76 deletions(-)
```

- 音声経路 (`public/worklets/fl-audio-worklet.js`・`src/runtime/audio-shim.ts`・`tools/audio/src`・`tools/audio/test`・`tools/audio/build.sh`・`tools/audio/flags.sh`・`tools/audio/harness/chrome.mjs`) の差分は 0 行。soak30 の §2 測定は、測定対象コードそのものである。
- `tools/audio/harness/run.mjs` (+12 −3) は main 側の `--busy` (負荷下ソーク) 追加。既定 (`--busy` なし) では `soakTag` が空文字・spawn は 0 本で、シナリオ名と結果ファイル名は変わらない。
- `src/runtime/gui_hostcall.ts` は GUI 側の変更。`tools/audio` の build・harness と `audio-shim.ts`・`audio-input.ts` からは参照されない (grep 0 件)。

実測 (HEAD `c2cbf806`): build は `EMSDK_ENV=<emsdk 6.0.12 の emsdk_env.sh> bash tools/audio/build.sh` で `build OK` (emcc 6.0.12、2.3 s)。emsdk は `[EMSDK]` の展開が素材に無かったため上流 (`emscripten-core/emsdk`) から `./emsdk install 6.0.12` で取得した。

| 試行 | 結果 | wall (host) / load 1 分平均 (開始→終了) |
|---|---|---|
| `--soak 10` 初回 | PASS: underruns 0, silence 0, ramp 0 / 480,512 f, workletErrors 0, cb 1,875 late 0, cb_max 15,074 µs, T=1024, dev_fill 128/818/1024, jumps 0 | 16.6 s / 0.82 → 0.87 |
| `--soak 10` 反復 1〜5 | 5/5 PASS: 各回 underruns 0, silence 0, ramp 0 / 480,512 f, workletErrors 0, secs_wall 10.004〜10.005 | 63.3〜63.8 s / 0.74→0.40, 0.40→0.13, 0.13→0.04, 0.04→0.01, 0.01→0.00 |

- 通算: HEAD で `--soak 10` は 6 回 6/6 PASS。§2 の断続 FAIL は HEAD では再現しなかった (原因は未特定のまま #1570)。
- 初回の wall 16.6 s は反復 (63 s 台) と違う。secs_wall と ramp の結果は通常どおりで、差の原因は未確認。
- `node tools/audio/test/worklet_jump_check.mjs` は HEAD で PASS 4/4 (exit 0)。
- HEAD の 6 回の soak10 では jump が 0 件で、`ct`・`pn`・`cb` の表示は実ブラウザで出力されていない。表示の経路は `worklet_jump_check.mjs` (mock) でのみ検査した。
- `--soak30` は HEAD で再測定していない (30 分の前景実行が本 run の時間上限に収まらないため)。§2 の結果は `7c5ee224` の実測で、対象コードは上記の差分 0 のとおり同一。
