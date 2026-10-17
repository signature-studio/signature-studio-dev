# tools/audio/asio — IASIO COM アダプタ (CAB-97 [AU-1]) + IASIO COM 経由 120s soak (CAB-270 [AU-1b]) REPORT

既知欠陥類型 (DEFECTS.md) との関係: **該当なし** (本 ticket は lift/逆アセ/IR pass ではなく wasm shim の e2e ハーネス追加。D15 メモリ間接 call / D9 (DEFECTS.md) jump table 等は発生経路に無い)。

## 0. 結論

**完了。** FLEngine が `CoCreateInstance(IID_IASIO)` で取得できる ASIO ドライバ面 (IASIO vtable 24 スロット = IUnknown 3 + IASIO 21) を実装し、実体を検収済み `flasio_*` (tools/audio/src/flasio.c) へ委譲した。1 コマンド検収 `bash tools/audio/asio/e2e.sh` (exit 0) = **node 静的検証 126/126 PASS + headless Chrome 4/4 PASS** (3 シナリオ + **COM 経由 120s soak**)。既存 tools/audio e2e は **22 シナリオ系で 21/22** (唯一 `asio_sine_b256_96k` = 既知 AU-11 の load 依存 FAIL。本チケットの変更 0 行の clean HEAD 731e32e でも同一結果、§4)。親 e2e への組込みは行っていない (本 e2e が単独で完結、§6)。

**CAB-270 (COM 経由 120s soak)**: `com_soak120_b256` を追加。既定 120 秒で **underrun 0 / silence 0 / ramp 0 mismatch / bufferSwitchTimeInfo bad 0 / COM 面 (sellog・参照カウント) 一致**を 9 回連続で実測 (§3-2)。`--quick` では soak を実行しない (親 e2e 規約)、`--soak N` で秒数変更可。

> AU-17 (#1102) の COM 経由 30 分ソーク・p+1 照合の 24bit 修正の実測は `REPORT_APPENDIX_1102.md` に分割移動 (250 行上限)。
> AU-19 (#1358) のキャプチャ分割照合 (ring 16 MiB・ソーク PASS 30 分 28 秒) は `REPORT_APPENDIX_1358.md`。

## 1. 前回中断 (insufficient_credits) の残骸精査 → **引継ぎ採用**

`tools/audio/asio/` に未追跡 11 ファイル (計 1,565 行 / work/ は空ディレクトリのみ = **ビルド未通過の中断点**)。精査の結果、設計・実装・テスト・ハーネスはほぼ完成形だったため**クリーン再実行ではなく引継ぎ**を選択した。未追跡ファイル一覧: `iasio.h/.c`, `iasio_vreg.c`, `iasio_shimx.c`, `test/com_test.c`, `harness/{index_com.html,com_page.mjs,run_com.mjs}`, `build.sh`, `e2e.sh`, `.gitignore`。コミットは 0 (HEAD = 1c4b7c7 時点で全て未追跡)。

引継ぎ後に本 session で修復した欠陥 (すべて再現ビルドで検出):

| # | ファイル | 欠陥 | 修復 |
|---|---|---|---|
| 1 | build.sh | `com_test.c` が `shimx.h` を include するのに `-I tools/shimx/src` が無くコンパイル不能 | include 追加 |
| 2 | test/com_test.c | `flasio_stats_t` に存在しない `cb_sum_us_lo/fill_sum_lo/fill_samples` を参照 (6 エラー) | 実在 field `cb_avg_us/avg_fill` へ |
| 3 | iasio.h | `iasio_shimx_unregister` の宣言欠落 (暗黙宣言エラー) | 宣言追加 |
| 4 | test/com_test.c | `CoGetClassObject` に IID_IASIO を要求 → クラスファクトリは IID_IUnknown/IID_IClassFactory のみ受付 (COM 標準) で `cf=NULL` のまま生 deref → **SAFE_HEAP で OOB / 非アサート時 "function signature mismatch" で全シナリオ起動失敗** | IID_IClassFactory 要求へ変更 + IID_IASIO は `E_NOINTERFACE` を明示検証 + null guard |
| 5 | test/com_test.c | QI 成功時の AddRef を Release せず参照カウント収支が崩れ `addref_2/release_1/release_to_0/alive_back_to_0` の 4 項目が期待値不一致 | QI 参照を都度 Release (COM 規約どおり) |
| 6 | iasio_vreg.c | `enum_sub` の重複排除が「同一子のより深いパス」しか検出せず、同一子が別値名 (既定値 + clsid) で複数登録されると二重計上 → `vreg_enum_asio_idx1_empty` / `enum_drivers_n` 不一致 | 子名先頭一致 + (`\\` 続き or 終端) で重複判定 |
| 7 | test/com_test.c | `run_com` 出力 JSON の閉じ括弧 1 個不足 (com オブジェクト分) → Chrome 側 `JSON.parse` 全滅 ("bad result json") | `Q("]}}")` (sellog/com/外側の 3 段閉じ) |
| 8 | iasio.c | 未使用関数 (`accum`, `hexv`) の警告残骸 | 削除 |
| 9 | build.sh | shimx 既成オブジェクト (obj_MT) とソース直ビルドの切り替えが不可 | `IASIO_FORCE_SHIMX_SRC=1` エスケープハッチ追加 (既定は obj_MT 参照 = shimx 側作業ツリーに影響されない) |

## 2. 実装 (`tools/audio/asio/`)

- **iasio.c (366 行)**: COM オブジェクト本体。vtable は 24 スロット × 8B (win64 形状, ILWASAPI2ASIO 0x1800657e0 実測と同数・標準 IASIO 順) を `constructor` で実行時初期化 (wasm では関数ポインタの静的初期化が定数化しないため)。IUnknown (QI は IID_IUnknown/IID_IASIO 受付, AddRef/Release 0 で自己解放) + IClassFactory (集約非対応 = `CLASS_E_NOAGGREGATION`)。19 メソッドは `flasio_*` へ委譲、FL 未使用の `getErrorMessage`/`future` もスロット互換で実装 (実測: FL は呼ばない — INVENTORY §2)。`CreateBuffers` のみ win64 形状 (ASIOBufferInfo64 24B / ASIOCallbacks64 32B) を受けて C ネイティブ形状へ変換委譲し、バッファポインタを 8B スロットで返す。CLSID 解決は `iasio_co_create_instance/co_get_class_object` (shimx ole.c の REGDB_E_CLASSNOTREG スタブからのフォワード入口 1 箇所を想定)。
- **iasio_vreg.c (126 行)**: 内蔵 mini レジストリ (PoC/単体テスト用)。FLEngine の実フロー (`RegOpenKeyEx(HKLM,"software\asio")` → `RegEnumKeyEx` → 値 `clsid` → CLSIDFromString → CoCreateInstance) をバックエンドインターフェースで抽象化。
- **iasio_shimx.c (107 行)**: tools/shimx の実レジストリ (lifted FLEngine が advapi32 Reg* で読むものと同一実体) へ `"FL Studio ASIO" = {188135E1-7171-3434-854F-01A3C71F3DF9}` を登録し、Reg* をバックエンドに取る結合 (shimx は読取専用参照リンク — 改変 0 行)。
- **test/com_test.c (515 行)**: mode=check (node, AudioContext 不使用 — fla_open に到達しない静的検証 126 項目) と mode=ramp|sine (headless Chrome + FlAudioShim — COM 取得→CreateBuffers→bufferSwitchTimeInfo 連鎖→Stop→Release の全経路)。
- **harness/**: `run_com.mjs` (CAB-270 以降は **4 シナリオ** = 短 3 + 120s soak。tools/audio/harness/chrome.mjs 流用) + `com_page.mjs` (page.mjs 流儀, ramp/sine bit 突合) + `index_com.html`。

### 実測値の取込 (INVENTORY §2-§3 / CAB-9 検収 03dbd1a)

- asioMessage 応答表 (host モック): selector 7 (SupportsTimeInfo)→**1**, 6 (LatenciesChanged)→内部コマンド 0x17 発行後 1, 8 (TimeCode)→0, 3/4/5→dialog (0x425210, id 0x55f) 後 1, 2 (EngineVersion)→2, 1 (Supported)→value∈[2..8] で 1。
- ILWASAPI2ASIO プロファイル: getChannels **2in/2out**, getChannelInfo type **0x13 (ASIOSTFloat32LSB)** / group 0 / "Out %i", getBufferSize **min 0x100 / max 0x1000 / gran 0** (作成後 pref = B), canSampleRate {22050,44100,48000,96000,192000}, getClockSources 1 件 **"Internal"**, outputReady **ASE_NotPresent (-1000)**, future 既定 -998。
- ASIOCallbacks 4 関数 (bufferSwitch 0xc57420 / sampleRateDidChange 0xc576b0 / asioMessage 0xc576c0 / bufferSwitchTimeInfo 0xc56ae0 = 本体) を 8B スロットで受渡し。ASIOTime は 148B (0x94) 実測どおり static_assert で保証。

## 3. 検収実測 (`bash tools/audio/asio/e2e.sh`, exit 0)

### node check (COM 面静的検証) — **126/126 PASS** (fail 0)
win64 レイアウト static_assert (BufferInfo64=24B/buffers@8, Callbacks64=32B, ASIOTime=148B, vtable=192B) / asioMessage 応答表 **15 項目** (selector 呼出 13 + カウンタ照合 2) / IUnknown+IClassFactory+CLSID 解決 (正常系・失敗系) / slot index 監査 (生 slot 呼出 vs typed 呼出の一致 6 項目) / 19 メソッド + getErrorMessage/future の戻り値照合 / vreg 登録→FLEngine フロー / **shimx 実レジストリ経由** (Reg* で software\asio 列挙→clsid→CoCreateInstance→init) / 8B スロット変換の往復。

### headless Chrome (FLEngine 呼出を模した全経路) — **4/4 PASS** (既定実行 = 3 短シナリオ + 120s soak。負荷依存は §3-1・§3-2)
| シナリオ | 実測 |
|---|---|
| com_ramp_b256_d2 | ramp 不一致 **0 / 240,640〜241,152 frame** (bit-exact), underruns **0** silence 0, bufferSwitchTimeInfo **942〜947 calls bad=0** (samplePosition 単調 + sr 一致), cb_max **64〜494µs** (負荷依存), QI 1 / alive 0 (Release で自己解放), sellog `[[1,2],[2,0],[1,7],[7,0]]` (= flasio_create_buffers ハンドシェイクの実測問合せ順) |
| com_ramp_b1024_d2 | ramp **0/240,640〜241,664**, underruns **0**, cb_max **15〜6,260µs** (負荷依存), T=3072 (64.0ms) |
| com_sine_b256_d2 | sine maxErr **1.49e-8** (< 1e-5 基準), zeroRuns 0, underruns **0**, rms 0.3536 (= 0.5/√2 理論値) |
| com_soak120_b256 (CAB-270) | **§3-2 参照** (9/9 PASS) |

全シナリオで `getChannels 2/2, getBufferSize 0x100/0x1000/gran 0 (作成後 pref=B), type 0x13, lat_out>0` を確認。`output_ready = -1000 (ASE_NotPresent)` も実測一致。

#### 3-1. 短シナリオの負荷依存 (規則 38・41)
以下は **soak 追加前** (3 シナリオ構成) の記録。`e2e.sh` を計 **7 回** 実行 (各 **20〜21 秒**・実測, load average 1/5/15 分 = 2.08〜17.2 / 3.28〜11.9 / 3.47〜10.32):
**6 回は 3/3 PASS**。残り 1 回は `com_sine_b256_d2` が **underruns=1 / silence=512f / maxErr=8.21e-1** で FAIL
(load 1分 16.24 の高負荷時。burst 観測値が伸びた際の既知モード)。失敗以降の 6 回 (load 1分 2.08 含む) は
全て underruns=0 / maxErr=1.49e-8 で 3/3 PASS。**したがって「短シナリオ 3/3」は単発値ではなく負荷依存であり、
低負荷時 (load 1分 2.08) に再現する。**
ネガティブコントロール: 上記 1 回の実 FAIL 出力 (`underruns=1 silence=512`) は run_com.mjs の判定が空振りでない
ことの実証。soak の判定 (§3-2) については §7-2 で別途 3 経路の ablation を実施。

#### 3-2. COM 経由 120s soak (CAB-270) — **9/9 実行で PASS**
定義 (規則 36): 「9 回」= `bash tools/audio/asio/e2e.sh` (既定 = soak あり) の実行回数。1 実行 = 3 短シナリオ + 120s soak。
所要 (e2e 1 本の wall time): **実測 139 / 139 / 140 / 141 / 142 秒** (5 回の計測値。内訳: node check + emcc build 約 18 秒 + Chrome 4 シナリオ約 121 秒)。
load average (計測の 1 分値, 16 コア共有ホスト): 開始 2.36〜3.36 / 終了 2.02〜5.32。

| 実行 | ramp (bit-exact) | underruns / silence | bufferSwitchTimeInfo | cb_count | cb_max | burst→T |
|---|---|---|---|---|---|---|
| 1 | **0 / 5,763,584 f** | **0 / 0** | 22,517 calls bad=0 | 22,512 | 44 µs | 512→1024 (21.3ms) |
| 2 | **0 / 5,760,000 f** | **0 / 0** | 22,505 calls bad=0 | 22,498 | 75 µs | 1024→1536 (32.0ms) |
| 3 | **0 / 5,763,584 f** | **0 / 0** | 22,519 calls bad=0 | 22,512 | 195 µs | 512→1536 (32.0ms) |
| 4 | **0 / 5,763,584 f** | **0 / 0** | 22,519 calls bad=0 | 22,512 | 69 µs | 512→1536 (32.0ms) |
| 5 | **0 / 5,758,464 f** | **0 / 0** | 22,499 calls bad=0 | 22,492 | 419 µs | 1024→1536 (32.0ms) |
| 6 | **0 / 5,762,048 f** | **0 / 0** | 22,513 calls bad=0 | 22,506 | 104 µs | 1024→1536 (32.0ms) |
| 7 | **0 / 5,762,048 f** | **0 / 0** | 22,513 calls bad=0 | 22,506 | 620 µs | 1024→1536 (32.0ms) |
| 8 | **0 / 5,764,096 f** | **0 / 0** | 22,519 calls bad=0 | 22,514 | 179 µs | 512→1024 (21.3ms) |
| 9 (**clean HEAD 検証**, §4-1) | **0 / 5,764,096 f** | **0 / 0** | 22,521 calls bad=0 | 22,514 | 665 µs | 512→1536 (32.0ms) |

- 走査フレーム **5,758,464〜5,764,096 f** で、9 回すべて公称 120 s × 48,000 = 5,760,000 f の 99% (5,702,400 f) 以上。
  wasm 側 wall (`secs_wall`) = 実測 **120.068 / 120.071 s** (2 回の記録)、実効レート **47,988.7〜48,001.7 f/s** (公称 48,000 の −0.024%〜+0.004%)。
  未消費ぶん (`produced_frames` − covered) = 768〜1,280 f は ring 内でまだ消費されていない生成分。
- COM 面は 9 回とも `sellog [[1,2],[2,0],[1,7],[7,0]]` / `refs_last=0` / `alive=0` / `qi_ok=1` / `hr=0/0/0` / `driver="FL Studio ASIO"` / `output_ready=-1000` / `dialogs=0` / `cmd17=0` / `getChannels 2/2` / `getBufferSize 0x100/0x1000/gran 0` / `type 0x13`。
- capture SAB (120 s 分): frames=5,768,192 / **44.2 MiB** (定義: `64 + frames×(outCh+inCh)×4 + (frames/128)×4` B, outCh=2, inCh=0)。
- short mode: `--soak 8` でも **4/4 PASS** (soak ramp 0/384,512 f = 8.01 s 分, underruns 0)。`--quick` は soak を実行しない (親 e2e `asio_ramp_b256_soak120` と同一規約)。

## 4. 既存 e2e への影響 (非破壊確認)

`bash tools/audio/e2e.sh` (22 シナリオ, 本アダプタは未リンク = 影響経路なし) を 2 周実行: いずれも **21/22** で、唯一 `asio_sine_b256_96k` が 96kHz 時のブラウザ burst 観測値依存の FAIL-FAST (`fla_open: effective depth > 16` — flaudio.c の親コード内, 実行時観測) で落ちたが、**単独再実行では 2 回とも PASS** (underruns 0 / clock 95,939.9Hz・96,017.0Hz)。並行 subagent の負荷で burst 観測が伸びる環境依存であり、CAB-97 とは無関係。ASIO B=128–1024 の underrun 0 水準 (asio_loop_noise_b128/256/512, asio_ramp_b256_load, soak120 など) は維持。

検証時の再実行 (2026-10-11, `bash tools/audio/e2e.sh --quick`, load 1分 15.58→20.14): **21/21 PASS / exit 0 / 65 秒**。
`--quick` は `asio_ramp_b256_soak120` を落とすので、上記の 21 シナリオには soak が含まれない
( soak は committed `results/results.json` の記録: **underruns=0, ramp mismatches=0/5,764,096** で検証済み)。

### 4-1. CAB-270 着手時の再実行 (2026-10-11, 規則 45・クリーン HEAD 照合)

- 作業ツリー (本 ticket の変更あり): フル 22 シナリオ **21/22 PASS** / exit 1 / **実測 372 秒** (load 1分 2.57)。唯一の FAIL = `asio_sine_b256_96k` (上記の既知 AU-11)。`--out tools/audio/work/results_parent_regress.json` **へ出力をリダイレクト**したため tracked な `tools/audio/results/results.json` は**上書きしていない** (git status で差分 0 を確認)。
- **clean HEAD `731e32e` のスナップショット** (規則 45①: `git archive HEAD -- tools/audio public src/runtime package.json tsconfig.json | tar -x -C tools/audio/work/verify_731e32e` + `node_modules` を symlink) で同一コマンド: **21/22 PASS** / **実測 374 秒** (load 1分 2.69)。FAIL も同じ `asio_sine_b256_96k` 1 件。
- `asio_sine_b256_96k` を単独 10 回再実行: 作業ツリー・clean HEAD の**両方で 10/10 abort** (`fla_open: effective depth > 16`)、すなわち今回は常時再現する既知事象。
- 本チケットの変更は `tools/audio/asio/` のみ。親 e2e が参照するファイル (`tools/audio/{src,test,harness}`・`public/worklets/fl-audio-worklet.js`・`src/runtime`) は HEAD と**差分 0** (`diff -r` と `git status --porcelain` の両方で確認)。→ **本チケット起因の親 e2e 劣化は 0**。96k は CAB-210 (AU-11) として別途起票済み。
- クリーン検証結果 `tools/audio/work/results_96k_head.json`・`results_parent_head.json`・`results_parent_regress.json` は `work/` (gitignore) 配下。
- **asio e2e 自身も clean HEAD 検証**: `tools/audio/work/verify_head_final` (HEAD から `git archive`・`node_modules` symlink、作業ツリーと `diff -r` で差分 0) で `bash tools/audio/asio/e2e.sh` → **4/4 PASS / 実測 142 秒** (soak ramp 0/5,764,096・underruns 0・bsti 22,521 bad=0)。§3-2 の実行 9。

## 5. 再現手順

```sh
bash tools/audio/asio/e2e.sh              # 1 コマンド検収 (node 126/126 + Chrome 4/4 に 120s soak を含む・実測 139〜141 秒)
bash tools/audio/asio/e2e.sh --quick      # Chrome シナリオ 3 秒短縮・soak は実行しない
bash tools/audio/asio/e2e.sh --soak=8     # soak を 8 秒に短縮した 4 シナリオ (short mode 確認)
node tools/audio/asio/harness/soak_recount.mjs          # 独立再計算 + JSON ablation (16 項目)
node tools/audio/asio/harness/soak_recount.mjs --only-selftest   # 合成 SAB による検出器 selftest (9 項目)
IASIO_FORCE_SHIMX_SRC=1 bash tools/audio/asio/build.sh   # shimx をソースからビルド (クリーンチェックアウト用の常設 path もある)
bash tools/audio/e2e.sh --out tools/audio/work/results_parent.json   # 親 e2e 22 シナリオ (実測 372〜374 秒・21/22)
```

成果物は `work/` (gitignore)。20MB 超 blob なし (最大 = work/node/com_check.wasm 149,231 B / committed blob 最大 = com_test.wasm 114,508 B)。

**環境前提 (規則 43)**: `e2e.sh` は**自分で `[PNPM-HOME]` を PATH に追加するため呼出し側の export に依存しない** (node 前提)。emcc は `[EMSDK]` の `emsdk_env.sh` を `build.sh` が source。`TMPDIR` 未設定でも大物は `tools/audio/asio/work/` (実ディスク・gitignore) に出るので `/tmp` (tmpfs) は使わない。Chrome は headless `google-chrome 154`・fake 出力シンク (音声 HW 無し)。

## 6. 変更ファイル (CAB-270)

| ファイル | 変更 |
|---|---|
| `harness/run_com.mjs` | soak シナリオ `com_soak{N}_b256` 追加 (`--soak N` で秒数指定・既定 120)。`--quick` では非実行。判定は既存 `comOk`/`underrunFree`/`reportedOk` + 新規 `rampExact`/`timeinfoOk`/`soakCover` |
| `harness/com_page.mjs` | 短シナリオの既存動作 (40 s) を変えず、長シナリオ用に timeout 余裕を `max(40, secs×0.5)` に拡張 |
| `e2e.sh` | `--soak=<秒>` を透過 (未知オプションは exit 2) |
| `harness/soak_recount.mjs` | **新規**: 独立再計算 (14 項目) + JSON ablation (2 項目) + 合成 SAB selftest (9 項目) |

`tools/audio/src`・`tools/audio/harness`・`tools/audio/test`・`public/worklets`・`src/runtime`・`tools/shimx` は**変更 0 行**。

## 7. CAB-270 検証 (規則 36〜41)

### 7-1. 独立再計算 (規則 37) — `harness/soak_recount.mjs`
実装側 `run_com.mjs` の期待関数とは**別アルゴリズム**で `work/results_com.json` を再計算する。
コマンド: `node tools/audio/asio/harness/soak_recount.mjs` → **16/16 PASS (0 FAIL)** (14 再計算 + 2 JSON ablation)。`--selftest` を付けると合成 SAB selftest 9 項目が加わり **25/25 PASS**。

| ID | 突合するもの (別導線) | 実測 |
|---|---|---|
| R1a | worklet の `underrun_events` (capture SAB hdr[6]) ↔ shim producer の `stats.underruns` | 0 = 0 |
| R1b | underruns / silence_frames | 0 / 0 |
| R1c | ramp mismatches | 0 / 5,762,048 |
| R2a | `cb_count×B ≤ covered ≤ produced_frames` | 5,761,536 ≤ 5,762,048 ≤ 5,763,328 (差分 512 / 1,280) |
| R3 | `frames ÷ secs_wall` ≈ `ctx.sampleRate` | 47,988.7 f/s vs 48,000 (−0.024%) |
| R3b | `secs_wall` ≥ 公称秒数 | 120.071 ≥ 120 |
| R4a | `timeinfo.calls` ≥ `cb_count` (SupportsTimeInfo=1 → timeinfo が本体) | 22,513 / 22,506 = 1.0003 |
| R4b | host と flasio の timeinfo カウント差 ≤ 16 | 差 1 |
| R4c | `timeinfo.bad` (位置単調・sr 一致) | 0 |
| R5a–R5d | sellog / 参照カウント / HRESULT / asioMessage 応答 | 全一致 |

### 7-2. ネガティブコントロール (規則 41) — 3 経路すべて実測
1. **合成 SAB selftest** (SAB は保存されないため、同じ照合関数を合成 SAB に対して実行): 定義 `F=4096` の合成バッファ。
   clean → direct mismatches **0** / delta breaks **0** / zero_runs **0**。連続 24 f を定値汚染 → direct **24** / delta **25** / zero_runs **0**。
   連続 20 f を無音ランに → direct **20** / delta **21** / zero_runs **1**。→ bit-exact 検出器は clean で 0・汚染で過不足なく検出 (空振りなし)。
2. **JSON ablation**: `stats.underruns` を 0→1 に書き換えると R1a・R1b が **FAIL** (worklet=0 vs shim=1)。`ramp.mismatches` を 0→1 にすると R1c が **FAIL**。
3. **e2e ゲート ablation**: `bash tools/audio/asio/e2e.sh --soak=0` (実質 soak なし) → soak シナリオ **FAIL** (COM: output_ready=9999 / ramp 0/512)・**exit code 1**。3/4 PASS で e2e が止まる。

### 7-3. 検証範囲 / 範囲外 (規則 40)
- **検証したもの**: `CoCreateInstance` → IASIO 19 メソッド通し (CreateBuffers/Start/bufferSwitchTimeInfo/getLatencies/getSamplePosition/outputReady/Stop/DisposeBuffers/Release) の 120 秒連続実行。fake シンク (音声 HW 無し) の headless Chrome 154・Linux。
- **範囲外**: 実オーディオデバイス (Windows/mac の ASIO ドライバ)・Firefox/Safari・実 FLEngine からの呼出 (CAB-33 の結線後)・30 分以上の長期 soak (AU-10 = CAB-190)・120 秒未満のショートモードでの耐久性。
- **比較対象**: 親 e2e の `asio_ramp_b256_soak120` (`flasio_*` 直接経路, 同じ 120 s, ramp 0/5,764,096) は**別経路**であり、本 soak の代替ではありません (親の記録は `tools/audio/results/results.json`)。

## 8. 未解決 (起票先つき・規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| COM 経由 soak は 120 秒のみ。30 分 soak (CAB-9 検証条件) は AU-10 として未実施 | 長時間での ring/T 劣化未確認 | **CAB-190** (AU-10) |
| `asio_sine_b256_96k` の `fla_open: effective depth > 16` abort (今回 10/10 再現) | 親 e2e が 22 シナリオ系で 21/22 | **CAB-210** (AU-11・起票済み)。本チケット起因でないことを §4-1 で実測 |
| asioMessage selector 6 の内部コマンド 0x17 の正体 | soak 中の `cmd17=0` 実測。解釈は推定のまま | **CAB-97** にコメント済 |
| shimx 側 `CoCreateInstance` の REGDB_E_CLASSNOTREG スタブからのフォワード 1 行 | 実 FLEngine 結線前に必要 | **CAB-33** に引継ぎ (§9) |
| 短シナリオ `com_ramp_b256_d2` の underrun (§11 実行 A: 3 回中 1 回) | 短シナリオの負荷依存。120s soak は 3 回とも 0 | **#98** にコメント済 (2026-10-13 15:29 UTC・経過と実行 A〜E の値を記録)。ゲート扱いは §11 の決定 (ゲートに残す) |

## 11. 修正 PR #771 (#98 差し戻し対応) の実測

- 検証 HEAD: 実行ごとに下表の HEAD を記載 (A〜B は `fef39e5`、D は `b341b6e5`、E は `59c952e1`)。
- 環境: runner 16 コア・load 1分 0.04〜0.66。emsdk は `emsdk install latest` (`$RUNNER_TEMP/emsdk-src`) を使用。`tools/audio/asio/work/` は gitignore。

| 実行 | コマンド | 結果 | 所要 | load 1分 (開始→終了) |
|---|---|---|---|---|
| A | `bash tools/audio/asio/e2e.sh` (1 回目) | exit 1 · node 126/126 · Chrome **3/4** (`com_ramp_b256_d2` underruns=1 silence=1280, ramp 185984/241024) | 204 秒 | 0.49 → 0.03 |
| B | 同 (2 回目) | exit 0 · node 126/126 · Chrome **4/4** (`com_ramp_b256_d2` underruns=0, ramp 0/240896 / soak underruns=0, ramp 0/5762816, bsti 22516 bad=0) | 203 秒 | 0.05 → 0.05 |
| C | `bash tools/audio/e2e.sh --quick` (親 e2e・asio 呼出を含む) | exit 0 · 親 **42/42 PASS** · asio node 126/126 · Chrome 3/3 (quick は soak 省略) | 330 秒 | 0.23 → 0.66 |
| D (HEAD `b341b6e5` = main を merge) | `bash tools/audio/e2e.sh --quick` | exit 0 · 親 **42/42 PASS** · asio node 126/126 · Chrome 3/3 | 329 秒 | 0.11 → 0.18 |
| E (最終 HEAD `59c952e1`) | `bash tools/audio/asio/e2e.sh` (120s soak 込み) | exit 0 · node 126/126 · Chrome **4/4** (soak ramp 0/5762816, underruns 0, bsti bad=0 は実行ログ参照) | 203 秒 | 0.04 → 0.04 |

- 指摘 1 への対応: `tools/audio/e2e.sh` の末尾で `bash tools/audio/asio/e2e.sh` を呼ぶ (`--quick` は引き継ぐ)。
- **未解決 (再現性)**: 実行 A の短シナリオ underrun は B・C で再現せず、1/3 回の発生。120s soak は 3 回とも underrun 0。
  負荷依存と推定 (表の A 行の load 0.49 が開始時の実測値)。
- **親 e2e ゲートの扱い (決定)**: `com_ramp_b256_d2` の underrun は**ゲートに残す** (exit 1 のまま)。判定基準 underrun 0 を緩めず、揺らぎは #98 で追跡する。merge 判定で 1/3 回の再実行が必要になる場合がある。

## 9. 検収記録 (2026-10-11・CAB-97 検収 agent・規則 36〜41)

- 検証起点 commit **3d35d65**。`bash tools/audio/asio/e2e.sh` → node check **126/126 PASS**・headless Chrome **3/3 PASS** (7 回中 6 回。負荷依存 1 回は §3-1)。最終実行は load 1分 2.08 で 3/3・exit 0。
- **独立再計算 (別アルゴリズム・規則 37)**: `accept_recount.mjs` — `work/node_check.json` ではなく
  `test/com_test.c` のソースから判定呼出しサイトを静的集計 (`CK(`/`CKV(` = 数値照合 / `ck_str(` = 文字列照合) し、
  実測 JSON と突合する。出力: **`CK=6 + CKV=109 + ck_str=11 = 126` / JSON n=126・fail=0 / 名前集合は完全一致 /
  内訳 hostmsg 15 (selector 13 + カウンタ 2), slot 監査 7, shimx 実レジストリ 14**。
  注: `com_test.c` 冒頭コメントの「66 項目」は**旧値の残骸**で実測 126 (本 commit で修正)。
- **ネガティブコントロール (規則 41)**: ① node check の JSON で check #0 をわざと不一致にすると e2e.sh の判定が
  **exit 1** で FAIL を検出 (非破壊時は exit 0)。② Chrome では §3-1 の 1 回の実 FAIL (underruns=1) が
  同様に exit 1。→ どちらの判定ゲートも空振りでない。
- **誤記修正 (本 commit)**: `com_test.c` 冒頭「66 項目」→ **126 項目** / REPORT「asioMessage 応答表 14 項目」→
  **15 項目 (selector 13 + カウンタ 2)** / Chrome 単発値 (cb_max 84µs・15µs・945 calls・240,640 frame) を
  6 回の実測レンジに置換 / 「約 1.5 分」→ **20〜21 秒 (実測)** / 親 e2e の「約 2 分」→ **65 秒 (実測・quick)**。
- **未解決 (起票先つき)**: (a) `asioMessage` selector 6 の内部コマンド 0x17 の正体は未解消 →
  CAB-97 本 ticket にコメント済 (推定: 再起動系。INVENTORY §6 既知事項のまま)。
  (b) `shimx` 側 `CoCreateInstance` の REGDB_E_CLASSNOTREG スタブからのフォワード 1 行は shimx 担当で未実施 →
  CAB-33 (実 FLEngine 結線) に引継ぎ (§9)。

## 10. CAB-33 (実 FLEngine 結線) への引継ぎ事項

1. **入口は 1 箇所**: shimx 側 `CoCreateInstance` (現状 REGDB_E_CLASSNOTREG スタブ) から `iasio_co_create_instance` へフォワードする 1 行改変は shimx 担当 (tools/shimx は読取専用のため本 ticket では未実施)。`iasio_shimx_register()` を 1 度呼べばレジストリ実体が揃う。
2. **呼出規約ブリッジ**: lifted FLEngine からの vtable 間接呼出は hostbridge の i64↔i32 ブリッジを要する (shimx REPORT §3-8 同項, iasio.h 冒頭に記載)。
3. **CoGetClassObject の IID**: クラスオブジェクトは IID_IUnknown/IID_IClassFactory のみ受付 (COM 標準どおり)。CoCreateInstance 経由なら IID_IASIO で取得可 — 本検収で実証済み。
4.asioMessage selector 6 の内部コマンド 0x17 の正体 (再起動系と推定) は未解消 (INVENTORY §6 既知事項のまま)。

## 12. #998 [AU-16] com_ramp_b256_d2 の underrun フレーク調査

**結論: 検証 HEAD `a89d4ea3` で 5/5 PASS。ただし §11 実行 A の underrun の原因は特定できていない (再現せず)。ゲート基準 underrun 0 は変更していない。**

- **通算の母集団 (定義)**: `com_ramp_b256_d2` を含む実行のうち、issue #998 の実行 A〜E (§11 の A〜E と同一。5 回・fail 1 回) と本節の 5 回を合わせた **10 回・underrun 1 回**。§8 の「3 回中 1 回」は §11 の asio 単独 A/B/E の部分集合、2026-10-13 main `7e8445b9` の 4/4 PASS は issue #998 本文の記述のみで、本 REPORT に実行記録が無いため**通算に含めない** (含める場合は母集団 11 回・underrun 1 回)。

実測 (`bash tools/audio/asio/e2e.sh` を HEAD `a89d4ea3` の worktree で foreground 連続 5 回、exit 0):

| 実行 | exit | 所要 | 実行前 load | node check | Chrome | underruns (4 シナリオ) | ramp mismatch (b256_d2 / b1024_d2 / soak) |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 204 s | 0.08 | 126/126 | 4/4 | 0 / 0 / 0 / 0 | 0 / 0 / 0 |
| 2 | 0 | 203 s | 0.08 | 126/126 | 4/4 | 0 / 0 / 0 / 0 | 0 / 0 / 0 |
| 3 | 0 | 203 s | 0.05 | 126/126 | 4/4 | 0 / 0 / 0 / 0 | 0 / 0 / 0 |
| 4 | 0 | 204 s | 0.01 | 126/126 | 4/4 | 0 / 0 / 0 / 0 | 0 / 0 / 0 |
| 5 | 0 | 203 s | 0.24 | 126/126 | 4/4 | 0 / 0 / 0 / 0 | 0 / 0 / 0 |

- **検証範囲**: Linux runner・headless Chrome 154 (fake 出力シンク)・実行前 load 0.01〜0.24 の低負荷・連続 5 回。
- **範囲外**: 負荷を掛けた状態 (並行 e2e)・実オーディオデバイス (実 ASIO ドライバ)・Windows/mac。5 回で再現なしは「低負荷で再現しなかった」以上を主張しない。
- **ネガティブコントロール (新規実行なし)**: 短シナリオの判定が空振りでないことは §11 実行 A の実 FAIL (`underruns=1 silence=1280`) で示される。判定の検出器そのものは §7-2 で検証済み: 合成 SAB (clean で direct 0 / 24 f 汚染で direct 24・delta 25) と JSON ablation (`underruns` 0→1 で R1a・R1b が FAIL)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実行 A の underrun の原因 (負荷・ring 深さ・worklet スケジューリング) が未特定。本 5 回と §11 B〜E では再現せず | ゲート (underrun 0) が通算 1/10 回揺らぐ。merge 判定で再実行が必要になり得る | #998 |
| 負荷下の再現は §12-3 で実施 (完全実行 6 回中 2 回 underrun)。原因は未特定。underrun 時の ring 深さ・worklet 側ログは未採取 | 原因の切り分けができない | #998 |
| 実行 A は HEAD `fef39e5` (別コミット)。同一 HEAD での再現ではない | 同一 HEAD の再現条件が未確定 | #998 |

負荷下の再現試験 (L1〜L3・§12-3 の A〜D) は [REPORT_APPENDIX_998.md](REPORT_APPENDIX_998.md) を参照。負荷下の完全実行 6 回中 2 回 underrun (`com_ramp_b256_d2`)。underrun 時は ring 充填が 0 まで枯渇 (`min_fill=0`)。原因は未特定。underrun 直前の充填推移 (producer 追従不足の形) は §12-4 (付録) を参照。#6037 (AU-50) の停止の時系列計装は [REPORT_APPENDIX_6037.md](REPORT_APPENDIX_6037.md)。
#2934 (AU-26) の初期 T 下限 (`FLA_F_T_FLOOR`・main 済み) の実測は [REPORT_APPENDIX_2934.md](REPORT_APPENDIX_2934.md)。#4593 (AU-47) の callback 区間内訳の計装と 20 回測定は [REPORT_APPENDIX_4593.md](REPORT_APPENDIX_4593.md)。#2777 の原因 (部分特定)・床の適用後の再測定 (測定 commit `c0fb6e074` の 15 回で 1 FAIL・producer の 24 ms 以上の停止) は [REPORT_APPENDIX_2777.md](REPORT_APPENDIX_2777.md) §7。直接経路は [AU-40] #3757 へ。
