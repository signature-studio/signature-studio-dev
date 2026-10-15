# tools/audio REPORT 付録 (#863 AU-15・旧 §30 全文)

> **ナビゲーション**: 本ファイルは `REPORT_APPENDIX_863.md` §30 の旧版 (測定 commit `287655cf`・初回 31 run) の全文。
> 正本は `REPORT_APPENDIX_863.md` §30 (測定 commit `89b10538`)。250 行上限のため分割移動した (`docs/DOC_MAP.md` §1)。
> 内容は削除していない。移動元は Git 履歴の `d4e39f9d:tools/audio/REPORT_APPENDIX_863.md` の 211〜234 行 (同一内容)。

## 30 AU-15 (#863) producer の write 単位の記録を ctl に追加 (測定 commit `287655cf`)

- 変更 (`287655cf`): wasm `tools/audio/src/flasio.c` の `thread_fn` が write ごとに `[w (書き込み開始 frame), fill (起床時の充填), 起床時刻 µs, 完了時刻 µs]` を `fla_ctl_t.pw_trace` (256 件リング、通算 `pw_n`) へ記録する。`FLA_CTL_SIZE` を 384 → 4488 (`pw_n`@384・`pw_trace`@388)。TS は `audio-layout.ts` と `audio-shim.ts` (`producerStats().writes`、ctl ビュー長を `FLA_CTL_SIZE` に)。
- e2e の判定行に `pw_n` `pw_w_step` `pw_lat_max_us` (起床→完了の最大) `pw_gap_max_us` (連続起床の間隔の最大) を追加。FAIL 時は `pw_at_underrun` (underrun 直前の write と次の write を `w/fill/起床µs/完了µs` で出す)。
- 合成データで `pwInfo` の FAIL 経路 (`pw_at_underrun` あり) を確認 (node で関数を抜き出して実行)。実 FAIL は未捕獲。
- 測定: 素材 `toolchain-emsdk` (`$ARTIFACTS_DIR`) を使用、`TMPDIR=$RUNNER_TEMP`、foreground、worktree `ws-863` (`origin/main` `7622290b` 起点)。

| 区分 | run 数 | 結果 | 備考 |
|---|---|---|---|
| 初回 (`287655cf`) | 1 | 13/13 PASS・exit 0 (11.1 s) | dev `pw_w_step=256` `pw_lat_max_us=35` `pw_gap_max_us=10070`・preview `25` / `10066` |
| 連続 (300 s 上限、FAIL で停止) | 30 | 30/30 PASS・exit 0 | load 0.02〜1.90 |

- 連続 30 run の判定行 (dev:tone): `first_err_frame=-1` が全件。`pw_lat_max_us` 16〜180 µs。`pw_gap_max_us` 10050〜12025 µs。`prod_cb_max_us` 20〜385 µs (§28・§29 と同程度)。
- 読み (事実のみ): 起床から書き込み完了までは最大 180 µs で、producer の書き込み処理自体は遅くない。一方、連続起床の間隔は PASS の中でも最大 10〜12 ms に達する。B=256 (5.33 ms) の 2 周期分に相当する。目標充填 T の値は判定行に出していないため、この間隔が underrun の余裕とどう対応するかは断定できない。
- 次の失敗が出たときは `pw_at_underrun` で、underrun を起こした write が (a) 起床していたか (起床の `fill` が閾値より低い、または `pw_at_underrun` に次の write が無い)、(b) 書き込み完了まで時間がかかったか、を読む。consumer 側の同時刻は未計測のため、突き合わせは (a)(b) の範囲に限られる。

### 通算

- §19〜§29 の 4 件 / 520 run に本節 31 run (全 PASS) を加えて **4 件 / 551 run** (0.73%)。
- 失敗 4 件はいずれも `first_err_frame = first_underrun_frame` (§19・§23・§25 は 56576、§29 は 56320)。本節では 0 件のため、この一致が今後も出るかは次の捕獲で確認する。

### 未解決 (追跡 **#863**)

(a) consumer (worklet) の quantum 時刻との突き合わせ (worklet 側に時刻を残す変更が要る。新規 issue は起票していない)。(b) 再現条件の特定 (負荷・タイミングとも相関は見えていない)。(c) 目標充填 T を判定行へ出す (連続起床の間隔との比較のため)。(d) 初回 run 仮説の検証 (キャッシュ状態を分けた実測)。
