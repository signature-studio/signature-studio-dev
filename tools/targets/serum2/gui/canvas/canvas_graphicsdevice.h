// SR-39 #2107: canvas platform (wasm) の IPlatformGraphicsDevice* 実装。
// 描画命令はラスタライザを持たないため、描画系は false (未描画) を返す。
// 状態設定は lineWidth・clipRect・fillColor・frameColor・globalAlpha だけ値を保持し、他 (lineStyle・drawMode・transformMatrix・global state の save/restore) は何もしない。

#pragma once

#include "vstgui/lib/cbitmap.h"
#include "vstgui/lib/ccolor.h"
#include "vstgui/lib/cdrawdefs.h"
#include "vstgui/lib/crect.h"
#include "vstgui/lib/platform/iplatformgraphicsdevice.h"
#include <memory>

namespace VSTGUI {

//------------------------------------------------------------------------
class CanvasGraphicsDeviceFactory : public IPlatformGraphicsDeviceFactory
{
public:
	PlatformGraphicsDevicePtr getDeviceForScreen (ScreenInfo::Identifier screen) const override;
};

//------------------------------------------------------------------------
class CanvasGraphicsDevice : public IPlatformGraphicsDevice,
                             public std::enable_shared_from_this<CanvasGraphicsDevice>
{
public:
	PlatformGraphicsDeviceContextPtr createBitmapContext (
		const PlatformBitmapPtr& bitmap) const override;
};

//------------------------------------------------------------------------
class CanvasGraphicsDeviceContext : public IPlatformGraphicsDeviceContext,
                                    public IPlatformGraphicsDeviceContextBitmapExt
{
public:
	explicit CanvasGraphicsDeviceContext (std::shared_ptr<const CanvasGraphicsDevice> device) noexcept;

	const IPlatformGraphicsDevice& getDevice () const override;
	PlatformGraphicsPathFactoryPtr getGraphicsPathFactory () const override;

	bool beginDraw () const override;
	bool endDraw () const override;

	bool drawLine (LinePair line) const override;
	bool drawLines (const LineList& lines) const override;
	bool drawPolygon (const PointList& polygonPointList,
	                  PlatformGraphicsDrawStyle drawStyle) const override;
	bool drawRect (CRect rect, PlatformGraphicsDrawStyle drawStyle) const override;
	bool drawArc (CRect rect, double startAngle1, double endAngle2,
	              PlatformGraphicsDrawStyle drawStyle) const override;
	bool drawEllipse (CRect rect, PlatformGraphicsDrawStyle drawStyle) const override;
	bool drawPoint (CPoint point, CColor color) const override;
	bool drawBitmap (IPlatformBitmap& bitmap, CRect dest, CPoint offset, double alpha,
	                 BitmapInterpolationQuality quality) const override;
	bool clearRect (CRect rect) const override;
	bool drawGraphicsPath (IPlatformGraphicsPath& path, PlatformGraphicsPathDrawMode mode,
	                       TransformMatrix* transformation) const override;
	bool fillLinearGradient (IPlatformGraphicsPath& path, const IPlatformGradient& gradient,
	                         CPoint startPoint, CPoint endPoint, bool evenOdd,
	                         TransformMatrix* transformation) const override;
	bool fillRadialGradient (IPlatformGraphicsPath& path, const IPlatformGradient& gradient,
	                         CPoint center, CCoord radius, CPoint originOffset, bool evenOdd,
	                         TransformMatrix* transformation) const override;

	void saveGlobalState () const override;
	void restoreGlobalState () const override;
	void setLineStyle (const CLineStyle& style) const override;
	void setLineWidth (CCoord width) const override;
	void setDrawMode (CDrawMode mode) const override;
	void setClipRect (CRect clip) const override;
	void setFillColor (CColor color) const override;
	void setFrameColor (CColor color) const override;
	void setGlobalAlpha (double newAlpha) const override;
	void setTransformMatrix (const TransformMatrix& tm) const override;

	const IPlatformGraphicsDeviceContextBitmapExt* asBitmapExt () const override;

	bool drawBitmapNinePartTiled (IPlatformBitmap& bitmap, CRect dest,
	                              const CNinePartTiledDescription& desc, double alpha,
	                              BitmapInterpolationQuality quality) const override;
	bool fillRectWithBitmap (IPlatformBitmap& bitmap, CRect srcRect, CRect dstRect, double alpha,
	                         BitmapInterpolationQuality quality) const override;

private:
	std::shared_ptr<const CanvasGraphicsDevice> device;
	mutable double globalAlpha {1.};
	mutable CColor fillColor {};
	mutable CColor frameColor {};
	mutable CCoord lineWidth {1.};
	mutable CRect clipRect {};
};

} // VSTGUI
