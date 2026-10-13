// soft_render.mjs — 表示リスト → RGBA (ソフトウェア合成). e2e の画素検証と work/ への snapshot 出力用 (text は描かない).
import { decodePng } from './png_lite.mjs';

export function loadAssets(manifest, getRsrc) { // getRsrc("PNG/128") -> Buffer
  const out = {};
  for (const [id, a] of Object.entries(manifest.assets)) {
    const img = decodePng(getRsrc(a.rsrc));
    if (img.w !== a.w || img.h !== a.h) throw new Error(`asset ${id}: ${img.w}x${img.h} != manifest ${a.w}x${a.h}`);
    out[id] = img;
  }
  return out;
}

export function render(list, assets, w, h) {
  const px = Buffer.alloc(w * h * 4);
  for (const it of list) {
    if (it.op === 'image') {
      const A = assets[it.asset];
      for (let y = 0; y < it.sh; y++) {
        const dy = it.dy + y; if (dy < 0 || dy >= h) continue;
        for (let x = 0; x < it.sw; x++) {
          const dx = it.dx + x; if (dx < 0 || dx >= w) continue;
          const s = ((it.sy + y) * A.w + it.sx + x) * 4, d = (dy * w + dx) * 4, a = A.rgba[s + 3];
          if (a === 255) { px[d] = A.rgba[s]; px[d + 1] = A.rgba[s + 1]; px[d + 2] = A.rgba[s + 2]; px[d + 3] = 255; }
          else if (a) { const ia = 255 - a; for (let k = 0; k < 3; k++) px[d + k] = Math.round((A.rgba[s + k] * a + px[d + k] * ia) / 255); px[d + 3] = 255; }
        }
      }
    } else if (it.op === 'rect') {
      for (let y = 0; y < it.h; y++) for (let x = 0; x < it.w; x++) {
        const dx = it.x + x, dy = it.y + y; if (dx < 0 || dx >= w || dy < 0 || dy >= h) continue;
        const d = (dy * w + dx) * 4; px[d] = 235; px[d + 1] = 240; px[d + 2] = 245; px[d + 3] = 255;
      }
    }
  }
  return { w, h, rgba: px };
}
