// SR-39 #2107: canvas platform (wasm) の IPlatformGraphicsDevice* 実装。
// SR-50 #3260: drawRect (塗り・線 1px)・clearRect・drawString (canvas_font.cpp) は bitmap へ画素を書く。
// 他の描画命令 (drawLine・drawPolygon・drawEllipse・drawArc・drawPoint・drawBitmap・drawGraphicsPath・gradient・9 分割・bitmap 合成) は no-op で false を返す。
// 状態設定は lineWidth (1px 固定で描く)・clipRect (bitmap 境界との交差)・fillColor・frameColor・globalAlpha だけ値を保持し、他 (lineStyle・drawMode・transformMatrix・global state の save/restore) は何もしない。

#pragma once

#include "vstgui/lib/cbitmap.h"
#include "vstgui/lib/ccolor.h"
#include "vstgui/lib/cdrawdefs.h"
#include "vstgui/lib/crect.h"
#include "vstgui/lib/platform/iplatformgraphicsdevice.h"
#include <cstdint>
#include <memory>

namespace VSTGUI {

class CanvasBitmap;

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
	CanvasGraphicsDeviceContext (std::shared_ptr<const CanvasGraphicsDevice> device,
	                             PlatformBitmapPtr bitmap) noexcept;

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

	// 文字列描画 (canvas_font.cpp) から呼ぶ。1 画素を globalAlpha 付きの source-over で合成する。クリップ外・bitmap 外は書かない。
	void blendPixel (int32_t x, int32_t y, const CColor& color) const;

private:
	CanvasBitmap* canvas () const noexcept;
	uint8_t* pixelAt (int32_t x, int32_t y) const noexcept;
	void paintRect (const CRect& rect, const CColor& color, bool blend) const;
	void strokeRect (const CRect& rect, const CColor& color) const;
	CRect clipWithinBitmap (CRect clip) const;

	std::shared_ptr<const CanvasGraphicsDevice> device;
	PlatformBitmapPtr bitmap;
	mutable double globalAlpha {1.};
	mutable CColor fillColor {};
	mutable CColor frameColor {};
	mutable CCoord lineWidth {1.};
	mutable CRect clipRect {};
};

} // VSTGUI
