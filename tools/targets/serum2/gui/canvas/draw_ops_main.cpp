// SR-55 #3422: 描画命令 (drawLine・drawLines・drawPolygon・drawEllipse・drawBitmap) を bitmap へ直接呼んで画素を確かめる harness (wasm)。検証専用で製品には入らない。
// 各命令ごとに、描かれた画素数 (非ゼロ) と、描画先の代表画素の色を出す。判定は check_draw_ops.sh 側。

#include "canvas_bitmap.h"
#include "canvas_graphicsdevice.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/vstguiinit.h"
#include <cstdio>
#include <memory>

namespace {

constexpr uint32_t kWidth = 64;
constexpr uint32_t kHeight = 64;

size_t countNonZeroPixels (const uint8_t* rgba, size_t byteCount)
{
	size_t n = 0;
	for (size_t i = 0; i < byteCount; i += 4)
	{
		if (rgba[i] || rgba[i + 1] || rgba[i + 2] || rgba[i + 3])
			++n;
	}
	return n;
}

} // namespace

int main ()
{
	using namespace VSTGUI;
	init (nullptr);
	const size_t byteCount = static_cast<size_t> (kWidth) * kHeight * 4;
	auto device = std::make_shared<CanvasGraphicsDevice> ();

	auto run = [&] (const char* name, auto&& draw) {
		auto* canvasBitmap = new CanvasBitmap (kWidth, kHeight);
		PlatformBitmapPtr bitmap (canvasBitmap);
		auto context = device->createBitmapContext (bitmap);
		auto* ctx = static_cast<CanvasGraphicsDeviceContext*> (context.get ());
		ctx->setClipRect (CRect (0, 0, kWidth, kHeight));
		ctx->setFrameColor (CColor (255, 0, 0, 255));
		ctx->setFillColor (CColor (0, 255, 0, 255));
		ctx->setGlobalAlpha (1.);
		bool rc = draw (*ctx);
		size_t n = countNonZeroPixels (canvasBitmap->data (), byteCount);
		std::printf ("draw_op name=%s rc=%d nonzero=%zu\n", name, rc ? 1 : 0, n);
	};

	run ("drawLine", [] (IPlatformGraphicsDeviceContext& c) {
		return c.drawLine ({CPoint (2., 2.), CPoint (50., 40.)});
	});
	run ("drawLines", [] (IPlatformGraphicsDeviceContext& c) {
		return c.drawLines ({{CPoint (1., 1.), CPoint (10., 1.)}, {CPoint (1., 5.), CPoint (1., 20.)}});
	});
	run ("drawPolygon", [] (IPlatformGraphicsDeviceContext& c) {
		return c.drawPolygon ({CPoint (5., 5.), CPoint (40., 6.), CPoint (20., 40.)}, PlatformGraphicsDrawStyle::Filled);
	});
	run ("drawEllipse", [] (IPlatformGraphicsDeviceContext& c) {
		return c.drawEllipse (CRect (4., 4., 60., 60.), PlatformGraphicsDrawStyle::Filled);
	});

	auto* source = new CanvasBitmap (8, 8);
	PlatformBitmapPtr sourcePtr (source);
	for (size_t i = 0; i < 8 * 8 * 4; i += 4)
	{
		source->data () [i] = 0;
		source->data () [i + 1] = 0;
		source->data () [i + 2] = 255;
		source->data () [i + 3] = 255;
	}
	auto* canvasBitmap = new CanvasBitmap (kWidth, kHeight);
	PlatformBitmapPtr bitmap (canvasBitmap);
	auto context = device->createBitmapContext (bitmap);
	auto* ctx = static_cast<CanvasGraphicsDeviceContext*> (context.get ());
	ctx->setClipRect (CRect (0, 0, kWidth, kHeight));
	bool rc = ctx->drawBitmap (*source, CRect (10., 10., 18., 18.), CPoint (0., 0.), 1., BitmapInterpolationQuality::kLow);
	std::printf ("draw_op name=drawBitmap rc=%d nonzero=%zu\n", rc ? 1 : 0, countNonZeroPixels (canvasBitmap->data (), byteCount));
	return 0;
}
