# tools/shared/lift/rex — REX Shared Library (win `block24351_PE.bin`) の export 閉包測定 — T-SH-11 (#153)

測定 commit: `2d73ba27` (`tools/shared/lift/rex/rex_closure.py` を最後に変更した commit。以降の差分は REPORT のみ)。
既知の類型との関係: 該当なし (lift していない)。

## 結論 (1 行)
REX DLL の export 14 本の閉包を `rex_closure.py` で実測 (0.6 秒・再実行で JSON 一致)。最小の `REXGetCreatorInfo` は 22 関数・924 命令・間接 0。`REXCreate` (514 関数) など REX 読込の中核は閉包が大きいため、lift と差分テストは子 issue に分ける。**lift は §7 (T-SH-44 #2733 の部分達成) に記録**。

## 0. 位置づけ
- 方針: `docs/DECISIONS.md` D20 (#163 の PM 判断, 2026-10-14)。REX は**所有者限定 tier でのみ lift**し、FL 本体と別の side module にして、ビルドフラグで除外できる構成にする。優先度は低いまま。
- 路線: `docs/DECISIONS.md` D5。本測定は pefile + capstone だけを使い、RetDec は使わない。lift 方式 (x64c / liftlib) は子 issue で選ぶ。
- 本 PR の範囲: 閉包の測定と再現スクリプト。lift・差分テスト・side module は含まない (lift と差分は §7 で追記)。

## 1. 対象
- `REX Shared Library.dll` = fl-win64 の `extracted/block24351_PE.bin` (PE32+ x64, 321,848 B, ImageBase 0x180000000, `.text` RVA 0x1000・サイズ 0x320de)。`tools/shared/scripts/classify.py` の 24351 に対応。
- export 14 本: Open / Close / REXCreate / REXDelete / REXGetCreatorInfo / REXGetInfo / REXGetInfoFromBuffer / REXGetSliceInfo / REXRenderPreviewBatch / REXRenderSlice / REXSetOutputSampleRate / REXSetPreviewTempo / REXStartPreview / REXStopPreview。
- 直接 import (`pefile` で実測): KERNEL32 (77 名。名前付き、序数のみは 0) と WINMM `timeGetTime` (1 名)。閉包に現れる import は KERNEL32 の 35 名のみ (`timeGetTime` は閉包に現れない)。C++ ランタイムの DLL 名 import は無い (静的リンク)。
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
- **最小単位の候補**: `REXGetCreatorInfo` (22 関数・924 命令・間接 0) と `REXGetInfo` (39・1,238・間接 1) は閉包が小さく、間接もほぼ無い。ただし両者は近似比率が高く (`REXGetCreatorInfo` 12/22 = 55%、`REXGetInfo` 27/39 = 69%)、閉包の関数の半分以上が `.pdata` 無しの近似に依る。「小さい」は近似込みの値で、確定した大きさではない。lift の最初の対象として妥当 [推定: x64c で閉包が取れるかは未検証。近似関数の範囲が確定するまで、閉包の大きさは上限寄りの値として扱う]。
- **中核**: `REXCreate` (514) と `REXGetInfoFromBuffer` (242)・`REXRenderSlice` (168) は間接 call を 15〜74 件含む。間接の先は測定に含まれない (下限) ため、lift の完全性は未確認。
- **CRT 相当の閉包**: `Close` / `REXCreate` 等の閉包は FLS・heap・critical section・SEH (`RtlUnwindEx` 等) の import を含む。これは C++ 例外・TLS の初期化経路で、wasm 側の代替が要る (子 issue で扱う)。
- **近似の影響**: `approx` (`.pdata` 無しの関数) は閉包の 33〜69% を占める (§3 表の「うち近似」÷「閉包の関数数」。最小が `REXGetInfoFromBuffer` 80/242 = 33%、最大が `REXGetInfo` 27/39 = 69%)。関数数の少ない export ほど比率が高く、39 関数以下の 7 本は 46〜69%、51 関数以上の 7 本は 33〜42%。関数数・命令数の上限は近似で膨らみうる。正確な値は lift 後の関数単位突合で確定する。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 最小閉包 (`REXGetCreatorInfo` / `REXGetInfo`) の x64c lift と native 直実行の差分テスト (ネガコン込み) | lift 方式と差分ゲートが未検証 | #2733 (T-SH-44) |
| 中核閉包 (`REXCreate` / `REXGetInfoFromBuffer` / `REXRenderSlice`) の lift。間接 call 74 件の解決を含む | REX 読込の実機能が未実装 | #2734 (T-SH-45) |
| owner-only tier の side module 化・ビルドフラグ・release guard の deny-list 追加 (D20・D11) | 公開 tier への混入防止が未実装 | PM (D11 により手元で実施。本 PR の範囲外) |
| 33 バイナリの `REXCreate` 文字列の参照関係 (各 importer が呼ぶ export) | REX 読込の実利用経路が未確定 | #2734 (T-SH-45) の受入条件 |

## 6. 検証範囲
- **検証した**: `rex_closure.py` の閉包・命令数・間接数・import 解決が、同じ入力で再実行して一致すること。
- **範囲外**: lift・wasm 化・native との差分テスト (未実施)。`.pdata` 無し関数の範囲は近似。間接 call の先は含まない。`docs/DEFECTS.md` の類型との照合は lift 後に行う。

## 7. x64c lift と元の機械語との差分 — T-SH-44 (#2733) 部分達成

測定 commit: `7bbd5c86` (`tools/shared/lift/rex/` の最後のコード変更)。以降の差分は本 REPORT のみ (差分 0 の証跡は §7.8)。
既知類型との関係: 該当なし (本測定で不一致 0)。閉包内の `movnti` 未対応 (x64c の unsup) は、比較した入力では実行されなかった (§7.5)。

### 7.1 結論 (1 行)
REXGetCreatorInfo / REXGetInfo の閉包 (x64c で 35 関数・982 命令) を lift して wasm (80,154 B) にし、元の機械語の直接実行と比べた。比較できた 133 case は戻り値・import 呼出回数・arena・.data が全バイト一致 (不一致 0)。ネガコン 2 件は FAIL。**成功経路 (戻り値 1 / 3) は未到達**のため、受入条件は部分達成 (`Refs #2733`)。

### 7.2 対象と閉包 (x64c・測定 commit `7bbd5c86`)
- DLL: `block24351_PE.bin` (SizeOfImage 0x6a000)。root は export wrapper の 2 本 (VA 0x1800011c0 = REXGetCreatorInfo / 0x180001130 = REXGetInfo)。
- `python3 tools/flelift/x64c.py --pe <dll> --entries <roots> --closure 99 --img 0x180000000 --shift 0x150000000 --img-size 0x6a000 --impbase 0x1D80000` の出力: 関数 35・命令 982・unlifted 0・unsup 25 箇所 (`movnti` 24・`repz ret` 1)・import 5 (GetLastError / RaiseException / ReleaseMutex / RtlPcToFileHeader / WaitForSingleObject)。
- §3 の RetDec 測定 (22 / 39 関数) とは数え方が違う (x64c は tail jmp と thunk を別に扱う)。本節の数値は x64c の出力そのもの。
- 配置: VA 0x180000000+RVA を wasm の 0x30000000+RVA へ写す (`--shift`)。DIR64 再配置 701 件を `rex_image.py` で適用し、native も同じ配置 (0x30000000 固定) で同じ再配置を適用する。

### 7.3 方法 (`tools/shared/lift/rex/`)
- `lift_x64c.sh` (ドライバ): x64c → `rex_image.py` → `gen_cases.py` → emcc (`rex_glue.c` + `tools/flelift/rt/fle_cpu.c`) → `native_ref.c` → `run_wasm.mjs` → `diff_test.py`。
- 参照: 元の機械語を RWX mmap で 0x30000000 に敷設し、ms_abi 関数ポインタで直接呼ぶ (`native_ref.c`)。被験: node で wasm を実行 (`run_wasm.mjs`)。
- 入力: `gen_cases.py` (seed 2733・200 case = 2 export × 100)。arena 64 KiB (0x30100000)。ctx 大域 (RVA 0x49e08) に arena 内の構造体を指す。根ノードの key は、`0x180019f0` の命令列を模倣した値 (`key_of`) で一致させる。
- 比較: RAX・import 呼出回数・arena 全体・.data (RVA 0x47000 + 0x1b1d8 B) の全バイト。
- import スタブは両側で同じ規約: WaitForSingleObject=0・ReleaseMutex=1・RtlPcToFileHeader=0・GetLastError=0。RaiseException は両側とも fail-fast (呼ばれたら失敗)。
- 除外: 元の機械語が SIGSEGV または 300 ms を超えた case は、定義された結果が無いので比較から外す (wasm 側は実行しない)。件数は報告する。

### 7.4 実測 (測定 commit `7bbd5c86`・`bash tools/shared/lift/rex/lift_x64c.sh all`)
| 項目 | 値 |
|---|---|
| 本検査 `ok` | 比較 133 case 全一致 (不一致 0)。除外 67 件 |
| 比較の内訳 | REXGetCreatorInfo 69 / REXGetInfo 64 |
| 除外の内訳 | REXGetCreatorInfo 31 / REXGetInfo 36 |
| 戻り値の分布 (比較対象) | 0xca 44 / 0xcb 48 / 0xcc 41。成功 (1)・0x3 は 0 件 |
| 戻り値の意味 [推定: 命令列からの読み] | 0xca = 0x1de0 の検査失敗 / 0xcb = 第 2 引数 < 0x500 / 0xcc = 出力ポインタ NULL |
| import 経路 | 比較対象 133 件すべてで import (ロック系) を通過 |
| ネガコン `neg-cmp` | 比較対象の最初の case の 1 バイトを反転 → 1 件不一致 → FAIL (期待どおり) |
| ネガコン `neg-ctx` | wasm 側だけ ctx 大域を 0 → 133/133 不一致 → FAIL (期待どおり) |
| 所要 (`ok`) | 3 s (x64c・emcc・native・node・diff を含む全体)。`all` は 3 モード合計で約 10 s。load 開始 0.59 / 0.86 / 0.69 |

### 7.5 検証範囲 / 範囲外
- 範囲: 戻り値 0xca / 0xcb / 0xcc の 3 経路と、その経路で通る import・ロック・木の検索 (`0x1a80`) の挙動、arena と .data の書込。
- 範囲外: ① 成功経路 (戻り値 1 / 3)。木の 1 段目の検査は通るが、2 段目 (`0x12a50`) を通る入力が未構成で、`0x12ed0` が書く creator info は比較されていない。② 除外 67 件 (元の機械語が落ちる入力) の作り直し。③ `movnti` 24 箇所 (閉包内) は比較入力で未到達。到達すれば wasm は fail-fast で、差分は FAIL になる。④ 所有者限定 tier の side module 化・ビルドフラグ・release guard (受入 5、D20・D11)。⑤ REXCreate 以下 (#2734)。

### 7.6 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 成功経路 (戻り値 1 / 3) の入力構成と差分 (`0x12a50` / `0x12ed0` の経路) | 出力の書込が比較されていない。受入 2 の「書込バッファの一致」は未達 | 子 issue [T-SH-46] (本 PR で起票。親: #2733) |
| 元の機械語が落ちる 67 件の入力 (木のキーを arena 外の値で作る経路) | 比較数が 133/200 | 上の子 issue |
| 所有者限定 tier の side module 化・ビルドフラグ・release guard の deny-list (受入 5) | 公開 tier への混入防止が未実装 | PM (D11・D20 により手元で実施) |
| `movnti` 24 箇所の x64c 対応 | 閉包内で未到達。到達すると fail-fast | 上の子 issue の範囲に含める |
| REXCreate 以下の中核閉包の lift | REX 読込の実機能が未実装 | #2734 (T-SH-45) |

### 7.7 再現
```
FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_x64c.sh all   # ok + neg-cmp + neg-ctx
```
`<fl-win64 展開先>` は `extracted/block24351_PE.bin` を含むディレクトリ (`tar --zstd -xf fl-win64.tar.zst -C <dir> extracted/block24351_PE.bin`)。生成物は `tools/shared/work/lift/rex/` (gitignore)。
