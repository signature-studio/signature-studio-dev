# REPORT — [SR-7 #68] Serum 2 GUI 戦略: 残留 2 点の実バイナリ確認

- 日付: 2026-10-13 / 親: #15 [PLG-E] / 前段: `tools/targets/serum2/REPORT.md` §6.1 GUI 行・§9 T7、`license/authstub/REPORT.md` §4 N7
- 範囲: 本 dir (`tools/targets/serum2/gui/`) のみ新設。既存 REPORT.md は無変更 (250 行上限)。
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift 前の静的確認。silent miscompile 類型は未触)。
- 検証起点: 本 PR の commit (クリーン HEAD の worktree `68-serum2-gui-strategy`)。入力 `Serum2_win64.vst3` sha256 `501e7bb3…5283` (19,236,864 B, REPORT §11 と一致)。

## 0. 結論 (先出し)

| 残留 | 判定 |
|---|---|
| (1) Splice 3 テンプレートの実体化分岐 | **未特定のまま**。確定したのは「uidesc 内の定義は 3 件・参照 0 件」「SpliceController の 0x180796320 は support 記事 URL を開くボタン処理」まで。実体化を行う関数は静的に見つけられなかった |
| (2) overlay_demo_version(_mini) | **表示経路の参照は bitmap 登録の 1 件のみ** (template の子・key からの参照は 0)。実体化の経路は無いと判断でき、authstub N7 の「実害なし」と整合 |

GUI 戦略 (a) 全 lift / (b) upstream VSTGUI 再構築の比較と判定は **本 run では行っていない** (§9 T7 の範囲)。

## 1. 再現手順と入力確認

```sh
# 素材: fl-win64 ではなく plugins-serum2 の Install_Xfer_Serum2_2.1.5.exe を使用 (docs/REFERENCES.md [PLUGINS-SERUM2]。展開は §9-1 の手順で `$EXE` に設定済みとする)
7z x -y -owork/exe_extract "$EXE"
cp -f 'work/exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' work/Serum2_win64.vst3
python3 gui/extract_uidesc.py work/Serum2_win64.vst3 work/uidesc.json     # uidesc bytes 2093822 (REPORT §2 と一致)
python3 gui/decode_splice_url.py work/Serum2_win64.vst3                  # 0x180796320 の復号文字列
```

- 依存: `pefile` `capstone` `zstandard` (`python3 -m pip install --break-system-packages`)。
- 実測: sha256 `501e7bb3dd9cafe4…` (先頭 16 桁) が REPORT §11 の入力と一致。uidesc 抽出 **2,093,822 B** (REPORT §2 と一致)。
- 所要 (real, 逐次, load 未計測):
  - 今回 run (HEAD `0dcf5f4e` + 修正, 2026-10-13): `extract_uidesc.py` **2.97 s** / `decode_splice_url.py` **3.00 s** (別プロセス・各 1 run)。
  - 前回 run (HEAD `d692129c`, 修正前の値): 抽出 + 復号 + uidesc 解析 = 6.82 s。今回 run との差は環境差 (同一 run で再測定した値のみ採用)。

## 2. 残留 (1) Splice 3 テンプレートの実体化分岐

### 2-1. uidesc 内の定義と参照 (実測)

| 項目 | 結果 |
|---|---|
| `templates` 件数 | 123 |
| `SpliceRTO` / `SpliceExpired` / `SpliceMaxLimit` の定義 | 各 1 件。`class: CViewContainer`・`sub-controller: SpliceController`・`size: 1190, 740` |
| 他の template の子・属性からの参照 | **0 件** (own def を除く `"Splice*"` 文字列 count = 0) |
| 平文バイナリ内の出現 | **0 件** (ASCII・UTF-16LE とも。名前は zstd 圧縮 uidesc の中にだけ存在) |

→ 静的な名前参照では実体化元を辿れない。実行時の template 辞書引き (文字列キー) か、テーブル index 経由の可能性がある。

### 2-2. SpliceController のメソッド候補 (実測)

- `0x180796320` (size 358): 状態フィールド `[rsi+0x168/0x178/0x170/0x160]` の比較で 4 分岐し、`0x1801bc300` (ShellExecuteEx ラッパ, authstub §4) か `0x1800ccf60` / `0x1800cbb90` を呼ぶ。
- **復号結果 (`gui/decode_splice_url.py`)**: `https://support.splice.com/en/articles/10055412-serum-2-license-instructions` (76 文字・全文)。→ Splice 関連の「support 記事を開く」ボタン処理と判定 (high)。
- 復号の範囲: `0x180796320` の `movups xmmword ptr [rsp + 0x5d], xmm0` はバッファ offset 61 から 16 バイト (61〜76) を書く。バッファ長 76 の末尾 15 バイト (61〜75) を埋める。旧版は `off <= N - 16` (上限 60) でこの書き込みを捨てて文字化けしていた (旧出力 `...license-Ö×ØÙÚÛÜÝÞßàá`)。修正版は `0 <= off < N` で `min(16, N - off)` バイトを書く。
- `0x180796090` (size 587) は未解析。`0x180542a20` (size 3,105) は起動直後の初期化側と推定 (med)。いずれも実体化分岐の確定根拠ではない。

### 2-3. 未確定

実体化を行う関数 (state → template 名の選択) は**未特定**。`0x180796320` は「既に表示された Splice ビュー上のボタン処理」であって、ビューを選ぶ側ではない。

## 3. 残留 (2) overlay_demo_version(_mini)

| 項目 | 結果 |
|---|---|
| `templates` に `overlay_demo_version` を key とする定義 | **0 件** (`_mini` / `_fx_version` 系も同様) |
| 文字列の出現 | uidesc 内に `"path": "overlay_demo_version"` の bitmap 登録 1 件 (`overlay_demo_version_mini` ほか) |
| 参照元 (template 子) | 0 件 |

→ template として表示される経路は uidesc から見当たらない。bitmap 登録のみという authstub N7 の記述と一致する。

## 4. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (1) Splice テンプレートの実体化関数 (state → template 名) | authstub N7 の「非表示固定」が未検証。demo bit ≡ 0 で表示条件が偽になるかは実測不能 | #623 (SR-2c, 既存) |
| 残り 2 点の動的確認 (実 host で Splice 表示が出ないこと) | 静的確認のみ。実 VSTGUI 実行が必要 | #623 (SR-2c) / GUI lift 時 |
| GUI 戦略 (a) 全 lift / (b) upstream VSTGUI 再構築の比較 | 本 run 未実施。§9 T7 (2〜3 週調査) の本体 | 本 issue #68 の残作業 (Refs) |

## 5. GUI 戦略 (a) 全 lift / (b) upstream VSTGUI 再構築 の比較 (§9 T7)

### 5-1. 実測 (`gui/strategy_count.py` → `out/gui_strategy_count.txt`)

| 項目 | 実測 |
|---|---|
| 入力 | `work/uidesc.json` (2,093,822 B, §1 と同一)。templates 123 / bitmaps 344 |
| View クラス参照 | 817 件 / **103 種** (全 103 種がバイナリ RTTI に名前一致) |
| うち VSTGUI 標準名とみなした分 (`C` 接頭辞, ヒューリスティック) | 16 種 / **260 件** (`CViewContainer` 165 が大半) |
| うち Xfer 独自とみなした分 (その他, ヒューリスティック) | 87 種 / **557 件** (`HoverView` `XferAdvancedOptionMenu` `VectorKnob` `XferOnOffButton` ほか) |
| sub-controller | 159 件 / 61 種。RTTI 名一致 58 種。不一致 3 種 (`OscController2` `RoutingSlotController2` `RoutingSlotController6`) |
| VSTGUI `UIViewCreator` 系 RTTI | 39 件 (`VSTGUI::UIViewCreator::*Creator`) |
| GUI 関数 (closure, `out/closure_summary.json`, 静的・過大近似) | GUI root 836 / GUI closure 7,138 関数 (4.21 MB) / GUI のみ 3,217 関数 (1.92 MB) / DSP と共有 3,921 関数 (2.29 MB) |

注: 「C 接頭辞 = VSTGUI」「その他 = Xfer」は名前からの**推定**であり、個々の class の実体 (どの RTTI がどの .text に対応するか) は未確認。RTTI 照合は部分文字列ではなく単語境界の一致のみ。

### 5-2. 比較

| 観点 | (a) 全 lift | (b) upstream VSTGUI 再構築 + Xfer 固有ビューのみ lift/置換 |
|---|---|---|
| 対象量 | GUI closure 7,138 関数 / 4.21 MB (過大近似)。実数は動的トレース後 | VSTGUI 基盤 (推定 約 3,360 関数 / 692 KB, 本体 REPORT §3) は upstream ソースで置換。lift 対象は Xfer 固有 87 種 (557 参照) |
| 依存 | Win32 / D2D / DirectComposition を含む platform 層を lift するか、canvas へ差し替えるかが不明のまま | canvas platform を新規実装する前提。upstream VSTGUI の版は未確定 (SR-3 の cut 表に VSTGUI は未掲載) |
| 量の根拠 | 関数数・バイトは実測。ただし closure は間接呼出の取りこぼしを含み、真値は未確定 | 置換側の工数は未実測 (推定のみ) |
| 検証の取り方 | バイナリ同士の挙動比較が可能 | 参照 (実機) 表示との突合が必要。§4 の動的確認と同じ経路 |
| 既存資産 | host (§host/REPORT) で editor 生成まで到達。描画は未実施 | uidesc 展開 (§1) と PNG/TTF は既に取得可能 |

### 5-3. 判定 (推奨・確度付き)

- **推奨: (b)。** 根拠は実測の 2 点 (a) GUI closure 4.21 MB は DSP と 3,921 関数を共有し、lift 単独では DSP 側の切り分けも要る。(b) は uidesc の View 種が 103 と有限で、Xfer 固有は 87 種に限られる。
- **確度: 中。** (b) の工数・canvas platform の工数は**未実測**。VSTGUI 版の同定も未了のため、(b) を採るなら版確定を先にする。
- **残留 (1) Splice 実体化分岐** は (a)(b) どちらでも同じ未解決 (§2-3)。SpliceController は Xfer 固有ビューなので (b) では置換側で扱う。
- **PoC 境界 (次段)**: 最小 1 view (例 `CTextLabel` 系 + `XferOnOffButton`) を upstream VSTGUI で canvas 描画し、uidesc から 1 template を実体化する。ここまでを GUI 戦略の PoC とし、全 Xfer ビューの置換はこの後に起票する。

本 run では (a)(b) の工数見積もりを実測していないため、**判定は推奨止まり**。最終決定はユーザ判断。

## 6. 検証 (実測)

- `gui/strategy_count.py work/uidesc.json out/rtti_classes.txt` を 1 回実行 (0.09 s)。出力は `out/gui_strategy_count.txt` (691 B)。
- 入力の sha256 `501e7bb3dd9cafe4…` / 19,236,864 B は REPORT §11 と一致 (本 run で `plugins-serum2` の exe から再抽出)。
- uidesc 抽出 2,093,822 B (`extract_uidesc.py`, 3.55 s, 逐次)。

## 7. 検証 (前 run, 残留 2 点)

- 抽出 → 復号 → uidesc 解析を 1 コマンド系列で 1 回実行 (§1)。出力は §2-1 / §3 の数値と一致。
- ネガティブコントロール: テンプレート参照カウントは own def を差し引いて 0 (= 自己参照を数えていない)。定義件数 3 は `SpliceExpired`/`SpliceMaxLimit`/`SpliceRTO` の 3 名を列挙して確認。
- 範囲外: 実 VSTGUI 実行、wasm/canvas 上の表示、Machine ID、mac 版。

## 8. VSTGUI upstream 版の同定 (2026-10-13 run, §5-3 の未了分)

入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` から展開した `Serum2.vst3` (sha256 `501e7bb3dd9cafe4…`, 19,236,864 B)。gitignore 対象の `work/` に置いた。

| 観測 | 結果 | 判定 |
|---|---|---|
| VSTGUI ソースパス文字列 (`vstgui\lib\cframe.cpp` 等) | 存在。`uidescription/detail/uijsonpersistence.cpp` を含む | VSTGUI 由来の確認 (高) |
| `VSTGUI` / `vstgui` 文字列 | §9 の値を正とする (件数・offset は §9 表を参照) | 版番号を含まない |
| `3.7.12` | `VST 3.7.12` (フォント表示付近の文字列)。offset は §9 を参照 | **VST3 SDK の版**。VSTGUI の版ではない |
| `3.19.3` / `9.1.5` / `2.0.20` / `2.0.24` | 版番号として単独出現 | VSTGUI と結び付く根拠は無い (未特定) |
| `kVstVersion*` / `VSTGUI_VERSION` 系 | 0 件 | 版定数は無い |

結論: **Xfer 版の VSTGUI の版は、バイナリの文字列からは同定できなかった。** 版確定には (1) upstream の各版 (4.x 系) の uidescription ソース (`uijsonpersistence.cpp` の有無と JSON 形式の差) と本バイナリの UIDescription JSON 読込関数を突き合わせる (2) 版ごとの `UIViewCreator` 名集合と §5-1 の 103 種 / RTTI 39 件を照合する、のいずれかが要る。どちらも本 run では未実施。

§5-3 の (a)/(b) 工数実測は本節の版同定を前提とするため、未実施のまま残す。

### 検証

- 本 run の再測定: **未実施**。素材 `[PLUGINS-SERUM2]` が本 run の `$ARTIFACTS_DIR` に無く (`fl-win64.tar.zst` のみ)、上表の数値は前 run の実測値。本節の sha256 (`501e7bb3dd9cafe4…`) も前 run の記録で、本 run では照合していない。
- 前 run で使った grep の正確な式はログに残っていない。表の数値の正は §9 (§9-1 の手順で再測定する)。
- 再測定の手順は §9-1 を参照する。
- 所要と load: **未計測** (PR 本文と揃える)。

## 9. VSTGUI 版の同定 (2026-10-13 再測定・ソース照合)

§8 の未了分を、VST3 SDK の `vstgui4` submodule との突合で行った。入力は §8 と同一のファイル (sha256 `501e7bb3dd9cafe4…` / 19,236,864 B)。素材の展開と再測定の手順は §9-1。

| 観測 | 結果 | 判定 |
|---|---|---|
| バイナリ内の VSTGUI ソースパス (`vstgui4\vstgui\...`) | 34 件抽出。`..` を含む 1 件を除く **33 件** | 比較対象 |
| 33 件が存在する vstgui4 タグ | `vstgui4_13_0` 〜 `vstgui4_14_3` は **33/33**。`vstgui4_12_3` は 32 (`lib/platform/win32/direct2d/d2dgraphicscontext.cpp` が無い) | **13.0 以降**に絞れる |
| 12.x 以前 | `vstgui4_10`=30, `vstgui4_11`=32, `vstgui4_12_x`=32 | 除外 (ファイル数で不一致) |
| 13.x と 14.x の区別 | 33 件のパス集合は同一。13.3 と 14.3 の `UIViewCreator` 系クラス名集合も同一 (4 件) | **パスでは区別できない** |
| v3.7.12 SDK の vstgui4 pin | submodule commit `02eadc0d` (= `vstgui4_14_0-1`) | SDK 3.7.12 は 14.0 系を同梱 |
| `VST 3.7.12` の offset | 16595116 | VST3 SDK 版文字列であることは不変 |
| VSTGUI 文字列計 (大小区別なし) | `VSTGUI` 2,291 + `vstgui` 72 = **2,363** | 参考値。版判定には使わない |
| 版定数 `kVstVersion` / `VSTGUI_VERSION` | 0 件 | §8 と同じ |

- **結論: VSTGUI は vstgui4 の 13.0 以降 (実質 13.x または 14.x)。13.x と 14.x は今回の手法では区別できない。** 同梱 SDK 3.7.12 の pin (14.0 系) と整合するが、断定はしない。
- JSON uidescription (`"vstgui-ui-description": {"version": "1"}`) の書式は `uijsonpersistence.cpp` (2020-05 導入, vstgui4_10 系で既に存在) と一致する。書式だけでは版は絞れない。
- 未確定: 13.x と 14.x の確定。方法は (1) 13.x/14.x 間で差分のある関数本体 (逆アセンブル突合) (2) `UIViewCreator` の RTTI 名 (39 件) を 14.x 側と照合 のいずれか。(2) は本 run で RTTI の mangled 名の抽出に失敗 (0 件) したため未完。

### 9-1. 再現手順 (`tools/targets/serum2/` を cwd・`work/` は gitignore)

素材の所在は `docs/REFERENCES.md` の `[PLUGINS-SERUM2]` (取得指定 `oc_artifacts: plugins-serum2`)。

```sh
# tools/targets/serum2/ を cwd とする。$ARTIFACTS_DIR は docs/REFERENCES.md [PLUGINS-SERUM2] の配置先
mkdir -p work/plugins-serum2
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" -C work/plugins-serum2 --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
EXE=$(find work/plugins-serum2 -name 'Install_Xfer_Serum2_2.1.5.exe' | head -1)
7z x -y -owork/exe_extract "$EXE"
cp -f 'work/exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' work/Serum2_win64.vst3
sha256sum work/Serum2_win64.vst3   # 501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283
grep -aoE 'vstgui4[\\/][A-Za-z0-9_\\/.-]+\.(cpp|h|mm)' work/Serum2_win64.vst3 | sed -E 's#\\#/#g; s#^vstgui4/vstgui/##' | sort -u > work/vstgui_src_paths.txt
```

ソース照合の基準:

- 基準 SDK: `https://github.com/steinbergmedia/vst3sdk.git` の tag `v3.7.12_build_20`。`.gitmodules` の `vstgui4` の url は `../vstgui`、pin commit は `02eadc0d2d8295a3b856678fb67901c756580faf` (`git describe` で `vstgui4_14_0-1`)。
- vstgui 本体: `https://github.com/steinbergmedia/vstgui.git` を `work/vstgui4` に clone し、タグごとに下記を数える。
  ```sh
  git clone --filter=blob:none --no-checkout https://github.com/steinbergmedia/vstgui.git work/vstgui4
  for t in $(git -C work/vstgui4 tag -l 'vstgui4_1[0-4]*'); do
    n=0; while read p; do git -C work/vstgui4 cat-file -e "$t:vstgui/$p" 2>/dev/null && n=$((n+1)); done < work/vstgui_src_paths.txt
    echo "$t $n/$(wc -l < work/vstgui_src_paths.txt)"
  done
  ```
  判定に使うのは「vstgui/ 配下のパス存在数」のみ。`d2dgraphicscontext.cpp` の有無は `git -C work/vstgui4 cat-file -e vstgui4_12_3:vstgui/lib/platform/win32/direct2d/d2dgraphicscontext.cpp` で個別に確認できる。

- 所要 (real, 逐次): `extract_uidesc.py` 2.62 s (venv `work/venv`)。ソース照合の所要・load は**未計測**。
- §8 の表の offset・件数は本節へのリンクに置き換えた (値は本節だけに残す)。

## 10. VSTGUI 13.x / 14.x の確定 (2026-10-14 run)

§9 の未確定事項 (1) を、差分リテラル法で実施した。入力は §9 と同一 (sha256 `501e7bb3dd9cafe4…` / 19,236,864 B、`plugins-serum2` から再展開して一致確認)。

| 観測 | 結果 | 判定 |
|---|---|---|
| 13.3 → 14.0 の差分 (製品コード, `tests/` 除外) | 14.0 で `uidescription/viewcreator/rowcolumnviewcreator.cpp` の `layoutStrings` に 9 配置名 (`top-left` … `bottom-right`) が追加。13.x の製品コードには存在しない | 差分の一次情報 |
| 9 配置名のバイナリ出現 | 9 件すべて ASCII で 1 回ずつ出現 (オフセットは未記録。再現は §10-1) | **14.x 系の文字列を持つ** |
| 14.0 → 14.3 の差分リテラル | 0 件 (バイナリ・ソースとも) | 14.x 内の区別は不可 |
| 14.3 → 15.0 の差分リテラル | バイナリに当たるのは `Error` `Object` 等の一般語のみ | 15.x 判定の根拠にならない (未検証) |

- **結論: Xfer Serum 2 (2.1.5) の VSTGUI は 14.x 系。13.x は除外できる。** 14.0 〜 14.3 のどれかは未確定 (差分リテラル無し)。SDK 3.7.12 の pin (`vstgui4_14_0-1`) とも整合する。
- 「13.x と 14.x の確定」は §9 の方法 (1) 関数本体の逆アセンブル突合、または (2) RTTI 名の照合が必要。本節は 13.x 除外までを確定とする。
- 残件: 14.0〜14.3 の確定と 15.x 以降の除外。方法は §9 (1) の逆アセンブル突合。

### 10-1. 再現手順

```sh
# tools/targets/serum2/ を cwd・work/ は gitignore。§9-1 の手順で work/Serum2_win64.vst3 と work/vstgui4 を用意する
python3 gui/vstgui_version.py    # 0.70 s (real, 逐次, load 未計測)
```

- 出力の判定: 13.0 / 13.3 は 0/9、14.0 / 14.3 は 9/9。バイナリ内 9 件 = 1 each。
- 14.3 → 15.0 の差分リテラル比較 (`git -C work/vstgui4 grep -h -oE '"[^"\\\n]{6,60}"' <tag> -- vstgui/` の集合差) は、一般語が多く判定に使えないため本節の手順には含めない。

## 11. 14.0〜14.3 の差分リテラル法 (2026-10-14 run, #1350)

§10 の残件 (14.0〜14.3) を、版間の製品コード差分にバイナリ出現する文字列リテラルがあるかで試した。入力は §9 の入力 (sha256 とバイト数の正は §9-1 の `sha256sum` 行)。**本 run では素材 `plugins-serum2` が `$ARTIFACTS_DIR` に無く (`fl-win64` のみ)、入力の再照合もバイナリ照合も未実施。** 下表の値は前 run の実測で、本 run では再現していない。

| 段 (製品コード, `tests/` 除外) | 差分の変更行数 | 差分に現れる文字列リテラル | バイナリ内の出現 | 判定 |
|---|---|---|---|---|
| 13.3 → 14.0 | 1,075 行 (46 ファイル、insertions 844 + deletions 231) | §10 の 9 配置名 | 各 1 件 | 13.x 除外の根拠 (§10) |
| 14.0 → 14.1 | 145 行 (7 ファイル) | `CRowColumnResizing` / `Fonts\*` | `CRowColumnResizing` 1 件 (両版の製品コードに存在)。`Fonts\*` は文字列自体が不変 (`*basePath +=` → `basePath +=` のコード変更) | 区別不可 |
| 14.1 → 14.2 | 43 行 (7 ファイル) | `cairobitmap.h` | 0 件 (`vstgui/lib/platform/linux` 側のヘッダ名) | 区別不可 |
| 14.2 → 14.3 | 116 行 (13 ファイル) | `hand1` / `fleur` | 0 件 (`vstgui/lib/platform/linux/x11platform.cpp` のカーソル名。Win32 バイナリに入らない) | 区別不可 |

- 14.0 → 14.3 の Win32 / common / uidescription 差分 (9 ファイル) は関数本体の変更が中心 (`d2dfont.cpp` `win32frame.cpp` `genericoptionmenu.cpp` 等)。追加行でリテラルを含むのは 1 件 (`basePath += "Fonts\\*"`、既存の文字列を残したまま `*` の間接参照を外した変更で、文字列自体は不変)。
- **結論: 14.0〜14.3 の確定は差分リテラル法では不可。** 差分の文字列で版を分ける手は取れない。残る手段は §9 (1) の逆アセンブル突合 (関数本体の差) のみ。確定は #1350 の作業に残す。
- 対象外: 14.x 内の差は Win32 の描画関数 (`d2dfont` / `win32frame`) に集中するため、逆アセンブル突合を行うなら `d2dfont.cpp` 相当の関数を先に候補にすると効率がよい (推定。未検証)。

### 11-1. 再現手順

```sh
# tools/targets/serum2/ を cwd・work/vstgui4 は §9-1 の clone
for p in "vstgui4_14_0 vstgui4_14_1" "vstgui4_14_1 vstgui4_14_2" "vstgui4_14_2 vstgui4_14_3"; do
  set -- $p; git -C work/vstgui4 diff --stat $1 $2 -- vstgui/ ':!*/tests/*' | tail -1
  git -C work/vstgui4 diff -U0 $1 $2 -- vstgui/ ':!*/tests/*' | grep -E '^[-+][^-+]' | grep -oE '"[^"]{4,80}"' | sort -u > work/lit_$1_$2.txt
  while IFS= read -r q; do
    s=${q:1:-1}
    echo "$1 -> $2 | $(grep -o -a -F -- "$s" work/Serum2_win64.vst3 | wc -l) | $s"
  done < work/lit_$1_$2.txt
done
```

- 前提: `work/Serum2_win64.vst3` と `work/vstgui4` は §9-1 で用意。照合の出力は「段 | 出現数 | リテラル」で、表の「バイナリ内の出現」列と一致させる (`grep -c` は行数なので使わない)。
- 本 run の照合: **未実施** (`plugins-serum2` 不在・`work/` 無し)。上表の出現数は前 run の値。所要・load は未計測。
