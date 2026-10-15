// SR-55 #3422: 描画命令 (drawLine・drawLines・drawPolygon・drawEllipse・drawBitmap) を bitmap へ直接呼んで画素を確かめる harness (wasm)。検証専用で製品には入らない。
// SR-62 #4233: fillLinearGradient・fillRadialGradient・drawBitmapNinePartTiled・fillRectWithBitmap を追加する。
// 各命令ごとに、描かれた画素数 (非ゼロ) と、描画先の代表画素の色を出す。判定は check_draw_ops.sh 側。
// 各命令の出力行 `draw_op` の後に `draw_color name=... distinct=N` を出す (異なる色の数。gradient は変化して見えることを判定する)。

#include "canvas_bitmap.h"
#include "canvas_gradient.h"
#include "canvas_graphicsdevice.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/platform/iplatformgraphicspath.h"
#include "vstgui/lib/platform/iplatformgraphicsdevice.h"
#include "vstgui/lib/vstguiinit.h"
#include <cstdio>
#include <memory>
#include <set>

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

size_t countDistinctColors (const uint8_t* rgba, size_t byteCount)
{
	std::set<uint32_t> colors;
	for (size_t i = 0; i < byteCount; i += 4)
		colors.insert ((uint32_t (rgba[i]) << 24) | (uint32_t (rgba[i + 1]) << 16) | (uint32_t (rgba[i + 2]) << 8) | rgba[i + 3]);
	return colors.size ();
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
		std::printf ("draw_color name=%s distinct=%zu\n", name, countDistinctColors (canvasBitmap->data (), byteCount));
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

	auto makeSource = [] (uint32_t w, uint32_t h) {
		auto* source = new CanvasBitmap (w, h);
		for (size_t i = 0; i < static_cast<size_t> (w) * h * 4; i += 4)
		{
			source->data () [i] = 0;
			source->data () [i + 1] = 0;
			source->data () [i + 2] = 255;
			source->data () [i + 3] = 255;
		}
		return PlatformBitmapPtr (source);
	};

	{
		auto sourcePtr = makeSource (8, 8);
		auto* source = static_cast<CanvasBitmap*> (sourcePtr.get ());
		auto* canvasBitmap = new CanvasBitmap (kWidth, kHeight);
		PlatformBitmapPtr bitmap (canvasBitmap);
		auto context = device->createBitmapContext (bitmap);
		auto* ctx = static_cast<CanvasGraphicsDeviceContext*> (context.get ());
		ctx->setClipRect (CRect (0, 0, kWidth, kHeight));
		bool rc = ctx->drawBitmap (*source, CRect (10., 10., 18., 18.), CPoint (0., 0.), 1., BitmapInterpolationQuality::kLow);
		std::printf ("draw_op name=drawBitmap rc=%d nonzero=%zu\n", rc ? 1 : 0, countNonZeroPixels (canvasBitmap->data (), byteCount));
		std::printf ("draw_color name=drawBitmap distinct=%zu\n", countDistinctColors (canvasBitmap->data (), byteCount));
	}

	run ("fillLinearGradient", [] (IPlatformGraphicsDeviceContext& c) {
		auto path = c.getGraphicsPathFactory ()->createPath (PlatformGraphicsPathFillMode::Winding);
		path->addRect (CRect (4., 4., 60., 60.));
		CanvasGradient gradient;
		gradient.addColorStop ({0., CColor (255, 0, 0, 255)});
		gradient.addColorStop ({1., CColor (0, 255, 0, 255)});
		return c.fillLinearGradient (*path, gradient, CPoint (4., 0.), CPoint (60., 0.), false, nullptr);
	});
	run ("fillRadialGradient", [] (IPlatformGraphicsDeviceContext& c) {
		auto path = c.getGraphicsPathFactory ()->createPath (PlatformGraphicsPathFillMode::Winding);
		path->addRect (CRect (4., 4., 60., 60.));
		CanvasGradient gradient;
		gradient.addColorStop ({0., CColor (255, 0, 0, 255)});
		gradient.addColorStop ({1., CColor (0, 0, 255, 255)});
		return c.fillRadialGradient (*path, gradient, CPoint (32., 32.), 28., CPoint (0., 0.), false, nullptr);
	});

	{
		auto sourcePtr = makeSource (12, 12);
		auto* source = static_cast<CanvasBitmap*> (sourcePtr.get ());
		auto* canvasBitmap = new CanvasBitmap (kWidth, kHeight);
		PlatformBitmapPtr bitmap (canvasBitmap);
		auto context = device->createBitmapContext (bitmap);
		auto* ctx = static_cast<CanvasGraphicsDeviceContext*> (context.get ());
		ctx->setClipRect (CRect (0, 0, kWidth, kHeight));
		CNinePartTiledDescription desc (3., 3., 3., 3.);
		bool rc = ctx->drawBitmapNinePartTiled (*source, CRect (4., 4., 60., 60.), desc, 1., BitmapInterpolationQuality::kLow);
		std::printf ("draw_op name=drawBitmapNinePartTiled rc=%d nonzero=%zu\n", rc ? 1 : 0, countNonZeroPixels (canvasBitmap->data (), byteCount));
		std::printf ("draw_color name=drawBitmapNinePartTiled distinct=%zu\n", countDistinctColors (canvasBitmap->data (), byteCount));
	}

	{
		auto sourcePtr = makeSource (4, 4);
		auto* source = static_cast<CanvasBitmap*> (sourcePtr.get ());
		auto* canvasBitmap = new CanvasBitmap (kWidth, kHeight);
		PlatformBitmapPtr bitmap (canvasBitmap);
		auto context = device->createBitmapContext (bitmap);
		auto* ctx = static_cast<CanvasGraphicsDeviceContext*> (context.get ());
		ctx->setClipRect (CRect (0, 0, kWidth, kHeight));
		bool rc = ctx->fillRectWithBitmap (*source, CRect (0., 0., 4., 4.), CRect (10., 10., 40., 40.), 1., BitmapInterpolationQuality::kLow);
		std::printf ("draw_op name=fillRectWithBitmap rc=%d nonzero=%zu\n", rc ? 1 : 0, countNonZeroPixels (canvasBitmap->data (), byteCount));
		std::printf ("draw_color name=fillRectWithBitmap distinct=%zu\n", countDistinctColors (canvasBitmap->data (), byteCount));
	}
	{
		auto sourcePtr = makeSource (8, 8);
		auto* source = static_cast<CanvasBitmap*> (sourcePtr.get ());

		// 8x8 の source を 32x32 へ拡大する。拡大後の被覆は 32*32 画素 (scale 判定)。
		auto runStretch = [&] (const char* name, BitmapInterpolationQuality quality) {
			PlatformBitmapPtr outPtr (new CanvasBitmap (kWidth, kHeight));
			auto* out = static_cast<CanvasBitmap*> (outPtr.get ());
			auto outCtx = device->createBitmapContext (outPtr);
			auto* octx = static_cast<CanvasGraphicsDeviceContext*> (outCtx.get ());
			octx->setClipRect (CRect (0, 0, kWidth, kHeight));
			bool ok = octx->fillRectWithBitmap (*source, CRect (0., 0., 8., 8.), CRect (10., 10., 42., 42.), 1., quality);
			std::printf ("draw_op name=%s rc=%d nonzero=%zu\n", name, ok ? 1 : 0,
			             countNonZeroPixels (out->data (), byteCount));
		};
		runStretch ("fillRectWithBitmap_scale", BitmapInterpolationQuality::kLow);

		// 白黒 2x2 を bilinear で拡大すると中間階調が出る。kLow は出ない。
		auto* checker = new CanvasBitmap (2, 2);
		PlatformBitmapPtr checkerPtr (checker);
		for (size_t i = 0; i < 4 * 4; i += 4)
		{
			const uint8_t v = (i / 4) % 2 ? 255 : 0;
			checker->data () [i] = v;
			checker->data () [i + 1] = v;
			checker->data () [i + 2] = v;
			checker->data () [i + 3] = 255;
		}
		auto countMid = [&] (BitmapInterpolationQuality quality, bool& ok) {
			PlatformBitmapPtr outPtr (new CanvasBitmap (kWidth, kHeight));
			auto* out = static_cast<CanvasBitmap*> (outPtr.get ());
			auto outCtx = device->createBitmapContext (outPtr);
			auto* octx = static_cast<CanvasGraphicsDeviceContext*> (outCtx.get ());
			octx->setClipRect (CRect (0, 0, kWidth, kHeight));
			ok = octx->fillRectWithBitmap (*checker, CRect (0., 0., 2., 2.), CRect (0., 0., 32., 32.), 1., quality);
			size_t mid = 0;
			for (size_t i = 0; i < byteCount; i += 4)
			{
				if (out->data () [i + 3] && out->data () [i] > 0 && out->data () [i] < 255)
					++mid;
			}
			return mid;
		};
		bool bilinearOk = false;
		bool nearestOk = false;
		const size_t bilinearMid = countMid (BitmapInterpolationQuality::kMedium, bilinearOk);
		const size_t nearestMid = countMid (BitmapInterpolationQuality::kLow, nearestOk);
		std::printf ("draw_op name=fillRectWithBitmap_bilinear rc=%d nonzero=%zu\n", bilinearOk ? 1 : 0, bilinearMid);
		std::printf ("mid_tone name=fillRectWithBitmap_nearest count=%zu\n", nearestMid);

		// 9 分割: 8x8 の source を枠 2 px・中央を伸ばして 20x20 へ描く。被覆は dest の 20*20 画素。
		auto* nineOut = new CanvasBitmap (kWidth, kHeight);
		PlatformBitmapPtr nineOutPtr (nineOut);
		auto nineCtx = device->createBitmapContext (nineOutPtr);
		auto* nctx = static_cast<CanvasGraphicsDeviceContext*> (nineCtx.get ());
		nctx->setClipRect (CRect (0, 0, kWidth, kHeight));
		bool nineRc = nctx->drawBitmapNinePartTiled (*source, CRect (10., 10., 30., 30.), CNinePartTiledDescription (2., 2., 2., 2.), 1., BitmapInterpolationQuality::kLow);
		std::printf ("draw_op name=drawBitmapNinePartTiled_scale rc=%d nonzero=%zu\n", nineRc ? 1 : 0, countNonZeroPixels (nineOut->data (), byteCount));
	}
	return 0;
}
