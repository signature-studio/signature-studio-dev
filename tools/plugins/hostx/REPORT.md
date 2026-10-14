# tools/plugins/hostx REPORT — PLG-X host 統合 / big3p 12 本の方針決定と lift 前提の実測 (#210)

- 検証起点 commit: **0e7f717** (`210-big3p-policy` の head。origin/main ec79ef5 を取り込んだ 1ab852f の上に、REPORT と `hostx_nega.sh` の期待値を載せた commit)。§2〜§5 の数値は `bash tools/plugins/hostx/hostx_e2e.sh` を 0e7f717 で 1 回実行 (exit 0、1,092 秒) して取得し、`hostx_nega.sh` (`[hostx_nega] OK`) と公式 gate `f2/icall_gate.py` も同じ 0e7f717 で実行。1ab852f の実測 (1,099 秒) は §5 に併記。後続の commit は本 REPORT のみを変える (lift・閉包のコードは不変)。
- 日付: 2026-10-13 / 担当 dir: `tools/plugins/hostx/` のみ (生成物は `tools/plugins/work/` = gitignore)
- 既知類型との関係: **(icall §4) D1 = 間接 call/jmp 脱落**。#514 の復元で IR 側の間接 call は 2,178 site まで回復したが、公式ゲート `f2/icall_gate.py` で 8 閉包中 6 本が未被覆 (§3)。f80 (x87) は `tools/plugins/REPORT.md` §4.3 の既知事象。新規類型なし。
- 範囲: issue #210 の「方針決定」(§1) と、手順 1 (固有閉包 lift → `emcc -c`) の再現 (§2)、間接 call の gate (§3)、C++ engine の窓 lift の到達性 (§4)。**差分試験 (bit-exact) と Render test .flp は未達** (§6)。PR は `Refs #210`、`Closes` は付けない。

## 0. 結論 (先出し)

1. **12 本の分類**: lift する **6 本** (Wrapper×2 / Patcher×2 / MIDI Out / Video Player)、当初の区分は lift しない **2 本** (Razer Chroma / ReWired)、ユーザ判断 **4 本** (ZGE / FL Mobile×3)。2026-10-14 に PM が確定した (`docs/DECISIONS.md` D22): Razer・ReWired (#558)・FL Mobile×3 (#560) は lift しない、ZGE (#559) は保留 (#29 待ち)。
2. **「big3p 12 本」は呼称が不正確**: `PLUGIN_MATRIX` の scope は host 8 + big3p 4 (ZGE と FL Mobile×3)。推定 81 人日の内訳は host 21 + big3p 60 (matrix の Tier 規則 est_days の合計; 根拠の薄い機械推定)。同じ matrix の host の `Control Surface` は #205 (PLG-F8)、big3p の `DirectWave` / `FLEX` は `batch_plan.md` §7 の PLG-G4 側にあり、12 本には含まれない。
3. **lift の前提は再現した**: 合格必須 7 閉包 (Wrapper×2 / Patcher×2 / MIDI Out / Razer Chroma / Video Player) は RetDec + pass 鎖で **7/7 が `lift_rc=0`・`emcc -c` rc=0・未実装 helper 0**。ReWired は f80 2 関数で `emcc -c` が失敗 (p0c の f80→f64 lowering を当てれば通る)。ZGE 殻は閉包が 0 件で lift 不能 (未計測)。
4. **間接 call は #514 の復元で IR に載るようになったが、gate は未達**: 8 閉包の機械語側の間接 call site は 2,181 (audit) / 2,297 (線形 sweep)、IR 側の `@__icall_dispatch` は 2,178。`f2/icall_gate.py` (#514 の回帰ゲート) で **8 閉包中 6 本 FAIL**。未被覆 site は **120** (F1)、site 不明の dispatch は 1 (F3, 23674)。MIDI Out (69) と Razer Chroma (23) は PASS。
5. **差分試験の出口条件は未達**。理由は 2 つ: (a) 上記の未被覆 120 site (#514 で未解決)、(b) 共有 framework wasm / Host shim とのリンク未達 (#195〜#197)。`emcc -c` 通過は正しさの証拠にならない。

## 1. 方針決定 (12 本の分類)

区分: **A = lift する** / **B = lift しない (D22 で確定)** / **C = 当初のユーザ判断 (D22 で確定: FL Mobile×3 は lift しない、ZGE は保留 (#29 待ち))**。工数は matrix の Tier 規則 est_days (機械推定)。demo = demo .flp の出現数、preset = preset 数 (`PLUGIN_MATRIX.json` の `usage`)。

| plugin | block | Tier / 工数 | 区分 | 根拠 | 依存・次 |
|---|--:|---|---|---|---|
| Fruity Wrapper (Effects) | 19091 | T2 / 4 d | **A** | VST2 ホスト実体。ロード経路の解析と「wasm 同梱プラグイン表」の設計・PoC は #24 (closed) で完了。閉包 171 関数 / 84,695 B が lift・`emcc -c` 通過 (§2)。#46 (E2E-6: OTT を Wrapper 経由で発音) の前提。demo 2 | #514 (icall; 未被覆 10 site)・#195〜#197 (P0a/b/c)。host ID 54 が `hs_ids` に未登録 (shim 追加) |
| Fruity Wrapper (Generators) | 23676 | T2 / 4 d | **A** | 同上 (閉包 177 関数 / 84,891 B)。Effects 版との閉包ハッシュ重なり: 共通 162 / E のみ 9 / G のみ 15 distinct (§2) = 2 本目は差分のみ | 同上 (未被覆 10 site) |
| Patcher (Effects) | 19220 | T2 / 4 d | **A** | 内部にプラグインホストを持つ (RTTI にプラグイン/ホスト系クラス名 135 件、`TFruityPlugHost` など)。閉包 516 関数 / 173,324 B が通過。**Render test .flp を持つ唯一の本**で出口条件が最も具体的。demo 12・preset 137 | Wrapper の結線 (#33 PLG-E5 は Patcher を含む)・#514 (未被覆 45 site) |
| Patcher (Generators) | 24155 | T2 / 4 d | **A** | 閉包 513 関数 / 171,025 B が通過。E 版との重なり: 共通 466 / E のみ 48 / G のみ 45 distinct。demo 12・preset 172 | 同上・#514 (未被覆 44 site) |
| MIDI Out | 23918 | T0 / 0.5 d | **A** | 12 本中で最小の閉包 (30 関数 / 9,086 B) が通過。icall_gate は PASS (69 site 全被覆)。殻に MIDI 出力固有の import は無く (全殻共通の winmm 4 関数のみ; §2)、出力は host 側 vtable 経由。ブラウザでは Web MIDI に接続する想定 (shim 側)。demo 3・preset 41 | #196 (Web MIDI 出力 shim は P0b Host shim の vtable 送出先として扱う; §6) |
| Fruity Video Player | 23674 | T1 / 1.5 d | **A (後順位)** | 閉包 63 関数 / 19,496 B が通過。`ILVideo_*` の文字列 21 種を持ち (復号は libILVideo 経由)、FFmpeg の wasm 再ビルド + libILVideo wrapper は #149 (closed)。描画は #29 (PLG-E2)。demo 0・preset 1 で優先度は低い | #29 の描画経路・#514 (未被覆 10 site + F3 1 件) |
| Razer Chroma | 19244 | T1 / 1.5 d | **B** | `RzChromaSDK64.dll` を動的ロードして Razer 周辺機器の LED を制御する (殻の文字列 23 hit)。音声処理なし・host ID 36 を 1 回呼ぶだけ。ブラウザから周辺機器に届かない。閉包 32 関数は通過するため**技術障害ではなく方針の問題**。demo 0・preset 0 | **#558** |
| ReWired | 24161 | T1 / 1.5 d | **B** | ReWire は別プロセスの ReWire ホスト/デバイスとの音声・MIDI ルーティングで、ブラウザに相手方がいない (仕様上の推論。殻内に `ReWire.dll` / `ReWireDebug.dll` の文字列)。技術的にも `emcc -c` 失敗 (f80 2 関数; §2)。icall の未被覆は 1 site。demo 0・preset 5 | **#558** |
| ZGameEditor Visualizer | 19304 (+19299/19300/19303/19305/19306) | T3 / 15 d | **C** | 殻 7.6 MB は現行鎖で閉包 0 件 (lift 未計測)。NDI 27 MB (ネットワーク; D3 対象外)・Spout (Windows 共有テクスチャ)・DMX/Hue/OSC 出力は切り落とす前提でも、OpenGL 描画 (`opengl32`) の WebGL 化 (#29) が未達。demo 9・preset 230 でユーザに見える | **#559** |
| FL Studio Mobile Rack FX | 18976 | T3 / 15 d | **C** | MSVC C++ engine 8.2 MB・16,261 関数。窓 lift は 3 窓中 1 窓が `emcc -c` 失敗 (§4)。sqlite / FLAC / élastique / DirectWave を内包し、再配布条件は #163 待ち。demo 0・preset 31 | **#560** |
| FL Studio Mobile Rack | 23605 | T3 / 15 d | **C** | Rack FX と関数ハッシュの 90.8% が共通 (§4) = 実質同一エンジン。demo 0・preset 0 | **#560** |
| FL Studio Mobile | 22444 | T3 / 15 d | **C** | engine 12.1 MB・24,237 関数 + `FLMManagedBridge_x64.dll` (`mscoree.dll` を import = .NET CLR 経由と推定; wasm に載らない)・`ws2_32` 20 import (FL Cloud 等; D3 対象外)。demo 0・preset 0 | **#560** |

- **機能単位で切り落とすもの** (`docs/DECISIONS.md` D3 外部通信機能は対象外): Wrapper / Patcher の FL Cloud 系 (RTTI の `TCloudPluginsLicenseEngine` / `TFLCloudPluginHost`)、32bit プラグイン用 `ilbridge.exe` bridged 経路 (#24 の設計どおり wasm では instance 分離で代替)、ZGE の NDI、FL Mobile の winsock。
- **A の合計工数**: matrix の est_days で 4+4+4+4+0.5+1.5 = **18 人日**。ただし §3 のとおり icall gate が未達のため、実作業量の見積りは #514 完了後に再推定する。
- 区分 B/C の 6 本は lift しない (ZGE は #29 待ちの保留)。FLP 上の未対応プラグインは「state を保持して素通し」にする (`docs/DECISIONS.md` D22)。

## 2. 手順 1: 固有閉包 lift の結果 (`work/batch/status.csv`)

閉包 = DSP エントリ (vtable override) から `call/jmp rel32` で到達する固有関数 (framework 共通 13 DLL 以上は除外; 定義は `lift/plugin_closure.py`)。`defines` = `p.final.ll` の `^define` 数、`seconds` = `batch_lift` の `status.csv` 記録秒 (1 閉包)。`declares_unimpl` = `p.simd.log` の未実装 helper 数。

| block | plugin | 閉包関数 | 閉包 x86 B | defines | lift_rc | declares_unimpl | f80 関数 | emcc -c rc | seconds |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 19091 | Wrapper (E) | 171 | 84,695 | 173 | 0 | 0 | 0 | 0 | 23 |
| 23676 | Wrapper (G) | 177 | 84,891 | 179 | 0 | 0 | 0 | 0 | 24 |
| 19220 | Patcher (E) | 516 | 173,324 | 522 | 0 | 0 | 0 | 0 | 52 |
| 24155 | Patcher (G) | 513 | 171,025 | 519 | 0 | 0 | 0 | 0 | 52 |
| 23918 | MIDI Out | 30 | 9,086 | 30 | 0 | 0 | 0 | 0 | 5 |
| 19244 | Razer Chroma | 32 | 9,729 | 32 | 0 | 0 | 0 | 0 | 6 |
| 23674 | Video Player | 63 | 19,496 | 63 | 0 | 0 | 0 | 0 | 8 |
| 24161 | ReWired | 102 | 18,488 | 102 | 0 | 0 | **2** | **1** | 8 |
| 19304 | ZGE 殻 | 0 | 0 | 0 | **1** | - | - | **1** | 3 |

- 合格必須 7 本の判定は `judge.py` (`lift_rc` / `declares_unimpl` / `f80_funcs` / `emcc_c_rc` がすべて 0) で **7/7 合格・bad=0**。`declares_unimpl` は head で全 7 本 0 (旧 a9fc9e4 では Wrapper 2 本に `rep_stosb_memset` 1 件)。許可名 `rep_stosb_memset` は現 head では不要だが、判定スクリプトの引数として残す。
- 既知不合格 2 本の状態固定 (`expect_state.py`): ReWired は f80=2・emcc rc=1、ZGE 殻は `lift_rc=1` のまま = **期待どおり**。合格に変わると exit 1 になり、本 §1 の区分の見直しが要る。
- **ReWired の f80**: `function_6f1ff0` / `function_6f5f30` の 2 関数が `x86_fp80` を含み、`emcc -c` は `do not know how to soften fp_extend` / `no libcall available for fadd with type f80` で失敗する。`p0c/f80_lower.py --no-rint` を当てると **x86_fp80 行 0・`emcc -c` rc 0** (到達性のみ。lowering 後の数値の正しさは未検証)。
- **ZGE 殻**: `plugin_closure.py` が vtable 入口を 1 件も見つけず (`entries` が空)、`lift_ranges.sh` が空の range で `invalid range` を出して終わる。ZGE 殻は標準の Fruity 入口を持たない構造の可能性があるが、原因は未切り分け (§6)。
- **matrix との突合** (`matrix_check.py`): `PLUGIN_MATRIX.json` の `lift` 欄と **48/48 項目が一致** (ZGE 殻は matrix に lift 欄がなく比較対象外 1 本)。
- **host 呼出の規模** (`closure_facts.py`、閉包 ranges 内の host vtable 呼出 site 数): Wrapper 54/61 (E/G; うち ID が動的な site 22)、Patcher 36/35 (動的 8)、ReWired 23 (動的 3)、MIDI Out 29 (slot 0x48 が 23)、Video Player 22 (動的 5)、Razer 1。Wrapper の ID 54、Patcher の ID 96 は `framework/hostshim/hs_ids.json` に未登録。
- **import の外形** (`static_facts.py`): 8 本の Delphi 殻は kernel32 / user32 / gdi32 系を除くと winmm 4 関数のみを共通に import し、MIDI Out / Razer / ReWired に固有の外部 DLL import は無い (Razer は `LoadLibrary` で `RzChromaSDK64.dll` を動的ロード)。ZGE 殻だけが `opengl32` / `wsock32` / `mpr` を import する。全 18 モジュールの表は `work/hostx/static.md` (再生成物)。

## 3. 間接 call 監査 (公式 gate: `f2/icall_gate.py` #514)

定義 (3 列):
- **機械語側の site**: 閉包 ranges の非 IAT 間接 call。`hostx/icall_audit.py` (`tools/icall/audit_icall.py`、recursive descent) と `hostx/xcheck_icall.py` (capstone 線形 sweep) の 2 算法。
- **IR 側の site**: lift 後 IR の `call void @__icall_dispatch(i64 <site VA>)` (#514 の復元 pass が元 site VA 付きで戻したもの) と、callee が `@name` でない call (RetDec が自力で残した間接 call)。
- **gate (正本)**: `f2/icall_gate.py` が、線形 sweep の site VA 集合を IR dispatch の site VA 集合と突合する。F1 = 未被覆 (機械語 site のうち IR に無いもの)、F3 = site 不明の dispatch。

| block | plugin | 静的 site (audit) | 線形 sweep | IR dispatch 呼出し | IR native 間接 call (`@` なし) | F1 未被覆 | F3 site 不明 | gate 判定 |
|--:|---|--:|--:|--:|--:|--:|--:|---|
| 19091 | Wrapper (E) | 353 | 361 | 351 | 0 | 10 | 0 | FAIL |
| 23676 | Wrapper (G) | 348 | 356 | 346 | 0 | 10 | 0 | FAIL |
| 19220 | Patcher (E) | 596 | 642 | 597 | 0 | 45 | 0 | FAIL |
| 24155 | Patcher (G) | 583 | 628 | 584 | 0 | 44 | 0 | FAIL |
| 23918 | MIDI Out | 69 | 69 | 69 | 0 | 0 | 0 | PASS |
| 19244 | Razer Chroma | 23 | 23 | 23 | 0 | 0 | 0 | PASS |
| 23674 | Video Player | 112 | 120 | 111 | 0 | 10 | 1 | FAIL |
| 24161 | ReWired | 97 | 98 | 97 | 0 | 1 | 0 | FAIL |
| **合計** | | **2,181** | **2,297** | **2,178** | **0** | **120** | **1** | |

- gate の出力 (全 8 閉包の表と F1/F2/F3 の判定文) は `tools/plugins/work/icall_gate.md` に保存 (gitignore)。判定の文言: 「F1 missing=10; F2 ir_total=351 + waived=0 < machine=361」など。`waived` は 0 (RetDec の到達不能除去による除外は無い)。
- IR dispatch の異 site 数は 23674 のみ 110 (呼出し 111)。同じ site VA に dispatch が 2 回立つ 1 件があり、F3 の 1 件と同じ閉包。
- 線形 sweep と audit の差は +116 site (19091 +8 / 23676 +8 / 19220 +46 / 24155 +45 / 23674 +8 / 24161 +1; MIDI Out と Razer は 0)。線形 sweep は関数範囲内のインライン data を命令として読むため上振れすると推定するが、差分 site の切り分けは未実施。gate は線形 sweep を機械語側の正本として使う。
- 旧版の「IR の間接 call 0」「2,181 site 脱落」は #514 の復元前の値で、head では成り立たない。`hostx_nega.sh` の NC6 の grep 側は `@` を含む dispatch 行を数えないため、復元後も判定の識別力を保つ (§5)。

## 4. FL Studio Mobile の C++ engine: 窓 lift の到達性 (`hostx/engine_sample.sh`)

全関数ではなく `.pdata` 関数をアドレス順に並べ、先頭 / 1/3 / 2/3 位置から各 300 関数の窓を RetDec + pass 鎖で lift → `emcc -c`。`unimpl` = 窓の `p.simd.log` が報告する未実装 helper 数。

| engine | 窓 | 開始 index | 窓の x86 B | lift_rc | defines | f80 関数 | unimpl | emcc -c rc | lift 秒 | 最初の error |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|---|
| Rack FX 18976 | w0 | 0 | 204,868 | 0 | 415 | 0 | 102 | 0 | 67 | |
| Rack FX 18976 | w1 | 5,420 | 69,333 | 0 | 344 | 0 | 0 | 0 | 26 | |
| Rack FX 18976 | w2 | 10,840 | 98,779 | 0 | 315 | 0 | 1 | **1** | 27 | `use of undefined value '%104'` |
| Mobile 22444 | w0 | 0 | 204,868 | 0 | 415 | 0 | 102 | 0 | 69 | |
| Mobile 22444 | w1 | 8,079 | 76,217 | 0 | 353 | 0 | 0 | 0 | 29 | |
| Mobile 22444 | w2 | 16,158 | 88,498 | 0 | 323 | 0 | 2 | **1** | 26 | `use of undefined value '%54'` |

- 6 窓中 **2 窓が `emcc -c` 失敗** (LLVM IR の SSA 整合の崩れ)。w0 は両 engine で同一 (同じ 204,868 B・415 defines・unimpl 102) で、通っても未実装 helper 102 件を含む。C++ engine を現行鎖でそのまま lift する経路は未成立で、同種の問題は #527 (PLG-F5-2) で追跡中。FLEngine と同じ x64c 経路 (`tools/flelift`) の適用可否は未測定 (#560 の選択肢 B)。
- **エンジンの重なり** (`closure_facts.py`: `.pdata` 全関数の位置非依存ハッシュ; 分母は a の関数数、割合は a の関数のうち b に同ハッシュがあるもの): Rack FX → Rack **14,759 / 16,261 = 90.8%** (バイト加重 67.2%)、Rack → Rack FX 14,759 / 16,265 = 90.7%、Rack FX → Mobile 14,241 / 16,261 = 87.6% (バイト加重 59.5%)、Mobile → Rack FX 17,252 / 24,237 = 71.2% (バイト加重 43.6%)。Rack FX と Rack は実質同一エンジン。

## 5. 検算とネガティブコントロール (`bash tools/plugins/hostx/hostx_nega.sh`)

| 検査 | 壊し方 | 結果 (HEAD 0e7f717) |
|---|---|---|
| NC1 `emcc -c` rc | MIDI Out の `p.final.ll` の 1 関数から `ret` を除去 | 無改変 rc 0 → 壊した IR rc 1 |
| NC2 閉包 → define 数 | 閉包 29 range の末尾 1 本を落として再 lift | defines 30 → 28、落とした `function_701d90` は 1 → 0 |
| NC3 `judge.py` の識別力 | 実測 (declares_unimpl=0) / declares_unimpl=1 の合成行 (許可名なし・許可名違い) / `emcc_c_rc=1` の合成行 / 行欠落 | 実測+許可名 rc 0 / 実測・許可名なし rc 0 (期待どおり: 未実装 0) / 合成 declares=1 で rc 1 / 1 / emcc_c_rc=1 合成 rc 1 / 行欠落 rc 1 |
| NC4 `expect_state.py` | ReWired を合格値 (f80=0, emcc rc=0) にした合成 CSV | 実測 rc 0 → 合成 rc 1 |
| NC5 `matrix_check.py` | Patcher (E) の `closure_bytes` を +1 した合成 facts | 実測 rc 0 → 合成 rc 1 (MISMATCH 1 行) |
| NC6 間接 call 監査の識別力 | MIDI Out の先頭関数に間接 call を 1 本注入 | `audit_icall` の IR 間接 call 基準 69 → 注入 70 (差分 +1)、grep 側 (`@` なし call 行) 0 → 1 |

- 本 commit で変えたのは NC3 と NC6 の期待値のみ (旧: 「許可名なし → rc 1」「IR 間接 call 0 → 1」は head の実測 (未実装 0・基準 69) と合わない)。NC3 の合成行は、実データに名前の根拠が無いため許可名に関係なく FAIL する。
- `[hostx_nega] OK` で exit 0。
- 環境: GitHub Actions runner (`nproc`=4)。

### 所要時間 (`hostx_e2e.sh`、HEAD 0e7f717、n=1)

- **wall 1,092 秒 (18 分 12 秒) を n=1 で実測** (exit 0)。並列 1。fl-win64 展開済みの `$RUNNER_TEMP/fl-win64` を使用 (展開・venv は既存)。
- load average: e2e 開始直前の `uptime` は 0.78 / 0.43 / 0.17、終了直後の `/proc/loadavg` は 1.00 / 2.82 / 4.26 (実行中の推移は未サンプル)。
- 先行 HEAD 1ab852f での実測: wall 1,099 秒 (18 分 19 秒, n=1、fl-win64 展開と venv 作成を含む)。lift 経路は両 HEAD で同一 (差分は REPORT と `hostx_nega.sh` のみ)。
- n≥3 のレンジは取っていない (1 回 18 分のため、本 run の上限 58 分に 3 回は収まらない)。単発値であることを明記する。旧 REPORT の「7 分 29.6 秒」は本 HEAD で測っていないため削除した。

## 6. 範囲外・未解決

検証範囲: 手順 1 の再現、間接 call の gate (#514 の回帰ゲート) の結果、C++ engine の窓 lift の到達性。**native との出力比較は 1 件も実施していない**。Render test .flp (Patcher の 2 本) による E2E も未実施。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| icall 復元の未被覆 120 site (F1: 19091 10 / 23676 10 / 19220 45 / 24155 44 / 23674 10 / 24161 1) と site 不明 dispatch 1 件 (F3: 23674) | 8 閉包中 6 本が `icall_gate.py` FAIL。差分試験の前提が未達 | 既存 **#514** にコメント (本 PR の gate 出力を添付) |
| 差分試験 (native ms_abi vs wasm) と共有 framework wasm / Host shim とのリンク | 出口条件 | 既存 #195 (P0a) / #196 (P0b) / #197 (P0c) の完了待ち。本 issue #210 に残す |
| Razer Chroma・ReWired の対象外確定 | 区分 B | **#558** (D22 で確定・close) |
| ZGE の扱い。殻の閉包が 0 件になる原因 (標準入口を持たない構造か) は未切り分け | 区分 C | **#559** (D22 で保留と確定。#29 に blocked_by) |
| FL Mobile×3 の扱い。C++ engine の窓 lift が 6 窓中 2 窓で失敗 | 区分 C | **#560** (D22 で対象外と確定・close)・技術面は既存 #527 |
| Wrapper の host ID 54 / Patcher の host ID 96 が `hs_ids.json` に未登録 | Wrapper / Patcher を framework とリンクする段 | 既存 #196 (P0b) にコメント |
| MIDI Out の出力先 (Web MIDI) の shim | MIDI Out の動作 | 既存 **#196** (P0b Host shim) にコメント。Host shim の vtable 送出先として Web MIDI 出力を追加する範囲 |
| 線形 sweep と audit_icall の差 (+116 site) の切り分け | §3 の機械語側の精度 (gate は線形 sweep を正本とする) | 既存 **#514** にコメント (gate 化の一部として扱う) |

DEFECTS.md 行案: なし (既存 (icall §4) D1 の再確認)。

## 7. 再現

```sh
source tools/plugins/hostx/env.sh                 # fl-win64 の展開 ($RUNNER_TEMP/fl-win64) と pefile+capstone+numpy の venv
bash tools/plugins/hostx/hostx_e2e.sh             # 全再現 (--skip-engines で C++ 窓 lift を省略)
bash tools/plugins/hostx/hostx_nega.sh            # NC1〜NC6 (e2e 後に実行)
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/plugins/f2/icall_gate.py 19091 23676 19220 24155 23918 19244 23674 24161   # 公式 gate (pefile が要る venv の python)
```

| ファイル | 役割 |
|---|---|
| `hostx_e2e.sh` | 前提 work/ 生成 → `static_facts.py` → 閉包 → `batch_lift.sh` → `judge.py` / `expect_state.py` → `icall_audit.py` → `xcheck_icall.py` → `closure_facts.py` → `matrix_check.py` → ReWired f80 → FL Mobile engine の窓 lift (参考) |
| `static_facts.py` / `closure_facts.py` | 全 18 モジュールの PE 外形・API・文字列 / 閉包の host 呼出・クラス名・双子と engine の重なり |
| `judge.py` / `expect_state.py` / `matrix_check.py` | 合格必須の判定 / 既知不合格の状態固定 / PLUGIN_MATRIX との突合 |
| `icall_audit.py` / `xcheck_icall.py` | 間接 call 監査 (audit) / 線形 sweep の検算 |
| `rewired_f80.sh` / `engine_sample.sh` / `engine_window.py` | ReWired の f80 lowering 局所検証 / C++ engine の窓 lift / 窓の range 生成 |
| `mk_blockmap.py` / `env.sh` / `hostx_nega.sh` | blockmap 再構成 / 環境 / ネガティブコントロール |
