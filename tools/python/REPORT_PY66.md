# PY-66 (#2078): chan 上で +0x794 を書く箇所の特定 (部分・未達)

親: #2030 (PY-63)・#1973 (PY-58)・#1916 (PY-55)。前段: `REPORT_PY63.md`・`REPORT_PY58.md`。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 受入条件 1 (chan 上で `+0x794` を書く箇所の特定) は**未達**。chan 上の書込み元は未特定。
- 受入条件 2 (`0xffe370` の vtable 範囲と所属クラス) は**一部達成**。`0xfe2e98` の表は 2 エントリ (`0xffe370`・`0xffa930`) を確認。`.text` 内の RIP 相対参照は 0 件。所属クラスは未確定。
- 受入条件 3 (`0x1306dbf` の対象確定) は**一部達成**。命令境界は正しい。書込み先は RIP 相対 global `0x196eba0` (`.bss`) が指すオブジェクトの `+0x794`。このオブジェクトの型は未確定。
- 受入条件 4 (`0x130760f`・`0xec60ae` の対象型) は**未達**。`0x130760f` も同じ global `0x196eba0` が指すオブジェクトへの `+0x794` 書込みと分かったが、型は未確定。`0xec60ae` は未着手。
- 新規: `0x1306dbf` と `0x130760f` は同一 global `0x196eba0` を経由する。このグローバルは `.bss` で、`.text` 内に直接の store は無く (読出し・比較のみ 64 件)、書込み元は未特定。
- `0x8ed012` は未着手。

## 測定条件

- 測定 commit: `308f16af` (`tools/python/analysis/py66_riprefs.py` の追加。この commit 以後にコードは変えていない)。基点は `6a88bf35` (origin/main)。
- 差分 (測定 commit から HEAD まで、コード範囲 `tools/python/analysis`・`tools/python/src`): **0 行** (証跡は下記「差分 0 の証跡」)。
- 素材: `[WIN64]` (`docs/REFERENCES.md`) の `extracted/block00031_PE.bin`。`tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C tools/python/work/py66 --wildcards '*block00031_PE.bin'` で展開。展開先 `tools/python/work/py66/` は gitignore。展開時間は n=3 で 2.27 / 2.24 / 2.24 秒 (wall)。
- PE (`pefile`, fast_load): ImageBase `0x400000`。`.text` VA `0x401000`・RawPtr `0x400`・RawSize `0xfa3600`。`.data` VA `0x13a5000`。`.bss` VA `0x15e6000`。
- VA → file offset (`.text` 内): `0xfe2e98` → `0xbe2298`。その位置の 8 バイトは `0xffe370`、次の 8 バイトは `0xffa930`。

### 再現コマンド

```sh
cd tools/python
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py66 --wildcards '*block00031_PE.bin'
P=work/py66/extracted/block00031_PE.bin
python3 analysis/py55_fieldwrites.py $P 0x794          # 書込み候補 20 件 (実測 0.14 秒、PY-58 と一致)
python3 analysis/py58_context.py $P 0x1306dbf,0x130760f 0x60 0x40
python3 analysis/py66_riprefs.py $P 0x196eba0:8 0xfe2e98:16   # 実測 n=3: 59.71〜60.40 秒 (wall)
python3 analysis/py66_riprefs.py $P 0x12345678:8              # ネガティブコントロール: 0 件
```

### 測定環境 (全走査・展開の n=3)

- `nproc` = 4。測定前後の load average (1 分値): 0.52→1.13 (run1)、1.13→1.10 (run2)、1.10→1.22 (run3)。他プロセスは並列に走らせていない (逐次実行)。
- 全走査 `py66_riprefs.py $P 0x196eba0:8 0xfe2e98:16` (wall / user): run1 59.93 / 59.90、run2 60.40 / 60.37、run3 59.71 / 59.68。**min–max 59.71〜60.40 秒**。3 回の出力は `cmp` で一致 (64 行)。
- 参考: レビュー側の独立再実行では 55.25 秒 (user 55.2 秒・同一 runner)。本測定 (60 秒前後) と約 5 秒の差があり、runner の負荷差と考える。どちらも 1 分前後で、以前の 75 秒は 1 回測定の値のため採らない。
- 展開 `tar --zstd -xf` (`fl-win64` から `block00031_PE.bin` のみ): n=3 で 2.27 / 2.24 / 2.24 秒 (wall)。

### 差分 0 の証跡

測定 commit `308f16af` から HEAD (`e9448aaf` 時点) までの、解析コードの差分:

```
$ git diff 308f16af HEAD -- tools/python/analysis tools/python/src
(出力 0 行・exit 0)
```

- この証跡の後に追加する commit は REPORT・PR 本文のみ (`tools/python/REPORT_PY66.md`・`docs/DOC_MAP.md`)。コード範囲の差分は依然 0 行。

### 検証 (ネガティブコントロール・正例)

| 項目 | 内容 | 結果 |
|---|---|---|
| 負例 | `0x12345678` は RIP 相対参照 0 件 | PASS (0 件) |
| 正例 | `0x196eba0` の参照に `0x1306db8` (既知の load) が含まれる | PASS (1 件) |
| 再現 | `py55_fieldwrites.py` の `+0x794` 書込み候補が PY-58 の 20 件と一致 | PASS |

### `py66_riprefs.py` の測定 (測定 commit `308f16af`)

- `0x196eba0` (8 バイト): RIP 相対参照 64 件。store は 0 件 (`mov qword ptr [rip+..], reg` なし)。読出し・比較のみ。
- `0xfe2e98` (16 バイト): RIP 相対参照 0 件。

## 1. 受入条件 3・4 の詳細

| 命令 | 命令境界 | 対象 |
|---|---|---|
| `0x1306dbf` `mov qword [rcx+0x794],rax` | 正しい (`py58_context.py` で確認) | `rcx = [rip+0x667de1]` = `0x196eba0` |
| `0x130760f` `mov qword [rax+0x794],r14` | 正しい | `rax = [rip+0x667591]` = `0x196eba0` |

直前の `0x1306db8`・`0x1307608` の load はどちらも `0x196eba0` を読む。

## 2. 未確定

| 未解決 | 影響 | 起票先 |
|---|---|---|
| chan 上で `+0x794` を書く箇所 | `pairedChanIndex` の由来が決まらない。書込み先の global `0x196eba0` の型と書込み元が未特定 | #2159 (PY-67) |
| `0x196eba0` (`.bss`) の書込み元 | `.text` 内に直接の store が無い。間接 (関数経由の代入・`lea` 経由) の可能性 | #2159 (PY-67) |
| `0xffe370` の所属クラス・呼出し元 | 間接呼出しの経路が未特定。`0xfe2e98` を指す RIP 相対参照は 0 件 | #2159 (PY-67) |
| `0xec60ae` の対象型 | chan 以外と確定できない | #2159 (PY-67) |
| `0x8ed012` の `[rbp+0x70]` が chan か | 判断保留 | #2159 (PY-67) |

## 3. 次の手順 (提案)

- `0x196eba0` の書込み元を、`.bss` へのアドレス計算 (`lea` + 間接書込み) と関数ポインタ経由で探す。
- `0xfe2e98` の表が `.text` 内にある理由 (定数表か) を確認し、`0xffe370` の呼出し元を表の参照経路から特定する。
- `0xec60ae`・`0x8ed012` の対象を、同じ手順で確定する。
