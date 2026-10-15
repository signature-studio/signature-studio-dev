// SR-62 #4233: canvas platform (wasm) の IPlatformGradient 実装。色停止点 (位置と色) を保持するだけで、描画は canvas_graphicsdevice.cpp が行う。

#pragma once

#include "vstgui/lib/platform/iplatformgradient.h"

namespace VSTGUI {

//------------------------------------------------------------------------
class CanvasGradient : public IPlatformGradient
{
public:
	void setColorStops (const GradientColorStopMap& colorStops) override { stops = colorStops; }
	void addColorStop (const GradientColorStop& colorStop) override { stops.insert (colorStop); }
	const GradientColorStopMap& getColorStops () const override { return stops; }

private:
	GradientColorStopMap stops;
};

} // VSTGUI
