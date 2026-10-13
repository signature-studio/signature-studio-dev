# tools/plugins/hostx REPORT — PLG-X host 統合 / big3p 12 本の方針決定と lift 前提の実測 (#210)

- 検証起点 commit: **a9fc9e4** (origin/main 7cb9e50 を基点とする `210-big3p-policy`)。§2〜§4 の数値は `bash tools/plugins/hostx/hostx_e2e.sh` をこの HEAD で 1 回実行して取得 (a9fc9e4 → eca788e の差分は `hostx_nega.sh` のみ。NC は eca788e で再実行)。
- 日付: 2026-10-13 / 担当 dir: `tools/plugins/hostx/` のみ (生成物は `tools/plugins/work/` = gitignore)
- 既知類型との関係: **(icall §4) D1 = 間接 call/jmp 脱落** が測定した 8 閉包すべてで再現 (§3)。f80 (x87) と `rep_stosb` の未実装 helper は `tools/plugins/REPORT.md` §4.3 / #538 の既知事象。新規類型なし。
- 範囲: issue #210 の「方針決定」(§1) と、手順 1 (固有閉包 lift → `emcc -c`) の再現 (§2)。**手順 2〜4 と出口条件 (差分試験 bit-exact・Render test .flp) は未達** (§6)。よって PR は `Refs #210`、`Closes` は付けない。

## 0. 結論 (先出し)

1. **12 本の分類**: lift する **6 本** (Wrapper×2 / Patcher×2 / MIDI Out / Video Player)、lift しない (推奨・ユーザ確認) **2 本** (Razer Chroma / ReWired)、ユーザ判断 **4 本** (ZGE / FL Mobile×3)。判断が要る 3 件は needs-user-input で起票: **#558** (Razer・ReWired)・**#559** (ZGE)・**#560** (FL Mobile×3)。回答がなければ #558 は「lift しない」、#559 は「保留 (#29 待ち)」、#560 は「対象外」で進める。
2. **「big3p 12 本」は呼称が不正確**: `PLUGIN_MATRIX` の scope は host 8 + big3p 4 (ZGE と FL Mobile×3)。推定 81 人日の内訳は host 21 + big3p 60 (matrix の Tier 規則 est_days の合計; 根拠の薄い機械推定)。同じ matrix の host の `Control Surface` は #205 (PLG-F8)、big3p の `DirectWave` / `FLEX` は `batch_plan.md` §7 の PLG-G4 側にあり、12 本には含まれない。
3. **lift の前提は再現した**: 合格必須 7 閉包 (Wrapper×2 / Patcher×2 / MIDI Out / Razer Chroma / Video Player) は RetDec + pass 鎖で **7/7 が `lift_rc=0`・`emcc -c` rc=0** (許可した未実装 helper は `rep_stosb_memset` 1 件のみ; Wrapper 2 本が持つ)。ReWired は f80 2 関数で `emcc -c` が失敗 (p0c の f80→f64 lowering を当てれば通る)。ZGE 殻は閉包が 0 件で lift 不能 (未計測)。
4. **ただし `emcc -c` 通過は正しさを意味しない**: 通った 7 閉包 + ReWired の機械語には非 IAT の間接 call が **計 2,181 site** あるが、lift 後 IR の間接 call は **0** (§3)。#199 (eq-filter) の 550 site と同じ (icall §4) D1 で、`batch_lift.sh` に icall 復元が未接続のため。**この鎖の出力に対する差分試験は、実施しても不一致になる**。復元の接続は既存 **#514** (PLG-F2-2)。本 PR では出口条件を満たさない。

## 1. 方針決定 (12 本の分類)

区分: **A = lift する** / **B = lift しない (推奨; ユーザ確認待ち)** / **C = ユーザ判断**。工数は matrix の Tier 規則 est_days (機械推定)。demo = demo .flp の出現数、preset = preset 数 (`PLUGIN_MATRIX.json` の `usage`)。

| plugin | block | Tier / 工数 | 区分 | 根拠 | 依存・次 |
|---|--:|---|---|---|---|
| Fruity Wrapper (Effects) | 19091 | T2 / 4 d | **A** | VST2 ホスト実体。ロード経路の解析と「wasm 同梱プラグイン表」の設計・PoC は #24 (closed) で完了。閉包 171 関数 / 84,695 B が lift・`emcc -c` 通過 (§2)。#46 (E2E-6: OTT を Wrapper 経由で発音) の前提。demo 2 | #514 (icall)・#195〜#197 (P0a/b/c)。host ID 54 が `hs_ids` に未登録 (shim 追加) |
| Fruity Wrapper (Generators) | 23676 | T2 / 4 d | **A** | 同上 (閉包 177 関数 / 84,891 B)。Effects 版との閉包ハッシュ重なり: 共通 162 / E のみ 9 / G のみ 15 distinct (§2) = 2 本目は差分のみ | 同上 |
| Patcher (Effects) | 19220 | T2 / 4 d | **A** | 内部にプラグインホストを持つ (RTTI にプラグイン/ホスト系クラス名 135 件、`TFruityPlugHost` など)。閉包 516 関数 / 173,324 B が通過。**Render test .flp を持つ唯一の本**で出口条件が最も具体的。demo 12・preset 137 | Wrapper の結線 (#33 PLG-E5 は Patcher を含む) |
| Patcher (Generators) | 24155 | T2 / 4 d | **A** | 閉包 513 関数 / 171,025 B が通過。E 版との重なり: 共通 466 / E のみ 48 / G のみ 45 distinct。demo 12・preset 172 | 同上 |
| MIDI Out | 23918 | T0 / 0.5 d | **A** | 12 本中で最小の閉包 (30 関数 / 9,086 B・lift 3 秒) が通過。殻に MIDI 出力固有の import は無く (全殻共通の winmm 4 関数のみ; §2)、出力は host 側 vtable 経由。ブラウザでは Web MIDI に接続する想定 (shim 側)。demo 3・preset 41 | #514。Web MIDI 出力 shim (起票先未定: Host shim #196 の範囲か PM 判断) |
| Fruity Video Player | 23674 | T1 / 1.5 d | **A (後順位)** | 閉包 63 関数 / 19,496 B が通過。`ILVideo_*` の文字列 21 種を持ち (復号は libILVideo 経由)、FFmpeg の wasm 再ビルド + libILVideo wrapper は #149 (closed)。描画は #29 (PLG-E2)。demo 0・preset 1 で優先度は低い | #29 の描画経路・#514 |
| Razer Chroma | 19244 | T1 / 1.5 d | **B** | `RzChromaSDK64.dll` を動的ロードして Razer 周辺機器の LED を制御する (殻の文字列 23 hit)。音声処理なし・host ID 36 を 1 回呼ぶだけ。ブラウザから周辺機器に届かない。閉包 32 関数は通過するため**技術障害ではなく方針の問題**。demo 0・preset 0 | **#558** |
| ReWired | 24161 | T1 / 1.5 d | **B** | ReWire は別プロセスの ReWire ホスト/デバイスとの音声・MIDI ルーティングで、ブラウザに相手方がいない (仕様上の推論。殻内に `ReWire.dll` / `ReWireDebug.dll` の文字列)。技術的にも `emcc -c` 失敗 (f80 2 関数 + 未実装 helper 1; §2)。demo 0・preset 5 | **#558** |
| ZGameEditor Visualizer | 19304 (+19299/19300/19303/19305/19306) | T3 / 15 d | **C** | 殻 7.6 MB は現行鎖で閉包 0 件 (lift 未計測)。NDI 27 MB (ネットワーク; D3 対象外)・Spout (Windows 共有テクスチャ)・DMX/Hue/OSC 出力は切り落とす前提でも、OpenGL 描画 (`opengl32`) の WebGL 化 (#29) が未達。demo 9・preset 230 でユーザに見える | **#559** |
| FL Studio Mobile Rack FX | 18976 | T3 / 15 d | **C** | MSVC C++ engine 8.2 MB・16,261 関数。窓 lift は 3 窓中 1 窓が `emcc -c` 失敗 (§4)。sqlite / FLAC / élastique / DirectWave を内包し、再配布条件は #163 待ち。demo 0・preset 31 | **#560** |
| FL Studio Mobile Rack | 23605 | T3 / 15 d | **C** | Rack FX と関数ハッシュの 90.8% が共通 (§4) = 実質同一エンジン。demo 0・preset 0 | **#560** |
| FL Studio Mobile | 22444 | T3 / 15 d | **C** | engine 12.1 MB・24,237 関数 + `FLMManagedBridge_x64.dll` (`mscoree.dll` を import = .NET CLR 経由と推定; wasm に載らない)・`ws2_32` 20 import (FL Cloud 等; D3 対象外)。demo 0・preset 0 | **#560** |

- **機能単位で切り落とすもの** (`docs/DECISIONS.md` D3 外部通信機能は対象外): Wrapper / Patcher の FL Cloud 系 (RTTI の `TCloudPluginsLicenseEngine` / `TFLCloudPluginHost`)、32bit プラグイン用 `ilbridge.exe` bridged 経路 (#24 の設計どおり wasm では instance 分離で代替)、ZGE の NDI、FL Mobile の winsock。
- **A の合計工数**: matrix の est_days で 4+4+4+4+0.5+1.5 = **18 人日**。ただし §3 のとおり icall 復元 (#514) 前の lift 出力は使えず、実作業量の見積りは #514 完了後に再推定する。
- 区分 B/C の 6 本は、ユーザ判断までの間 lift しない。FLP 上の未対応プラグインを「state を保持して素通し」にする共通扱いは各 issue に選択肢として書いた。

## 2. 手順 1: 固有閉包 lift の結果 (`work/batch/status.csv`, `work/hostx/`)

閉包 = DSP エントリ (vtable override) から `call/jmp rel32` で到達する固有関数 (framework 共通 13 DLL 以上は除外; 定義は `lift/plugin_closure.py`)。`defines` = `p.final.ll` の `^define` 数、`seconds` = `lift_ranges.sh` の実測秒。

| block | plugin | 閉包関数 | 閉包 x86 B | defines | lift_rc | 未実装 helper | f80 関数 | emcc -c rc | seconds |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 19091 | Wrapper (E) | 171 | 84,695 | 173 | 0 | 1 (`rep_stosb_memset`) | 0 | 0 | 10 |
| 23676 | Wrapper (G) | 177 | 84,891 | 179 | 0 | 1 (同上) | 0 | 0 | 10 |
| 19220 | Patcher (E) | 516 | 173,324 | 522 | 0 | 0 | 0 | 0 | 21 |
| 24155 | Patcher (G) | 513 | 171,025 | 519 | 0 | 0 | 0 | 0 | 21 |
| 23918 | MIDI Out | 30 | 9,086 | 30 | 0 | 0 | 0 | 0 | 3 |
| 19244 | Razer Chroma | 32 | 9,729 | 32 | 0 | 0 | 0 | 0 | 4 |
| 23674 | Video Player | 63 | 19,496 | 63 | 0 | 0 | 0 | 0 | 3 |
| 24161 | ReWired | 102 | 18,488 | 102 | 0 | 1 | **2** | **1** | 3 |
| 19304 | ZGE 殻 | 0 | 0 | 0 | **1** | - | - | **1** | 0 |

- 合格必須 7 本の判定は `judge.py` (`lift_rc` / 未実装 helper / f80 / `emcc_c_rc` がすべて 0。未実装 helper は名前が `--allow-unimpl rep_stosb_memset` に含まれるときだけ許可) で **7/7 合格・bad=0**。`rep_stosb_memset` は memset へ写像可能で、`tools/plugins/REPORT.md` §4.3 / #538 で追跡されている。
- 既知不合格 2 本の状態固定 (`expect_state.py`): ReWired は f80=2・unimpl=1・emcc rc=1、ZGE 殻は `lift_rc=1` のまま = **期待どおり**。合格に変わると exit 1 になり、本 §1 の区分の見直しが要る。
- **ReWired の f80**: `function_6f1ff0` / `function_6f5f30` の 2 関数が `x86_fp80` を含み、`emcc -c` は `do not know how to soften fp_extend` / `no libcall available for fadd with type f80` で失敗する。`p0c/f80_lower.py --no-rint` を当てると **x86_fp80 行 0・`emcc -c` rc 0** (到達性のみ。lowering 後の数値の正しさは未検証)。
- **ZGE 殻**: `plugin_closure.py` が vtable 入口を 1 件も見つけず (`entries` が空)、`lift_ranges.sh` が空の range で `invalid range` を出して終わる。ZGE 殻は標準の Fruity 入口を持たない構造の可能性があるが、原因は未切り分け (§6)。
- **matrix との突合** (`matrix_check.py`): `PLUGIN_MATRIX.json` の `lift` 欄 (closure_funcs / closure_bytes / lift_rc / emcc_c_rc / defines など) と **48/48 項目が一致** (ZGE 殻は matrix に lift 欄がなく比較対象外 1 本)。
- **host 呼出の規模** (`closure_facts.py`、閉包 ranges 内の host vtable 呼出 site 数): Wrapper 54/61 (E/G; うち ID が動的な site 22)、Patcher 36/35 (動的 8)、ReWired 23 (動的 3)、MIDI Out 29 (slot 0x48 が 23)、Video Player 22 (動的 5)、Razer 1。Wrapper の ID 54、Patcher の ID 96 は `framework/hostshim/hs_ids.json` に未登録。
- **import の外形** (`static_facts.py`): 8 本の Delphi 殻は kernel32 / user32 / gdi32 系を除くと winmm 4 関数のみを共通に import し、MIDI Out / Razer / ReWired に固有の外部 DLL import は無い (Razer は `LoadLibrary` で `RzChromaSDK64.dll` を動的ロード)。ZGE 殻だけが `opengl32` / `wsock32` / `mpr` を import する。全 18 モジュールの表は `work/hostx/static.md` (再生成物)。

## 3. 間接 call 監査 (`hostx/icall_audit.py` → `tools/icall/audit_icall.py --funcs <閉包関数 VA> --ir p.final.ll`)

定義: 「静的 site」= 閉包関数範囲の非 IAT 間接 call 命令数。「IR の間接 call」= `p.final.ll` で callee が `@name` でない call の数 (`audit_icall` の `ir_call_ind_total`)。独立の数え方として、IR の `call` 行のうち `@` を含まないものを grep で数えた値を併記。

| block | plugin | 静的 site | call あり関数 | IR の間接 call | 同 (grep) | IR の call 行 | 閉包関数 |
|--:|---|--:|--:|--:|--:|--:|--:|
| 19091 | Wrapper (E) | 353 | 101 | 0 | 0 | 2,119 | 171 |
| 23676 | Wrapper (G) | 348 | 104 | 0 | 0 | 2,198 | 177 |
| 19220 | Patcher (E) | 596 | 221 | 0 | 0 | 4,653 | 516 |
| 24155 | Patcher (G) | 583 | 222 | 0 | 0 | 4,587 | 513 |
| 23918 | MIDI Out | 69 | 19 | 0 | 0 | 226 | 30 |
| 19244 | Razer Chroma | 23 | 10 | 0 | 0 | 455 | 32 |
| 23674 | Video Player | 112 | 32 | 0 | 0 | 497 | 63 |
| 24161 | ReWired | 97 | 47 | 0 | 0 | 505 | 102 |
| 合計 | | **2,181** | | **0** | **0** | 15,240 | |

- 8 閉包すべてで「静的 site > 0 かつ IR 0」。機械語側の間接 call は vtable 呼出 (host / 仮想メソッド) とジャンプ先が実行時に決まる呼出で、脱落すると host への発行 (`Dispatcher` ID・MIDI 出力など) が IR から消える。**判定の識別力は `emcc -c` rc には無く、この表が gate になる** (#514 の「回帰ゲート」の対象にこの 8 閉包を加えることを提案)。
- 別算法の検算 (`hostx/xcheck_icall.py`: 閉包 ranges の capstone 線形 sweep; `audit_icall` は recursive descent): 合計 **2,297 (線形) vs 2,181 (audit)**。MIDI Out (69) と Razer (23) は一致、他 6 本は線形 sweep が +1〜+46 多い (Patcher (E) +46 / (G) +45、Wrapper +8/+8、Video Player +8、ReWired +1)。線形 sweep が関数範囲内のインライン data (jump table 等) を命令として復号するための上振れと推定するが、差分 site の切り分けは未実施。**どちらの数え方でも静的 site は 0 ではなく、IR 側 0 との結論は変わらない**。

## 4. FL Studio Mobile の C++ engine: 窓 lift の到達性 (`hostx/engine_sample.sh`)

全関数ではなく `.pdata` 関数をアドレス順に並べ、先頭 / 1/3 / 2/3 位置から各 300 関数の窓を RetDec + pass 鎖で lift → `emcc -c`。`unimpl` = 窓の `p.simd.log` が報告する未実装 helper 数。

| engine | 窓 | 開始 index | 窓の x86 B | lift_rc | defines | f80 関数 | unimpl | emcc -c rc | lift 秒 | 最初の error |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|---|
| Rack FX 18976 | w0 | 0 | 204,868 | 0 | 415 | 0 | 122 | 0 | 66 | |
| Rack FX 18976 | w1 | 5,420 | 69,333 | 0 | 344 | 0 | 0 | 0 | 26 | |
| Rack FX 18976 | w2 | 10,840 | 98,779 | 0 | 315 | 0 | 2 | **1** | 26 | `use of undefined value '%104'` |
| Mobile 22444 | w0 | 0 | 204,868 | 0 | 415 | 0 | 122 | 0 | 68 | |
| Mobile 22444 | w1 | 8,079 | 76,217 | 0 | 353 | 0 | 0 | 0 | 28 | |
| Mobile 22444 | w2 | 16,158 | 88,498 | 0 | 323 | 0 | 4 | **1** | 25 | `expected type` |

- 6 窓中 **2 窓が `emcc -c` 失敗** (LLVM IR の型・SSA 整合の崩れ)。w0 が通っても未実装 helper 122 件を含む (先頭窓は両 engine で同一規模: 同じ 204,868 B・415 defines・unimpl 122)。C++ engine を現行鎖でそのまま lift する経路は未成立で、同種の問題は #527 (PLG-F5-2) で追跡中。FLEngine と同じ x64c 経路 (`tools/flelift`) の適用可否は未測定 (#560 の選択肢 B)。
- **エンジンの重なり** (`closure_facts.py`: `.pdata` 全関数の位置非依存ハッシュ; 分母は a の関数数、割合は a の関数のうち b に同ハッシュがあるもの): Rack FX → Rack **14,759 / 16,261 = 90.8%** (バイト加重 67.2%)、Rack → Rack FX 14,759 / 16,265 = 90.7%、Rack FX → Mobile 14,241 / 16,261 = 87.6% (バイト加重 59.5%)、Mobile → Rack FX 17,252 / 24,237 = 71.2% (バイト加重 43.6%)。Rack FX と Rack は実質同一エンジン。

## 5. 検算とネガティブコントロール (`bash tools/plugins/hostx/hostx_nega.sh`、4.6 秒、eca788e)

| 検査 | 壊し方 | 結果 |
|---|---|---|
| NC1 `emcc -c` rc | MIDI Out の `p.final.ll` の 1 関数から `ret` を除去 | 無改変 rc 0 → 壊した IR rc 1 |
| NC2 閉包 → define 数 | 閉包 29 range の末尾 1 本を落として再 lift | defines 30 → 28、落とした `function_701d90` は 1 → 0 |
| NC3 `judge.py` の識別力 | 実測 / 許可名なし / 許可名違い / `emcc_c_rc=1` の合成行 / 行欠落 | rc 0 / 1 / 1 / 1 / 1 (期待どおり) |
| NC4 `expect_state.py` | ReWired を合格値 (f80=0, emcc rc=0) にした合成 CSV | 実測 rc 0 → 合成 rc 1 |
| NC5 `matrix_check.py` | Patcher (E) の `closure_bytes` を +1 した合成 facts | 実測 rc 0 → 合成 rc 1 (MISMATCH 1 行) |
| NC6 間接 call 監査の識別力 | MIDI Out の先頭関数に間接 call を 1 本注入 | `audit_icall` の IR 間接 call 0 → 1、grep 側も 0 → 1 |

別算法の検算は §3 の線形 sweep と grep の 2 本。環境: GitHub Actions runner (`nproc`=4)。`hostx_e2e.sh` 全体 **7 分 29.6 秒** (n=1; 開始時 load average 0.59 / 1.73 / 3.81、終了時 0.92 / 1.14 / 2.71、並列 1)。内訳は lift 計 75 秒 (§2 の seconds 合計) と C++ 窓 lift 計 239 秒 (§4) が主。n=3 のレンジは 60 分枠のため取っていない。決定的な値 (閉包数・defines・rc) は、1 つ前の HEAD (45992cb) の初回実行の `[batch]` 9 行と一致した。

## 6. 範囲外・未解決

検証範囲: 手順 1 の再現、IR の間接 call 件数の静的比較、C++ engine の窓 lift の到達性。**native との出力比較は 1 件も実施していない**。Render test .flp (Patcher の 2 本) による E2E も未実施。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `batch_lift.sh` に icall 復元が無く、8 閉包で 2,181 site 脱落 | 区分 A の 6 本 + ReWired。接続しない限り差分試験は必ず不一致 | 既存 **#514** にコメント (この 8 閉包を回帰ゲートに加える) |
| 差分試験 (native ms_abi vs wasm) と共有 framework wasm / Host shim とのリンク | 出口条件 | 既存 #195 (P0a) / #196 (P0b) / #197 (P0c) の完了待ち。本 issue #210 に残す |
| Razer Chroma・ReWired の対象外確定 | 区分 B | **#558** (needs-user-input) |
| ZGE の扱い。殻の閉包が 0 件になる原因 (標準入口を持たない構造か) は未切り分け | 区分 C | **#559** (needs-user-input) |
| FL Mobile×3 の扱い。C++ engine の窓 lift が 6 窓中 2 窓で失敗 | 区分 C | **#560** (needs-user-input)・技術面は既存 #527 |
| Wrapper の host ID 54 / Patcher の host ID 96 が `hs_ids.json` に未登録 | Wrapper / Patcher を framework とリンクする段 | 既存 #196 (P0b) にコメント |
| MIDI Out の出力先 (Web MIDI) の shim | MIDI Out の動作 | 起票先未定。#196 の範囲か PM 判断 |
| 線形 sweep と audit_icall の差 (+1〜+46 site) の切り分け | §3 の検算の精度 (結論は不変) | 本 REPORT のみ。#514 で gate 化する際に再検討 |

DEFECTS.md 行案: なし (既存 (icall §4) D1 の再確認)。

## 7. 再現

```sh
source tools/plugins/hostx/env.sh                 # fl-win64 の展開 ($RUNNER_TEMP/fl-win64) と pefile+capstone+numpy の venv
bash tools/plugins/hostx/hostx_e2e.sh             # 全再現 (work/ があれば 7 分 30 秒; --skip-engines で C++ 窓 lift を省略)
bash tools/plugins/hostx/hostx_nega.sh            # NC1〜NC6 (e2e 後に 5 秒)
python3 tools/plugins/hostx/xcheck_icall.py 19091 23676 19220 24155 23918 19244 23674 24161   # 別算法検算
```

| ファイル | 役割 |
|---|---|
| `hostx_e2e.sh` | 前提 work/ 生成 → `static_facts.py` → 閉包 → `batch_lift.sh` → `judge.py` / `expect_state.py` → `icall_audit.py` → `closure_facts.py` → `matrix_check.py` → `rewired_f80.sh` → `engine_sample.sh` |
| `static_facts.py` / `closure_facts.py` | 全 18 モジュールの PE 外形・API・文字列 / 閉包の host 呼出・クラス名・双子と engine の重なり |
| `judge.py` / `expect_state.py` / `matrix_check.py` | 合格必須の判定 / 既知不合格の状態固定 / PLUGIN_MATRIX との突合 |
| `icall_audit.py` / `xcheck_icall.py` | 間接 call 監査 / 線形 sweep の検算 (`f2/xcheck_icall.py` の入力パスのみ変更) |
| `rewired_f80.sh` / `engine_sample.sh` / `engine_window.py` | ReWired の f80 lowering 局所検証 / C++ engine の窓 lift / 窓の range 生成 |
| `mk_blockmap.py` / `env.sh` / `hostx_nega.sh` | blockmap 再構成 / 環境 / ネガティブコントロール |
