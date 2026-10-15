// SR-39 #2107: canvas platform (wasm) の IPlatformGraphicsDevice* 実装。
// SR-50 #3260: drawRect・clearRect を bitmap へ描く。bitmap は createBitmapContext で結線し、clip は bitmap 境界で保持する。
// SR-55 #3422: drawLine・drawLines・drawPolygon・drawEllipse・drawBitmap を bitmap へ描く。
// SR-78 #4551: fillRectWithBitmap の拡大縮小と bilinear、drawBitmapNinePartTiled の 9 部分拡大縮小を入れる。
// SR-62 #4233: fillLinearGradient・fillRadialGradient・drawBitmapNinePartTiled・fillRectWithBitmap を bitmap へ描く。
// SR-71 #4469: 太い線の端 (cap)・接合 (join)・破線 (setLineStyle) を plotLines の被覆に載せて描き分ける。

#include "canvas_graphicsdevice.h"
#include "canvas_bitmap.h"
#include "canvas_graphicspath.h"
#include "vstgui/lib/platform/iplatformgradient.h"
#include <algorithm>
#include <array>
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
// 円弧は角度 (ラジアン) を正の向きに掃引する。開始角と終了角の間の弧長に比例して辺数を取り、上限を置く。
PointList arcPoints (const CRect& rect, double startAngle, double endAngle)
{
	auto cx = (rect.left + rect.right) / 2.;
	auto cy = (rect.top + rect.bottom) / 2.;
	auto rx = (rect.right - rect.left) / 2.;
	auto ry = (rect.bottom - rect.top) / 2.;
	auto sweep = endAngle - startAngle;
	while (sweep < 0.)
		sweep += 2. * M_PI;
	sweep = std::min (sweep, 2. * M_PI);
	auto count = static_cast<int32_t> (std::clamp (std::ceil (sweep * (rx + ry)), 2., 1024.));
	PointList points;
	points.reserve (static_cast<size_t> (count) + 1);
	for (int32_t i = 0; i <= count; ++i)
	{
		auto rad = startAngle + sweep * i / count;
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
// 線の形状 (線分の帯・端の円・接合の多角形) は凸多角形か円で表し、符号付き距離 (内側が負) で内外を判定する。
struct Convex
{
	std::vector<CPoint> normals; // 外向き単位法線
	std::vector<double> offsets; // 法線と辺上の点との内積
	double x0;
	double y0;
	double x1;
	double y1;
};

//------------------------------------------------------------------------
Convex convexOf (const std::vector<CPoint>& vertices)
{
	Convex s {};
	CPoint centroid (0., 0.);
	for (const auto& v : vertices)
	{
		centroid.x += v.x / static_cast<double> (vertices.size ());
		centroid.y += v.y / static_cast<double> (vertices.size ());
	}
	s.x0 = s.x1 = vertices[0].x;
	s.y0 = s.y1 = vertices[0].y;
	for (size_t i = 0; i < vertices.size (); ++i)
	{
		const auto& a = vertices[i];
		const auto& b = vertices[(i + 1) % vertices.size ()];
		s.x0 = std::min (s.x0, a.x);
		s.y0 = std::min (s.y0, a.y);
		s.x1 = std::max (s.x1, a.x);
		s.y1 = std::max (s.y1, a.y);
		auto len = std::hypot (b.x - a.x, b.y - a.y);
		if (len < 1e-9)
			continue;
		CPoint n ((b.y - a.y) / len, -(b.x - a.x) / len);
		if (n.x * (centroid.x - a.x) + n.y * (centroid.y - a.y) > 0.)
			n = CPoint (-n.x, -n.y);
		s.normals.push_back (n);
		s.offsets.push_back (n.x * a.x + n.y * a.y);
	}
	return s;
}

//------------------------------------------------------------------------
double signedDistance (const Convex& s, CPoint p)
{
	if (s.normals.empty ())
		return 1e300;
	double d = -1e300;
	for (size_t i = 0; i < s.normals.size (); ++i)
		d = std::max (d, s.normals[i].x * p.x + s.normals[i].y * p.y - s.offsets[i]);
	return d;
}

//------------------------------------------------------------------------
// 形状 1 つ。disc は中心と半径の円、そうでなければ凸多角形 (poly)。poly の外接矩形は disc でも入れる。
struct Shape
{
	bool disc;
	CPoint center;
	double radius;
	Convex poly;
};

//------------------------------------------------------------------------
Shape discShape (CPoint center, double radius)
{
	Shape s {};
	s.disc = true;
	s.center = center;
	s.radius = radius;
	s.poly.x0 = center.x - radius;
	s.poly.y0 = center.y - radius;
	s.poly.x1 = center.x + radius;
	s.poly.y1 = center.y + radius;
	return s;
}

//------------------------------------------------------------------------
Shape polyShape (const std::vector<CPoint>& vertices)
{
	Shape s {};
	s.poly = convexOf (vertices);
	return s;
}

//------------------------------------------------------------------------
bool insideShape (const Shape& s, CPoint p)
{
	if (s.disc)
		return std::hypot (p.x - s.center.x, p.y - s.center.y) <= s.radius;
	return signedDistance (s.poly, p) <= 0.;
}

//------------------------------------------------------------------------
// 非 premultiplied 画素を α で重み付けして足し合わせる (bilinear の 4 近傍用)。
struct SampleAccumulator
{
	double r {0.};
	double g {0.};
	double b {0.};
	double a {0.};

	void add (const uint8_t* px, double weight)
	{
		auto alpha = px[3] / 255. * weight;
		r += px[0] * alpha;
		g += px[1] * alpha;
		b += px[2] * alpha;
		a += alpha;
	}
};

//------------------------------------------------------------------------
uint8_t toByte (double value)
{
	return static_cast<uint8_t> (std::clamp (std::lround (value), 0L, 255L));
}

//------------------------------------------------------------------------
template <typename F>
void forEachBresenhamPixel (CPoint from, CPoint to, F&& visit)
{
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
		visit (x0, y0);
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
void writeRGBA (uint8_t* dst, const CColor& color)
{
	dst[0] = color.red;
	dst[1] = color.green;
	dst[2] = color.blue;
	dst[3] = color.alpha;
}

//------------------------------------------------------------------------
// 色停止点 (位置 0〜1) の間を線形に補間する。stops は空でないこと。
// 補間は premultiplied の値で行う (Cairo の参照実装と同じ)。alpha が途中で変わる停止点で色が濁らないようにするため。
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
	auto premultiplied = [] (const CColor& c) {
		auto a = c.alpha / 255.;
		return std::array<double, 4> {c.red * a, c.green * a, c.blue * a, static_cast<double> (c.alpha)};
	};
	auto p = premultiplied (prev->second);
	auto n = premultiplied (next->second);
	std::array<double, 4> mixed {};
	for (size_t i = 0; i < 4; ++i)
		mixed[i] = p[i] + (n[i] - p[i]) * f;
	auto alpha = mixed[3];
	if (alpha <= 0.)
		return CColor (0, 0, 0, 0);
	auto unpremultiply = [alpha] (double v) { return toByte (v * 255. / alpha); };
	return CColor (unpremultiply (mixed[0]), unpremultiply (mixed[1]), unpremultiply (mixed[2]), toByte (alpha));
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
	strokePolyline ({transformPoint (line.first), transformPoint (line.second)}, false, frameColor);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawLines (const LineList& lines) const
{
	for (const auto& line : lines)
		strokePolyline ({transformPoint (line.first), transformPoint (line.second)}, false, frameColor);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawPolygon (const PointList& polygonPointList,
                                               PlatformGraphicsDrawStyle drawStyle) const
{
	if (polygonPointList.size () < 2)
		return false;
	auto points = transformPoints (polygonPointList);
	if (drawStyle != PlatformGraphicsDrawStyle::Stroked)
		fillRings ({points}, fillColor, true);
	if (drawStyle != PlatformGraphicsDrawStyle::Filled)
		strokePolyline (points, true, frameColor);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawRect (CRect rect, PlatformGraphicsDrawStyle drawStyle) const
{
	auto r = deviceRect (rect);
	if (drawStyle != PlatformGraphicsDrawStyle::Stroked)
		paintRect (r, fillColor, true);
	if (drawStyle != PlatformGraphicsDrawStyle::Filled)
		strokeRect (r, frameColor);
	return true;
}

//------------------------------------------------------------------------
// 塗りは弧と弦で囲んだ領域 (cairo_arc の fill と同じ)。線は弧だけを描く。
bool CanvasGraphicsDeviceContext::drawArc (CRect rect, double startAngle1, double endAngle2,
                                           PlatformGraphicsDrawStyle drawStyle) const
{
	auto points = transformPoints (arcPoints (rect, startAngle1, endAngle2));
	if (drawStyle != PlatformGraphicsDrawStyle::Stroked)
		fillRings ({points}, fillColor, true);
	if (drawStyle != PlatformGraphicsDrawStyle::Filled)
		strokePolyline (points, false, frameColor);
	return true;
}

//------------------------------------------------------------------------
bool CanvasGraphicsDeviceContext::drawEllipse (CRect rect, PlatformGraphicsDrawStyle drawStyle) const
{
	auto points = transformPoints (ellipsePoints (rect));
	if (drawStyle != PlatformGraphicsDrawStyle::Stroked)
		fillRings ({points}, fillColor, true);
	if (drawStyle != PlatformGraphicsDrawStyle::Filled)
		strokePolyline (points, true, frameColor);
	return true;
}

//------------------------------------------------------------------------
// 1 画素を、端点と同じく四捨五入した位置に置く。
bool CanvasGraphicsDeviceContext::drawPoint (CPoint point, CColor color) const
{
	auto device = transformPoint (point);
	blendPixel (static_cast<int32_t> (std::lround (device.x)), static_cast<int32_t> (std::lround (device.y)),
	            color);
	return true;
}

//------------------------------------------------------------------------
// 1:1 で転写する (dest の左上に offset から始まる画素を置く)。拡大縮小と quality は未対応で、quality は無視する。
// dest の位置だけ transformMatrix で変換する (拡大縮小は掛けない)。
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
	auto origin = transformPoint (CPoint (dest.left, dest.top));
	auto box = pixelBoxOf (CRect (origin.x, origin.y, origin.x + dest.getWidth (), origin.y + dest.getHeight ()));
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
	paintRect (deviceRect (rect), CColor (0, 0, 0, 0), false);
	return true;
}

//------------------------------------------------------------------------
// 全 subpath を対象にする。塗りは Filled (非零) / FilledEvenOdd (偶奇) で切り替える。線は各 subpath を閉じずに描く (閉じる場合は path 側で終点を置く)。
bool CanvasGraphicsDeviceContext::drawGraphicsPath (IPlatformGraphicsPath& path,
                                                    PlatformGraphicsPathDrawMode mode,
                                                    TransformMatrix* transformation) const
{
	auto* source = dynamic_cast<CanvasGraphicsPath*> (&path);
	if (!source)
		return false;
	auto subpaths = source->subpaths ();
	if (transformation)
	{
		for (auto& subpath : subpaths)
		{
			for (auto& p : subpath)
				transformation->transform (p.x, p.y);
		}
	}
	for (auto& subpath : subpaths)
		subpath = transformPoints (subpath);
	if (mode != PlatformGraphicsPathDrawMode::Stroked)
		fillRings (subpaths, fillColor, mode == PlatformGraphicsPathDrawMode::FilledEvenOdd);
	else
	{
		for (const auto& subpath : subpaths)
			strokePolyline (subpath, false, frameColor);
	}
	return true;
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
// originOffset だけ焦点をずらした放射状。色は焦点からの距離 / radius で求める。楕円形は transformation の非等方スケールで作る (色は逆変換後の局所座標で決まるため、device 上では楕円になる)。
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
		auto t = std::hypot (p.x - focal.x, p.y - focal.y) / radius;
		if (t > 1.)
			return false; // 半径の外は描かない (Cairo の参照実装は extend NONE)
		color = gradientColorAt (stops, t);
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
	lineStyle = style;
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
	transformMatrix = tm;
}

//------------------------------------------------------------------------
const IPlatformGraphicsDeviceContextBitmapExt* CanvasGraphicsDeviceContext::asBitmapExt () const
{
	return this;
}

//------------------------------------------------------------------------
// 9 分割の各部分を fillRectWithBitmap で拡大縮小して描く (部分ごとの src → dst)。
bool CanvasGraphicsDeviceContext::drawBitmapNinePartTiled (IPlatformBitmap& bitmap, CRect dest,
                                                           const CNinePartTiledDescription& desc,
                                                           double alpha,
                                                           BitmapInterpolationQuality quality) const
{
	auto* source = dynamic_cast<CanvasBitmap*> (&bitmap);
	if (!source)
		return false;
	const CRect bitmapBounds (0., 0., source->getSize ().x, source->getSize ().y);
	CRect srcRects[CNinePartTiledDescription::kPartCount];
	CRect dstRects[CNinePartTiledDescription::kPartCount];
	desc.calcRects (bitmapBounds, srcRects);
	desc.calcRects (dest, dstRects);
	for (size_t i = 0; i < CNinePartTiledDescription::kPartCount; ++i)
		fillRectWithBitmap (bitmap, srcRects[i], dstRects[i], alpha, quality);
	return true;
}

//------------------------------------------------------------------------
// srcRect を dstRect (device 座標は deviceRect) へ引き伸ばして描く。kMedium・kHigh は bilinear、それ以外は最近傍。
// 画素中心を source 座標へ写す。source の参照範囲は srcRect を bitmap 境界で切ったもの。
bool CanvasGraphicsDeviceContext::fillRectWithBitmap (IPlatformBitmap& bitmap, CRect srcRect,
                                                      CRect dstRect, double alpha,
                                                      BitmapInterpolationQuality quality) const
{
	auto* source = dynamic_cast<CanvasBitmap*> (&bitmap);
	if (!source || srcRect.isEmpty () || dstRect.isEmpty ())
		return false;
	const auto& sourceSize = source->getSize ();
	const auto range = pixelBoxOf (CRect (std::max (srcRect.left, 0.), std::max (srcRect.top, 0.),
	                                      std::min (srcRect.right, sourceSize.x),
	                                      std::min (srcRect.bottom, sourceSize.y)));
	if (range.x0 >= range.x1 || range.y0 >= range.y1)
		return false;
	const auto dev = deviceRect (dstRect);
	if (dev.getWidth () <= 0. || dev.getHeight () <= 0.)
		return false;
	const auto box = pixelBoxOf (dev);
	const auto scaleX = srcRect.getWidth () / dev.getWidth ();
	const auto scaleY = srcRect.getHeight () / dev.getHeight ();
	const bool bilinear = quality == BitmapInterpolationQuality::kMedium ||
	                      quality == BitmapInterpolationQuality::kHigh;
	const auto clampX = [&] (int32_t x) { return std::clamp (x, range.x0, range.x1 - 1); };
	const auto clampY = [&] (int32_t y) { return std::clamp (y, range.y0, range.y1 - 1); };
	const auto pixelOf = [&] (int32_t x, int32_t y) {
		return source->data () + (static_cast<size_t> (y) * static_cast<size_t> (sourceSize.x) + x) * 4;
	};
	for (auto y = box.y0; y < box.y1; ++y)
	{
		const auto v = srcRect.top + (y + 0.5 - dev.top) * scaleY;
		for (auto x = box.x0; x < box.x1; ++x)
		{
			auto* dst = pixelAt (x, y);
			if (!dst)
				continue;
			const auto u = srcRect.left + (x + 0.5 - dev.left) * scaleX;
			SampleAccumulator sample;
			if (bilinear)
			{
				const auto fx = u - 0.5;
				const auto fy = v - 0.5;
				const auto x0 = static_cast<int32_t> (std::floor (fx));
				const auto y0 = static_cast<int32_t> (std::floor (fy));
				const auto tx = fx - x0;
				const auto ty = fy - y0;
				for (int32_t dy = 0; dy < 2; ++dy)
				{
					for (int32_t dx = 0; dx < 2; ++dx)
					{
						const auto weight = (dx ? tx : 1. - tx) * (dy ? ty : 1. - ty);
						sample.add (pixelOf (clampX (x0 + dx), clampY (y0 + dy)), weight);
					}
				}
			}
			else
			{
				sample.add (pixelOf (clampX (static_cast<int32_t> (std::floor (u))),
				                     clampY (static_cast<int32_t> (std::floor (v)))),
				            1.);
			}
			if (sample.a <= 0.)
				continue;
			const CColor color (toByte (sample.r / sample.a), toByte (sample.g / sample.a),
			                    toByte (sample.b / sample.a), toByte (sample.a * 255.));
			blendRGBA (dst, color, alpha * globalAlpha);
		}
	}
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

namespace {

//------------------------------------------------------------------------
// 折れ線を破線の区間 (on の部分) に分け、それぞれを開いた折れ線として返す。
// 区間の並びは dashLengths を繰り返す。要素数が奇数のときは 2 周で 1 サイクル (SVG と同じ)。
std::vector<PointList> dashRuns (const PointList& points, bool closed, const CLineStyle& style)
{
	const auto& dashes = style.getDashLengths ();
	const size_t count = dashes.size ();
	const size_t cycle = count % 2 ? 2 * count : count;
	double cycleLength = 0.;
	for (size_t k = 0; k < cycle; ++k)
		cycleLength += std::max (dashes[k % count], 0.);
	std::vector<PointList> runs;
	if (cycleLength <= 0.)
		return runs;
	auto phase = std::fmod (style.getDashPhase (), cycleLength);
	if (phase < 0.)
		phase += cycleLength;
	size_t k = 0;
	double remaining = std::max (dashes[0], 0.);
	while (phase > 0.)
	{
		if (phase >= remaining)
		{
			phase -= remaining;
			k = (k + 1) % cycle;
			remaining = std::max (dashes[k % count], 0.);
		}
		else
		{
			remaining -= phase;
			phase = 0.;
		}
	}
	bool on = k % 2 == 0;
	PointList current;
	auto push = [&] (const CPoint& p) {
		if (current.empty () || current.back ().x != p.x || current.back ().y != p.y)
			current.push_back (p);
	};
	// 区間の境界で on/off を切り替える。on から off では現在の区間を runs へ出す。
	auto toggle = [&] (const CPoint& p) {
		if (on)
		{
			push (p);
			if (current.size () >= 2)
				runs.push_back (current);
			current.clear ();
		}
		else
		{
			current.clear ();
			current.push_back (p);
		}
		on = !on;
	};
	if (on)
		current.push_back (points.front ());
	const size_t segments = closed ? points.size () : points.size () - 1;
	for (size_t i = 0; i < segments; ++i)
	{
		const auto& a = points[i];
		const auto& b = points[(i + 1) % points.size ()];
		auto length = std::hypot (b.x - a.x, b.y - a.y);
		if (length <= 0.)
			continue;
		auto ux = (b.x - a.x) / length;
		auto uy = (b.y - a.y) / length;
		double pos = 0.;
		while (pos < length)
		{
			if (remaining <= 0.)
			{
				k = (k + 1) % cycle;
				remaining = std::max (dashes[k % count], 0.);
				toggle (CPoint (a.x + ux * pos, a.y + uy * pos));
				continue;
			}
			auto step = std::min (length - pos, remaining);
			pos += step;
			remaining -= step;
		}
		if (on)
			push (b);
	}
	if (on && current.size () >= 2)
		runs.push_back (current);
	return runs;
}

} // namespace

//------------------------------------------------------------------------
// 太さ 1 かつ aliasing は 1 px の Bresenham 線 (端点は四捨五入して画素に置く)。画素は集めてから 1 回ずつ合成する。
// 辺どうしが共有する頂点や交差の画素を二重に合成しない (plotLines の bit mask と同じ考え方)。
void CanvasGraphicsDeviceContext::plotThinPolyline (const PointList& points, bool closed,
                                                    const CColor& color) const
{
	const auto segmentCount = closed ? points.size () : points.size () - 1;
	std::vector<std::pair<int32_t, int32_t>> pixels;
	for (size_t i = 0; i < segmentCount; ++i)
	{
		forEachBresenhamPixel (points[i], points[(i + 1) % points.size ()],
		                       [&] (int32_t x, int32_t y) { pixels.emplace_back (x, y); });
	}
	std::sort (pixels.begin (), pixels.end ());
	pixels.erase (std::unique (pixels.begin (), pixels.end ()), pixels.end ());
	for (const auto& [x, y] : pixels)
		blendPixel (x, y, color);
}

//------------------------------------------------------------------------
// 太い線 (lineWidth > 1 または kAntiAliasing) の被覆。線分ごとの帯・端 (cap)・接合 (join) の形状の和を、
// 画素ごとに標本点 (AA は 4x4・aliasing は 1 点) の bit mask で求め、被覆 (立った標本の割合) を alpha に掛けて 1 回だけ合成する。
// 形状どうしが重なっても標本は 1 回だけ立つので、接合部で二重に濃くならない。
void CanvasGraphicsDeviceContext::plotLines (const PointList& points, bool closed, const CColor& color) const
{
	if (points.size () < 2)
		return;
	const auto half = std::max (lineWidth, 1.) / 2.;
	const int sub = drawMode.antiAliasing () ? 4 : 1;
	const auto cap = lineStyle.getLineCap ();
	const auto join = lineStyle.getLineJoin ();
	std::vector<Shape> shapes;
	const auto segmentCount = closed ? points.size () : points.size () - 1;
	for (size_t i = 0; i < segmentCount; ++i)
	{
		const auto& a = points[i];
		const auto& b = points[(i + 1) % points.size ()];
		auto len = std::hypot (b.x - a.x, b.y - a.y);
		if (len <= 0.)
			continue;
		auto nx = -(b.y - a.y) / len * half;
		auto ny = (b.x - a.x) / len * half;
		shapes.push_back (polyShape ({CPoint (a.x + nx, a.y + ny), CPoint (b.x + nx, b.y + ny),
		                              CPoint (b.x - nx, b.y - ny), CPoint (a.x - nx, a.y - ny)}));
	}
	// 端: dir は線の外側へ向かう単位ベクトル。round は端の円、square は半幅ぶん延ばした矩形、butt は何もしない。
	auto addCap = [&] (const CPoint& p, const CPoint& dir) {
		if (cap == CLineStyle::kLineCapRound)
			shapes.push_back (discShape (p, half));
		else if (cap == CLineStyle::kLineCapSquare)
		{
			auto nx = -dir.y * half;
			auto ny = dir.x * half;
			auto ex = dir.x * half;
			auto ey = dir.y * half;
			shapes.push_back (polyShape ({CPoint (p.x + nx, p.y + ny), CPoint (p.x + nx + ex, p.y + ny + ey),
			                              CPoint (p.x - nx + ex, p.y - ny + ey), CPoint (p.x - nx, p.y - ny)}));
		}
	};
	if (!closed && points.size () >= 2)
	{
		const auto& a = points.front ();
		const auto& b = points[1];
		const auto& y = points[points.size () - 2];
		const auto& z = points.back ();
		auto l0 = std::hypot (b.x - a.x, b.y - a.y);
		auto l1 = std::hypot (z.x - y.x, z.y - y.y);
		if (l0 > 0.)
			addCap (a, CPoint ((a.x - b.x) / l0, (a.y - b.y) / l0));
		if (l1 > 0.)
			addCap (z, CPoint ((z.x - y.x) / l1, (z.y - y.y) / l1));
	}
	// 接合: 頂点 p で前後の線分をつなぐ。外側の隙間を、miter は三角形の先端、bevel は直線、round は円で埋める。
	auto addJoin = [&] (const CPoint& prev, const CPoint& p, const CPoint& next) {
		if (join == CLineStyle::kLineJoinRound)
		{
			shapes.push_back (discShape (p, half));
			return;
		}
		auto ax = p.x - prev.x;
		auto ay = p.y - prev.y;
		auto bx = next.x - p.x;
		auto by = next.y - p.y;
		auto la = std::hypot (ax, ay);
		auto lb = std::hypot (bx, by);
		if (la <= 0. || lb <= 0.)
			return;
		ax /= la;
		ay /= la;
		bx /= lb;
		by /= lb;
		// 外側の側を求める: 曲がる方向の反対側。
		auto cross = ax * by - ay * bx;
		auto sgn = cross > 0. ? -1. : 1.;
		CPoint n1 (-ay * half * sgn, ax * half * sgn);
		CPoint n2 (-by * half * sgn, bx * half * sgn);
		CPoint o1 (p.x + n1.x, p.y + n1.y);
		CPoint o2 (p.x + n2.x, p.y + n2.y);
		if (join == CLineStyle::kLineJoinBevel)
		{
			shapes.push_back (polyShape ({p, o1, o2}));
			return;
		}
		// miter: 2 本の外側の辺の交点を先端とする。角が鋭すぎる (比が大きい) 場合は bevel に落とす。
		auto denom = ax * by - ay * bx;
		if (std::abs (denom) < 1e-9)
		{
			shapes.push_back (polyShape ({p, o1, o2}));
			return;
		}
		auto t = ((o2.x - o1.x) * by - (o2.y - o1.y) * bx) / denom;
		CPoint tip (o1.x + ax * t, o1.y + ay * t);
		auto tipDistance = std::hypot (tip.x - p.x, tip.y - p.y);
		if (tipDistance > 4. * half)
			shapes.push_back (polyShape ({p, o1, o2}));
		else
			shapes.push_back (polyShape ({p, o1, tip, o2}));
	};
	if (closed)
	{
		for (size_t i = 0; i < points.size (); ++i)
		{
			const auto& prev = points[(i + points.size () - 1) % points.size ()];
			const auto& next = points[(i + 1) % points.size ()];
			addJoin (prev, points[i], next);
		}
	}
	else
	{
		for (size_t i = 1; i + 1 < points.size (); ++i)
			addJoin (points[i - 1], points[i], points[i + 1]);
	}
	if (shapes.empty ())
		return;
	// 形状の外接矩形の和を描画範囲にする (miter の先端は点の外接矩形の外へ出る)。
	double minX = shapes[0].poly.x0;
	double minY = shapes[0].poly.y0;
	double maxX = shapes[0].poly.x1;
	double maxY = shapes[0].poly.y1;
	for (const auto& shape : shapes)
	{
		minX = std::min (minX, shape.poly.x0);
		minY = std::min (minY, shape.poly.y0);
		maxX = std::max (maxX, shape.poly.x1);
		maxY = std::max (maxY, shape.poly.y1);
	}
	auto box = pixelBoxOf (CRect (minX - 1., minY - 1., maxX + 1., maxY + 1.));
	auto clip = pixelBoxOf (clipRect);
	box.x0 = std::max (box.x0, clip.x0);
	box.y0 = std::max (box.y0, clip.y0);
	box.x1 = std::min (box.x1, clip.x1);
	box.y1 = std::min (box.y1, clip.y1);
	if (box.x0 >= box.x1 || box.y0 >= box.y1)
		return;
	const auto width = static_cast<size_t> (box.x1 - box.x0);
	const uint16_t fullMask = static_cast<uint16_t> ((1u << (sub * sub)) - 1u);
	std::vector<uint16_t> covered (width * static_cast<size_t> (box.y1 - box.y0), 0);
	auto cover = [&] (int32_t x, int32_t y) -> uint16_t& {
		return covered[static_cast<size_t> (y - box.y0) * width + static_cast<size_t> (x - box.x0)];
	};
	for (const auto& shape : shapes)
	{
		auto shapeBox = pixelBoxOf (CRect (shape.poly.x0 - 1., shape.poly.y0 - 1., shape.poly.x1 + 1.,
		                                   shape.poly.y1 + 1.));
		for (auto y = std::max (shapeBox.y0, box.y0); y < std::min (shapeBox.y1, box.y1); ++y)
		{
			for (auto x = std::max (shapeBox.x0, box.x0); x < std::min (shapeBox.x1, box.x1); ++x)
			{
				auto& bits = cover (x, y);
				if (bits == fullMask)
					continue;
				for (int sy = 0; sy < sub; ++sy)
				{
					for (int sx = 0; sx < sub; ++sx)
					{
						const CPoint p (x + (sx + 0.5) / sub, y + (sy + 0.5) / sub);
						if (insideShape (shape, p))
							bits |= static_cast<uint16_t> (1u << (sy * sub + sx));
					}
				}
			}
		}
	}
	for (auto y = box.y0; y < box.y1; ++y)
	{
		for (auto x = box.x0; x < box.x1; ++x)
		{
			const uint16_t bits = cover (x, y);
			if (bits == 0)
				continue;
			auto* dst = pixelAt (x, y);
			if (!dst)
				continue;
			int hits = 0;
			for (int b = 0; b < sub * sub; ++b)
				hits += (bits >> b) & 1;
			blendRGBA (dst, color, globalAlpha * (hits / double (sub * sub)));
		}
	}
}

//------------------------------------------------------------------------
// 画素中心 (y + 0.5) で走査線塗りを行う。各輪郭の辺は閉じているものとして扱い、輪郭どうしの交点はまとめて数える。
// evenOdd が false のときは非零巻き数則 (Winding)。
void CanvasGraphicsDeviceContext::fillRings (const std::vector<PointList>& rings,
                                             const CColor& color, bool evenOdd) const
{
	bool any = false;
	double minY = 0.;
	double maxY = 0.;
	for (const auto& ring : rings)
	{
		if (ring.size () < 3)
			continue;
		for (const auto& p : ring)
		{
			minY = any ? std::min (minY, p.y) : p.y;
			maxY = any ? std::max (maxY, p.y) : p.y;
			any = true;
		}
	}
	if (!any)
		return;
	std::vector<std::pair<double, int>> crossings;
	for (auto y = static_cast<int32_t> (std::floor (minY)); y < static_cast<int32_t> (std::ceil (maxY)); ++y)
	{
		auto yc = y + 0.5;
		crossings.clear ();
		for (const auto& points : rings)
		{
			if (points.size () < 3)
				continue;
			for (size_t i = 0, j = points.size () - 1; i < points.size (); j = i++)
			{
				const auto& a = points[j];
				const auto& b = points[i];
				if ((a.y <= yc) == (b.y <= yc))
					continue;
				auto x = a.x + (yc - a.y) * (b.x - a.x) / (b.y - a.y);
				crossings.emplace_back (x, b.y > a.y ? 1 : -1);
			}
		}
		std::sort (crossings.begin (), crossings.end ());
		int winding = 0;
		double spanStart = 0.;
		for (const auto& [x, dir] : crossings)
		{
			auto wasInside = evenOdd ? (winding & 1) != 0 : winding != 0;
			winding = evenOdd ? winding + 1 : winding + dir;
			auto isInside = evenOdd ? (winding & 1) != 0 : winding != 0;
			if (!wasInside && isInside)
				spanStart = x;
			else if (wasInside && !isInside)
			{
				auto xStart = static_cast<int32_t> (std::ceil (spanStart - 0.5));
				auto xEnd = static_cast<int32_t> (std::ceil (x - 0.5));
				for (auto px = xStart; px < xEnd; ++px)
					blendPixel (px, y, color);
			}
		}
	}
}

//------------------------------------------------------------------------
void CanvasGraphicsDeviceContext::strokePolyline (const PointList& points, bool closed,
                                                  const CColor& color) const
{
	if (points.size () < 2)
		return;
	// 点が 2 つの閉じた線は往復になるので、閉じるのは 3 点以上のときだけにする (従来の plotLine と同じ)。
	closed = closed && points.size () > 2;
	const bool dashed = !lineStyle.getDashLengths ().empty ();
	const bool thick = lineWidth > 1. || drawMode.antiAliasing ();
	if (!dashed)
	{
		if (thick)
			plotLines (points, closed, color);
		else
			plotThinPolyline (points, closed, color);
		return;
	}
	// 破線は区間ごとの開いた折れ線にして、区間の中では太さに応じて描く。
	for (const auto& run : dashRuns (points, closed, lineStyle))
	{
		if (thick)
			plotLines (run, false, color);
		else
			plotThinPolyline (run, false, color);
	}
}

//------------------------------------------------------------------------
CPoint CanvasGraphicsDeviceContext::transformPoint (const CPoint& p) const
{
	CPoint q (p);
	transformMatrix.transform (q);
	return q;
}

//------------------------------------------------------------------------
PointList CanvasGraphicsDeviceContext::transformPoints (const PointList& points) const
{
	PointList result;
	result.reserve (points.size ());
	for (const auto& p : points)
		result.push_back (transformPoint (p));
	return result;
}

//------------------------------------------------------------------------
// 回転・傾斜があるときは変換後の 4 隅の外接矩形を取る。
CRect CanvasGraphicsDeviceContext::deviceRect (const CRect& rect) const
{
	auto a = transformPoint (CPoint (rect.left, rect.top));
	auto b = transformPoint (CPoint (rect.right, rect.top));
	auto c = transformPoint (CPoint (rect.left, rect.bottom));
	auto d = transformPoint (CPoint (rect.right, rect.bottom));
	return CRect (std::min ({a.x, b.x, c.x, d.x}), std::min ({a.y, b.y, c.y, d.y}),
	              std::max ({a.x, b.x, c.x, d.x}), std::max ({a.y, b.y, c.y, d.y}));
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
