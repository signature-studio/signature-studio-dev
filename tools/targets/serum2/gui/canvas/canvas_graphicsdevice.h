// SR-39 #2107: canvas platform (wasm) の IPlatformGraphicsDevice* 実装。
// SR-50 #3260: drawRect (塗り・線 1px)・clearRect・drawString (canvas_font.cpp) は bitmap へ画素を書く。
// SR-55 #3422: drawLine・drawLines・drawPolygon・drawEllipse・drawBitmap (1:1 転写) も bitmap へ画素を書く。
// SR-78 #4551: fillRectWithBitmap は srcRect を dstRect へ拡大縮小して描く (quality が kMedium・kHigh なら bilinear、それ以外は最近傍)。drawBitmapNinePartTiled はその 9 部分を fillRectWithBitmap で描く。
// SR-61 #4231: drawArc (弧の塗り・線)・drawPoint (1 画素)・drawGraphicsPath (path の塗り・線) も bitmap へ画素を書く。
// SR-62 #4233: fillLinearGradient・fillRadialGradient (path の内側を色停止点で塗る) も bitmap へ画素を書く。
// SR-69 #4428: transformMatrix は点・線・多角形・楕円・矩形・clearRect・bitmap の dest 位置・文字の基準点へ適用する (clipRect は CDrawContext が device 座標で渡すので変換しない)。回転・傾斜は矩形を外接矩形で近似し、拡大縮小は bitmap と文字に掛けない。
// SR-68 #4427: 線は lineWidth の太さで描く (太さ 1 かつ aliasing は従来の Bresenham)。drawMode の kAntiAliasing は線の被覆率を alpha に掛けて描く。
// 状態設定は lineWidth・drawMode・clipRect (bitmap 境界との交差)・fillColor・frameColor・globalAlpha・transformMatrix を保持し、他 (lineStyle・global state の save/restore) は何もしない。

#pragma once

#include "vstgui/lib/cbitmap.h"
#include "vstgui/lib/ccolor.h"
#include "vstgui/lib/cdrawdefs.h"
#include "vstgui/lib/cgraphicstransform.h"
#include "vstgui/lib/crect.h"
#include "vstgui/lib/platform/iplatformgraphicsdevice.h"
#include <cstdint>
#include <functional>
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

	// 文字列描画 (canvas_font.cpp) から呼ぶ。文字の基準点を transformMatrix で device 座標へ変換する。
	CPoint transformPoint (const CPoint& p) const;

private:
	CanvasBitmap* canvas () const noexcept;
	uint8_t* pixelAt (int32_t x, int32_t y) const noexcept;
	PointList transformPoints (const PointList& points) const;
	CRect deviceRect (const CRect& rect) const;
	void paintRect (const CRect& rect, const CColor& color, bool blend) const;
	void strokeRect (const CRect& rect, const CColor& color) const;
	void plotLines (const PointList& points, bool closed, const CColor& color) const;
	void fillRings (const std::vector<PointList>& rings, const CColor& color, bool evenOdd) const;
	void strokePolyline (const PointList& points, bool closed, const CColor& color) const;
	CRect clipWithinBitmap (CRect clip) const;
	void fillPathByPixel (IPlatformGraphicsPath& path, bool evenOdd, TransformMatrix* transformation,
	                      const std::function<bool (CPoint, CColor&)>& colorAt) const;
	void tileBitmap (CanvasBitmap& source, CRect srcRect, CRect dstRect, double alpha) const;

	std::shared_ptr<const CanvasGraphicsDevice> device;
	PlatformBitmapPtr bitmap;
	mutable double globalAlpha {1.};
	mutable CColor fillColor {};
	mutable CColor frameColor {};
	mutable CCoord lineWidth {1.};
	mutable CDrawMode drawMode {};
	mutable CRect clipRect {};
	mutable TransformMatrix transformMatrix {};
};

} // VSTGUI
