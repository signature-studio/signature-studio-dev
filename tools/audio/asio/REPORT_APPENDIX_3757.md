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
- 同一 HEAD の計 20 回 (計装前 1 回 + 計装後 19 回) のうち FAIL は 1 回。FAIL の時系列は未取得。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| producer 停止の直接経路 (FAIL 時の write 時系列の取得) | 原因未特定。計装後の cold 9 回では再現せず | [AU-40] #3757 (本 issue) |
| cold 起動の FAIL 頻度 (計装後 9 回で 0 件・計装前含め 1/10) | 母数不足。頻度は確定できない | #3757 |
| `probed_burst` の JSON 記録 (現状はログのみ) | depth 4/6 の振り分けを直接確かめられない | #3757 |

## 5. 検証 (規則 6)

- 測定 commit: `68c6cbb75`＋本 PR のコード変更 (計装)。`git diff 68c6cbb75 HEAD -- tools/audio/asio/harness` の出力は本 PR の計装だけ。
