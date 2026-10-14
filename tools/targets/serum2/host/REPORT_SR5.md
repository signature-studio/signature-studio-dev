# REPORT — [SR-5 #73] Serum 2 参照音源との dB 誤差ハーネス (参照は wine64 で生成)

- 日付: 2026-10-14 / 測定 commit: `4993995f` (SR-47 #2414 のコード変更を含む最後の commit。実測は §4)。§1・§2 の既存測定は `8680cf44` (SR-5 当時)
- 再現: `bash tools/targets/serum2/host/ref_harness.sh` (参照生成 → 決定性 → self-test → ネガコン)。wasm 候補は第 1 引数。
- 入力: 実 `Serum2_win64.vst3` sha256 `501e7bb3…5283` (無改変 unpatched)。取り出し: `tar --zstd -xf <plugins-serum2.tar.zst> -C work/dl Install_Xfer_Serum2_2.1.5.exe` → `7z x -y -owork/exe_extract <exe> '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'` → `work/Serum2_win64.vst3` へ cp。
- 前提 (runner): `sudo apt-get install -y --no-install-recommends wine64 libwine g++-mingw-w64-x86-64-posix` (素材 `apt-mingw` は `gcc-mingw-w64-x86-64` のみで、`build.sh` の `x86_64-w64-mingw32-g++` は入らない)。`ref_render.sh` は PATH に `wine64` が無いときだけ wine 同梱 dir を足す。
- content dir (DLL の CWD): 既定は installer 全展開 `work/content_full` (Tables あり。`host/ref_content.sh` で作る。SR-47 #2414 で切替え、根拠は §4)。専用の空 dir は env `S2REF_CONTENT` で指定する (variant)。**出力は content dir の中身で変わる** (§1)。

## 0. 結論

1. **参照レンダラ**: `ref_render.sh` で実 DLL を wine64 上から駆動し、32-bit float WAV を書く (`vst3host.cpp` に WAV 書出と `S2HOST_PITCH` を追加)。既定 state (Init)・48 kHz・128 frames・64 blocks・NoteOn C4 (block 0) / NoteOff (block 24)。WAV 本体は `work/` (gitignore)、commit は `ref_manifest.json` (sha256・基本メトリクス・再生成コマンド) のみ。
2. **再現性**: 同一入力 3 回で WAV ファイル全体の SHA-256 が一致。ORACLE T2 を満たした。許容クラス D の反映は不要。ただし参照 WAV は **content dir 条件ごとに別物** (空 dir `672007a0…` / 全展開 `b4fd6d64…`)。**参照 (主 pin) は installer 全展開条件** (SR-47 #2414 で空 dir から切替え。根拠 §4)。空 dir 条件は `ref_manifest.json` の `content_empty` (variant) として残す。
3. **ハーネス**: 判定は `tools/flp` の `judgeWav` (`cli/wavcmp.ts`) を `bun` で呼ぶ (runner の Node は 22 で `.ts` の type-stripping が使えないため)。
4. **ネガコン (両方・両条件で FAIL)**: 別ノート C#4 を D-spectral で FAIL、1 サンプル (+0.01) 改変を A-exact で FAIL (値は §1)。
5. **未達 (受入 4)**: wasm 側との比較は SR-4 の WAV が無いため未実施。入力口 (第 1 引数) までを作った。残りは子 issue に移した (§3)。

## 1. 実測

測定 commit `8680cf44`、wine64 9.0、実 DLL。Init state・C4・48 kHz・128 frames・64 blocks。load は開始時の 1 分値。

| 項目 | 空 dir (`work/ref_content`。SR-47 以前の既定 → `content_empty`) | installer 全展開 (7,370 files・Tables あり。SR-47 以降の既定 → 主 pin) |
|---|---|---|
| ref 3 回の file SHA-256 | 一致 `672007a06d1482ada6f846ec8f5e8a763a2586e032dbabe5fb5432332bd332c1` | 一致 `b4fd6d642b2d0a8f8e4b075b91b029ca4c6fc95ed3688c3e9397cf03ea416420` |
| data 部 SHA-256 | `7adcbc28…81fce` | `87fb7149…058ef` |
| peak / rms | 0.790915 / 0.310052 (非ゼロ 16,380/16,384 cell) | 0.691102 / 0.269762 |
| ref_manifest.json との pin 照合 | 一致 (測定当時の主 pin。現在のキーは `content_empty`) | 一致 (現在の主エントリ `main` = JSON の top-level。旧キー `content_full` は主エントリに統合 (§4.2)) |
| self-test (ref_1 vs ref_2, A-exact) | PASS (bit-exact) | PASS (bit-exact) |
| ネガコン 別ノート (D-spectral) | FAIL: rmsDiff 3.4 dB・STFT 4086/4102 bin・LUFS 差 0.438 | FAIL: rmsDiff 4.3 dB・STFT 4902/4922 bin・LUFS 差 1.852 |
| ネガコン 1 サンプル改変 (A-exact) | FAIL: maxUlp 671089 | FAIL: maxUlp 1342177 |
| `ref_harness.sh` | NG=0, 14.0 s, load 0.30 | NG=0, 14.0 s, load 0.21 |

- 件数: 「全展開 7,370 files」は installer 全展開 (`7z x`) の files 数で、`$COMMONFILES64` (8 files) と `$PLUGINSDIR` (5 files) を含む。「7,357 files」は wasm 側が読む content の 7 グループ (`tools/assets/serum2/REPORT.md` §2)。差 13 files は content ではない。
- `saved_controller_state.bin` は 2 条件 (と `exe_extract` = DLL のみ) で同一。`saved_processor_state.bin` は空 dir と DLL のみの `exe_extract` で同一 (1,200 B)、全展開だけ異なる (1,253 B)。出力 WAV の差は content 由来で、DLL・MIDI・SR は同じ。
- 既存 `e2e.sh` (測定 commit `8680cf44`。content は `work/exe_extract` = DLL のみ展開): **62/62 OK, 69.5 s, load 0.23**、NC1/NC2 とも期待どおり (exit 1, NG=1)。
- 履歴 (測定 commit `dcafb442`。参照は `exe_extract` を CWD にしていた): `ref_harness.sh` NG=0, 13.6 s, load 0.33 / `e2e.sh` 62/62 OK, 67.3 s, load 0.12。空 dir と pin が同じ `672007a0…` なので、`dcafb442` からの content dir 切替で参照は変わっていない。
- 補助 (実 DLL なし。再測定ではない): `ref_stub_check.sh` (§2.1)。実行 commit `8680cf44`、wine64 導入済み runner で FAIL=0。

## 2. 既存 e2e への影響 (SR-5 測定 commit `8680cf44` 以降のコード差分。SR-47 以降の差分は §4.3)

`vst3host.cpp` の変更は `dcafb442` の 1 commit のみ (WAV 書出と `S2HOST_PITCH` 追加。`S2HOST_PITCH` 未設定時は従来どおり pitch 60、WAV は追加出力のみで既存の summary・ログは変えない)。`dcafb442` 以降の host 配下のコード差分 (`92f88190`: 表記修正と `set -e` 下の終了コード処理、`8680cf44`: content dir の専用化と PATH 優先) は、いずれも `8680cf44` 上の `ref_harness.sh`・`e2e.sh` の実測に含まれる。

```
git diff 8680cf44 f108211e -- tools/targets/serum2/host ':(exclude)*.md'
(出力: 空 = 0 行。f108211e 以降の host のコード差分は SR-47 (#2414) の変更で、§4.3 の基点 4993995f から見て扱う)
```

### 2.1 実 DLL なしの補助確認 (stub wine64。再測定ではない)

再現: `bash tools/targets/serum2/host/ref_stub_check.sh`。決定的な合成 WAV (f32 2ch 48 kHz・8192 frame・ノート依存周波数) を書く偽 `wine64` を PATH 先頭に置き、`ref_render.sh` / `ref_harness.sh` の制御経路だけを実行する。`ref_render.sh` は PATH に `wine64` があればそれを使うので、実 wine64 が導入済みの runner でも偽 wine64 が選ばれる (`f188d7ae` では常に wine 同梱 dir を先頭に足し、導入済み runner で FAIL=5 になった)。

| 確認 | 結果 |
|---|---|
| wine が rc=3 を返す | `wine exit=3 ...` を表示して exit 3 / rc=0 で exit 0 |
| content dir | 既定は `work/ref_content` (`tables=no`)。`S2REF_CONTENT=<Tables あり dir>` で `tables=yes`。存在しない dir は exit 1 |
| `ref_harness.sh` 全体 (stub WAV) | [1]〜[4] の流れは OK。[1] の ref_manifest.json 照合だけ NG (stub は実 DLL の出力でないため。pin 照合が効く確認) → NG=1 |

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 候補 (SR-4 の WAV) との比較 | 受入 4。入力口は `ref_harness.sh <candidate.wav> <class>` で用意済み。判定結果は §5 に追記する (§4 は SR-47) | #2383 [SR-45] (親: #73) |
| 参照は既定 Init state のみ (ファクトリ preset 未使用) | 「固定 state (preset 1〜数本)」の受入に届かない。Init 合成は preset 未取得時の許容 | #2384 [SR-46] (親: #73) |
| (解決済み) content 条件の正 | 全展開を正と決定 (§4)。空 dir は `content_empty` として残す | — (#2414 [SR-47] で完了) |
| C/D 許容閾値は暫定 (ORACLE §7) | ネイティブ FL の golden 待ち。Serum 2 の閾値は本件で再校正していない | ORACLE §7 (既存) |

## 4. SR-47 (#2414) — 参照 content 条件の正と既定の切替

### 4.1 判断 (正 = installer 全展開)

- **比較先の現状**: wasm 側 (SR-4 #75) はまだ WAV を出していない。`tools/targets/serum2/sr4/REPORT.md` の pilot は関数単位の bit 比較 (liftlib harness のランダム scenario) で、content dir を読まない。よって比較条件は**将来の wasm 本体が読む content** から決める。
- **wasm 本体が読む content**: SR-6 (`tools/assets/serum2/REPORT.md`) は素材 `plugins-serum2` の installer を `7z x` で全展開し、7 グループ 7,357 files (Tables 289 files を含む。全展開 7,370 files から §1 の 13 files を除いたもの) を LazyVfs で配信する設計で、全 files の sha256 一致まで確認済み。SR-6 の設計では wasm 側はこの全展開 content を読む。Serum 2 本体への FS shim 接続は未確認 (§4.4)。
- **SR-46 (#2384) との整合**: factory preset は全展開の `Presets/` からのみ取れる。全展開に揃えると SR-46 と同じ content 条件になる。
- **判定への影響**: 同じ DLL・MIDI・SR で content だけ変えると別の音になる (§1: 空 dir peak 0.790915 / 全展開 0.691102)。条件の選択は判定結果を変えるため、導入後の状態 (installer は Tables 等を導入する: `tools/targets/serum2/REPORT.md` §1.1) に合わせる。

→ **正 = installer 全展開 (`work/content_full`)**。空 dir は variant `content_empty` として残す。

### 4.2 変更 (`host/`)

- `ref_content.sh` (新): 素材 installer から `work/content_full/` (`7z x`・Tables あり) と `work/Serum2_win64.vst3` (DLL 無改変・sha256 `501e7bb3…5283` を確認) を作る。installer が無ければ `$ARTIFACTS_DIR/plugins-serum2.tar.zst` から取り出す。
- `ref_render.sh`: 既定 content を `work/content_full` にした (無ければ FAIL)。空 dir は `S2REF_CONTENT=<dir>`。
- `ref_manifest.json` / `ref_manifest.py`: 主エントリ = 全展開 (`ref_manifest.py <wav> <json> full`)。`content_empty` = 空 dir variant (`... empty`)。`content_full` 旧キーは主エントリに統合。
- `ref_harness.sh`: pin 選択を `tables=yes → main`、それ以外 → `content_empty` に。
- `ref_stub_check.sh`: 既定が全展開になったことに合わせて更新 (偽 wine64 で制御経路のみ確認)。

### 4.3 実測 (測定 commit `4993995f`・実 DLL・wine64 9.0・Actions runner)

検証手順 (コミット済み HEAD): `bash tools/targets/serum2/host/ref_content.sh` → `bash tools/targets/serum2/host/ref_harness.sh`。

| 項目 | 結果 |
|---|---|
| `ref_harness.sh` (既定 = 全展開) | **NG=0**・14.0 s・load 0.16 (実行後の 1 分値) |
| ref 3 回の file SHA-256 | 一致 `b4fd6d642b2d0a8f8e4b075b91b029ca4c6fc95ed3688c3e9397cf03ea416420` (data 部 `87fb7149…058ef`) |
| `ref_manifest.json` 主 pin (`main`) | 一致 |
| self-test (ref_1 vs ref_2, A-exact) | PASS (bit-exact) |
| ネガコン 別ノート (C#4, D-spectral) | FAIL: rmsDiff 4.3 dB・peakDiff 1.782 dB・STFT 4902/4922 bin |
| ネガコン 1 サンプル改変 (A-exact) | FAIL: maxUlp 1342177 |
| 空 dir variant (`S2REF_CONTENT=work/ref_content`) | 再レンダ `672007a0…` = `content_empty` pin と一致 (§1 と同値) |
| `ref_stub_check.sh` (偽 wine64) | FAIL=0 |

- §1 の全展開列と同じ値 (`b4fd6d64…`・peak/rms・ネガコン値) が再現した。SR-5 当時の pin と一致するため、DLL・MIDI・state は変わっていない。
- host/e2e.sh (SR-1 の 62 本 e2e) は未実行。`vst3host.cpp` と `e2e.sh` は無変更で、`ref_render.sh` / `ref_harness.sh` を呼ばない。
- 差分確認 (測定 commit 以降の md 以外のコード差分): `git diff 4993995f HEAD -- tools/targets/serum2/host ':(exclude)*.md'` → 出力 0 行。

### 4.4 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 候補 (SR-4 の WAV) との比較 (判定は §5 に追記) | 受入 4 (SR-5) | #2383 [SR-45] (親: #73) |
| 固定 factory preset での参照 (Init 以外) | 「固定 state」の受入。全展開の `Presets/` を使う | #2384 [SR-46] (親: #73) |
| 全展開 content を読む wasm 本体の接続 (FS shim → Serum 2 本体) | 比較条件の前提が実物の wasm で成立するかは未確認 (SR-6 §5 の未実施項目) | #2383 の比較時に確認 |
