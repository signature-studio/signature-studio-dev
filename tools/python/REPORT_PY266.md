# PY-266 (#3890): flag `byte [[[0x15e14a0]]+0x7e0+0x49e]` の書込み元 (PE の .text 全 block の走査)

親: #3627 (PY-223) / 前段: `tools/python/REPORT_PY223.md` (受入 3)。既知類型との関係: 該当なし (PE の逆アセンブル読解と走査。lift 作業ではない)。

## 結論

- **受入 1 (`+0x49e` への書込み命令を全 `.text` で列挙): 達成。** 全 313 PE block (x64 258・i386 55) で、`disp32 = 0x49e` の書込み命令は **24 件** (byte 20・word 3・xmmword 1)。このうち block00031 (FLEngine 本体) は **3 件** (byte)。0x49e を覆う幅の広い書込み (disp 0x497〜0x49d の qword・dword・xmmword など) は全 block で **2569 件** あり、block00031 では 63 件。覆う書込みは「`+0x49e` の値を変えうる」集合で、flag 専用ではない。
- **受入 2 (書込み関数と件数を REPORT に残す): 達成。** 節「書込み関数と件数」。
- **受入 3 (書込み値を関数ごとに 1 行で分類): block00031 は達成、他 PE は部分。** block00031 の 3 件は、(a) 関数 `0x737560` の `dl` (呼出し側の引数) の store 1 件、(b) 関数 `0x128f9e0` の定数 `0` の store 1 件、定数 `1` の store 1 件。他 PE の 21 件は、値の種類 (定数・レジスタ) だけ分類した。どの構造体への書込みかは未確認 (節「他 PE block」)。
- **flag の所有者 (`[[[0x15e14a0]]+0x7e0]`) と書込み対象の一致: 未確定。** 書込み命令の base レジスタを `0x15e14a0` → `+0x7e0` の連鎖まで遡る解析は本 PR では行っていない。`0x15e14a0` の RIP 相対参照は 439 件 (`pe_rip_refs.py`、再測定済み) で、その多くは読出し。
- **受入の判定**: 受入 1・2 は満たす。受入 3 は block00031 の範囲で満たし、他 PE と flag の所有者は未達。よって issue は閉じず `Refs #3890`。
- **製品 KPI (起動・GUI)**: 本 PR は解析スクリプトと REPORT のみで、製品コードを変えない。起動の dispatch 数・通過 unit 数・最初のウィンドウの有無は**動かしていない**。

## 測定

- 測定 commit: `f7ce3a151` (下の「測定の記録」)。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`)。展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C tools/python/work/py266 --wildcards '*_PE.bin'` (3.2 秒・313 block)。展開先は gitignore (`tools/python/work/`)。
- 走査: `analysis/py266_flag_writers.py` (全 PE・`.text` の生バイト列で disp 0x497〜0x49e の 4 byte を探し、直前 15 byte から復号して memory operand の disp が一致する命令だけ採る。線形走査はしない)。所属関数は x64 の `.pdata` (RUNTIME_FUNCTION)。
- 検査 (PASS): `FL_WIN64_DIR=$PWD/work/py266 python3 analysis/py266_flag_writers.py` → rc 0・所要 (下の「測定の記録」)。
- ネガティブコントロール: `--mutate` (既知の書込み `0x737574` `mov byte ptr [rbx+0x49e], dl` の disp の 1 bit を反転したメモリ上の複製で走査) → `mutate PASS at 0x737574` (= その命令が write として出ない)・rc 0。検出器は既知の書込みを落とすことができる。
- `pe_scan_store.py 0x49e byte` (block00031 だけの既存の走査) の結果も一致: 3 件 (`0x737574`・`0x1291829`・`0x1291883`)。

## 書込み関数と件数 (受入 1・2)

`disp=0x49e` の直接書込み (全 PE・24 件):

| block | 件数 | 幅 | 関数 (`.pdata` 所属) | 件数の内訳 |
|---|---|---|---|---|
| block00031 (FLEngine) | 3 | byte | `0x737560`・`0x128f9e0` | 関数 2 件 (`0x737560`: 1・`0x128f9e0`: 2) |
| block24175 | 5 | byte 4・word 1 | `0x64ac90`・`0x64b780`・`0x64ee00`・`0x7523e0` | 関数 4 件 |
| block24414 | 1 | byte (add) | `0x180064fdb` | 1 |
| block24433 | 2 | xmmword 1・word 1 | `0x18157ddb0`・`-` (pdata 外) | 2 |
| block24435 | 1 | word | `0x1800e8ee0` | 1 |
| block24766 | 4 | byte | `0x6a2710`・`0x6a3200`・`0x6a6910` | 3 |
| block24826 | 8 | byte | `0x6aeda0`・`0x6fcaf0`・`0x6fd640`・`0x700fe0`・`0x809bc0`・`0x80d680`・`0x80ffc0` | 7 |

- 直接書込みの「値」の分類は、block00031 の 3 件 (次節) と、他 PE の 21 件 (節「他 PE block の byte 書込み」) に分けた。

## block00031 の書込み値の分類 (受入 3)

| 命令 | 関数 | 書込み値 | 条件 (復号した命令列) | 呼出し元 |
|---|---|---|---|---|
| `0x737574` `mov byte ptr [rbx+0x49e], dl` | `0x737560` (setter) | `dl` (引数) | 直前 `cmp byte ptr [rbx+0x49e], dl`・`je 0x737631` で、既に同値なら書かない (変化時だけ store) | 直接 call 3 件: `0x73d102` in `0x73d0e0`・`0x73d2a2` in `0x73d280`・`0x79fd44` in `0x79fd40` |
| `0x1291829` `mov byte ptr [rbp+0x49e], 0` | `0x128f9e0` | 定数 `0` | 関数先頭の `cmp byte ptr [rbp+0x49f], 0`・`jne 0x1291a79` を通過した経路で 0 を書く (`[rbp+0x49f]` が 0 のとき) | 未調査 |
| `0x1291883` `mov byte ptr [rbp+0x49e], 1` | `0x128f9e0` | 定数 `1` | `mov dword ptr [rbp+0x498], eax` の後、`cmp dword ptr [rbp+0x498], 0`・`je 0x1291a28` の**非 0 の側** (呼出し結果が 0 でないとき) | 未調査 |

setter `0x737560` の呼出し元の詳細:

- `0x73d0e0` (`.pdata` `0x73d0e0`〜`0x73d181`): `mov byte ptr [rbp+0x2f], dl` で受けた引数を `movzx rdx, byte ptr [rbp+0x2f]` で `dl` に渡す。この関数の呼出し元は `0x6f24f0` (直接 call 1 件)。
- `0x6f24f0` (`.pdata` `0x6f24f0`〜`0x6f252e`): `mov esi, edx` で受けた引数 `esi` を、`cmp byte ptr [rbx+0x49e], sil` (既に同値なら何もしない) の後、`mov edx, esi` で `0x73d0e0` に渡す。つまり 0x737560 の `dl` は、`0x6f24f0` の第 2 引数そのもの。
- `0x73d280` (`.pdata` `0x73d280`〜`0x73d321`): 同形。直接呼出し元 0 件 (関数ポインタ・vtable 経由と推定。未確認)。
- `0x79fd40` (`.pdata` `0x79fd40`〜`0x79fd4e`): `sub rsp,0x28`・`call 0x737560` の 14 byte の関数。引数 `dl` は呼出し元で設定されず、このトランポリンの直接呼出し元 0 件。値の出所は未確認。

**`0x79fd44` の所属の訂正**: 前の作業メモでは `func 0x79fd44` が `0x79fb70` を返したが、`.pdata` では `0x79fd44` は `0x79fd40`〜`0x79fd4e` の関数に入る。`pe_callgraph.py func` は int3 パディングの推定で、関数先頭を取り違えた (REPORT_PY223 の「限界」と同じ型)。本 REPORT の所属は `.pdata` を根拠にする。

## 他 PE block の byte 書込み (参考・分類のみ)

block00031 以外の 21 件 (byte 17・word 3・xmmword 1)。disp は同じ 0x49e だが、**これらの PE が FLEngine の同じ構造体を扱うかは未確認**。各 PE は別の ImageBase を持つ (REPORT_PY223 の全 block 走査 (受入 4) の前提)。値の種類:

- 定数の store (11 件): block24175 (3: `0`・`0`・`1`)・block24766 (3: `0`・`1`・`0`)・block24826 (5: `1`・`0`・`1`・`0`・`2`)。
- レジスタの store (byte 6・word 2・xmmword 1 のうち 9 件): block24175 `sil` (byte)・block24414 `add byte ... bh`・block24766 `sil`・block24826 `sil`・`al`・`al`・block24175 `ax` (word)・block24435 `dx` (word)・block24433 xmmword。
- 定数の word store 1 件 (block24433 `mov word ptr [rcx+0x49e], 0`・pdata 外)。

## 限界 (この走査で見えないもの)

1. **base レジスタの由来**: 書込みの base (`rbx`・`rbp`・`rax` 等) が `[[[0x15e14a0]]+0x7e0]` の値かは確定していない。`0x15e14a0` → `+0x7e0` の連鎖を遡らないと、「flag の書込み」か「同じ disp の別フィールド」かは分からない。
2. **計算された base / 間接アドレス**: `lea reg,[base+0x49d]` 等で番地を作り、後で `[reg+1]` に書く経路は、disp 一致では見えない。`addr` (lea) は block00031 で 63 件 (覆う範囲の全 PE では 1145 件) あり、経路の候補として残す。
3. **覆う幅の広い書込み**: 0x49e を含む qword・dword 書込み (2569 件) は、「+0x49e の値を変えうる」集合だが、flag 専用ではない。これらの所属の分類は未実施。
4. **呼出し元の一意性**: `0x737560` の直接呼出し元は 3 件、`0x73d0e0` は 1 件。そこから先の `dl` の源 (0x6f24f0 の呼出し元) は未追跡。
5. **間接呼出し**: `0x73d280`・`0x79fd40` は直接呼出し元 0 件。vtable・関数ポインタ経由の呼出しは静的に解決していない (`REPORT_PY223.md` の vptr 候補の未解決と同じ)。

## 再現

```
cd tools/python
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py266 --wildcards '*_PE.bin'
FL_WIN64_DIR=$PWD/work/py266 python3 analysis/py266_flag_writers.py > work/py266/scan.tsv   # 実測 130.0 秒・rc 0
FL_WIN64_DIR=$PWD/work/py266 python3 analysis/py266_flag_writers.py --mutate               # mutate PASS・rc 0
awk -F'\t' '$3=="disp=0x49e"' work/py266/scan.tsv                                            # 直接書込み 24 件
FL_WIN64_DIR=$PWD/work/py266 python3 analysis/flapi/pe_callgraph.py callers 0x737560         # 直接呼出し元 3 件
```

## 測定の記録

- 測定 commit: `f7ce3a151` (コードを変えた最後の commit。`analysis/py266_flag_writers.py` と本 REPORT を入れた commit)。
- 測定 1 (commit `f7ce3a151`・n=1): `analysis/py266_flag_writers.py` → rc 0・実時間 130.0 秒・user 129.4 秒・負荷 (実行後) `0.94 0.73 0.70`・並列数 1 (4 コア)。出力は `counts {'write': 2569, 'addr': 1145, 'read': 18343, 'rip': 853}`。
- 測定 2 (同 commit・再現・n=2): 出力を測定 1 と `cmp` で比較し一致 (`SAME_OUTPUT`)。実時間 130.0 秒・user 129.4 秒・負荷 `0.32 0.56 0.65` → 実行後 `0.94 0.73 0.70`。
- ネガティブコントロール (commit `f7ce3a151`): `--mutate` → `mutate PASS at 0x737574 rc 0`。
- `git diff f7ce3a151 HEAD -- tools/python/analysis tools/python/REPORT_PY223.md` の出力は本 REPORT の commit 以降で 0 行 (コードの差分は無い)。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[[[0x15e14a0]]+0x7e0]` の連鎖を遡り、block00031 の 3 件の base が flag の所有者かを確定する (受入 3 の残り) | flag の書込みの確定 | #3890 (本 issue の残り・Refs) |
| 0x737560 の `dl` の源 (0x6f24f0 の呼出し元・0x73d280・0x79fd40 の間接呼出し元) | 書込み値の分類の確定 | #3890 (同上) |
| 他 PE block の 21 件が FLEngine の同じ構造体か | 他 block の書込みの扱い | #3890 (同上) |
