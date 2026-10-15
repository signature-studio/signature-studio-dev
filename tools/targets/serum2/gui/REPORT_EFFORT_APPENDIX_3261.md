> **付録**: `REPORT_EFFORT.md` §16 (#2065 / SR-36) の子 issue B (#3261 / SR-51)。親の §16-6 未解決表の「wasm の初期化経路」1 件を扱う。

既知類型との関係: 該当なし (lift の欠陥類型ではなく、PoC の初期化経路の構成)。

## 結論

- 受入条件 1〜3 を満たす。issue #3261 は範囲を縮めず `Closes #3261` で閉じる。
- 文字列・描画 (`createString` / 描画命令 / bitmap 結線) は #3260 (SR-50)、XferOnOffButton は #3262 (SR-52) で、本 PR では触らない。
- 検証起点 (変更前): `650590ed`。測定 commit (コードを変えた最後の commit): `12e5f54fb`。
- 差分 (コード): `git diff 12e5f54fb HEAD -- tools/targets/serum2/gui/canvas tools/targets/serum2/gui/check_wasm_syntax.sh tools/targets/serum2/gui/patches` の出力は 0 行。本文書の commit はコード範囲の外。
- 製品 KPI: 動かしていない。本 PR は Serum 2 GUI PoC の wasm 初期化経路のみで、FLEngine 起動 (`tools/flelift/boot`・`tools/startup`・`tools/gui/flengine`) は変更していない。

## 1. 変更前の欠陥 (実測)

- upstream `vstgui/lib/platform/platformfactory.cpp` (vstgui4_14_3 = `b1e82355`) は `MAC` / `WINDOWS` / `LINUX` の分岐しか無い。`em++ -fsyntax-only` は 2 error (`platformfactory.cpp:33:61` の `VSTGUIPlatformFactory` 未定義と、抽象クラスの生成)。vstguibase.h と platformfwd.h の wasm 分岐は適用済みの状態で測定した (`N2` 参照)。
- upstream `lib/vstguiinit.cpp` の `init()` は `initPlatform()` の後に `CFontDesc::init()` を呼ぶ。変更前の harness は `getPlatformFactory` を自前定義し、`CFontDesc::init()` を直呼びして、この経路を迂回していた (`REPORT_EFFORT_APPENDIX_2065.md` 16-1)。

## 2. 変更 (コミット `12e5f54fb`)

| ファイル | 変更 |
|---|---|
| `patches/platformfactory_emscripten.patch` (新規) | upstream `platformfactory.cpp` に `#elif WASM` 分岐を入れる。`VSTGUIPlatformFactory` = `VSTGUI::CanvasPlatformFactory` |
| `canvas/canvas_platformfactory.h` | `explicit CanvasPlatformFactory (PlatformInstanceHandle)` を追加 (`initPlatform` の `new VSTGUIPlatformFactory (instance)` に合わせる) |
| `canvas/render_poc_main.cpp` | `getPlatformFactory` の自前定義と `CFontDesc::init()` の直呼びを削除し、`init (nullptr)` を呼ぶ |
| `canvas/check_render_poc.sh` | compile 対象に `vstgui/lib/platform/platformfactory.cpp` を追加 (69 → 70 files) |
| `canvas/check_canvas_syntax.sh` | 検査対象に `platformfactory.cpp` を追加 (6 → 7 files) |
| `check_wasm_syntax.sh`・`canvas/check_canvas_syntax.sh`・`canvas/check_render_poc.sh` | patch 適用を 3 本の個別冪等適用に統一 (`git apply --reverse --check` で適用済みを判定)。2 本だけ適用済みの作業ツリーでも壊れない |

## 3. 受入条件と結果

| 受入条件 | 結果 |
|---|---|
| 1. `platformfactory.cpp` (patch 後) の `em++ -fsyntax-only` が 0 error | 達成。clean upstream から `check_canvas_syntax.sh` が 3 本の patch を適用し、7 files 全て rc=0 errors=0 |
| 2. harness から `getPlatformFactory` の自前定義と `CFontDesc::init()` の直呼びを外し、run rc=0 のまま | 達成。compile 70/70・link rc=0 (未解決シンボル 0)・run rc=0 (3 回)。出力行は変更前と同一 |
| 3. 検証の実測値 (rc・所要秒・load) を REPORT に残す | 達成 (下の §4) |

## 4. e2e の実測 (`bash canvas/check_render_poc.sh`)

| 段階 | 変更前 (`650590ed`・n=1) | 変更後 (`12e5f54fb`・n=3) |
|---|---|---|
| compile | 69/69 ok・19.967 s・開始 load 0.53 | 70/70 ok・20.22–21.25 s (min–max)・開始 load 0.70 / 1.36 / 2.54 |
| link | rc=0・未解決 0・0.537 s・wasm 10,574,897 B | rc=0・未解決 0・0.28–0.54 s・wasm 10,601,480 B (3 回同一) |
| run | rc=0・127 ms | rc=0 ×3・42–46 ms |
| 出力行 | `render_poc size=200x60 bytes=48000 nonzero_before=0 control=1 nonzero_after=0 text=Signature text_width=-1` | 同一 (3 回とも) |

- wasm の差 (+26,583 B) は `platformfactory.o` の追加と `-g` の絶対パス長による。同一内容を別の作業ディレクトリで build すると、コミット前の main 作業ツリーで 10,603,014 B、worktree で 10,601,480 B (1,534 B 差) になり、パス依存を確認した。
- 構文検査 `check_wasm_syntax.sh` (seed 6): rc=0 errors=0 (変更前後とも)。`check_canvas_syntax.sh`: 7 files 全て rc=0 errors=0 (開始 load 0.74・4.14 s)。
- 素材: `toolchain-emsdk` のみ使用 (`$ARTIFACTS_DIR/toolchain-emsdk.tar.zst` を `work/emsdk` に展開し、`work/emsdk/upstream` へ symlink)。`fl-win64` は本 PoC で読まないため未使用。

### 負の対照 (1 件ずつ壊して FAIL を確認)

| 対照 | 操作 | 結果 | 判定 |
|---|---|---|---|
| N1 | 3 本の patch をすべて未適用 (clean upstream) で `platformfactory.cpp` を `em++ -fsyntax-only` | rc=1・error 6 (`vstguibase.h:139` の `unsupported system/compiler` から連鎖) | FAIL (期待どおり) |
| N2 | vstguibase・platformfwd のみ適用 (変更前の状態) で `platformfactory.cpp` を検査 | rc=1・error 2 (`platformfactory.cpp:33:61` の `VSTGUIPlatformFactory` 未定義) | FAIL (変更前の基準と同一) |
| N3 | harness から `init (nullptr)` の呼出しだけを外す (他は `12e5f54fb` のまま) | link rc=0・run rc=1・`RuntimeError: memory access out of bounds` | FAIL (`REPORT_EFFORT_APPENDIX_2065.md` 16-3-1 T-c と同じ trap。init 経路が run を支えていることを示す) |

## 5. 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 文字列 `createString` が nullptr・描画命令が no-op・bitmap 未結線 | `text_width=-1`・描画は未達 (本 PR で変化なし) | #3260 (SR-50) |
| XferOnOffButton の canvas 実装 | 受入条件 1 の XferOnOffButton 描画は未着手 | #3262 (SR-52) |
| patch の `#include "canvas_platformfactory.h"` は `-I canvas` に依存する (裸の名前) | 製品の wasm ビルドの include path は未定義。本 harness と検査スクリプトでのみ成立する | PM 判断 (本 run では未起票) |

## 6. 検証範囲 / 範囲外

- 範囲内: canvas と `platformfactory.cpp` の構文 (clean upstream + patch)、seed 6 の構文、harness の compile・link・run (node)、負の対照 3 件。
- 範囲外: 描画の成否 (#3260)、XferOnOffButton (#3262)、実 host での表示 (#623)、Windows / mac 版、人日。

## 7. 再現手順

```sh
# cwd は tools/targets/serum2/gui。work/ は gitignore
mkdir -p work/emsdk && tar --zstd -xf "$ARTIFACTS_DIR/toolchain-emsdk.tar.zst" -C work/emsdk && ln -sfn emsdk/upstream work/emsdk/upstream
git clone --depth 1 --branch vstgui4_14_3 https://github.com/steinbergmedia/vstgui.git work/vstgui4
bash canvas/check_canvas_syntax.sh && bash check_wasm_syntax.sh && bash canvas/check_render_poc.sh
```

- 終了コードは link と run の成否。描画の成否は `work/render_poc/summary.txt` の `render:` 行で判定する (本 PoC では計測不能のまま)。
