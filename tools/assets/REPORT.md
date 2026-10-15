# CAB-21 asset-vfs — 引継ぎ完了レポート (314MB 級 wasm asset の chunk ローダ + 二段キャッシュ)

実施 2026-10-10 / node v26.10.0 / Chrome 154 headless (実ディスクプロファイル) / 検証 `bash tools/assets/e2e.sh --full` (exit 0)。
**検収 2026-10-11 (CAB-21 In Review / commit c2c31c8)**: e2e を clean HEAD の worktree から再実行して全 PASS、数値の一部を実測で修正 (§5・§10)。既知類型との関係: 該当なし (本 ticket は lift/逆アセ/IR pass 系ではない)。

## 1. 結論

- **前担当残骸 (tools/assets/, コミット 0 件) は全面採用**。VFS 本体 (manifest v1 / pack / LazyVfs / SlotCache(OPFS) / SabLoader / Emscripten FS) は修正 1 行も不要で node/Chrome 実測 ALL PASS。壊れていたのは**テストハーネス側 3 点**のみで修正した (§3)。
- チケット要件の未実装部分「**manifest→chunk 取得→連結→compileStreaming→キャッシュ (IDB/OPFS)**」を `vfs/asset.ts` + `vfs/idb.ts` として新規実装し、**314,206,140 byte の wasm (素材 k100, exports 8271) で 4 シナリオ e2e 全 PASS** (§5)。
- キャッシュは **L1=IndexedDB (bytes のみ保存, Module は保存しない) / L2=OPFS SyncAccessHandle** の二段。破損検出は **chunk 単位 sha256 (内容アドレス id) を毎読み照合**し、破損 chunk だけ他 tier / network から再取得して部分修復する (§4)。
- **deploy/client/chunked.mjs との統合判断: ストリーミング契約は同一形に寄せ、実装は統合せず E 側に置く** (理由と統合経路は §6)。

## 2. 前担当残骸の評価 (採用/放棄)

| 資産 | 判断 | 根拠 (再検証実測) |
|---|---|---|
| `vfs/` (manifest/path/codec/lazy-vfs/cache/opfs/sab/loader/http-source/emscripten/node-file) | **採用 (無改修)** | `tsc` OK, node 結合テスト ALL PASS (399 ファイル照会 sha256 一致 [サンプル定義: `dataFiles` から `i % ceil(27090/400) === 0`]、restart で 231–232 slot 復元) |
| `pack/pack.ts` + `bootset/` `inventory/` `win_paths/` | **採用 (無改修)** | full pack 610MB (2,009 chunk) を本 tickets で再利用せずとも 1 ファイル pack がそのまま使えた (§5 の 300 chunk 生成 0.8s) |
| `test/{node,emscripten,browser}-test.ts`, `bench.ts`, `server.ts`, `spawn-server.ts` | **採用 + 修正** | §3 の通りハーネス 3 点を修正。VFS ロジック自体のバグは今回 0 件 |
| `results/` `MANIFEST.md` `PACKAGE_STATS.md` | 採用 (実績値として維持) | 再計測と矛盾なし |
| 停止時の未完成物 (314MB wasm 経路) | **不在** — work/ に痕跡なし (最終成果物は 15:42 の空 pack 実行のみ)。要件どおり新規実装 | `find -newermt` で確認 |

## 3. 停止地点のデバッグ (「manifest fetch 後 chunk request 無しで停止」)

停止セッションの再現は事後では不可能 (痕跡なし) だが、構造原因を 3 点特定し全て修正した。いずれも「manifest fetch が成功するが chunk request が出ない窓」に該当する:

1. **Chrome プロファイルが tmpfs** (`/tmp/opencode/chrome-*`): 本 VM の /tmp は tmpfs 3.7GB で、tools/hosting/REPORT.md §6-8 の実測どおり OPFS SyncAccessHandle 書込が `InvalidStateError` で壊れる。→ **プロファイルを実ディスク (`work/chrome-profiles/`, gitignore) へ変更** (browser-test.ts, asset-e2e.ts)。
2. **`/__report` のポーリング競合**: spawn-server が 250ms 間隔で `GET /__report` を繰り出し、サーバは GET で pendingReport を**消費**する。デバッグ中の curl や先行 GET がエラー報告を吸うと本体は report timeout で「停止」に見える。→ **`GET /__report?wait=<ms>` ロングポール**を追加し、spawn-server は 1 本の待ち受けに変更 (curl の覗き見は消費しない)。
3. **停止が報告されない経路**: probe-worker の応答待ちと fetcher の `ready` 待ちに timeout も onerror も無く、nested worker が起動しなければ永久停止する。→ **stage 進行報告 (progress) + 全待受に timeout + ページ側 90s 監視**を追加し、停止時は必ず `stage` 付きで /__report にエラーが届くようになった (engine-worker.ts, asset-page/main.ts)。

修正後、旧ハーネス相当 (VFS browser-test) と新 e2e が**同条件で再現なく ALL PASS** (cold/warm/xhr + asset 4 シナリオ × 複数回)。

## 4. 追加実装: asset ローダのアーキテクチャ

```
engine Worker                                    test server (= 案S Static Assets 相当)
┌──────────────────────────────────────┐        ┌─────────────────────────┐
│ fetchManifest → latest.json → m/*.br │◄──────►│ c/<id2>/<id>.br (immutable)│
│ ManifestIndex.file(path) → 300 chunk │        │ m/<sha16>.json.br        │
│        openAssetStream()             │        └─────────────────────────┘
│  chunk i の解決順:                    │
│   L2 OPFS fl-assets/<keyHash>.bin    │  4KiB header (magic/ver/nChunks/chunkSize/
│    ├ bitmap 未書込 → skip            │  keyHash/書込済み bitmap) + chunk i を
│    ├ 読み→sha256(id)照合 → NG なら破損│  4096+i*1MiB に固定配置 (SyncAccessHandle)
│   L1 IDB fl-assets-v1 parts/${key}/${i} → bytes (Uint8Array) + meta
│    ├ 照合 NG なら part 削除→破損      │
│   network HttpChunkSource (fetch+復号│
│    +sha128検証+再試行)                │
│  修復: 破損 chunk だけ取得して両 tier │
│  に書き戻し (部分修復)                │
│        ↓ 順序保証 ReadableStream      │
│  (並列先読み6 + 背圧, HWM=0)          │
│  new Response(stream,{'content-type':│
│   'application/wasm',content-length}) │
│        ↓ WebAssembly.compileStreaming │
└──────────────────────────────────────┘
```

- 破損検出の単位: **chunk id = 非圧縮 chunk の sha256 先頭 128bit** (manifest の内容アドレスと同じ)。OPFS 読み出し毎に照合する (314MB 全量で約 0.9–1.2s, pass2 実測 0.867–1.198s を参照)。asset 全体の sha256 一致は e2e が別途全バイト再読みで検証した (`shaOk`)。
- OPFS header の bitmap は payload 書込**後に**立てるので torn write 安全。未書込 chunk は読まずに次 tier へ落ちる (再開時の無駄読みなし)。bitmap は 64..4095 バイト = 最大 32,256 chunk (32GiB @1MiB)。
- **IDB に Module を保存しない理由**: 保存対象は bytes のみ。Module の構造化複製は可能だが Chrome 固有最適化に寄せると、chunk id による照合・部分修復・他 tier との整合が bytes 単位で保てなくなるため (設計決定)。
- 保存完了の成否は `done` (ストリーム消費完了 → 全 IDB put 完了 → meta 書込) で保証し、compileStreaming 成功後に await する。

## 5. e2e 実測 (`node test/asset-e2e.ts`, 4 起動で OPFS/IDB を跨ぐ, 1 シナリオ = Chrome 1 起動 + ロングポール 1 本)

asset: `Engine/FLEngine.wasm` = k100.wasm 314,206,140B / 300 chunk (br, 125.8MB 格納) / 期待 sha256 `0f31f2df…`

| シナリオ | network | chunk 取得内訳 | compileStreaming | 全体 sha256 | tier 復元 |
|---|---|---|---|---|---|
| cold (net ON) | 300/300 req, 314.2MB | opfs 0 / idb 0 / net 300 | **4.264–6.518s** (n=12。最大値は `e2e.sh --full` 内実行 = 他テストと page cache を争う条件) | 一致 | OPFS 314,210,236B + IDB meta 保存 |
| warm-netoff (net OFF) | **0 req** (server chunk request 0) | opfs 300 | **1.104–1.883s** | 一致 | OPFS 読み 300 |
| corrupt-opfs (net OFF) | 0 req | opfs 299 / **idb 1 (修復)**, 破損検出 1 | **1.110–1.880s** | 一致 | OPFS 自動修復 (opfsWrites 1) |
| corrupt-both (net ON) | **1 req (1MiB のみ再取得)** | opfs 299 / net 1, 破損検出 2 (opfs+idb) | **1.122–1.931s** | 一致 | 両 tier 修復 (opfsWrites 1 / idbWrites 1) |

- compile の定義: manifest fetch → 全 chunk 解決 (二段キャッシュ + 部分修復) → 連結 → `WebAssembly.compileStreaming` 成功までの wall time (Chrome 内 `performance.now()`)。
- 負荷条件: load average 1.9–17.4 (nproc=16, 他 agent 並行) / headless Chrome 154.0.8037.97 / 実ディスクプロファイル `work/chrome-profiles/`。負荷・page cache 依存なので min–max で記載 (規則 38)。実装側 3 回分の生値は `work/` が毎回上書きされるため残っていない。
- exports **8271** / imports **21** (全 func import、module は `env` と `wasi_snapshot_preview1`) を返し、**CAB-61 が Worker 内実測した同 wasm の exports 数 8271 と一致**。
- キャッシュ全読み + 全量 sha256 検証 (pass2) は **0.867–1.198s = 262–358 MB/s, per-chunk sha256 検証込み** (n=4、生 JSON が残る runs)。
- cold の後片付けを含む全 e2e (`e2e.sh --full`): node / emscripten / browser(cold,warm,xhr) / bench / asset 4 シナリオ **全部 PASS, exit 0**。

## 6. deploy/client/chunked.mjs との統合判断 (読取のみで確認)

- **同一の契約**: descriptor(index.json)+part → 並列先読み (6) → 順序保証 ReadableStream (HWM=0, pull 駆動) → `new Response` → `compileStreaming`。E の `openAssetStream` はこの形をそのまま踏襲した (CAB-61 の実績契約と byte-stream 動作が同一)。
- **相違**: ① ソースが part index でなく E の内容アドレス manifest (`c/<id2>/<id>.<ext>`, chunk id がそのまま検証子) ② **二段キャッシュ (OPFS/IDB) と破損部分修復を持つ** (chunked.mjs はキャッシュ無し・検証は part sha256) ③ 再試行は案S 前提で控えめ (既存 HttpChunkSource の 3 回, 429 過剰設計を回避) ④ Access 失効系 (`AccessExpiredError`) は未実装 — 案S + 同一オリジン構成では現れていないため (要約: T REPORT §6-5)。
- **統合判断: コード統合はしない**。deploy/client は「part index 形式の資産」用の完成品で tests もあり (7/7), E 側は manifest 由来 chunk のキャッシュ付きローダが必要。**統合するなら「E の asset.ts を chunked.mjs のソース差し替え (fetchChunk 部) として逆輸入する」方向**が最小で、必要になったのは >25MiB 資産を part index 形式で配る場合 (deploy 05-stage.mjs 経路)。現行の E manifest 経路 (案S, ≤1MiB chunk, 2,009 objects) では重複にならない。REPORT として記録し、両者の契約互換 (ReadableStream+Response+compileStreaming) は維持した。

## 7. 制限・既知事項

- **Chrome 専用実測** (Chrome 154 headless)。Firefox/Safari 未検証 (OPFS/IDB は両対応のはず, T REPORT §8)。
- compile のメモリ: compileStreaming は逐次だが、e2e の全量 sha256 検証 (pass2) は 314MB を一括確保する (検証のため。製品版は chunk 単位検証のみでよく一括確保は不要)。
- IDB 単位は chunk (1MiB) ごと。**全体を 1 Blob で持つ場合の比較は未実施** (部分修復と部分充填再開を優先した設計判断)。
- `warm-netoff` は manifest (latest.json + m/*.br, 6KB) の取得は許す (内容アドレス・短TTL pointer の設計どおり)。完全オフライン (manifest もキャッシュ) は未実装。
- 旧ハーネスの `/tmp` プロファイル問題の再現実験は本環境では行っていない (T の 8/8 再現実測を引用。実ディスクでの全 PASS で代替確認)。
- `SyncXhrLoader` 経路は asset ローダには実装していない (SAB/xhr は VFS 側の役務)。

## 8. 次タスク提案 (下流チケット案)

1. **engine ブート結合 (M12 hostbridge)**: `loadWasmAsset` を hostbridge/nfo の起動経路に接続し、OPFS キャッシュから instantiate → shim 初期化まで通す (asset.ts は compile まで実装済。instantiate と imports 接続が残務)。
2. **part index 形式との相互運用**: deploy/05-stage.mjs 形式の資産を E ローダで読む adapter (§6 の逆輸入路線)。>25MiB 資産が Static Assets に載る場合の唯一の経路。
3. **manifest の完全オフライン化**: latest.json/manifest も IDB に載せて「2 回目は全くネット無し」を成立させる (e2e に `net=m` モード追加)。
4. **複数 asset のキャッシュ管理**: fl-assets 配下の quota 管理 (storage.estimate との突合, LRU 削除, バージョン更新時の差分再取得)。OPFS bitmap は差分再開に対応済み。

## 9. 後続: 書込可能 VFS (RT-5, `wvfs/`)

CAB-123 により `/c/home`・`/c/tmp` の OPFS バッキング書込 mount が `wvfs/` に追加された
(アペンドジャーナル + A/B スーパーブロック, flush 契約 `onYield()`/`onPageHide()` = FS.syncfs 相当,
pathreg 既定マウント表の `/c/home`・`/c/tmp` 写像先を実装)。本 REPORT (CAB-21) の資産は無変更。
詳細は **`wvfs/REPORT.md`**、検収は `bash tools/assets/wvfs/scripts/e2e.sh`。
差分: 本ファイルへのこの節追加と `tsconfig.json` include への `"wvfs"` 追加のみ。

## 10. 検収 (2026-10-11 / 検証起点 commit c2c31c8, clean HEAD worktree)

- **範囲**: c2c31c8 の 62 files / 9,192 insertions は全て `tools/assets/` 配下 (他 dir 0 行)。最大 blob 21,363 B (`inventory/compress_bench.json`)、20 MiB 超 0 個。`git status --porcelain -- tools/assets` = 空 (取りこぼしなし)。
- **clean HEAD 再実行**: `git worktree add --detach tools/assets/work_verify HEAD` で展開し `bash e2e.sh --full` → **exit 0** (wall 180s, load average 開始 4.73 → 終了 6.59)。node / emscripten / browser(cold,warm,xhr) / bench / asset 4 シナリオ ALL PASS。
- **独立再計算 (別アルゴリズム)**: `node test/make-asset-pkg.ts && node test/asset-e2e.ts && node test/verify-asset-indep.ts` (pack.ts / asset.ts を import しない node 経路)。300/300 chunk の内容アドレス一致・Σu 314,206,140 B・連結後 sha256 = 元ファイル sha256・独立 section 解析 exports 8,271 / imports 21 (`WebAssembly.Module.imports()` と一致)。OPFS ファイルサイズ 314,210,236 = 4,096 + 314,206,140 を全シナリオで確認。
- **② OPFS 設計の検算**: HDR 4,096 / bitmap 64..4,095 = 4,032 B = 32,256 bit (300 chunk は 38 bit 使用)。書込順は payload → bitmap (`opfsWriteChunk` → `opfsBitmapSet`) で、bitmap が立っていない chunk は読まずに次 tier へ落ちる。模擬では「payload 書込後・bitmap 未書込み」の torn write 300 件すべてが未書込扱い (破損受入 0)。対照 (bitmap 先書き) では payload 未書込でも読み出しに行くが sha 不一致で 300/300 破損検出される。
- **③ 契約互換**: `openAssetStream` と `deploy/client/chunked.mjs` は同じ `while (next < n && next - emit < conc) start(next++)` / `pull` 駆動 / `highWaterMark: 0` / `new Response(stream, {content-type, content-length})` 構造。差異は §6 の 4 点 (ソース・二段キャッシュ・再試行・Access 失効) で、コード統合しない判断を支持。
- **⑤ 停止原因 3 点の修正を確認**: (1) Chrome プロファイルは `work/chrome-profiles/` (実ディスク) — test/asset-e2e.ts:70,71 と test/browser-test.ts:65,66 (2) `GET /__report?wait=<ms>` ロングポール、spawn-server は 1 本待ち受け — server.ts:75-101, spawn-server.ts:34,35 (3) `progress('stage')` 報告 + 全待受 timeout (`withTimeout` 30s/60s, `waitReport(240000)`) + ページ側 90s watchdog — engine-worker.ts:20,74、asset-worker.ts:16-18、main.ts:16-24。
- **ネガティブコントロール (規則 41)**: 検証 copy の `vfs/asset.ts` から OPFS 読み出しの per-chunk sha128 照合だけを削除すると (検証後に HEAD 内容へ復旧済み)、corrupt-opfs が `CompileError: length overflow` で FAIL (2 シナリオ FAIL)。照合が破損検出の実体であることを確認。追加の検算: 1 バイト破損は sha128 不一致で検出 / 照合を外すと全体 sha256 が不一致のまま通過 / chunk 0 と 1 を入替えると `WebAssembly.compile` が magic word エラーで失敗 (§5 の表と同一条件で `node test/verify-asset-indep.ts` 出力)。
- **修正した誤記** (この commit): §2 の 227 ファイル→399 ファイル・234 slot→231–232 slot、§4 の pass2 923–1229ms→0.867–1.198s、§5 の 4 シナリオ compile を n=12 の min–max に更新 (当初の n=3 の範囲は狭く、`e2e.sh --full` 内実行の 6.518s を含んでいなかった)、pass2 255–350 MB/s→262–358 MB/s、**imports 3→21**。

## 11. ST-T14 の tier 差分 6 点を bootset 規則に反映 (#592 / 親 #39 / 検証起点 8f55002)

既知類型との関係: 該当なし (lift/逆アセ系ではない)。`tools/startup/loadpaths/REPORT.md` §4 の表を `bootset/classify_bootset.py` の `RULES` に反映し、`bootset.json` / `BOOTSET.md` を**再生成**した (人手編集なし)。tier は引き続き**推定** (実トレースは #105)。

- **変更**: RULES の first-match 順で個別規則を包括規則の前に置いた (#1 `Help/*.scr` T0p / #2 `Artwork/Wallpapers/Default.txt` T0 / #3 `System/Languages/*.moe` T2・残りは T1 / #4 `StartSnd.wv` T0p / #5 Skins/Default の 5 件 T1 / #6 `System/Texts/*.txt` 直下 8 件は T0p 規則を削除して T1)。`BOOTSET.md` の自動生成ヘッダ (「人手編集禁止」) を生成元に取り込んだ (従来は人手追記だった)。
- **差分検査** `bootset/verify_tier_diff.py <変更前 bootset.json>`: 変更前の rules (8f55002) と新 `work/tiers.json` をファイル単位で比べ、表の 6 点と過不足なく一致することを検査 (不一致は exit 1)。
  実測: 差分 24 件 = #1 2 件 10949 B / #2 1 件 97 B / #3 7 件 6282124 B / #4 1 件 72076 B / #5 5 件 270952 B / #6 8 件 (1881 B)。表外の差分 0。T0 の byte 増減 -342931 (表の記載 -342931 と一致)。
  集計 (files / bytes): T0 142→137 / 2212908→1869977、T0p 258→253 / 5595646→5676790、T1 1700→1704 / 76414481→70394241、T2 24990→24996 / 1001026635→1007308662。X-* は無変更。
- **ネガティブコントロール**: (a) 期待表の #2 の新 tier を壊す → 検査 exit 1 (期待どおり検出)。(b) 規則 `Help/*.scr` を T1 に戻して再生成 → 検査 exit 1 (差分 22 件・期待 24 件) かつ再生成物がコミットと不一致 (`git diff --exit-code` exit 1)。
- **再現性**: 変更前の規則で再生成した `bootset.json` は旧ファイルとバイト一致 (入力の素材が同一であることの確認)。コミット済み HEAD 4c8f034 で n=3: 再生成 + 検査 + ネガコン + 生成物一致 2.94–2.98 秒 / load average 1.44–1.52 / 並列 1、全回 exit (検査 0・ネガコン 1・生成物差分 0)。
- **Actions 向け修正** (素材 `fl-win64` = installer + `extracted/` のみの環境): `block_manifest.json` / `pe_metadata.json` が素材に無いので `e2e.sh` が再構成する。`startup/loadpaths/mk_manifest.py` が `{idx, payload_off}` を作り (`recover_paths.py` の入力)、`inventory/mk_inputs.py <extracted> <out> <offsets.json>` が `{idx, path, kind, dsize, payload_off}` 入りの manifest と `pe_metadata.json` (PE 313 件 / x86 55 件) を作る (`recover_paths.py` と `inventory.py` の両方の入力)。`inventory.py` / `strings_scan.py` は `FL_WIN64_DIR` を読み、この経路では `inventory.py` の `summary.json` を `INVENTORY_SUMMARY_OUT` で `work/` に逃がす (tracked の `inventory/summary.json` を汚さない)。`e2e.sh` に検査・ネガコン・生成物一致を追加 (いずれも不合格なら exit 1)。
- **変更前の bootset.json**: 検査の入力は `bootset/bootset.pre592.json` (8f55002 の `bootset.json` と同一内容の固定ファイル)。`git show 8f55002:...` に依存しないので shallow clone でも動く。
- **クリーン work/ からの実測** (コミット済み HEAD 7647640 で再実行。`work/` を空にして素材 `fl-win64` のみ・`tsc` の手前まで = mk_manifest → mk_inputs → recover_paths → inventory → strings_scan → classify → 差分検査 → ネガコン → 生成物一致): n=3 で 12.35–13.48 秒 / load average 0.62–1.02 / 並列 1 / 全回 exit 0。以降は `tsc` が main 時点の既存不具合 (#637) で止まる (`node_modules/.bin/tsc` が無い環境では exit 127) ため、`pack` 以降 (node-test / browser-test / emscripten-test / asset-e2e) はこの経路では未到達。実行後の作業ツリーは clean (tracked ファイルの変更なし)。
- **既存 e2e の維持 (この run で実行できた範囲)**: `node test/node-test.ts` 15 項目 ALL PASS (1.38 秒) / `node test/browser-test.ts` 17 項目 ALL PASS (3.72 秒、Chrome)。pack は bootset の tier を入力にするため `work/pkg-small` を再生成して実行。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `e2e.sh` の `emscripten-test.ts` を未実行 (`toolchain-emsdk` 未取得) | 受入条件 2 (既存 e2e 維持) の一部が未検証 | #592 (`oc_artifacts: fl-win64 toolchain-emsdk` で再実行) |
| `e2e.sh` の `asset-e2e.ts` を未実行 (素材 k100 が許可素材に無い) | 同上 (tier 規則は触らないため影響は小さい。推定) | #592 (素材の置き場の確認は PM) |
| `tsc -p tsconfig.json --noEmit` が main 時点で exit 1 (`../../shared/paths.mjs` の型宣言なし・esbuild の解決不可) | `e2e.sh` が tsc で止まる (本 PR 由来ではない。origin/main の clean worktree で同じ 4 件を確認) | #637 [CI-12] |

## 12. 既存 e2e の維持 (#592 受入条件 2 / 検証 HEAD 1885bc03 / 2026-10-13 UTC)

PR #638 (規則反映) は merge 済み。検証は PR HEAD `1885bc03` の worktree (`ws-822`) で行った。
素材は `fl-win64` (`$ARTIFACTS_DIR/fl-win64.tar.zst`) を `$RUNNER_TEMP/fl-win64` に展開して `FL_WIN64_DIR` とした。
実行シェルは `TMPDIR=$RUNNER_TEMP`。`load` は `/proc/loadavg` の 1 分値 (開始→終了)。

| 段 | 結果 | 実測 | コマンド・日時 (UTC) |
|---|---|---|---|
| fl-win64 展開 | OK | 8.518 秒 / 25,166 件 / load 0.29→0.78 | `tar --zstd -xf fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` / 15:40:35 |
| 復元 → inventory → strings_scan → classify → 差分検査 → ネガコン → 生成物一致 | PASS (exit 0 まで。`e2e.sh` 35 行目の tsc で停止) | 11 秒 / load 0.81→0.92 | `bash tools/assets/e2e.sh` / 15:40:57 |
| `tsc -p tsconfig.json --noEmit` | exit 0 (`node_modules` の リンク時のみ) | 166 ms / load 0.52→0.52。`node_modules` 無しでは exit 1 (TS2688 `node` 型定義なし) | `../../node_modules/.bin/tsc -p tsconfig.json --noEmit` / 15:41:49 |
| `pack` (small) | OK | 2.941 秒 / load 0.47→0.52 | `node pack/pack.ts --only '^(Data/System/[^/]*$\|Artwork/\|System/Config/\|Data/Templates/Minimal/)' --out work/pkg-small` / 15:42:05 |
| `node-test` | ALL PASS | 1.327 秒 / load 0.44→0.80 | `node test/node-test.ts --pkg work/pkg-small --out work/results-node.json` / 15:42:23 |
| `browser-test` (Chrome) | ALL PASS | 4.119 秒 / load 0.70→0.70 | `node test/browser-test.ts --pkg work/pkg-small --out work/results-chrome.json` / 15:42:38 |
| `emscripten-test` | 実行済み (ALL PASS)。§13 | (§13 参照) | `node test/emscripten-test.ts` / §13 |
| `asset-e2e` | **未実行** | k100 (314 MB wasm 素材) が未配置 | (許可素材に無い) |

- 旧版 (origin/main 64d09590 / run 2) の値「展開 5.5 秒」は今回 8.5 秒と再現せず、本表の値で置き換えた。
- `node_modules` 無しの clean worktree では `e2e.sh` の tsc 段が落ちる (`node_modules` はルートの `pnpm i` が必要)。これは本 PR 由来ではなく、#637 の解消条件は「ルートの `node_modules` がある」こと。
- `node-test` は初回、`pack` と並列に起動したため manifest 未生成で失敗した (`latest.json` 不在)。直列で再実行して PASS。

未解決: asset-e2e (要 k100 の素材化、PM 判断) → #592。emscripten-test は §13 で解消 (`[EMSDK]` は runner 既存の emcc 6.0.12 を使用)。

## 13. emscripten-test の実行 (#592 受入条件 2 / 検証 HEAD 986e7415 / 2026-10-13 UTC)

§12 の「emscripten-test 未実行」を解消する。`[EMSDK]` は runner 既存の emcc 6.0.12 (`docs/REFERENCES.md` §4 の既定位置) を使った。`$ARTIFACTS_DIR/toolchain-emsdk.tar.zst` は展開していない (`emscripten-test.ts` が `[EMSDK]` の `emsdk_env.sh` を直接 source するため)。
素材は `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開し `FL_WIN64_DIR` とした。`TMPDIR=$RUNNER_TEMP`。`pnpm install --frozen-lockfile` は 0.35 秒で完了。

`bash tools/assets/e2e.sh` (既定サブセット) を 3 回。各回 asset-e2e の 1 段で停止するため rc=1 (既知: k100 不在)。

| run | 所要 | load (1 分値) 開始→終了 | node-test | emscripten-test | browser-test | asset-e2e |
|---|---|---|---|---|---|---|
| 1 | 12.384 秒 | 0.91→1.16 | ALL PASS | ALL PASS | ALL PASS | 未達 (`source wasm not found: tools/perf/work/huge/k100.wasm`) |
| 2 | 11.203 秒 | 1.16→1.21 | ALL PASS | ALL PASS | ALL PASS | 未達 (同) |
| 3 | 11.256 秒 | 1.21→1.16 | ALL PASS | ALL PASS | ALL PASS | 未達 (同) |

- 並列 1 (`e2e.sh` は直列)。ログは `tools/assets/work/e2e-n{1,2,3}.log` (gitignore)。
- 初回 run (`e2e-run4.log`) でも同じ順序で emscripten-test ALL PASS (`fread/fseek/ftell` で 8.86 MB ファイルの fnv 一致・`write denied`)。
- 前段の段ごとの exit code (ec06535e・素材 fl-win64 を `$RUNNER_TEMP/fl-win64` に展開して単独実行): mk_manifest 0 / mk_inputs 0 / recover_paths 0 / inventory 0 / strings_scan 0 / classify 0 / 差分検査 0 / ネガコン 1 (期待どおり FAIL を検出。`e2e.sh` は「ネガコンが通ったら FAIL」と判定) / 生成物差分 0。`tsc` も exit 0 (`node_modules` あり)。
- asset-e2e は未達のまま。k100 (314 MB) の素材化は PM 判断 (§5・§12 参照)。`oc_artifacts` の許可名に k100 を含む素材は無い。

## 環境パス置換 (#3831, 親 #294): /home/ubuntu 直書きを tools/shared 経由へ

- 対象: `tools/assets` (e2e.sh の PATH・bootset/strings_scan.py の WIN/MAC・inventory/inventory.py の `_WIN64`/`MAC_APP`)、`tools/audio/asio/e2e.sh`・`tools/hostbridge/hostbridge.sh` (PATH)、`tools/hostbridge/analysis/reproduce.sh` (素材パスを `FL_WIN64_DIR`/`PLUGINS_DIR` へ)、`tools/perf/build/ott_build.sh` (m6_build.sh を REPO 相対へ)・`tools/perf/report/env.sh` (PATH)、`tools/ott/f7eval/outhash_gate.sh` (`REPO_ROOT` 基準)、`tools/shared/lift/libkio/diff_test.py`・`tools/shared/run_all.sh`。
- 方式: 既定値の定義は `tools/shared/env.sh` / `paths.py` / `paths.mjs` のまま変えない。Python は `paths` を import、bash は `env.sh` を source。PATH の pnpm は `$HOME/.local/share/pnpm/bin` (既定の解決先は従来と同一)。
- 受入条件 1: 対象 code の `/home/ubuntu` 参照 → 0 件 (定義元 `env.sh`・`paths.*`・`test_paths.sh` を除く)。
- 既定値の同一性: env 未設定で `inventory.py` の `MAC_APP` を評価した結果は `origin/main` の従来文字列と一致。
- `bash tools/shared/test_paths.sh` → PASS default / analysis_dir_only / individual_override / negctl (4/4)。
- before/after (`tools/assets/e2e.sh`、`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`、`TMPDIR=$RUNNER_TEMP`、n=1 直列、load 0.19〜0.91): before (`origin/main`) rc=1 15 s、after (`7b7697efa`) rc=1 8 s。両者とも `ALL PASS` の後に `emcc: command not found` で停止し、結果は同一。差分は timing と readahead 実測値のみ。
- 未達: `tools/assets/e2e.sh` 全体は runner に emsdk (`/opt/emsdk`) が無いため完走しない。emscripten-test 以降は未検証。
