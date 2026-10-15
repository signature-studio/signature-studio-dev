# REPORT — [SR-58 #4097] Serum 2 受信 base の支配判定: NODOM 242 件の分類

- 日付: 2026-10-15 / 親: #3237 (SR-49) / 前段: `REPORT_SR49.md` §5 (b-1)・`REPORT_SR43.md` §2
- 範囲: 静的解析のみ。所属関数の中だけを見る (SR-49 と同じ)。支配判定の変更は行わない。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-43・SR-49 と一致)。
- 測定 commit: `5ec9c5a65` (`receiver_this_trace.py` に NODOM 理由の記録を足した commit)。ベースライン: `ddfb27fb4` (SR-49 の測定 commit)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. NODOM 242 件を支配判定の精度の観点で分類し、件数を書く | **達成**。間接 jmp 89・back-edge 79・merge 74 (§2) |
| 2. 支配判定の変更で、偽陰性・偽陽性の件数を書く | **未達 (未着手)**。支配判定そのものは変えていない。正解データが無く、偽陰性・偽陽性は未測定。子 issue へ分割 (§5) |
| 3. 測定 commit と再現手順を書く | **達成** (§4) |
| 4. 変更前後の TSV の件数差を書く | **達成**。既定 TSV は変化 0 件 (md5 同一)。理由別 TSV は 242 件 (§3) |

## 1. 変更 (`receiver_this_trace.py`)

1. `--nodom-tsv <path>` を追加。指定したときだけ、NODOM 候補 (`vptr:NODOM`・`R-nodom`・`vptr-emb:NODOM`) の理由を書く。既定の出力 (`--tsv`) は変えない。
2. 理由 (`nodom_why`):
   - `indirect`: 所属関数に間接 jmp (`jmp [..]`・`jmp reg`) があり、`Fn.dominated` が常に偽を返す。
   - `back-edge`: 定義 `d` が使用 `u` から到達できる (`u` から先の経路で `d` に戻る = ループ)。
   - `merge`: `u` へ `d` を通らない経路がある (分岐の合流で、もう一方の分岐の経路に定義が無い)。
3. 判定の順: `indirect` を先に見て、それ以外で back-edge、残りを merge とする。

限界: 理由は「定義の位置から見た経路の形」の分類で、正しい支配関係を示すものではない。back-edge の 79 件に本当のループ由来でない件が混じる可能性は未確認。

## 2. 分類結果 (strict・NODOM 242 件)

| 理由 | 件数 | 内訳 (`vptr:NODOM` / `R-nodom` / `vptr-emb:NODOM`) |
|---|---|---|
| indirect (間接 jmp を含む関数) | 89 | 0 / 89 / 0 |
| back-edge (定義が使用から到達可能) | 79 | 69 / 9 / 1 |
| merge (使用へ定義を通らない経路あり) | 74 | 63 / 10 / 1 |
| 合計 | 242 | 132 / 108 / 2 |

間接 jmp を含む関数の 89 件は、switch の jump table と見られる `jmp [rax+N]`・`jmp r9` などを含む 54 関数由来 (`REPORT_SR43.md` の 89 件と一致)。jump table の分岐先を読んでいないため、支配を見ず全件 NODOM になる。

## 3. 変更前後の TSV

| 項目 | ベースライン (`ddfb27fb4`) | 測定 (`5ec9c5a65`) | 差 |
|---|---|---|---|
| 既定 TSV md5 | `1e1f5500f43b069330b9e2ba41c75367` | `1e1f5500f43b069330b9e2ba41c75367` | 0 件 (同一) |
| 理由別 TSV 候補数 | (なし) | 242 | +242 |

## 4. 再現手順・実測

```sh
# $S: リポジトリ外の作業用 dir (RUNNER_TEMP 配下)。$P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv trace.tsv --nodom-tsv nodom.tsv
```

- 入力の確認: `Serum2_win64.vst3` の sha256 `501e7bb3…` / 19,236,864 B。
- 決定性: 測定 commit の 3 回の実行で、既定 TSV md5 は全て `1e1f5500…`、理由別 TSV md5 は全て `848be6cf…` で一致。
- 実測 (`5ec9c5a65`・n=3・逐次・並列数 1・nproc=4。load は `/proc/loadavg` の 1 分値):

| 実行 | real (s) | user (s) | sys (s) |
|---|---|---|---|
| 1 | 23.13 | 21.95 | 1.18 |
| 2 | 23.18 | 22.04 | 1.14 |
| 3 | 23.36 | 22.23 | 1.11 |
| min–max | 23.13–23.36 | 21.95–22.23 | 1.11–1.18 |

- load: 測定前 0.06 → 測定後 0.71 (1 分値)。
- 報告前コマンド (`docs/WORKFLOW.md` §6): `git diff 5ec9c5a65 HEAD -- tools/targets/serum2/gui/receiver_this_trace.py` は 0 行 (測定後にコードを変えていない)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (b-1') 支配判定の精度変更と偽陰性・偽陽性の件数 (受入 2)。正解データ (手で確定した支配関係) が無い | 受入 2 | #4433 [SR-70] (本 run で起票) |
| (b-1'') back-edge 79 件のうち、本当のループ由来でない件の確認 | 受入 1 の解釈 | #4433 [SR-70] |
| (b-2) OUTPARAM 59 件の出力引数であることの個別確認 | SR-49 の受入 1 の解釈 | #3236 [SR-48] |
| (b-3) 使用より後に escape するスロット・INDEX・CALLRET・CLOBBER・ENTRY の原因 | SR-49 の受入 1・3 | #3237 に残す |
