# tools/fruityplug — T-SH-12 (#154): SGv2 の win 対応 (FruityPlug_x64.dll 候補) の検証

既知類型との関係 (docs/DEFECTS.md): 該当なし。lift は行っていない (対象の同定のみ)。

## 0. 結論 (先出し)

- **判定: 未達 (SGv2 の win 側の対応は未特定)**。PR は `Refs #154` (Closes しない)。
- **既存の推定は誤り**: `tools/shared/scripts/classify.py:58` が SGv2 の win 候補として固定している
  `block24353_PE.bin` は、VERSIONINFO の `ProductName` / `InternalName` が `Maximus` (Image-Line の Fruity プラグイン)。
  FileDescription だけ `Sytrus Synthesizer` (テンプレート由来の残り)。SGv2 の根拠にはならない。
- **export 名による対応付けは識別力が無い**: 内部名 `FruityPlug_x64.dll` の PE 133 本はすべて `CreatePlugInstance` を持ち、
  131 本は export 組が完全に同一。サイズの一意性 (5,892,096 B は block24353 のみ) も同定根拠にならない
  (個別プラグインの別バイナリ)。
- **次の一手 (PM 判断・素材追加が要る)**: mac 側 `SGv2_x64.dylib` (FPC 3.2.3 版) を mac 素材と突合する。
  `analysis-mac-shared` に SGv2_x64.dylib が含まれるかは未確認 (`tools/shared/REPORT.md` の mac Shared 素材範囲に入る想定)。
  本 run の素材は `fl-win64` / `toolchain-emsdk` / `toolchain-retdec` のみで、突合は未実施。

## 1. 実測 (`identify_win.py`、測定 commit `d40bd24e`)

| 項目 | 値 |
|---|---|
| 内部名 `FruityPlug_x64.dll` の PE (fl-win64 `extracted/block*_PE.bin`) | **133 本** |
| `CreatePlugInstance` を持つ | 133 / 133 |
| export 組が 3 本 (`CreatePlugInstance` + `__dbk_fcall_wrapper` + `dbkFCallWrapperAddr`) と一致 | 131 / 133 |
| 他 2 本の export 組 | ZGE (ZGameEditor) 系 (多数の export) / DecodeAudioFile 系 (5 本) |
| VERSIONINFO なし | 79 / 133 (ProductName の種類は 42) |
| 同サイズ 5,892,096 B の PE | block24353 のみ |
| block24353 の VERSIONINFO | ProductName = InternalName = `Maximus` / FileDescription = `Sytrus Synthesizer` |
| 別版の Maximus | block19148 (5,904,384 B、ProductName = InternalName = `Maximus`) |
| win PE 内の `FPC 3.2.3` 文字列 | 0 件 (win は Delphi。FPC 3.2.3 は mac 側のみ) |

- 実行: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/fruityplug/identify_win.py` (pefile 必要)。
  実行時間 1.2 s、実行後 load 0.17 0.29 0.16、nproc 4。作業 TSV は `tools/fruityplug/work/identify.tsv` (gitignore)。
- 測定 commit `d40bd24e` から HEAD までの `tools/fruityplug` の差分は本 REPORT の追加のみ (`git diff d40bd24e HEAD -- tools/fruityplug/*.py` は空)。

## 2. 既存記述の訂正 (注記のみ・分類データは未変更)

- `tools/shared/REPORT.md` §1 の IL プロプラ行 (SGv2 ↔ win `FruityPlug_x64.dll`、export `CreatePlugInstance` 一致・推定) は、
  block24353 を指す `classify.py:58` の固定値 (`win=(..., 24353)`) と `data/classification.json` の `win` 欄に対応する。
  本測定で block24353 = Maximus と判明したため、この対応は採らない。
  分類データの修正は、対応が決まるまで PM 判断とする (本 PR では変更しない)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SGv2 の win 対応 (133 本から一意に決める根拠) | T-SH-12 の第 3 段 (FruityPlug) が未着手。SGv2 の lift 対象が未定 | #154 (PM 判断。`analysis-mac-shared` を足して再起動すれば mac 側と突合できる想定) |
| ILTools の x87 lift 方式 (unsup 1,236 site) | ILTools の lift 完走不可 (`tools/iltools/REPORT.md`) | #154 (PM 判断。前 run の停止報告と同じ) |
| QFC の boot (InitDll → FontCache_*) / FreeType 結合 | 実行時の正しさ未検証 | #154 継続 (T-SH-01 依存) |

## 4. 再現

```
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/fruityplug/identify_win.py
```

出力 (標準出力) の 1 行目〜4 行目が §1 の表の値に対応する。gate ではないため、判定の exit code は持たない。
