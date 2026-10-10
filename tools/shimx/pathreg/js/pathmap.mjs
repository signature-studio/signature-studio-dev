// pathmap.mjs — pathmap.c (C 参照実装) の JS ミラー。
//   用途: ランタイム glue (CAB-101) が wasm 起動前に「どこに書けば C 側から見えるか」を計算する / テストで C と突合する。
//   規則は include/pathreg.h の既定表と 1:1 (e2e.mjs が C↔JS の一致を全 fixture で検査する)。
//
//   正規化: '/'→'\'、\\?\ / \\.\ / \\?\UNC 剥がし、ドライブレター大文字化、連続区切り圧縮、'.' '..' 畳み込み、末尾 '\' 除去 ("C:\" は保持)
//   写像:   マウント表を大小無視・最長一致 (同長は後勝ち) で照合 → vfsTarget + 残り ('/' 区切り)。
//           非対応 (Win 形絶対パスで無い / 表に無い) は null を返す = shimx 既定写像 (C:\x→/c/x) に委譲。

export const FLAG_RO = 1;
export const FLAG_PERSIST = 2;
export const FLAG_TMP = 4;

/** stub_plan §4 / vreg seed paths / shimx SHGetFolderPathW・env 既定に整合する既定設定 */
export const DEFAULT_PATHS = {
  installDir: 'C:\\Program Files\\Image-Line\\FL Studio 2026',
  vfsInstall: '/fl',
  userProfile: 'C:\\Users\\user',            // shimx SHGetFolderPathW / env と一致
  user2Profile: 'C:\\Users\\webstudio',      // vreg seed "Shared data" 値 (推定)
  vfsHome: '/c/home',
  sharedDataDir: null,                       // null = <profile>\Documents\Image-Line
  vfsSharedData: '/c/home/Documents/Image-Line',
  vfsTmp: '/c/tmp',
};

/** Win パスを正準化する。戻りは Win 形 ('\ '区切り) の文字列。
 *  形: UNC "\\srv\share\..." / ドライブ "C:\..." / ルート付き "\foo" (入力が '\\' 始まり) / 相対 "foo\bar"。
 *  ".." が根を超える場合は無視 (Win32 相当)。pathmap.c pr_canonicalize と同じ結果 */
export function normalizeWinPath(p) {
  if (typeof p !== 'string' || p === '') return null;
  let s = p.replaceAll('/', '\\');
  let unc = false;
  if (s.startsWith('\\\\?\\') || s.startsWith('\\\\.\\')) {
    s = s.slice(4);
    if (/^UNC\\/i.test(s)) { s = s.slice(4); unc = true; }
  }
  if (!unc) unc = s.startsWith('\\\\');
  if (unc && s.startsWith('\\\\')) s = s.slice(2);
  const rooted = unc || s.startsWith('\\');
  const lead = unc ? '\\\\' : rooted ? '\\' : '';
  const segs = [];
  const floor = () => (segs.length && /^[a-zA-Z]:$/.test(segs[0]) && !unc ? 1 : 0);  // ドライブ表記は根 (pop 越境防止)
  for (const raw of s.split('\\')) {
    if (raw === '' || raw === '.') continue;
    if (raw === '..') { if (segs.length > floor()) segs.pop(); continue; }
    segs.push(raw);
  }
  let r = lead + segs.join('\\');
  if (/^[a-zA-Z]:$/.test(r)) r += '\\';
  else if (/^[a-zA-Z]:/.test(r)) r = r[0].toUpperCase() + r.slice(1);
  return r;
}

/** 既定マウント表を構築する (pathmap.c pr_add_user_mounts と同じ順序・内容)。mounts = [{win,target,flags}] */
export function defaultMounts(paths = DEFAULT_PATHS) {
  const mounts = [];
  const add = (win, target, flags) => mounts.push({ win: normalizeWinPath(win), target: target.replace(/\/+$/, ''), flags });
  if (paths.installDir) add(paths.installDir, paths.vfsInstall || '/fl', FLAG_RO);
  for (const user of [paths.userProfile, paths.user2Profile]) {
    if (!user) continue;
    const sd = paths.sharedDataDir || `${user}\\Documents\\Image-Line`;
    add(sd, paths.vfsSharedData || '/c/home/Documents/Image-Line', FLAG_PERSIST);
    add(`${user}\\AppData\\Roaming`, '/c/home/AppData/Roaming', FLAG_PERSIST);
    add(`${user}\\AppData\\Local\\Temp\\Image-Line`, paths.vfsTmp || '/c/tmp', FLAG_TMP);
    add(`${user}\\AppData\\Local`, '/c/home/AppData/Local', FLAG_PERSIST);
    add(`${user}\\AppData\\Roaming\\Image-Line`, '/c/home/AppData/Roaming/Image-Line', FLAG_PERSIST);
    add(user, paths.vfsHome || '/c/home', FLAG_PERSIST);
  }
  add('C:', '/c', FLAG_PERSIST);
  return mounts;
}

/** マウント表 (既定 + 追加) を束ねた写像器。C の pathreg_map と同じ結果を返す (非対応は null) */
export function createMapper({ extraMounts = [], paths = DEFAULT_PATHS } = {}) {
  const mounts = [...defaultMounts(paths), ...extraMounts.map((m) => ({ ...m, win: normalizeWinPath(m.win), target: m.target.replace(/\/+$/, '') }))];
  function map(winPath) {
    const canon = normalizeWinPath(winPath);
    if (!canon) return null;
    const winish = /^[a-zA-Z]:/.test(canon) || canon.startsWith('\\\\');
    if (!winish) return null;
    let best = null, bestLen = -1;
    for (const m of mounts) {
      const c = canon.toLowerCase(), w = m.win.toLowerCase();
      if (!c.startsWith(w)) continue;
      const boundary = c.length === w.length || c[w.length] === '\\' || w.endsWith('\\');
      if (!boundary) continue;
      if (w.length >= bestLen) { best = m; bestLen = w.length; }
    }
    if (!best) return null;
    const rest = canon.slice(best.win.length).replace(/^\\/, '');
    return rest ? `${best.target}/${rest.replaceAll('\\', '/')}` : best.target;
  }
  function unmap(posixPath) {
    if (typeof posixPath !== 'string' || !posixPath.startsWith('/')) return null;
    let best = null, bestLen = -1;
    for (const m of mounts) {
      const t = m.target;
      if (posixPath.length < t.length) continue;
      if (posixPath.slice(0, t.length).toLowerCase() !== t.toLowerCase()) continue;
      if (posixPath.length > t.length && posixPath[t.length] !== '/') continue;
      if (t.length >= bestLen) { best = m; bestLen = t.length; }
    }
    if (!best) return null;
    const rest = posixPath.slice(best.target.length).replace(/^\//, '');
    return rest ? `${best.win}\\${rest.replaceAll('/', '\\')}` : best.win;
  }
  return { map, unmap, mounts };
}

/** 利便: 既定設定での写像 (単発) */
export function mapPath(winPath, opts = {}) { return createMapper(opts).map(winPath); }
