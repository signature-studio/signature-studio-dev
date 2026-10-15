// SR-69 #4428: setTransformMatrix の実測 harness (wasm)。検証専用で製品には入らない。
// 同じ親に、原点 (0,0) のコンテナと原点以外 (40,20) のコンテナを置き、それぞれの中の (0,0)-(30,10) の子 view に
// 固定色 (赤) の矩形を描く。領域ごとの赤画素数を数える: origin = (0,0)-(30,10)、shifted = (40,20)-(70,30)。
// 期待 (変換が効く): origin=300 shifted=300。変換が no-op なら shifted=0 になる。
// 後半は device を直接呼ぶ 3 命令 (drawPoint・drawArc・drawGraphicsPath) を、回転 90 度と平行移動 (40,20) を掛けて描く。
// 変換前の位置 (0,0)-(20,20) には画素が出ず、変換後の位置 (点 (35,25)・弧 x20-31 y20-41・path x30-41 y20-31) には出ること。
// 90 度回転で (x,y)->(40-y,20+x)。点 (5,5)->(35,25)。弧の半円は x20-30 y20-40。path (0,0)-(10,10) は x30-40 y20-30。

#include "canvas_bitmap.h"
#include "canvas_graphicsdevice.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/cview.h"
#include "vstgui/lib/cviewcontainer.h"
#include "vstgui/lib/platform/iplatformgraphicspath.h"
#include "vstgui/lib/vstguiinit.h"
#include <cmath>
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

//------------------------------------------------------------------------
size_t countDrawn (const uint8_t* rgba, int x0, int y0, int x1, int y1)
{
	size_t n = 0;
	for (int y = y0; y < y1; ++y)
	{
		for (int x = x0; x < x1; ++x)
		{
			if (rgba[(static_cast<size_t> (y) * kWidth + x) * 4 + 3] != 0)
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

	auto* opsBitmap = new CanvasBitmap (kWidth, kHeight);
	PlatformBitmapPtr opsPtr (opsBitmap);
	auto opsContext = device->createBitmapContext (opsPtr);
	TransformMatrix tm;
	tm.rotate (90.);
	tm.translate (40., 20.);
	opsContext->setTransformMatrix (tm);
	opsContext->beginDraw ();
	opsContext->drawPoint (CPoint (5., 5.), CColor (255, 255, 0, 255));
	opsContext->setFillColor (CColor (0, 255, 0, 255));
	opsContext->drawArc (CRect (0, 0, 20, 20), 0., std::acos (-1.), PlatformGraphicsDrawStyle::Filled);
	auto path = opsContext->getGraphicsPathFactory ()->createPath ();
	path->addRect (CRect (0, 0, 10, 10));
	path->finishBuilding ();
	opsContext->setFillColor (CColor (0, 0, 255, 255));
	opsContext->drawGraphicsPath (*path, PlatformGraphicsPathDrawMode::Filled, nullptr);
	opsContext->endDraw ();

	const auto* opsRgba = opsBitmap->data ();
	const size_t untransformed = countDrawn (opsRgba, 0, 0, 20, 20);
	const bool pointShifted = opsRgba[(25 * kWidth + 35) * 4 + 3] != 0;
	const size_t arcShifted = countDrawn (opsRgba, 20, 20, 31, 41);
	const size_t pathShifted = countDrawn (opsRgba, 30, 20, 41, 31);
	const bool opsPass = untransformed == 0 && pointShifted && arcShifted > 0 && pathShifted > 0;
	std::printf ("transform_ops untransformed_px=%zu point=%d arc_px=%zu path_px=%zu result=%s\n",
	             untransformed, pointShifted ? 1 : 0, arcShifted, pathShifted,
	             opsPass ? "pass" : "fail");
	return pass && opsPass ? 0 : 1;
}
