# AU-2 (#187) CI 代理指標の測定 (ubuntu runner)

親: `REPORT.md` §8。実機でしか測れない項目は [AU-22] (#2366) に分離済み。

## 1. 代理経路の検証 (PulseAudio null-sink) — 1 回目 run (n=1・接続未確認) — §5 で解消

| 項目 | 値 |
|---|---|
| 環境 | ubuntu runner (4 vCPU, 15 GiB), `google-chrome 155.0.8059.39` (REPORT の 154 とは版が違う), PulseAudio 16.1 (apt 導入) |
| PulseAudio | `module-null-sink sink_name=ci_null` を起動 (`pactl info` の Default Sink = `ci_null`) |
| 比較 | `asio_sine_b256_d2` を同一ハーネス・同一 HEAD (`1ddc8512`) で 2 回 (fake シンク / PulseAudio 起動中) |

| 条件 | sampleRate | baseLatency | outputLatency | clock (Hz) | burst | T | 判定 |
|---|---|---|---|---|---|---|---|
| fake シンク (既定) | 48000 | 0.011625 s | 0.036 s | 47969.0 | 1152 | 1792 | PASS |
| PulseAudio null-sink 起動中 | 48000 | 0.011625 s | 0.036 s | 47971.0 | 1152 | 1792 | PASS |

**結論**: Chrome の `baseLatency` / `outputLatency` / `burst` / `T` は PulseAudio 起動の有無で変わらず、`clock` も 2 Hz の差に留まった (各条件 n=1)。ただし Chrome の sink-input が `ci_null` に接続したかは **未確認** (`pactl list sink-inputs` は未取得)。そのため「null-sink は代理にならない」とは結論できず、「fake と同一の値に留まった。接続先は未検証」とだけ書く。よって P1〜P4 を null-sink の代理として扱う前提は、この時点では未検証のままだった (接続は §5 で確認済み)。Firefox は `tools/audio/harness` が Chrome CDP 専用のため、同じ方法では測れない。
**この結論は §5 で置き換えた**: §5 で sink-input の接続 (`ci_null`) を確認した。接続を確認した 2 回目 run の比較では、報告値・burst が fake と一致せず、null-sink の 96k では fake と異なる値になった (§5-1)。

## 2. ベースライン `e2e.sh --quick` (main `1ddc8512`, 測定 commit = `1ddc8512`)

- 実行: `bash tools/audio/e2e.sh --quick`, `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh`, `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`
- 結果: **43/44 PASS**, wall 266.9 s, load avg 開始 2.25 → 終了 0.42 (nproc 4)
- FAIL: `asio_ramp_b128_d2` — `underruns=1 silence=2688; ramp mismatches=162944/192384`。B=128 の ramp は本 run で再現。原因は未切り分け (負荷起因の疑い、未確認)。追跡先: #187 (§4)
- burst 分布 (quick, 48k): 512f 大半。96k は 1024f (`asio_sine_b256_96k`, `asio_sine_b512_96k`)。96k/B=256 の `burst_floor=4096` ネガコントロールは PASS (T=5376)

## 3. 未実施 (この run の時間内に収まらないため)

- フル `e2e.sh` (約 9 分 + ASIO COM 経路 約 3 分) と 30 分ソーク: 行列にすると 1 run の 58 分上限を超えるため未実施
- Firefox 行列: §9 で実施 (AU-23 #2540)
- Windows / macOS runner の仮想オーディオ workflow: 未着手 (権限・検証手段の確認が先)

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~Chrome が null-sink に接続したか未確認~~ → 解消 (§5-4: `results/au2_recheck/null_r1_sinkinputs.txt` に ci_null 接続を保存。報告値・burst は fake と異なる) | — | — |
| ~~Firefox 行列がハーネス未対応~~ → 解消 (§9: Firefox 157.0 で 48k/96k とも 3/3 PASS・sink-input の ci_null 接続 6/6) | — | — |
| Chrome 行列 (§5) の再測定。測定 commit `54bacdc0` の後に main に入った clock_jump の差分 26 行 (§8) が未適用 | §5 の数値は clock_jump 前のコードで測った値。burst・T・underrun への影響は未確認 | #187 |
| Firefox 48k の rep 1 の burst・T の差 (§9-4) | 行列の burst・T の範囲に影響。PASS (underrun・sine・sink 接続) には影響しない | #187 |
| sink の規格固定と PulseAudio の再サンプルの有無 (Chrome・Firefox 共通) | 96k の clock が sink 経路で変わるかは未確定 (§5・§9-4) | #187 |
| Firefox 他版・Safari・30 分ソーク・負荷下 | Firefox は 157.0・10 s・無負荷のみ。版差・長時間・負荷下は未確認 | #187 / [AU-22] (#2366) |
| `asio_ramp_b128_d2` の FAIL (quick, 負荷起因の疑い) | 回帰判定の不安定さ | #187 (要切り分け) |
| 30 分ソーク (AU-10 null-sink 版) | 長時間の underrun 0 が未確認 | #187 |
| 実機の outputLatency・総往復遅延・Safari | CI で測れない | [AU-22] (#2366) |

## 5. 行列の実測 (2 回目 run, 2026-10-14) — §1 の未確認事項を解消

測定 commit = `54bacdc0` (main)。測定に使った `tools/audio/{src,harness,test}`・`public/worklets` は同 commit から差分あり (§8 の 6 ファイル・26 行。clock_jump の取り込みによる)。Chrome 行列の再測定は §4 の未解決。
再現: `bash tools/audio/build.sh` → `bash tools/audio/au2_matrix.sh 3` → `node tools/audio/au2_summary.mjs` (この run は 2181abc0 時点の `au2_matrix.sh` で実行。接続採取と NC の追加は §5-4 の再採取から)。
環境: ubuntu runner (4 vCPU), `google-chrome 154.0.8037.97`, PulseAudio 16.1 (apt 導入, `module-null-sink sink_name=ci_null` を既定 sink)。
生結果 `results/au2/{fake,null}_r{1,2,3}.json` (各 3 シナリオ)、`results/au2/null_soak600.json` (ソーク)。

**null-sink の接続を確認** (§1 の未確認事項の解消): 再生中の `pactl list sink-inputs` に `application.name = "Google Chrome"` が `Sink: 1` で現れ、`ci_null` (index 1) は RUNNING。Chrome は null-sink を使っている。この確認は 2 回目 run 中に行ったもので結果ファイルは残っていない。保存した根拠は §5-4 (再採取の sink-input 採取)。
よって §1 の「fake と同一の値」は、接続を確認しないまま比べた結果だったと読む。接続を確認した今回の比較では、報告値も burst も fake と**一致しなかった** (下表)。

### 5-1. 行列 (P1〜P4, 各セル n=3。シナリオは `asio_sine_b256_d2` (48k) / `asio_sine_b256_96k` / `asio_sine_b512_96k`)

| 条件 | sr | シナリオ | n | PASS | underrun (合計) | burst max (f) | 実 T (f) | T_req (f) | T≥T_req | baseLatency (ms) | outputLatency (ms) | clock (Hz, 平均) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Chrome fake シンク | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 512 | 1536 | 1024 | OK | 10.0 | 30.0 | 48000.0 |
| Chrome fake シンク | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1024 | 2816 | 1536 | OK | 10.0 | 30.0 | 96000.4 |
| Chrome fake シンク | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 1024 | 3072 | 2048 | OK | 10.0 | 30.0 | 96000.1 |
| Chrome PulseAudio null-sink | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1152 | 1792 | 1792 | OK | 11.6 | 36.0 | 48008.5 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 3456〜4480 | 4608〜5888 | 5888 | OK | 11.6 | 71.0〜80.0 | 96002.2 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 4352〜4480 | 6144 | 6144 | OK | 11.6 | 68.0〜70.0 | 95987.8 |

※ **T≥T_req の判定は run ごと** (各 run の burst から T_req を計算し、全 run で T≥T_req なら OK)。issue #187 の P4 はセル最大 burst 基準 (表の T_req 列 = 各 run の T_req の最大) で判定する。この基準では null 96k・B=256 の r1・r2 (T=4608) が T_req 5888 に満たず、P4 は未達 (§5-3 所見 1 と同じ結論)。行の OK は run ごとの判定である。

- 表の値: burst = `stats.burst_obs` (連続 process の総フレーム数の**最大**)、T_req = `ceil((burst×1.25 + B)/B)×B` (各 run の burst で計算)。セル内の範囲は n=3 の min〜max。表は `node tools/audio/au2_summary.mjs` の出力と一致する。
- 元の 18 シナリオ実行 (n=3) はすべて PASS (underrun 0・ramp/sine 誤差 1.49e-8)。load avg は各 run 開始 0.0〜0.6。**ただし同 HEAD の再採取 (n=1, §5-4) では fake_r1 の `asio_sine_b256_d2` が underrun 1 で FAIL した**。元の n=3 と合わせても再現性は確定していない。
- P2 の p99 は §10 で計測した (AU-30 #3151)。この節の表は p99 列の無い旧測定。

### 5-2. 30 分ソーク (P1) — 10 分のみ実施

| 条件 | シナリオ | 結果 |
|---|---|---|
| Chrome null-sink 48k B=256 ramp | `asio_ramp_b256_soak600` (`--soak 600`) | **PASS**: underrun 0・silence 0・ramp mismatch 0/28,803,328 f・wall 600.01 s。T=1792 (fixed), burst 1152 |

30 分 (1800 s) のソークは時間内に収まらなかったため未実施 (§6 未解決)。

### 5-3. T 下限と安全係数 (P4) の再評価

- **所見 1 (係数不足)**: null-sink の 96k では起動時の較正 T0 が実行中の burst を下回った。B=256 の 96k run では T0=4608 に対し、run 中の burst (`burst_obs`) は 3456〜4480 (r1・r2 は 3456、r3 のみ 4480 = 3456 の 1.30 倍)。r3 の揺れ (4480) に対し、現行の安全係数 1.25 は覆えない (r1・r2 は T=4608 のまま終わり T_req 5888 に満たない。r3 は grows 2 回で 5888 へ拡張)。
  - **推定 (T0 からの逆算)**: T0=4608 の open 時の較正 burst は **推定 3328 または 3456** (128 の倍数)。`flaudio.c` の `depth = (b + b/4 + 2B−1)/B` を T0/B=18 について解いた (`g_burst_floor` は既定 0)。実体は `fla_open` の phase 1 が得る `res[0]` を 128 に切り上げた値で、JSON には残っていない。この値は run 中の `burst_obs` とは別の量である。
  - B=512 96k は T0=5120 から実行中に `grows` 1〜2 回で 6144 へ拡張。B=256 96k は 1 run (r3) で `grows` 2 回で 5888 へ拡張。
  - **underrun は全 run で 0**。ただし拡張は実行中に行われるため、初回の揺れで underrun の余裕が少ない (実機で揺れがさらに大きい場合は未検証)。
- **所見 2 (fake の代理性)**: fake の burst 512 (48k)・1024 (96k) は、null-sink の 1152・3456〜4480 を代表しない。fake の値で T を決めると、96k で T が不足する。
  - fake 96k・B=256 の T0=2816 からは、同じ逆算で open 時の較正 burst を **推定 1920 または 2048** と読める。これは run 中の最大 `burst_obs` (1024) とは別の量で、表の `burst max` と同一視しない。
- **係数の候補 (計算値, 未適用)**: 96k・B=256・burst 4480 → 係数 1.25 で T=5888 / 1.30 で 6144 / 1.50 で 7168。B=512 → 1.25 で 6144 / 1.50 で 7680。48k・B=256・burst 1152 → 1.25 で 1792 / 1.50 で 2048。
  係数の値は遅延とのトレードオフのため、PM 判断。係数は `tools/audio/src/flasio.c:225` の `need = (burst + burst/4 + 2B−1)/B·B` (実行中の拡張式。`grows` はこの式で増える) にある。AU-24 (#2541) で実測し、係数は 125 のまま維持した (§5-5)。

### 5-4. 接続の根拠・NC・再採取 (同コード, n=1)

- 再採取: `AU2_OUT=tools/audio/results/au2_recheck bash tools/audio/au2_matrix.sh 1` (測定コードは 2181abc0 = 54bacdc0 と同一。§8)。`au2_matrix.sh` は本 PR で、null の各 run の sink-input を `null_r<rep>_sinkinputs.txt` へ 1 秒ごとに採る処理と、末尾の NC を組み込んだ。
- **接続の根拠 (保存済み)**: `results/au2_recheck/null_r1_sinkinputs.txt` (90 サンプル)。`ci_null` (sink index 1) は RUNNING で、`application.name = "Google Chrome"` の sink-input が `Sink: 1` に 41 サンプル現れる。§5 の 2 回目 run の接続確認は結果ファイルに残していなかったため、接続の根拠はこの再採取分を正とする。
- **NC (検出能力)**: `results/au2_recheck/nc_soak15_negctl.json` (`asio_ramp_b256_soak15_negctl`、`--soak 15 --inject-hiccup` = 60 ms の強制ブロック混入)。**FAIL (exit 1) は期待どおり**: underrun 7・silence 3712・ramp mismatch 669952/720896。行列の underrun 列は、この注入で FAIL する検出能力を前提に読む。

再採取の集計 (`node tools/audio/au2_summary.mjs tools/audio/results/au2_recheck`、n=1 のため範囲は単一値):

| 条件 | sr | シナリオ | n | PASS | underrun (合計) | burst max (f) | 実 T (f) | T_req (f) | T≥T_req | baseLatency (ms) | outputLatency (ms) | clock (Hz, 平均) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Chrome fake シンク | 48000 | asio_sine_b256_d2 | 1 | 0/1 | 1 | 512 | 1536 | 1024 | OK | 10.0 | 30.0 | 48000.0 |
| Chrome fake シンク | 96000 | asio_sine_b256_96k | 1 | 1/1 | 0 | 1024 | 2816 | 1536 | OK | 10.0 | 30.0 | 95999.8 |
| Chrome fake シンク | 96000 | asio_sine_b512_96k | 1 | 1/1 | 0 | 1024 | 3072 | 2048 | OK | 10.0 | 30.0 | 95999.9 |
| Chrome PulseAudio null-sink | 48000 | asio_sine_b256_d2 | 1 | 1/1 | 0 | 1152 | 2560 | 1792 | OK | 11.6 | 37.0 | 48007.1 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b256_96k | 1 | 1/1 | 0 | 4480 | 5888 | 5888 | OK | 11.6 | 83.0 | 95995.2 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b512_96k | 1 | 1/1 | 0 | 4480 | 6144 | 6144 | OK | 11.6 | 68.0 | 95974.9 |

- **FAIL 1 件 (未解決)**: fake_r1 の `asio_sine_b256_d2` (再採取の 1 件目) で underrun 1・silence 384・sine maxErr 9.98e-1・zeroRuns 1 (欠落と位相ずれ)。最終 T は 1536 (実行中に grows 1 回で拡張)。同条件の元の 3 回 (§5-1) はすべて PASS で、再現性は未確定。原因は未切り分け (§2 の `asio_ramp_b128_d2` FAIL と同種の疑い、未確認)。
- 再採取の 6 件のうち 5 件 PASS。null 側はこの再採取でも underrun 0・PASS。

### 5-5. 安全係数の実測 (AU-24 #2541・係数は 125 のまま維持)

- 測定 commit = `90d144e9` (`FLA_BURST_PCT` 導入 `a2ca18f4` 以後で、コードを変えた最後の commit。m2 の型幅の揃え)。測定の実行は HEAD `748c686e` (= `90d144e9` + REPORT のみ) 上で行った。`git diff 90d144e9 748c686e -- tools/audio/src` の出力は空 (コード差分 0 行)。よって下の表は現 HEAD のコードの値。
  - 旧 sweep (`a2ca18f4`) は 125 の 3 run とも T0 4608・grows 0。今回の再測定では 125 の r1 だけ T0 3328 が出た。OPEN 較正 T0 は run ごとに変わる (旧 sweep の値は Git 履歴)。
- 対象: null-sink (PulseAudio `ci_null`) の `asio_sine_b256_96k` (B=256・96k・sine・10 s) を各係数で n=3。係数は `FLA_DEFS="-DFLA_BURST_PCT=<値>" bash tools/audio/build.sh` で変え、`node tools/audio/harness/run.mjs --only asio_sine_b256_96k --out <json>` を PulseAudio 起動中に実行 (JSON・sink-input は `tools/audio/results/au24_sweep/`)。9 run すべての sink-input で `Google Chrome` が `Sink: 1` (`ci_null`) に現れた (`pct<係数>_r<rep>_sinkinputs.txt`)。
- 環境: ubuntu runner (4 vCPU)・google-chrome 154.0.8037.97・PulseAudio 16.1 (apt 導入)。

| FLA_BURST_PCT | OPEN 較正 T0 (run 1/2/3) | 最終 T | grows (run 1/2/3) | underrun (run 1/2/3) | burst_obs | 判定 |
|---|---|---|---|---|---|---|
| 125 (変更前と同値) | 3328 / 4608 / 4608 | 4608 ×3 | 3 / 0 / 0 | 0 / 0 / 0 | 3456 ×3 | PASS |
| 130 | 4608 ×3 | 4864 ×3 | 1 / 1 / 1 | 0 / 0 / 0 | 3456 ×3 | PASS・grows あり・T +256 |
| 150 | 5376 ×3 | 5632 ×3 | 1 / 1 / 1 | 0 / 0 / 0 | 3456 ×3 | PASS・grows あり・T +1024 |

- **結論**: 係数 125 は T が最小 (4608) で、9 run とも underrun 0・PASS。grows は 125 では 3 run 中 1 run (T0 3328 から 3 回拡張) だけに出た。130 / 150 は毎 run grows 1 回 (T0 が要求値を下回る) で、T を 256 / 1024 フレーム増やしても grows は消えない。係数は 125 のまま維持する (PM 判断の材料)。
- **grows の原因**: 要求値は `need = (burst×PCT/100 + 2B−1)/B·B` (B=256・run 中 burst 3456): 125 → 4608 / 130 → 4864 / 150 → 5632。OPEN 較正の T0 がこれを下回ると run 中に拡張される。125 は T0 4608 (= 要求) の run で grows 0、T0 3328 の run で 3 回拡張。130 は T0 4608 < 4864、150 は T0 5376 < 5632 のため毎 run 1 回拡張。T0 は `flaudio.c` の OPEN 較正で決まり run ごとに変わる。`res[0]` は記録していないため、較正 burst の値は T0 からの逆算による推定。係数を変えると 256 フレームの境界が移るだけで、T0 のばらつきは係数の変更では吸収できない。§5-3 の旧測定 (run 中 burst 4480) は本測定では再現せず、その場合の要求値 (130: 6144 / 150: 7168) は初期 T0 を上回るため grows は残る。→ 子 issue **[AU-28]** #3051。
- **underrun**: 9 run (125・130・150 × n=3) すべて 0。
- **e2e 回帰 (`bash tools/audio/e2e.sh --quick`・HEAD `90d144e9`)**: `e2e.sh` の 5 工程 (inventory → tsc → build → harness → ASIO COM) を順に実行し、全工程 exit 0。harness **44/44 PASS** (wall 251.6 s・load avg (1 分) 0.51 → 0.43)。ASIO COM 段は node check 126/126・COM 3/3 PASS。e2e 全体の wall は 5 分 51 秒。
- **同じ e2e の 1 回目 (HEAD `a8aaa39a`・m2 の前)**: harness 43/44 で exit 1。FAIL は `asio_ramp_b128_d2` (underrun 1・silence 384・ramp 不一致 164480/192896)。同シナリオは §2・REPORT_AU5・REPORT_DS で同じ症状の FAIL が記録された既知の断続 FAIL (追跡 #187)。同 HEAD で単独再実行 `node tools/audio/harness/run.mjs --only asio_ramp_b128_d2` は 1/1 PASS (underrun 0・不一致 0/961024・73.5 s・load 0.37 → 0.11)。1 回目は harness 段で止まったため ASIO 段を `a8aaa39a` で別途実行 (node check 126/126・COM 3/3 PASS・76.7 s)。その後 `90d144e9` で全工程を再実行し、上記の PASS を得た。
- **FAIL の扱い**: 本 PR の差分 (既定 125) は旧コードと数値的に同一。1 回目の FAIL の原因は未切り分け (#187)。PR の変更に起因するとは判断していない (根拠: 単独再実行 PASS・既知の同症状)。
- **範囲外 (未実施)**: 本節は null 96k のみ。`au2_matrix.sh 3` 全体 (fake 側・48k 行列) は時間内に収まらず未実施 (→ [AU-28] #3051)。DirectSound 側 `flds.c:258` の 1.25 は未変更 (→ [AU-28])。

## 6. 未解決 (実測ではなく実装が必要なものは子 issue)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~Firefox 行列 (PulseAudio null-sink × 48k/96k)~~ | ~~`tools/audio/harness` が Chrome CDP 専用~~ → 解消 (§9・AU-23 #2540) | — |
| OPEN 較正 burst と run 中 burst のずれで grows が残る (係数は 125 維持・§5-5) | 96k null で grows 0〜3 回・underrun 0 (§5-5 の再測定)。係数の変更では解消しない | **[AU-28]** #3051 |
| 30 分ソーク (null-sink, 48k B=256) | 10 分 PASS のみ。30 分の underrun 0 は未確認 | #187 (測定のみのため子にせず残す) |
| ~~P2 burst の p99~~ | ~~worklet が最大値しか公開しない~~ → 解消 (§10・AU-30 #3151: `burst_hist` を公開し結果 JSON に `burst_p99`)。Firefox 側は未配線 | #187 (Firefox の p99) |
| Windows / macOS runner (任意) | 未着手 (受入 4) | #187 |
| `asio_ramp_b128_d2` quick FAIL (§2) | 本 run では再実行していない。原因未切り分け | #187 |
| fake の `asio_sine_b256_d2` の underrun 1 (再採取 n=1 で FAIL, §5-4) | 行列の再現性が未確定。原因未切り分け (`asio_ramp_b128_d2` と同種の疑い) | #187 (測定の追跡) |

## 7. 検証範囲 / 範囲外

- 範囲: ubuntu runner の Chrome 154 (fake / PulseAudio null-sink) の 48k・96k。null-sink は PulseAudio の出力経路で、実デバイス (実 IF の outputLatency) を代表しない (AU-22 #2366)。
- 範囲外: Safari・Windows/macOS・実機の総往復遅延。Firefox は §9 (157.0・headless・Linux のみ)。

## 8. コード差分 (Chrome 行列の測定 commit `54bacdc0` → 最終 head)

§5 の Chrome 行列が使うコード (`tools/audio/{src,test,build.sh,harness/run.mjs,harness/chrome.mjs}`・`public/worklets`・`src/runtime`) の差分:

- 実行: `git diff --stat 54bacdc0 HEAD -- tools/audio/src tools/audio/test tools/audio/build.sh tools/audio/harness/run.mjs tools/audio/harness/chrome.mjs public/worklets src/runtime`
- 出力:

```
 public/worklets/fl-audio-worklet.js | 12 +++++++++++-
 src/runtime/audio-layout.ts         |  1 +
 src/runtime/audio-shim.ts           |  2 +-
 tools/audio/harness/run.mjs         |  2 +-
 tools/audio/src/flaudio.c           |  3 ++-
 tools/audio/src/flaudio.h           |  6 +++++-
 6 files changed, 21 insertions(+), 5 deletions(-)
```

- 差分の由来: `429f36bd` (clock_jump の正/負成分の別計上, #1570) が `54bacdc0` の後に main に入った。本 PR (#2540) の変更ではない。よって §5 の Chrome 行列は、この 26 行を含まないコードで測った値である。取り込み後 HEAD での Chrome 行列の再測定は §4 の未解決。
- 本 PR で追加した `harness/bidi.mjs`・`harness/au2.mjs` は Firefox 専用 (Chrome の `run.mjs` は使わない) なので、上の範囲には含めていない。Firefox 行列の測定 commit と差分は §9 冒頭。

## 9. Firefox 行列 (AU-23 #2540・WebDriver BiDi)

- **測定 commit**: `63ea7d45` (main `322f81b6` を取り込んだ merge)。`tools/audio/au2_firefox_matrix.sh`・`tools/audio/au2_firefox_summary.mjs` の追加と `harness/au2.mjs` の説明の修正はこの commit に含む。以後の HEAD でコードは変えていない。
  コード差分: `git diff --stat 63ea7d45 HEAD -- tools/audio/src tools/audio/harness tools/audio/test tools/audio/build.sh tools/audio/au2_firefox_matrix.sh tools/audio/au2_firefox_summary.mjs public/worklets src/runtime` の出力は空 (0 行)。
- **環境**: ubuntu runner (4 vCPU)・Firefox 157.0 (headless)・PulseAudio 16.1 (apt 導入)・既定 sink = `module-null-sink sink_name=ci_null`。emsdk は素材 `toolchain-emsdk` を `$RUNNER_TEMP` に展開して使った (`EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh`。`[EMSDK]` 参照)。
- **駆動**: `harness/bidi.mjs` (`withFirefox`: `chrome.mjs` の `serve` を共用し、`{navigate, eval}` は `withChrome` と同形。評価は `script.evaluate` + `awaitPromise`)、`harness/au2.mjs` (1 rep で 48k・96k を 1 セッション実行。再生中に `pactl list short sink-inputs` を 300 ms 間隔で採取)。
- **再現**: `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh bash tools/audio/build.sh` → `bash tools/audio/au2_firefox_matrix.sh 3` (→ `results/au2/firefox_r{1,2,3}.json`、集計 `node tools/audio/au2_firefox_summary.mjs`)。条件は B=256・depth=2・sine・10 s。48k は `asio_sine_b256_d2`、96k は `asio_sine_b256_96k` と同名 (`harness/run.mjs`)。NC は §9-3。
- **PASS の判定**: `run.mjs` の `underrunFree` と `sineOk` に加え、`ctx.sampleRate` が要求値に一致し、abort と worklet エラーが無く、sink-input が既定 sink (`ci_null`) に接続したこと (`pulse_sink_input.on_ci_null`)。`au2_firefox_matrix.sh` の終了コード 0 はこの全条件が全 rep で成立したことを表す。

### 9-1 行列 (n=3, 測定 commit `63ea7d45`)

| browser | sampleRate | シナリオ | n | PASS | underruns | burst (f) | T (f) | clock (Hz) | baseLatency (s) | outputLatency (s) | sink-input が ci_null に接続 | sink-input の規格 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| firefox | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1024–1152 | 1536–1792 | 48005–48021 | 0 | 0.0283125–0.049083333 | 3/3 | float32le 2ch 48000Hz |
| firefox | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1920 | 2816 | 96003–96016 | 0 | 0.046041666–0.04909375 | 3/3 | float32le 2ch 96000Hz |

- 表は `node tools/audio/au2_firefox_summary.mjs` の出力そのもの (`results/au2/firefox_r{1,2,3}.json`)。baseLatency は Firefox が 0 を報告した値で、意味は未確認。outputLatency は報告値をそのまま載せた。
- wall: rep 1 = 41.7 s (Firefox 起動直後の cold 実行)、rep 2・3 = 26.4 s。行列全体 94.9 s。各 rep 開始時の load avg (1 分値) = 0.99 / 0.96 / 0.63。sine の最大誤差は 6 run すべて 1.49e-8、`zero_runs_ge16=0`。`ctx.sampleRate` は 6 run すべて要求値と一致。
- 旧測定 (`98ef9d3b`・測定 commit `db9eb829`) の数値はこの節で置き換えた (Git 履歴に残る)。

### 9-2 Firefox の制約 (受入 4・probe を各 rep 1 回、計 3 回)

| 項目 | 実測 (Firefox 157.0) | 判定 |
|---|---|---|
| SharedArrayBuffer / crossOriginIsolated | `function` / `true` (3/3) | 成り立つ |
| main thread の `Atomics.wait(…, 0)` | TypeError (3/3) | 成り立つ (main では wait 不可) |
| AudioWorklet 内 `Atomics.wait(…, timeout 20 ms)` | `timed-out`、経過 20 ms (3/3) | **成り立たない**: Firefox は worklet での wait を止めず、実際にブロックする |
| AudioWorklet 内 `Atomics.notify` | `function` (3/3) | 成り立つ |

- `public/worklets/fl-audio-worklet.js` は `Atomics.wait` を呼ばず、`Atomics.notify` のほか `Atomics.load/store/add/compareExchange` を使う。そのため shim の動作は、worklet 内 wait が Firefox で成り立つかに依らない。
- 行列の 6 run がすべて underrun 0 で通ったことも、worklet が Firefox で正常に動いている証跡になる。Chrome・Safari の worklet は Firefox 側の測定の範囲外。

### 9-3 ネガティブコントロール (各 n=1)

| NC | 操作 | 期待 | 実測 |
|---|---|---|---|
| 強制 underrun | `node tools/audio/harness/au2.mjs --rep 1 --extra "hiccup_ms=60&hiccup_every=200" --out tools/audio/results/au2/neg/hiccup_r1.json` | 両条件 FAIL・終了コード非 0 | 0/2 PASS・rc=1。48k は underruns=8・silence=7168f、96k は underruns=16・silence=30336f (`results/au2/neg/hiccup_r1.json` の `rc`・`failed`) |
| sink 接続 | `pactl load-module module-null-sink sink_name=ci_other` → `pactl set-default-sink ci_other` → `node tools/audio/harness/au2.mjs --rep 1 --secs 4 --out tools/audio/results/au2/neg/sink_other_r1.json` → `pactl set-default-sink ci_null` | sink-input の `ci_null` 接続が false・両条件 FAIL・終了コード非 0 | 0/2 PASS・rc=1。音声判定 (underrun 0・sine 一致) は両条件で満たすが `on_ci_null=false` のため FAIL。JSON の `pulse.default_sink` は `ci_other` (`results/au2/neg/sink_other_r1.json`) |

### 9-4 検証範囲 / 範囲外 / sink の規格

- **範囲**: Firefox 157.0 headless (Linux)・PulseAudio null-sink (既定 sink)・48k/96k・sine・B=256・depth=2・10 s・n=3。NC は各 n=1。
- **範囲外**: Safari・Firefox 他版・30 分ソーク・負荷下・実機 outputLatency ([AU-22])。
- **sink の規格**: 測定中に固定していない。各 rep 開始時の ci_null 規格は `results/au2/firefox_r*.json` の `pulse.ci_null_before` に記録 (rep 1 = `s16le 2ch 44100Hz`、rep 2・3 = `s16le 2ch 48000Hz`)。sink-input の規格は全 run で要求どおり (48000 / 96000 Hz、float32)。PulseAudio が sink 側へ再サンプルしたかは未確認 (`clock` は AudioContext 側の値)。
- **rep 1 の差**: 48k の burst・T は rep 1 = 1152・1792、rep 2・3 = 1024・1536。96k は 3 rep とも 1920・2816。rep 1 の clock は 48020.6 Hz で rep 2 と同じ (旧測定の rep 1 の 46590 Hz は今回は出なかった)。rep 1 だけ開始時の sink 規格が 44100 Hz だった点は旧測定と同じ。rep 1 の 48k の burst の差の原因は未切り分け (§4)。

## 10. P2 の p99 (AU-30 #3151)

- **測定 commit**: `e403fd7a` (コードを変えた最後の commit。worklet・ctl・ハーネス・集計)。`git diff --stat e403fd7a HEAD -- tools/audio/src tools/audio/test tools/audio/harness tools/audio/build.sh tools/audio/au2_summary.mjs public/worklets src/runtime` の出力は 0 行 (測定後に増えたのはこの REPORT と結果 JSON だけ)。
- **方式**: worklet は連続 `process()` の run (Date.now 差 ≤1 ms) が終わるたびに `burst_hist[floor(len/512)]` (ctl @384、`FLA_CTL_SIZE` 384→512) を +1 する。末尾 bin は ≥15872 f。`run.mjs` は p99 を該当 bin の上端で出す (512 f 刻み。真の p99 はこの値以下) → 結果 JSON の `stats.burst_p99`・`stats.burst_runs`。run には待機中の 128 f 単独 run も入る (fake 48k の bin 0 は 1499 run 中 364。発生源は未切り分け)。
- **再現**: `bash tools/audio/build.sh` → `AU2_OUT=tools/audio/results/au30_p99 bash tools/audio/au2_matrix.sh 3` → `node tools/audio/au2_summary.mjs tools/audio/results/au30_p99`。環境: ubuntu runner (4 vCPU), google-chrome 154.0.8037.97, PulseAudio 16.1 (apt 導入)。生結果: `results/au30_p99/`。

### 10-1 行列 (n=3, 測定 commit `e403fd7a`)

| 条件 | sr | シナリオ | n | PASS | underrun (合計) | burst max (f) | burst p99 (f, bin 上端) | 実 T (f) | T_req (f) | T≥T_req | baseLatency (ms) | outputLatency (ms) | clock (Hz, 平均) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Chrome fake シンク | 48000 | asio_sine_b256_d2 | 3 | 2/3 | 1 | 512 | 1024 | 1024〜1536 | 1024 | OK | 10.0 | 30.0 | 48000.0 |
| Chrome fake シンク | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1024 | 1536 | 2816 | 1536 | OK | 10.0 | 30.0 | 95999.7 |
| Chrome fake シンク | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 1024 | 1536 | 3072 | 2048 | OK | 10.0 | 30.0 | 96000.0 |
| Chrome PulseAudio null-sink | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1152 | 1536 | 1792 | 1792 | OK | 11.6 | 31.0〜36.0 | 48017.9 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 3456 | 3584 | 4608 | 4608 | OK | 11.6 | 81.0〜83.0 | 96008.8 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 4480〜5504 | 3584 | 6144〜7680 | 7680 | OK | 11.6 | 68.0〜71.0 | 95989.8 |

- **受入 3 (null 48k の PASS 判定)**: `asio_sine_b256_d2` の null-sink は 3/3 PASS (underrun 0・silence 0・sine maxErr 1.49e-8)。
- **p99 と最大値**: 最大値は 1 run の外れ値になりうる。例: null 96k・B=512 は 393〜394 run。最大 5504 f は r1・r2 で各 1 run、4480 f は r3 で 1 run。p99 はいずれも 3584 (bin 3072〜3584)。
- **FAIL 1 件 (未解決)**: fake_r1 の `asio_sine_b256_d2` で underrun 1・silence 128・sine maxErr 6.85e-1 (fake 48k は 2/3 PASS)。症状は §5-4 の fake_r1 (underrun 1) と同じ。今回は 1 回のみで、原因は未切り分け (#187)。null 48k では出ていない。
- **NC**: `nc_soak15_negctl` は FAIL (exit 1・underrun 7・silence 3712・ramp mismatch 669952/720896)。§5-4 の NC と同値で、期待どおり。
- **未実施**: Firefox の p99 (`harness/au2.mjs` は `burst_obs` のみ)・30 分ソークの p99 (#187)。
