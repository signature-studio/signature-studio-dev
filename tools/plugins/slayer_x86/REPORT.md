# tools/plugins/slayer_x86/REPORT.md — FL Slayer x86 engine (Slayer_Engine.dll) の結合方式と lift 方針 (#536)

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/slayer_x86/` のみ / 親 #207 (前段 PR #524・`tools/plugins/synth/REPORT.md` §1)
- 検証起点 commit: §5 の「検証の実行記録」の表 (スクリプトは コミット済み HEAD を `git worktree add --detach` で展開して実行)
- 再現: `bash tools/plugins/slayer_x86/slayer_x86.sh` (検査 C1〜C7 → ネガコン N1〜N7 → RetDec 計測。非 0 で終わる条件は §5)。 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし** (本件は静的解析で、差分試験を未実施。 RetDec の x86 出力は emcc -c 前の loud な IR 不正で、silent miscompile ではない)

## 0. 結論 (先出し)

1. **結合方式 = 殻が `32bit\ilbridge.exe` を別プロセスで起動し、その中で `Slayer_Engine.dll` を x86 VST2 plugin としてロードする (プロセス境界あり)。** 殻 (x64) が `Slayer_Engine.dll` を `LoadLibrary` するのではない
   (x64 プロセスは x86 DLL をロードできない)。 根拠は §1 の C1〜C7 (全 7 検査 PASS、ネガコン 7/7 が期待どおり FAIL)。
2. **lift 方針の決定 = 「32bit 鎖の整備」のうち、RetDec 鎖の 32bit 化ではなく x64c 系の ia32 front-end を整備して engine だけを lift する」。 `ilbridge.exe` の起動経路 (プロセス境界) は wasm では作らず、
   殻 → engine を同一 wasm 内の関数呼出にする。** 別実装・提供しないは採らない (理由 §3)。 実装は新規子 issue **#674** に起票した。
3. **RetDec 鎖を x86 engine に流用する案は不採用。** RetDec は完走する (rc 0、488 関数、11.5 s) が、`emcc -c` は 1 件目で不通過 (`%wide-string` の関数局所名を global 定数に使う不正 IR)。
   それだけを機械的に除いても 2 件目で不通過 (`lshr` 定数式)。 さらに 114/488 関数に `x86_fp80` が混入する (§4)。 `docs/DECISIONS.md` D5 とも整合 (RetDec は過去の試験的手段)。
4. **#207 の出口条件 (FL Slayer を含む synth 14 本の差分試験 bit-exact) は本 issue では満たせない。** 本 issue の受入条件 (結合方式の解析結果 + lift 方針の決定) は満たしたため PR は `Closes #536`。 #207 は `Refs`。

## 1. 結合方式の解析 (検査 C1〜C7)

アドレスは殻 (block 22433, `FL Slayer_x64.dll`, ImageBase 0x400000) は RVA、engine (block 22434, ImageBase 0x10000000) は VA。 経路探索は byte 走査の呼出グラフ
(`e8/e9 rel32` と `ff 25` thunk を `.text` 全体から拾い、`.pdata` の関数範囲に割り当てる近似。 命令境界は見ない) で、検査 C3 の経路は命令列と突き合わせて確認した (下表の根拠列)。

| 検査 | 内容 | 実測 | 根拠 |
|---|---|---|---|
| C1 | engine は x86 DLL・`.pdata` 無し・export は `main` のみ・import は KERNEL32 のみ | machine 0x14c、`.pdata` 0 B、exports `[main]` (1 件)、KERNEL32 55 関数 | PE ヘッダ |
| C2 | 殻が `Slayer_Engine.dll` (UTF-16 Delphi 文字列) を**ちょうど 1 箇所**で参照し、その関数が `System\Tools\Bridge\` も参照する | 参照 1 件: 関数 `0x4521e0` 内 `0x452419`。 同関数が `Bridge\` を 1 件参照 | `lea r8,[rip+0x18f]` (→ `Slayer_Engine.dll`) の直後に `call 0x413c80` で `rbp+0x20` の文字列を組み立て、`call 0x8529c0` (= `0x4529c0`) へ渡す |
| C3 | 生成関数 `0x4521e0` → ロード関数 `0x4529c0` → `0x35bf10` → `0x35d440` → `0x330aa0` → `0x330c40` → `0x32df80` (`CreateProcessW` を呼ぶ) の経路が存在 | 6 段で到達 | `0x4529c0` の失敗側は文字列「The plugin engine couldn't be loaded. Please make sure the plugin has been installed correctly.」を `+0xbc` 先のホストへ通知 |
| C4 | 殻が `32bit\ilbridge.exe`・`64bit\ilbridge.exe`・`-wrapper`・`-address`・`-processid` の文字列を持つ | 5 文字列とも各 1 件 (存在のみの検査) | `.rdata` の Delphi UnicodeString |
| C5 | `ilbridge.exe` の実体 (x86 EXE と x64 EXE) が FL に同梱され、共有メモリ/プロセス API を使う | block **24765** (x86 EXE, 4,124,744 B)・block **24766** (x64 EXE, 6,200,392 B)。 両方 `TBridgeCommandLineParams`・`OpenFileMappingW`・`MapViewOfFile`・`CreateFileMappingW`・`LoadLibraryW`・`GetProcAddress`・`OpenProcess` を持つ | `TBridgeCommandLineParams` を持つ PE は全 block 中この 2 本のみ (`grep -l -a`) |
| C6 | engine の `main` が VST2 の `main(audioMasterCallback)` で、`audioMaster(0, 1 /* audioMasterVersion */, 0,0,0,0)` を呼び、AEffect に magic `'VstP'` (0x56737450) を書く | `main`=0x10007ca0、`push 0 ×4; push 1; push 0; call esi` を確認。 `'VstP'` の即値は `.text` 内 1 箇所 (0x1000113d) | 命令列。 `0x10001000` 以降の `[eax+0x40]->vtable` 転送 stub が `AEffect.dispatcher/process/setParameter/getParameter` (offset 0x24/0x28/0x2c/0x30) |
| C7 | engine は SIMD 命令 0・x87 あり | 線形掃引 25,349 命令 (`.text` 73,002 B。 `.text` 内データが命令に化けるため近似): SIMD 0、x87 4,203 (mnemonic が `f` で始まるもの。 内訳: `fldcw` 32 + `fnstcw` 18 = 制御語 50、`fnstenv` 2 + `fldenv` 2、`fnsave` 2 + `frstor` 2 を**含む**)、間接 call 302 | capstone (CS_MODE_32) |

解釈:

- 殻の生成関数 `0x4521e0` は `Slayer_Engine.dll` のパスを組み立てて `0x4529c0` に渡し、`0x4529c0` は `0x35bf10` (bridge クライアントの生成。 `+0x761` に種別を保持) 経由で `CreateProcessW` を呼ぶ関数に到達する (C2・C3)。
  種別 (`0x35bdb0`) はロード対象 PE のヘッダを読む `0x1c0520` (RVA。 VA 0x5c0520) が決める。 `0x35bdb0` は直接ではなく、1 段のラッパ `0x1c0740` を呼び、そこから `0x1c0520` を呼ぶ。
  `0x1c0520` は `Machine` が 0x14c なら 32 ビット、0x200 / 0x8664 なら 64 ビットと分類し (`0x1c0659`〜`0x1c068c`)、
  `IMAGE_FILE_DLL` (0x2000) が立っていれば 32 ビットに種別コード 7、64 ビットに 6 を割り当てる (`0x1c0691`〜`0x1c06b7`)。 x86 の `Slayer_Engine.dll` は `Machine`=0x14c・DLL なので 32 ビット側 (コード 7)。
  `0x35bdb0` がコード 7 → 2、6 → 3 に写し (`0x35be46`〜`0x35be5b`)、この値が `this+0x761` に入る。
  `0x35d440` は `[this+0x761]` を `sub cl,2` / `sub cl,1` で判定し、2 の側は `0x330a80` を呼ぶ (`0x35d4dd`〜`0x35d4e1`)。 `0x330a80` は `.data` の `0x4b0330` を読み (RVA。 `0x4b0330` 自体の値は 0 で、ここは未解決)、
  続けて `0x35d4ee` の `[rip+0x16b54b]` が指す `.data` の間接スロット `0x4c8a40` を読む。 `0x4c8a40` の値は `0x4b0320` (`32bit\ilbridge.exe` の UnicodeString) で、3 の側 (`0x35d503`〜) は `0x4c7df0` → `0x4b0328` (`64bit\ilbridge.exe`) を選ぶ。
  つまり **x86 engine は `32bit\ilbridge.exe` に流れる** (手作業の逆アセンブル読み。 `slayer_x86.py` の検査には入れていない)。
  なお `0x35bdb0` が `0x1c0520` に渡す「対象 PE」が Slayer の engine であること自体 (引数の出所) は追っていない (**未確認**)。
  FL 全体の bridged 経路の一般解析は `tools/hostbridge/HOSTBRIDGE.md` §1.6 にあり、本件はその Slayer への適用。
- engine の `main` は VST2 の標準エントリで、`audioMaster` コールバック (殻/ブリッジ側が提供) を呼んで `AEffect` を返す (C6)。 つまり**ホスト API は VST2 だけ**で、FL の `TFruityHost` (Dispatcher ID) には直接触れない。
  engine 内の KERNEL32 import はヒープ・TLS・クリティカルセクション・`LoadLibraryA`/`GetProcAddress`/`GetModuleHandleA` (VC6 の CRT 由来) で、GUI/ファイル/音声 API は無い (C1)。
- **未確認**: 共有メモリ/イベントのメッセージ書式 (`ilbridge.exe` と殻の間)。 wasm では使わないため解析しない (§3 の方針で不要)。 殻 `0x35bf10` 以降の `TBridgeClient` の全 opcode は解析範囲外。

## 2. 範囲外 (弱めた主張)

- **結論 1 は静的解析に基づく推論**で、動的な確認 (実際に `ilbridge.exe` が engine をロードする様子の観測) は未実施。 Linux runner に Wine 無し。 C2〜C4 は参照関係・到達可能性の確認で、
  Slayer の経路が実行時に必ず `CreateProcessW` を通ることまでは示していない (上の「未確認」)。 一方、x64 プロセスは x86 DLL を `LoadLibrary` できない (OS の制約) ため、x86 の engine を使う以上
  プロセス境界を経由するしかない、という点が結論 1 の主な根拠。
- 殻の中の `Slayer_Engine.dll` 文字列の参照は C2 のとおり 1 件のみ。 ただし `0x4529c0` からは `LoadLibraryExW`・`GetProcAddress` を呼ぶ関数にも到達する (`0x4529c0` → `0x35bf10` → `0x346520` → … → `0x192e0`、depth 9)。
  これらが engine をロードする経路かどうかは追っていない (汎用の DLL ロード (VST plugin 一般) と見るのが自然だが**未確認**)。
- C3 の呼出グラフは `e8/e9 rel32` のみで、間接 call (vtable 経由) の先は追っていない。 経路が存在する (到達可能) ことは示すが、他に経路が無いことは示さない。

## 3. lift 方針の決定と理由

候補 3 つ (issue 受入条件) の評価:

| 候補 | 判定 | 理由 |
|---|---|---|
| **A. 32bit 鎖の整備 (x64c 系の ia32 front-end で engine のみ lift)** | **採用** | engine は小さい (`.text` 73,002 B、export `main` 1 つ、KERNEL32 のみ、SIMD 0)。 x87 は 4,203 / 25,349 命令 (16.6%、線形掃引の近似) あり、SIMD は 0。 x87 の f80→f64 lowering は `tools/plugins/p0c/REPORT.md` §3.4 で kernel 分類ごとに判定済み: f32 系 21 本と int32 系 8 本は実測 0 差分、f64 出力系 4 本は ±1 ulp が 0.018%、**int64 系 2 本は f64 経由で 64% 不一致** (i64 保持の lowering pass が必要と結論)。 engine の x87 は同じ分類で扱える見込み (**推定**。 engine 単体での実測は #674。 int64 系相当の命令が engine にあるかは未確認) |
| B. 別実装 | 不採用 | FL Slayer は reFX 由来の音源 (engine の VERSIONINFO に `CompanyName = reFX`・`LegalCopyright = Copyright (C) 2002/2003 reFX`、UTF-16) で、音の同一性を示す仕様が無い。 差分試験の参照 (native 実行) を作れる A のほうが出口条件 (#207) に合う |
| C. 提供しない | 不採用 | 受入条件の「決定がなければ FL Slayer は #207 の出口条件を満たせない」の裏返しで、提供しないと #207 の対象 14 本が 13 本になる。 A で最小コスト (engine 73 KB) で収まる見込みがあるため、先に A を試す (A が不成立の場合に C へ降りる判断を #674 の末尾に残す) |

A の中での方式選択:

- **RetDec 鎖の 32bit 化は採らない**。 `docs/DECISIONS.md` D5 (RetDec は過去の試験的手段・新規 lift は x64c) に従う。 実測でも §4 のとおり emcc 不通過の要因が 2 件連続で出て、x87 混入もある。
- **プロセス境界 (`ilbridge.exe`) は wasm では作らない**。 殻 → engine を wasm 内の関数呼出にする。 `tools/hostbridge/HOSTBRIDGE.md` §1.6 の wasm 移植方針 (bridged 無効化・`CreateProcessW` は shim で fail-fast、プロセス分離の目的は wasm の instance 分離で代替) と同じ。
  engine は 32bit (ILP32) のため、殻 (LP64 の x64 レイアウト) との間で `AEffect`・`ERect`・`VstEvents` 等のポインタ幅差を marshal する層が要る (#674)。
  engine の lift 先は wasm32 で自然にポインタ 4 B となるため、engine 側の構造体レイアウトは native のまま保てる (**推定**)。
- 殻側の `0x4529c0` (engine ロード) → `LoadLibrary("Slayer_Engine.dll")` の解決は #94 (HB-H4) の shim と接続する。

## 4. RetDec 計測 (情報。 合否に含めない。 n=3、同一結果)

`slayer_x86.py --probe-retdec <dir>` (`retdec-decompiler slayer_engine_x86.dll --timeout 250`、`emcc -c -O0`)。

| 項目 | 実測 (3 回とも同じ) |
|---|---|
| RetDec 終了コード / 所要 | 0 / 10.8–11.5 s (4 core runner、load 0.0〜1.2) |
| `define` 数 / `x86_fp80` を含む `define` | 488 / 114 (定義: `\n(?=define )` で分割した各関数本体に `x86_fp80` を含むもの) |
| `emcc -c` (無改変の IR) | rc 1: `se.ll:218:43: error: invalid use of function-local name` (`@global_var_10013c0c = constant [7 x i16] %wide-string`) |
| 上の 1 行を `zeroinitializer` に置換して再度 `emcc -c` | rc 1: `se2.ll:3270:41: error: lshr constexprs are no longer supported` (定数式の `lshr` が 18 箇所) |

x87 を含む関数数 114 は RetDec の IR 型。 機械語の x87 命令 4,203 (§1 C7) とは別の単位。 3 回目以降の阻害要因の有無は未調査 (打ち切り)。

## 5. 検証 (判定は fail-closed)

- `slayer_x86.py` は検査 C1〜C7 のどれかが不合格なら **exit 1**。 `[slayer_x86] OK (7/7)` は全て合格のときだけ出る。
- `slayer_x86.py --nega` は 7 つの入力を壊し、**壊した検査だけが FAIL する (他の検査は PASS のまま)** ことを確認する。 期待が外れた件数を `nega: N/7 miss` と出し、N>0 なら **exit 1**。
- `slayer_x86.sh` は上記 2 つのどちらかが非 0 なら (`set -e`) 落ちる。 RetDec 計測 (§4) は情報のみで合否に含めない (toolchain 素材が無い環境でも `--skip-probe` で 2 つは実行できる)。

ネガティブコントロール (`--nega`、各 1 箇所を壊す。 括弧内は壊した内容):

| NC | 壊した箇所 | 期待 | 実測 |
|---|---|---|---|
| N1 | engine の `Machine` を 0x14c → 0x8664 | C1 のみ FAIL | C1 FAIL・他 PASS |
| N2 | 殻の UTF-16 `Slayer_Engine.dll` を `Slayer_Engine.dlX` | C2 のみ FAIL | C2 FAIL・他 PASS |
| N3 | 殻の import 名 `CreateProcessW` → `CreateProcessX` | C3 のみ FAIL | C3 FAIL・他 PASS |
| N4 | 殻の UTF-16 `64bit\ilbridge.exe` を `64bit\ilbridgX.exe` | C4 のみ FAIL | C4 FAIL・他 PASS |
| N5 | x86 `ilbridge.exe` の `TBridgeCommandLineParams` を `TBridgeCommandLineParamX` | C5 のみ FAIL | C5 FAIL・他 PASS |
| N6 | engine `main` の `audioMaster` opcode (push 1 → push 2) | C6 のみ FAIL | C6 FAIL・他 PASS |
| N7 | engine の `.text` のパディング 3 B を `xorps xmm0,xmm0` に | C7 のみ FAIL | C7 FAIL・他 PASS |

開発中 (最初のコミット前) の初回実行で、C6 の検査自体の誤り (命令列の開始オフセットを 1 つ誤った) を `--nega` が「N6 以外の全ケースで `others_failed=[6]`」(= C6 が常に FAIL) として検出した。 `code[5:]` に直して 7/7 になった。
この経緯は未コミットの版でのもので、git 履歴には残っていない (コミットされているのは修正後の版)。

### 検証の実行記録

| 項目 | 値 |
|---|---|
| 検証起点 commit | `524af3e` (本 REPORT の最終版を含む HEAD。 検査の挙動は `55ee377` と同一。 下表は `524af3e` を detached worktree に展開して 1 回実行した実測) |
| 実行方法 | `git worktree add --detach <dir> 524af3e` で展開し `RUNNER_TEMP=/home/runner/work/_temp FL_WIN64_DIR=/home/runner/work/_temp/fl-win64 bash tools/plugins/slayer_x86/slayer_x86.sh` |
| 結果 | exit 0・`[slayer_x86] OK (7/7)`・`nega: 0/7 miss`・`[slayer_x86.sh] OK (51 s, load 0.71 0.63 0.36)`・`[probe] retdec rc=0 defines=488 defines_with_x86_fp80=114 emcc_rc=1` |
| 所要 (wall) | 51 s |
| load average | 開始時 0.33 / 終了時 (1 分平均) 0.71。 4 core の Actions runner、並列数 1 |
| 同条件の再現 | 直前の `30c444c` で 3 回 (各 51 s・exit 0・同じ判定) を確認済み (`55ee377`→`30c444c` は REPORT のみの差) |
| 内訳 | 本 run では内訳未計測。 前回 (`3163914`) の内訳: C1〜C7 5.5 s、`--nega` 37.7 s、`--probe-retdec` 11.5 s (n=3 は 11.45–11.53 s) |
| `git status --porcelain=v1 -- tools/plugins/slayer_x86` | 空 |
| 20 MiB 超の blob | 無し (`find tools/plugins/slayer_x86 -type f -size +20M`) |

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| x64c の ia32 front-end・engine の lift・x87 の意味論 (f80→f64 の bit 差分実測)・殻↔engine の marshal・engine 単体の native vs wasm 差分試験 | FL Slayer が #207 の出口条件を満たすのに必要 | **#674** (新規。 親 #207) |
| 殻の `LoadLibrary("Slayer_Engine.dll")` を engine wasm に解決する shim | 同上 | #674 に含める (shim の土台は #94 HB-H4) |
| `ilbridge.exe` のメッセージ書式 (共有メモリ/イベント) は未解析 | wasm では使わない方針のため影響なし。 方針変更 (ブリッジを残す) になった場合のみ必要 | 対応不要 (方針変更時に #94 へ) |
| 動的な確認 (Wine 等で `ilbridge.exe` が engine をロードする様子) 未実施 | §2 のとおり静的参照のみ | #674 の差分試験の前提に含める |

## 7. 成果物

| ファイル | 内容 |
|---|---|
| `slayer_x86.py` | 検査 C1〜C7・ネガコン `--nega`・RetDec 計測 `--probe-retdec` |
| `slayer_x86.sh` | 1 コマンド再現 (`--skip-probe` で RetDec 計測を飛ばす) |
