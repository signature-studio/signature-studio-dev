# PY-63 (#2030): chan 上で +0x794 を書く箇所の特定 (部分・未達)

親: #1973 (PY-58)・#1916 (PY-55)。前段: `REPORT_PY58.md`・`REPORT_PY55.md`。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 受入条件 1 (chan 上で `+0x794` を書く箇所を特定) は**未達**。chan 系フィールドと同一関数で `+0x794` を書く箇所は、この run でも見つからなかった。
- 受入条件 2 (未確定 4 件と保留 1 件の対象確定) は**一部達成**。
  - `0xffe370`: 直接の `call`・`jmp` は無い。絶対アドレス `0xfe2e98` (`.text` 内の関数ポインタ表) に格納されている。間接呼出し経由で、chan との関係は未確定。
  - `0x1306dbf`: 逆アセンブルが命令境界を外している (データ域を読んだ)。対象は未確定。
  - `0x130760f`: `rax` は `[rip+0x667591]` の global ポインタ。`0x130f1e0`・`0x130fab0` の後で `[rax+0x794]` に `r14` を書く。対象型は未同定。
  - `0xec60ae`: `[rbp+0x120]` 上 (`cmp [rax+0x7e0],1` の分岐内)。直前に `+0x79c` (dword) を書く。`[rip+0x71ae44]` の dword 値を格納するもので、対象の型は未同定。
  - `0x8ed012`: `[rbp+0x70]` の初期化関数内で、`+0x714`・`+0x718` と同関数。`[rbp+0x70]` が chan かどうかは未確定。
- 判断保留の `0x8ed012` は、chan 系の初期化経路かどうかを本 run では決められなかった。

## 測定条件

- 素材: `$HOME/artifacts/fl-win64.tar.zst` → `extracted/block00031_PE.bin` (`tar --zstd -xf ... --wildcards '*block00031_PE.bin'`、実測 2.9 秒、wall)。展開先は `tools/python/work/py58/` (gitignore)。PE サイズ 22,227,016 bytes。
- 逆アセンブル: `tools/python/analysis/py58_context.py` (PY-58 の既存スクリプトを無変更で使用)。`capstone` / `pefile` は利用可能。
- 参照検索: `tools/python/analysis/py63_refs.py` (本 PR で追加)。rel32 の直接 call/jmp と、8 バイト絶対アドレスの出現を検索する。
- 注意: ファイル先頭の `ImageBase` は `0x400000` と読めたが、本 run では VA と絶対アドレスの対応を確定できなかった。vtable の先頭を特定するための RIP 相対参照検索は 0 件で、vtable 範囲の同定は保留した。`0xfe2e98` の値 `0xffe370` は、`.text` の 8 バイト列から直接読んだ値である。
- 測定 commit: 本 PR の commit (コードを変えた最後の commit)。基点は `6f144c45` (origin/main)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| chan 上で `+0x794` を書く箇所 | `pairedChanIndex` の由来が決まらない | #1973 (PY-58) |
| `0xffe370` の vtable 範囲と所属クラス (`0xfe2e98` の表の先頭特定。ImageBase 対応の確認が要る) | 間接呼出しの呼出し元が未特定 | #2030 (本 issue の残り) |
| `0x1306dbf` の対象 (逆アセンブルの命令境界が外れている) | 書込み対象が未確定 | #2030 (本 issue の残り) |
| `0x130760f`・`0xec60ae` の対象型 | chan 以外と確定できない | #2030 (本 issue の残り) |
