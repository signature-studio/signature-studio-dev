// SR-68 #4427: 線の太さ (lineWidth) と drawMode (aliasing / kAntiAliasing) を bitmap へ直接描いて画素を数える harness (wasm)。検証専用で製品には入らない。
// 各ケースごとに、非ゼロ画素数・部分被覆の画素数 (0 < alpha < 255、AA の証拠)・完全被覆の画素数を出す。判定は check_line_width.sh 側。

#include "canvas_bitmap.h"
#include "canvas_graphicsdevice.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/vstguiinit.h"
#include <cstdio>
#include <memory>

namespace {

constexpr uint32_t kWidth = 64;
constexpr uint32_t kHeight = 64;

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

} // namespace

int main ()
{
	using namespace VSTGUI;
	init (nullptr);
	const size_t byteCount = static_cast<size_t> (kWidth) * kHeight * 4;
	auto device = std::make_shared<CanvasGraphicsDevice> ();

	auto run = [&] (const char* name, double width, CDrawMode mode) {
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
		bool rc = ctx->drawLine ({CPoint (4.5, 8.5), CPoint (58.5, 40.5)});
		auto c = countPixels (canvasBitmap->data (), byteCount);
		std::printf ("line_width name=%s rc=%d nonzero=%zu partial=%zu full=%zu\n", name, rc ? 1 : 0, c.nonzero, c.partial, c.full);
	};

	run ("w1_alias", 1., CDrawMode (kAliasing));
	run ("w4_alias", 4., CDrawMode (kAliasing));
	run ("w1_aa", 1., CDrawMode (kAntiAliasing));
	run ("w4_aa", 4., CDrawMode (kAntiAliasing));
	return 0;
}
