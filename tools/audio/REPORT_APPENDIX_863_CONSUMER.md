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
