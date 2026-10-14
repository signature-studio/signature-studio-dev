# tools/shared/lift/rex — REX Shared Library (win `block24351_PE.bin`) の export 閉包測定 — T-SH-11 (#153)

測定 commit: `2d73ba27` (`tools/shared/lift/rex/rex_closure.py` を最後に変更した commit。以降の差分は REPORT のみ)。
既知の類型との関係: 該当なし (lift していない)。

## 結論 (1 行)
REX DLL の export 14 本の閉包を `rex_closure.py` で実測 (0.6 秒・再実行で JSON 一致)。最小の `REXGetCreatorInfo` は 22 関数・924 命令・間接 0。`REXCreate` (514 関数) など REX 読込の中核は閉包が大きいため、lift と差分テストは子 issue に分ける。**lift はまだ行っていない**。

## 0. 位置づけ
- 方針: `docs/DECISIONS.md` D20 (#163 の PM 判断, 2026-10-14)。REX は**所有者限定 tier でのみ lift**し、FL 本体と別の side module にして、ビルドフラグで除外できる構成にする。優先度は低いまま。
- 路線: `docs/DECISIONS.md` D5。本測定は pefile + capstone だけを使い、RetDec は使わない。lift 方式 (x64c / liftlib) は子 issue で選ぶ。
- 本 PR の範囲: 閉包の測定と再現スクリプト。lift・差分テスト・side module は含まない。

## 1. 対象
- `REX Shared Library.dll` = fl-win64 の `extracted/block24351_PE.bin` (PE32+ x64, 321,848 B, ImageBase 0x180000000, `.text` RVA 0x1000・サイズ 0x320de)。`tools/shared/scripts/classify.py` の 24351 に対応。
- export 14 本: Open / Close / REXCreate / REXDelete / REXGetCreatorInfo / REXGetInfo / REXGetInfoFromBuffer / REXGetSliceInfo / REXRenderPreviewBatch / REXRenderSlice / REXSetOutputSampleRate / REXSetPreviewTempo / REXStartPreview / REXStopPreview。
- 直接 import: KERNEL32 (約 60 名) と WINMM `timeGetTime`。閉包に現れる import は KERNEL32 の 35 名のみ (`timeGetTime` は閉包に現れない)。C++ ランタイムの DLL 名 import は無い (静的リンク)。
- 参照元の候補: fl-win64 内で文字列 `REXCreate` を含むバイナリは **33 件** (`tar --zstd -xf … --to-command` で走査、ディスク展開なし)。`block24341` (DirectWaveCtEngine.dll) を含む。**文字列の存在だけで、各バイナリがどの export を呼ぶかは未確認** (子 issue で確定する)。

## 2. 方法 (`rex_closure.py`)
- export の stub が 1 命令の `jmp rel32` なら実体へ辿る (最大 4 段)。今回は 14 本とも stub = 実体 (辿る必要なし)。
- BFS で直接 `call` 先と、関数範囲の外への直接 `jmp` (tail call) を辿る。関数範囲は `.pdata` の RUNTIME_FUNCTION で切る。
- `.pdata` に無い先は「次の `.pdata` 先頭までの近似」とし、表の `approx` 列に数える。**近似の関数は範囲が末尾の非関数データを含みうるため、命令数は上限寄り**。
- IAT 経由の `call [rip+disp]` は import 名に解決して `imports` 列に記録。それ以外の間接 call/jmp (レジスタ・jump table 等) は `indirect` 列に数え、先は含めない (下限側)。
- 命令数は命令開始アドレスの和集合で数える (範囲の重なりを二重計上しない)。

再現:
```
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/lift/rex/rex_closure.py [--json OUT]
```
`<fl-win64 展開先>` は `extracted/block24351_PE.bin` を含むディレクトリ (`docs/WORKFLOW.md` §11 の `tar --zstd -xf` で展開)。

## 3. 実測 (測定 commit `2d73ba27`)

| export | 閉包の関数数 | 命令数 | 間接 call/jmp | うち近似 (`.pdata` 無し) | import 名数 |
|---|---:|---:|---:|---:|---:|
| Open | 13 | 407 | 0 | 6 | 6 |
| Close | 51 | 1,684 | 10 | 19 | 33 |
| REXCreate | 514 | 20,614 | 74 | 195 | 35 |
| REXDelete | 57 | 1,848 | 10 | 24 | 33 |
| REXGetCreatorInfo | **22** | **924** | **0** | 12 | 6 |
| REXGetInfo | 39 | 1,238 | 1 | 27 | 6 |
| REXGetInfoFromBuffer | 242 | 8,210 | 42 | 80 | 33 |
| REXGetSliceInfo | 125 | 5,987 | 9 | 47 | 35 |
| REXRenderPreviewBatch | 20 | 650 | 0 | 10 | 6 |
| REXRenderSlice | 168 | 7,549 | 15 | 68 | 35 |
| REXSetOutputSampleRate | 121 | 5,837 | 9 | 43 | 35 |
| REXSetPreviewTempo | 23 | 647 | 0 | 12 | 7 |
| REXStartPreview | 20 | 564 | 0 | 10 | 6 |
| REXStopPreview | 20 | 564 | 0 | 10 | 6 |
| **和集合 (14 export)** | **578 (関数の重複を除く)** | — | — | — | **35** |

- 命令数と間接数は export の間で重なるため、和集合の値は出さない (表は各 export 単独の値)。
- 単発実行の所要 0.61 秒 (`time` の real)。同じ入力で 2 回実行し、JSON が `cmp` で一致 (決定的)。

## 4. 読み (実測から言えること・推定)
- **最小単位の候補**: `REXGetCreatorInfo` (22 関数・924 命令・間接 0) と `REXGetInfo` (39・1,238・間接 1) は閉包が小さく、間接もほぼ無い。lift の最初の対象として妥当 [推定: x64c で閉包が取れるかは未検証]。
- **中核**: `REXCreate` (514) と `REXGetInfoFromBuffer` (242)・`REXRenderSlice` (168) は間接 call を 15〜74 件含む。間接の先は測定に含まれない (下限) ため、lift の完全性は未確認。
- **CRT 相当の閉包**: `Close` / `REXCreate` 等の閉包は FLS・heap・critical section・SEH (`RtlUnwindEx` 等) の import を含む。これは C++ 例外・TLS の初期化経路で、wasm 側の代替が要る (子 issue で扱う)。
- **近似の影響**: `approx` は閉包の 15〜40% 程度 (`.pdata` 無しの leaf 関数)。関数数・命令数の上限は近似で膨らみうる。正確な値は lift 後の関数単位突合で確定する。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 最小閉包 (`REXGetCreatorInfo` / `REXGetInfo`) の x64c lift と native 直実行の差分テスト (ネガコン込み) | lift 方式と差分ゲートが未検証 | #2733 (T-SH-44) |
| 中核閉包 (`REXCreate` / `REXGetInfoFromBuffer` / `REXRenderSlice`) の lift。間接 call 74 件の解決を含む | REX 読込の実機能が未実装 | #2733 (T-SH-44) |
| owner-only tier の side module 化・ビルドフラグ・release guard の deny-list 追加 (D20・D11) | 公開 tier への混入防止が未実装 | PM (D11 により手元で実施。本 PR の範囲外) |
| 33 バイナリの `REXCreate` 文字列の参照関係 (各 importer が呼ぶ export) | REX 読込の実利用経路が未確定 | #2734 (T-SH-45) の受入条件 |

## 6. 検証範囲
- **検証した**: `rex_closure.py` の閉包・命令数・間接数・import 解決が、同じ入力で再実行して一致すること。
- **範囲外**: lift・wasm 化・native との差分テスト (未実施)。`.pdata` 無し関数の範囲は近似。間接 call の先は含まない。`docs/DEFECTS.md` の類型との照合は lift 後に行う。
