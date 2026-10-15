// SR-69 #4428: setTransformMatrix の実測 harness (wasm)。検証専用で製品には入らない。
// 同じ親に、原点 (0,0) のコンテナと原点以外 (40,20) のコンテナを置き、それぞれの中の (0,0)-(30,10) の子 view に
// 固定色 (赤) の矩形を描く。領域ごとの赤画素数を数える: origin = (0,0)-(30,10)、shifted = (40,20)-(70,30)。
// 期待 (変換が効く): origin=300 shifted=300。変換が no-op なら shifted=0 になる。

#include "canvas_bitmap.h"
#include "canvas_graphicsdevice.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/cview.h"
#include "vstgui/lib/cviewcontainer.h"
#include "vstgui/lib/vstguiinit.h"
#include <cstdio>
#include <memory>

namespace {

constexpr uint32_t kWidth = 100;
constexpr uint32_t kHeight = 60;

//------------------------------------------------------------------------
class FillView : public VSTGUI::CView
{
public:
	explicit FillView (const VSTGUI::CRect& size) : VSTGUI::CView (size) {}
	void draw (VSTGUI::CDrawContext* context) override
	{
		context->setFillColor (VSTGUI::CColor (255, 0, 0, 255));
		context->drawRect (VSTGUI::CRect (0, 0, 30, 10), VSTGUI::kDrawFilled);
	}
};

//------------------------------------------------------------------------
size_t countRedIn (const uint8_t* rgba, int x0, int y0, int x1, int y1)
{
	size_t n = 0;
	for (int y = y0; y < y1; ++y)
	{
		for (int x = x0; x < x1; ++x)
		{
			const uint8_t* p = rgba + (static_cast<size_t> (y) * kWidth + x) * 4;
			if (p[0] == 255 && p[1] == 0 && p[2] == 0 && p[3] == 255)
				++n;
		}
	}
	return n;
}

} // namespace

int main ()
{
	using namespace VSTGUI;
	init (nullptr);

	auto* canvasBitmap = new CanvasBitmap (kWidth, kHeight);
	PlatformBitmapPtr bitmap (canvasBitmap);
	auto device = std::make_shared<CanvasGraphicsDevice> ();
	auto deviceContext = device->createBitmapContext (bitmap);
	CDrawContext drawContext (deviceContext, CRect (0, 0, kWidth, kHeight), 1.);

	// VSTGUI は子 view の位置を親コンテナの offsetTransform で与える。原点のコンテナと (40,20) のコンテナを並べる。
	auto* root = new CViewContainer (CRect (0, 0, kWidth, kHeight));
	auto* originContainer = new CViewContainer (CRect (0, 0, 60, 40));
	originContainer->addView (new FillView (CRect (0, 0, 30, 10)));
	auto* shiftedContainer = new CViewContainer (CRect (40, 20, 100, 60));
	shiftedContainer->addView (new FillView (CRect (0, 0, 30, 10)));
	root->addView (originContainer);
	root->addView (shiftedContainer);

	drawContext.beginDraw ();
	root->draw (&drawContext);
	drawContext.endDraw ();

	const auto* rgba = canvasBitmap->data ();
	const size_t origin = countRedIn (rgba, 0, 0, 30, 10);
	const size_t shifted = countRedIn (rgba, 40, 20, 70, 30);
	const bool pass = origin == 300 && shifted == 300;
	std::printf ("transform_check origin_px=%zu shifted_px=%zu expected=300 result=%s\n", origin,
	             shifted, pass ? "pass" : "fail");
	return pass ? 0 : 1;
}
