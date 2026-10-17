# tools/audio REPORT 付録 (#863 AU-15・consumer 側の履歴)

> **ナビゲーション**: 本ファイルは `REPORT_APPENDIX_863.md` の続き (§31)。同ファイルは 250 行上限のため、新節をここへ置いた (`docs/DOC_MAP.md` §1)。
> 製品 (FL 本体) の挙動は変えていない。変えたのは worklet の診断記録と e2e の判定行だけ。

## 31 AU-15 (#863) consumer (worklet) 側の quantum 履歴と underrun 通知 (測定 commit `2367066a5`)

- 変更 (`2367066a5`): `public/worklets/fl-audio-worklet.js` が毎 quantum `[p, rd, wr, wl, dms]` (p = run 内位置・rd/wr = out_read/out_write・wl = 状態 0/1/2・dms = 前 quantum からの Date.now 差 ms) を 64 件のリング (worklet 内のみ・SAB には置かない) へ記録する。underrun 時だけ直近 64 件を `underrun_trace` で main へ送る (1 processor あたり先頭 8 件まで)。PASS の run では送信は発生しない。
- 配線: `src/runtime/audio-shim.ts` (`ConsumerUnderrun`・`consumerStats()`)、`src/runtime/audio_app.ts` (`consumer()`)、`src/index.ts` (verify に `consumer`)。SAB レイアウト・C ヘッダ・wasm は変えていない (`git diff f44264ebe 2367066a5 -- tools/audio/src` は 0 行)。
- 判定行: `tools/audio/integration/e2e.mjs` の `cwInfo` が `cw_p cw_consumed cw_rebuf cw_notes cw_at_underrun=[p/rd/wr/wl/dms,...]` を出す (直近 6 quantum)。`rd` / `wr` は producer の `pw_at_underrun` の `w` と同じ領域で突き合わせられる。

### 機能確認 (強制 underrun・捕獲ではない)

- 検証用に、`p === 38400` の quantum で `consumed = 0` を強制する 1 行を入れた commit を捨てのデタッチ worktree で作り、e2e を 1 回通した (本 branch には入れていない。検証後に worktree を削除)。
- 結果: dev / preview とも underrun 1 件で FAIL (想定どおり)。判定行:
  `cw_p=38400 cw_consumed=0 cw_rebuf=256 cw_notes=1 cw_at_underrun=[37760/37760/38912/2/0,37888/37888/39168/2/0,38016/38016/39424/2/10,38144/38144/39424/2/0,38272/38272/39424/2/0,38400/38400/39936/2/10]`
- 整合: 最後の行 `38400/38400/39936` は `p = rd` (38400) で、`wr - rd = 1536` は同じ判定行の `fill_at_first_underrun=1536` と一致。`exceptions=0`・`worklet error` 0 件 (通知経路で例外は出ない)。
- この 1 run は合成の失敗であり、測定の母数に入れていない。

### 測定 (実 HEAD・捕獲の試行)

素材 `toolchain-emsdk` を `$RUNNER_TEMP/emsdk` に展開 (`EMSDK_ENV` 指定)、`TMPDIR=$RUNNER_TEMP`、foreground。`e2e.sh` は `git archive HEAD` を検証するため、測定の app 側は HEAD のコードである。

| 区分 | HEAD | run 数 | 結果 | 備考 |
|---|---|---|---|---|
| hunt (変更前) | `f44264ebe` (本 PR の基点) | 41 | **41/41 PASS・exit 0・FAIL 0** | 13/13 PASS・wall 11〜12 s (run 1 のみ 15 s)・1 分 load 0.43〜2.66 (`hunt.sh` の summary.txt)。回数上限 41 run・時間上限 900 s |
| hunt (変更後) | `2367066a5` | 36 | **36/36 PASS・exit 0・FAIL 0** | 13/13 PASS・wall 11〜12 s・1 分 load 0.75〜2.87。hunt 上限 420 s |

- 素材の出所は両者で異なる。変更前 (`f44264ebe`) は上流 tag `6.0.12` を `emsdk install` / `activate` したもの。変更後 (`2367066a5`) は R2 の `toolchain-emsdk.tar.zst` を展開したもの (展開物の `emsdk/upstream/emscripten/emscripten-version.txt` は `6.0.12`・`releases-6e9f6885cb17a3d6c8fd488a5cff730f50aba61d-64bit`)。版表記は一致するが、バイナリの同一性 (sha256) は未確認 (変更前の emsdk は本 run に残っていない)。

- 変更前 hunt の再測定 (`f44264ebe`・2026-10-15 01:47〜01:55 UTC): 旧版の『1 + 41 / 42/42 PASS』は、内訳 (1 の扱い) を裏付けるログが残っておらず確認できなかった。同じ手順で取り直した 41 run の値に置き換える。worktree を detached で `f44264ebe` に作り、`EMSDK_ENV` は上流 tag `6.0.12` (`tools/m1/flags.sh` の pin・CI と同版。R2 の `toolchain-emsdk` は本 run の `$ARTIFACTS_DIR` に無かった) を `emsdk install` / `activate` したもの。`bash tools/audio/integration/hunt.sh 41 900` (foreground)。判定は `f44264ebe` 自身の `e2e.mjs` (cw 行なし)。`2367066a5` の `e2e.mjs` の差分は `loc` に `cwInfo` を足すだけで、PASS 判定式は変わらない。
- 型検査・build (測定 HEAD `bdd211295`・foreground): `pnpm typecheck` (= `tsc --noEmit`) rc=0、`pnpm build` (= `tsc --noEmit && vite build`) rc=0 (`built in 116ms`)。build の `INEFFECTIVE_DYNAMIC_IMPORT` 警告 (`src/runtime/gui_proto.ts`) は本 PR の差分に含まれないファイルの警告。
- 測定 commit: `2367066a5` (コードを変えた最後の commit)。`git diff 2367066a5 bdd211295 -- public/worklets src/runtime tools/audio/integration tools/audio/src` は 0 行 (本 fix 時点で確認。以降の commit は文書のみ)。
- 本 run の PASS 判定行: dev:tone `max_err=1.49e-8`・`zero_runs=0`・`underrun_cap=0`・`first_err_frame=-1`・`cw_at_underrun=[none]`・`pw_lat_max_us` / `pw_gap_max_us` は §30 と同程度。

### 通算

- §19〜§30 の 5 件 / 560 run に本節の PASS 77 run (41 + 36) を加えて **5 件 / 637 run** (0.78%)。強制 underrun の 1 run は通算に入れない。
- 失敗の捕獲は本節でも 0 件。よって producer (wasm 出力遅延) と consumer (worklet rebuffer) の切り分けは**未達**。consumer 側の同時刻の記録 (本節) は、次の失敗で突き合わせられるようになった、という段階にとどまる。

### 未解決 (追跡 **#863**。新規 issue は起票していない)

(a) 実失敗の捕獲 (0 件のため切り分けは未了)。(b) 再現条件の特定 (頻度 5/637)。(c) 目標充填 T を判定行へ出す (連続起床の間隔との比較のため)。(d) 初回 run 仮説 (キャッシュ状態との切り分け)。(e) 通知は 1 processor あたり先頭 8 件まで・直近 64 quantum。2 件目以降の underrun は通知されない (失敗の 1 件目は取れる)。(f) worklet の `trN` (記録リング) は `gen` の変更 (start 毎) でリセットされない。`p` は run ごとに 0 から数え直すため、2 回目以降の start の underrun では直近 64 件と `cw_at_underrun` の末尾 6 件に前 run の `p` が混ざりうる。e2e は 1 page 1 start のため現在の判定には影響しない。対応は `gen` 変更の分岐で `this.trN = 0` を入れること (コード変更のため、差分分の再測定が要る)。worklet のコメントは変えていない (測定 commit のコード差分を 0 に保つため)。(g) underrun 時の診断 (`run()` の underrun 分岐) は render thread で、通知 1 回ごとに最大 64 件の `Array.from` を作って `postMessage` する (1 processor あたり最大 8 回)。PASS 時は 0 件。underrun 時の割り当て・GC・通知の負荷が、後続の underrun の出方を変えうる。対応は事前確保の `Float64Array` へ詰めて 1 回だけ post する形 (コード変更のため再測定が要る)。本 PR では未対応。

## 32 AU-15 (#863) 捕獲試行 (hunt 1 回 115 run 全 PASS・hunt.sh の出力先を起動ごとに分離)

- 測定 commit: `3c735d220` (hunt.sh に PASS run の dev:tone 判定行の保存 `pass_detail.txt` を追加。検証対象の e2e・src・worklet は不変)。その後 `fa2c9b961` で hunt.sh の出力先を起動ごとの `tools/audio/work/hunt/<UTC 開始時刻>/` に分けた。`git diff 3c735d220 HEAD -- tools/audio/integration` は hunt.sh の 2 行の差し替えのみ (`OUT` の定義行と冒頭コメント)。
- 方法: worktree `ws-863` (origin/main `95814e904` の上)。`node_modules` は main の共有分を symlink。emsdk は runner 既定の導入 (`tools/audio/build.sh` の `EMSDK_ENV` 既定値、emcc 6.0.12)。`TMPDIR=$RUNNER_TEMP bash tools/audio/integration/hunt.sh 400 1380` を foreground (時間上限 1380 s)。

| 区分 | run 数 | 結果 | 備考 |
|---|---|---|---|
| hunt (`3c735d220` と同内容の作業ツリー) | 115 | **115/115 PASS・exit 0・FAIL 0** | 1380 s で打ち切り。wall 11〜13 s (12 s が 107 run)・実行直後の 1 分 load は run 1 0.22 / run 3 1.23 / run 115 1.17 |
| `3c735d220` HEAD の確認 | 5 | 5/5 PASS | `pass_detail.txt` の判定行を確認。`cb_gap_max_ms=11`・`prod_cb_max_us` 34〜54・`pw_gap_max_us` 10215〜11006 |
| `fa2c9b961` HEAD の確認 | 3 | 3/3 PASS | 出力先が起動ごとの dir に分かれることを確認 |

- 初回 run: run 1 は PASS (13/13・wall 13 s)。hunt 開始前は `node_modules/.vite` が無く、hunt の間に作られた (どの run で作られたかは未確認)。初回 run の失敗は今回は再現しなかった。
- 115 run の集計 (hunt 中に読んだ値。ファイルは後述の上書きで残っていない): `cb_gap_max_ms` は 10 ms が 23 run・11 ms が 85 run・12 ms が 7 run。判定 1 件あたりの値の範囲は、同じ run の `pass_detail` の結果ではなく計測中の表示から読んだもの。
- 運用上の欠陥 (修正済み `fa2c9b961`): §27 までの hunt.sh は `tools/audio/work/hunt/` を起動ごとに上書きしていた。本節の 2 回目の確認 (5 run) で、115 run 分の `summary.txt`・`pass_detail.txt` が消えた。`fail_<n>.log` も後続の hunt で同名のものが上書きされうる。修正後は起動ごとに別 dir に残す。

### 読み (観測事実のみ)

- 115 run の 0 件は、通算 率 5/637 (0.78%) の下で 0 件となる確率が約 0.41 (0.9922^115)。0 件は率が下がった根拠にならない。
- 通算は §31 までの 5 件 / 637 run に本節の 123 run (115 + 5 + 3、全 PASS) を加えて **5 件 / 760 run** (0.66%)。失敗の位置が取れた 4 件は、いずれも `first_err_frame = first_underrun_frame` (56576 が 3 件 (§19・§23・§25 の記録)、56320 が 1 件 (§29))。§30 の 1 件は underrun のみ (39680) で first_err は未取得。
- 失敗が 0 件のため producer (wasm 出力遅延) と consumer (worklet rebuffer) の切り分けは**未達**。

### 未解決 (追跡 **#863**。新規 issue は起票していない)

(a) 実失敗の捕獲 (通算 0 件・本節 123 run 全 PASS)。(b) 再現条件の特定 (通算 頻度 5/760)。(c) 初回 run 仮説 (通算 5 件は、いずれも各節で最初に走らせた run。ただし節の初回 run でも PASS がある (§28 の初回 1 run など)。本節の初回 run は PASS。キャッシュ状態を分けた実測は未実施)。

## 33 AU-15 (#863) 目標充填 T を判定行へ出す (測定 commit `b10972c73`)

- 変更: `src/runtime/audio-shim.ts` の `ProducerStats` に `target_fill` (= ctl の `depth` × `buffer_frames`) を追加し、`tools/audio/integration/e2e.mjs` の判定行に `prod_target_fill=` を出す。C・worklet・SAB レイアウトは変えていない。
- 方法: worktree `ws-863` (origin/main `97a5bd8ab` 基点)。`TMPDIR=$RUNNER_TEMP EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh bash tools/audio/integration/e2e.sh`、foreground。素材 `toolchain-emsdk` を展開して使用。`e2e.sh` は `git archive HEAD` を検証するため、最初の実行 (未コミット) では `undefined` になった。コミット後に再実行して確認した。

| 区分 | HEAD | 結果 | 判定行 |
|---|---|---|---|
| e2e (1 回) | `b10972c73` | 15 PASS・0 FAIL・exit 0 (wall 38.3 s・`time` の実測) | dev:tone / preview:tone とも `prod_target_fill=1536`・`max_err=1.49e-8`・`underrun_cap=0`・`cw_at_underrun=[none]` |

- 鮮度 (コード差分 0): `git diff b10972c73 951ed5cf -- src tools/audio/integration tools/audio/src public/worklets` の出力は空 (0 行・0 バイト)。測定 commit 以降の変更は文書のみ。
- 1 分 load: 実行直前の `uptime` は 0.41 (実行後の値は未取得)。
- 読み: 無負荷の PASS run で T = 1536 frames。underrun は 0 件のため、失敗時の T はこの run からは分からない。
- 失敗時の T は `underrun` の記録に入っていない。失敗 run で `prod_target_fill` を見るには、verify 時点の値 (= 終了時の T) で代用する。T の変化 (`latency_changes`・`fla_ctl.depth` の自動拡張) は起きうるため、失敗 run の T が起床間隔の判定に使えるかは未確認。

### 通算

- 通算は §32 までの 5 件 / 760 run のまま (本節は PASS 1 回の判定行確認で、捕獲試行ではない)。

### 未解決 (追跡 **#863**。新規 issue は起票していない)

(a) 実失敗の捕獲 (通算 0 件)。(b) 再現条件の特定 (頻度 5/760)。(c) 失敗時の T は記録されない (verify 時点の値のみ)。underrun 時点の T の記録は別途必要。(d) 初回 run 仮説 (キャッシュ状態との切り分け)。

## §33 underrun 時点の目標充填 T の記録 (#863 未解決 (c))

- 変更: worklet の `underrun_trace` 通知に `T = depth × buffer_frames` を載せ、shim の `ConsumerUnderrun.T` と e2e の判定行 `cw_T=` に出す。SAB レイアウト・wasm は不変。
- 測定 commit: `a11946b16` (本番向けのコードのみ。`git diff --stat 03627cab5 a11946b16 -- public/worklets src/runtime tools/audio/integration` = 3 files, 7 insertions, 4 deletions。`03627cab5` は origin/main)。
- 判定 (clean): `e2e.sh` 15/15 PASS・exit 0 (7.8 s)。`prod_target_fill=1536`・underrun 0 件のため `cw_at_underrun=[none]` (`cw_T` は出ない)。
- 再現手段: なし。1 回限りの観測・commit 未保存・再現手段なし。強制 underrun に使った検証用 commit (`fl-audio-worklet.js` に `if (p === 25600) consumed = 0;` の 1 行を入れたもの) は repo にも origin にも残っていない。PR ブランチには入れていない。
- 結果 (強制 underrun・1 回観測・再現なし): 11/15 PASS・exit 1・9.3 s。dev / preview とも `underruns=1`・`first_underrun_frame=25600`・`cw_p=25600 cw_consumed=0 cw_rebuf=256 cw_T=1792` (dev) / `cw_T=1536` (preview)。同 run の `prod_target_fill` は dev 1792 / preview 1792。`cw_at_underrun` の末尾は `25600/25600/26880/2/0` (`p = rd`・`wr - rd = 1280` が一致)。
- 読み: `cw_T` (underrun 時点) と `prod_target_fill` (verify 時点) は、dev では一致 (1792) し、preview では一致しなかった (1536 と 1792)。`fill_trace` と `prod_target_fill` の差から、run 途中で T が変わった可能性がある。ただし 1 run の観測で、原因は未検証。
- 旧版 (`a11946b16` 時点) の記述 (dev 1536 / preview 1792・dev のみ不一致) は、この再現では一致しなかった。旧 run の出力は残っていないため、旧値は再現できないものとして扱う。
- clean 実行 (強制なし・HEAD `1e21a61a1`・`TMPDIR=$RUNNER_TEMP`・foreground): 15/15 PASS・exit 0・10 s (`uptime` load 1.77)。`prod_target_fill=1536`・`cw_at_underrun=[none]`。
- 注意: 強制 underrun 版の観測は、検証用 commit を入れた detached worktree で 1 回行った (`e2e.sh` は `git archive HEAD` を検証するため)。その commit は保存していないため、再現はできない。本番向け branch は作っていない (`863-au15-underrun-T-clean` は origin に存在しない)。本番の失敗で `cw_T` が出ることは未確認。

### 通算

- 通算は §32 までの 5 件 / 760 run のまま (本節は判定行の確認で、捕獲試行ではない)。

### 未解決 (追跡 **#863**。新規 issue は起票していない)

(a) 実失敗の捕獲 (通算 0 件)。(b) 再現条件の特定 (頻度 5/760)。(c) 失敗時の T の記録経路を追加した (本節。本番の失敗で `cw_T` が出る確認は未了)。`prod_target_fill` と `cw_T` の食い違い (preview 1 run) は仮説のみで未検証。(d) 初回 run 仮説 (キャッシュ状態との切り分け)。
