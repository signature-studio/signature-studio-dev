# REPORT — CAB-123 (RT-5): 書込可能 OPFS VFS (`/c/home`・`/c/tmp`)

日付: 2026-10-10 / 関連: CAB-21 (asset-vfs, In Review) / CAB-168 (pathreg, In Review) / CAB-94 (vreg) / CAB-98 (nfo)
書込範囲: `tools/assets/wvfs/` (新規) + `tools/assets/tsconfig.json` (include に "wvfs" 追加の 1 行) + `tools/assets/REPORT.md` (§9 の追記のみ)。既存ファイルの動作変更は 0。
検収: **`bash tools/assets/wvfs/scripts/e2e.sh` → exit 0** (node 単体 64 checks → emcc probe 8 checks → Chrome OPFS e2e 3 起動 18 checks, 実測 約 100 秒)。既存 `tsc -p tsconfig.json --noEmit` も PASS。

## 0. 結論 (数値は全て実測)

1. **`/c/home`・`/c/tmp` を OPFS バッキングの書込可能 mount として実装し、Chrome 154 (実ディスクプロファイル) で「書込 → flush → プロセス再起動 → 読取一致」を実証した**。
   実装は **アペンドジャーナル型ストア** (1 mount = 1 ジャーナルファイル + A/B スーパーブロック)。
   seed 7 ファイル (Settings/Manifest.xml, Plugin database の OTT.fst/OTT.nfo/VerifiedIDs.nfo, Roaming config.xml, tmp 256KiB bin, fd 部分書込ファイル) が
   **SIGKILL を跨いで全件 sha256 一致** (run1 seed → run2 verify: mismatches=0)。
2. **torn-write 安全は CAB-21 の OPFS 実装規約 (「payload を先に書き、commit を後に書く」) を踏襲**。
   レコード = `[recLen][crc32][seq][op][pathLen][dataLen][mtime][path][data]` を flush し、再生時に
   recLen/crc 検証で最終不完全レコードを捨てる。e2e で (a) 末尾書きかけ注入 → 復元 (logicalEnd 巻き戻し確認),
   (b) 中間レコード 1 バイト破壊 → 以降を捨てて以前の state を保持, の両方を実測した (Chrome e2e + node 単体)。
3. **flush 契約は pathreg RegBridge と同一インタフェース名** (`onYield()` / `onPageHide()`)。
   ジャーナル append は物理 flush しない → 明示 flush 点 (onYield / onPageHide / `sync()` / `fsync(fd)` / close) で
   flush する。**FS.syncfs 相当口**として Emscripten `mount.type.syncfs(mount, populate, cb)` を実装し、
   `FS.syncfs(false, cb)` で全 wvfs mount をまとめて flush 可 (node 実機 probe で PASS)。
   Chrome e2e では fd を close せず `onPageHide()` のみで SIGKILL を跨いだ永続を実証 (flush 点契約の実機確認)。
4. **pathreg 整合 (JS 契約)**: `pathlink.ts` が pathreg JS ミラー (`tools/shimx/pathreg/js/pathmap.mjs`, 読取専用 import) を使い、
   既定マウント表どおり Win パス → `/c/home/**` (PERSIST) / `/c/tmp` (TMP) に振り分ける。
   node 単体で pathreg e2e と同一の 15 fixture の経路分類 15/15 一致 + Plugin database 配置パスへの
   ダミー .fst 書込/大小無し再読みを検証。**境界: C 側 `shimx_set_path_mapper` の実呼出検証は未実施**
   (pathreg REPORT §2.3 の C↔JS 15 fixture 全件一致を前提に JS 側契約のみ検証。C 実機結合は CAB-101)。
5. **quota 限界時の挙動**: `QuotaExceededError` → `WvfsError('ENOSPC')` 変換、部分書込 (レコード半分で死ぬ) は
   torn tail として次回起動に復元、dirty は保持されて再試行可能 (node 単体で実測)。
   単一ファイル上限超過は `EFBIG` (既定 128MiB, 変更可)。実 quota は e2e で
   `navigator.storage.estimate()` = quota 10,741,613,654 B / usage 4,195,414 B を報告 (実ディスク計測)。

## 1. 設計

```
Wvfs (wvfs.ts)                          Journal (journal.ts)                SyncFile
  case-insensitive tree (Map)             4KiB header + アペンドレコード        OPFS SyncAccessHandle (Worker)
  fd = 共有書込 buffer (同一パスで相互可視)   [recLen][crc][seq][op]...            / node fd (単体テスト)
  read = ジャーナル直読み (メモリは index のみ)  A/B superblock (root 4KiB)
  flush 契約: onYield / onPageHide        compaction (生存 set で新 journal)
```

- **ジャーナル = そのまま記憶域**: ファイル本文はジャーナル内の固定位置に置き、読み出しは
  SyncAccessHandle の同期 read でジャーナル直読みする (メモリには index のみ。CAB-21 の
  SlotCache と同方針の「メモリ非依存」設計)。open 中 fd の書込はメモリ buffer (同一パスの fd 間で
  共有 = MEMFS の node.contents 相当)、close/flush 点で PUT レコード化。
- **レイアウト (OPFS)**: `fl-wvfs/<mount>/root` (スーパーブロック 4KiB = 2KiB×2 スロット) と
  `fl-wvfs/<mount>/jrn-<id>.bin` (4KiB ヘッダ + レコード列)。スロット = `[magic 'WVS1'][ver][gen][journalId][crc32]`。
- **compaction**: 生存レコード (明示 dir + file) だけの新ジャーナル `jrn-<id+1>.bin` を書き切って
  flush → スーパーブロックを **2 回 commit** (両スロットとも新 journalId に更新) → 旧ジャーナル削除。
  しきい値: `used > max(4MiB, 4×liveBytes + 1MiB)`。実測: 5,254,587 B → 137,276 B (40×128KiB churn)。
  単一スロット破損時の fallback が「削除済み旧ジャーナル」を指さないよう、起動時に
  `backend.exists()` でジャーナル実在を確認し、無ければ他スロット/新規へ落ちる (node 単体で回帰試験済み)。
- **case-insensitive**: エントリは元ケースのパスを保持し、比較のみ lower (`Win32` 相当)。
  readdir は元ケースを返す (LazyVfs manifest tree の lookup 方針と同一)。
- **セマンティクス**: POSIX 風 (親無し open は ENOENT / mkdir EEXIST / rmdir ENOTEMPTY /
  unlink 後の open fd 書込は捨てて復活させない / O_APPEND / ftruncate / fsync / rename (dir 越境チェック付き)。
  暗黙 dir は最後のファイル削除で刈り込み、明示 `mkdir` された dir は永続。

## 2. Emscripten 結合 (`emscripten-wvfs.ts`)

- `createWvfsFs(FS, wvfs, {stores})` → `FS.mount(..., '/c/home')`。読取系 `createEmscriptenFs`
  (vfs/emscripten.ts, /fl) と**同一パターン**で node_ops/stream_ops を実装し、既存 mount と共存する
  (node 実機 probe で /fl=MEMFS と /c/home・/c/tmp=Wvfs の 3 mount 共存 + C stdio 読み書きを実測)。
- lookup は case-insensitive 解決 (既存エントリの元ケースへ正規化)。O_CREAT/O_TRUNC/O_EXCL は
  FS コアが処理するので、adapter は mknod (空ファイル作成+ジャーナル即 PUT) / setattr (truncate/utimes) /
  append を受ける。mmap は未実装 (FS コアの汎用 fallback 経路 = read に落ちる)。
- **`mount.type.syncfs(mount, populate, cb)` 実装**: `populate=false` で `stores[].sync()`
  (= dirty fd → ジャーナル → 物理 flush)。`FS.syncfs(false, cb)` の契約どおり errCode コールバック。

## 3. e2e 実測 (`wvfs/test/wvfs-e2e.ts`, Chrome 154 headless, 実ディスクプロファイル使い回し 3 起動)

| run | 内容 | 実測 |
|---|---|---|
| seed | pathreg 経路で 7 ファイル (writeFileSync 5 + fd 部分書込 1 + tmp bin) → `onYield()`/`onPageHide()` のみで flush → SIGKILL | files=7 / caseOk / journal home 6,654 B (6 files + 16 dirs) / tmp 266,396 B (256KiB 本体 + 頭 4.3KB) |
| verify | **別プロセス**で全件 sha256 照合 → torn 注入 → slot 破壊 → compaction → 再 open | mismatches=**0** / torn detected=1, state intact / slot 復旧 (journal 存続) / compaction 5,254,587→137,276 B, churn+plugin db 無傷 |
| verify2 | compaction 後の**別プロセス**で再照合 | mismatches=**0** / active journal id=2 |

- storage.estimate (実ディスク): quota 10,741,613,654 B / usage 4,195,414 B (seed 直後)。
- node 単体 (64 checks): 基本 CRUD / case-insensitive / unicode パス / fd (部分書込・append・fsync・unlink-while-open) /
  flush 契約 (clean 時 onYield は no-op) / torn tail 2 種 / superblock A/B (片側破壊・両側破壊・resurrection・全壊) /
  EFBIG・ENOSPC (QuotaExceededError 変換・部分書込・再試行) / compaction / pathreg 15 fixture。
- Emscripten adapter probe (emcc 6.0.12, node): C stdio で `/fl` (MEMFS 共存) 読み・`/c/home` 書込+読戻し・
  `/c/tmp` バイナリ書込・JS 書込ファイルの読み・`FS.syncfs(false)` → reload 後の永続 8 checks。

## 4. 契約まとめ (下流結線用)

| 項目 | 契約 |
|---|---|
| mount 点 | `/c/home` = `OpfsBackend('fl-wvfs/home')`、`/c/tmp` = `OpfsBackend('fl-wvfs/tmp')` (dir 名は `storeDir()`) |
| flush 点 | ポンプ yield 点で `onYield()` (Promise を返したら await 推奨 / compaction を兼ねる)、`pagehide`+`visibilitychange(vhidden)` で `onPageHide()`。`FS.syncfs(false, cb)` でも可 |
| 永続単位 | flush 点までの全確定書込 (fd 未 close 分を含む)。flush 点前に死ぬと未 flush 分は失われる (vreg と同一) |
| エラー | ENOSPC (quota) / EBUSY (同一 store の二重 open = OPFS 単一 writer) / EFBIG (128MiB/ファイル) / EIO (short read/write) |
| 制限 | 書込対象は `/c/home/**` と `/c/tmp`。`/c` 直下・`D:\` 等は対象外 (pathreg の mapRaw で glue が判断) |

## 5. 制限・既知事項

1. **Chrome 154 のみ実測** (headless)。Firefox/Safari は OPFS SyncAccessHandle 非対応 or 部分対応のため
   未検証 (worker 限定 API のため main thread では動かない = E 側構成は Worker 前提)。
2. **tmpfs プロファイル禁止** (CAB-21 REPORT §3 の実績を継承)。e2e は `wvfs/work/chrome-profiles/` 固定。
3. **単一 writer**: 同一 store の二重 open は OPFS の SyncAccessHandle 排他で EBUSY。FL は単一 Worker 前提。
4. **大ファイル**: 単一ファイル上限 128MiB (ジャーナル 1 レコード = 1 ファイル全体のため)。それ以上は
   chunk 化 (CAB-21 の asset 経路) か上限引き上げが必要。fd 書込中の buffer はファイル全体をメモリに持つ
   (MEMFS 同等。256KiB e2e 実測の他、/c/tmp への大径 render 出力はこの上限とメモリに従属)。
5. **flush 前喪失**: プロセス強制終了時、最後の flush 点以降の書込は失われる (契約)。vreg・RegBridge と同一。
6. **mtime は JS 時刻** (Win32 timestamp の厳密再現はしない。FL が timestamp を比較検査する経路は未確認)。
7. **C 側 pathreg 実呼出は未検証** (§0-4 の境界)。`shimx_path_mapper_fn` への登録は CAB-101。
8. ジャーナル肥大は compaction で対処するが、compaction 中の書込は一時的に 2 ジャーナル分の容量を使う。

## 6. CAB-216 (generateDb → 仮想 FS 結線) への引き継ぎ

1. `generateDb()` の出力 (path → bytes の Map) は `pathreg` 既定表の `Shared data` 配下 =
   **`/c/home/Documents/Image-Line/...` へ `createPathRouter().route()` 経由で書く**。
   e2e の seed が同一経路 (`OTT.fst` / `OTT.nfo` / `VerifiedIDs.nfo` を含む Plugin database ツリー) を
   実証済み → generateDb の結合は「Map を回して mkdirp+writeFileSync」だけで良い。
   本チケットの .fst はダミーバイト (nfo writer は未呼出)。差し替え = 1 ファイル。
2. 書込後の永続は `home.onYield()` (ポンプ yield 点) + `home.onPageHide()` (pagehide)。vreg の
   `Vreg.flush()` / RegBridge と**同一呼出点**で並列に呼んで良い (独立 store なので競合しない)。
3. `.Plugins.ini` / VerifiedIDs.nfo も同一経路。FL 側の case 無視 lookup は wvfs が吸収する
   (元ケース保持 + 比較 lower)。
4. `/c/tmp` は CAB-168 §2.2 の `<profile>\AppData\Local\Temp\Image-Line` 写像先。S18 の一時 dir 作成は
   `tmp.mkdirpSync()` で可能 (e2e 実測済み)。

## 7. ユーザ依頼事項

なし。

## 8. 次タスク提案 (下流チケット案)

1. **CAB-101 (実FL結線)**: pathreg の `shimx_set_path_mapper` 実登録 + `/fl` (LazyVfs)・`/c/home`・`/c/tmp`
   (本 wvfs) を同一 module に mount し、`CreateFileW` の読み書きが正しい実体に届くことを SHIMX_TRACE で確認。
2. **CAB-216 (Plugin database 生成)**: `generateDb()` 出力を §6-1 の経路で書込 + 起動時に 1 回実行
   (存在判定つき) して FL の Plugin Manager 走査代替とする。
3. **レジストリとの一括 flush 点**: RegBridge (`onYield`/`onPageHide`) と wvfs を同じ pump hook に束ねる
   glue (vreg REPORT §8-1 の T6 接続と同一箇所)。flush 順序の規約 (どちらも独立 flush で良い) を明記。
4. **quota 管理**: `storage.estimate()` 監視と eviction ポリシー (fl-assets キャッシュとの合算上限)。
   CAB-21 REPORT §8-4 の quota 管理チケットに本 mount 分を加算する形。

## 9. 規約遵守メモ

- コミット: `feat(assets): writable opfs vfs (RT-5)` / 追加は `tools/assets/wvfs/` + `tsconfig.json` 1 行 +
  `tools/assets/REPORT.md` §9 追記のみ (`wvfs/work/` は gitignore 済)。20MB 超 blob なし (最大 = e2e 結果 JSON 数百 KB)。
- 再現: `bash tools/assets/wvfs/scripts/e2e.sh` (約 100 秒, exit 0)。環境: node v26.10.0 / emcc 6.0.12 / Chrome 154 headless。
