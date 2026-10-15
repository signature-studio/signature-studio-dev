# REPORT_PY72 の付録 (#3267): setChannelPitch の仮想メソッド表 (TPublicChannel / TPreviewChannel) の確定

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #3214 (PY-171)・#2576 (PY-77)。本 issue #3267 (PY-177) は受入 1 を達成し、受入 2・3 を子 #3371 (PY-190) へ移送した (issue 本文の範囲を受入 1 に縮めた)。

## 結論

- 受入 1 (達成): `0xffe290` と `0x1001b70` は、Delphi の仮想メソッド表 (VMT) の slot 35 (VMT+0x118) に入っている関数。VMT は `TPublicChannel` (VA `0xfe2cf8`) と `TPreviewChannel` (VA `0xfe2fc8`) で、クラス名は VMT-0x88 が指す ShortString から読んだ。
- 格納元は `.text` 内の静的な VMT。`.rdata` は 0x45 バイトしかなく、VMT は `.text` に置かれている。従来の「`.data` の絶対ポインタ 0 件」は、この配置による。
- 呼出し: `0xffe290`・`0x1001b70` への直接 call は 0 件 (従来どおり)。slot 35 は仮想呼出し `call qword ptr [reg+0x118]` で呼ばれ、disp 0x118 の形の呼出しは `.text` 全体で 151 箇所ある。slot 35 は VMT を持つ全クラスで共有される位置なので、箇所ごとの受け手の型は未確定 (子 #3371)。
- 受入 2・3 は未確定 (子 #3371 へ移送)。`0xfe9090` の直接 call 元は、上の 2 関数 (それぞれ `0xffe29b`・`0x1001b7b`) だけ。一覧 A (`0x15e2218`)・B (`0x15e0128`) の要素型は未確定。TPreviewChannel を生成して格納する大域 `0x16bcae8` は A/B と別の参照元で、A/B との関係は未確定。

## 解析 (PY-177 #3267)

### 1. VMT の確定

検証ツール: `analysis/flapi/pe_vmt_probe.py` (本 PR で追加)。VMT の VA と slot の位置を渡すと、クラス名・slot 番号・関数 VA・VMT 値を持つスロット・それを読む命令・仮想呼出しの箇所数を出す。

| 項目 | TPublicChannel | TPreviewChannel |
|---|---|---|
| VMT (slot 0) | `0xfe2cf8` | `0xfe2fc8` |
| vmtClassName (VMT-0x88 の ShortString) | `0xfe2eae` → `TPublicChannel` (14 字) | `0xfe317e` → `TPreviewChannel` (15 字) |
| slot 35 の位置 (VMT+0x118) | `0xfe2e10` | `0xfe30e0` |
| slot 35 の関数 | `0xffe290` | `0x1001b70` |
| VMT 値を持つ 8 バイトのスロット | `0xfe2c30`・`0xfe2ed8` | `0xfe2f00`・`0xfe31a9` |
| 上のスロットを RIP 相対で読む命令 | 75 件 (`0xfe2c30` 側の型判定・生成を含む) | 4 件 |
| `call qword ptr [reg+0x118]` (仮想呼出し、slot 35) | 151 件 (disp 0x118 の全箇所。VMT に依らない) | 同左 |

- VMT-0x80 の値は `0x8a8` (TPublicChannel) と `0x7d8` (TPreviewChannel)。インスタンスサイズと推定 (未確認)。

### 2. クラス参照スロットの読出し箇所

- `0xfe2c30` の読出し例: `0xfe8e99` が `mov rdx, [0xfe2c30]` の後に `0xfe8ea0` で `call 0x40fe90` を呼ぶ。`0x40fe90` の意味は未確認 (型判定と推定)。
- TPreviewChannel の生成: `0x1190dee` が `mov rcx, [0xfe2f00]`・`mov dl, 1`・`call 0x1001620` (関数 `0x1190d20`) を行い、直後の `0x1190e03` が `mov [rcx+rsi*8], rax` で結果を配列へ格納する。`rcx` は `[0x16bcae8]`。さらに `0x1190e12` で `[rax+0x168] = 1` を書く。
- `0x11c3809` (関数 `0x11c2d80`) も同じ `call 0x1001620` を行い、結果を大域 `[rip+...]` に格納する。
- `0x1001620` の直接 call 元は 2 件 (`0x1190df7`・`0x11c3812`)。
- `0x16bcae8` の参照: 16 件 (lea によるアドレス取得 2 件を含む)、直接の書込み 0 件 (`pe_xref.py 0x16bcae8`)。

### 3. 受入 2・3 の判定 (移送)

- 受入 2 (`0xfe9090` が chan に呼ばれるか): 直接 call 元は VMT slot 35 の 2 関数だけ (`0xffe29b`・`0x1001b7b`。PY-77 #3214 の節で確定済み)。よって `0xfe9090` が chan に呼ばれるのは、slot 35 への仮想呼出し 151 件のうち、受け手が TPublicChannel / TPreviewChannel になるものに限られる。受け手の型は未確定 → #3371。
- 受入 3 (一覧 A/B の要素型): 要素候補は TPreviewChannel (生成と格納は上の 2)。ただし大域 `0x16bcae8` は一覧 A (`0x15e2218`)・B (`0x15e0128`) とは別のスロット。A/B の容器 Q への追加 (`add dword ptr [Q+0x10], 1` の候補が多数ある) の所有者は未確定 → #3371。

### 測定

- 測定 commit: `f13b104c1` (`pe_vmt_probe.py` を追加した commit。コードを変えた最後の commit)。
- 検証 HEAD: `1ff8ee111` (コミット済み・作業ツリー clean。n=3 の測定時点)。後続の docs 修正 `4585eb2e4` でも 2 probe を各 1 回再現し、出力は md5 一致 (TPublicChannel `35b0e0dc`・TPreviewChannel `b0ef6841`)、終了 0。`git diff f13b104c1 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。本付録の commit は `tools/python/REPORT_PY72*.md` と `docs/DOC_MAP.md` だけを変える。
- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-3267 --wildcards '*block00031_PE.bin'` (2.3 秒。`extracted/block00031_PE.bin` に展開。repo 外)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-3267 python3 analysis/flapi/pe_vmt_probe.py <VMT> <slot> --disp 0x118` を同一 HEAD で連続 3 回 (n=3)。終了コードは 6 回すべて 0。出力は 3 回ともバイト単位で同一 (md5 一致)。

| 対象 (`<VMT> <slot>`) | 所要 (n=3・min–max) | load (1 分値・各回の 開始→終了) |
|---|---|---|
| `0xfe2cf8 0xfe2e10` (TPublicChannel) | 8.20–8.36 秒 | 0.94→1.03・1.03→1.19・1.19→1.31 |
| `0xfe2fc8 0xfe30e0` (TPreviewChannel) | 8.27–8.29 秒 | 1.31→1.49・1.49→1.45・1.45→1.38 |

- 所要は負荷では説明できない。load 0.37〜1.49 の範囲で 8.2〜8.6 秒 (本 run の n=3 と、後続の HEAD `4585eb2e4` での 2 回)。レビュアの独立再実行 (load 0.71) では 13.4 秒・13.9 秒で、原因は未確認。秒数は参考値で、性能の主張には使わない。
- 前回の n=1 の値 (load 0.46 での 7.3 秒・7.4 秒) は、上の n=3 の値に置き換えた。
- 補助 (測定対象外・repo 外の一時スクリプト): PE 全体の 8 バイト値 (`0xffe290`・`0x1001b70`・`0xfe9090`) と 4 バイト値 (VA・RVA) の走査。`.text` の 1 件ずつ (VMT slot)、`.pdata` の関数 RVA の 1 件ずつ。

### ネガティブコントロール

同じ HEAD・同じ素材で 1 件ずつ入力を壊し、検査が期待どおりに落ちることを確認した (n=1)。

| 検査 | 入力 | 実測 (終了コード) | 判定 |
|---|---|---|---|
| slot の 8 の倍数検査 | `0xfe2cf8 0xfe2e11` | `slot 0xfe2e11: not a slot of this VMT` (0) | slot として扱わない |
| 誤った VMT (VMT-8) | `0xfe2cf0 0xfe2e10` | vmtClassName のポインタが `0x0` で `ValueError: 0x0 is not in a file-backed section` (1) | クラス名を読めない |
| 誤った VMT (値スロット) | `0xfe2c30 0xfe2e10` | `ValueError: 0x74c0000 is not in a file-backed section` (1) | クラス名を読めない |
| 使われない disp | `0xfe2cf8 --disp 0x119` | `call [reg + 0x119] (virtual slot 35): 0` (0) | 0 件 |

- 注: `--disp 0x119` の表示ラベル「virtual slot 35」は `disp // 8` の表示で、8 の倍数でない disp では意味を持たない。件数 0 の判定には影響しない。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 仮想呼出し `call [reg+0x118]` 151 件の受け手の型 | 受入 2 (`0xfe9090` が chan に呼ばれるか) | #3371 (PY-190) |
| 一覧 A・B の容器 Q への要素追加箇所と要素型 T | 受入 3 | #3371 (PY-190) |
| 大域 `0x16bcae8` (TPreviewChannel の配列) の役割と A/B との関係 | 受入 3 | #3371 (PY-190) |
| `0x40fe90` の意味 (クラス参照を取る型判定と推定) | 型判定の解釈 | #3371 (PY-190) |
