# tools/audio/asio — IASIO COM アダプタ (CAB-97 [AU-1]) REPORT

## 0. 結論

**完了。** FLEngine が `CoCreateInstance(IID_IASIO)` で取得できる ASIO ドライバ面 (IASIO vtable 24 スロット = IUnknown 3 + IASIO 21) を実装し、実体を検収済み `flasio_*` (tools/audio/src/flasio.c) へ委譲した。1 コマンド検収 `bash tools/audio/asio/e2e.sh` (exit 0) = **node 静的検証 126/126 PASS + headless Chrome 3/3 PASS**。既存 tools/audio e2e は **22/22** (2 周目実測、§4) を維持。親 e2e への組込みは行っていない (本 e2e が単独で完結、§6)。

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
- **harness/**: `run_com.mjs` (3 シナリオランナー, tools/audio/harness/chrome.mjs 流用) + `com_page.mjs` (page.mjs 流儀, ramp/sine bit 突合) + `index_com.html`。

### 実測値の取込 (INVENTORY §2-§3 / CAB-9 検収 03dbd1a)

- asioMessage 応答表 (host モック): selector 7 (SupportsTimeInfo)→**1**, 6 (LatenciesChanged)→内部コマンド 0x17 発行後 1, 8 (TimeCode)→0, 3/4/5→dialog (0x425210, id 0x55f) 後 1, 2 (EngineVersion)→2, 1 (Supported)→value∈[2..8] で 1。
- ILWASAPI2ASIO プロファイル: getChannels **2in/2out**, getChannelInfo type **0x13 (ASIOSTFloat32LSB)** / group 0 / "Out %i", getBufferSize **min 0x100 / max 0x1000 / gran 0** (作成後 pref = B), canSampleRate {22050,44100,48000,96000,192000}, getClockSources 1 件 **"Internal"**, outputReady **ASE_NotPresent (-1000)**, future 既定 -998。
- ASIOCallbacks 4 関数 (bufferSwitch 0xc57420 / sampleRateDidChange 0xc576b0 / asioMessage 0xc576c0 / bufferSwitchTimeInfo 0xc56ae0 = 本体) を 8B スロットで受渡し。ASIOTime は 148B (0x94) 実測どおり static_assert で保証。

## 3. 検収実測 (`bash tools/audio/asio/e2e.sh`, exit 0)

### node check (COM 面静的検証) — **126/126 PASS**
win64 レイアウト static_assert (BufferInfo64=24B/buffers@8, Callbacks64=32B, ASIOTime=148B, vtable=192B) / asioMessage 応答表 14 項目 / IUnknown+IClassFactory+CLSID 解決 (正常系・失敗系) / slot index 監査 (生 slot 呼出 vs typed 呼出の一致 6 項目) / 19 メソッド + getErrorMessage/future の戻り値照合 / vreg 登録→FLEngine フロー / **shimx 実レジストリ経由** (Reg* で software\asio 列挙→clsid→CoCreateInstance→init) / 8B スロット変換の往復。

### headless Chrome (FLEngine 呼出を模した全経路) — **3/3 PASS**
| シナリオ | 実測 |
|---|---|
| com_ramp_b256_d2 | ramp 不一致 **0 / 240,640 frame** (bit-exact), underruns **0** silence 0, bufferSwitchTimeInfo **945 calls bad=0** (samplePosition 単調 + sr 一致), cb_max **84µs**, QI 1 / alive 0 (Release で自己解放), sellog `[[1,2],[2,0],[1,7],[7,0]]` (= flasio_create_buffers ハンドシェイクの実測問合せ順) |
| com_ramp_b1024_d2 | ramp **0/240,640**, underruns **0**, cb_max 15µs, T=3072 (64.0ms) |
| com_sine_b256_d2 | sine maxErr **1.49e-8** (< 1e-5 基準), zeroRuns 0, underruns **0**, rms 0.3536 (= 0.5/√2 理論値) |

全シナリオで `getChannels 2/2, getBufferSize 0x100/0x1000/gran 0 (作成後 pref=B), type 0x13, lat_out>0` を確認。`output_ready = -1000 (ASE_NotPresent)` も実測一致。

## 4. 既存 e2e への影響 (非破壊確認)

`bash tools/audio/e2e.sh` (22 シナリオ, 本アダプタは未リンク = 影響経路なし) を 2 周実行: いずれも **21/22** で、唯一 `asio_sine_b256_96k` が 96kHz 時のブラウザ burst 観測値依存の FAIL-FAST (`fla_open: effective depth > 16` — flaudio.c の親コード内, 実行時観測) で落ちたが、**単独再実行では 2 回とも PASS** (underruns 0 / clock 95,939.9Hz・96,017.0Hz)。並行 subagent の負荷で burst 観測が伸びる環境依存であり、CAB-97 とは無関係 (HEAD の検収結果 results.json も 22/22 PASS を記録)。**マージ後の results.json は 22/22 PASS**。ASIO B=128–1024 の underrun 0 水準 (asio_loop_noise_b128/256/512, asio_ramp_b256_load, soak120 など) は維持。

## 5. 再現手順

```sh
bash tools/audio/asio/e2e.sh          # 1 コマンド検収 (node 126/126 + Chrome 3/3, 約 1.5 分)
bash tools/audio/asio/e2e.sh --quick  # Chrome シナリオ 3 秒短縮版
IASIO_FORCE_SHIMX_SRC=1 bash tools/audio/asio/build.sh   # shimx をソースからビルド (クリーンチェックアウト用の常設 path もある)
bash tools/audio/e2e.sh               # 親 e2e 22 シナリオ (約 9 分, --quick 約 2 分)
```

成果物は `work/` (gitignore)。20MB 超 blob なし (最大 = com_test.wasm 114,508B)。

## 6. CAB-33 (実 FLEngine 結線) への引継ぎ事項

1. **入口は 1 箇所**: shimx 側 `CoCreateInstance` (現状 REGDB_E_CLASSNOTREG スタブ) から `iasio_co_create_instance` へフォワードする 1 行改変は shimx 担当 (tools/shimx は読取専用のため本 ticket では未実施)。`iasio_shimx_register()` を 1 度呼べばレジストリ実体が揃う。
2. **呼出規約ブリッジ**: lifted FLEngine からの vtable 間接呼出は hostbridge の i64↔i32 ブリッジを要する (shimx REPORT §3-8 同項, iasio.h 冒頭に記載)。
3. **CoGetClassObject の IID**: クラスオブジェクトは IID_IUnknown/IID_IClassFactory のみ受付 (COM 標準どおり)。CoCreateInstance 経由なら IID_IASIO で取得可 — 本検収で実証済み。
4.asioMessage selector 6 の内部コマンド 0x17 の正体 (再起動系と推定) は未解消 (INVENTORY §6 既知事項のまま)。
