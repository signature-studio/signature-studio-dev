// Win32 / posix パスを manifest キー (tree 相対, '/' 区切り) へ正規化する。
// root prefix (例 'C:\\Program Files\\Image-Line\\FL Studio 2026') は大小無視で剥がす。

export function normalizePath(p: string, roots: string[] = []): string {
  let s = p.replace(/\\/g, '/');
  const low = s.toLowerCase();
  for (const r of roots) {
    const rr = r.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
    if (low === rr) return '';
    if (low.startsWith(rr + '/')) {
      s = s.slice(rr.length + 1);
      break;
    }
  }
  const out: string[] = [];
  for (const part of s.split('/')) {
    if (part === '' || part === '.') continue;
    if (part === '..') out.pop();
    else out.push(part);
  }
  return out.join('/');
}
