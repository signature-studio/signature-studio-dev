# CAB-21 asset-vfs — 引継ぎ完了レポート (314MB 級 wasm asset の chunk ローダ + 二段キャッシュ)

実施 2026-10-10 / node v26.10.0 / Chrome 154 headless (実ディスクプロファイル) / 検証 `bash tools/assets/e2e.sh --full` (exit 0)。

## 1. 結論

- **前担当残骸 (tools/assets/, コミット 0 件) は全面採用**。VFS 本体 (manifest v1 / pack / LazyVfs / SlotCache(OPFS) / SabLoader / Emscripten FS) は修正 1 行も不要で node/Chrome 実測 ALL PASS。壊れていたのは**テストハーネス側 3 点**のみで修正した (§3)。
- チケット要件の未実装部分「**manifest→chunk 取得→連結→compileStreaming→キャッシュ (IDB/OPFS)**」を `vfs/asset.ts` + `vfs/idb.ts` として新規実装し、**314,206,140 byte の wasm (tools/perf/work/huge/k100.wasm, exports 8271) で 4 シナリオ e2e 全 PASS** (§5)。
- キャッシュは **L1=IndexedDB (bytes のみ保存, Module は保存しない) / L2=OPFS SyncAccessHandle** の二段。破損検出は **chunk 単位 sha256 (内容アドレス id) を毎読み照合**し、破損 chunk だけ他 tier / network から再取得して部分修復する (§4)。
- **deploy/client/chunked.mjs との統合判断: ストリーミング契約は同一形に寄せ、実装は統合せず E 側に置く** (理由と統合経路は §6)。

## 2. 前担当残骸の評価 (採用/放棄)

| 資産 | 判断 | 根拠 (再検証実測) |
|---|---|---|
| `vfs/` (manifest/path/codec/lazy-vfs/cache/opfs/sab/loader/http-source/emscripten/node-file) | **採用 (無改修)** | `tsc` OK, node 結合テスト ALL PASS (227 ファイル照会 sha256 一致, restart で 234 slot 復元) |
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

- 破損検出の単位: **chunk id = 非圧縮 chunk の sha256 先頭 128bit** (manifest の内容アドレスと同じ)。OPFS 読み出し毎に照合する (314MB 全量で約 1s, pass2 実測 923–1229ms を参照)。asset 全体の sha256 一致は e2e が別途全バイト再読みで検証した (`shaOk`)。
- OPFS header の bitmap は payload 書込**後に**立てるので torn write 安全。未書込 chunk は読まずに次 tier へ落ちる (再開時の無駄読みなし)。bitmap は 64..4095 バイト = 最大 32,256 chunk (32GiB @1MiB)。
- **IDB に Module を保存しない理由**: 保存対象は bytes のみ。Module の構造化複製は可能だが Chrome 固有最適化に寄せると、chunk id による照合・部分修復・他 tier との整合が bytes 単位で保てなくなるため (設計決定)。
- 保存完了の成否は `done` (ストリーム消費完了 → 全 IDB put 完了 → meta 書込) で保証し、compileStreaming 成功後に await する。

## 5. e2e 実測 (`node test/asset-e2e.ts`, 4 起動で OPFS/IDB を跨ぐ, 1 シナリオ = Chrome 1 起動 + ロングポール 1 本)

asset: `Engine/FLEngine.wasm` = k100.wasm 314,206,140B / 300 chunk (br, 125.8MB 格納) / 期待 sha256 `0f31f2df…`

| シナリオ | network | chunk 取得内訳 | compileStreaming | 全体 sha256 | tier 復元 |
|---|---|---|---|---|---|
| cold (net ON) | 300/300 req, 314.2MB | opfs 0 / idb 0 / net 300 | **4.7–7.7s** (3 回, --full 同時実行時は 13.3s) | 一致 | OPFS 314,210,236B + IDB meta 保存 |
| warm-netoff (net OFF) | **0 req** (server chunk request 0) | opfs 300 | **1.06–1.28s** | 一致 | OPFS 読み 300 |
| corrupt-opfs (net OFF) | 0 req | opfs 299 / **idb 1 (修復)**, 破損検出 1 | 1.10–1.29s | 一致 | OPFS 自動修復 (opfsWrites 1) |
| corrupt-both (net ON) | **1 req (1MiB のみ再取得)** | opfs 299 / net 1, 破損検出 2 (opfs+idb) | 1.16–2.17s | 一致 | 両 tier 修復 (opfsWrites 1 / idbWrites 1) |

- exports 8271 / imports 3 を返し、**CAB-61 が Worker 内実測した同 wasm の exports 数 8271 と一致**。
- キャッシュ全読み + 全量 sha256 検証 (pass2) は **0.89–1.23s (約 255–350 MB/s, per-chunk sha256 検証込み)**。
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
