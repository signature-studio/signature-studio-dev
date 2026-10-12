# 自動生成: `python3 tools/m2/delphi_inventory.py`

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。

# delphi_inventory.md (FLEngine Delphi 固有面の機械採取)
生成: `tools/m2/delphi_inventory.py` (`docs/REFERENCES.md` `[STRATEGY]` §5.7 / M2 検証条件 5)

> 結論 (機械採取時点): **FLEngine 双方とも Delphi x64 の VMT/RTTI がそのまま残っており (win 1,244 / mac 3,896 class 検出), 関数名の自動復元は Delphi RTTI + VMT 経由で機械生成可能**。どちらのエクスポート面も超薄い (`CreateFruityInstance` 1 本 + `dbkFCallWrapper` 経由 Delphi RTL 定形) ので、シンボル面からの名付けは当たらない。よって M3 以降は「VMT→関数名/型表」(本書の class 一覧) を IR pass (名付け + 型付け) に注入する。

## 1. Delphi VMT / class pointer 一覧 (機械走査)

検出法は delphi_scan.py/mac 版と同一: **vmtClassName (class pointer -112 位置) に格納された Pascal 文字列**を data/.text const から QWORD 走査で取り出し、class pointer を`storage_addr + 112` として計算する。

| | FLEngine_x64.dll (win64) | FLEngine_x86_64.dylib slice (mac) |
|---|---|---|
| 検出された VMT class pointer | 1244 | 3896 |
| 検出された Pascal 文字列候補 | (win 版は delphi_scan.py の data/.text 走査) | 13984 |

### mac slice: class pointer の先頭 60 個

| class name | class pointer (RVA) |
|---|---|
| TOsxLauncher | 0x124c9f8 |
| TAggregatedObject | 0x124cfc0 |
| TContainedObject | 0x124d090 |
| EGnuGettext | 0x12642f0 |
| EGGProgrammingError | 0x12643c0 |
| EGGComponentError | 0x1264490 |
| EGGIOError | 0x1264560 |
| EGGAnsi2WideConvError | 0x1264630 |
| TGnuGettextInstance | 0x1264a68 |
| TTP_RetranslatorItem | 0x1264b70 |
| TTP_Retranslator | 0x1264c40 |
| TEmbeddedFileInfo | 0x1264d18 |
| TFileLocator | 0x1264de8 |
| TGnuGettextComponentMarker | 0x1264eb8 |
| TClassMode | 0x1265070 |
| THook | 0x1265140 |
| THookedObjects | 0x1265210 |
| TScrollingWinControl | 0x126d480 |
| TLoadableWinControl | 0x126da50 |
| TCustomForm | 0x126e020 |
| TForm | 0x126e698 |
| TMonitor | 0x126ed10 |
| TControlScrollBar | 0x126ede0 |
| TScrollBox | 0x126eed8 |
| TCustomFrame | 0x126f4a8 |
| TFrame | 0x126fa78 |
| TGlassFrame | 0x12700b8 |
| TCustomActiveForm | 0x12701b8 |
| TCustomDockForm | 0x1270830 |
| TScreen | 0x1270ea8 |
| TApplication | 0x1271060 |
| TComponentAccess | 0x12720b0 |
| TControlAccess | 0x1272268 |
| TWinControlAccess | 0x12726f8 |
| TCommonDialog | 0x1278f30 |
| TOpenDialog | 0x12790f0 |
| TSaveDialog | 0x12792d8 |
| TColorDialog | 0x12794c0 |
| TFontDialog | 0x1279680 |
| TPrinterSetupDialog | 0x1279840 |
| TPrintDialog | 0x1279a00 |
| TPageSetupDialog | 0x1279bc0 |
| TFindDialog | 0x1279d80 |
| TReplaceDialog | 0x1279f50 |
| TDragObject | 0x1283950 |
| TControl | 0x1283a60 |
| TWinControl | 0x1283ef0 |
| TDragImageList | 0x12844a8 |
| TBaseDragControlObject | 0x12848e0 |
| TDragControlObjectEx | 0x1284b20 |
| TDragDockObjectEx | 0x1284c40 |
| TControlCanvas | 0x1284d80 |
| TControlActionLink | 0x1284eb0 |
| TSizeConstraints | 0x1285078 |
| TMargins | 0x1285180 |
| TPadding | 0x1285298 |
| TCustomGestureManager | 0x12853b0 |
| TCustomGestureCollection | 0x12855e0 |
| TCustomGestureCollectionItem | 0x1285750 |
| EGestureException | 0x12858e8 |

### win64 DLL: class pointer の先頭 40 個 (delphi_scan.py 収取)

| class name | class pointer (RVA) |
|---|---|
| TCustomAttribute | 0x2678 |
| WeakAttribute | 0x27c8 |
| UnsafeAttribute | 0x28e0 |
| RefAttribute | 0x2a00 |
| EArgumentException | 0x2ec08 |
| EArgumentOutOfRangeException | 0x2ed48 |
| EArgumentNilException | 0x2ee98 |
| ENotSupportedException | 0x2efe0 |
| EListError | 0x2f128 |
| EInvalidOpException | 0x2f258 |
| EAbort | 0x2f3b8 |
| EOutOfMemory | 0x2f680 |
| EPathTooLongException | 0x2fa00 |
| EDirectoryNotFoundException | 0x2fb48 |
| EFileNotFoundException | 0x2fc98 |
| EExternal | 0x30030 |
| EExternalException | 0x30188 |
| EDivByZero | 0x303f0 |
| ERangeError | 0x30520 |
| EIntOverflow | 0x30650 |
| EMathError | 0x30780 |
| EInvalidOp | 0x308b0 |
| EZeroDivide | 0x309e0 |
| EUnderflow | 0x30c38 |
| EInvalidPointer | 0x30d68 |
| EInvalidCast | 0x30ea0 |
| EConvertError | 0x30fd0 |
| EAccessViolation | 0x31108 |
| EPrivilege | 0x31240 |
| EStackOverflow | 0x31370 |
| EVariantError | 0x315d0 |
| EPropReadOnly | 0x31708 |
| EPropWriteOnly | 0x31840 |
| EAssertionFailed | 0x31978 |
| EAbstractError | 0x31ab0 |
| EIntfCastError | 0x31be8 |
| EOSError | 0x31d20 |
| ESafecallException | 0x31e70 |
| EMonitor | 0x31fb0 |
| EMonitorLockException | 0x320d8 |

## 2. `dbk*` / Delphi 定形 export (実機 exe/dll 面)

win64 DLL (FLEngine_x64.dll) の export 一覧 (llvm-objdump -p):

| export | 備考 |
|---|---|
| CreateFruityInstance |  |
| __dbk_fcall_wrapper | ## Delphi RTL 定形 (FastCall wrapper; lifting / IR pass で本来の対象外扱い) |
| dbkFCallWrapperAddr | ## Delphi RTL 定形 (FastCall wrapper; lifting / IR pass で本来の対象外扱い) |

mac slice (FLEengine x86_64) の export 一覧: CreateFruityInstance (CreateFruityInstance の1 本のみ。FL64.exe / OsxFL と同等の超薄い面= IR 化対応 C ABI 面)

## 3. Delphi x64 calling convention / シグネチャの機械面

- M2 では calling_convention 観点の候補を自動抽出し、RetDec リフト IR と
  Ghidra pseudo-C を対照させている (tools/m2/REPORT.md 参照)。
  RetDec bin2llvmir は x64 PE を Microsoft x64 calling convention 既定と
  して解釈するため、Delphi 特有の record 変型 / open array / hidden
  return buffer / var param (= qrr 系 mangling 対応のパラメータ面) の
  補正は M3 の Delphi 固有 IR pass (シグネチャ定義表) で扱う。
