# REPORT — [SR-5 #73] Serum 2 参照音源との dB 誤差ハーネス (参照は wine64 で生成)

- 日付: 2026-10-14 / 測定 commit: `8680cf44` (コードを変えた最後の commit。実 DLL・wine64 9.0 上で測定)
- 再現: `bash tools/targets/serum2/host/ref_harness.sh` (参照生成 → 決定性 → self-test → ネガコン)。wasm 候補は第 1 引数。
- 入力: 実 `Serum2_win64.vst3` sha256 `501e7bb3…5283` (無改変 unpatched)。取り出し: `tar --zstd -xf <plugins-serum2.tar.zst> -C work/dl Install_Xfer_Serum2_2.1.5.exe` → `7z x -y -owork/exe_extract <exe> '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'` → `work/Serum2_win64.vst3` へ cp。
- 前提 (runner): `sudo apt-get install -y --no-install-recommends wine64 libwine g++-mingw-w64-x86-64-posix` (素材 `apt-mingw` は `gcc-mingw-w64-x86-64` のみで、`build.sh` の `x86_64-w64-mingw32-g++` は入らない)。`ref_render.sh` は PATH に `wine64` が無いときだけ wine 同梱 dir を足す。
- content dir (DLL の CWD): 既定は専用の空 dir `work/ref_content` (Tables 無し)。installer 全展開 dir (Tables あり) は env `S2REF_CONTENT` で指定する。**出力は content dir の中身で変わる** (§1)。

## 0. 結論

1. **参照レンダラ**: `ref_render.sh` で実 DLL を wine64 上から駆動し、32-bit float WAV を書く (`vst3host.cpp` に WAV 書出と `S2HOST_PITCH` を追加)。既定 state (Init)・48 kHz・128 frames・64 blocks・NoteOn C4 (block 0) / NoteOff (block 24)。WAV 本体は `work/` (gitignore)、commit は `ref_manifest.json` (sha256・基本メトリクス・再生成コマンド) のみ。
2. **再現性**: 同一入力 3 回で WAV ファイル全体の SHA-256 が一致。ORACLE T2 を満たした。許容クラス D の反映は不要。ただし参照 WAV は **content dir 条件ごとに別物** (空 dir `672007a0…` / 全展開 `b4fd6d64…`)。**参照 (主 pin) は空 dir 条件**とし、全展開は `S2REF_CONTENT` 指定時の別 pin (`ref_manifest.json` の `content_full`)。全展開を正の参照にするかは #2414 で決める。
3. **ハーネス**: 判定は `tools/flp` の `judgeWav` (`cli/wavcmp.ts`) を `bun` で呼ぶ (runner の Node は 22 で `.ts` の type-stripping が使えないため)。
4. **ネガコン (両方・両条件で FAIL)**: 別ノート C#4 を D-spectral で FAIL、1 サンプル (+0.01) 改変を A-exact で FAIL (値は §1)。
5. **未達 (受入 4)**: wasm 側との比較は SR-4 の WAV が無いため未実施。入力口 (第 1 引数) までを作った。残りは子 issue に移した (§3)。

## 1. 実測

測定 commit `8680cf44`、wine64 9.0、実 DLL。Init state・C4・48 kHz・128 frames・64 blocks。load は開始時の 1 分値。

| 項目 | 空 dir (`work/ref_content`。既定・主 pin) | installer 全展開 (7,370 files・Tables あり。`S2REF_CONTENT`) |
|---|---|---|
| ref 3 回の file SHA-256 | 一致 `672007a06d1482ada6f846ec8f5e8a763a2586e032dbabe5fb5432332bd332c1` | 一致 `b4fd6d642b2d0a8f8e4b075b91b029ca4c6fc95ed3688c3e9397cf03ea416420` |
| data 部 SHA-256 | `7adcbc28…81fce` | `87fb7149…058ef` |
| peak / rms | 0.790915 / 0.310052 (非ゼロ 16,380/16,384 cell) | 0.691102 / 0.269762 |
| ref_manifest.json との pin 照合 | 一致 (主) | 一致 (`content_full`) |
| self-test (ref_1 vs ref_2, A-exact) | PASS (bit-exact) | PASS (bit-exact) |
| ネガコン 別ノート (D-spectral) | FAIL: rmsDiff 3.4 dB・STFT 4086/4102 bin・LUFS 差 0.438 | FAIL: rmsDiff 4.3 dB・STFT 4902/4922 bin・LUFS 差 1.852 |
| ネガコン 1 サンプル改変 (A-exact) | FAIL: maxUlp 671089 | FAIL: maxUlp 1342177 |
| `ref_harness.sh` | NG=0, 14.0 s, load 0.30 | NG=0, 14.0 s, load 0.21 |

- `saved_controller_state.bin` は 2 条件 (と `exe_extract` = DLL のみ) で同一。`saved_processor_state.bin` は空 dir と DLL のみの `exe_extract` で同一 (1,200 B)、全展開だけ異なる (1,253 B)。出力 WAV の差は content 由来で、DLL・MIDI・SR は同じ。
- 既存 `e2e.sh` (測定 commit `8680cf44`。content は `work/exe_extract` = DLL のみ展開): **62/62 OK, 69.5 s, load 0.23**、NC1/NC2 とも期待どおり (exit 1, NG=1)。
- 履歴 (測定 commit `dcafb442`。参照は `exe_extract` を CWD にしていた): `ref_harness.sh` NG=0, 13.6 s, load 0.33 / `e2e.sh` 62/62 OK, 67.3 s, load 0.12。空 dir と pin が同じ `672007a0…` なので、`dcafb442` からの content dir 切替で参照は変わっていない。
- 補助 (実 DLL なし。再測定ではない): `ref_stub_check.sh` (§2.1)。実行 commit `8680cf44`、wine64 導入済み runner で FAIL=0。

## 2. 既存 e2e への影響 (測定 commit 以降のコード差分)

`vst3host.cpp` の変更は `dcafb442` の 1 commit のみ (WAV 書出と `S2HOST_PITCH` 追加。`S2HOST_PITCH` 未設定時は従来どおり pitch 60、WAV は追加出力のみで既存の summary・ログは変えない)。`dcafb442` 以降の host 配下のコード差分 (`92f88190`: 表記修正と `set -e` 下の終了コード処理、`8680cf44`: content dir の専用化と PATH 優先) は、いずれも `8680cf44` 上の `ref_harness.sh`・`e2e.sh` の実測に含まれる。

```
git diff 8680cf44 HEAD -- tools/targets/serum2/host ':(exclude)*.md'
(出力: 空。測定 commit 以降のコード差分は 0)
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
| wasm 候補 (SR-4 の WAV) との比較 | 受入 4。入力口は `ref_harness.sh <candidate.wav> <class>` で用意済み | #2383 [SR-45] (親: #73) |
| 参照は既定 Init state のみ (ファクトリ preset 未使用) | 「固定 state (preset 1〜数本)」の受入に届かない。Init 合成は preset 未取得時の許容 | #2384 [SR-46] (親: #73) |
| content 付き (installer 全展開) を正の参照にするか | wasm 側が content を読む条件で比べるなら参照条件が変わる。#2383 の比較先に関わる | #2414 [SR-47] (親: #73) |
| C/D 許容閾値は暫定 (ORACLE §7) | ネイティブ FL の golden 待ち。Serum 2 の閾値は本件で再校正していない | ORACLE §7 (既存) |
