# PY-63 (#2030): chan 上で +0x794 を書く箇所の特定 (部分・未達)

親: #1973 (PY-58)・#1916 (PY-55)。前段: `REPORT_PY58.md`・`REPORT_PY55.md`。既知類型との関係: 該当なし (lift 作業ではない)。
残りは子 #2078 (PY-66) へ移管。

## 結論

- 受入条件 1 (chan 上で `+0x794` を書く箇所の特定) は**未達**。移管先 #2078。
- 受入条件 2 の一部: `0xffe370` の呼出し形態を確定した。直接の `call`・`jmp` は無く、`.data` ではなく `.text` 内 file offset `0xbe2298` に、VA `0xfe2e98` を指す 8 バイトの格納値 `0xffe370` がある (表の要素。間接呼出し経路)。chan との関係は未確定。
- 他の候補 (`0x1306dbf`・`0x130760f`・`0xec60ae`・`0x8ed012`) の対象確定は #2078 へ移管。

## 測定条件

- 測定 commit: `ee087e2b` (`analysis/py63_refs.py` の出力件数追加と `analysis/py63_negctl.py` の追加。この commit 以後にコードは変えていない)。
  基点は `6f144c45` (origin/main)。
- 差分 (測定 commit から HEAD まで、コード範囲 `tools/python`): 下記 `git diff` の出力を参照。
- 素材: `[WIN64]` (`docs/REFERENCES.md`) の `extracted/block00031_PE.bin`。取得は `$HOME/artifacts/fl-win64.tar.zst` (R2 由来の `oc_artifacts: fl-win64`) から
  `tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C tools/python/work/py63 --wildcards '*block00031_PE.bin'`。実測 2.81 秒 (wall)、load は未計測。
  展開先 `tools/python/work/py63/` は gitignore。
- PE 実測 (`pefile`, fast_load): ファイルサイズ 22,227,016 bytes、ImageBase `0x400000`。
  `.text` は VA `0x1000`・RawPtr `0x400`・RawSize 16,397,824。`.data` は VA `0xfa5000`・RawPtr `0xfa3a00`。
  ImageBase は `pefile` の `OPTIONAL_HEADER.ImageBase` の読み値 (手読みではない)。
- VA → file offset 変換式 (`.text` 内): `file_off = VA − 0x400000 − 0x1000 + 0x400`。
  `0xfe2e98` → `0xbe2298`。その位置の 8 バイトは `0xffe370` (`py63_refs.py` の abs64 出力と一致)。
- 逆アセンブル: `tools/python/analysis/py58_context.py` (PY-58 の既存スクリプトを無変更で使用)。
- 参照検索: `tools/python/analysis/py63_refs.py`。rel32 の直接 `E8`/`E9` と 8 バイト絶対アドレスの検索のみ。**RIP 相対の検索は未実装**。

### 再現コマンド

```sh
cd tools/python
tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C work/py63 --wildcards '*block00031_PE.bin'
P=work/py63/extracted/block00031_PE.bin
python3 analysis/py63_refs.py $P 0xffe370     # rel32 none / abs64 total=1 (格納位置 file_off=0xbe2298)
python3 -c "import struct,sys; d=open('$P','rb').read(); print(hex(struct.unpack_from('<Q',d,0xfe2e98-0x400000-0x1000+0x400)[0]))"   # 0xffe370
python3 analysis/py63_negctl.py $P             # ネガティブコントロール (C1〜C4)
```

### ネガティブコントロール (`analysis/py63_negctl.py`, 測定 commit `ee087e2b`)

| 項目 | 内容 | 結果 |
|---|---|---|
| C1 正例 rel32 | 既知の call `0x41430c` → `0x4130c0` が検出される | PASS (rel32 候補 13 件) |
| C2 負例 | `0x12345678` は rel32 0 件・abs64 0 件 | PASS |
| C3 正例 abs64 | `.data` の格納位置 `0xfa3a70` (値 `0x40a120`) が検出され、総数 1 件 | PASS |
| C4 改変 | C1 の VA を +4 にずらすと `0x41430c` が消える | PASS |

全体: `ALL PASS` (実行時間 6.05 秒 wall)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| chan 上で `+0x794` を書く箇所 | `pairedChanIndex` の由来が決まらない | #2078 (PY-66) |
| `0xffe370` を指す関数ポインタ表 (VA `0xfe2e98` の表の先頭・範囲・所属クラス) | 間接呼出しの呼出し元が未特定。RIP 相対の参照検索が未実装 | #2078 (PY-66) |
| `0x1306dbf` の対象 (逆アセンブルの命令境界が外れている) | 書込み対象が未確定 | #2078 (PY-66) |
| `0x130760f`・`0xec60ae` の対象型 | chan 以外と確定できない | #2078 (PY-66) |
| `0x8ed012` の `[rbp+0x70]` が chan かどうか | 判断保留 | #2078 (PY-66) |
