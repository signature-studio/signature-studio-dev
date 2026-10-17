# tools/shared/lift/rex — REX Shared Library (win `block24351_PE.bin`) の export 閉包測定 — T-SH-11 (#153)

測定 commit: `2d73ba27` (`tools/shared/lift/rex/rex_closure.py` を最後に変更した commit。以降の差分は REPORT のみ)。
既知の類型との関係: 該当なし (lift していない)。

## 結論 (1 行)
REX DLL の export 14 本の閉包を `rex_closure.py` で実測 (0.6 秒・再実行で JSON 一致)。最小の `REXGetCreatorInfo` は 22 関数・924 命令・間接 0。`REXCreate` (514 関数) など REX 読込の中核は閉包が大きいため、lift と差分テストは子 issue に分ける。**lift は §7 (T-SH-44 #2733 の部分達成) に記録**。中核閉包 (REXCreate 等) の lift と参照元の特定は §8 (T-SH-45 #2734 の部分達成)。中核閉包の所有者限定 tier 配置と `REX_SIDE` 除外は付録 `REPORT_APPENDIX_2969.md` (T-SH-48 #2969 の部分達成)。

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
`.data` 書込の到達元は DllMain の `reason == 1` 経路で、方式 A (export 前に DllMain を 1 回呼ぶ) を採る (T-SH-129 #4833・正本は付録 `REPORT_APPENDIX_4833.md` §12)。`dllmain` モードの実測 (223 件 FAIL・host 依存の 6 バイト) は付録 `REPORT_APPENDIX_4834.md` §13。

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

測定 commit: `fe5f7a4f` (`tools/shared/lift/rex/` の最後のコード変更)。前回の測定 `744b5cfc` からの変更は、crash の fault アドレスの記録 (`native_ref.c`)・a0 の範囲別の件数 (`diff_test.py`)・`gen_cases.py` の docstring 修正だけ (比較の入力と比較結果は変わっていない: 133 / 133 一致)。以降の差分は本 REPORT のみ (差分 0 の証跡は §7.8)。
既知類型との関係: 該当なし (本測定で不一致 0)。閉包内の `movnti` 未対応 (x64c の unsup) は、比較した入力では実行されなかった (§7.5)。

### 7.1 結論 (1 行)
REXGetCreatorInfo / REXGetInfo の閉包 (x64c で 35 関数・982 命令) を lift して wasm (80,154 B) にし、元の機械語の直接実行と比べた。比較できた 133 case は戻り値・import 呼出回数・arena・.data が全バイト一致 (不一致 0)。ネガコン 2 件は FAIL。**ただし書込が発生した比較 case は 0 件** (全 133 件で arena・.data が入力・初期値から不変。ctx 大域は除く)。そのため書込バッファの一致は検証されておらず、成功経路 (戻り値 1 / 3) も未到達。書込の一致と成功経路は子 #2870 (T-SH-46) で、side module・ビルドフラグは子 #2896 (T-SH-47) で扱う。

### 7.2 対象と閉包 (x64c・測定 commit `fe5f7a4f`)
- DLL: `block24351_PE.bin` (SizeOfImage 0x6a000)。root は export wrapper の 2 本 (VA 0x1800011c0 = REXGetCreatorInfo / 0x180001130 = REXGetInfo)。
- `python3 tools/flelift/x64c.py --pe <dll> --entries <roots> --closure 99 --img 0x180000000 --shift 0x150000000 --img-size 0x6a000 --impbase 0x1D80000` の出力: 関数 35・命令 982・unlifted 0・unsup 25 箇所 (`movnti` 24・`repz ret` 1)・import 5 (GetLastError / RaiseException / ReleaseMutex / RtlPcToFileHeader / WaitForSingleObject)。
- §3 の RetDec 測定 (22 / 39 関数) とは数え方が違う (x64c は tail jmp と thunk を別に扱う)。本節の数値は x64c の出力そのもの。
- 配置: VA 0x180000000+RVA を wasm の 0x30000000+RVA へ写す (`--shift`)。DIR64 再配置 701 件を `rex_image.py` で適用し、native も同じ配置 (0x30000000 固定) で同じ再配置を適用する。

### 7.3 方法 (`tools/shared/lift/rex/`)
- `lift_x64c.sh` (ドライバ): x64c → `rex_image.py` → `gen_cases.py` → emcc (`rex_glue.c` + `tools/flelift/rt/fle_cpu.c`) → `native_ref.c` → `run_wasm.mjs` → `diff_test.py`。
- 参照: 元の機械語を RWX mmap で 0x30000000 に敷設し、ms_abi 関数ポインタで直接呼ぶ (`native_ref.c`)。被験: node で wasm を実行 (`run_wasm.mjs`)。
- 入力: `gen_cases.py` (seed 2733・200 case = 2 export × 100)。arena 64 KiB (0x30100000)。ctx 大域 (RVA 0x49e08) に arena 内の構造体を指す。根ノードの key は、`0x180019f0` の命令列を模倣した値 (`key_of`) で一致させる。
- 比較: RAX・import 呼出回数・arena 全体・.data (RVA 0x47000 + 0x1b1d8 B) の全バイト。
- 書込件数: `diff_test.py` が、比較した case ごとに native の arena と .data を入力 arena・初期 .data と比べ、変化した case を数える。ctx 大域 (8 B) は case ごとに入力で書き換えるので除く。
- import スタブは両側で同じ規約: WaitForSingleObject=0・ReleaseMutex=1・RtlPcToFileHeader=0・GetLastError=0。RaiseException は両側とも fail-fast (呼ばれたら失敗)。
- 除外: 元の機械語が SIGSEGV/SIGBUS または 300 ms を超えた case は、定義された結果が無いので比較から外す (wasm 側は実行しない)。内訳は `native_ref` の stderr で報告する: 件数 (SIGSEGV/SIGBUS と SIGALRM)・SIGSEGV/SIGBUS の fault アドレスの分類 (0x10000 未満 / arena 内 / image 内 / その他)・case ごとの行 (`[native] crash case=… addr=…`)。

### 7.4 実測 (測定 commit `fe5f7a4f`・`bash tools/shared/lift/rex/lift_x64c.sh all` を 3 回)
| 項目 | 値 |
|---|---|
| 本検査 `ok` | 比較 133 case 全一致 (不一致 0)。除外 67 件 (3 回とも同じ) |
| 除外の理由 (`native_ref` の stderr) | SIGSEGV/SIGBUS 66 件・SIGALRM (300 ms 超過) 1 件。SIGSEGV/SIGBUS の fault アドレス: 0x10000 未満 38 件・arena 内 0 件・image 内 0 件・その他 28 件 |
| a0 の範囲別の除外 (`diff_test`) | a0 が arena 外の入力 122 件のうち 40 件 (33%)、arena 内の 78 件のうち 27 件 (35%) (§7.6) |
| 比較の内訳 | REXGetCreatorInfo 69 / REXGetInfo 64 |
| 除外の内訳 | REXGetCreatorInfo 31 / REXGetInfo 36 (3 回の `all` の stderr で `fn=` 別に数えて各 run 一致) |
| 書込が発生した比較 case | **0 / 133** (arena 0・.data 0。ctx 大域は除く)。書込の一致は未検証 (§7.5 ⑥) |
| 戻り値の分布 (比較対象) | 0xca 44 / 0xcb 48 / 0xcc 41。成功 (1)・0x3 は 0 件 |
| 戻り値の意味 [推定: 命令列からの読み] | 0xca = 0x1de0 の検査失敗 / 0xcb = 第 2 引数 < 0x500 / 0xcc = 出力ポインタ NULL |
| import 経路 | 比較対象 133 件すべてで import (ロック系) を通過 |
| ネガコン `neg-cmp` | 比較対象の最初の case の 1 バイトを反転 → 1 件不一致 → FAIL (期待どおり) |
| ネガコン `neg-ctx` | wasm 側だけ ctx 大域を 0 → 133/133 不一致 → FAIL (期待どおり) |
| 所要 (n=3) | `all` の wall 7.0〜7.2 s (`time` の実測)。各モードの `elapsed` は 3 回とも `ok` 3 s・`neg-cmp` 2 s・`neg-ctx` 2 s (x64c・emcc・native・node・diff を含む)。load average (1 分値) は各 run の開始 0.09 / 0.16 / 0.29、終了 0.16 / 0.29 / 0.35 (4 vCPU)。展開直後の 1 回目の `ok` 単独は wall 2.5 s |

### 7.5 検証範囲 / 範囲外
- 範囲: 戻り値 0xca / 0xcb / 0xcc の 3 経路と、その経路で通る import・ロック・木の検索 (`0x1a80`) の挙動。
- 範囲外: ① 成功経路 (戻り値 1 / 3)。比較した 133 件は戻り値 0xca / 0xcb / 0xcc で返る経路で、木の検索 (`0x1a80`) の 1 段目を通るかは戻り値の分布からは読めない [推定。分岐の VA の逆アセ確認は未実施]。2 段目 (`0x12a50`) を通る入力が未構成で、`0x12ed0` が書く creator info は比較されていない。② 除外 67 件 (元の機械語が落ちる入力) の作り直し。③ `movnti` 24 箇所 (閉包内) は比較入力で未到達。到達すれば wasm は fail-fast で、差分は FAIL になる。④ side module 化・ビルドフラグ (子 #2896 [T-SH-47])・release guard の deny-list (D11。PM が手元で行う)。⑤ REXCreate 以下 (#2734)。⑥ 書込の一致: 比較した 133 case はいずれも arena・.data を書かなかった (`writes` = 0)。書込が起きる入力 (①) で初めて検証できる。書込の一致は未検証で、子 #2870 で検証する。

### 7.6 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 成功経路 (戻り値 1 / 3) の入力構成と差分 (`0x12a50` / `0x12ed0` の経路) | 出力の書込が比較されていない。書込の一致は未検証 (書込が発生した比較 case は 0 件) | 子 #2870 [T-SH-46] (親: #2733) |
| 元の機械語が落ちる 67 件 (SIGSEGV/SIGBUS 66・時間切れ 1)。fault アドレスは 0x10000 未満 38 件 (NULL 付近の参照と推定)・arena/image 内 0 件・その他 28 件。a0 の範囲との関係: a0 が arena 外の入力 122 件のうち 40 件、arena 内の 78 件のうち 27 件が落ちる。率はほぼ同じで、a0 の範囲外は原因として支持されない。a0 範囲別の fault 内訳は、外が NULL 付近 28・その他 12、内が NULL 付近 10・その他 16・時間切れ 1 (stderr 行と `cases.bin` から手で再集計)。原因は未切り分け | 比較数が 133/200 | 子 #2870 [T-SH-46] (受入 3) |
| side module 化・ビルドフラグ除外 (受入 5) | §10 で部分実装 (standalone wasm の複製とフラグ。SIDE_MODULE 形式は未達。公開 tier への結線は未実施) | 子 #3630 [T-SH-91] (SIDE_MODULE 形式・PM 判断待ち)。親 #2896 [T-SH-47] |
| release guard の deny-list 追加 (D11)。子 #2896 の範囲外 | 同上 | PM (#2896 本文の「範囲外の PM 作業」・D11) |
| `movnti` の x64c 対応 | memset の 8 箇所は a1 ≥ 0x70000 の入力で到達 (fail-fast)。reach 16 件は arena 0x80000 で完了 (#4324・`REPORT_APPENDIX_4324.md`)。memcpy の 16 箇所は直接 call では到達しない (静的読み。間接 call 経路は未確認) | 付録 `REPORT_APPENDIX_3589.md` (#3589)・`REPORT_APPENDIX_3894.md` (#3894: info 4 件はハーネスの arena 越境で、閾値 0x70000 は sweep で確定)。子 #3893 [T-SH-93] (memset の x64c 対応)・#3895 [T-SH-95] (REX_RUN_CRASHED=1 の停止) |
| REXCreate 以下の中核閉包の lift | REX 読込の実機能が未実装 | #2734 (T-SH-45) |

### 7.7 再現
```
FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_x64c.sh all   # ok + neg-cmp + neg-ctx
```
`<fl-win64 展開先>` は `extracted/block24351_PE.bin` を含むディレクトリ (`tar --zstd -xf fl-win64.tar.zst -C <dir> extracted/block24351_PE.bin`)。生成物は `tools/shared/work/lift/rex/` (gitignore)。

### 7.8 測定後のコード差分 (差分 0 の証跡)
`git diff fe5f7a4f HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (0 = コード差分なし。以降は本 REPORT の文言のみ)。HEAD は本 REPORT を含む commit。実行経路 (`tools/flelift`・`tools/shared/env.sh`) も範囲に含めた。

## 8. 中核閉包 (REXCreate / REXGetInfoFromBuffer / REXRenderSlice) の x64c lift と参照元の特定 — T-SH-45 (#2734, 部分達成)

測定 commit: `5fe86502` (`tools/shared/lift/rex/` の最後のコード変更: `importers.py` の store 検索の修正。`lift_core.sh` は `fa18c860` から変更なし)。以降の差分は本 REPORT のみ (差分 0 の証跡は §8.8)。
既知類型との関係: 該当なし (差分テストは未実施。unsup の内訳は §8.3)。

### 8.1 結論 (1 行)
3 export の閉包を x64c で lift して wasm (854,208 B) のコンパイルまで通した (519 関数・22,987 命令・unlifted callee 0・unsup 50)。REX export を呼ぶ importer は REX 本体を除く **32 件**で、GetProcAddress の結果を slot 経由で呼ぶ 1 段の静的追跡で確定した。REXGetInfoFromBuffer は 31 件の importer で slot に格納されるが、その呼出は 0 件 (未確認。§8.4)。**元の機械語との差分テストは未実施**: REX 入力 (`.rx2` 等) が素材に無い (受入 3)。差分・side module (受入 5) は子 issue に分けた (§8.5)。

### 8.2 方法
- lift: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_core.sh`。root は export の RVA 0x10b0 (REXCreate)・0x1170 (REXGetInfoFromBuffer)・0x1280 (REXRenderSlice)。`x64c.py --closure 99` (§7.2 と同じ配置) → emcc (`lift_x64c.sh` と同じ設定)。
- **間接 call/jmp の解決方法** (x64c の仕様。`tools/flelift/x64c.py` の `ott_dispatch`):
  1. IAT への直接 call (`call [rip+IAT]`) → import 名へ静的に直結 (34 名)。
  2. jump table (Delphi 形・MSVC 形) → 静的に展開 (`jt_ranges` 2 範囲)。
  3. それ以外の register 間接 call/jmp → 実行時に `ott_dispatch(t)` が lift 済み関数表 (519) と IAT pseudo-VA を引く。表に無い先は `ott_unlifted` で止まる (fail-fast)。**静的には先を確定しない**。
- importer: `python3 tools/shared/lift/rex/importers.py <fl-win64 展開先>` (`grep -rl REXCreate` で 33 件を取り、REX 本体 `block24351` を除く)。判定は次の 1 段:
  (1) `lea reg,[rip+d]` が REX 名の文字列 VA を指す → (2) 直後 12 命令以内の GetProcAddress 呼出 (`call`/`jmp [rip+IAT]`)。直接 call 先 (ヘルパ) は 2 段まで辿る → (3) 直後 4 命令以内 (rax を上書きする call/jmp/ret・rax への書込みの手前まで) の `mov [rip+S],rax` で slot S に束縛 → (4) `call [rip+S]` (または `mov reg,[rip+S]` の後 6 命令以内の `call reg`) を呼出とみなす。
  - 文字列の存在だけでは判定しない。IAT・遅延 import に REX 名は 0 件 (33 件すべて)。

### 8.3 実測 (測定 commit `5fe86502`・HEAD 上で実行。`lift_core.sh` は emcc 込みで 4 回、`importers.py` は 2 回)
| 項目 | 値 |
|---|---|
| 閉包 (3 root 同時) | 関数 519・命令 22,987・unlifted callee 0・import 34 (IAT 78 のうち使用 34) |
| root 別 (参考・単独) | REXCreate 481 関数・19,727 命令 / REXGetInfoFromBuffer 248・8,914 / REXRenderSlice 145・7,162 |
| unsup 50 箇所 | movnti 24・x87 14 (`fld` 3・`fstp` 2・`fyl2x`・`frndint`・`fxch`・`fsub`・`f2xm1`・`fld1`・`faddp`・`fscale`・`wait`)・repz ret 9・repne scasb 3。閉包内で実行されたかは未計測 |
| register 間接 call/jmp (`ott_dispatch`) | 101 サイト。静的に先を確定できたのは 0 件。表に無い先の件数は差分テスト未実施のため未計測 |
| wasm | 854,208 B (emcc 6.0.12・`-O1`)。コンパイル成功 (n=4 で同値)。`toolchain-emsdk` 素材は本 run に無いため、上流の `emsdk install 6.0.12` (`tools/m1/flags.sh` の pin と同版) を取得して実測 |
| 所要 | lift + emcc は `lift_core.sh` の elapsed で 6〜7 s (n=4)。load (1 分値) は開始 0.45〜0.61・終了 0.54〜0.67 (4 vCPU)。importer 解析 52.6〜53.7 s (n=2) |

注: §3 の間接数 (REXCreate 74・REXGetInfoFromBuffer 42・REXRenderSlice 15) は `rex_closure.py` (pefile の近似) の数え方で、x64c の 101 とは対応しない。比較しない。

### 8.4 参照元の特定 (受入 2)
- 33 件のうち REX 本体 `block24351` は export 本体で、GetProcAddress を持たない。残り **32 件が importer** で、全件が REX 名 12 件の文字列を参照し、GetProcAddress で解決する (IAT 直載せ 0 件・遅延 import 0 件)。
- 12 名の格納と呼出 (測定 commit `5fe86502`・`importers.py --json` の集計)。格納 = GetProcAddress の直後に rax を rip 相対 slot へ保存した importer 数。呼出 = その slot への `call [rip+S]` (または `mov reg,[rip+S]` の後の `call reg`) の件数:

| export | 格納 (slot へ束縛した importer) | 呼出を確定した importer (呼出件数) | 呼出を確認できない slot 読込 (importer) |
|---|---:|---|---|
| REXCreate | 32 | 31 (31) | 1 (`block24341`) |
| REXDelete | 32 | 32 (33) | 0 |
| REXGetInfo | 32 | 32 (32) | 1 (`block24341`。同 importer は同名の呼出も 1 件) |
| REXGetSliceInfo | 32 | 32 (32) | 0 |
| REXGetCreatorInfo | 32 | 31 (31) | 1 (`block24341`) |
| REXRenderSlice | 32 | 31 (31) | 1 (`block24341`) |
| REXSetOutputSampleRate | 32 | 2 (3) (`block23609`・`block24341`) | 0 |
| REXRenderPreviewBatch | 31 | 1 (1) (`block24341`) | 0 |
| REXSetPreviewTempo | 31 | 1 (1) (`block24341`) | 0 |
| REXStartPreview | 31 | 1 (1) (`block24341`) | 0 |
| REXStopPreview | 31 | 1 (1) (`block24341`) | 0 |
| REXGetInfoFromBuffer | 31 | **0 (0)** | 0 |

- REXGetInfoFromBuffer の呼出 0 件は「呼出が無い」の証明ではなく、本判定の範囲で確認できなかったという意味。判定は rip 相対の `mov reg,[rip+S]` と `call [rip+S]` だけを数える。`lea` で番地を取る参照・`cmp` の読込・構造体へ転記した後の参照は数えていない。
- `block24341` は 4 名 (REXCreate・REXGetCreatorInfo・REXGetInfo・REXRenderSlice) の slot を、直後に呼出を確認できない形で 1 件ずつ読む。REXGetInfoFromBuffer は同 importer で格納 1 件のみ (読込・呼出 0 件)。
- `block23609` の未束縛の GetProcAddress は 10 サイト (REXGetInfoFromBuffer 2・REXRenderPreviewBatch 2・REXSetPreviewTempo 2・REXStartPreview 2・REXStopPreview 2)。REXGetInfoFromBuffer の 1 サイト (0x18030e8c0) は、GetProcAddress の結果 (rax) を slot に保存する前に、次の GetProcAddress 呼出 (REXGetCreatorInfo) が rax を上書きする (逆アセンブルで確認)。もう 1 サイトは同じ規則で未束縛と判定したが、逆アセンブルは未確認。残り 4 名は rip 相対 slot への保存が無く、構造体への格納等は未確認。

### 8.5 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| REX 入力 (`.rx2` 等) が素材に無い。fl-win64 の全エントリ 25,168 件 (`tar --zstd -tf` の行数。ディレクトリ 1 件を含む。非ディレクトリ 25,167 件、`extracted/` 配下の通常ファイル 25,166 件) のうち、名前に REX・`.rx2`・`.rex` を含むものは 0 件 (大文字小文字を区別しない)。WORKFLOW §11 の許可素材名のどれも REX 入力を含むと確認できない。よって元の機械語との差分テスト (受入 3) と戻り値・書込・import の一致は未検証 | 中核閉包の動作は未確認。lift の正しさは未検証 | 子 [T-SH-49] (素材待ち: PM が REX 入力の素材名を定めて投入する) |
| 所有者限定 tier の side module 化・ビルドフラグ除外 (受入 5) を中核閉包へ適用 | 公開 tier への混入防止が未実施。現時点の生成物は `tools/shared/work/` (gitignore) のみで commit していない | 子 [T-SH-48] (関連 #2896) |
| register 間接 call 101 サイトの実行時の解決 (表に無い先の件数)・x64c unsup 50 箇所 (閉包内での到達) | 間接先と unsup の完全性は未確認 | 子 [T-SH-49] (差分テストで計数) |
| `block23609` の未束縛の GetProcAddress 10 サイト (REXGetInfoFromBuffer 2・REXRenderPreviewBatch 2・REXSetPreviewTempo 2・REXStartPreview 2・REXStopPreview 2) の格納先 (構造体等)・`block24341` の呼出を確認できない slot 読込 4 件 (REXCreate・REXGetCreatorInfo・REXGetInfo・REXRenderSlice)・REXGetInfoFromBuffer の呼出 (格納 31 件・呼出 0 件) | importer 32 件はすべて何らかの export の呼出を確定した。ただし REXGetInfoFromBuffer の呼出は未確認で、上の読込 4 件と未束縛 10 サイトの先は未確定 | 子 [T-SH-49] |

### 8.6 検証範囲
- **検証した**: lift (519 関数・unsup 50)・emcc のコンパイル (854,208 B・上流 emsdk 6.0.12 で 4 回)・importer 解析 (32 件・HEAD 上の 2 回で JSON が `cmp` 一致)。
- **範囲外**: 元の機械語との差分テスト・wasm の実行 (素材なし)・side module (受入 5)・成功経路。

### 8.7 再現
```
FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<emsdk 6.0.12 の emsdk_env.sh> bash tools/shared/lift/rex/lift_core.sh   # lift + wasm (コンパイル確認。EMSDK_ENV 省略時は `[EMSDK]` の emsdk_env.sh)
python3 tools/shared/lift/rex/importers.py <fl-win64 展開先> --json OUT.json        # importer 33 件 (REX 本体を含む)
```
`<fl-win64 展開先>` は `extracted/` を含むディレクトリ (`tar --zstd -xf fl-win64.tar.zst -C <dir>`)。生成物は `tools/shared/work/lift/rex-core/` (gitignore)。

### 8.8 測定後のコード差分 (差分 0 の証跡)
`git diff 5fe86502 HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (0 = コード差分なし)。HEAD は本 REPORT を含む commit。

## 9. 成功経路 (戻り値 1 / 3) と書込の一致 — T-SH-46 (#2870, 部分達成)

結論: 成功経路 (戻り値 1 / 3) に入る入力を追加し、比較対象に成功経路を含めた。arena 書込は元の機械語と全件一致。`.data` の一致・movnti は未解決 (到達元は付録 `REPORT_APPENDIX_4833.md` §12)。落ちる 73 件は全件分類した (T-SH-89・#3588。付録 `REPORT_APPENDIX_3588.md`)。測定 commit `80c5ff7a`。数値・未解決は付録 `REPORT_APPENDIX_2870.md` の §9.1・§9.3・§9.4 が正本 (§9 全文)。同 §9 の成功経路の続き (REXGetInfo fn=1 の成功経路。測定 commit `142df3b53`) は付録 `REPORT_APPENDIX_3587.md` §11 が正本で、`.data` の書込は DllMain の初期化で起きて export 経由では到達しない (子 #3850)。

## 10. 所有者限定 tier の side module 分離とビルドフラグ除外 — T-SH-47 (#2896)

測定 commit: `63e6c04d1` (`tools/shared/lift/rex/` の最後のコード変更。main 取り込みの merge)。以降の差分は本 REPORT のみ。旧測定 (`105733875`・133 件版) は `REPORT_APPENDIX_2896.md`。

### 10.1 結論と方法
- **結論 (1 行)**: 部分。REX の standalone wasm を所有者限定 tier の `owner/rex_side.wasm` に複製し、`REX_SIDE=0` で `owner/` から除外できるようにした。両フラグで `lift_x64c.sh all` が ALL OK。**SIDE_MODULE 形式 (dlopen 形) は未達** (§10.3 (a)・子 #3630)。**公開 tier への結線は未実施** (§10.3 (b))。
- フラグ `REX_SIDE` (既定 `1`、0/1 以外は exit 2)。`1` = `$W/owner/rex_side.wasm` (`rex.wasm` の複製。`cmp` で一致)。`0` = 空。`rex.wasm` は両フラグとも `$W` 直下に生成される (`REX_SIDE=0` でも残る)。フラグが切り替えるのは `owner/` への複製だけで、§10.1 の「分離」と §10.3 の「組み込みを切り替える単位」はこの範囲に限る。
- `ok`: 本検査 PASS 後に `owner/` を作り直して一覧を期待値と突合 (`1` で `owner/rex_side.wasm` の 1 行、`0` で 0 行。`0` では `*rex*`・`*glue*`・`*.c` も 0 件)。`neg-owner` は `owner/rex_glue.c` (ダミー) を足して突合し、FAIL を検出すれば exit 0。`all` = `ok neg-cmp neg-ctx neg-owner`。

### 10.2 実測 (測定 commit `63e6c04d1`・各フラグで `all` を 3 回。n=3)
| 項目 | `REX_SIDE=1` | `REX_SIDE=0` |
|---|---|---|
| `all` の wall (`time` の real) / rc | 7.69–7.86 s / 0 (3 回) | 7.70–7.74 s / 0 (3 回) |
| 本検査 `ok` (diff_test) | 248 件中 175 一致・不一致 0・除外 73 (3 回とも) | 同左 |
| 配信物の一覧 (`ok`) | `owner/rex_side.wasm` (3 回とも) | 空 (3 回とも) |
| sha256 | `rex.wasm` = `owner/rex_side.wasm` = `76dce05e…` (sha256sum・python `hashlib` で一致) | `owner/` は空 |
| neg-cmp / neg-ctx (diff_test の不一致) | 1 件 / 175 件 → 両方 FAIL (期待どおり) | 同左 |
| neg-owner (一覧突合) | `owner/rex_glue.c owner/rex_side.wasm` ≠ 期待 → FAIL | `owner/rex_glue.c` ≠ 期待 (空) → FAIL |

### 10.3 検証範囲 / 範囲外 / 未解決
- 検証した: 2 フラグ × 3 回の `all` (本検査・配信物の一覧・`cmp`・sha256・ネガコン 3 種)。独立検算は §10.4 の 1 行。
- 受入 1 は**部分**: `owner/rex_side.wasm` は `-sSTANDALONE_WASM=1 --no-entry` でビルドした `rex.wasm` の同一バイト複製で、side module 形式ではない。範囲外: (a) `-sSIDE_MODULE=2` の dlopen 形は作っていない (固定 VA 0x30000000 の画像と global 配置の再配置を要する)。(b) 公開 tier の配信 (`deploy/`・release guard) への結線は無い。(c) 配信側の host は未実装。本検査の範囲 (§7.5) は変えていない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) dlopen 形 (`-sSIDE_MODULE=2`・固定 VA・global 再配置)、(c) 組み込み先 host の実装 | side module の形式と結線が未決。`rex_side.wasm` を読む経路が無い | 子 #3630 [T-SH-91] (PM agent の判断待ち。既定案は現状の standalone 複製) |
| (b) 公開 tier の配信 (`deploy/`・release guard の deny-list) への結線 | `REX_SIDE=1` の配信物が公開 tier に載る経路は塞がれていない | PM (#2896 本文の「範囲外の PM 作業」・D11) |

### 10.4 再現
- `FL_WIN64_DIR=<fl-win64 展開先> REX_SIDE=1 bash tools/shared/lift/rex/lift_x64c.sh all` (`REX_SIDE=0` も同じ)。配信物の確認は `cd tools/shared/work/lift/rex && find owner -type f | sort && sha256sum rex.wasm owner/rex_side.wasm`。
- 独立検算 (一覧とハッシュを python で再計算): `cd tools/shared/work/lift/rex && python3 -c "import hashlib,pathlib; [print(hashlib.sha256(p.read_bytes()).hexdigest(), p) for p in sorted(pathlib.Path('owner').rglob('*')) if p.is_file()]"`。`REX_SIDE=1` では `owner/rex_side.wasm` 1 行に `76dce05e…` が出れば一致。

### 10.5 測定後のコード差分 (差分 0 の証跡)
`git diff 63e6c04d1 HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (0 = コード差分なし)。HEAD は本 REPORT を含む commit。
