# tools/audio/asio — AU-50 (#6037) 停止時の時系列計装と停止の主体の切り分け 付録

親: [REPORT.md](REPORT.md) §8 / #3757 / #2777 (#3757 残件)。前提: [REPORT_APPENDIX_4593.md](REPORT_APPENDIX_4593.md) (memset 区間の 127 ms はスレッド未実行時間と読める)。

## 1. 計装 (判定は変えない)

| 場所 | 内容 |
|---|---|
| `tools/audio/src/flasio.c` | producer 周期ごとに `[notify_ms, fill, underruns, wake, cb0, cb1, wr]` を静的配列 (2048 行) に記録。時刻は `fla_now_ms` (epoch ms)。`fla_ctl_t` の外に置き共有 SAB の layout は変えない |
| `public/worklets/fl-audio-worklet.js` | `underrun_trace` に `ms: Date.now()` を追加 (consumer の underrun 時刻) |
| `src/runtime/audio-shim.ts` | `underrunLog` に `ms` を保持 |
| `tools/audio/asio/harness/com_page.mjs` | main thread の heartbeat (5 ms 周期、20 ms 超の間隔を `hb_gaps` へ) と、`tl` / `ul_ms` (underrun 時刻と worklet 直近 64 quantum の `recs`) を結果 JSON へ |

すべて同じ epoch ms の時計 (`performance.timeOrigin + now`。worklet は `Date.now()`)。

## 2. 測定

測定 commit: `6b5ddfd22` (計装を入れた最後の commit)。

- 負荷: `yes > /dev/null` × 4 (PID を控えて終了後に PID 指定で `kill`)。
- 対象: `node tools/audio/asio/harness/run_com.mjs --only com_ramp_b256_d2`。

### 2-1. 計装コード上の負荷下の試行 (作業ツリーの途中版を含む)

| 試行 | 結果 | underrun 時刻の producer 状態 |
|---|---|---|
| r6037_load1 | underruns=1 silence=3712 | fill 0・producer wake 間隔 101.6 ms (worklet `recs` なし) |
| r6037_load2 | underruns=1 silence=2560 | fill 0・producer wake 間隔 91.7 ms (worklet `recs` なし) |
| r6037_L1〜L5 | 0 / 5 | — |
| r6037_load4 | 個別の結果は未記録 (下記 注) | — |
| r6037_L6〜L8 | 0 / 3 | — |
| r6037_L9 | underruns=1 silence=256 (ramp 117,632 mismatch) | fill 0・producer wake 間隔 62.5 ms |

- 試行は `6b5ddfd22` と作業ツリー途中版のどちらで取ったかを区別して記録していない (両方を含む)。HEAD `6b5ddfd22` の 6/6 PASS (§2-2) とは別の試行として扱う。
- 計装途中版 (`recs` が入る前) の試行 (load1・load2) は、worklet の直近 quantum が JSON に入っていない。`recs` が取れたのは L9 だけ。
- load3 は試行後に出力欠落を確認して除外した。分母 12 はこの除外後の数 (load1・load2・load4・L1〜L9)。load4 の個別の結果は記録が無い。underrun 3 回の内訳は load1・load2・L9 として記録されている。

### 2-2. 計装 commit `6b5ddfd22` 上の負荷下 (段別計装 `570f76617` の前)

| 試行 | 結果 |
|---|---|
| c6b5_L1〜L6 | 6 / 6 PASS (underruns 0・silence 0・ramp 0 mismatch) |

計装途中版 (§2-1) は負荷下 12 回 (load1・load2・load4・L1〜L9。load3 は試行後に除外) で underrun 3 回。`6b5ddfd22` は 6 回で 0 回。母数が小さく、この commit での再現は確認していない。段別計装 `570f76617` の HEAD では 5 回中 2 回 FAIL で再現している (§3-3)。

## 3. 停止の時間帯の切り分け (L9 の 1 例)

underrun を基準 (0 ms) とした相対時刻。

| 系 | 観測 |
|---|---|
| worklet (consumer) | 直近 64 quantum のすべてで `rd` が進む。直近 61 ms の quantum 間隔 `dms` は最大 13 ms・合計 60 ms。停止なし |
| producer (flasio thread) | producer 列の `wr` (epoch ms) は underrun +1.4 ms まで書き込み。その後の wake は +8.5 ms・+17.7 ms と間を空けて、最後に +56.5 ms。区間の最大 wake 間隔は 62.5 ms (`cb0`/`cb1` の計算は 0.00〜0.02 ms)。worklet 側の `wr` (rd/wr のサンプル index) は 122880 で止まる (producer 列の値ではない) |
| main thread heartbeat | 下限 20 ms 超の間隔は underrun 後 [+210, +247, +271] ms と [-3232〜-2934] ms のみ。停止の時間帯 [-100, +60] ms に gap は無い |
| 区間内の seg 最大 (run 全体) | memset 2780 µs・out_write 2225 µs・bufferswitch 2375 µs (1 run の最大。区間は計算の仕事量より桁違いに長い) |

読み (n=1: L9 のみ、計装途中版での 1 回。HEAD `6b5ddfd22` の 6/6 PASS とは別の試行): producer の wake 間隔は 62.5 ms。直近 61 ms では worklet に停止は見られない (最大 13 ms)。ただし直近 64 quantum (約 171 ms 分) には worklet の 41 ms の quantum 間隔が 1 つあり、その位置は未確認のため、停止の時間帯との重なりは言えない。したがって停止の主体は未確定。producer が OS に preempt されたのか、`wait32` の返りが遅れたのかは、記録点が wake と書き込み完了の 2 点のみのためこの計装では区別できない。
L9 では producer の wake 間隔 62.5 ms に加えて、-139.9 ms の 41.7 ms gap もあった。consumer の 41 ms と時刻は一致しない。

## 3-2. 段別計装後の再測定 (本 run・受入 1 の JS 側 bufferSwitchTimeInfo 時刻)

計装: `do_buffer` に `tb` (memset 直前)・`t0` (memset 直後 = ホスト `bufferSwitchTimeInfo` 呼出し直前)・`cb1` (呼出し直後) の epoch ms を `flasio_tl2_ptr` で追加 (判定に使わない)。
測定: `yes` × 4 (PID 指定で停止)・`run_com.mjs --only com_ramp_b256_d2`。

用語 (本 REPORT での定義はここ 1 箇所。以下すべてこの定義で使う):

- **段別計装前**: `tb`・`t0`・`cb1` を入れる前の版で取った試行 (r6037_a のみ)。
- **段別計装版**: `tb`・`t0`・`cb1` を入れた版で取った試行 (r6037_b〜d)。commit は未記録。
- **HEAD `570f76617`**: 段別計装を入れた最後の commit。r570_1〜5 はこの commit で取った。

| 試行 | 結果 | 備考 |
|---|---|---|
| r6037_a (段別計装前) | FAIL: underruns=1 silence=3968・cb_max 100450 µs | 停止の時間帯 [-20, +80] ms で do_buffer の span が 100 ms。main thread の gap 無し |
| r6037_b・c1・c2・c3 (段別計装版) | 4/4 PASS | underruns 0 |
| r6037_d1 (段別計装版) | FAIL: underruns=1 | 下記 |
| r6037_d2〜d5 (段別計装版) | 4/4 PASS | underruns 0 |

- r6037_a (段別計装前・underrun 0 ms 基準): wake = cb0 = -20.0 ms、cb1 = wr = +80.5 ms。do_buffer の span は 100.5 ms で `cb_max_us` (100450 µs) と一致する。`cb_max_us` は `t0`〜`t1` (クロック読取り + ホスト `bufferSwitchTimeInfo` 本体) の区間なので、**この 1 例の停止は JS 側 bufferSwitchTimeInfo の区間の中で起きた**。ただし段別の記録が無いため、クロック読取り・ホスト本体・OS preempt のどれかは区別できない。
- r6037_d1 (underrun 0 ms 基準): 直前の producer 書き込みは -38.5 ms、次の wake は +17.4 ms (wake 間隔 55.9 ms)。wake 以降の `tb`・`t0`・`cb1`・`wr` はすべて 17.4 ms で、**do_buffer の中の span は 0 ms**。区間 [-38.5, +17.4] は callback の外 (`wait32` 中か、OS に preempt されていた)。
- 2 例で停止の位置が違う (a: callback 内側の 100 ms、d1: callback の外側の 55.9 ms 間隔)。どちらも仕事量の計装では説明できず、preempt の可能性が残る。
- 「wake の遅れ」と「wake 後に実行を得られなかった」は、`tl_wake` と `cb0` が同一時刻のため区別できない。
- worklet の直近 64 quantum の `dms` 最大 38 ms は位置が未確定 (wake 間隔の窓 [-38.5, +17.4] と一致しない)。
- main thread heartbeat: 停止の時間帯の gap は無し (d1 の gap 51〜94 ms は underrun より 2.4〜2.7 s 前)。

### 3-3. HEAD `570f76617` (段別計装入り) の負荷下

測定 commit: `570f76617`。`yes` × 4 (PID 指定で停止)・`run_com.mjs --only com_ramp_b256_d2`。

| 試行 | 結果 | underrun 0 ms 基準の内訳 |
|---|---|---|
| r570_1〜3 | 3/3 PASS | — |
| r570_4 | FAIL: underruns=1 silence=512 | callback 内 span 最大 7.9 ms (`cb_max` 2.6 ms)。heartbeat gap [-78, -52] ms (26 ms)。producer の wake 間隔最大 48.5 ms は underrun の 2.5 s 前 |
| r570_5 | FAIL: underruns=1 silence=512 | callback 内 span 最大 0.1 ms。producer の wake 間隔最大 59.6 ms が [-20.6] ms で始まり、区間内に callback 実行なし。heartbeat gap なし (停止の時間帯) |

- 両例とも、停止の時間帯に callback 内の仕事 (memset・ホスト `bufferSwitchTimeInfo`・out_write) は長くない。producer の wake 間隔が 48〜60 ms 空いている。
- r570_4 の heartbeat gap [-78, -52] ms は main thread 側の停止の候補だが、同時刻の wake 間隔とは一致していない (wake 間隔の最大は別位置)。
- 観測 5 例 (L9・a・d1・r570_4・r570_5) の位置の整理は §4。

## 4. 結論と未解決 (#6037 受入)

- **停止の位置 (観測 5 例)**:
  - L9 (計装途中版・§3): producer の wake 間隔 62.5 ms。直近 61 ms の worklet に停止なし。`wait32` 区間の側。
  - a (段別計装前・§3-2): do_buffer の span 100 ms。callback 内の側。
  - d1 (段別計装版・§3-2): callback の外の wake 間隔 55.9 ms。`wait32` 区間の側。
  - r570_4 (HEAD・§3-3): callback 内 span は最大 7.9 ms と短い。heartbeat gap [-78, -52] ms があり、main thread 側の候補。producer の wake 間隔 48.5 ms は別位置。
  - r570_5 (HEAD・§3-3): wake 間隔 59.6 ms。区間内に callback 実行なし。`wait32` 区間の側。heartbeat gap なし。
  - 結論: 停止の位置は 5 例で一つに定まらない。`wait32` 区間 (L9・d1・r570_5)、callback 内 (a)、main thread の gap 候補 (r570_4) がある。段別計装では直接経路は確定できない。
- **直接経路**: 特定できなかった。区間 a の 100 ms が「クロック読取り・ホスト本体の実行遅延」か「OS の preempt」かは、段別の記録が無い a では区別できない。d1 と r570_5 は callback の外側 (`wait32` 中) で、wake の遅れと wake 後の実行待ちは `tl_wake` = `cb0` のため区別できない。
- **受入 1 (#6037)**: 部分達成。wasm 側 (producer) と worklet/main の時系列は同じ epoch ms で記録した。JS 側 bufferSwitchTimeInfo の呼出し時刻は、段別計装 (`tb`・`t0`・`cb1`) で記録できるようになった (d1 で確認)。
- **前 run の「`6b5ddfd22` で 6/6 PASS」**: 段別計装 HEAD `570f76617` では 5 回中 2 回 FAIL (§3-3)。6/6 は母数が小さく、再現性の根拠にはならない。
- **負荷下の FAIL 頻度 (本 run の全試行)**: 段別計装前 1/1 (a)・段別計装版 1/9 (b〜d)・HEAD `570f76617` 2/5 (r570)。計 4/15。
- **未解決**:
  - 負荷下の失敗頻度は母数が小さく、確定しない。HEAD `570f76617` では 2/5 で再現している (§3-3)。§2-1 の計装途中版の 3/12 とは別集計。
  - JS 側 bufferSwitchTimeInfo の独立した呼出しログは追加していない (§3-2)。
  - 床の値 (`FLA_F_T_FLOOR`) は変えていない (PM 判断)。

## 5. 待ち記録の計装と本 run の再測定 (run 3・受入 1 の残件・受入 2)

計装: `fla_out_wait_fill_le` の wait32 1 回ごとに [開始 ms, 終了 ms, rc, 待ち入り時の fill, max_fill] を `flasio_wt_*` で記録 (判定に使わない)。rc: 0=通知、1=値変化で即戻り、2=timeout。commit: `9d9305f20` (記録) → `c525b67cb` (fill 記録の版)。

**注 (差し戻し対応)**: `c525b67cb` は `fla_wait_trace_hook` の宣言 (3 引数) と定義 (5 引数) が食い違い、C がビルドできない (clang: `redefinition ... with a different type`)。そのため `c525b67cb` と `9d9305f20` の測定は、どのビルド成果物で取ったかを確認できない。以下 r10・r11 の PASS は根拠にしない。fill の記録は、食い違いを直した `52b5a68d1` で初めて実装どおり動いた。

修正 commit: `52b5a68d1` (宣言・`wt_note`・harness の列を 5 引数 / 5 列に揃えた)。`git diff c525b67cb 52b5a68d1 -- tools/audio/src tools/audio/asio/harness tools/audio/asio/build.sh` の差分は 3 ファイル 7 行 (`flaudio.h` 1 行・`flasio.c` 3 行・`com_page.mjs` 3 行)。build.sh は差分に含まれないが、本体の `node_modules` の `tsc` を参照して完走させた (worktree の `node_modules` は symlink で、commit していない)。

測定: `yes` × 4 (PID 指定で停止)・`run_com.mjs --quick --only com_ramp_b256_d2`。測定 commit: `52b5a68d1` (ビルド OK・emsdk 6.0.12)。

| 試行 | 結果 | 備考 |
|---|---|---|
| r9_1 (`9d9305f20`) | FAIL: underruns=1 silence=5760 | 上の注のとおり、ビルド不可の commit。停止の時間帯 [-130, +113] ms。wait は [-130, -30] で rc=0 が続く。producer の書き込みは -29.7 ms、次の書き込みは +113.5 ms |
| r9_2・r9_4 (`9d9305f20`) | PASS ×2 | ビルド不可の commit (注) |
| r9_3 (`9d9305f20`) | FAIL: underruns=1 | ビルド不可の commit (注)。`wait_timeouts=1`。wait [-53.9, -2.8] は rc=2 (timeout 50 ms) |
| r10_1〜8 (`c525b67cb`) | 8/8 PASS | ビルド不可の commit (注)。根拠にしない |
| r11_1 (`c525b67cb`) | PASS | ビルド不可の commit (注)。根拠にしない |
| e2e `--quick` (`c525b67cb`) | exit 0・3/3 PASS・73 秒 | ビルド不可の commit (注)。根拠にしない |
| e2e `--quick` (`52b5a68d1`) | exit 1・2/3 PASS・77 秒 | node check 126/126 PASS。`com_ramp_b256_d2` FAIL (underruns=1 silence=1024・ramp 114560/144256)。負荷なし (load avg 0.72) |
| rl_1 (`52b5a68d1`・負荷) | FAIL: underruns=1 | wait 335 件 (rc 0=331・1=2・2=2)。`wait_timeouts=2` |
| rl_2 (`52b5a68d1`・負荷) | FAIL: underruns=2 | wait 464 件 (rc 0=461・1=2・2=1)。`wait_timeouts=1` |
| rl_3〜rl_8 (`52b5a68d1`・負荷) | 6/6 PASS | underruns 0 |

rl_1〜8 は `work/load_trial.cjs 8` で取った (`yes` × 4 を全 8 試行の間で 1 度立て、終了後に PID 指定で停止)。8 回中 FAIL 2 (rl_1・rl_2)。

- rl_1 の timeout 2 件: 52.9 ms (fill 2176・max_fill 2048)・50.3 ms (fill 2304・max_fill 2048)。どちらも待ち入り時 fill が max_fill を超えたまま timeout に入っている。
- rl_2 の timeout 1 件: 50.1 ms (fill 1664・max_fill 1536)。同じ形。

読み:

- `52b5a68d1` (実装どおりに fill を記録する版) で、無負荷 e2e 1 回の underrun と、負荷下 8 回中 2 回の underrun を再現した。`c525b67cb` の 8/8 PASS (r10) は、ビルド不可の commit での測定のため根拠にならない。
- 失敗時の wait 記録は、待ち入り時 fill が max_fill を上回ったまま 50 ms の timeout に入った形。producer の通知が届かない (out_read が wake_target に達しても notify されない) か、worklet が追いつく前に producer が寝た形のどちらとも、この記録だけでは区別できない。
- 直接経路 (producer の preempt か、wait 返りの遅れか、通知の欠落か) は特定できなかった。

## 6. run 4: wait の返り時 fill の記録と負荷下の再測定 (受入 2)

計装: `wt` に返り時 fill (`fill1` = `w - out_read` after wait32) の列を追加 (判定に使わない)。宣言・定義・呼出し・harness の列を同時に揃えた (`fla_wait_trace_hook` の型不一致を再発させないため)。

測定 commit: `602a274e5` (本計装を入れた最後の commit。基底は `2b64a163b`)。`yes` × 4 (PID 指定で停止)・`run_com.mjs --quick --only com_ramp_b256_d2`。

| 試行 | 結果 | 備考 |
|---|---|---|
| r4_1 | FAIL: underruns=1 silence=3840 | ramp 114688/143616。結果 JSON は r4_2 で上書きされる前に解析した (解析値は本節のとおり。ファイルのコピーは無い) |
| r4_2〜r4_9 | 8/8 PASS | underruns 0 |

- 負荷下 FAIL は 9 回中 1 回 (r4_1)。母数が小さく、頻度は確定しない。
- r4_1 の停止の時間帯 (underrun = 0 ms 基準): producer の row107 は `wake` = `tb` = -29.9 ms、`t0` (memset 直後) = +77.2 ms。区間 [-29.9, +77.2] (約 107 ms) は `tb`→`t0` の間で、この区間の仕事は memset のみ (数 µs)。
- 同区間の `wait32` の記録は無い。最後の wait (開始 -39.8・終了 -29.9 ms、rc 0) が返った時刻と row107 の wake (-29.9 ms) は一致し、次の wait の開始は +77.4 ms。つまり producer は wait が返った直後から `tb`→`t0` (memset 区間) の中で約 107 ms 戻らなかった。
- 読み: 区間の仕事は memset だけ (数 µs) なので、この空白はスレッドが実行されなかった時間として読める。「memset 中に preempt された」か「`tb` 記録の後に実行を得られなかった」かは、`tb`・`t0` の 2 点しか無いため区別できない。wait の返り時刻 (-29.9 ms) が notify に対して遅れたかは、row107 の notify 時刻を照合していないため未確定。
- 受入 2 (直接経路の特定): 特定できなかった。切り分けの範囲は「producer thread が wait の返りの直後、memset 区間で約 107 ms 実行されなかった」まで。OS の preempt かホスト側の thread 停止かは、wasm 側の計装では分けられない。
