// SR-35 #2064: canvas platform (wasm) の IPlatformGraphicsPath 実装。

#include "canvas_graphicspath.h"
#include "vstgui/lib/cgraphicstransform.h"
#include <algorithm>
#include <cmath>

namespace VSTGUI {

//------------------------------------------------------------------------
CanvasGraphicsPath::CanvasGraphicsPath (PlatformGraphicsPathFillMode fillMode) noexcept
: fillMode (fillMode)
{}

//------------------------------------------------------------------------
void CanvasGraphicsPath::appendPoint (const CPoint& p)
{
	if (!hasSubpath)
	{
		beginSubpath (p);
		return;
	}
	points.push_back (p);
	current = p;
}

//------------------------------------------------------------------------
void CanvasGraphicsPath::beginSubpath (const CPoint& start)
{
	subpathStarts.push_back (points.size ());
	points.push_back (start);
	subpathStart = start;
	current = start;
	hasSubpath = true;
}

//------------------------------------------------------------------------
void CanvasGraphicsPath::addLine (const CPoint& to)
{
	appendPoint (to);
}

//------------------------------------------------------------------------
void CanvasGraphicsPath::addBezierCurve (const CPoint& control1, const CPoint& control2,
                                         const CPoint& end)
{
	appendPoint (control1);
	appendPoint (control2);
	appendPoint (end);
}

//------------------------------------------------------------------------
void CanvasGraphicsPath::closeSubpath ()
{
	if (hasSubpath)
	{
		appendPoint (subpathStart);
		hasSubpath = false;
	}
}

//------------------------------------------------------------------------
void CanvasGraphicsPath::addRect (const CRect& rect)
{
	beginSubpath (CPoint (rect.left, rect.top));
	points.push_back (CPoint (rect.right, rect.top));
	points.push_back (CPoint (rect.right, rect.bottom));
	points.push_back (CPoint (rect.left, rect.bottom));
	current = CPoint (rect.left, rect.bottom);
	closeSubpath ();
}

//------------------------------------------------------------------------
void CanvasGraphicsPath::addEllipse (const CRect& rect)
{
	// 楕円は外接矩形の 4 頂点で近似する (PoC 用。曲線の正確な形は後続で置き換える)。
	addRect (rect);
}

//------------------------------------------------------------------------
void CanvasGraphicsPath::addArc (const CRect& rect, double startAngle, double endAngle,
                                 bool clockwise)
{
	// 円弧は開始点と終了点の 2 頂点で近似する (PoC 用)。
	double cx = (rect.left + rect.right) / 2.;
	double cy = (rect.top + rect.bottom) / 2.;
	double rx = (rect.right - rect.left) / 2.;
	double ry = (rect.bottom - rect.top) / 2.;
	(void)clockwise;
	auto at = [&] (double deg) {
		double rad = deg * M_PI / 180.;
		return CPoint (cx + rx * std::cos (rad), cy + ry * std::sin (rad));
	};
	if (!hasSubpath)
		beginSubpath (at (startAngle));
	else
		addLine (at (startAngle));
	addLine (at (endAngle));
}

//------------------------------------------------------------------------
void CanvasGraphicsPath::finishBuilding ()
{
	hasSubpath = false;
}

//------------------------------------------------------------------------
bool CanvasGraphicsPath::hitTest (const CPoint& p, bool evenOddFilled,
                                  CGraphicsTransform* transform) const
{
	CGraphicsTransform tm;
	if (transform)
		tm = *transform;
	auto inside = false;
	auto n = points.size ();
	if (n < 3)
		return false;
	CPoint q = p;
	tm.inverse ().transform (q.x, q.y);
	for (size_t i = 0, j = n - 1; i < n; j = i++)
	{
		const auto& a = points[i];
		const auto& b = points[j];
		if (((a.y > q.y) != (b.y > q.y)) &&
		    (q.x < (b.x - a.x) * (q.y - a.y) / (b.y - a.y) + a.x))
			inside = !inside;
	}
	(void)evenOddFilled;
	return inside;
}

//------------------------------------------------------------------------
CRect CanvasGraphicsPath::getBoundingBox () const
{
	if (points.empty ())
		return CRect ();
	CRect r (points[0].x, points[0].y, points[0].x, points[0].y);
	for (const auto& p : points)
	{
		r.left = std::min (r.left, p.x);
		r.top = std::min (r.top, p.y);
		r.right = std::max (r.right, p.x);
		r.bottom = std::max (r.bottom, p.y);
	}
	return r;
}

//------------------------------------------------------------------------
PlatformGraphicsPathPtr CanvasGraphicsPathFactory::createPath (PlatformGraphicsPathFillMode fillMode)
{
	return PlatformGraphicsPathPtr (new CanvasGraphicsPath (fillMode));
}

//------------------------------------------------------------------------
PlatformGraphicsPathPtr CanvasGraphicsPathFactory::createTextPath (const PlatformFontPtr& font,
                                                                   UTF8StringPtr text)
{
	(void)font;
	(void)text;
	// 文字の輪郭は font 実装 (後続) が担う。ここでは空の path を返す。
	return createPath (PlatformGraphicsPathFillMode::Winding);
}

} // VSTGUI
