# REPORT_5923 — fl-win64 素材からの FLEngine 実体の抽出 (PLG-P0b-68・#5923)

親 #5871 (受入 2: FLEngine 実行中の `0x132ee00` 呼出し時 rcx) の前提。FLEngine の実体 (PE) が素材に
あるかを確定し、一覧を記録する。

## 結論

- `fl-win64` 素材に **FLEngine の実体 `FLEngine_x64.dll` は入っている** (前 run の「インストーラ 1 本のみ」は誤り)。
- 素材の中身は、インストーラ `flstudio_win64_26.1.7.5653.exe` (1,106,033,456 B) と、NSIS payload を
  切り出した `extracted/` 配下の block 25,166 件 (PE 313 件・DATA/RIFF/ZIP 等)。
- `FLEngine_x64.dll` は PE32+ x86-64 DLL で、`block00031_PE.bin` (22,227,016 B)。export は
  `CreateFruityInstance` / `__dbk_fcall_wrapper` / `dbkFCallWrapperAddr` の 3 件。
- 同じ export 名を持つ PE は他に無い。

## 展開手段の選定

- 採用: **素材の `extracted/` をそのまま使う** (展開不要)。tar を `tar --zstd -xf` で展開 (約 14 秒・展開先 2.3GB)。
  NSIS payload の再展開は不要。素材の block 切り出しは `[WIN64]` (`tools/nsis_extract.py`) が済ませている。
- 不採用: NSIS の専用ツール・runner での FL Studio インストール。素材に既に切り出し済みの実体があり、
  インストール・wine 実行は受入 1 の範囲外。

## 一覧 (実測)

測定: `bash tools/plugins/framework/hostshim/hs_flengine_list.sh` (`work/flengine/pe_list.tsv`・gitignore 対象)。

| 項目 | 値 |
|---|---|
| 測定 commit | (下記 §検証) |
| PE block 件数 | 313 (合計 1,262,116,832 B) |
| `FLEngine_x64.dll` | `block00031_PE.bin` / 22,227,016 B / sha256 `b2c64da40921cf262c15c5b25c2b0422e4d1851e953c87e0bc38ed2c19f9496d` / export 3 件 |

FL 系の関連 DLL (同じ `extracted/` の PE・export 名で確認):

| block | module (export 名) | 大きさ (B) | sha256 |
|---|---|---|---|
| `block23609_PE.bin` | `engineV2_x64.dll` (`CreatePlugInstance`・`FLEX2Dispatcher`) | 8,119,808 | `e4755e14…c0c86` |
| `block23610_PE.bin` | `engine_x64.dll` (`CreatePlugInstance`・`DispatchToEngine`) | 5,673,984 | `a45f66f3…572a` |
| `block25162_PE.bin` | (export 無し・Nullsoft 自己展開 PE) | 4,128,008 | `dbd57a24…4a06d` |

※ `block23609`・`block23610` は FLEngine ではない別 engine DLL。

## 未確定・未検証

- `extracted/` の block と NSIS 内のファイル名・配置先の対応 (manifest) は素材に無い。
  block → 配置パスの確定は未了 (`tools/assets/REPORT.md` の `mk_manifest.py` 経路が近い)。
- FLEngine を実行してはいない。`0x132ee00` の rcx 採取 (#5871 受入 2) は未着手。
- 製品 KPI (FLEngine 起動 dispatch 数・通過 unit 数・最初のウィンドウ): 動かしていない。

## 検証

- 再現: `bash tools/plugins/framework/hostshim/hs_flengine_list.sh` (素材 `fl-win64` (`$ARTIFACTS_DIR/fl-win64.tar.zst`) が必要)。
