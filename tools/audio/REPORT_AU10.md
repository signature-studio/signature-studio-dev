# AU-10 (#191) 30 分ソーク (`--soak30`) 全文 — tools/audio/

> 本体 `REPORT.md` §15 から分割移動した全文 (内容は無変更。節番号は本体と一致させるため §15 を維持)。親: [`REPORT.md`](REPORT.md)。

## 15. AU-10 (#191) 30 分ソーク (`--soak30`)

既知類型との関係: 該当なし (ランタイム shim の長時間検証)。検証起点 commit: `0a721b0` (ブランチ `191-audio-soak30`, base `149f073`)。環境: GitHub runner 4 core / 15 GiB, headless Chrome 154.0.8037.97 (fake 出力シンク), emcc は toolchain-emsdk。

**実測の版の注意**: 下表の 30 分・負荷下・ネガコンは 0a721b0 (AU-7 取り込み前) の実測。現 head `57519ca` は main (`790e003`) を取り込んでおり、`FLASIO_PROFILE_ILWASAPI` 既定 0→1 (報告 min/gran 128/128 → 256/0)・`audio-shim.ts` の ATTACH 待ち (outputLatency 0 の間 最大 600 ms)・`flasio.c` の systemTime を含む。head `57519ca` での 30 分は未計測 (下の表の head 行を参照)。head `57519ca` の 10 秒ソークは下表の 2 行のとおり 4 回中 1 回 FAIL。

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
| head `57519ca` での 30 分ソーク (無負荷) は**未実施** (未計測)。上の表の 30 分行は `0a721b0` (AU-7 取り込み前) のもので、マージ後の shim (`audio-shim.ts` ATTACH 待ち・`FLASIO_PROFILE_ILWASAPI` 既定 1) では未計測。fix run の 40 分上限に 30 分 + build が収まらないため見送り | #191 にコメント (別 run で `bash tools/audio/build.sh && node tools/audio/harness/run.mjs --soak30` を head で実施) |
| head `57519ca` の `--soak 10` が 4 回中 1 回 FAIL (underrun 1・ramp mismatch 411,392 f、T=1280 で lat_changes 1)。原因未特定。同 head の 2 回目・3 回目は PASS | 断続的な欠陥か計測ノイズかを切り分けていない。30 分実測の信頼性にも関わる | #191 にコメント (head で `--soak 10` を 5 回以上反復し、FAIL 時の `T`・dev_fill・underrun のログを採る) |
| 旧 page.mjs (巻き戻し非対応) での FAIL 再現未実施 | 修正の必要性は理屈のみ | 本 REPORT に明記 |
