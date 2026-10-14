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

### 16.5〜16.7 AU-21 (#1570) 切り分け 1〜3 (head `60932d35`・`5229fe5f`・`c2f67568`)

全文は付録 `REPORT_APPENDIX_1570.md` に分割移動 (250 行上限・内容は無変更)。結論: 10 秒 FAIL は通算 2/31 まで、30 分無負荷 cb_max は 1 ms 未満、clock_jumps の符号付き合計は 0 のまま。

### 16.8 AU-21 (#1570) 切り分け 4: head `429f36bd` (clock_jump の計上分離)

測定 commit: `429f36bd` (origin/main `54bacdc0` 起点の worktree `ws-1570`)。コード変更は worklet の計上分離と、それを読み出す C/TS 表・snapshot・harness 表示の追加: `clock_jump_frames` の符号付き合計に加え、正の成分 `clock_skip_frames` (描画されなかったフレーム)・負の成分の絶対値 `clock_dup_frames`・1 回の最大 jump `clock_jump_max` と発生 quantum 番号 `clock_jump_max_q` を追加 (`pad2` の未使用領域、既存オフセットは不変)。C 表 (`flaudio.h` / `flaudio.c`)・TS 表と snapshot (`audio-layout.ts` / `audio-shim.ts`)・harness 表示 (`run.mjs`) を同時更新。環境: GitHub runner 4 core / 15 GiB, headless google-chrome 154, `bash tools/audio/build.sh` OK (3.1 s, emcc 6.0.12, [EMSDK] 既存)。生ログは `tools/audio/work/soak10/` (gitignore)。

| 試行 | 結果 | 所要 / load (開始→終了, UTC) |
|---|---|---|
| `--soak 10` 1 回目 (build 直後) | PASS: underruns 0, ramp 0 / 480,512 f, T=1536, cb_max 3,140 µs, jumps 0 (skip 0 / dup 0) | 64.3 s / 0.07 → 0.02 (14:34:36〜14:35:40) |
| `--soak 10` 2〜4 回目 | 3/3 PASS: underruns 0, ramp 0 / 480,512〜481,024 f, T=1536, cb_max 114 / 409 / 79 µs, jumps 0 (全 3 回) | 3 回合計 189 s (15:06:24〜15:09:35) |
| **`--soak30` (1800 s, 無負荷)** | **PASS**: underruns 0, silence 0, ramp 0 / 86,404,352 f, workletErrors 0, cb 337,515 回 late 0, **cb_max 155 µs**, T=1536, dev_fill 1024/1308/1536, lat_changes 0, secs_wall 1800.08, **clock_jumps 2 / clock_jump_frames 0 (skip +128 f ×1, dup −128 f ×1, max 128 f @ quantum 274,688)** | 1801.6 s / 0.02 → 0.00 (14:36:00〜15:06:01) |

判定:
- 30 分ソーク (無負荷) の通算は 6 回 (`d7d91d2`・`12586095`・`60932d35`・`5229fe5f`・`c2f67568`・`429f36bd`)。cb_max は 184 / 169 / 475 / 344 / 385 / 155 µs で、いずれも 1 ms 未満。ms 級 spike は未再現。
- clock_jumps (新計上): 本試行の 2 件は「描画されなかった 1 quantum (+128)」と「重複 1 quantum (−128)」で、符号付き合計 0 のため従来の `clock_jump_frames` には 0 として現れていた。通算 6 回の 30 分試行の件数 4 / 14 / 2 / 8 / 4 / 2 はすべて偶数で、符号付き合計は全て 0。「±の組で出る」仮説と整合するが、この 1 試行では 2 件が隣接していたか未確認 (`clock_jump_max_q` は最初の 1 件のみ記録)。ramp は全フレーム bit-exact で、データ欠落の証拠は無い。**発生源 (ブラウザ描画時刻のずれか、計測側か) は未特定**。
- 10 秒ソーク FAIL: 本 head では 0/4 回 (初回含む)。通算 (head `57519ca`〜`429f36bd`) で 2/35。原因は**未特定**。初回 run の cb_max 3,140 µs は FAIL 試行の 174 ms とは桁が異なり、関係は未確認。
- 負荷下の 30 分ソークは本 run では未実施 (§16.2 が最新)。

未解決:

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 10 秒ソーク FAIL の原因 (通算 2/35) | 30 分実測の信頼性 | #1570 (再現待ち。FAIL 時は `clock_jump_max_q`・dev_fill・underrun を採取) |
| clock_jumps の発生源: 2 件の隣接性と、±組の仮説の検証 (30 分試行を追加して全件の位置を取る必要あり) | 「実スキップか計測か」の切り分けが未完 | #1570 |
| 負荷下 (load avg 10 超) の 30 分ソーク | 負荷下の clock/ spike は未計測 | #1570 |

鮮度の証跡 (docs/WORKFLOW.md §6): 測定 commit `429f36bd` → HEAD の `git diff --stat 429f36bd HEAD -- tools/audio public/worklets src/runtime` は REPORT_AU10.md のみ (修正 commit 時点で確認。e2e が取り込むのは `build.sh` が cp する `public/worklets/fl-audio-worklet.js` と、トランスパイルされる `src/runtime/`)。

### 16.9 AU-21 (#1570) 切り分け 5: head `084d2e36` (jump の位置・cb_max の発生 quantum を記録)

測定 commit: `084d2e36` (origin/main `f1711848` 起点の worktree `ws-1570`、ブランチ `1570-au21-soak-triage-4`)。コード変更は計測の追加のみ。worklet が clock_jump の**最初と直近の位置** (`clock_first_q` / `clock_last_q`: process() 通し番号、bit31 = 負 = 重複・後退) を、producer が **cb_max_us を更新した時点の quantum 番号** (`cb_max_q`) を記録する。`pad2[3]` (180〜191) を置換し、構造体サイズ (384 B) と既存オフセットは不変。C 表 (`flaudio.c` g_layout)・TS 表 (`audio-layout.ts`)・snapshot (`audio-shim.ts`)・harness 表示 (`run.mjs`) を同時更新し、`verifyLayout` は通過。環境: GitHub runner 4 core / 15 GiB, headless google-chrome 154, `bash tools/audio/build.sh` OK (3.0 s, emcc 6.0.12, [EMSDK] 既存)。生ログ・JSON は `tools/audio/work/soak10/` (gitignore)。quantum 番号 q の時刻換算は q × 128 / 48000 s。

| 試行 | 結果 | 所要 / load (開始→終了, 1 分平均) |
|---|---|---|
| `--soak 10` 1 回目 (16:45:23 UTC) | PASS: underruns 0, ramp 0 / 481,024 f, T=1536, cb_max 90 µs (cb_max_q 177 ≈ 0.47 s), jumps 0 | 64.1 s / 0.10 → 0.06 |
| `--soak 10` 2 回目 | PASS: underruns 0, ramp 0 / 481,024 f, T=1536, cb_max 70 µs (cb_max_q 176 ≈ 0.47 s), jumps 0 | 63.5 s / 0.00 → 0.00 |
| `--soak 10` 3 回目 | PASS: underruns 0, ramp 0 / 481,024 f, T=1536, cb_max 199 µs (cb_max_q 1,424 ≈ 3.8 s), jumps 0 | 63.5 s / 0.00 → 0.35 |
| **`--soak30` (1800 s, 無負荷)** (16:46:36〜17:16:38 UTC) | **PASS**: underruns 0, silence 0, ramp **0 / 86,401,536 f**, cb 337,504 回 late 0, **cb_max 1,055 µs (cb_max_q 550,685 ≈ 1,468.5 s)**, T=1536 固定 (lat_changes 0), dev_fill 1024/1311/1536, **clock_jumps 6 / skip 384 f (+128 × 3) / dup 384 f (−128 × 3) / 符号付き合計 0**, first −q451,592 (≈ 1,204.2 s), last +q655,407 (≈ 1,747.7 s) | 1801.5 s / 0.05 → 0.00 |

判定:
- 30 分ソーク (無負荷) の通算は 7 回 (`d7d91d2`・`12586095`・`60932d35`・`5229fe5f`・`c2f67568`・`429f36bd`・`084d2e36`)。cb_max は 184 / 169 / 475 / 344 / 385 / 155 / **1,055** µs。1 ms 超は §16.1 の 18,165 µs に続く 2 例目。ただし 18 ms 級の再現は無く、今回の 1,055 µs も単発で原因は**未特定**。発生時刻は q550,685 (≈ 1,468.5 s、試行の後半)。
- clock_jumps (今回の 30 分): 6 件で、skip と dup が 3 件ずつ・符号付き合計 0 (§16.8 の「±組」仮説と整合)。ただし記録した最初 (dup, q451,592) と直近 (skip, q655,407) は 543.5 s 離れており、**単一の隣接ペアではない**。中間 4 件の位置は未記録のため、隣接性と発生源は**未特定**。cb_max_q (q550,685) は記録した 2 件のどちらとも一致しない。
- 10 秒ソーク: 本 head で 3/3 PASS。通算 (head `57519ca`〜`084d2e36`) で FAIL は 2/38。原因は**未特定**。FAIL 時の `cb_max_q` 採取データは無い (§16.5 の 1 回のみ、cb_max 174 ms)。
- 負荷下の 30 分ソークは本 run では未実施 (§16.2 が最新)。

鮮度の証跡 (docs/WORKFLOW.md §6): 測定 commit `084d2e36` → 本 REPORT commit の `git diff --stat 084d2e36 HEAD -- tools/audio public/worklets src/runtime` は REPORT_AU10.md のみ (PR 作成時点で確認。出力は PR 本文に添付)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 10 秒ソーク FAIL の原因 (通算 2/38) | 30 分実測の信頼性 | #1570 (FAIL 時は cb_max_q・dev_fill・underrun・clock_first_q/last_q を採取) |
| clock_jumps 6 件のうち中間 4 件の位置 (隣接性) と発生源 | 実スキップか計測由来かの切り分けが未完 | #1570 (全件の位置記録は次の実装) |
| cb_max 1,055 µs (q550,685) の原因 | 単発の 1 ms 超。原因不明 | #1570 |
| 負荷下 (load avg 10 超) の 30 分ソーク | 負荷下の clock・spike は未計測 | #1570 |

### 16.10 AU-21 (#1570) 切り分け 6: head `c62dd783` (clock_jump の全件位置を記録)

測定 commit: `c62dd783` (origin/main `26f90ada` 起点の worktree `ws-1570`、ブランチ `1570-au21-soak-triage-5`)。コード変更は計測の追加のみ: worklet が clock_jump 1 件ごとに `port` で `{q, d, frame, prev, ms}` を通知 (上限 256 件)、shim が `clockJumpLog` に積み、`test/page.mjs` の result と harness 表示 (`clock_jump_log=`) に出す。SAB の Atomics 配列 (layout) は不変。`q` は process() の通し番号 (計上時点の値)、`d` = `frame - prev - 128` (+ = 描画されなかった frame、− = 同一 frame の重複)、`frame` = worklet の currentFrame。環境: GitHub runner 4 core / 15 GiB, headless google-chrome 154, `pnpm install --frozen-lockfile` 後 `bash tools/audio/build.sh` OK (1.95 s, emcc 6.0.12, [EMSDK] 既存)。生ログは repo 外の作業ディレクトリ、結果 JSON は `tools/audio/results/soak_10.json` / `soak_1800.json` (未コミット)。

| 試行 | 結果 | 所要 / load (開始→終了, 1 分平均) |
|---|---|---|
| `--soak 10` 初回 (build 直後, 19:21 UTC) | PASS: underruns 0, ramp 0 / 480,512 f, T=1024, cb_max 74 µs, clock_jump_log なし | 70.2 s / 0.38 → 0.20 |
| `--soak 10` 1〜5 回目 (19:53〜19:58 UTC) | **5/5 PASS**: underruns 0, silence 0, ramp 0 / 480,512 f (全 5 回), workletErrors 0, clock_jump_log なし (全 5 回)。cb_max 395 / 44 / 64 / 34 / 369 µs, T=1536, dev_fill min 1024 | 各 63.3〜63.4 s / 0.06→0.02, 0.02→0.00, 0.00→0.00, 0.00→0.00, 0.00→0.03 |
| **`--soak30` (1800 s, 無負荷)** (19:22:54〜19:52:55 UTC) | **PASS**: underruns 0, silence 0, ramp **0 / 86,407,296 f**, workletErrors 0, cb 337,526 回 late 0, **cb_max 340 µs** (cb_max_q 11,938 ≈ 31.8 s), T=1024 固定 (lat_changes 0), dev_fill 512/786/1024, **clock_jumps 6 件** (skip 384 f / dup 384 f / 符号付き合計 0), secs_wall 1800.139 | 1801.3 s / 0.20 → 0.08 |

30 分試行の jump 全 6 件 (`clock_jump_log`):

| q (process 通し番号) | d (frames) | frame (currentFrame) | 時刻 (frame ÷ 48000) |
|---|---|---|---|
| 22314 | −128 (重複) | 2,869,632 | 59.78 s |
| 22315 | +128 (描画されなかった frame) | 2,869,888 | 59.79 s |
| 60187 | −128 | 7,717,376 | 160.78 s |
| 60188 | +128 | 7,717,632 | 160.78 s |
| 383062 | −128 | 49,045,376 | 1,021.78 s |
| 383063 | +128 | 49,045,632 | 1,021.78 s |

判定:
- **発生パターンの確定**: 6 件は 3 組の隣接ペア (q と q+1)。各組は「同じ currentFrame P の process() が 2 回 (P, P)、続けて P+256 (2 quantum 分進む)」の並びで、dup 側の `prev` は同じ frame を指す。符号付き合計は各組 0 (§16.8 の「±組」仮説と、§16.9 の「単一の隣接ペアではない」は、この 30 分では 3 組それぞれ隣接で一致)。
- **発生源の切り分け**: `currentFrame` はブラウザの音声スレッドの frame カウンタで、shim・harness の計測は値を書かない。よって「計測タイミングの誤差」ではなく、ブラウザの render thread が process() を同一 frame で 2 回呼んだ結果と判定する。`skip` (+128) 単独では実スキップに見えるが、直前の重複 (−128) と対になり、出力 sample は ramp 照合で 86,407,296 f 全て一致 (6 件の前後も含む)。よって音声の欠落・重複の証拠は無い。ただし「なぜ同一 frame の process() が 2 回呼ばれるか」(ブラウザ内部の起床・再描画の条件) は**未特定**。
- 30 分ソーク (無負荷) の通算は 8 回。cb_max は 184 / 169 / 475 / 344 / 385 / 155 / 1,055 / 340 µs。ms 級 spike は今回も未再現。1,055 µs (q550,685) の原因は未特定 (今回の jump の位置 q22314 等とは一致しない)。
- 10 秒ソーク FAIL: 本 head で 0/6 回 (初回 1 + 反復 5)。通算 (head `57519ca`〜`c62dd783`) で **2/44**。原因は**未特定**、FAIL 時の採取データは §16.5 の 1 回のみ。
- 負荷下の 30 分ソークは本 run では未実施 (§16.2 が最新)。
- 検証範囲: 30 分は無負荷 n=1。jump は 1 試行 (6 件) のみで、件数・位置の再現性は未確認。

鮮度の証跡 (docs/WORKFLOW.md §6): 測定 commit `c62dd783` → 本 REPORT commit の `git diff --stat c62dd783 HEAD -- tools/audio public/worklets src/runtime` は REPORT_AU10.md のみ (PR 作成時点で確認)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 10 秒ソーク FAIL の原因 (通算 2/44) | 30 分実測の信頼性 | #1570 (再現待ち。FAIL 時は cb_max_q・dev_fill・underrun・clock_jump_log を採取) |
| 同一 frame の process() が 2 回呼ばれる条件 (ブラウザ内部の起床・再描画) | clock_jumps の発生源 (無害と判定するための根拠が sample 照合のみ) | #1570 (30 分試行の追加で件数と時刻・cb 時刻の相関を取る) |
| cb_max 1,055 µs (q550,685) の原因 | 単発の 1 ms 超。原因不明 | #1570 |
| 負荷下 (load avg 10 超) の 30 分ソーク | 負荷下の clock・spike は未計測 | #1570 |

### 16.11 AU-21 (#1570) 切り分け 7: head `306ecc9b` (負荷並走 30 分ソーク `--busy N`)

測定 commit: `306ecc9b` (origin/main `e64cfc70` 起点の worktree `ws-1570`、ブランチ `1570-au21-load-soak`)。コード変更は harness のみ: `harness/run.mjs` に `--busy <N>` を追加 (soak 指定時のみ。busy ループ N 本を `sh -c "while :; do :; done"` で並走させ、終了後に各子プロセスを `kill()` で PID 指定停止)。結果は `soak_<秒>_busy<N>.json` に出し、無負荷の結果は上書きしない。worklet・shim・C 側は不変。環境: GitHub runner 4 core / 15 GiB, headless google-chrome 154, `pnpm install --frozen-lockfile` 後 `bash tools/audio/build.sh` OK (emcc 6.0.12, [EMSDK] 既存)。結果 JSON は `tools/audio/results/` (未コミット)。

| 試行 | 結果 | 所要 / load (開始→終了) |
|---|---|---|
| `--soak 10 --busy 14` (動作確認, 21:33 UTC) | PASS: underruns 0, silence 0, ramp 0 / 480,896 f, workletErrors 0, cb_max 80 µs, T=1536, clock_jumps 0 | 78.5 s / 0.34 → 12.84 |
| **`--soak30 --busy 14`** (1800 s, busy 14 本並走, 21:35〜22:05 UTC) | **PASS (exit 1 完了)**: underruns 0, silence 0, ramp **0 / 86,394,752 f**, workletErrors 0, cb 337,478 回 late 0, **cb_max 400 µs** (cb_max_q 24,640 ≈ 65.7 s), T=1536 固定 (lat_changes 0), dev_fill 512/1311/1536, **clock_jumps 2 件** (dup −128 f @ q631980 → skip +128 f @ q631981, 符号付き合計 0), secs_wall 1800.107 | 1803.8 s / 9.99 → 終了時 (busy 停止直後) 1 分/5 分/15 分平均 16.86 / 16.59 / 14.48 |

判定:
- 負荷下 (busy 14 本、load avg 10〜17) の 30 分ソークを現 head で初めて実施し、PASS。ramp は全フレーム bit-exact、underrun 0。cb_max 400 µs で ms 級 spike は未再現。旧 head の §16.2 (busy 14, cb_max 450 µs) とも同程度。
- clock_jumps は 2 件で、§16.10 と同じ「dup −128 の直後に skip +128」の隣接ペア 1 組。負荷下で件数が増えたかは n=1 のため判断できない。同一 frame の process() が 2 回呼ばれる条件は**未特定**。
- 10 秒ソーク FAIL: 本 run では反復せず、動作確認の 1 回 (負荷下) が PASS のみ。通算 2/45 (分母 +1)。原因は**未特定**。

鮮度の証跡 (docs/WORKFLOW.md §6): 測定 commit `306ecc9b` → 本 REPORT commit の `git diff --stat 306ecc9b HEAD -- tools/audio public/worklets src/runtime` は REPORT_AU10.md のみ (PR 作成時点で確認)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 10 秒ソーク FAIL の原因 (通算 2/45) | 30 分実測の信頼性 | #1570 (FAIL 時は cb_max_q・dev_fill・underrun・clock_jump_log を採取) |
| clock_jumps の発生源 (隣接ペアで同一 frame の process() が 2 回呼ばれる条件) | 無害判定の根拠は sample 照合のみ | #1570 |
| cb_max 1,055 µs (§16.9) の原因 | 単発の 1 ms 超。原因不明 | #1570 |
| 負荷の強さを変えた 30 分ソークの反復 (現在 n=1) | 負荷と clock_jumps・cb_max の関係は未確定 | #1570 |
