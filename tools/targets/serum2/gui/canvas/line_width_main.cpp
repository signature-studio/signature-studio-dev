// SR-68 #4427: 線の太さ (lineWidth) と drawMode (aliasing / kAntiAliasing) を bitmap へ直接描いて画素を数える harness (wasm)。検証専用で製品には入らない。
// 各ケースごとに、非ゼロ画素数・部分被覆の画素数 (0 < alpha < 255、AA の証拠)・完全被覆の画素数を出す。判定は check_line_width.sh 側。
// SR-72 #4470: 閉じた三角形の角 (接合部) の画素を、線分の和集合の被覆の参照値と比べる。辺ごとに合成していると角の alpha が参照値より大きくなる。

#include "canvas_bitmap.h"
#include "canvas_graphicsdevice.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/vstguiinit.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <memory>

namespace {

constexpr uint32_t kWidth = 64;
constexpr uint32_t kHeight = 64;
constexpr int kSub = 4;

struct Counts
{
	size_t nonzero;
	size_t partial;
	size_t full;
};

Counts countPixels (const uint8_t* rgba, size_t byteCount)
{
	Counts c {0, 0, 0};
	for (size_t i = 0; i < byteCount; i += 4)
	{
		const auto a = rgba[i + 3];
		if (rgba[i] || rgba[i + 1] || rgba[i + 2] || a)
			++c.nonzero;
		if (a > 0 && a < 255)
			++c.partial;
		if (a == 255)
			++c.full;
	}
	return c;
}

double distanceToSegment (double px, double py, VSTGUI::CPoint from, VSTGUI::CPoint to)
{
	const auto dx = to.x - from.x;
	const auto dy = to.y - from.y;
	const auto lengthSquared = dx * dx + dy * dy;
	const auto qx = px - from.x;
	const auto qy = py - from.y;
	const auto t = lengthSquared > 0. ? std::clamp ((qx * dx + qy * dy) / lengthSquared, 0., 1.) : 0.;
	const auto ex = qx - t * dx;
	const auto ey = qy - t * dy;
	return std::sqrt (ex * ex + ey * ey);
}

// 閉じた三角形の線分の和集合について、画素ごとの被覆 (標本点の割合) を直接求め、描かれた alpha と比べる。
void checkCornerJoin (const char* name, const uint8_t* rgba, const VSTGUI::PointList& tri, double half)
{
	size_t over = 0;
	int maxDiff = 0;
	for (uint32_t y = 0; y < kHeight; ++y)
	{
		for (uint32_t x = 0; x < kWidth; ++x)
		{
			int count = 0;
			for (int sy = 0; sy < kSub; ++sy)
			{
				for (int sx = 0; sx < kSub; ++sx)
				{
					const auto px = x + (sx + 0.5) / kSub;
					const auto py = y + (sy + 0.5) / kSub;
					bool inside = false;
					for (size_t i = 0; i < tri.size () && !inside; ++i)
						inside = distanceToSegment (px, py, tri[i], tri[(i + 1) % tri.size ()]) <= half;
					count += inside ? 1 : 0;
				}
			}
			const int expected = static_cast<int> (std::lround (count / double (kSub * kSub) * 255.));
			const int actual = rgba[(static_cast<size_t> (y) * kWidth + x) * 4 + 3];
			if (actual > expected + 1)
				++over;
			maxDiff = std::max (maxDiff, std::abs (actual - expected));
		}
	}
	std::printf ("corner_join name=%s over=%zu maxdiff=%d\n", name, over, maxDiff);
}

} // namespace

int main ()
{
	using namespace VSTGUI;
	init (nullptr);
	const size_t byteCount = static_cast<size_t> (kWidth) * kHeight * 4;
	auto device = std::make_shared<CanvasGraphicsDevice> ();
	const PointList triangle {CPoint (8.5, 50.5), CPoint (32.5, 10.5), CPoint (56.5, 50.5)};

	auto run = [&] (const char* name, double width, CDrawMode mode, bool closedTriangle) {
		auto* canvasBitmap = new CanvasBitmap (kWidth, kHeight);
		PlatformBitmapPtr bitmap (canvasBitmap);
		auto context = device->createBitmapContext (bitmap);
		auto* ctx = static_cast<CanvasGraphicsDeviceContext*> (context.get ());
		ctx->setClipRect (CRect (0, 0, kWidth, kHeight));
		ctx->setFrameColor (CColor (255, 0, 0, 255));
		ctx->setFillColor (CColor (0, 255, 0, 255));
		ctx->setGlobalAlpha (1.);
		ctx->setLineWidth (width);
		ctx->setDrawMode (mode);
		bool rc = closedTriangle ? ctx->drawPolygon (triangle, PlatformGraphicsDrawStyle::Stroked)
		                         : ctx->drawLine ({CPoint (4.5, 8.5), CPoint (58.5, 40.5)});
		auto c = countPixels (canvasBitmap->data (), byteCount);
		std::printf ("line_width name=%s rc=%d nonzero=%zu partial=%zu full=%zu\n", name, rc ? 1 : 0, c.nonzero, c.partial, c.full);
		if (closedTriangle)
			checkCornerJoin (name, canvasBitmap->data (), triangle, width / 2.);
	};

	run ("w1_alias", 1., CDrawMode (kAliasing), false);
	run ("w4_alias", 4., CDrawMode (kAliasing), false);
	run ("w1_aa", 1., CDrawMode (kAntiAliasing), false);
	run ("w4_aa", 4., CDrawMode (kAntiAliasing), false);
	run ("corner_tri_w4_aa", 4., CDrawMode (kAntiAliasing), true);
	return 0;
}
