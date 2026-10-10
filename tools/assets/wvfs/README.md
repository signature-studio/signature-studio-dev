# wvfs — 書込可能 VFS (RT-5 / CAB-123)

`/c/home`・`/c/tmp` を **OPFS バッキングの書込可能 mount** として実装する。CAB-21 の読取系
LazyVfs (`../vfs`, `/fl` mount) とは独立したモジュールで、mount 点でのみ共存する。
設計・契約・制限の正本は **`REPORT.md`**。

## 構成

| パス | 内容 |
|---|---|
| `journal.ts` | 物理層: SyncFile (OPFS SyncAccessHandle / node fd) 上のアペンドジャーナル + A/B スーパーブロック。torn-write 安全 (CAB-21 規約「データ→commit」順序を踏襲) |
| `wvfs.ts` | 論理層: case-insensitive パスツリー + 同期 file API + flush 契約 (`onYield()` / `onPageHide()` / `sync()`) |
| `backend-opfs.ts` | OPFS バックエンド (Worker 限定) |
| `backend-node.ts` | node fs バックエンド (単体テスト / node Emscripten probe 用) |
| `emscripten-wvfs.ts` | Emscripten FS アダプタ (書込可)。`FS.syncfs` 対応 (`mount.type.syncfs`) |
| `pathlink.ts` | pathreg (`tools/shimx/pathreg/js/pathmap.mjs`, 読取専用参照) の写像 → home/tmp 振り分け |
| `test/` | node 単体 (64 checks) / Emscripten adapter probe (emcc, node) / Chrome OPFS e2e |
| `scripts/e2e.sh` | 1 コマンド検収 |

## 検収

```sh
bash tools/assets/wvfs/scripts/e2e.sh [--fresh]   # node 単体 → emcc probe → Chrome OPFS e2e (3 起動)
```

Chrome e2e は**実ディスクプロファイル** (`wvfs/work/chrome-profiles/`, gitignore) を使う。
tmpfs プロファイルでは OPFS SyncAccessHandle 書込が壊れる実績あり (CAB-21 REPORT §3)。

## 使い方 (CAB-216 / CAB-101 結線イメージ)

```ts
import { Wvfs, OpfsBackend, createPathRouter, createWvfsFs, storeDir } from '.../wvfs/index.ts';

const home = await Wvfs.open(new OpfsBackend(storeDir('home')));   // OPFS: fl-wvfs/home
const tmp  = await Wvfs.open(new OpfsBackend(storeDir('tmp')));
FS.mkdir('/c/home'); FS.mount(createWvfsFs(FS, home, { stores: [home, tmp] }), {}, '/c/home');
FS.mkdir('/c/tmp');  FS.mount(createWvfsFs(FS, tmp,  { stores: [home, tmp] }), {}, '/c/tmp');

const router = createPathRouter();                                 // pathreg 既定マウント表
const r = router.route('C:\\Users\\user\\Documents\\Image-Line\\...\\OTT.fst');
// → { mount: 'home', path: '/Documents/Image-Line/.../OTT.fst' }
stores[r.mount].mkdirpSync(dirname(r.path));
stores[r.mount].writeFileSync(r.path, bytes);

// flush 契約 (vreg / RegBridge と同一インタフェース名):
//   メッセージポンプの yield 点で home.onYield() / tmp.onYield()
//   pagehide・visibilitychange(vhidden) で home.onPageHide() / tmp.onPageHide()
//   もしくは FS.syncfs(false, cb) (全 wvfs mount をまとめて flush)
```
