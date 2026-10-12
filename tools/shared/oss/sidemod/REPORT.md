# oss/sidemod REPORT — FFmpeg / LAME を差し替え可能な side module として再ビルド (LGL-4, #87)

> 正本: `tools/shared/oss/sidemod/REPORT.md`。方針の根拠は `docs/LEGAL.md` §3.2・§6。
> **事実整理であり法的助言ではない。** §6(b)「適切な共有ライブラリ機構」に当たるかは専門家確認事項 (未解決 1)。

## 0. 結論

- FFmpeg n4.4.2 / LAME 3.99.5 を upstream tarball から再ビルドし、`ffmpeg.wasm` / `lame.wasm` (`-sSIDE_MODULE=2`) にした。
  host (`-sMAIN_MODULE=1`、FL 由来コードを含まない) が `dlopen` でロードし、native `.so` 版と同一結果を出す。
- GPL 系の混入検出 (`check_license_flags.py`) を configure **前**・`config.h`・成果物バイト列の 3 点に置いた。
  `--enable-gpl` / `--enable-version3` / `--enable-nonfree` / x264・x265 等を入れると build.sh が configure 前に失敗する。
- 実測値は §4 (コミット済み HEAD で再現した値)。

## 1. 構成

| ファイル | 役割 |
|---|---|
| `build.sh` | upstream 取得 → GPL 検出 → FFmpeg (wasm32 / native 並列) → LAME → side module / host / native 基準 `.so` |
| `ffmpeg_side.c` / `lame_side.c` | side module の公開 ABI。**差し替え境界は `ss_*` 関数のみ** (`ss_abi_version()`=1。AV* / lame 型は外に出さない) |
| `host.c` | `dlopen` ローダ兼テスト。パスを変えるだけで別ビルドの side module に入れ替えられる |
| `check_license_flags.py` | GPL 混入検出 (`selftest` で 18 ケース) |
| `e2e.sh` | build → ロード・動作 → 差し替え → 検出ネガコン |

- FFmpeg の configure は `oss/ffmpeg/build.sh` と同じ最小構成 (decoder flac/mp3/vorbis/pcm_s16le/wmav2/aac 等) + `--enable-pic`、`--disable-programs`。
- LAME は `--disable-decoder` (mpglib = GPL を含めない)、ソース一覧からも `mpglib` を除外。upstream の `COPYING` (LGPL) をそのまま採用。
- LAME wasm は `oss/lame/build.sh` と同じく SSE を落とし、native 基準 `.so` も同じ `config.h` で作るので byte 一致を比較できる。

## 2. 検出する項目 (`check_license_flags.py`)

| 段階 | 検査 |
|---|---|
| configure 前 | FFmpeg 引数に `--enable-{gpl,nonfree,version3,libx264,libx265,libxvid,...}` が無い / LAME 引数に `--disable-decoder` がある |
| configure 後 | `config.h` の `CONFIG_GPL` / `CONFIG_NONFREE` / `CONFIG_VERSION3` が全て 0 |
| 成果物 | `ffmpeg.wasm` 内の configure 文字列と `LGPL version 2.1 or later`、`lame.wasm` に `hip_decode` / `lame_decode` / `mpglib` 系シンボルが無い |

禁止リストは FFmpeg configure の GPL / version3 / nonfree 必須ライブラリを手で転記したもの。**FFmpeg の将来版で増えるオプションは追従しない** (未解決 3)。

## 3. 設計上の注意

- `-sMAIN_MODULE=2` では side module 同士の dlopen が失敗した (`could not load dynamic lib`)。`=1` にした。
- `emsdk_env.sh` は `EMSDK_ENV` を unset するため、emsdk 指定は `SS_EMSDK_ENV` にした (旧名だと事前に source した環境で `set -u` により無出力で rc=1 になる)。
- 本 PoC の host は FL を含まない。FL 側 wasm からこの ABI を呼ぶ結線 (FL 由来 wasm が `ss_*` を呼ぶ経路) は未実施 (未解決 2)。

## 4. 実測
(下記はコミット済み HEAD で `bash tools/shared/oss/sidemod/e2e.sh` を再実行した値)

TODO_MEASURED

## 5. 未解決

| 項目 | 起票先 |
|---|---|
| LGPL-2.1 §6(b) に「side module + dlopen」が当たるか、LGPL §6 の再リンク可能性を wasm でどう満たすかは専門家確認 | #87 コメント (`docs/LEGAL.md` §3.2 と同じ未確定事項) |
| FL 由来 wasm から `ss_*` を呼ぶ結線、および LGL-3 (THIRD_PARTY_NOTICES・ソース提供の記録) との連動 | LGL-3 の issue |
| 禁止フラグ表は手転記。FFmpeg 更新時の追従は人手 | #87 コメント |
| CI (GitHub Actions) への組込み。`.github/workflows` はこの run のスコープ外 (opencode.yaml のみ) | 新規 issue を #87 コメントで提案 |
