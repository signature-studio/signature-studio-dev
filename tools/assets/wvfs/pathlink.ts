// pathlink.ts — pathreg (tools/shimx/pathreg, 読取専用参照) の JS ミラー写像と Wvfs mount の結合。
//
// pathreg の既定マウント表 (REPORT §2.2) は Win パス → /fl (RO asset) | /c/home/** (PERSIST) | /c/tmp (TMP)
// へ写像する。本モジュールはそのうち書込対象 (/c/home, /c/tmp) を Wvfs (OPFS ジャーナル) に振り分ける。
//
//   const router = createPathRouter();
//   const home = await Wvfs.open(new OpfsBackend('fl-wvfs/home'));
//   const r = router.route('C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml');
//   // → { mount: 'home', path: '/Documents/Image-Line/FL Studio/Settings/Manifest.xml' }
//   home.mkdirpSync(dirname(r.path)); home.writeFileSync(r.path, bytes);
//
// 境界: C 側 shimx_set_path_mapper への実呼出検証は本チケットの範囲外 (JS 側契約のみ)。
// pathmap.mjs は pathreg e2e の 15 fixture で C 実装と全件一致済み (pathreg REPORT §2.3)。
// @ts-expect-error — pathmap.mjs は JS 実装 (型定義無し)。読取専用参照 (tools/shimx/pathreg は無変更)
import { createMapper } from '../../shimx/pathreg/js/pathmap.mjs';

export const HOME_MOUNT = '/c/home';
export const TMP_MOUNT = '/c/tmp';
export const WVFS_ROOT = 'fl-wvfs'; // OPFS 内のコンテナ dir (配下に home/ tmp/)

export type WvfsMountName = 'home' | 'tmp';

export interface Route {
  mount: WvfsMountName;
  /** mount ルート (/c/home or /c/tmp) 基準の絶対パス */
  path: string;
}

export interface PathRouter {
  /** Win パス → 書込先 (非対応 / 対象外は null。/fl など RO asset や /c 直下は対象外) */
  route(winPath: string): Route | null;
  /** 対象外を含む写像の生値 (pathreg mapper の結果。診断用) */
  mapRaw(winPath: string): string | null;
  mounts: { home: string; tmp: string };
}

export function createPathRouter(opts: { home?: string; tmp?: string } = {}): PathRouter {
  const mapper = createMapper();
  const home = (opts.home ?? HOME_MOUNT).replace(/\/+$/, '');
  const tmp = (opts.tmp ?? TMP_MOUNT).replace(/\/+$/, '');
  const pick = (t: string): Route | null => {
    if (t === home || t.startsWith(home + '/')) return { mount: 'home', path: t.slice(home.length) || '/' };
    if (t === tmp || t.startsWith(tmp + '/')) return { mount: 'tmp', path: t.slice(tmp.length) || '/' };
    return null;
  };
  return {
    route: (winPath) => {
      const t = mapper.map(winPath);
      return t ? pick(t) : null;
    },
    mapRaw: (winPath) => mapper.map(winPath),
    mounts: { home, tmp },
  };
}

/** OPFS コンテナ dir 名 (mount 名から) */
export function storeDir(mount: WvfsMountName, root = WVFS_ROOT): string {
  return `${root}/${mount}`;
}
