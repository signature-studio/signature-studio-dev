/**
 * 描画転送ユーティリティ (strategy.md §3 #5 / §4 M7 の雛形)。
 * 将来は wasm 側フレームバッファ (SAB / wasm memory) → OffscreenCanvas への
 * blit に差し替える。現状は Uint8ClampedArray → putImageData の最小版のみ。
 */

export type FrameTarget = {
  /** メイン Canvas 2D でも OffscreenCanvasHostingContext でも同じ interface */
  ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
  width: number;
  height: number;
};

/** 全画面 Canvas を作る (index.html の #screen を掴む) */
export function setupCanvas(id: string): FrameTarget | null {
  const canvas = document.getElementById(id) as HTMLCanvasElement | null;
  if (!canvas) return null;
  const resize = () => {
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
  };
  resize();
  window.addEventListener("resize", resize);
  const ctx = canvas.getContext("2d", { alpha: false });
  return ctx
    ? { ctx, width: canvas.width, height: canvas.height }
    : null;
}

/** フレームバッファ (RGBA8, width*height*4) を 1 枚 blit する */
export function blitFrame(
  target: FrameTarget,
  buf: Uint8ClampedArray<ArrayBuffer>,
  width = target.width,
  height = target.height,
): void {
  const imageData = new ImageData(buf, width, height);
  target.ctx.putImageData(imageData, 0, 0);
}

/** サイズ変更時の受け皿 (将来 OffscreenCanvas 化した際の再初期化用) */
export function resizeTarget(
  target: FrameTarget,
  width: number,
  height: number,
): void {
  target.width = width;
  target.height = height;
}
