# reverb_delay REPORT 付録 (#523 PLG-F4-2 追補)

本体 `REPORT.md` の §12 に続く節。 250 行上限のため分割して置く。

## 13. #523 追補 (2026-10-13 · 測定起点 HEAD 986e7415 · 再測定)

- **測定起点**: main **986e7415** (§13 の測定はこの HEAD で行った。 本 PR は docs のみで engine コードは変更していない)。 `REPORT.md` §12 の起点 97f28539 は E6 修正 (b5372ec3) の親で、作業ブランチ `523-plg-f4-2-engine-lift` の起点。 両者は祖先関係 (97f28539 → 986e7415) にある。
- **素材の確認 (本 PR の fix run、2026-10-13 17:54 UTC)**: `$HOME/artifacts` には `fl-win64.tar.zst` (2.3 GB) のみ実在。 `toolchain-retdec` / `toolchain-emsdk` / `work-*` / `plugins-ott` は確認時点で不在。 したがって本 run では e2e・engine lift を再実行できず、 下表の数値は再現していない。 §13 の測定時に上記素材が揃っていたかは、 PR 本文の記録以外に確認できない。
- **run の別**: 19165 の測定は §12 (15:37:59–15:48:22 UTC、wall 10 分 23 秒、summary.csv 行あり) と §13 (wall 6 分 42 秒) の 2 回として記録されている。 条件 (IPPCODE 除外 + AVX 系 78 除外) は同じで、 wall が一致しないため同一 run の再掲ではないと判断した。 §13 の run の開始時刻は記録していない。 各 run は 1 回のみ。
- engine の正しさは示さない (到達性のみ)。 負荷 (load) は測定していない。

| engine | 条件 | lift rc | define | f80 関数 | `emcc -c` rc | lift 秒 (PR 本文) | wall (PR 本文) |
|---|---|--:|--:|--:|--:|--:|--:|
| 19165 Multiband Delay | IPPCODE 除外 + AVX 系 78 除外 (`avx_bad_ranges.py`) | 0 | 2,608 | 6 | **139 (segfault)** | 391 | 6 分 42 秒 |
| 19165 同上 | 同 + `PLUG_F80_LOWER=1` | 0 | 2,608 | 0 | **1** | 416 | 6 分 57 秒 |
| 19000 Delay 3 | `PLUG_F80_LOWER=1` (全 3,632 関数) | 0 | 4,107 | 0 | **0** | 未記録 | 2 分 7 秒 |

- 秒の列は PR 本文の値のみ。 旧版の付録は表見出しを「秒 (lift+emcc)」としていたが、本文の lift 時間 (391 s) と wall の内訳は記録になく、wall を正とする。

- **19165 segfault の位置**: `emcc` は `function_1800ceec0` の WebAssembly 命令選択 (DAG combine の `visitSTORE`) で落ちる。 同関数は x86_fp80 を含む (`final.ll` の f80 関数 6 本のうち 1 本)。 `PLUG_F80_LOWER=1` で f80 を外すと segfault は消える。
- **19165 の次の類型 (f80 lowering 後)**: `e.final.ll:273362: invalid cast opcode for cast from 'double' to 'i80'`。 `p0c/f80_lower.py` は `bitcast x86_fp80 to i80` (f80 のビット列を読む命令) を double に置換するが、`bitcast double to i80` を残す。 f80 のビット操作を扱えないことが原因と推定。 この類型は共有鎖 (`p0c/f80_lower.py`) の修正が必要で、T0/T1 の退行確認 (#523 受入条件 2) を伴うため、本 run では未修正。 **新類型 E7 (f80 ビット操作の lowering 漏れ)** として記録。 **§14 で改訂 (推定)**: 上流の lift 側の型誤りが本体の可能性が高い。 対処の順序は §14 を参照。
- **19000 の f80 lowering**: `PLUG_F80_LOWER=1` は f64 化で精度を落とす (53 bit 仮数)。 19000 の f80 関数 (`function_1800bcb00` ほか) の精度影響は未検証。 既定 (`PLUG_F80_LOWER=0`) では `emcc -c` が rc 1 のまま (REPORT §12 の既存結果)。
- 19165 の segfault の起点 (`function_1800ceec0`) と f80 6 本の内訳は測定時の `work/reverb_delay/engine19165_noipp_nobad/` (gitignore) に残したが、 本 runner の `work/` には存在しない。 再現手順は下記。

### 再現手順

```
source tools/plugins/reverb_delay/env.sh
python3 tools/plugins/reverb_delay/avx_bad_ranges.py 19165 > work/reverb_delay/bad19165.out
ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges $PWD/work/reverb_delay/bad19165.out" \
  ENGINE_TAG=_noipp_nobad bash tools/plugins/reverb_delay/engine_lift.sh 19165 1200
PLUG_F80_LOWER=1 bash tools/plugins/reverb_delay/engine_lift.sh 19000 800
```

注: `--exclude-ranges` には絶対パスを渡す (`engine_lift.sh` が `tools/plugins` へ cd するため相対パスは解決されない)。 再現には `fl-win64` に加えて `toolchain-retdec` / `toolchain-emsdk` が要る。

### 受入条件への対応 (#523)

1. 19000 は `PLUG_F80_LOWER=1` で `emcc -c` rc 0 (到達性のみ・精度未検証)。 19165 は未達 (E7)。 既定 (f80 lowering 無し) では両方未達。
2. 共有鎖 (`p0c/f80_lower.py`) は未変更のため退行確認は不要だが、E7 の修正時に必要。 未実施。
3. IPPCODE の扱い: 未決 (#38 [IPP-10] と PM 判断)。
4. LoadLibrary 結合解析: 未実施。

## 14. #523 E7 の切り分け (2026-10-13 · コード変更なし · 未再現)

- **位置付け**: §13 の E7 記述を本節で改訂する (診断は下記の推定を採る)。 測定値・rc・再現手順は §13 が正本。 本節は未再現の転記で、再測定はしていない。
- **IR 位置 (未再現・転記)**: `e.final.ll` の `function_1800ceec0` 内、ブロック `dec_label_pc_1800ceffe` の `bitcast x86_fp80 %12 to i80` → `trunc i80 to i64` → `inttoptr` (行 273381・273392 付近)、`sext i32 to i80` → `bitcast i80 to x86_fp80` (行 273480・273633 付近)。 行番号は f80 lowering 前基準。 別経路の同型は行 348058 以降。 `%12` は `load x86_fp80, x86_fp80* %11`、`%11 = bitcast ptr %rcx to x86_fp80*` と記録されているが、IR 抜粋は未確認。
- **推定原因 (推定)**: `%11` のポインタ型が f80 と推定されたのは lift 側 (RetDec の型推定) の誤りの可能性が高い。 整数スロットを f80 として読んでいるなら、`bitcast` 以前に型が違う。 `p0c/f80_lower.py` の通常モード (`token_lower`) は `x86_fp80`→`double` の型名置換と f80 定数・intrinsic 名の変換を行うが、`bitcast` 命令を書き換える規則を持たない。 そのため `bitcast x86_fp80 to i80` が `bitcast double to i80` になり、i80 を含む規則が無いまま残る。 これは `f80_lower.py` のコードを読んだうえの推定で、実行による確認はしていない。
- **対処方針 (未実施)**: (a) lift 側の型修復で `%11` の load を `i64` に差し替える (先に試す)。 (b) `f80_lower.py` に i80 ビット列の規則を足す (共有鎖のため T0/T1 退行確認が必要)。
- **残りの類型 (転記・未再現)**: 同 IR で `do not know how to soften fp_extend` と `no libcall available for fp_round with type f80` が出る (`f80_lower` 無し時と記録)。 E7 を消しても f80 の libcall が残るため、19165 が `emcc -c` rc 0 になるには E7 の修正に加えて f80 の扱いを決める必要がある。

## 15. #523 E7 の engine-local 修復の試行 (2026-10-13 · 実測 · 負の結果)

- **HEAD**: `80c32a06` (origin/main 起点の作業ブランチ。 測定コードは共有鎖を含めて未変更)。
- **再現 (lift + emcc, `ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges <78 件>" ENGINE_TAG=_noipp_nobad engine_lift.sh 19165 900`)**: summary `19165,2000,0,2608,6,241,139,0,139,612,2,445,0,608,2606`。 lift rc 0 / define 2,608 / f80 6 / `emcc -c` rc **139** (segfault) / wall 10 分 28 秒 / load 1.15 (5 分平均 0.99)。 §13 の 2 回目 (6 分 42 秒) と一致し、E7 の `invalid cast` は既定の経路では出ない (segfault が先に出る)。
- **試行 (engine-local)**: `e.final.ll` の x87 `load x86_fp80` (26 箇所) を `load i80` + `bitcast i80 to x86_fp80` に置換して `emcc -c` を再実行した。 結果は **rc 139 (segfault)** のまま。 IR 構文は有効になり、`do not know how to soften fp_extend` / `no libcall available for sint_to_fp with type f80` が出た。 置換は 7 秒で終わる再実行で、lift の再実行は不要。
- **判断**: segfault は `load` の型だけでは消えない。 §14 の推定 (E7 = 型誤り) は、少なくとも単独では成立しなかった。 残る経路は (a) f80 の libcall 不足 (`fp_extend` / `sint_to_fp` / `fp_round`) の共有鎖での扱い、(b) `function_1800ceec0` の DAG combine の segfault。 いずれも共有鎖 (`p0c/f80_lower.py` / lift) の変更になり、T0/T1 の退行確認 (#523 受入条件 2) が必要。 engine-local の試行は本節で打ち切り、修正コードは commit しない。

## 16. #523 segfault の切り分け (2026-10-13 · 実測 · 診断のみ · コード変更なし)

- **HEAD**: `13bdc5fe` (origin/main)。 測定入力は §15 と同じ `80c32a06` 系の engine lift 出力 (lift 側の差分 0。 `git diff 512c53ab origin/main -- tools/plugins/reverb_delay tools/lift tools/p0c` は空)。
- **再現 (19165, IPPCODE 除外 + AVX 系 78 除外)**: summary `19165,2000,0,2608,6,148,139,0,139,601,...`。 lift rc 0 / define 2,608 / f80 6 / `emcc -c` **rc 139**。 §15 と define・f80・rc が一致。 unimpl helper は 148 (§15 の 241 とは不一致。 未切り分け)。 601 は lift 段の秒数 (`engine_lift.sh` の `t1-t0`)。
- **スタック上限は原因でない**: `ulimit -s unlimited` でも rc 139。 クラッシュは `WebAssembly Instruction Selection` 中の `DAGCombiner::visitSTORE` (LLVM の DAG combine)。
- **落ちる関数は 2 つ**: 関数単位でスタブ化 (`unreachable` 置換・診断専用・コミットせず) して `emcc -c` を再実行したところ、`function_1800ceec0` (f80 参照 859 箇所) を外すと次は `function_1801439a0` (f80 参照 879 箇所) で落ち、両方を外すと segfault は消えた (rc 1)。 いずれも x87 を大量に含む。
- **両スタブ外し後の残り (ferror-limit=0)**: `emcc -c` rc 1 / error 296 件。 内訳は `no libcall available for fmul with type f80` 134、`fadd` 116、`do not know how to soften fp_extend` 22、`fp_round` 19、`sint_to_fp` 4、`frem` 1。 segfault 以外の未解決はすべて f80 の libcall 不足。
- **判断**: 19165 の `emcc -c` rc 0 の前提は「f80 の扱い」の 1 点に集約される。 f80 を f64 に下げる (`PLUG_F80_LOWER=1`) と segfault は消えた (§13 で 19165 rc 1 = E7)。 一方で E7 の型誤り推定は §15 で単独では成立しなかった。 次の判断は PM 側で、(a) f80 を持つ関数の扱い (精度を落とす lowering か、関数単位の除外か)、(b) x87 を含む 2 関数の DAG combine 回避 (LLVM 側・wasm backend の回避策) のどちらを取るか。
- **注意**: スタブ版の wasm は生成していない (関数を消すため miscompile)。 本節の数値は到達性の診断であり、engine の正しさは示さない。

## 18. #3446 (PLG-F4-4) 殻 ↔ engine DLL の結合方式 (2026-10-15 · 静的解析 · 測定 commit 1a72e7dbf)

- **既知類型との関係**: 該当なし (逆アセンブル・PE 解析のみ。 lift 鎖・IR は変更していない)。 測定は `tools/plugins/reverb_delay/shell_bind.py` (本節で追加。 gate 付き)。
- **素材**: `fl-win64` のみ (`$RUNNER_TEMP/fl-win64/extracted/block{18999,19000,19164,19165}_PE.bin`)。 engine の正しさや実行時の挙動は見ていない (範囲外)。
- **再現**: `FL_WIN64_DIR=<展開先> python3 tools/plugins/reverb_delay/shell_bind.py 18999 19000` (Delay 3) と `... 19164 19165` (Multiband Delay)。 両方とも rc 0・判定 `OK`。 NC: `--engine-name Nope_x64.dll` で rc 1・判定 `FAIL ['load', 'entry']` (経路と間接呼出が見つからないと落ちる)。

### 18-1. 結論 (先出し)

1. **結合方式は LoadLibrary + GetProcAddress (名前引き) で、殻が engine を読み込む。** engine 側から殻への関数ポインタ渡しは無い。 殻が自分の audioMaster コールバックの関数ポインタを engine の入口に渡し、engine が返す `AEffect*` を殻が保持する (VST2 の入口形)。
2. **入口の名前は 26 通りの候補表を総当たりする。** 殻は `VstPluginMain` / `VSTPluginMain` / `main` / `maiN` … (大文字小文字の違いを含む 26 件、Delphi UnicodeString) を順に `GetProcAddress` し、最初に成功した名前を使う。 両 engine では大文字小文字を区別した最初の一致が `VSTPluginMain` (表の 2 番目)。
3. **engine の入口は両 engine で別物**: Delay 3 engine (19000) の `VSTPluginMain` (RVA 0xe9a0) は `jmp ?CreateEngine` (RVA 0xe830) の trampoline。 Multiband Delay engine (19165) の `VSTPluginMain` (RVA 0x1d77f0) は本体 (`push rbx` で始まる)。 19165 の export は `VSTPluginMain` / `main` のみ。
4. **呼出境界 (殻 → engine)**: 入口は引数 1 つ (rcx = 殻のコールバック)、戻り値 rax = `AEffect*`。 殻は `AEffect*` を自分の object の `+0x9b4` に保存し、以後 `call [rax+8]` (AEffect.dispatcher、64-bit VST2 の配置) で呼ぶ。 dispatcher の初回呼出は `edx=0` (effOpen)・`r8=0`・`r9=0`・`[rsp+0x20]=NULL`・`[rsp+0x28]=0.0f`。

### 18-2. 殻の import と読込系 API の呼出位置 (shell_bind.py [1])

| 殻 | thunk (`jmp [IAT]`) の呼出位置 | 件数 |
|---|---|--:|
| 18999 Delay 3 | LoadLibraryW 0x44077b ほか 8 箇所 / LoadLibraryA 0x418cf1 / LoadLibraryExW 0x4158ab / GetProcAddress 10 箇所 | W 9・A 1・ExW 1・Gpa 10 |
| 19164 Multiband Delay | LoadLibraryW 0x4407db ほか 8 箇所 / LoadLibraryA 0x418cf1 / LoadLibraryExW 0x4158ab / GetProcAddress 10 箇所 | W 9・A 1・ExW 1・Gpa 10 |

- 殻の IAT には `kernel32!LoadLibraryA` / `LoadLibraryW` / `LoadLibraryExW` / `GetProcAddress` / `FreeLibrary` / `GetModuleHandleW` が並ぶ。 engine 経路の `LoadLibraryW` 呼出は 1 箇所 (下の経路)。 他の呼出はそれぞれ別の DLL (FL 本体側の API 解決) で、本節の対象外。

### 18-3. engine 名 → LoadLibraryW の経路 (shell_bind.py [2])

| 殻 | engine 名の UnicodeString | 参照 (`lea`, 1 箇所) | 直接 call で LoadLibraryW へ届く経路 |
|---|---|---|---|
| 18999 | `engine_x64.dll` (VA 0x6e9b44、長さ 14) | 0x6e999f (関数 0x6e9940) | 0x6e9940 → 0x6dcb80 → 0x440750 → `call LoadLibraryW` @0x44077b |
| 19164 | `Engine_x64.dll` (VA 0x6e6504、長さ 14) | 0x6e632f (関数 0x6e62d0) | 0x6e62d0 → 0x6d59b0 → 0x4407b0 → `call LoadLibraryW` @0x4407db |

- 0x440750 (18999 側) は、引数 `edx=0x8000` を `SetErrorMode` 相当 (0x41d520) で設定し、その間に `LoadLibraryW` を呼ぶ wrapper (0x41d520 の同定と 0x8000 = SEM_NOOPENFILEERRORBOX は SDK の定数からの推定)。 19164 側の 0x4407b0 も同形と推定 (未確認)。
- **未確定**: `LoadLibraryW` の引数は `obj+0x2a6` (18999 では 0x6dd0fe / 0x6dd0f0 で `UnicodeString` に複写) から来る。 この `+0x2a6` へ書く命令は殻の全 code に見当たらず (読み出しと比較 (0x6dfa30) のみ)、**読み込まれる実パスが `engine_x64.dll` であることは静的に確定できていない**。 参照元 0x6e9940 の `dir + engine_x64.dll` 連結結果は、0x6e9940 のローカル `[rbp+0x26a]` に複写されるだけで LoadLibrary へ届いていない (静的に追えた範囲)。

### 18-4. 候補表と解決名 (shell_bind.py [3][4])

- 候補表: 18999 は 26 件 (VA 0x73c468–0x73c530、8 バイト間隔、`.data` のポインタ配列)、19164 は 26 件 (VA 0x73b7f8–0x73b8c0)。 順序は両殻で同じ: `VstPluginMain, VSTPluginMain, main, maiN, maIn, maIN, mAin, mAiN, mAIn, mAIN, Main, MaiN, MaIn, MaIN, MAin, MAiN, MAIn, MAIN, vstpluginmain, VSTPluginMain, VSTPluginmain, VSTpluginmain, VSTpluginMain, vstPluginMain, vstPluginmain, vstpluginMain`。
- 候補表を参照する関数: 18999 0x6dc2d0 (`lea rbx,[rip+…]` で表の先頭 0x73c468 を参照)、19164 0x6d5100 (表の先頭 0x73b7f8 付近)。 いずれも直接 call 2 段の先で `GetProcAddress` の thunk を呼ぶ (18999: 0x6dc2a0 → 0x41d1b0 の 0x41d1de、19164: 0x41d1d0 の 0x41d1fe)。 wrapper (0x41d1b0 / 0x41d1d0) は、第 2 引数の上位 16 bit が 0 なら序数として直接渡し、そうでなければ文字列を変換してから渡す (変換関数の同定は未了)。
- 18999 では 0x6dc2d0 の呼出元は仮想メソッド (0x6dff80、vtable 上の位置 0x6db200 を `.text` 内で確認) で、0x6dff80 が明示名 (r8) を先に試し、失敗時に 0x6dc2d0 の総当たりへ回る。 19164 の仮想メソッド経由の呼出は未確認。
- 解決名: 両 engine の export と大文字小文字を区別して照合すると、最初の一致は `VSTPluginMain` (表の 2 番目)。 `VstPluginMain` (表の 1 番目) は両 engine に無い。

### 18-5. 呼出境界の実測 (shell_bind.py [5][6])

| 項目 | 18999 (Delay 3) | 19164 (Multiband Delay) |
|---|---|---|
| 入口の呼出 (解決した FARPROC) | 0x6dd3d5 `call [rbp+0x338]` (関数 0x6dcb80) | 0x6d6205 `call [rbp+0x338]` (関数 0x6d59b0) |
| 引数 (rcx) | `lea rcx,[rip-0x18d5]` → 0x6dbb00 (殻のコールバック) | `lea rcx,[rip-0x18d5]` → 0x6d4930 (殻のコールバック) |
| 戻り値 | rax → 0x6dd3e2 `mov [rcx+0x9b4], rax` | rax → 0x6d6212 `mov [rcx+0x9b4], rax` |
| コールバックの先頭 | `push` 6 個・`mov [rbp+0x30],rcx` … (rcx=effect、edx=opcode、r8d=index、r9=value、残りはスタック。 0x6dbb0f〜0x6dbb1a) | 同形 (0x6d4930 から push 6 個・`sub rsp,0x78`) |
| dispatcher 呼出 | 0x6dd6e9 `call [rax+8]` (rcx=`[obj+0x9b4]`、edx=0、r8=0、r9=0、`[rsp+0x20]`=0、`[rsp+0x28]`=0.0f) | 0x6d6519 `call [rax+8]` (同じ設定) |
| engine 側の入口 (shell_bind.py [6]) | `VSTPluginMain` = `jmp ?CreateEngine` (RVA 0xe9a0 → 0xe830)。 `CreateEngine` の引数型は `AEffect* (*)(audioMasterCallback)` (export 名のマングリングから) | `VSTPluginMain` = 本体 (RVA 0x1d77f0、`push rbx`)。 `CreateEngine` の export は無い |

- 呼出規約は Win64 (rcx/rdx/r8/r9 + スタック)。 戻り値は rax。 engine → 殻の方向の呼出 (engine が殻のコールバックを呼ぶ箇所) は本節で測っていない (範囲外)。
- `[rax+8]` が dispatcher であることは、VST2 SDK の 64-bit `AEffect` 配置 (magic: int32、dispatcher: offset 8) からの推定。 配置の実測はしていない。

### 18-6. 検証・限界

- 検証範囲: 殻と engine の PE 上の静的な呼出関係、export 名の照合、呼出の引数準備の静的読取り。 範囲外: 実行 (Wine 等での起動)、engine の正しさ、wasm へのリンク (#201 の出口条件側)。
- NC (ネガティブコントロール): 存在しない engine 名 `Nope_x64.dll` で経路と間接呼出の判定が落ちる (`FAIL ['load', 'entry']`、rc 1)。
- 鮮度: 測定 commit 1a72e7dbf。 以後の差分は本節の文書のみ (`git diff 1a72e7dbf HEAD -- tools/plugins/reverb_delay/shell_bind.py` の出力は 0 行)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `LoadLibraryW` の引数 (`obj+0x2a6`) の書込元が未特定。 読み込まれる実パスが `engine_x64.dll` / `Engine_x64.dll` であることは静的に未確認 | 結合の前提 (読み込む DLL の同一性) | 本 PR の未解決表 → #3446 へのコメント。 子 issue 化は PM 判断 |
| 殻 ↔ engine の実行時検証 (dispatcher 呼出の戻り値、コールバックの実際の引数) なし | ABI は静的推定 | #201 の差分試験 (出口条件 3) |
| 19164 の名前走査の仮想メソッド経由の呼出元 (18999 の 0x6dff80 相当) 未確認 | 19164 の解決経路の一部 | 同上 (本 PR の範囲外) |
| engine → 殻の呼出 (engine が殻のコールバックを呼ぶ箇所) の ABI 未測定 | 双方向の境界の一部 | #523 系 (PLG-F4-2、engine の lift 側) |
