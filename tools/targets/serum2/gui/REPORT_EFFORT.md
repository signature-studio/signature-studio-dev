# REPORT — [SR-19 #1351] GUI 戦略 (a) 全 lift / (b) upstream VSTGUI 再構築: 対象量の実測

- 日付: 2026-10-14 / 親: #68 (SR-7) / 前段: `gui/REPORT.md` §5 (推奨 (b)・工数未実測)、`gui/REPORT.md` §8〜§11 (版同定)
- 範囲: 対象量 (関数数・バイト・クラス数・template 数) と PoC 境界の見積り材料。**人日の工数は測っていない** (下記 §4)。
- 既知類型: 該当なし (lift 前の静的確認)。

## 0. 結論 (先出し)

| 観点 | 実測 |
|---|---|
| (b) で置換が要る Xfer 固有 view クラス | **91 種 / 594 参照** (uidesc の 103 種のうち、upstream VSTGUI 14.3 に宣言が無い分) |
| (b) で upstream をそのまま使える view | 12 種 / 223 参照 (`CViewContainer` `CTextLabel` `CView` `CControl` 等) |
| sub-controller | 61 種 / 159 参照。**upstream 宣言は 0 件** (全て Xfer 固有) |
| template の依存 | 123 件のうち、Xfer 固有 class も sub-controller も無いのは **3 件** (`ArpBrowser` `ClipBrowser` `Empty`)。**120 件が Xfer 側の置換を要する** |
| (a) 全 lift の対象 | GUI closure 7,138 関数 / 4.21 MB (`gui/REPORT.md` §5-1 の保存値と一致。ただし静的・過大近似の値) |
| 判定 | 推奨 (b) は**維持**。ただし (b) の置換対象は「Xfer 固有 87 種の差し替え」ではなく「uidesc の 91 種 + sub-controller 61 種」で、想定より広い |

## 1. 再現手順と入力確認

```sh
# tools/targets/serum2/ を cwd・work/ は gitignore
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" -C work --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -owork/exe_extract work/Install_Xfer_Serum2_2.1.5.exe
cp -f 'work/exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' work/Serum2_win64.vst3
sha256sum work/Serum2_win64.vst3   # 501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283
python3 gui/extract_uidesc.py work/Serum2_win64.vst3 work/uidesc.json   # 2,093,822 B
git clone --depth 1 --branch vstgui4_14_3 https://github.com/steinbergmedia/vstgui.git work/vstgui4
python3 gui/strategy_count.py work/uidesc.json out/rtti_classes.txt > work/gui_strategy_count.txt
python3 gui/effort_measure.py work/uidesc.json work/vstgui4/vstgui > work/effort_measure.txt
```

- 入力 sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` は `gui/REPORT.md` §9-1 の値 (前版 `f0212bab` で照合)。本 HEAD では `plugins-serum2` が未展開のため再照合していない。
- 依存: `pefile` `capstone` `zstandard` (venv `work/venv`、`uv venv` + `uv pip install`)。
- upstream: tag `vstgui4_14_3` (commit `b1e82355`) を depth 1 で clone。14.0〜14.3 のどれかは未確定 (`gui/REPORT.md` §11) のため、14.3 の宣言照合は**版の差に対して頑健な範囲のみ**使う (宣言の有無は 14.0〜14.3 で同一と仮定。仮定は未検証)。

## 2. 実測

### 2-1. uidesc (入力 2,093,822 B)

| 項目 | 値 |
|---|---|
| templates / bitmaps | 123 / 344 |
| view class 参照 | 817 件 / 103 種 |
| upstream 14.3 に宣言あり | 12 種 / 223 参照 |
| upstream 14.3 に宣言なし (置換対象) | **91 種 / 594 参照** |
| うち C 接頭辞だが upstream に無い | `CBitmapTextEdit` `CHoverKickButton` `CHoverKickButton2` `COneShotRockerSwitch` `CPUGraph` (5 種。C 接頭辞で VSTGUI 標準と見なすと誤る) |
| Xfer 固有 class の属性キー (和集合) | 240 種 |
| sub-controller | 61 種 / 159 参照。upstream 宣言 0 件 |

前 run (`gui/REPORT.md` §5-1) の「C 接頭辞 16 種 = VSTGUI 標準」は、実際は 11 種 (宣言あり) + 5 種 (宣言なし) で、接頭辞推定は誤る。以後は宣言照合の値を正とする。

### 2-2. template の依存

| 区分 | 件数 |
|---|---|
| upstream のみ・sub-controller 無し | 3 (`ArpBrowser` `ClipBrowser` `Empty`) |
| Xfer 固有 class または sub-controller を 1 つ以上含む | **120** |

→ template 単位では「置換せず upstream で済む」は 3 件のみ。(b) の作業は view 単位の差し替えでなく、ほぼ全 template に及ぶ。

### 2-3. (a) 全 lift の対象 (`out/closure_summary.json`・保存値)

| 項目 | 値 |
|---|---|
| GUI root / closure | 836 / 7,138 関数 (4.21 MB) |
| GUI のみ | 3,217 関数 (1.92 MB) |
| DSP と共有 | 3,921 関数 (2.29 MB) |

(a) は GUI closure 全体を lift するため、DSP との共有 3,921 関数の切り分けが要る。

### 2-4. upstream VSTGUI 14.3 の規模 (`work/vstgui4/vstgui`、テスト除外)

| 区分 | 行数 | バイト |
|---|---|---|
| 全 cpp/h/mm | 151,152 行 | 4,842,372 B |
| うち `platform/` (Win32・Direct2D・mac・linux 等) | 33,845 行 | 1,036,519 B |
| platform 以外 | 117,307 行 | 3,805,853 B |

- Xfer バイナリが参照するソースパス 34 件は 14.3 の tree に **34/34 存在** (`gui/REPORT.md` §9 の「33/33」は `..` を除いた数え方の違い)。
- 再構築で canvas platform を新規実装する場合、置換すべきは `platform/` 以外の描画依存 (`lib/` の draw 系) と、`platform/` 相当の canvas 実装。canvas 側の対象量は本測定の範囲外 (未実測)。

### 2-5. PoC 境界 (推奨の最小単位)

- `CTextLabel` (uidesc 26 参照・属性キー 34) + `XferOnOffButton` (43 参照・属性キー 15) は、uidesc 上で `CViewContainer` と組み合わせた template が存在する。
- 最小 template の例: `GranularOscBottomDefault` (4 class: `CViewContainer` `HoverView` `VectorKnob` `XferOnOffButton`)。`Voicing` (4 class: `BitmapTextParamDisp` `CTextLabel` `CViewContainer` `XferOnOffButton`) は `HoverView` を含まない。ただし `BitmapTextParamDisp` (Xfer 固有) の置換を要するため、upstream のみでは閉じない。
- **`{CTextLabel, XferOnOffButton, CViewContainer}` だけで閉じる sub-controller 無しの template は 3 件** (`ArpBrowser` `ClipBrowser` `Empty`) で、いずれも `XferOnOffButton` を含まない。つまり PoC は「uidesc 1 template の完全実体化」ではなく「Xfer 固有 1 種 (`XferOnOffButton`) を含む最小 template の部分実体化」になる (`CTextLabel` は upstream 宣言あり)。

## 3. 判定

- **(b) の推奨は維持。** ただし前 run の見込みより対象は広い: (b) の置換対象は Xfer 固有 91 種 (594 参照) + sub-controller 61 種 (159 参照)、影響 template は 120 / 123。
- (a) と比べた対象量の差は、関数数 (a: GUI closure 7,138 / b: 置換は Xfer 側 view 91 種 + sub-controller 61 種。関数数は未実測) で示せない。(b) の関数数は**未実測**のため、比較は「対象の種類数」でしか言えない。
- 確度: 中。依然として (a)(b) の**工数 (人日)** は未測定。

## 4. 未実測 (本 run の範囲外)

| 項目 | 状態 | 起票先 |
|---|---|---|
| (a) の工数 (人日) | 未測定 (対象量のみ実測) | 本 issue の残 |
| (b) の工数 (人日・canvas platform 新規実装を含む) | 未測定 | 本 issue の残 |
| (b) の置換側の関数数・バイト数 (Xfer 91 種の実装量) | 未測定 (uidesc 側の種数・参照数のみ) | PoC 後に起票 |
| VSTGUI の版 14.0〜14.3 の確定 | 未確定 (`gui/REPORT.md` §11) | #1350 (SR-18) |
| canvas platform の対象量 | 未測定 | PoC 後に起票 |
| 実 host で template 表示を確認する動的検証 | 未実施 | #623 (SR-2c) / GUI lift 時 |

## 5. 検証

- 以下の §2 の値は**前版 `f0212bab` での測定値**。本 HEAD では再実行していない (入力 `work/uidesc.json` は `plugins-serum2` の展開が要る)。
- 前版では、入力の sha256 は `gui/REPORT.md` §9-1 の値と一致 (§1)。`strategy_count.py` の出力は、コミット済みの `out/gui_strategy_count.txt` と一致 (`diff`)。
- 前版の `effort_measure.py` の出力 (`work/effort_measure.txt`): 所要 0.93 s real (逐次, load 未計測)。
- ネガティブコントロール: C 接頭辞 ヒューリスティックが誤る 5 種 (`CBitmapTextEdit` 等) を宣言照合で検出。宣言照合の偽陰性は、前方宣言のみのクラス (`CKickButton` `COnOffButton` 等) で一度生じたため、宣言の正規表現は `class|struct <名>\b` の単語一致に限定して再照合済み (`gui/effort_measure.py` の `upstream_has`)。
- 範囲外: 実 VSTGUI 実行、wasm/canvas 上の表示、工数 (人日)、mac 版。

## 6. PoC 境界の対象量 (2026-10-14 run, #1351 残件)

PoC = 「CTextLabel 系 + XferOnOffButton 等 1 view を canvas 描画」(受入条件 2)。起点は upstream の宣言ファイルで、`#include "..."` を再帰的に辿る (`gui/effort_poc.py`)。

| 区分 | ファイル | 行数 | バイト |
|---|---|---|---|
| include 閉包 (`platform/` 除く) | 55 | 13,373 | 408,005 |
| `platform/` (閉包内) | 13 | 897 | 29,435 |
| 合計 | 68 | 14,270 | 437,440 |

- 起点 (seed): `CTextLabel` `CViewContainer` `CView` `CControl` `CBitmap` `CDrawContext` の宣言ファイル。
- canvas 側で実装が要る純粋仮想インタフェース (`lib/platform/iplatform*.h` と `platformfactory.h`、計 16 ファイル): **159 関数**。`effort_poc.py` が出力する (コメント除去後に `virtual ... = 0;` を数える。`grep -cE '=\s*0\s*;'` の行数 (frame 25 / graphicsdevice 31 / platformfactory 20 / graphicspath 13 / font 7 / framecallback 10) と一致を確認済み)。
  - 内訳 (ファイル別): graphicsdevice 31 / frame 25 / platformfactory 20 / graphicspath 13 / textedit 17 / framecallback 10 / openglview 10 / bitmap 7 / font 7 / viewlayer 6 / gradient 3 / resourceinputstream 3 / timer 3 / fileselector 2 / optionmenu 1 / string 1。
  - 前版の「133 関数・内訳 frame 22 / graphicsdevice 22 …」は、コードから再現できなかったため撤回する。
- PoC で最低限要る関数の部分集合 (bitmap / font / graphicspath / graphicsdevice / frame / factory の 6 ファイル) の関数数は、上記の内訳から合計 **103 関数** (bitmap 7 + font 7 + graphicspath 13 + graphicsdevice 31 + frame 25 + factory 20)。ただし「PoC で最低限要る 6 種」の選定は**本 run の判断で、閉包が実際に要求するかは未検証** (リンク・実行で確定する)。選定根拠: 「CTextLabel 系 + XferOnOffButton を canvas に描く」に直接使う描画・文字・ビットマップ・フレーム・ファクトリ。
- Xfer 固有は `XferOnOffButton` の 1 種のみ (uidesc 上 43 参照)。`CTextLabel` は upstream VSTGUI に宣言がある (§0 の upstream 12 種に含まれる) ため、置換対象ではない (uidesc 上 26 参照)。`XferOnOffButton` の**関数数・バイトは未実測**。Xfer の .text 上での対応付けが要る (`gui/REPORT.md` §5-1 の注記どおり)。

## 7. 工数 (人日) について (本 run の判断)

- 工数は**本 run では推定値を出さない**。入力として §2・§6 の対象量は揃った。
- 換算係数 (行/人日・関数/人日) を本リポジトリは持たない。係数を置くと、実測でない精度が数字に混入する。
- 受入条件 1 の「工数の根拠」は、対象量 (本 REPORT §2 / §6) で根拠の材料は示した。人日そのものは未達として残し、判断はユーザに委ねる。

## 8. 測定 commit

- 測定 commit: `0444a3f3` (`gui/effort_poc.py` に純粋仮想の計数を追加した commit。コードを変えた最後の commit)。初版 `f0212bab` は include 閉包のみを計数していた。
- `git diff 0444a3f3 HEAD -- tools/targets/serum2/gui/*.py` の出力: 空 (差分 0)。REPORT 文書のみの後続 commit は測定対象のコードを変えない。
- §6 の純粋仮想の計数は `0444a3f3` の `effort_poc.py` で測定。同一入力の 2 回実行で出力が一致 (`cmp` で確認)。
- `effort_measure.py` / `strategy_count.py` の §2 の値は前版 `f0212bab` での測定値。本 HEAD では再実行していない (入力 `work/uidesc.json` は `plugins-serum2` の展開が要る)。

## 9. 2026-10-14 run (#1738): (b) 置換側の対象量と PoC の canvas 描画の試行

- 範囲: 受入条件 1 (置換側の対象量) の残り (バイナリ側の vtable 由来の関数数)、受入条件 2 (最小 PoC の canvas 描画) の試行。人日は出さない (§7)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` から取り出した `Serum2_win64.vst3` (sha256 `501e7bb3…`, §1 の値と一致)。upstream `vstgui4_14_3` (depth 1)。
- 実行環境: `tools/targets/serum2/gui/work/` (gitignore)。venv は `uv venv` + `pefile capstone zstandard`。emsdk 6.0.12 (`toolchain-emsdk` 展開)。

### 9-1. 再測定 (HEAD の入力で再実行)

| スクリプト | 結果 | 前版 §2 との比較 |
|---|---|---|
| `extract_uidesc.py` | 2,093,822 B | 一致 |
| `strategy_count.py` | `out/gui_strategy_count.txt` と diff 0 | 一致 |
| `effort_measure.py` | 0.90 s real | 値は §2 と一致 (91 種 / 594 参照、upstream 宣言 12 種 / 223 参照、sub-controller 61 種 / 159 参照、Xfer 依存 template 120 / 123) |
| `effort_poc.py` | include 閉包 68 files / 14,270 行 / 437,440 B、純粋仮想 159 関数 (16 files) | §6 と一致 |

### 9-2. 受入条件 1: Xfer 固有 2 種の vtable 由来の関数数 (`vtable_measure.py`)

- 方法: PE の MSVC RTTI (`.?AV<cls>@<ns>@@`) → COL → vtable を辿り、vtable の各スロットのうち `.text` を指すものを数える。
- 限界: 継承元の関数を含む (vtable に展開されているため)。関数本体のバイト数は Ghidra が要るため未測定。
- 結果:

| クラス | TypeDescriptor | vtable 数 | vtable ごとのスロット数 / 異なる関数数 |
|---|---|---|---|
| `VSTGUI::CTextLabel` (upstream 宣言あり) | 1 | 3 | 105 / 90、2 / 2、3 / 3 |
| `XferOnOffButton` (Xfer 固有) | 1 | 4 | 85 / 74、2 / 2、3 / 3、3 / 2 |

- 解釈: 数値は継承込みの上限値であり、置換側の実数は未確定。upstream 宣言ありの `CTextLabel` (置換対象ではない) も同じ方法で 90 関数と数えられており、継承分が大半を占めることを示す。`XferOnOffButton` の 74 は「継承元との差分で override のみを数えた値」ではない。vtable 間の和集合は未算出 (vtable ごとの値のみ記録)。本体サイズは未測定。
- 次の測定: 継承元 vtable との差分 (override のみの数) は §10 で実測済み。

### 9-3. 受入条件 2: 最小 PoC の canvas 描画の試行

- emsdk: `toolchain-emsdk` の展開で `emcc` 6.0.12 が動くことを確認。
- 阻害要因 1 (実測): `vstguibase.h:139` が `#error unsupported system/compiler` で停止する。判定は `_WIN32` / `__APPLE__` / `__linux__` のみで、Emscripten (`__EMSCRIPTEN__`) を含まない。
- 阻害要因 2 (実測): `-D__linux__=1` を補うと、PoC の seed 6 宣言 (`ctextlabel.h` `cviewcontainer.h` `cview.h` `ccontrol.h` `cbitmap.h` `cdrawcontext.h`) の構文チェックは 0 error (rc 0)。ただし `__linux__` の補正は測定用の回避であり、wasm 向けの正しい分岐ではない。
- 未達: canvas 側の純粋仮想 159 関数 (16 files) の実装、リンク、描画、`XferOnOffButton` の .text 対応付け。いずれもこの run では未着手。

### 9-4. 測定 commit と検証

- 測定 commit: `31927856` (本 §9 と `gui/vtable_measure.py` を追加した commit。コードを変えた最後の commit)。PR の head は後続の docs 修正で進むため、測定 commit とは別物。REPORT 自身の hash は本文に書けないため、PR 本文には「測定 commit = `31927856`」と書き、head は PR の検証節で別に示す。以後この commit までのコード差分は 0 (`git diff 31927856 HEAD -- tools/targets/serum2/gui/*.py` が空であること)。
- 再現: `work/venv/bin/python vtable_measure.py work/Serum2_win64.vst3 XferOnOffButton CTextLabel@VSTGUI`。

## 10. 2026-10-14 run (#1920): 継承差分の実測と wasm 分岐

### 10-1. 継承差分 (override / 新規のみ) の実測

- 方法: `vtable_measure.py` に、COL → CHD → BaseClassArray で継承元 TypeDescriptor を辿る処理を追加した。vtable の各スロットを、継承元 vtable の同じインデックスと比較し、値が同じなら継承、違えば override または新規とみなす。継承元 vtable が PE 内に無い場合は全スロットを override とみなすため、上限値になる。
- 結果 (出力 `gui/work/vtable_measure.txt`、同一入力の 2 回実行で一致):

| クラス | vtable 数 | 主 vtable: スロット / 継承 / override・新規 | 全 vtable の override・新規 (.text アドレスの和集合) |
|---|---|---|---|
| `XferOnOffButton` | 4 | 85 / 80 / 5 | **8** |
| `CTextLabel` (upstream 宣言あり) | 3 | 105 / 95 / 10 | **13** |

- 解釈: §9-2 の「継承込みの 74 / 90」は、継承分を含む上限値だった。置換側の実数の上限は `XferOnOffButton` で 8 関数、`CTextLabel` で 13 関数。本体サイズ (B) は未測定 (Ghidra が要る)。`CTextLabel` は upstream 宣言があるため置換対象ではないが、同じ方法で比較のために測った。
- 限界: 差分は、RTTI の base class array に並ぶ継承元の vtable と、同じインデックスで比べた結果。`XferOnOffButton` の主 vtable の継承元は `COnOffButton` (先頭の base)。副次 vtable (スロット数 2 と 3 の 3 件) は、スロット数 2 の 1 件が全 2 スロット override、他の 2 件は継承を含む。副次 vtable の継承元の対応は未検証。和集合 (8 / 13) は .text アドレスの重複を除いた値で、副次 vtable の override も含む。

### 10-2. `vstguibase.h` の wasm 分岐

- 再現 (補正なし): `em++ -std=c++17 -fsyntax-only -Iwork/vstgui4 work/seed6.cpp` → `vstguibase.h:139: #error unsupported system/compiler` (rc=1)。
- 対策: `vstguibase.h` に `#elif defined(__EMSCRIPTEN__)` 分岐を追加 (`WASM 1` を定義)。patch は `gui/patches/vstguibase_emscripten.patch`。
- 検証: `gui/check_wasm_syntax.sh` が patch を適用してから seed 6 を `em++ -fsyntax-only` で通す。`-D__linux__=1` は付けない。結果は rc=0、error 0 (clean upstream の `vstgui4_14_3` = `b1e82355` から再現)。
- 注意: Emscripten の定義は `__EMSCRIPTEN__ 1`・`__unix__ 1`。`__linux__` は未定義。分岐は `__linux__` の後に置くため、Linux 判定に影響しない。

### 10-3. 未達 (本 run の範囲外)

| 未達 | 起票先 |
|---|---|
| canvas 側の純粋仮想 103 関数 (6 files) の wasm 実装 (受入条件 1 の残り) | #2064 ([SR-35]) |
| `CTextLabel` 系 + `XferOnOffButton` 1 view の canvas 描画 (受入条件 2 の残り) | #2065 ([SR-36])・前提 #2064 |
| `XferOnOffButton` の .text 対応付けと本体バイト数 (受入条件 3 の残り) | #2066 ([SR-37]) → §14 で完了 |

- 親 #2029 ([SR-31]) は、上記 3 件へ未達の受入条件を移したうえで範囲を縮めた。
- 測定 commit: 本 §10 と `vtable_measure.py`・`check_wasm_syntax.sh` を追加した commit (PR 本文参照)。

## 11. 2026-10-14 run (#2064 / SR-35): canvas platform の wasm 実装 (部分)

- 範囲: §6 の 103 関数 (6 files) のうち、依存が閉じる 2 files (bitmap 7・graphicspath 13 = 20 関数) を実装。残り 4 files (font 7・graphicsdevice 31・frame 25・factory 20 = 83 関数) は子 issue へ分割。
- 実装: `gui/canvas/canvas_bitmap.{h,cpp}`・`gui/canvas/canvas_graphicspath.{h,cpp}`。bitmap は RGBA8 の連続メモリ、graphicspath は頂点列保持。楕円・円弧・テキスト輪郭は PoC の近似 (正確な曲線・文字輪郭は未実装)。
- 検証: `gui/canvas/check_canvas_syntax.sh` (em++ `-fsyntax-only`、`-D__linux__` 補正なし)。bitmap rc=0 errors=0、graphicspath rc=0 errors=0。`check_wasm_syntax.sh` (seed 6) rc=0 errors=0 を維持。
- 未検証: リンク・実行・描画 (受入条件 2 の範囲外、#2065)。閉包が実際に要求する関数はリンク時に確定させる (§6 の注記どおり)。
- 測定 commit: `38072d4a` (コードを変えた最後の commit)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| canvas 側 font 7・graphicsdevice 31・frame 25・factory 20 (計 83 関数) の wasm 実装 | 描画の閉包が完結しない | 子 issue (親 #2064) |

## 12. 2026-10-14 run (#2109 / SR-40): canvas の frame 実装 (factory は子 #2139 へ)

- 範囲: §11 の残り 4 files のうち、frame (IPlatformFrame) を実装。font 7・graphicsdevice 31 は #2107 (SR-39)、factory 20 は #2139 (SR-42) へ移した。
- 実装: `canvas/canvas_frame.{h,cpp}`。ネイティブのウィンドウを持たないため、サイズだけ保持し、マウス・修飾キー・カーソル・tooltip・drag・text edit・option menu・view layer は `false` / `nullptr` を返す。
- 検証 (`canvas/check_canvas_syntax.sh`、`-D__linux__` 補正なし):
  - `canvas_bitmap.cpp`: rc=0 errors=0
  - `canvas_graphicspath.cpp`: rc=0 errors=0
  - `canvas_frame.cpp`: rc=0 errors=0
  - `check_wasm_syntax.sh` (seed 6): rc=0 errors=0
- 初回 (include 不足) の失敗: `canvas_frame.cpp` は `IPlatformTextEdit` / `IPlatformOptionMenu` / `IPlatformViewLayer` が不完全型のまま `SharedPointer` を返すため error 3 件。対策は 3 つの `iplatformXXX.h` の include 追加。これで abstract 化の error も消えた。
- factory 未実装の原因: `platformfactory.h` → `platformfwd.h:36` が `static_assert (false, "unknown platform")` で止まる。`vstguibase_emscripten.patch` は `WASM 1` のみで `LINUX` を立てないため。factory の 20 関数はこの分岐が決まるまで実装・検証できない (#2139)。
- 未検証: リンク・実行・描画 (#2065 の範囲)。
- 測定 commit: `c9a7329a` (コードを変えた最後の commit。本節の REPORT 修正は含まない)。

## 13. 2026-10-14 run (#2107 / SR-39): canvas platform の font・graphicsdevice (wasm)

- 結論: font 7 + graphicsdevice 31 (計 38 関数) を wasm 実装。構文検査は測定 commit `89495465` で 5/5 rc=0、具象性検査 (`check_concrete.cpp`) rc=0。リンク・閉包確定・描画は未実施 (#2065)。
- 詳細・実測・測定 commit と差分: 付録 `REPORT_EFFORT_APPENDIX_2107.md` (本節の全文)。

## 14. 2026-10-14 run (#2066 / SR-37): XferOnOffButton の .text 対応付けと本体バイト数
- 詳細・実測・測定スクリプト: 付録 `REPORT_EFFORT_APPENDIX_2066.md` (本節の全文)。
