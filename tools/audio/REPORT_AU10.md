# AU-10 (#191) 30 分ソーク (`--soak30`) 全文 — tools/audio/

> 本体 `REPORT.md` §16 から分割移動した全文 (内容は無変更。節番号は本体と一致させるため §16 を維持)。親: [`REPORT.md`](REPORT.md)。

## 16. AU-10 (#191) 30 分ソーク (`--soak30`)

既知類型との関係: 該当なし (ランタイム shim の長時間検証)。検証起点 commit: `0a721b0` (ブランチ `191-audio-soak30`, base `149f073`)。環境: GitHub runner 4 core / 15 GiB, headless Chrome 154.0.8037.97 (fake 出力シンク), emcc は toolchain-emsdk。

**実測の版の注意**: 下表の 30 分・負荷下・ネガコンは 0a721b0 (AU-7 取り込み前) の実測。現 head `fc93f45` は main (`44126c0`) を取り込んでおり (旧 head `57519ca` は main `790e003` 取り込み)、`FLASIO_PROFILE_ILWASAPI` 既定 0→1 (報告 min/gran 128/128 → 256/0)・`audio-shim.ts` の ATTACH 待ち (outputLatency 0 の間 最大 600 ms)・`flasio.c` の systemTime を含む。head `57519ca` での 30 分は未計測 (下の表の head 行を参照)。head `57519ca` の 10 秒ソークは下表の 2 行のとおり 4 回中 1 回 FAIL。

再現: `bash tools/audio/build.sh && node tools/audio/harness/run.mjs --soak30` (既定の全シナリオ実行・`e2e.sh` には含めない。`--soak <秒>` で秒数指定、`--inject-hiccup` でネガコン)。結果は `results/soak_<秒>.json` (既定の `results/results.json` は上書きしない)。合格条件 (AND): underrun 0 / silence 0 / ランプ全フレーム bit-exact / 実フレーム ≥ 公称×99% / `secs_wall` ≥ 公称 / worklet エラー 0・abort なし・exit=1(完了)。不合格は runner が exit 1。

| 実行 | 結果 | 所要 / load average (開始→終了, 1 分平均) |
|---|---|---|
| **30 分 (1800 s) B=256 48k ランプ・無負荷** | **PASS**: underruns 0, silence 0, ramp mismatches **0 / 86,402,944 f**, cb 337,509 回 (late 0, 最大 199 µs), `T`=1536 f 固定 (lat_changes 0), clock 48000.0 Hz, `secs_wall` 1800.053 | 1801.5 s / 0.11 → 0.07 |
| 420 s ランプ・**負荷下** (busy ループ 14 本を 560 s 並走) | **PASS**: underruns 0, silence 0, ramp 0 / 20,159,232 f, cb 78,747 回 (late 0, 最大 479 µs), lat_changes 2 (T=1536 のまま), clock 47996.2 Hz | 476.1 s / 0.06 → **16.56** (15 分平均 6.76 まで上昇) |
| ネガコン: 15 s + 60 ms hiccup 混入 (`--inject-hiccup`) | **FAIL (exit 1)**: underruns 8, silence 5120 f, ramp mismatches 670,464 / 721,408 | 68.5 s / 0.04 |
| 短縮確認 `--soak 10` (3 回) | 初回は gate の完了判定が `exit===0` で誤って FAIL (完了コードは 1) → `exit===1` に修正。修正後 2 回とも PASS (ramp 0 / 481,024 f) | 63.5 s (修正後 1 回目) / 0.16 → 0.06 |
| **head `57519ca` の `--soak 10` (計 3 回、`build.sh` 直後)** | **1 回目 FAIL (exit 1)**: underruns 1, silence 128 f, ramp mismatches 411,392 / 480,512 (T=1280 (26.7 ms), lat_changes 1, dev_fill min 0)。**2 回目 PASS** (ramp 0 / 480,512 f, underruns 0, T=1536, lat_changes 0)、**3 回目 PASS** (ramp 0 / 481,024 f, underruns 0, T=1536)。FAIL の原因は未特定 (1 回目は build 直後の初回実行。load は 0.32 → 0.46 と低い) | 70.4 s / 0.32 → 0.46 (FAIL)、63.4 s / 0.39 → 0.68、63.3 s / 0.68 → 0.23 |

**既存バグの修正 (副産物)**: `test/fla_test.c` のランプは `(n & 0xFFFFFF)+1` で 2^24 f (= 349.5 s @48k) で巻き戻るが、`test/page.mjs` の照合は `p+1` 固定だった。120 s では露見せず、**30 分では必ず mismatch になる**ので 24bit 巻き戻しに合わせた。420 s / 1800 s の PASS は巻き戻しを跨いだ照合 (1800 s では 86,402,944 ÷ 16,777,216 = 5.15 → 5 回) を含む。旧照合での FAIL 再現 (ネガコン) は**未実施** (巻き戻し地点以降は定義上不一致、の理屈のみ)。

検証範囲 / 範囲外: fake 出力シンクで、実機デバイス・Firefox/Safari は未計測 (#187 AU-2)。無負荷 30 分は 1 回 (n=1)。**負荷下 (load avg 10 超) の 30 分は未実施** (60 分ジョブ上限のため 420 s で代替)。キャプチャ SAB は 1800 s で 86,402,944 f × 2ch × 4 B ≈ 659 MiB。COM 経路 (#271) の 30 分、親 e2e `asio_ramp_b256_soak120` の既定組込は範囲外。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 負荷下 (load avg 10 超) の **30 分**ソーク未実施 | #191 スコープの「負荷下の結果も記録」は 420 s のみ | #191 にコメント (別 run で `--soak30` + busy 並走) |
| COM 経由 (`asio/e2e.sh --soak 1800`) 30 分 | #271 が COM 経路。キャプチャ約 661 MiB の分割照合設計が要る | #191 に提案 |
| COM 経路 harness の固定 `p + 1` 照合 (`asio/harness/com_page.mjs:95`)。生成元 `asio/test/com_test.c:84` は `(n & 0xFFFFFF)+1` で 2^24 f で巻き戻る = test/page.mjs と同一バグ | `asio/e2e.sh --soak` で 349.5 s 超は ramp mismatch → FAIL (コード読解による判断・未実行) | #191 にコメント。COM 側の修正は 360 s 以上の実測を添えて別 commit |
| **head `fc93f45` (main `44126c0` 取り込み後、`build.sh` OK 2.5 s) の `--soak 10`** | **PASS (exit=1 完了)**: underruns 0, silence 0, ramp 0 / 481,024 f, T=1024 (21.3 ms), lat_changes 0, secs_wall 10.004 | 71.6 s / 0.25 → 0.20 |
| head `fc93f45` での 30 分ソーク (無負荷) は**未実施** (未計測)。fix run の 40 分上限に 30 分 + build が収まらないため見送り。上の表の 30 分行は `0a721b0` (AU-7 取り込み前) のもので、マージ後の shim (`audio-shim.ts` ATTACH 待ち・`FLASIO_PROFILE_ILWASAPI` 既定 1) では未計測。fix run の 40 分上限に 30 分 + build が収まらないため見送り | #191 にコメント (別 run で `bash tools/audio/build.sh && node tools/audio/harness/run.mjs --soak30` を head で実施) |
| head `57519ca` の `--soak 10` が 4 回中 1 回 FAIL (underrun 1・ramp mismatch 411,392 f、T=1280 で lat_changes 1)。原因未特定。同 head の 2 回目・3 回目は PASS | 断続的な欠陥か計測ノイズかを切り分けていない。30 分実測の信頼性にも関わる | #191 にコメント (head で `--soak 10` を 5 回以上反復し、FAIL 時の `T`・dev_fill・underrun のログを採る) |
| 旧 page.mjs (巻き戻し非対応) での FAIL 再現未実施 | 修正の必要性は理屈のみ | 本 REPORT に明記 |

### 16.1 `6aa4b39` head での再計測 (2026-10-13, run 191-head)

計測対象は `6aa4b39` head。計測時点 (main `b069ecb9`) での再計測は未実施 (`6aa4b39` 以降に `tools/audio` の 11 ファイル・103 行追加・13 行削除が main に入っている)。

環境: GitHub runner 4 core / 15 GiB, headless google-chrome, `bash tools/audio/build.sh` 直後。結果は `results/soak_<秒>.json`。

| シナリオ | 結果 | 所要 / load (開始→終了) |
|---|---|---|
| **30 分 (1800 s) B=256 48k ランプ・無負荷** | **PASS (exit=1 完了)**: underruns 0, silence 0, ramp mismatches 0 / 86,402,048 f, cb 337,506 回 (late 0, 最大 18,165 µs), T=1024 (21.3 ms), lat_changes 0, dev_fill min/avg/max 128/799/1024, clock 47,999.8 Hz, secs_wall 1800.034 | 1812.4 s / 0.56 → 0.00 |
| `--soak 10` (head `6aa4b39`, 結果 JSON は 1 回分のみコミット: `results/soak_10.json`, ran_at 15:37:16) | **PASS (exit=1 完了)**: underruns 0, silence 0, ramp 0 / 480,512 f, T=1536, burst_obs 512, cb_max 370 µs, secs_wall 10.005 | 63.5 s / 0.03 → 0.06 |
| **420 s ランプ・負荷下** (busy ループ 14 本を並走) | **PASS (exit=1 完了)**: underruns 0, silence 0, ramp 0 / 20,168,192 f, cb 78,783 回 (late 0, 最大 184 µs), T=1536, lat_changes 1, clock 47,988.5 Hz | 476.5 s / 1.32 → 1 分平均 **14.15** (終了時 load 1 分/5 分/15 分 = 14.15 / 12.89 / 6.64) |

- 30 分 JSON (`results/soak_1800.json`) の旧版からの変化と、その扱い:
  - `depth` 6 → 4 (`reported.lat_out0` 3073 / `olat_us0` 30000 を新たに記録)。query は両版とも `depth=2` で同一。実効 depth の変化の原因は**未特定**。committed JSON 間で burst_obs と T の対応は一意に決まらない (`soak_10`: burst 512 → T 1536 / `soak_1800`: burst 512 → T 1024)。OPEN 時の較正値は JSON に残っていないため、設定差かどうかも未確定。
  - `clock_jumps` 10 (snapshot, `clock_jump_frames` 0)。比較元となる旧版の記録は §16 の表に無く、原因は**未調査**。ramp 照合は 86,402,048 f 全て一致 (mismatch 0)。
  - `cb_max_us` 18,165 µs (旧版 199 µs)。原因は**未調査**。late 0 (コールバック遅延の検出なし) の値。
- 本節の 30 分値は head `6aa4b39` (`AU-7` 取り込み後) の実測で、§16 の表の `0a721b0` 版より新しい。
- 未解決: **負荷下の 30 分ソーク** は未実施 (420 s で代替)。COM 経路 (#271) の 30 分は §16 の未解決表のとおり範囲外。

### 16.2 負荷下 30 分ソーク (2026-10-13, run 191-load, main `b6c91afd` の worktree)

環境: GitHub runner 4 core / 15 GiB, headless google-chrome 154, `bash tools/audio/build.sh` 直後。busy ループ (`while :; do :; done`) 14 本を `--soak30` と同時に並走させ、終了後に PID 指定で停止。結果は `results/soak_1800_load.json` (無負荷の `soak_1800.json` とは別ファイル)。

| シナリオ | 結果 | 所要 / load (開始→終了) |
|---|---|---|
| **30 分 (1800 s) B=256 48k ランプ・負荷下 (busy 14 本並走)** | **PASS (runner exit=1 完了)**: underruns 0, silence 0, ramp mismatches **0 / 86,387,968 f**, cb 337,451 回 (late 0, 最大 450 µs), burst_obs 1024, T=1536 (32.0 ms) 固定 (lat_changes 0, grows 0, shrinks 0), clock 47,980.5 Hz, secs_wall 1800.054 | 1815.7 s / 0.28 → **16.77** (終了時 1 分/5 分/15 分 = 16.77 / 16.76 / 14.48) |

- 無負荷 30 分 (§16.1) との比較: 両方とも underrun 0・ramp 0。負荷下は T が 1536 のまま (無負荷は 1024)、cb_max 450 µs (無負荷 18,165 µs 〔未調査〕とは別の値で、負荷下の方が小さい)。
- 検証範囲: 負荷は busy ループのみ (4 core に 14 本)。実 FL/他プロセスの負荷・実機デバイスは未計測。n=1。
- 本節で §16.1 の「負荷下 30 分は未実施」は解消。COM 経路 (#271) の 30 分は範囲外のまま (未解決表どおり)。

### 16.3 AU-18 (#1106) 切り分け: head `d7d91d2` での反復と 30 分再計測 (2026-10-13, run 1106)

測定 commit: `d7d91d2` (main, コード変更なし。本 run は `tools/audio/REPORT_AU10.md` のみ変更)。環境: GitHub runner 4 core / 15 GiB, headless google-chrome, `bash tools/audio/build.sh` 直後 (build OK 2.3 s)。生ログ・JSON は `tools/audio/work/soak10/` (gitignore) に保存。

| 試行 | 結果 | 所要 / load (開始→終了) |
|---|---|---|
| `--soak 10` 1 回目 | PASS: underruns 0, silence 0, ramp 0 / 481,024 f, T=1536, lat_changes 0, cb_max 70 µs | 76 s / 0.08 → 0.24 |
| `--soak 10` 2 回目 | PASS: underruns 0, ramp 0 / 481,024 f, T=1536, cb_max 44 µs | 64 s / 0.24 → 0.32 |
| `--soak 10` 3 回目 | PASS: underruns 0, ramp 0 / 480,512 f, T=1536, cb_max 80 µs | 63 s / 0.08 → 0.25 |
| `--soak 10` 4 回目 | PASS: underruns 0, ramp 0 / 481,024 f, T=1536, cb_max 80 µs | 64 s / 0.02 → 0.20 |
| `--soak 10` 5 回目 | PASS: underruns 0, ramp 0 / 480,512 f, T=1536, cb_max 324 µs | 63 s / 0.01 → 0.16 |
| **`--soak30` (1800 s, 無負荷)** | **PASS (exit=1 完了)**: underruns 0, silence 0, ramp **0 / 86,408,192 f** (全フレーム一致), cb 337,539 回 late 0, **cb_max 184 µs**, T=1536, dev_fill min/avg/max 1024/1299/1536, **clock_jumps 4 / clock_jump_frames 0**, secs_wall 1800.03 | 1802 s / 0.05 → 0.15 |

結論:
- head `57519ca` で 4 回中 1 回出た `--soak 10` の FAIL は、head `d7d91d2` の 5 回では**再現しなかった** (6aa4b39 の 1 回も PASS)。通算で FAIL は 1/10 回。原因は**未特定**。FAIL 時の T・dev_fill のログは今回の試行では採れていない。
- 30 分 JSON の値 (`results/soak_1800.json`, head `6aa4b39`) の再計測: `cb_max_us` 18,165 µs → 今回 184 µs、`clock_jumps` 10 → 4。旧 18 ms は単発の大きい spike だった可能性が高いが、spike 単発の原因は未特定 (一度きりで再現せず)。`clock_jumps` は件数が試行ごとに変わり、`clock_jump_frames` 合計は 0 のまま。ramp は全フレーム bit-exact のため、音声データの欠落は無いと判断する。
- 計測経路 (コード読解): `cb_max_us` は producer スレッドの `do_buffer` 内で `emscripten_get_now()` 差を取った wall-clock 時間 (`tools/audio/src/flasio.c` L200-204 = `bufferSwitch` 1 回の所要)。`clock_jumps` は worklet の `process()` が `currentFrame` の連続性を見る件数 (`public/worklets/fl-audio-worklet.js` L92-95 = `frame !== prevFrame + Q` で計上・`clock_jump_frames` はその差の合計)。shim の underrun とは別計上 (`tools/audio/docs/PROTOCOL.md` L69)。
- 未解決: 10 秒ソーク FAIL の原因、30 分の `cb_max` spike の原因 (単発・未再現)、`clock_jumps` の発生源 (ブラウザ側スキップか、計測タイミングか) は未特定。子 issue で追う (下記)。

### 16.4 AU-20 (#1363) 切り分け: head `12586095` での 30 分 1 回・10 秒 5 回 (2026-10-13〜14)

測定 commit: `12586095` (origin/main, コード変更なし。本 run は `tools/audio/REPORT_AU10.md` のみ変更)。環境: GitHub runner 4 core / 15 GiB, headless google-chrome 154, `bash tools/audio/build.sh` 直後 (emcc 6.0.12)。生ログ・JSON は `tools/audio/work/soak10/` (gitignore)。

| 試行 | 結果 | 所要 / load (開始→終了) |
|---|---|---|
| `--soak 10` 1〜5 回目 | 5/5 PASS: underruns 0, silence 0, ramp 0 / 480,512 f (全 5 回), workletErrors 0, lat_changes 0。cb_max 25 / 70 / 45 / 770 / 50 µs。dev_fill min 1024 (全 5 回)、clock_jumps 0 (全 5 回) | 各 63 s / 0.01〜0.15 |
| `--soak30` (1800 s, 無負荷) 1 回目 | PASS (exit=1 完了): underruns 0, silence 0, ramp 0 / 86,406,272 f, workletErrors 0, **cb_max 169 µs**, T=1024, dev_fill 512/794/1024, **clock_jumps 14 / clock_jump_frames 0** | 1808 s / 0.41 → 0.16 |

結論:
- 10 秒ソーク FAIL は今回 5 回で再現せず (通算 head `57519ca`〜`12586095` で 1/15)。FAIL 時の T・dev_fill・underrun・lat_changes は harness の console 行と `soak_<秒>.json` に既に出る仕組みで、本 run では FAIL が出ないため採取データは無い。原因は**未特定**。
- 30 分ソークの `cb_max` spike (18 ms 級) は今回の 1 回で再現せず (169 µs)。前回 d7d91d2 の 184 µs と合わせ 2 回とも 1 ms 未満。spike の発生時刻・原因は未特定。
- `clock_jumps` は 30 分ソークで 14 件だが `clock_jump_frames` は 0。件数は試行ごとに 4 → 14 と変動し、欠落フレームは無い。ramp は全フレーム bit-exact。発生源 (ブラウザ側スキップか計測タイミングか) は未特定。
- 次の切り分けは子 issue で行う (下記)。

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

測定 commit: `5229fe5f` (origin/main 起点、本 run は `tools/audio/REPORT_AU10.md` のみ変更)。環境: GitHub runner 4 core / 15 GiB, headless google-chrome, `bash tools/audio/build.sh` 直後 (emcc 6.0.12, [EMSDK] 既存)。生ログは `tools/audio/work/` 側・JSON は `tools/audio/results/soak_10.json` / `soak_1800.json` (gitignore 対象の生成物)。

| 試行 | 結果 | 所要 / load (start → end) |
|---|---|---|
| `--soak 10` 1〜5 回目 | 5/5 PASS: underruns 0, silence 0, ramp 0 / 480,512〜481,024 f (全 5 回), workletErrors 0, lat_changes 0, clock_jumps 0 (全 5 回)。cb_max 100 / 64 / 864 / 74 / 94 µs。dev_fill min 256 (1 回目, T=1024) / 1024 (2〜5 回目, T=1536) | 各 61〜73 s / 0.49 → 0.04 |
| `--soak30` (1800 s, 無負荷) 1 回目 | PASS (exit 1 完了): underruns 0, silence 0, ramp 0 / 86,403,968 f, workletErrors 0, cb 337,513 回 late 0, **cb_max 344 µs**, T=1536, dev_fill 1024/1308/1536, **clock_jumps 8 / clock_jump_frames 0**, lat_changes 0, secs_wall 1800.07 | 1802 s / 0.01 → 0.00 |

判定:
- 10 秒ソーク FAIL は今回 0/5 回。通算 (head `57519ca`〜`5229fe5f`) で 2/26。原因は**未特定**。FAIL 試行の採取データは §16.5 の 1 回のみ。
- 30 分ソーク (無負荷) の ms 級 spike は今回も未再現 (cb_max 344 µs)。無負荷 30 分の通算は 3 回 (`d7d91d2`・`12586095`・`5229fe5f`) で、cb_max は 184 / 169 / 344 µs (いずれも 1 ms 未満)。
- `clock_jumps` は 30 分で 8 件 (通算 2 / 4 / 14 / 8 件と変動)、`clock_jump_frames` は通算 0 のまま。ramp は全フレーム bit-exact で実スキップの証拠は無い。発生源は未特定。
- 負荷下の 30 分ソークは本 run では未実施 (§16.2 が最新)。
