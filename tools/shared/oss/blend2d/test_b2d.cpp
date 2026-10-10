// Blend2D 検証ハーネス: FL が使う面 (BLImage/BLContext fill/stroke/gradient/text) をソフトウェア描画し画素ハッシュを出力。
// native(JIT) / native(no-JIT) / wasm(no-JIT) を比較する。
#include <blend2d.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>

static uint64_t fnv(const void* p, size_t n, uint64_t h) { const unsigned char* c = (const unsigned char*)p; for (size_t i = 0; i < n; i++) { h ^= c[i]; h *= 1099511628211ULL; } return h; }

static void draw_scene(BLContext& ctx, int W, int H, BLFont* f22, BLFont* f12) {
  ctx.setCompOp(BL_COMP_OP_SRC_COPY);
  ctx.fillAll(BLRgba32(0xFF101830u));
  ctx.setCompOp(BL_COMP_OP_SRC_OVER);

  BLGradient lg(BLLinearGradientValues(0, 0, W, H));
  lg.addStop(0.0, BLRgba32(0xFFFF4000u)); lg.addStop(0.5, BLRgba32(0xFFFFE000u)); lg.addStop(1.0, BLRgba32(0xFF0040FFu));
  ctx.setFillStyle(lg);
  ctx.fillRoundRect(BLRoundRect(16, 16, 200, 110, 14));

  ctx.setFillStyle(BLRgba32(0x8000FF40u));
  ctx.fillCircle(150, 140, 70);

  BLGradient rg(BLRadialGradientValues(240, 70, 240, 70, 50));
  rg.addStop(0.0, BLRgba32(0xFFFFFFFFu)); rg.addStop(1.0, BLRgba32(0x20FF00FFu));
  ctx.setFillStyle(rg);
  ctx.fillEllipse(240, 70, 60, 40);

  BLPath path;
  path.moveTo(10, 225); path.cubicTo(90, 80, 190, 330, 310, 190); path.quadTo(300, 100, 260, 120);
  ctx.setStrokeWidth(5.5); ctx.setStrokeStyle(BLRgba32(0xFFF0F0F0u));
  ctx.setStrokeCaps(BL_STROKE_CAP_ROUND); ctx.setStrokeJoin(BL_STROKE_JOIN_ROUND);
  ctx.strokePath(path);

  if (f22) {
    ctx.setFillStyle(BLRgba32(0xFFFFFFFFu));
    ctx.fillUtf8Text(BLPoint(24, 60), *f22, "Signature Studio 26.1");
    ctx.fillUtf8Text(BLPoint(24, 80), *f12, "The quick brown fox jumps");
  }
}

int main(int argc, char** argv) {
  const int W = 320, H = 240;
  BLImage img(W, H, BL_FORMAT_PRGB32);
  BLFontFace face; BLFont font22, font12; bool have_font = false;
  if (argc > 1 && face.createFromFile(argv[1]) == BL_SUCCESS && font22.createFromFace(face, 22.0f) == BL_SUCCESS && font12.createFromFace(face, 12.0f) == BL_SUCCESS) have_font = true;
  { BLContext ctx(img); draw_scene(ctx, W, H, have_font ? &font22 : nullptr, have_font ? &font12 : nullptr); ctx.end(); }
  if (getenv("BENCH")) {   // 描画性能 (ms/frame): JIT vs no-JIT vs wasm の比較用
    int iters = atoi(getenv("BENCH")); struct timespec t0, t1; clock_gettime(CLOCK_MONOTONIC, &t0);
    for (int i = 0; i < iters; i++) { BLContext c(img); draw_scene(c, W, H, have_font ? &font22 : nullptr, have_font ? &font12 : nullptr); c.end(); }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    printf("bench iters=%d ms_per_frame=%.3f\n", iters, ((t1.tv_sec - t0.tv_sec) * 1e3 + (t1.tv_nsec - t0.tv_nsec) / 1e6) / iters);
  }

  BLImageData d; img.getData(&d);
  uint64_t h = 14695981039346656037ULL;
  for (int y = 0; y < H; y++) h = fnv((const uint8_t*)d.pixelData + (size_t)y * d.stride, (size_t)W * 4, h);
  printf("size=%dx%d stride=%d format=%d pixel_hash=%016llx\n", d.size.w, d.size.h, (int)d.stride, (int)d.format, (unsigned long long)h);
  if (getenv("DUMP_PPM")) { FILE* f = fopen(getenv("DUMP_PPM"), "wb"); fprintf(f, "P6\n%d %d\n255\n", W, H);
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) { uint32_t p = ((const uint32_t*)((const uint8_t*)d.pixelData + y * d.stride))[x]; fputc((p >> 16) & 255, f); fputc((p >> 8) & 255, f); fputc(p & 255, f); } fclose(f); }
  BLRuntimeBuildInfo bi; BLRuntime::queryBuildInfo(&bi);
  printf("blend2d %u.%u.%u\n", bi.majorVersion, bi.minorVersion, bi.patchVersion);
  return 0;
}
