# tools/audio/asio — #3757 com_ramp_b256_d2 の producer 停止の直接経路 (計装と測定の記録)

> 親: #2777 → 子 [AU-40] #3757。前提の経緯は [REPORT_APPENDIX_2777.md](REPORT_APPENDIX_2777.md) §6・§7、[REPORT_APPENDIX_2934.md](REPORT_APPENDIX_2934.md)。
> 測定はすべて headless Chrome・Linux runner (4 コア)・単独実行 (負荷下は `yes` を 4 本)。実オーディオデバイスでは測っていない。

## 1. 結論

- **直接経路は未特定。** 本 PR で producer の write 時系列を結果 JSON に出す計装を入れた。計装後の 19 回では underrun は 0 回で、停止 (write 間隔 24 ms 以上) は観測されなかった。失敗の時系列は取れていない。
- 判定基準 (underrun 0・silence 0・ramp bit-exact) は変えていない。`asio/e2e.sh` と `flasio.c` は変えていない。
- 本 PR の変更は計装 (`harness/com_page.mjs` の結果 JSON への `pw` 追加) だけ。

## 2. 計装

- `result.pw = { pw_n, first_index, trace, burst_hist }`。`trace` は直近 1024 件の `[w, fill, 起床 µs, 完了 µs]` (`fla_ctl_t.pw_trace` の添字 `pw_n % 1024`)。`burst_hist` は worklet 側の 32 bin。
- 読み方: `完了 µs` の差分が producer の write 間隔。`fill` が 0 へ単調に落ちる区間が枯渇の経路になる。
- 解析: `work/meas/analyze.py` (gitignore 対象の `work/` に置く)。

## 3. 実測 (HEAD `68c6cbb75` + 本 PR の計装)

| 区分 | 回数 | 結果 | min_fill | T | write 間隔の最大 (ms) |
|---|---|---|---|---|---|
| build 直後 (cold) | 9 | PASS 9/9 (underrun 0) | 640〜896 | 1536 | 11〜20 |
| 連続 (warm) | 6 | PASS 6/6 | 896 | 1536 | 12〜17 |
| 負荷下 (yes×4) | 4 | PASS 4/4 | 896 | 1536 | 15〜18 |

- cold の 9 回は build.sh の直後の 1 回目 (計装後のビルドごと)。
- 計装前の 1 回 (HEAD `68c6cbb75` の build 直後、2026-10-15 05:57) では FAIL (underrun 1・silence 384・T 1792・ramp 109952/144256)。この run の trace は計装前のため無い。
- 内訳: 計装前 1 回 + 計装後 19 回 (上表 9 + 6 + 4) = 計 20 回。FAIL は計装前の 1 回のみ。FAIL の時系列は未取得。
- §5 の HEAD 再測定 3 回 (同一コードで build 直後・3/3 PASS) を加えると、本 appendix の総計は 23 回 (cold 10 + warm 6 + 負荷下 4 + 再測定 3)。FAIL は計 23 回中 1 回。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| producer 停止の直接経路 (FAIL 時の write 時系列の取得) | 原因未特定。計装後の cold 9 回では再現せず | [AU-40] #3757 (本 issue) |
| cold 起動の FAIL 頻度 (計装後 9 回で 0 件・計装前含め 1/10) | 母数不足。頻度は確定できない | #3757 |
| `probed_burst` の JSON 記録 (現状はログのみ) | depth 4/6 の振り分けを直接確かめられない | #3757 |

## 5. 検証 (規則 6)

- 測定 commit: `1622a5648` (計装を入れた最後の commit)。同一 HEAD で build.sh 直後に `com_ramp_b256_d2` を 3 回: 3/3 PASS (underrun 0・silence 0・min_fill 896・T 1536・write 間隔の最大 14.4 ms)。load 0.28 (開始) → 0.90 (終了)。
- `git diff 68c6cbb75 1622a5648 -- tools/audio/asio/harness` の差分は `com_page.mjs` の計装 11 行のみ (判定ロジックは未変更)。
- 全 e2e (`bash tools/audio/asio/e2e.sh`) は本 run では未実行 (時間上限のため)。`com_ramp_b256_d2` の単独測定のみ。

## 6. 2 回目の run: probed_burst の記録と FAIL 時の時系列

計装: `harness/com_page.mjs` が shim の `OPEN` 行 (`probed_burst`) を結果 JSON の `shim_open` に入れる。判定には使わない。

### 6-1. 負荷なし (同一 HEAD・単独)

- 単独 1 回 (r1): **FAIL** (underrun 1・silence 1792・T 1792・min_fill 256)。trace で、index 128 の 1 件だけ `done − wake` が **63.5 ms** (callback 側 = `fill` と `do_buffer` の区間)。その直前の待ち (前回 done → wake) は 10 ms で正常。fill は 1024 → 256 へ落ちた。
  - 読み: この FAIL の遅れは **callback 側**。負荷下の FAIL (6-2) とは経路が違う。
- 連続 10 回 (s1〜s10): 10/10 PASS (underrun 0)。min_fill 512〜896。`probed_burst` は 896〜1024。write 間隔の最大 12.0〜29.9 ms。

### 6-2. 負荷下 (`yes` × 4・同一 HEAD・10 回)

| run | 結果 | underrun | min_fill | T | probed_burst | write 間隔の最大 (ms) | 遅い区間 |
|---|---|---|---|---|---|---|---|
| l3 | FAIL | 1 | 0 | 5376 | 896 | 87.8 | wait |
| l5 | FAIL | 1 | 0 | 3072 | 1024 | 48.9 | wait |
| l6 | FAIL | 1 | 0 | 2304 | 896 | 85.9 | wait |
| l9 | FAIL | 1 | 0 | 1792 | 896 | 56.1 | wait |
| 他 6 回 | PASS | 0 | 256〜896 | 1536〜3328 | 896〜2432 | 18.3〜66.7 | — |

- 4/10 で FAIL。4 回とも遅れは **待ち区間** (前回 done → 今回 wake。`fla_out_wait_fill_le` を含む) にある。callback 内 (done − wake) の最大は 0.1〜20.9 ms で、待ちの遅れを説明しない。
- FAIL 時の fill は直前の 1152〜1664 から 0 へ落ちる。`wait_timeouts` は 1〜2、`wake_hist` の遅い区間 (16 ms 以上) に件数あり。
- 読み: 負荷下の停止は **起床の遅れ** (wasm スレッドが CPU を得られなかった可能性)。JS 側の bufferSwitch 呼出し時刻は未計装のため、JS と wasm のどちらが先かは分けられていない。

### 6-3. 2 つの経路 (現時点の切り分け)

| 経路 | 観測 | 遅れの場所 |
|---|---|---|
| A: callback 側 | 負荷なし r1 (1/11) | done − wake 63.5 ms (fill・do_buffer 区間) |
| B: 起床側 | 負荷下 (4/10) | wake − 前回 done 49〜88 ms (wait 区間) |

- `probed_burst` は FAIL と PASS で 896〜1024 に重なり、depth の振り分けが FAIL を分けていない。
- 本節の計 21 回: 負荷なし 11 回 (r1 + s1〜s10。FAIL 1 回) + 負荷下 10 回 (l1〜l10。FAIL 4 回)。

### 6-4. 未解決 (本 PR 時点)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 経路 A の主因 (callback 内 63.5 ms の中身: host の bufferSwitchTimeInfo か fla_out_write か) | 原因未特定。host 側の区間を未計装 | #3757 |
| 経路 B の主因 (wasm 側の OS 先取り or JS 側の呼出し遅れ) | 原因未特定。JS 側の bufferSwitch 呼出し時刻を未計装 | #3757 |
| 負荷なしの FAIL 頻度 (本節 11 回中 1 回) | 母数不足 | #3757 |
