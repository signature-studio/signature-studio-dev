/**
 * gui_dirty.ts — present の dirty 矩形集合 (surface ごとの複数矩形) の統合。純関数 (DOM/Worker 非依存)。
 *
 * 1 フレーム (PRESENT 群 + FRAME_END) 内の矩形を surface 単位で併合する。
 * - 重なる/辺で接する矩形は必ず併合 (二重転送を避ける)
 * - 離れた矩形は「併合後の面積 ≤ 個別面積和 × (1 + slack)」のときだけ併合 (外接で無駄な転送を増やさない)
 * - surface あたり maxPerSurf を超えたら、面積増加が最小の組から併合 (最終的に外接矩形へ縮退)
 */
export type DirtyRect = { id: number; l: number; t: number; r: number; b: number };

const area = (a: DirtyRect): number => Math.max(0, a.r - a.l) * Math.max(0, a.b - a.t);
const touch = (a: DirtyRect, b: DirtyRect): boolean => a.l <= b.r && b.l <= a.r && a.t <= b.b && b.t <= a.b;
const union = (a: DirtyRect, b: DirtyRect): DirtyRect => ({ id: a.id, l: Math.min(a.l, b.l), t: Math.min(a.t, b.t), r: Math.max(a.r, b.r), b: Math.max(a.b, b.b) });

export function mergeRects(list: readonly DirtyRect[], maxPerSurf = 8, slack = 0.25): DirtyRect[] {
  const byId = new Map<number, DirtyRect[]>();
  for (const q of list) {
    if (q.r <= q.l || q.b <= q.t) continue;
    let g = byId.get(q.id);
    if (!g) byId.set(q.id, (g = []));
    g.push({ ...q });
  }
  const out: DirtyRect[] = [];
  for (const id of [...byId.keys()].sort((x, y) => x - y)) {
    const rs = byId.get(id)!;
    for (let again = true; again;) {
      again = false;
      outer: for (let i = 0; i < rs.length; i++) {
        for (let j = i + 1; j < rs.length; j++) {
          const u = union(rs[i], rs[j]);
          if (touch(rs[i], rs[j]) || area(u) <= (area(rs[i]) + area(rs[j])) * (1 + slack)) {
            rs[i] = u; rs.splice(j, 1); again = true; break outer;
          }
        }
      }
    }
    while (rs.length > maxPerSurf) {
      let bi = 0, bj = 1, best = Infinity;
      for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
        const g = area(union(rs[i], rs[j])) - area(rs[i]) - area(rs[j]);
        if (g < best) { best = g; bi = i; bj = j; }
      }
      rs[bi] = union(rs[bi], rs[bj]); rs.splice(bj, 1);
    }
    out.push(...rs);
  }
  return out;
}

export function rectArea(rs: readonly DirtyRect[]): number {
  let s = 0;
  for (const r of rs) s += area(r);
  return s;
}
