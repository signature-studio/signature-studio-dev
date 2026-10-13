// canvas_renderer.mjs — 表示リスト → Canvas2D (ブラウザ用). ctx は CanvasRenderingContext2D 互換 (e2e では記録用 mock).
//   images: assetId -> drawImage 可能な source (ImageBitmap / HTMLImageElement). 抽出 PNG の Blob から createImageBitmap で作る.
export function paintCanvas(ctx, list, images, { font = '600 14px sans-serif', color = '#d8e2ea' } = {}) {
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.font = font; ctx.fillStyle = color; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  let n = 0;
  for (const it of list) {
    if (it.op === 'image') ctx.drawImage(images[it.asset], it.sx, it.sy, it.sw, it.sh, it.dx, it.dy, it.sw, it.sh);
    else if (it.op === 'text') ctx.fillText(it.text, it.cx, it.cy);
    else if (it.op === 'rect') ctx.fillRect(it.x, it.y, it.w, it.h);
    n++;
  }
  return n;
}
