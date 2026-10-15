// SR-39 #2107: canvas platform (wasm) の IPlatformGraphicsDevice* 実装。
// SR-50 #3260: drawRect・clearRect を bitmap へ描く。bitmap は createBitmapContext で結線し、clip は bitmap 境界で保持する。
// SR-55 #3422: drawLine・drawLines・drawPolygon・drawEllipse・drawBitmap を bitmap へ描く。
// SR-71 #4469: 太い線の端 (cap)・接合 (join)・破線 (setLineStyle) を描き分ける。

#include "canvas_graphicsdevice.h"
#include "canvas_bitmap.h"
#include "canvas_graphicspath.h"
#include <algorithm>
#include <cmath>
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
// 太い線の形状 (線分の帯・端の円・接合の多角形) は凸多角形か円で表し、符号付き距離 (内側が負) から被覆を求める。
struct Circle
{
	CPoint center;
	double radius;
};

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
		fillPolygon (points, fillColor);
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
	auto points = transformPoints (ellipsePoints (rect));
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
// 太さ 1 かつ aliasing は 1 px の Bresenham 線 (端点は四捨五入して画素に置く)。
void CanvasGraphicsDeviceContext::plotThinLine (CPoint from, CPoint to, const CColor& color) const
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
// 太い線 (lineWidth > 1 または kAntiAliasing) を描く。線分ごとの帯と、端 (cap)・折れ目 (join) の形状の和で被覆を求める。
// 同じ線の中で画素の被覆は最大値を取るので、接合部が二重に濃くならない。
// aliasing は被覆 0/1 の二値、kAntiAliasing は境界の 1 px を線形に薄めて alpha に掛ける。
void CanvasGraphicsDeviceContext::strokeThick (const PointList& points, bool closed, const CColor& color) const
{
	const auto half = std::max (lineWidth, 1.) / 2.;
	const bool antiAliasing = drawMode.antiAliasing ();
	const auto cap = lineStyle.getLineCap ();
	const auto join = lineStyle.getLineJoin ();
	std::vector<Convex> bands;
	std::vector<Circle> discs;
	auto segmentCount = points.size () - 1 + (closed ? 1 : 0);
	for (size_t i = 0; i < segmentCount; ++i)
	{
		const auto& a = points[i];
		const auto& b = points[(i + 1) % points.size ()];
		auto len = std::hypot (b.x - a.x, b.y - a.y);
		if (len <= 0.)
			continue;
		auto nx = -(b.y - a.y) / len * half;
		auto ny = (b.x - a.x) / len * half;
		bands.push_back (convexOf ({CPoint (a.x + nx, a.y + ny), CPoint (b.x + nx, b.y + ny),
		                            CPoint (b.x - nx, b.y - ny), CPoint (a.x - nx, a.y - ny)}));
	}
	auto addCap = [&] (const CPoint& p, const CPoint& dir) {
		if (cap == CLineStyle::kLineCapRound)
			discs.push_back ({p, half});
		else if (cap == CLineStyle::kLineCapSquare)
		{
			auto nx = -dir.y * half;
			auto ny = dir.x * half;
			auto ex = dir.x * half;
			auto ey = dir.y * half;
			bands.push_back (convexOf ({CPoint (p.x + nx, p.y + ny), CPoint (p.x + nx + ex, p.y + ny + ey),
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
			discs.push_back ({p, half});
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
			bands.push_back (convexOf ({p, o1, o2}));
			return;
		}
		// miter: 2 本の外側の辺の交点を先端とする。角が鋭すぎる (比が大きい) 場合は bevel に落とす。
		auto denom = ax * by - ay * bx;
		if (std::abs (denom) < 1e-9)
		{
			bands.push_back (convexOf ({p, o1, o2}));
			return;
		}
		auto t = ((o2.x - o1.x) * by - (o2.y - o1.y) * bx) / denom;
		CPoint tip (o1.x + ax * t, o1.y + ay * t);
		auto tipDistance = std::hypot (tip.x - p.x, tip.y - p.y);
		if (tipDistance > 4. * half)
			bands.push_back (convexOf ({p, o1, o2}));
		else
			bands.push_back (convexOf ({p, o1, tip, o2}));
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
	double minX = points[0].x;
	double minY = points[0].y;
	double maxX = points[0].x;
	double maxY = points[0].y;
	for (const auto& p : points)
	{
		minX = std::min (minX, p.x);
		minY = std::min (minY, p.y);
		maxX = std::max (maxX, p.x);
		maxY = std::max (maxY, p.y);
	}
	auto box = pixelBoxOf (CRect (minX - half - 1., minY - half - 1., maxX + half + 1., maxY + half + 1.));
	auto clip = pixelBoxOf (clipRect);
	for (auto y = std::max (box.y0, clip.y0); y < std::min (box.y1, clip.y1); ++y)
	{
		for (auto x = std::max (box.x0, clip.x0); x < std::min (box.x1, clip.x1); ++x)
		{
			const CPoint c (x + 0.5, y + 0.5);
			// 符号付き距離 d (内側が負)。aliasing は d <= 0 の画素、AA は境界 1 px を線形に薄める。
			double d = 1e300;
			for (const auto& band : bands)
			{
				// 画素中心が形状の外接矩形から 1 px 以上離れていれば、被覆は 0 なので距離計算を省く。
				if (c.x < band.x0 - 1. || c.x > band.x1 + 1. || c.y < band.y0 - 1. || c.y > band.y1 + 1.)
					continue;
				d = std::min (d, signedDistance (band, c));
			}
			for (const auto& disc : discs)
				d = std::min (d, std::hypot (c.x - disc.center.x, c.y - disc.center.y) - disc.radius);
			const auto coverage = antiAliasing ? std::clamp (0.5 - d, 0., 1.) : (d <= 0. ? 1. : 0.);
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
	if (points.size () < 2)
		return;
	// 点が 2 つの閉じた線は往復になるので、閉じるのは 3 点以上のときだけにする (従来の plotLine と同じ)。
	closed = closed && points.size () > 2;
	const bool dashed = !lineStyle.getDashLengths ().empty ();
	const bool thick = lineWidth > 1. || drawMode.antiAliasing ();
	if (!dashed && thick)
	{
		strokeThick (points, closed, color);
		return;
	}
	if (dashed)
	{
		// 破線は区間ごとの開いた折れ線にして、区間の中では太さに応じて描く。
		for (const auto& run : dashRuns (points, closed, lineStyle))
		{
			if (thick)
				strokeThick (run, false, color);
			else
				for (size_t i = 0; i + 1 < run.size (); ++i)
					plotThinLine (run[i], run[i + 1], color);
		}
		return;
	}
	for (size_t i = 0; i + 1 < points.size (); ++i)
		plotThinLine (points[i], points[i + 1], color);
	if (closed && points.size () > 2)
		plotThinLine (points.back (), points.front (), color);
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
