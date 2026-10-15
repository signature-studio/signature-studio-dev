> **付録**: `REPORT_EFFORT.md` §16 (#2065 / SR-36) の本文。

## 16. 2026-10-14 run (#2065 / SR-36): canvas 描画の試行 (CTextLabel のみ)

- 範囲: 受入条件 1 (CTextLabel のみの最小 harness で canvas に描画を試みる) と受入条件 3 (描画できなかった阻害要因を実測で残す)。受入条件 2 (再現手順と実測値の記録) は本節の 16-2 以降で行う。人日は出さない (§7)。
- 結論: **未達 (画素計数は計測不能: 描画先が未結線)**。CTextLabel のみの harness は em++ でコンパイル・リンク・node で実行まで通る (16-3)。描画未達の根拠は実測できる 2 点: (a) 描画命令 15 件の静的 no-op 計数 (16-5)、(b) 文字列経路 `createString` が `nullptr` で `text_width=-1` (16-4)。`nonzero_after=0` は描画経路が bitmap に結線されないため構造上の 0 で、根拠にしない。成功扱いにしない。
- XferOnOffButton: 本 run の範囲外。stub は作らず、阻害要因だけ記録する (16-6)。
- 測定 commit: `39f3702d` (コードを変えた最後の commit。harness `canvas/render_poc_main.cpp`・計数 `canvas/count_canvas_noop.py` は `4b0327ba` から不変、再現スクリプト `canvas/check_render_poc.sh` は render 行のみ変更)。本節を含む REPORT の commit は後続で、コードは変えない (16-8)。

### 16-1. 前提確認

- 子 #2064 の canvas 6 files (bitmap・graphicspath・frame・font・graphicsdevice・platformfactory) は既存の構文検査で rc=0 (16-2)。
- 描画の差し込み点: upstream は `getPlatformFactory()` を `lib/platform/platformfactory.cpp` で定義し、その本体は `MAC` / `WINDOWS` / `LINUX` の分岐のみ。wasm 分岐が無く、`em++ -fsyntax-only vstgui/lib/platform/platformfactory.cpp` は **2 error** (`VSTGUIPlatformFactory` 未定義 `platformfactory.cpp:33`、抽象クラスの生成)。このファイルは harness のコンパイル対象から外し、harness が `VSTGUI::getPlatformFactory()` を `CanvasPlatformFactory` で定義して代替した。
- 初期化: upstream `lib/vstguiinit.cpp` の `init()` は `initPlatform()` の後に `CFontDesc::init()` を呼ぶ。harness は前者を代替するため、後者 (`CFontDesc::init()`) を直接呼ぶ。これを欠くと `kNormalFont` 等が `nullptr` のまま残る (16-3 の T-c)。
- XferOnOffButton: `work/vstgui4` (vstgui4_14_3) の全ツリーで `XferOnOffButton` の宣言・定義は **0 件** (`grep -rl XferOnOffButton work/vstgui4/vstgui` の結果 0)。Xfer 固有で、vtable 由来の override は 8 関数 (和集合・上限、§10-1)。`.text` 対応付けと本体バイト数は付録 `REPORT_EFFORT_APPENDIX_2066.md` (§15) を参照。
- 素材: `toolchain-emsdk.tar.zst` の展開は `work/emsdk/emsdk/upstream/emscripten` に配置される (アーカイブのルートが `emsdk/`)。`check_*.sh` の PATH に合わせて `work/emsdk/upstream` へ symlink した。em++ 6.0.12 で `--version` rc=0 を確認。`plugins-serum2` は本 run で展開していない (XferOnOffButton の lift をしないため不要)。

### 16-2. ベースライン (検査スクリプト・測定 commit 時点の HEAD)

| 検査 | rc | 所要 (wall) | load (uptime 1 分平均、開始時) | 結果 |
|---|---:|---:|---|---|
| `canvas/check_canvas_syntax.sh` (6 files) | 0 | 5.29 s | 2.34 | 6/6 で rc=0 errors=0 |
| `check_wasm_syntax.sh` (seed 6、`-D__linux__` 補正なし) | 0 | 0.91 s | 2.05 | rc=0 errors=0 |

- 注記: 測定 commit `39f3702d` の再測定は逐次で実行した。直前の e2e の後で load が高い (2 前後)。両検査の前に `check_render_poc.sh` を実行したため、`patch 適用済み扱い` 分岐の表示が両検査に出た。`git -C work/vstgui4 diff --stat` は `vstguibase.h` 12 行追加・`platformfwd.h` 1 行変更 (patch 1 回分) で、二重適用は無い。

### 16-3. harness の実測 (compile / link / run)

`canvas/check_render_poc.sh` の 1 回の実行 (測定 commit `39f3702d`、`-O0 -g`、`xargs -P 4`):

| 段階 | rc | 所要 | 件数・値 |
|---|---:|---:|---|
| compile | — | 30.1 s (summary の secs) | 69 files (upstream 62 = `lib/*.cpp`・`lib/controls/*.cpp`・`lib/animation/*.cpp` / canvas 6 / harness 1)。ok 69/69、`error:` 行 0 |
| link (`-sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1`) | 0 | 0.31 s | 未解決シンボル **0**。出力 `render_poc.wasm` **10,573,389 B** (`-g` のデバッグ名付き)、`render_poc.js` 62,001 B |
| run (node、CommonJS 複製で実行) | 0 | 57 ms | stdout 1 行 (下記) |

- 出力行: `render_poc size=200x60 bytes=48000 nonzero_before=0 control=1 nonzero_after=0 text=Signature text_width=-1`
- 各項目: `nonzero_before`・`nonzero_after` は描画先 `CanvasBitmap` の非ゼロ画素数 (描画前・描画後)。ただし描画経路は bitmap に結線されていない (16-4) ため、`nonzero_after` は描画の有無にかかわらず 0 になる。計測不能の値。`control` は陽性対照 (bitmap へ 1 画素を直接書いたときの計数。計数ロジックの確認のみで、描画の証拠ではない)。`text_width` は `CDrawContext::getStringWidth` の戻り値。
- サイズの参考: デバッグ名を除いた (`-g` 無しで link した) probe は `render_poc.wasm` 480,441 B (`4b0327ba` 時点の手動 1 回・script の外。同じ objects を使用)。
- 判定: **画素計数は計測不能** (描画先が未結線)。`nonzero_after=0` は構造上の 0 で、描画の成否の根拠にしない。`check_render_poc.sh` の `render:` 行は計測不能として出力する (`39f3702d` で確認)。描画未達の根拠は 16-4 の (a) 静的 no-op 計数 15/15 と (b) `text_width=-1`。成功扱いにしない。

#### 16-3-1. 試行の経過 (実測した失敗と対処、再現可能)

| 試行 | 結果 (実測) | 原因 (実測・読解) | 対処 |
|---|---|---|---|
| T-a 初回 run | rc=1 (`ReferenceError: require is not defined`) | リポジトリ直下 `package.json` の `"type": "module"` により emscripten の `.js` が ESM 扱い | 同じ wasm を指す `.cjs` 複製で実行 (script) |
| T-b 初回 link | 未解決 **1 件** `Animator::removeAnimations` (`CView::~CView` 経由) | `lib/animation/*.cpp` が閉包から漏れていた | `lib/animation/*.cpp` を対象に追加 → 未解決 0 |
| T-c run | `RuntimeError: memory access out of bounds`、最上位 `CParamDisplay::CParamDisplay` (`CTextLabel` ctor 経由) | `CFontDesc::init()` 未呼出のため `kNormalFont` が `nullptr` (`controls/cparamdisplay.cpp:35` の `fontID->remember()` で trap) | harness の `main` 先頭で `CFontDesc::init()` → rc=0 |
| T-d 切り分け | T-c と同じ trap | スタック不足ではないことを確認 (`-sSTACK_SIZE=4 MiB` の link で同一 trap) | 対処なし (切り分けのみ) |

### 16-4. 描画の成否と阻害要因 (実測)

- **画素計数は計測不能 (描画先が未結線)**: 描画経路は bitmap に届かないため、画素数で描画の成否は判定できない。描画未達の根拠は実測できる 2 点: (a) 描画命令の no-op 計数 (16-5)、(b) 文字列経路の `text_width=-1` (下の 1 件目)。`nonzero_after=0` は根拠に使わない。

- **文字列経路が描画の手前で止まる**: `text_width=-1` は upstream `CDrawContext::getStringWidth` (`lib/cdrawcontext.cpp:332-342`) が `getDrawString(...).getPlatformString()` の null で `-1` を返した結果。`UTF8String::getPlatformString` は `getPlatformFactory().createString()` を呼び (`lib/cstring.cpp:190`)、canvas の `CanvasPlatformFactory::createString` は `nullptr` を返す (付録 2139 の「未対応」)。`CDrawContext::drawString (UTF8StringPtr ...)` (`lib/cdrawcontext.cpp:345-349` / `:394-397`) は platform string が null なら何もせず return するため、文字描画の呼出は canvas の `CanvasFontPainter::drawString` に届かない。
- **描画命令が全て no-op**: 16-5 の計数で描画系 15 件は全て no-op (`return false` または空)。ラスタライザが無いため、仮に文字列が届いても画素は出ない。
- **描画先が結線されていない**: `CanvasGraphicsDevice::createBitmapContext` (`canvas_graphicsdevice.cpp:17-22`) は引数の `bitmap` を使わず、常に描画先の無い context を返す。このため `nonzero_after` は描画の有無にかかわらず構造上 0 になる。bitmap への描画を計数するには、ラスタライザと bitmap の結線の両方が要る。

### 16-5. no-op の静的計数 (`canvas/count_canvas_noop.py`)

- 方法: canvas の 5 files (`canvas_graphicsdevice.cpp`・`canvas_graphicspath.cpp`・`canvas_font.cpp`・`canvas_bitmap.cpp`・`canvas_frame.cpp`) の関数本体を読み、コメントと `(void)x;` を除いた本体が空か、`return false;` `return nullptr;` `return 0.;` `return -1.;` `return {};` `return;` のみなら no-op とする。関数名の接頭辞で分類する (描画: `draw*`・`clearRect`・`fill*` (`fillMode` を除く)、状態: `set*`・`save*`・`restore*`)。静的計数のため、呼出頻度は計っていない。
- 結果 (測定 commit `39f3702d`、`4b0327ba` と同じ値):

| 区分 | 関数数 | no-op | 実装あり |
|---|---:|---:|---:|
| 描画命令 (`draw*` `clearRect` `fill*` `drawString`) | 15 | **15** | 0 |
| 状態設定 (`set*` `save*` `restore*`) | 13 | 7 | 6 |

- 描画命令 15 件の内訳: `canvas_graphicsdevice.cpp` 14 件 (`drawLine` `drawLines` `drawPolygon` `drawRect` `drawArc` `drawEllipse` `drawPoint` `drawBitmap` `clearRect` `drawGraphicsPath` `fillLinearGradient` `fillRadialGradient` `drawBitmapNinePartTiled` `fillRectWithBitmap`) と `canvas_font.cpp` の `drawString` 1 件。
- 状態設定の no-op 7 件: `setLineStyle` `setDrawMode` `setTransformMatrix` `saveGlobalState` `restoreGlobalState` (graphicsdevice) と `setMouseCursor` `setupGenericOptionMenu` (frame)。実装 6 件は `setLineWidth` `setClipRect` `setFillColor` `setFrameColor` `setGlobalAlpha` `setSize`。
- 16-4 の「描画命令は no-op」は、この計数と一致する。
- 陰性対照 (分類器が本体の変化に反応すること): リポジトリ外の一時複製で `canvas_graphicsdevice.cpp` の `setLineWidth` 本体を空に差し替えて計数すると、state は noop 7→8・impl 6→5 (`setLineWidth` が impl→noop)、draw は 15/15 のまま。

### 16-6. 未解決 (阻害要因と子 issue)

| 未解決 | 影響 (実測) | 起票先 |
|---|---|---|
| 文字列 `IPlatformString` が未実装 (`createString` が `nullptr`) | 文字描画の呼出が canvas に届かない (`text_width=-1`) | #3260 (SR-50) |
| 描画命令 15 件が全て no-op (ラスタライザ無し) | 画素計数は計測不能 (描画先未結線)。静的 no-op 15/15 が根拠 (16-4・16-5) | #3260 (SR-50) |
| `createBitmapContext` が bitmap を結線しない | 描画先が無く、画素を計数できない | #3260 (SR-50) |
| wasm の初期化経路が無い (`platformfactory.cpp` に wasm 分岐が無く `em++` 2 error。`init()` 相当の呼出口が無い) | 本 harness は `getPlatformFactory` の代替と `CFontDesc::init()` の直呼びで回避。本番の初期化経路は閉じていない | #3261 (SR-51) |
| XferOnOffButton の canvas 実装 (upstream 宣言 0 件・override 8 関数・本体は未 lift) | 受入条件 1 の XferOnOffButton を含む描画は未着手。本 run では stub を作らない | #3262 (SR-52) |

- 子 issue (起票済み・最大 3 件):
  - **A** (#3260): `[SR-50] canvas の文字列と描画命令を実装 (IPlatformString・ラスタライザ・bitmap 結線)`。受入: `check_render_poc.sh` の `nonzero_after>0` かつ `text_width>=0`。依存: #2064 の後続 (#2064 は CLOSED)。`oc_artifacts: toolchain-emsdk`。
  - **B** (#3261): `[SR-51] wasm の初期化経路 (platformfactory.cpp の WASM 分岐と init() 相当の呼出口)`。受入: harness の `getPlatformFactory` 定義と `CFontDesc::init()` 直呼びが不要になる。依存: なし (A と独立)。`oc_artifacts: toolchain-emsdk`。
  - **C** (#3262): `[SR-52] XferOnOffButton の canvas 向け実装 (Xfer 固有、バイナリから lift)`。受入: uidesc の XferOnOffButton を含む 1 view が canvas に描画される (A の後)。依存: A・#2066 (完了)。`oc_artifacts: plugins-serum2 toolchain-emsdk`。

### 16-7. 検証範囲 / 範囲外

- 範囲内 (実測): canvas 6 files の構文、wasm seed 6 の構文、harness の compile (69 files)・link・run、描画前後の画素数 (計測不能・16-4)、文字幅、no-op の静的計数。
- 範囲外: 描画の実装 (未達のまま)、XferOnOffButton の実装 (本 run の範囲外)、実 host での表示 (#623)、人日 (§7)、Windows / mac 版。
- 限界: no-op 計数は静的 (実行時の呼出頻度は未計測)。描画先が未結線のため画素数は計測できていない (16-4)。`text_width=-1` は upstream の「取得失敗」の規約を観測したもので、canvas のフォント幅 (0) を直接観測したものではない。harness の描画は `CViewContainer::draw` の 1 回だけ。

### 16-8. 測定 commit と差分

- 測定 commit: `39f3702d` (コードを変えた最後の commit)。以降の commit は本節の REPORT 文書と `docs/DOC_MAP.md` の登録のみ。
- 差分 (コード): `git diff 39f3702d HEAD -- tools/targets/serum2/gui/canvas tools/targets/serum2/gui/*.py` の出力は空 (0 行)。
- 再現: `cd tools/targets/serum2/gui && bash canvas/check_canvas_syntax.sh && bash check_wasm_syntax.sh && bash canvas/check_render_poc.sh && python3 canvas/count_canvas_noop.py`。前提は `work/vstgui4` (vstgui4_14_3 の clone) と `work/emsdk/upstream/emscripten` (`toolchain-emsdk` の展開)。終了コードは link と run の成否のみで、描画の成否は `summary.txt` の `render:` 行で判定する。
