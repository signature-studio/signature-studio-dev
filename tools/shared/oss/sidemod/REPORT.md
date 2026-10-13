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
| `ci_detect.sh` | 検出テストだけを emsdk・ネットワーク無しで実行 (Actions の `gpl-guard` ジョブ用。#309)。workflow 本体は `detect-tests.workflow.yaml` (配置待ち、§5)。陽性 + 禁止表全件のネガコン + 検出器自身のネガコン。期待 rc を厳密比較 |

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
検証対象コミット 9935a07 (`work/build/sidemod` と `work/tmp` を削除した状態から再実行)。環境: GitHub Actions runner, nproc=4, emsdk 6.0.12。

| 項目 | 実測 |
|---|---|
| `e2e.sh` (build 込み) | **rc=0 / ALL PASS / 88 s** (loadavg 終了時 2.49 2.16 1.25) |
| side module サイズ | ffmpeg.wasm 872,830 B / lame.wasm 144,541 B / host.wasm 581,072 B |
| ロード | ffmpeg.wasm abi=1 license=`LGPL version 2.1 or later` / lame.wasm abi=1 version=3.99.5 |
| LAME 出力 | 16,181 B, stream hash `18dd8a4a4c91ee23` (native `.so` と一致、MP3 バイト列も `cmp` 一致。`oss/lame/build.sh` の §10.2 値と同じ) |
| FFmpeg 復号 | pcm_s16le 22050 samples `9249b2e1bb6ce0b2` / mp3 (LAME 出力) 39168 samples `1d45943fec1748ca` (native と一致。`oss/ffmpeg/build.sh` の値と同じ) |
| 差し替え | 別パスにコピーした side module で同一結果。存在しないパスは dlopen 失敗 rc!=0 |
| side module の import | `env` / `GOT.mem` / `GOT.func` のみ |
| 検出 selftest | 18/18 |
| 検出ネガコン | `--enable-gpl` / `--enable-version3` / `--enable-nonfree` / `--enable-libx264` / `--enable-libx265` / LAME `--disable-decoder` 欠落 / `CONFIG_GPL=1` を単体で検出。`build.sh` に `FF_EXTRA_ARGS=--enable-gpl` と `--enable-version3` を注入すると configure 前に失敗 (全 9 件 CAUGHT) |

所要時間は 1 回の単発値 (build 込み)。ネガコンの 2 回の build.sh 失敗は configure 前なので時間にほぼ影響しない。

### 4.1 `ci_detect.sh` (#309、検証起点 d7d847f、ローカル runner nproc=4)

| 項目 | 実測 |
|---|---|
| クリーン HEAD | **rc=0 / ALL PASS / PASS 65 件 (うちネガコン 54 件) / 2 s** (loadavg 0.05 0.15 0.08)。ネガコン = rc=1 かつ `GPL-GUARD FAIL` 出力を要求、引数誤り rc=2 は検出と数えない |
| 再検証 (REPORT 見出し修正後、コミット 60bfe17。検出スクリプト・検出器は d7d847f から無変更) | **rc=0 / ALL PASS / PASS 65 件 (うちネガコン 54 件) / 2 s** (loadavg 0.41 0.24 0.12、nproc 4) |
| ネガコン (build.sh の FF_ARGS に `--enable-gpl` を実際に書き込んだ作業ツリー) | **rc=1 / FAILED** (`build.sh の実引数` と `GPL-GUARD OK 出力` の 2 件が FAIL)。戻すと rc=0 |
| 検出器自身の変異 | 禁止表から gpl/nonfree/version3 を抜く / `check_config` が常に空を返す、のどちらも selftest rc=1 を `ci_detect.sh` が CAUGHT |
| Actions 上の実測 | **未実施** (§5 の workflow 配置待ち) |

## 5. 未解決

| 項目 | 起票先 |
|---|---|
| LGPL-2.1 §6(b) に「side module + dlopen」が当たるか、LGPL §6 の再リンク可能性を wasm でどう満たすかは専門家確認 | #87 コメント (`docs/LEGAL.md` §3.2 と同じ未確定事項) |
| FL 由来 wasm から `ss_*` を呼ぶ結線、および LGL-3 (THIRD_PARTY_NOTICES・ソース提供の記録) との連動 | LGL-3 の issue |
| 禁止フラグ表は手転記。FFmpeg 更新時の追従は人手 | #87 コメント |
| `detect-tests.workflow.yaml` を `.github/workflows/detect-tests.yaml` に置く作業 (App に `workflows` 権限が無く push 拒否された)。置くまで CI ジョブは未稼働・Actions 上のネガコン未実測 | [CI-6] #309 (open のまま) |
| e2e.sh (build 込み・emsdk 要) は CI 未配線 | 必要なら #309 にコメント |
