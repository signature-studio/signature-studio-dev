// SR-55 #3422: 描画命令 (drawLine・drawLines・drawPolygon・drawEllipse・drawBitmap) を bitmap へ直接呼んで画素を確かめる harness (wasm)。検証専用で製品には入らない。
// SR-62 #4233: fillLinearGradient・fillRadialGradient・drawBitmapNinePartTiled・fillRectWithBitmap を追加する。
// 各命令ごとに、描かれた画素数 (非ゼロ) と、描画先の代表画素の色を出す。判定は check_draw_ops.sh 側。
// 各命令の出力行 `draw_op` の後に `draw_color name=... distinct=N` を出す (異なる色の数。gradient は変化して見えることを判定する)。

#include "canvas_bitmap.h"
#include "canvas_gradient.h"
#include "canvas_graphicsdevice.h"
#include "canvas_graphicspath.h"
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
	run ("drawArc", [] (IPlatformGraphicsDeviceContext& c) {
		return c.drawArc (CRect (4., 4., 60., 60.), 0., M_PI, PlatformGraphicsDrawStyle::FilledAndStroked);
	});
	run ("drawPoint", [] (IPlatformGraphicsDeviceContext& c) {
		return c.drawPoint (CPoint (30., 30.), CColor (0, 0, 255, 255));
	});
	CanvasGraphicsPath graphicsPath (PlatformGraphicsPathFillMode::Winding);
	graphicsPath.addRect (CRect (4., 4., 30., 30.));
	graphicsPath.beginSubpath (CPoint (40., 40.));
	graphicsPath.addLine (CPoint (60., 40.));
	graphicsPath.addLine (CPoint (50., 60.));
	graphicsPath.closeSubpath ();
	run ("drawGraphicsPath", [&] (IPlatformGraphicsDeviceContext& c) {
		return c.drawGraphicsPath (graphicsPath, PlatformGraphicsPathDrawMode::Filled, nullptr);
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

	// 楕円形: x を 2 倍に伸ばす transformation を渡す。色は局所座標 (円) で決まるので、device 上では横長の楕円になる。
	// 停止点の末尾を alpha 0 にして、楕円の外を描かないようにする。中心の行と列に描かれた画素の数で広がりを比べる。
	{
		PlatformBitmapPtr bitmap (new CanvasBitmap (kWidth, kHeight));
		auto* canvasBitmap = static_cast<CanvasBitmap*> (bitmap.get ());
		auto context = device->createBitmapContext (bitmap);
		auto* ctx = static_cast<CanvasGraphicsDeviceContext*> (context.get ());
		ctx->setClipRect (CRect (0, 0, kWidth, kHeight));
		auto path = ctx->getGraphicsPathFactory ()->createPath (PlatformGraphicsPathFillMode::Winding);
		path->addRect (CRect (2., 2., 30., 30.));
		CanvasGradient gradient;
		gradient.addColorStop ({0., CColor (255, 0, 0, 255)});
		gradient.addColorStop ({1., CColor (0, 0, 255, 0)});
		TransformMatrix tm;
		tm.scale (2., 1.);
		bool rc = ctx->fillRadialGradient (*path, gradient, CPoint (16., 16.), 12., CPoint (0., 0.), false, &tm);
		const uint8_t* px = canvasBitmap->data ();
		auto filled = [&] (uint32_t x, uint32_t y) { return px[(y * kWidth + x) * 4 + 3] != 0; };
		size_t row = 0;
		size_t col = 0;
		for (uint32_t x = 0; x < kWidth; ++x)
			row += filled (x, 16) ? 1 : 0;
		for (uint32_t y = 0; y < kHeight; ++y)
			col += filled (32, y) ? 1 : 0;
		std::printf ("draw_op name=fillRadialGradient_ellipse rc=%d nonzero=%zu\n", rc ? 1 : 0, countNonZeroPixels (px, byteCount));
		std::printf ("ellipse_extent name=fillRadialGradient_ellipse x=%zu y=%zu\n", row, col);
	}

	// alpha 付き停止点: 赤 (不透明) → 青 (透明)。中間色は premultiplied で補間すると赤のまま alpha だけ下がる。非 premultiplied だと青が混ざる。
	{
		PlatformBitmapPtr bitmap (new CanvasBitmap (kWidth, kHeight));
		auto* canvasBitmap = static_cast<CanvasBitmap*> (bitmap.get ());
		auto context = device->createBitmapContext (bitmap);
		auto* ctx = static_cast<CanvasGraphicsDeviceContext*> (context.get ());
		ctx->setClipRect (CRect (0, 0, kWidth, kHeight));
		auto path = ctx->getGraphicsPathFactory ()->createPath (PlatformGraphicsPathFillMode::Winding);
		path->addRect (CRect (4., 4., 60., 60.));
		CanvasGradient gradient;
		gradient.addColorStop ({0., CColor (255, 0, 0, 255)});
		gradient.addColorStop ({1., CColor (0, 0, 255, 0)});
		bool rc = ctx->fillRadialGradient (*path, gradient, CPoint (32., 32.), 28., CPoint (0., 0.), false, nullptr);
		const uint8_t* px = canvasBitmap->data () + (32 * kWidth + 46) * 4;
		std::printf ("draw_pixel name=fillRadialGradient_alpha rc=%d r=%d g=%d b=%d a=%d\n", rc ? 1 : 0, px[0], px[1], px[2], px[3]);
	}

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
