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

- 入力 sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` は `gui/REPORT.md` §9-1 の値と一致 (本 run で `$ARTIFACTS_DIR/plugins-serum2.tar.zst` から再展開して照合)。
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
- **`{CTextLabel, XferOnOffButton, CViewContainer}` だけで閉じる sub-controller 無しの template は 3 件** (`ArpBrowser` `ClipBrowser` `Empty`) で、いずれも `XferOnOffButton` を含まない。つまり PoC は「uidesc 1 template の完全実体化」ではなく「Xfer 固有 2 種を含む最小 template の部分実体化」になる。

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

- 入力の sha256 は `gui/REPORT.md` §9-1 の値と一致 (上記 §1)。
- `strategy_count.py` の出力は、コミット済みの `out/gui_strategy_count.txt` と**一致** (`diff` で確認)。
- `effort_measure.py` の出力 (`work/effort_measure.txt`): 所要 0.93 s real (逐次, load 未計測)。
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
- canvas 側で実装が要る純粋仮想インタフェース (`lib/platform/iplatform*.h` と `platformfactory.h`): 全 16 ファイル・**133 関数**。内訳は frame 22 / graphicsdevice 22 / textedit 17 / platformfactory 14 / graphicspath 9 / framecallback 9 / openglview 10 / bitmap 7 / font 5 / ほか 18。
- PoC で最低限要るのは描画に直結する bitmap / font / graphicspath / graphicsdevice / frame / factory の 6 種 (計 79 関数)。**これは本 run の判断であり、実際に閉包が要求するかは未検証** (リンク・実行で確定する)。
- Xfer 固有 2 種 (`XferOnOffButton` 43 参照・`CTextLabel` 26 参照 は uidesc 上の参照数) の**関数数・バイトは未実測**。Xfer の .text 上での対応付けが要る (`gui/REPORT.md` §5-1 の注記どおり)。

## 7. 工数 (人日) について (本 run の判断)

- 工数は**本 run では推定値を出さない**。入力として §2・§6 の対象量は揃った。
- 換算係数 (行/人日・関数/人日) を本リポジトリは持たない。係数を置くと、実測でない精度が数字に混入する。
- 受入条件 1 の「工数の根拠」は、対象量 (本 REPORT §2 / §6) で根拠の材料は示した。人日そのものは未達として残し、判断はユーザに委ねる。

## 8. 測定 commit

- 測定 commit: `gui/effort_poc.py` を追加した commit (本 PR の最後のコード変更)。`git log -1 -- tools/targets/serum2/gui/effort_poc.py` で確認する。
- 既存の `effort_measure.py` / `strategy_count.py` は本 run で再実行し、§2 の値と一致した (`effort_measure.py` は `work/effort_measure.txt` に保存)。
