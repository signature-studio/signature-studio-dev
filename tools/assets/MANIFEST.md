# asset manifest v1 / R2 レイアウト仕様

実装: 生成 `pack/pack.ts` / 型 `vfs/types.ts` / 読取 `vfs/manifest.ts`。

## オブジェクトキー (R2 バケット直下)

| key | 内容 | Content-Encoding | Cache-Control |
|---|---|---|---|
| `c/<id[0:2]>/<id>.raw` | chunk そのまま (圧縮が効かない/しない) | なし | `public, max-age=31536000, immutable` |
| `c/<id[0:2]>/<id>.br`  | chunk を brotli (q11, lgwin22) | `br` | 同上 |
| `c/<id[0:2]>/<id>.zst` | chunk を zstd (`--codec zstd`) | `zstd` | 同上 |
| `m/<sha16>.json` | manifest (JSON を brotli) | `br` | 同上 (内容アドレス) |
| `latest.json` | `{manifest:"m/<sha16>.json", usize, size, chunkSize, created}` | なし | `public, max-age=60, stale-while-revalidate=600` |

- `id` = 非圧縮 chunk の SHA-256 先頭 128bit (hex 32 桁)。**内容アドレス = 世代間で同一内容は同一キー** (FL 更新時に未変更 chunk は再アップロード不要・クライアント OPFS キャッシュも再利用)。
- Content-Type は全て `application/octet-stream` (manifest/latest は `application/json`)。`Content-Encoding` を付けるので **ブラウザの fetch / sync XHR がネイティブ復号**する (JS/wasm 側のデコーダ不要)。Range は使わない (Content-Encoding 付きオブジェクトでは範囲がエンコード後バイト列になるため)。
- 手動復号フォールバック: `Content-Encoding` が付かない環境では `vfs/codec.ts` の `registerDecoders()` で br/zstd デコーダ(wasm 等)を注入する。

## 配信側の要件 (M12 ホスティング)

- COOP/COEP (`same-origin` / `require-corp`) はアプリ側オリジン。chunk を別オリジン (R2 カスタムドメイン) から取る場合、そのレスポンスに `Cross-Origin-Resource-Policy: cross-origin` と `Access-Control-Allow-Origin: *` が必要 (Transform Rules で付与)。headless Chrome で cross-origin 構成を検証済み (test/browser-test.ts: app=:A, chunk=:B)。
- `latest.json` のみ短 TTL。他はすべて immutable。

## manifest.json

```jsonc
{
  "v": 1,
  "name": "fl-studio-26.1.7.5653-win64",
  "created": "ISO8601",
  "chunkSize": 1048576,          // 論理 chunk の最大サイズ (非圧縮)
  "smallMax": 131072,            // これ以下のファイルは pack chunk に同居
  "layout": "objects",
  "chunks": {                    // 列指向。index = chunk 番号
    "n": 2009,
    "id": "<32hex x n を連結>",
    "u": [..],                   // 非圧縮サイズ
    "c": [..],                   // 格納サイズ
    "k": [..]                    // 0=raw 1=br 2=zstd
  },
  "groups": { "T0": [[0,5]], "T0p": [[5,17]], "T1": [[22,66]], "T2": [[88,1921]] },  // 優先度別の連続 chunk 範囲 [first,count]
  "tree": { "Data": { "System": { "Empty.flp": [46361, 3, 81920] }, ... } },          // 大小保持、lookup は大小無視
  "stats": { ... }
}
```

ファイル葉 `[size, first, off, flags?]`:
- `size=0` → `[0]`
- pack (小ファイル): `off>=0` → chunk `first` の `off` から `size` バイト (1 chunk に収まる)
- 大ファイル: `off=-1` → chunk `first`.. `first+ceil(size/chunkSize)-1` が連続 (最後以外は chunkSize ちょうど)
- `flags & 1` = **stub** (wasm 化/再ビルド対象バイナリ。ディレクトリ列挙・`GetFileSize` 用に size のみ載せ、読むと `ESTUB`)。インストーラ内部/非実行バイナリ (x86, installer, WebView2 等) はそもそも載せない。

## パッキング規則 (`pack/pack.ts`)

1. 内容 SHA-256 で重複除去 (同一内容の複数配置は同一葉を共有)。
2. 並び順 = (tier, 大ファイルか, path 小文字)。tier は `bootset/classify_bootset.py` が出力する `work/tiers.json` (推定 tier の内訳と根拠は **自動生成** `bootset/BOOTSET.md`)。**同 tier の小ファイルが連続して同じ pack chunk に入り、ブート chunk 群が連続範囲 (groups.T0/T0p) になる**。
3. 小ファイル (≤128KiB) は同 tier 内で 1MiB まで pack。tier が変わるたび flush。大ファイルは 1MiB 毎に専用 chunk。
4. 圧縮: 拡張子で不可能なもの (wv/flac/ogg/mp3/png/jpg/zip) は raw。256KiB 超は先頭 64KiB を br q3 で試し >98.5% なら raw。本圧縮後に >97% なら raw。
5. chunk 内容ハッシュが既出なら再書き込みしない (`stats.dedupeSavedUsize`)。

## VFS ランタイム (`vfs/`)

| 層 | 実装 | 備考 |
|---|---|---|
| 名前空間 | `ManifestIndex` (大小無視 lookup, `normalizePath` が `C:\...\FL Studio 2026\` を剥がす) | tree は JSON のまま lazy に lowercase index |
| 同期 read | `LazyVfs.readSync(fd,buf,off,len,pos)` | stub は `ESTUB` |
| L1 | メモリ LRU 8 chunk | 小ファイル連続 read |
| L2 | `SlotCache` (OPFS SyncAccessHandle / node fd) | 固定 slot=4KiB header+1MiB、header に id/len/sum/valid → 再起動時スキャンで復元 (別 index 不要)。LRU、pin (ブートセット) |
| L3 | `SabLoader`: fetcher Worker が fetch+復号 → SAB slab → `Atomics.wait` で同期化 | 16 slot (16MiB)、先読みは空き ≥3 枠のときだけ |
| fallback | `SyncXhrLoader` (Worker 内 sync XHR) | SAB/COOP-COEP 無し環境 |
| 先読み | 連続検出 (2^seq, 最大 8 chunk)、≤4chunk の大ファイルは初回丸ごと、`preload(group)` で優先群を並列取得 | |
| Emscripten | `vfs/emscripten.ts` `createEmscriptenFs(FS, vfs)` (読取専用 FS.mount) | |

## 大物 asset の単体ローダ (`vfs/asset.ts`)

1 ファイル (314MB 級 wasm 等) を manifest の連続 chunk として取得 → 連結 ReadableStream → `WebAssembly.compileStreaming` に渡す経路。chunk 解決は **L2 OPFS (`fl-assets/<keyHash>.bin`, 4KiB header + bitmap + 固定配置) → L1 IndexedDB (`fl-assets-v1`, parts/${keyHash}/${i} = bytes, Module は保存しない) → network** の順。読み出し毎に chunk id (sha256 128bit) を照合し、不一致 chunk だけ他 tier / network から再取得して部分修復する。詳細と実測は `REPORT.md` §4-6。
