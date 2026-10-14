# REPORT — [SR-5 #73] Serum 2 参照音源との dB 誤差ハーネス (参照は wine64 で生成)

- 日付: 2026-10-14 / 測定 commit: `dcafb442` (コードを変えた最後の commit)
- 再現: `bash tools/targets/serum2/host/ref_harness.sh` (参照生成 → 決定性 → self-test → ネガコン)。wasm 候補は第 1 引数。
- 入力: 実 `Serum2_win64.vst3` sha256 `501e7bb3…5283` (plugins-serum2 から 7z 展開、無改変 unpatched)。wine64 9.0 (apt `wine`)、mingw-w64 (apt)。

## 0. 結論

1. **参照レンダラ**: `ref_render.sh` で実 DLL を wine64 上から駆動し、32-bit float WAV を書く (`vst3host.cpp` に WAV 書出と `S2HOST_PITCH` を追加)。既定 state (Init)・48 kHz・128 frames・64 blocks・NoteOn C4 (block 0) / NoteOff (block 24)。WAV 本体は `work/` (gitignore)、commit は `ref_manifest.json` (sha256・基本メトリクス・再生成コマンド) のみ。
2. **再現性**: 同一入力 3 回で WAV ファイル全体の SHA-256 が一致 (`672007a0…`、data 部 `7adcbc28…`)。ORACLE T2 を満たした。許容クラス D の反映は不要。
3. **ハーネス**: 判定は `tools/flp` の `judgeWav` (`cli/wavcmp.ts`) を `bun` で呼ぶ (runner の Node は 22 で `.ts` の type-stripping が使えないため)。
4. **ネガコン (両方 FAIL)**: 別ノート C#4 を D-spectral で FAIL (rmsDiff 3.4 dB・STFT 4086/4102 bin が >0.1 dB・LUFS 差 0.438)。1 サンプル (+0.01) 改変を A-exact で FAIL (maxUlp 671089)。
5. **未達 (受入 4)**: wasm 側との比較は SR-4 の WAV が無いため未実施。入力口 (第 1 引数) までを作った。残りは子 issue に移した (§3)。

## 1. 実測

| 項目 | 値 |
|---|---|
| ref 3 回の file SHA-256 (`sha256_file`) | 一致 `672007a06d1482ada6f846ec8f5e8a763a2586e032dbabe5fb5432332bd332c1` (data 部 `sha256_data` = `7adcbc28…81fce`) |
| self-test (ref_1 vs ref_2, A-exact) | PASS (bit-exact) |
| ネガコン 別ノート (D-spectral) | FAIL |
| ネガコン 1 サンプル改変 (A-exact) | FAIL |
| ref メトリクス | peak 0.790915 / rms 0.310052 / 非ゼロ 16,380/16,384 cell |
| `ref_harness.sh` (測定 commit `dcafb442`) | NG=0, 13.6 s, load 0.33 (開始時 1 分値) |
| 既存 `e2e.sh` (測定 commit `dcafb442`) | 62/62 OK, 67.3 s, load 0.12 (開始時 1 分値), NC1/NC2 とも期待どおり |
| `84e411e7` 上の再測定 (ref_harness / e2e) | 未実施 (素材 `plugins-serum2`・`apt-mingw` が本 run に無い)。§2 参照 |

## 2. 既存 e2e への影響 (測定 commit 以降のコード差分)

`vst3host.cpp` の変更は `dcafb442` の 1 commit のみ。測定 commit 以降の host 配下のコード差分は以下 (`92f88190` で追加: 表記修正と `set -e` 下の終了コード処理)。

```
git diff dcafb442 HEAD -- tools/targets/serum2/host ':(exclude)*.md'
  ref_harness.sh   : 表示文言 data → file SHA-256 (1 行)
  ref_manifest.json / ref_manifest.py : runner 表記 (repo 外の wine64 絶対パス) → `wine64 (apt wine 9.0)` (1 行ずつ)
  ref_render.sh    : wine 実行を `|| RC=$?` に変更 (RC=0 を先置き)
```

この差分は実行経路を変えるため、`92f88190` 上での再測定が必要。ただし本 run では `wine64` と `plugins-serum2` (実 DLL) が無く、`ref_harness.sh` と `e2e.sh` を再実行できなかった。上の表の数値は `dcafb442` 時点の実測であり、`92f88190` の実測ではない。`bash -n` による構文確認のみ `92f88190` で実施 (OK)。再測定は素材 `plugins-serum2` を依頼に追加して行う (未解決 #3)。

`S2HOST_PITCH` 未設定時は従来どおり pitch 60、WAV は追加出力のみで既存の summary・ログは変えない。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 候補 (SR-4 の WAV) との比較 | 受入 4。入力口は `ref_harness.sh <candidate.wav> <class>` で用意済み | #2383 [SR-45] (親: #73) |
| 参照は既定 Init state のみ (ファクトリ preset 未使用) | 「固定 state (preset 1〜数本)」の受入に届かない。Init 合成は preset 未取得時の許容 | #2384 [SR-46] (親: #73) |
| C/D 許容閾値は暫定 (ORACLE §7) | ネイティブ FL の golden 待ち。Serum 2 の閾値は本件で再校正していない | ORACLE §7 (既存) |
| `92f88190` 上の再測定 (ref_harness / e2e) | 測定 commit `dcafb442` 以降に実行経路を変える差分あり。本 run では素材 `plugins-serum2` が無く未実施 | 本 PR で `oc_artifacts: fl-win64 plugins-serum2` を付けて再起動 (起票先: PR #2385) |
