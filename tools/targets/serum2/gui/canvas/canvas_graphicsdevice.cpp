// SR-39 #2107: canvas platform (wasm) の IPlatformGraphicsDevice* 実装。
// SR-50 #3260: drawRect・clearRect を bitmap へ描く。bitmap は createBitmapContext で結線し、clip は bitmap 境界で保持する。
// SR-55 #3422: drawLine・drawLines・drawPolygon・drawEllipse・drawBitmap を bitmap へ描く。
// SR-62 #4233: fillLinearGradient・fillRadialGradient・drawBitmapNinePartTiled・fillRectWithBitmap を bitmap へ描く。

#include "canvas_graphicsdevice.h"
#include "canvas_bitmap.h"
#include "canvas_graphicspath.h"
#include "vstgui/lib/platform/iplatformgradient.h"
#include <algorithm>
#include <cmath>
#include <iterator>
#include <vector>

namespace VSTGUI {

namespace {

//------------------------------------------------------------------------
// 楕円は外接矩形の内接多角形で近似する。辺の数は外周の大きさに比例させ、上限を置く。
PointList ellipsePoints (const CRect& rect)
{
	auto cx = (rect.left + rect.right) / 2.;
	auto cy = (rect.top + rect.bottom) / 2.;
	auto rx = (rect.right - rect.left) / 2.;
	auto ry = (rect.bottom - rect.top) / 2.;
	auto count = static_cast<int32_t> (std::clamp (2. * (rx + ry), 16., 1024.));
	PointList points;
	points.reserve (static_cast<size_t> (count));
	for (int32_t i = 0; i < count; ++i)
	{
		auto rad = 2. * M_PI * i / count;
		points.push_back (CPoint (cx + rx * std::cos (rad), cy + ry * std::sin (rad)));
	}
	return points;
}

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
// 色停止点 (位置 0〜1) の間を線形に補間する。stops は空でないこと。
CColor gradientColorAt (const GradientColorStopMap& stops, double t)
{
	t = std::clamp (t, 0., 1.);
	auto next = stops.lower_bound (t);
	if (next == stops.end ())
		return std::prev (next)->second;
	if (next == stops.begin ())
		return next->second;
	auto prev = std::prev (next);
	auto span = next->first - prev->first;
	auto f = span > 0. ? (t - prev->first) / span : 0.;
	auto mix = [f] (uint8_t a, uint8_t b) { return static_cast<uint8_t> (std::lround (a + (b - a) * f)); };
	return CColor (mix (prev->second.red, next->second.red), mix (prev->second.green, next->second.green),
	               mix (prev->second.blue, next->second.blue), mix (prev->second.alpha, next->second.alpha));
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
	plotLine (line.first, line.second, frameColor);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawLines (const LineList& lines) const
{
	for (const auto& line : lines)
		plotLine (line.first, line.second, frameColor);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawPolygon (const PointList& polygonPointList,
                                               PlatformGraphicsDrawStyle drawStyle) const
{
	if (polygonPointList.size () < 2)
		return false;
	if (drawStyle != PlatformGraphicsDrawStyle::Stroked)
		fillPolygon (polygonPointList, fillColor);
	if (drawStyle != PlatformGraphicsDrawStyle::Filled)
		strokePolyline (polygonPointList, true, frameColor);
	return true;
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
	auto points = ellipsePoints (rect);
	if (drawStyle != PlatformGraphicsDrawStyle::Stroked)
		fillPolygon (points, fillColor);
	if (drawStyle != PlatformGraphicsDrawStyle::Filled)
		strokePolyline (points, true, frameColor);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawPoint (CPoint point, CColor color) const
{
	(void)point;
	(void)color;
	return false;
}

//------------------------------------------------------------------------
// 1:1 で転写する (dest の左上に offset から始まる画素を置く)。拡大縮小と quality は未対応で、quality は無視する。
bool CanvasGraphicsDeviceContext::drawBitmap (IPlatformBitmap& bitmap, CRect dest, CPoint offset,
                                              double alpha, BitmapInterpolationQuality quality) const
{
	(void)quality;
	auto* source = dynamic_cast<CanvasBitmap*> (&bitmap);
	if (!source)
		return false;
	const auto& sourceSize = source->getSize ();
	auto srcWidth = static_cast<int32_t> (sourceSize.x);
	auto srcHeight = static_cast<int32_t> (sourceSize.y);
	auto box = pixelBoxOf (dest);
	auto srcX0 = static_cast<int32_t> (offset.x);
	auto srcY0 = static_cast<int32_t> (offset.y);
	for (auto y = box.y0; y < box.y1; ++y)
	{
		for (auto x = box.x0; x < box.x1; ++x)
		{
			auto sx = srcX0 + (x - box.x0);
			auto sy = srcY0 + (y - box.y0);
			if (sx < 0 || sy < 0 || sx >= srcWidth || sy >= srcHeight)
				continue;
			const uint8_t* src = source->data () + (static_cast<size_t> (sy) * srcWidth + sx) * 4;
			if (src[3] == 0)
				continue;
			auto* dst = pixelAt (x, y);
			if (!dst)
				continue;
			const CColor color (src[0], src[1], src[2], src[3]);
			blendRGBA (dst, color, alpha * globalAlpha);
		}
	}
	return true;
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
	const auto& stops = gradient.getColorStops ();
	if (stops.empty ())
		return false;
	auto dx = endPoint.x - startPoint.x;
	auto dy = endPoint.y - startPoint.y;
	auto len2 = dx * dx + dy * dy;
	fillPathByPixel (path, evenOdd, transformation, [&] (CPoint p, CColor& color) {
		auto t = len2 > 0. ? ((p.x - startPoint.x) * dx + (p.y - startPoint.y) * dy) / len2 : 0.;
		color = gradientColorAt (stops, t);
		return true;
	});
	return true;
}

//------------------------------------------------------------------------
// originOffset だけ焦点をずらした放射状。色は焦点からの距離 / radius で求める (楕円形の放射は未対応)。
bool CanvasGraphicsDeviceContext::fillRadialGradient (IPlatformGraphicsPath& path,
                                                      const IPlatformGradient& gradient,
                                                      CPoint center, CCoord radius,
                                                      CPoint originOffset, bool evenOdd,
                                                      TransformMatrix* transformation) const
{
	const auto& stops = gradient.getColorStops ();
	if (stops.empty () || radius <= 0.)
		return false;
	auto focal = CPoint (center.x + originOffset.x, center.y + originOffset.y);
	fillPathByPixel (path, evenOdd, transformation, [&] (CPoint p, CColor& color) {
		color = gradientColorAt (stops, std::hypot (p.x - focal.x, p.y - focal.y) / radius);
		return true;
	});
	return true;
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
	drawMode = mode;
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
// 9 分割の各部分を、元画像の対応部分から dest の対応部分へ 1:1 タイルで置く。拡大縮小と quality は未対応で無視する。
bool CanvasGraphicsDeviceContext::drawBitmapNinePartTiled (IPlatformBitmap& bitmap, CRect dest,
                                                           const CNinePartTiledDescription& desc,
                                                           double alpha,
                                                           BitmapInterpolationQuality quality) const
{
	(void)quality;
	auto* source = dynamic_cast<CanvasBitmap*> (&bitmap);
	if (!source)
		return false;
	const auto& size = source->getSize ();
	CRect srcParts[CNinePartTiledDescription::kPartCount];
	CRect dstParts[CNinePartTiledDescription::kPartCount];
	desc.calcRects (CRect (0., 0., size.x, size.y), srcParts);
	desc.calcRects (dest, dstParts);
	for (auto i = 0; i < static_cast<int> (CNinePartTiledDescription::kPartCount); ++i)
		tileBitmap (*source, srcParts[i], dstParts[i], alpha);
	return true;
}

//------------------------------------------------------------------------
// srcRect を繰り返して dstRect を塗る (タイル塗り)。拡大縮小は未対応で、quality は無視する。
bool CanvasGraphicsDeviceContext::fillRectWithBitmap (IPlatformBitmap& bitmap, CRect srcRect,
                                                      CRect dstRect, double alpha,
                                                      BitmapInterpolationQuality quality) const
{
	(void)quality;
	auto* source = dynamic_cast<CanvasBitmap*> (&bitmap);
	if (!source)
		return false;
	tileBitmap (*source, srcRect, dstRect, alpha);
	return true;
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
// path の内側の画素ごとに colorAt で色を決めて source-over で置く。colorAt は path と同じ座標 (transformation の逆変換後) の点を受け取る。
void CanvasGraphicsDeviceContext::fillPathByPixel (IPlatformGraphicsPath& path, bool evenOdd,
                                                   TransformMatrix* transformation,
                                                   const std::function<bool (CPoint, CColor&)>& colorAt) const
{
	auto bounds = path.getBoundingBox ();
	if (transformation)
		transformation->transform (bounds);
	auto box = pixelBoxOf (bounds);
	for (auto y = box.y0; y < box.y1; ++y)
	{
		for (auto x = box.x0; x < box.x1; ++x)
		{
			auto* dst = pixelAt (x, y);
			if (!dst)
				continue;
			CPoint p (x + 0.5, y + 0.5);
			if (!path.hitTest (p, evenOdd, transformation))
				continue;
			CPoint local = p;
			if (transformation)
				transformation->inverse ().transform (local);
			CColor color;
			if (colorAt (local, color))
				blendRGBA (dst, color, globalAlpha);
		}
	}
}

//------------------------------------------------------------------------
// source の srcRect を左上から繰り返して dstRect へ 1:1 で置く。srcRect の整数化した範囲を 1 タイルとする。
void CanvasGraphicsDeviceContext::tileBitmap (CanvasBitmap& source, CRect srcRect, CRect dstRect,
                                              double alpha) const
{
	const auto& sourceSize = source.getSize ();
	auto srcWidth = static_cast<int32_t> (sourceSize.x);
	auto srcHeight = static_cast<int32_t> (sourceSize.y);
	auto tile = pixelBoxOf (srcRect);
	auto tileWidth = tile.x1 - tile.x0;
	auto tileHeight = tile.y1 - tile.y0;
	if (tileWidth <= 0 || tileHeight <= 0)
		return;
	auto box = pixelBoxOf (dstRect);
	for (auto y = box.y0; y < box.y1; ++y)
	{
		auto sy = tile.y0 + (y - box.y0) % tileHeight;
		if (sy < 0 || sy >= srcHeight)
			continue;
		for (auto x = box.x0; x < box.x1; ++x)
		{
			auto sx = tile.x0 + (x - box.x0) % tileWidth;
			if (sx < 0 || sx >= srcWidth)
				continue;
			const uint8_t* src = source.data () + (static_cast<size_t> (sy) * srcWidth + sx) * 4;
			if (src[3] == 0)
				continue;
			auto* dst = pixelAt (x, y);
			if (!dst)
				continue;
			blendRGBA (dst, CColor (src[0], src[1], src[2], src[3]), alpha * globalAlpha);
		}
	}
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
// 太さ 1 かつ aliasing は 1 px の Bresenham 線 (端点は四捨五入して画素に置く)。それ以外は plotThickLine で描く。
void CanvasGraphicsDeviceContext::plotLine (CPoint from, CPoint to, const CColor& color) const
{
	if (lineWidth > 1. || drawMode.antiAliasing ())
	{
		plotThickLine (from, to, color);
		return;
	}
	auto x0 = static_cast<int32_t> (std::lround (from.x));
	auto y0 = static_cast<int32_t> (std::lround (from.y));
	auto x1 = static_cast<int32_t> (std::lround (to.x));
	auto y1 = static_cast<int32_t> (std::lround (to.y));
	auto dx = std::abs (x1 - x0);
	auto dy = -std::abs (y1 - y0);
	auto sx = x0 < x1 ? 1 : -1;
	auto sy = y0 < y1 ? 1 : -1;
	auto err = dx + dy;
	while (true)
	{
		blendPixel (x0, y0, color);
		if (x0 == x1 && y0 == y1)
			break;
		auto e2 = 2 * err;
		if (e2 >= dy)
		{
			err += dy;
			x0 += sx;
		}
		if (e2 <= dx)
		{
			err += dx;
			y0 += sy;
		}
	}
}

//------------------------------------------------------------------------
// 線分から画素中心までの距離で被覆を求める。太さ lineWidth の半分以内を塗る (端は丸い)。
// aliasing は被覆 0/1 の二値、kAntiAliasing は境界の 1 px を線形に薄めて alpha に掛ける。
void CanvasGraphicsDeviceContext::plotThickLine (CPoint from, CPoint to, const CColor& color) const
{
	const auto half = std::max (lineWidth, 1.) / 2.;
	const bool antiAliasing = drawMode.antiAliasing ();
	const auto dx = to.x - from.x;
	const auto dy = to.y - from.y;
	const auto lengthSquared = dx * dx + dy * dy;
	auto box = pixelBoxOf (CRect (std::min (from.x, to.x) - half - 1., std::min (from.y, to.y) - half - 1.,
	                              std::max (from.x, to.x) + half + 1., std::max (from.y, to.y) + half + 1.));
	auto clip = pixelBoxOf (clipRect);
	for (auto y = std::max (box.y0, clip.y0); y < std::min (box.y1, clip.y1); ++y)
	{
		for (auto x = std::max (box.x0, clip.x0); x < std::min (box.x1, clip.x1); ++x)
		{
			const auto px = x + 0.5 - from.x;
			const auto py = y + 0.5 - from.y;
			const auto t = lengthSquared > 0. ? std::clamp ((px * dx + py * dy) / lengthSquared, 0., 1.) : 0.;
			const auto ex = px - t * dx;
			const auto ey = py - t * dy;
			const auto distance = std::sqrt (ex * ex + ey * ey);
			const auto coverage = antiAliasing ? std::clamp (half + 0.5 - distance, 0., 1.)
			                                   : (distance <= half ? 1. : 0.);
			if (coverage <= 0.)
				continue;
			if (auto* dst = pixelAt (x, y))
				blendRGBA (dst, color, globalAlpha * coverage);
		}
	}
}

//------------------------------------------------------------------------
// 画素中心 (y + 0.5) で偶奇則の走査線塗りを行う。辺は閉じているものとして扱う。
void CanvasGraphicsDeviceContext::fillPolygon (const PointList& points, const CColor& color) const
{
	if (points.size () < 3)
		return;
	double minY = points[0].y;
	double maxY = points[0].y;
	for (const auto& p : points)
	{
		minY = std::min (minY, p.y);
		maxY = std::max (maxY, p.y);
	}
	std::vector<double> crossings;
	for (auto y = static_cast<int32_t> (std::floor (minY)); y < static_cast<int32_t> (std::ceil (maxY)); ++y)
	{
		auto yc = y + 0.5;
		crossings.clear ();
		for (size_t i = 0, j = points.size () - 1; i < points.size (); j = i++)
		{
			const auto& a = points[j];
			const auto& b = points[i];
			if ((a.y <= yc) == (b.y <= yc))
				continue;
			crossings.push_back (a.x + (yc - a.y) * (b.x - a.x) / (b.y - a.y));
		}
		std::sort (crossings.begin (), crossings.end ());
		for (size_t k = 0; k + 1 < crossings.size (); k += 2)
		{
			auto xStart = static_cast<int32_t> (std::ceil (crossings[k] - 0.5));
			auto xEnd = static_cast<int32_t> (std::ceil (crossings[k + 1] - 0.5));
			for (auto x = xStart; x < xEnd; ++x)
				blendPixel (x, y, color);
		}
	}
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::strokePolyline (const PointList& points, bool closed,
                                                  const CColor& color) const
{
	for (size_t i = 0; i + 1 < points.size (); ++i)
		plotLine (points[i], points[i + 1], color);
	if (closed && points.size () > 2)
		plotLine (points.back (), points.front (), color);
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
