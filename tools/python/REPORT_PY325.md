# PY-325 (#4405): 0x72db20 と 0x12acb70 の参照元の静的確定

親: #4346 (PY-320)。前段: `tools/python/REPORT_PY320.md` §3 (未確定)、`tools/python/REPORT_PY268.md` §4。
既知類型との関係: 該当なし (lift 作業ではない。PE の参照走査による解析)。
KPI: 起動・GUI に関わらないため記載不要 (解析のみ)。

## 結論

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. 0x12acb70 を `[Self+0x100]` へ格納する命令と格納値の出どころ | **未達** (子 #4604 に移す) | §2 (`[R+0x100]` への 8 バイト格納は 359 件。未分類) |
| 2. 0x72db20 の呼出し元 (関数と VA) | **未達** (子 #4603 に移す) | §1 (直接 call 0 件・8 バイト参照は VMT スロットのみ。間接呼出し 244 箇所は未分類) |
| 3. 検証 probe 追加。既存 probe が PASS のまま | **達成** | §4 |

## 1. 0x72db20 の参照

- `pe_callgraph.py callers 72db20`: 直接 call (E8) の呼出し元は 0 件。
- 8 バイト絶対参照は 1 件: `0x324f28` (VA `0x725b28` = TQuickMenuItem VMT+0xd0 のスロット)。
- 4 バイト参照は 2 件: 同じ `0x324f28` の下位 4 バイトと、`.pdata` 内 `0x12ce5fc` (RUNTIME_FUNCTION の関数先頭 RVA)。`.pdata` の 1 件は呼出しではない。
- よって 0x72db20 は VMT スロット経由 (`call [reg+0xd0]`) でしか呼ばれない。受入 2 の候補は間接呼出し 244 箇所 (PY-320 §3) に絞られるが、どれが MoveLeftMenu の発火かは未確定。

## 2. 0x12acb70 の参照

- 公開表エントリ 0x12acb70 の値は `.data` 内 `0xe78971` の 8 バイト絶対ポインタ (`0x1279571`)。4 バイト参照も同じ 1 箇所。
- コード中の RIP 相対参照・即値参照は 0 件 (表を経由して読まれる形)。
- `[R+0x100]` へ 8 バイト格納する命令は 359 件 (`work` 上の走査)。このうち 0x12acb70 を入れる箇所は未特定。REPORT_PY268 §3 の推定 (DFM 読込みで TMethod(Code, Data) を生成) は裏付けを得ていない。

## 3. 解釈の限界

- §1 の「0x72db20 は VMT 経由のみ」は直接 call と絶対参照の走査に基づく。レジスタ経由の即値生成 (`lea` + 間接) は走査していない。
- 動的 (実行) による確認は本 run の範囲外。

## 4. 検証

- probe: `tools/python/analysis/flapi/pe_py325_refs.py` (検査 6 件)。
- 測定 commit (コードを変えた最後の commit): `171ef59ad`。
- 実行: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py325_refs.py`。
- 実測 (HEAD `171ef59ad`・素材 fl-win64 の block00031_PE.bin・load 0.10):
  - `pe_py325_refs.py`: real 0.133 秒・終了 0・PASS 6 / FAIL 0。
  - `pe_py320_fire_site.py`: real 42.549 秒・終了 0・PASS 11 / FAIL 0。
  - `pe_py268_rdx.py`: real 42.633 秒・終了 0・件数 22 / 22。

## 5. [PY-347] (#4604) の絞り込み (部分)

- 走査: `analysis/flapi/pe_py347_store_src.py` (`.text` の線形走査)。`[reg+0x100]` への 8 バイト格納 493 件 (`pe_scan_store.py 0x100 qword`)。
- 格納直前 48 バイト以内に `call` があり格納元が rax の箇所: 195 件。
- さらに `[reg+0x108]` (TMethod.Data 相当) への格納が近く (±48 バイト) にある箇所: 105 件。
- その 105 件の直前 call 先の集計 (`pe_py347_store_src.py` の出力): `0x8403e0` 69 件・`0x4133f0` 12 件・`0x8404a0` 7 件・`0x8405f0` 2 件・`0x840520` 2 件・`0x414c70` 2 件・`0x8da350` 1 件 ほか (計 105)。
- 未確定: `0x8403e0` は TMethod 生成関数とは限らない (冒頭は `[rbx+0x78]`・`0x414e70` 比較後に `[rbx+0xc0]` を仮想呼出しする形で、戻り値を返す形ではない)。0x12acb70 の格納元は特定していない。
- 測定 commit (コードを変えた最後の commit): `654dc393d`。`pe_py347_store_src.py` の実測 (HEAD `654dc393d`・load 0.52〜0.78) real 49.2 秒・終了 0・hits 195・narrowed 105。dump は前回測定と一致 (cmp 一致)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x12acb70 の `[Self+0x100]` 格納元 (受入 1) | PY-274 の発火経路が閉じない | #4604 ([PY-347]) |
| 0x72db20 の間接呼出し元 (受入 2) | MoveLeftMenu の発火箇所が未同定 | #4603 ([PY-348]) |
