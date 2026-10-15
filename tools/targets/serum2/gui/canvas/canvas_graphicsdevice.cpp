// SR-39 #2107: canvas platform (wasm) の IPlatformGraphicsDevice* 実装。
// SR-50 #3260: drawRect・clearRect を bitmap へ描く。bitmap は createBitmapContext で結線し、clip は bitmap 境界で保持する。

#include "canvas_graphicsdevice.h"
#include "canvas_bitmap.h"
#include "canvas_graphicspath.h"
#include <algorithm>
#include <cmath>

namespace VSTGUI {

namespace {

//------------------------------------------------------------------------
struct PixelBox
{
	int32_t x0;
	int32_t y0;
	int32_t x1;
	int32_t y1;
};

//------------------------------------------------------------------------
PixelBox pixelBoxOf (const CRect& rect)
{
	return {static_cast<int32_t> (std::floor (rect.left)), static_cast<int32_t> (std::floor (rect.top)),
	        static_cast<int32_t> (std::ceil (rect.right)), static_cast<int32_t> (std::ceil (rect.bottom))};
}

//------------------------------------------------------------------------
void writeRGBA (uint8_t* dst, const CColor& color)
{
	dst[0] = color.red;
	dst[1] = color.green;
	dst[2] = color.blue;
	dst[3] = color.alpha;
}

//------------------------------------------------------------------------
// 非 premultiplied RGBA の source-over。dst の alpha が 0 のときは color をそのまま書く。
void blendRGBA (uint8_t* dst, const CColor& color, double globalAlpha)
{
	auto srcAlpha = std::min (1., color.alpha / 255. * globalAlpha);
	if (srcAlpha <= 0.)
		return;
	auto dstAlpha = dst[3] / 255.;
	auto outAlpha = srcAlpha + dstAlpha * (1. - srcAlpha);
	const uint8_t src[3] = {color.red, color.green, color.blue};
	for (int c = 0; c < 3; ++c)
	{
		auto value = (src[c] * srcAlpha + dst[c] * dstAlpha * (1. - srcAlpha)) / outAlpha;
		dst[c] = static_cast<uint8_t> (std::lround (value));
	}
	dst[3] = static_cast<uint8_t> (std::lround (outAlpha * 255.));
}

} // namespace

//------------------------------------------------------------------------
PlatformGraphicsDevicePtr CanvasGraphicsDeviceFactory::getDeviceForScreen (
	ScreenInfo::Identifier screen) const
{
	(void)screen;
	return std::make_shared<CanvasGraphicsDevice> ();
}

//------------------------------------------------------------------------
PlatformGraphicsDeviceContextPtr CanvasGraphicsDevice::createBitmapContext (
	const PlatformBitmapPtr& bitmap) const
{
	return std::make_shared<CanvasGraphicsDeviceContext> (shared_from_this (), bitmap);
}

//------------------------------------------------------------------------
CanvasGraphicsDeviceContext::CanvasGraphicsDeviceContext (
	std::shared_ptr<const CanvasGraphicsDevice> device, PlatformBitmapPtr bitmap) noexcept
: device (std::move (device))
, bitmap (std::move (bitmap))
{
	if (auto* target = canvas ())
		clipRect = CRect (0., 0., target->getSize ().x, target->getSize ().y);
}

//------------------------------------------------------------------------
const IPlatformGraphicsDevice& CanvasGraphicsDeviceContext::getDevice () const
{
	return *device;
}

//------------------------------------------------------------------------
PlatformGraphicsPathFactoryPtr CanvasGraphicsDeviceContext::getGraphicsPathFactory () const
{
	return std::make_shared<CanvasGraphicsPathFactory> ();
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::beginDraw () const
{
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::endDraw () const
{
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawLine (LinePair line) const
{
	(void)line;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawLines (const LineList& lines) const
{
	(void)lines;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawPolygon (const PointList& polygonPointList,
                                               PlatformGraphicsDrawStyle drawStyle) const
{
	(void)polygonPointList;
	(void)drawStyle;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawRect (CRect rect, PlatformGraphicsDrawStyle drawStyle) const
{
	if (drawStyle != PlatformGraphicsDrawStyle::Stroked)
		paintRect (rect, fillColor, true);
	if (drawStyle != PlatformGraphicsDrawStyle::Filled)
		strokeRect (rect, frameColor);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawArc (CRect rect, double startAngle1, double endAngle2,
                                           PlatformGraphicsDrawStyle drawStyle) const
{
	(void)rect;
	(void)startAngle1;
	(void)endAngle2;
	(void)drawStyle;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawEllipse (CRect rect, PlatformGraphicsDrawStyle drawStyle) const
{
	(void)rect;
	(void)drawStyle;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawPoint (CPoint point, CColor color) const
{
	(void)point;
	(void)color;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawBitmap (IPlatformBitmap& bitmap, CRect dest, CPoint offset,
                                              double alpha, BitmapInterpolationQuality quality) const
{
	(void)bitmap;
	(void)dest;
	(void)offset;
	(void)alpha;
	(void)quality;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::clearRect (CRect rect) const
{
	paintRect (rect, CColor (0, 0, 0, 0), false);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawGraphicsPath (IPlatformGraphicsPath& path,
                                                    PlatformGraphicsPathDrawMode mode,
                                                    TransformMatrix* transformation) const
{
	(void)path;
	(void)mode;
	(void)transformation;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::fillLinearGradient (IPlatformGraphicsPath& path,
                                                      const IPlatformGradient& gradient,
                                                      CPoint startPoint, CPoint endPoint,
                                                      bool evenOdd, TransformMatrix* transformation) const
{
	(void)path;
	(void)gradient;
	(void)startPoint;
	(void)endPoint;
	(void)evenOdd;
	(void)transformation;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::fillRadialGradient (IPlatformGraphicsPath& path,
                                                      const IPlatformGradient& gradient,
                                                      CPoint center, CCoord radius,
                                                      CPoint originOffset, bool evenOdd,
                                                      TransformMatrix* transformation) const
{
	(void)path;
	(void)gradient;
	(void)center;
	(void)radius;
	(void)originOffset;
	(void)evenOdd;
	(void)transformation;
	return false;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::saveGlobalState () const {}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::restoreGlobalState () const {}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::setLineStyle (const CLineStyle& style) const
{
	(void)style;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::setLineWidth (CCoord width) const
{
	lineWidth = width;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::setDrawMode (CDrawMode mode) const
{
	(void)mode;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::setClipRect (CRect clip) const
{
	clipRect = clipWithinBitmap (clip);
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::setFillColor (CColor color) const
{
	fillColor = color;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::setFrameColor (CColor color) const
{
	frameColor = color;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::setGlobalAlpha (double newAlpha) const
{
	globalAlpha = newAlpha;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::setTransformMatrix (const TransformMatrix& tm) const
{
	(void)tm;
}

//------------------------------------------------------------------------
const IPlatformGraphicsDeviceContextBitmapExt* CanvasGraphicsDeviceContext::asBitmapExt () const
{
	return this;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawBitmapNinePartTiled (IPlatformBitmap& bitmap, CRect dest,
                                                           const CNinePartTiledDescription& desc,
                                                           double alpha,
                                                           BitmapInterpolationQuality quality) const
{
	(void)bitmap;
	(void)dest;
	(void)desc;
	(void)alpha;
	(void)quality;
	return false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::fillRectWithBitmap (IPlatformBitmap& bitmap, CRect srcRect,
                                                      CRect dstRect, double alpha,
                                                      BitmapInterpolationQuality quality) const
{
	(void)bitmap;
	(void)srcRect;
	(void)dstRect;
	(void)alpha;
	(void)quality;
	return false;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::blendPixel (int32_t x, int32_t y, const CColor& color) const
{
	if (auto* dst = pixelAt (x, y))
		blendRGBA (dst, color, globalAlpha);
}

//------------------------------------------------------------------------
CanvasBitmap* CanvasGraphicsDeviceContext::canvas () const noexcept
{
	return dynamic_cast<CanvasBitmap*> (bitmap.get ());
}

//------------------------------------------------------------------------
uint8_t* CanvasGraphicsDeviceContext::pixelAt (int32_t x, int32_t y) const noexcept
{
	auto* target = canvas ();
	if (!target)
		return nullptr;
	const auto& size = target->getSize ();
	auto width = static_cast<int32_t> (size.x);
	auto height = static_cast<int32_t> (size.y);
	auto clip = pixelBoxOf (clipRect);
	if (x < 0 || y < 0 || x >= width || y >= height)
		return nullptr;
	if (x < clip.x0 || y < clip.y0 || x >= clip.x1 || y >= clip.y1)
		return nullptr;
	return target->data () + (static_cast<size_t> (y) * static_cast<size_t> (width) + static_cast<size_t> (x)) * 4;
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::paintRect (const CRect& rect, const CColor& color, bool blend) const
{
	auto box = pixelBoxOf (rect);
	for (auto y = box.y0; y < box.y1; ++y)
	{
		for (auto x = box.x0; x < box.x1; ++x)
		{
			auto* dst = pixelAt (x, y);
			if (!dst)
				continue;
			if (blend)
				blendRGBA (dst, color, globalAlpha);
			else
				writeRGBA (dst, color);
		}
	}
}

//------------------------------------------------------------------------
// 枠線は lineWidth に依らず 1 px で、矩形の内側に描く。
void CanvasGraphicsDeviceContext::strokeRect (const CRect& rect, const CColor& color) const
{
	paintRect (CRect (rect.left, rect.top, rect.right, rect.top + 1.), color, true);
	paintRect (CRect (rect.left, rect.bottom - 1., rect.right, rect.bottom), color, true);
	paintRect (CRect (rect.left, rect.top + 1., rect.left + 1., rect.bottom - 1.), color, true);
	paintRect (CRect (rect.right - 1., rect.top + 1., rect.right, rect.bottom - 1.), color, true);
}

//------------------------------------------------------------------------
CRect CanvasGraphicsDeviceContext::clipWithinBitmap (CRect clip) const
{
	auto* target = canvas ();
	if (!target)
		return CRect {};
	const auto& size = target->getSize ();
	return CRect (std::max (clip.left, 0.), std::max (clip.top, 0.), std::min (clip.right, size.x),
	              std::min (clip.bottom, size.y));
}

} // VSTGUI
