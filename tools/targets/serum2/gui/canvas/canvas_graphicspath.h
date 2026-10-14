// SR-35 #2064: canvas platform (wasm) の IPlatformGraphicsPath 実装。
// 頂点列だけを保持し、hitTest / 境界は頂点から求める (曲線は制御点を含む近似)。

#pragma once

#include "vstgui/lib/platform/iplatformgraphicspath.h"
#include <vector>

namespace VSTGUI {

//------------------------------------------------------------------------
class CanvasGraphicsPath : public IPlatformGraphicsPath
{
public:
	explicit CanvasGraphicsPath (PlatformGraphicsPathFillMode fillMode) noexcept;

	void addArc (const CRect& rect, double startAngle, double endAngle, bool clockwise) override;
	void addEllipse (const CRect& rect) override;
	void addRect (const CRect& rect) override;
	void addLine (const CPoint& to) override;
	void addBezierCurve (const CPoint& control1, const CPoint& control2, const CPoint& end) override;
	void beginSubpath (const CPoint& start) override;
	void closeSubpath () override;
	void finishBuilding () override;

	bool hitTest (const CPoint& p, bool evenOddFilled = false,
	              CGraphicsTransform* transform = nullptr) const override;
	CRect getBoundingBox () const override;

	PlatformGraphicsPathFillMode getFillMode () const override { return fillMode; }

private:
	void appendPoint (const CPoint& p);

	PlatformGraphicsPathFillMode fillMode;
	std::vector<CPoint> points;
	std::vector<size_t> subpathStarts;
	CPoint current {0., 0.};
	CPoint subpathStart {0., 0.};
	bool hasSubpath {false};
};

//------------------------------------------------------------------------
class CanvasGraphicsPathFactory : public IPlatformGraphicsPathFactory
{
public:
	PlatformGraphicsPathPtr createPath (PlatformGraphicsPathFillMode fillMode) override;
	PlatformGraphicsPathPtr createTextPath (const PlatformFontPtr& font, UTF8StringPtr text) override;
};

} // VSTGUI
