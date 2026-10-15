> **付録**: `REPORT_EFFORT_APPENDIX_4233.md` (SR-62 / #4233) の続き。SR-77 (#4550) の fillRadialGradient の楕円形放射・停止点の合成の実装と測定。測定値の正本はこの付録。

## 1. 2026-10-16 run (#4550 / SR-77): fillRadialGradient の楕円形・停止点の合成

### 1-1. 実装範囲
- 停止点の補間を **premultiplied** で行う (`gradientColorAt`)。非 premultiplied だと alpha が途中で変わる停止点の中間色に、透明側の色が混ざる。参照実装 (`vstgui4/vstgui/lib/platform/linux/cairogradient.cpp` の cairo gradient) は cairo 既定の premultiplied 補間に従う。
- 放射の外側 (`t > 1`) は描かない。参照実装は `cairo_pattern` の既定 extend (NONE) で、半径の外を塗らない。従来は clamp して最後の停止点の色で半径の外まで塗っていた。
- 楕円形: `fillRadialGradient` の色は逆変換後の局所座標で決まるので、呼び出し側が非等方の `transformation` (例: x 方向 2 倍) を渡せば device 上で楕円になる。harness で `transformation` の経路を確かめた。楕円形を作る専用の引数は VSTGUI の API に無い。
- 判定: `check_draw_ops.sh` に楕円の広がり (中心行の横の画素数 `x` と中心列の縦の画素数 `y` の比が 1.8〜2.2) と、alpha 付き停止点の中間画素 (赤のまま alpha が 120〜136) を追加した。期待 op 数は 15 → 16。

### 1-2. 測定 commit と検証
- 測定 commit: `ecbc93cc3` (canvas のコードを変えた最後の commit)。検証は HEAD = `ecbc93cc3` で行った。
- 測定方法: 直列に 1 本ずつ実行。開始時 load (1 分平均) は各 run の直前に記録。

| 検証 | 結果 (rc) | 所要 (real) | load (開始 → 終了・1 分平均) |
|---|---|---|---|
| `check_canvas_syntax.sh` | **0** (canvas_string.cpp・platformfactory.cpp rc=0 errors=0) | 7.2 s | 2.30 → 2.20 |
| `check_draw_ops.sh` | **0** (link rc=0・compile fail=0・run rc=0・pass 23 件・fail 0 件) | 31.8 s | 1.52 → 2.50 |
| `check_render_poc.sh` | **0** (nonzero_after=12000・text_px=112) | 32.1 s | 2.20 → 2.80 |
| `check_line_width.sh` | **0** (aa_dash_less_than_solid pass) | 32.3 s | 2.80 → 3.28 |

`check_draw_ops.sh` の楕円・alpha の結果 (HEAD `ecbc93cc3`):
- `fillRadialGradient_ellipse`: nonzero=908・extent x=48 y=24 (x≈2y) → pass
- `fillRadialGradient` (円・楕円の対照): nonzero=2472 (旧 3136 は半径外を塗っていたため。半径外を塗らない修正後の値) → pass・distinct=173
- stop alpha: `r=255 g=0 b=0 a=123` (premultiplied 補間の結果) → pass。非 premultiplied に戻した場合は計算上 `b≈127` になり fail する想定だが、戻して測ってはいない。

### 1-3. コード差分
- `git diff ecbc93cc3 HEAD -- tools/targets/serum2/gui/canvas` の出力は 0 行 (測定 commit = 検証 HEAD)。この付録を含む commit は REPORT のみで canvas に触れない。

### 1-4. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 楕円形の API 上の専用引数 | VSTGUI 側の API は非等方の `transformation` で楕円を作る形。専用の引数は無い | 未起票 (仕様の判断は PM) |
| 楕円の外周の曲線 (`canvas_graphicspath.cpp` の楕円は 4 頂点近似) | 楕円の縁が多角形で近似される | 既存の未解決 (#4231 系) |
| 起動 (FLEngine) の KPI 前後 | 本 PR では動かしていない | 本 PR 本文に明記 |
