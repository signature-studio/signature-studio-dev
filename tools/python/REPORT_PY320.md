# PY-320 (#4346): 公開表 0x12acb70 (MoveLeftMenuClick) を呼ぶ箇所と rdx (Sender) の出どころ

親: #3937 (PY-274)。前段: `tools/python/REPORT_PY268.md` §4 (発火側は未同定)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと参照走査による解析)。
KPI: 起動・GUI に関わらないため記載不要 (解析のみ)。

## 結論

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. 0x12acb70 を TMethod(Code, Data) として呼ぶ箇所 (関数と VA) と rdx の出どころ | **部分達成**。呼出し箇所は確定 (§1)。rdx = Self (`rbx`) は確定 (§2)。0x12acb70 がその枝で実際に `[Self+0x100]` に入ることは**未確定** (静的な推定) | §1・§2・§4 |
| 2. 検証 probe を追加し、既存 probe が PASS のまま | probe `pe_py320_fire_site.py` 追加 (11 件 PASS)。`pe_py268_rdx.py` 22/22 PASS (測定 §5) | §5 |

`pe_py274_dispatch.py` と `REPORT_PY274.md` は main に存在しないため、既存 probe としては照合できなかった (issue 本文の前提と不一致)。

## 0. 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf ... -C <展開先> --wildcards '*block00031_PE.bin'` で展開 (1.6 秒)。`FL_WIN64_DIR=<展開先>`。
- 検証起点: origin/main `267ee2069`。
- VMT: TMenuItem = 0x838c10 (自己ポインタ + classname "TMenuItem" の照合で 1 件)、TQuickMenuItem = 0x725a58 (同)。

## 1. 呼出し箇所 (受入 1 の前半)

- 仮想スロット 0xd0: TMenuItem (0x838c10+0xd0) = `0x840b50`。TQuickMenuItem (0x725a58+0xd0) = `0x72db20` (TMenuItem のスロットを上書きする関数)。
- `0x72db20` は `mov rcx, rbx` (Self) で `call 0x840b50` する (`0x72db3d`)。`0x840b50` への直接 call はこの 1 箇所だけ。
- `0x840b50` 内で `call qword ptr [rbx + 0x100]` (Code) を `rcx = [rbx + 0x108]` (Data)、`rdx = rbx` (Self) で呼ぶ箇所は 2 件: **`0x840be8`** (`cmp [rbx+0x81]` 系の分岐の後) と **`0x840c2e`** (`[rbx+0x8c]` が無い枝)。
- 同形の箇所は関数外に 5 件あるが、関数の範囲 (0x840b50〜0x840c3a) で絞った。`0x840cd0` は `[rbx+0xf0]` (Code) を `rdx = rbx` で呼ぶ別の枝 (`0x840d1b`)。

## 2. rdx の出どころ (受入 1 の後半)

- `0x840b50` 入口の `mov rbx, rcx` (Self) で保持し、`0x840be8`・`0x840c2e` の直前 8 命令内の `rdx` 設定は `mov rdx, rbx` のみ。
- よって rdx (第 2 引数) = **Self** (`0x840b50` の rcx = 呼出し元の rbx)。Self は `0x72db20` で `rbx = rcx` の `TQuickMenuItem` インスタンスとみられる。
- 対照: `0x840be8` と `0x840c2e` の 0x12acb70 への到達は、`[rbx+0x100]` が 0x12acb70 の値を持つことを要する。その値の書込み先は未確認。

## 3. 未確定 → #4656 [PY-351] (起票先。PY-325 #4405 は closed)

- `0x72db20` の呼出し元: PY-320 時点の数えでは `call [reg + 0xd0]` は 244 箇所 (PY-348 の全走査は 243 件・§6.1)。そのうち MoveLeftMenu の OnClick を発火する箇所は未同定。
- `[Self+0x100]` に 0x12acb70 が書き込まれる箇所 (DFM 読込みの TMethod 生成) は未確認。REPORT_PY268 §3 の推定 (`TMethod(Code = 0x12acb70, Data = TFXForm)`) の裏付けは未取得。
- 動的 (実行) による確認は本 run の範囲外。

## 4. 解釈の限界

- 「rdx = Self」は逆アセンブルの静的な読みで、`0x840b50` の Click 系ディスパッチャという同定 (VMT スロット 0xd0 と `call [Self+0x100]`/`[Self+0x108]` の形) に依る。Code/Data の名前付けは推定。
- 呼出し箇所の関数 (`0x840b50`) は、VMT スロットの同定に基づく。関数の先頭は `int3` パディングの推定 (`pe_callgraph.py` と同じ方式)。

## 5. 検証

- probe: `tools/python/analysis/flapi/pe_py320_fire_site.py` (検査 11 件)。
- 測定 commit (コードを変えた最後の commit): `b27f1942a` (probe の注釈と REPORT の表記の修正。検査ロジックは変えていない)。
- 実行: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py320_fire_site.py`。
  - 実測 (HEAD `b27f1942a`): real 23.877 秒・終了 0・PASS 11 / FAIL 0。
- 既存 probe: `pe_py268_rdx.py` は本 PR で変更していない。同じ素材で HEAD `ec11dfec5` 上で実行: real 24.283 秒・終了 0・検査 PASS 22 件 (集計行「件数 22 / 22」)。
- 負の対照: `0x840cd0` の `[+0xf0]` 枝は `+0x100` 検出 0 件・`+0xf0` 検出 1 件 (`0x840d1b`) で、検出器が枝を区別する。

## 6. PY-348 (#4603): 0x72db20 の間接呼出し元と MoveLeftMenu の発火箇所

結論: **未達** (受入 1・2 は未達)。0x72db20 の呼出し元の総数と、VMT からの型による絞り込みの不可を確定した。発火箇所の同定は #4656 (PY-351) に残す。

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. 0x72db20 を間接に呼ぶ箇所 (関数と VA) を特定する | **未達**。`call qword ptr [reg+0xd0]` の全走査は 243 件 (§6.1)。0x72db20 を指す VMT 位置は code に無いため、どの呼出しが 0x72db20 に当たるかは静的に絞れない (§6.2) | §6.1・§6.2 |
| 2. MoveLeftMenu の OnClick を発火する箇所を絞る | **未達** | §6.3 |
| 3. probe を追加し、`pe_py325_refs.py` 6/6 PASS のままであることを確認する | `pe_py325_refs.py` は PR の base (`cdcd804`) 時点では不在だった。現 main には `171ef59ad` で追加済みで、同じ素材で 6/6 PASS (実測・§6.4)。新 probe `pe_py348_vmt_d0_callers.py` は 4/4 PASS。`pe_py320_fire_site.py` 11/11 PASS | §6.4 |

### 6.1 `call [reg+0xd0]` の全走査

- 件数 243 (レジスタ別: rbx 140・rax 49・rsi 38・rdi 10・r13 5・r14 1)。所属関数 (推定) 136 件。
- PY-320 §3 の記載は 244 件。本走査は 243 件で、1 件ずれる。差の原因は未解明 (PY-351 で確認する)。
- 数え方 (probe に assert): `mnemonic=call` かつオペランドが `qword ptr [` で始まり `+ 0xd0]` で終わるもの = 243。
- 数え方 (probe に assert): `mnemonic=call` かつオペランドに `0xd0` を含み `qword ptr [` で始まらないもの = 即値形 **285**。`mnemonic=jmp` かつオペランドに `0xd0` を含むもの = **283**。いずれも `0xd0ece0` のような即値アドレス・変位の部分一致で、VMT スロットの間接呼出しではない。

### 6.2 型による絞り込みの不可

- TQuickMenuItem (VMT 0x725a58) を指す rip 相対変位は 2 件 (`0x725a02`・`0x725a54`)。どちらも VMT 自身の自己ポインタ位置で、関数の中からの参照は 0 件。
- TMenuItem (VMT 0x838c10) も同様に 2 件 (`0x838bba`・`0x838c0c`)。
- 本走査は disp32 の rip 相対変位と即値だけを数えた。`mov [reg], imm64` 形式の VMT 書込みは未検査。そのため「VMT を書く箇所が無い」とは言えない。
- よって、VMT 参照から「インスタンスの型が TQuickMenuItem である呼出し」を絞る手段は、本走査では見つからなかった。

### 6.3 発火箇所 (未達)

- 0x72db20 の内側で `call 0x840b50` する (§1)。0x840b50 の 0x840be8・0x840c2e から 0x12acb70 を呼ぶ経路 (§2) の前段は、0x72db20 を呼ぶ 243 件のどれから到達するかが未確定。
- 0x72db20 を呼ぶ候補の絞り込みは、次のどちらかを要する: (a) 動的 (実行中の vtable 呼出し) の確認、(b) `mov [reg], imm64` 形式を含む VMT 書込みの走査による TQuickMenuItem インスタンス生成箇所の特定 (本走査では未実施)。
- 残課題は #4656 (PY-351) に起票先として残す。

### 6.4 検証

- 新規 probe: `tools/python/analysis/flapi/pe_py348_vmt_d0_callers.py` (4 件 PASS・終了 0)。`FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py348_vmt_d0_callers.py`。
- 既存 probe: `pe_py320_fire_site.py` 11 件 PASS (終了 0)。
- 既存 probe: `pe_py325_refs.py` (現 main 版・`171ef59ad`) 6 件 PASS (終了 0)。同じ素材で実行。
- 素材: `fl-win64.tar.zst` の `block00031_PE.bin` (`$ARTIFACTS_DIR`)。展開 2.9 秒。
- 測定 commit と実行時間は PR 本文の「検証結果」に記載 (本ファイルには書かない。自己参照を避けるため)。

## 7. PY-351 (#4656): 0x72db20 の VMT 書込み走査と 243/244 の差

結論: 受入 3 (244 と 243 の差) は**説明できた**。受入 1・2 (0x72db20 を呼ぶ箇所の特定と発火箇所の絞り込み) は**未達**。静的な VMT 書込みの走査では、呼出し候補を絞れなかった。

- 差の原因: `call ptr [rdx + rax + 0xd0]` (0xd00111、`qword` 接頭辞なし) が 1 件。PY-348 probe は `qword ptr [` 形だけを数えるため 243 になる。PY-320 §3 の 244 は接頭辞なしを含む数え方。`call qword ptr [rax + rbp*2 + 0xd0]` (0xd062e1) は qword 形に入る。
- VMT 書込みの全形式の走査 (`analysis/flapi/pe_py351_vmt_writes.py`、3/3 PASS): オペランドに 0x725a58 を持つ命令は 0 件。`.text` 内の 8 バイト絶対 0x725a58 は 2 件 (0x725990 = VMT 先頭の自己ポインタ、0x725b80 = RTTI の classname 直後)。どちらもデータで、VMT を書くコードではない。
- 0x72db20 の内側の global `[rip+0xec8627]` (= 0x15f6170) は 0x72db42 の 1 箇所だけが書き、読む箇所は無い。クリックされた項目を静的に特定する手がかりにはならない。
- 残る手段: (a) 実行中の vtable 呼出しの動的確認、(b) TQuickMenuItem の生成経路 (クラス参照変数やコンストラクタ呼出し) の追跡。(b) は本走査の範囲外で、未実施。

## 8. #5309 (PY-351b): イメージ全体の VMT 参照走査

親: #5309 (#4907 の残り)。受入 1 (0x72db20 を間接に呼ぶ箇所の特定) と受入 2 (MoveLeftMenu の発火箇所の絞り込み) は**未達**。受入 1 の前段 (VMT 参照の全走査) だけ達成。

- probe: `analysis/flapi/pe_py351b_classref.py` (4 件 PASS)。`pe_py351_vmt_writes.py` が .text に限ったのに対し、本 probe はイメージ全体 (.data・.rdata・.pdata 等) を見る。
- 結果: 8 バイト絶対 0x725a58 は 0x725990 (VMT 自己ポインタ) と 0x725b80 (RTTI) の 2 件のみ。4 バイト RVA 0x325a58 は 0 件。rip 相対で 0x725a58 を指す命令は 0 件。オペランドに 0x725a58 を持つ命令は 0 件。
- 含意: TQuickMenuItem の VMT は、コードにもデータにも定数として現れない。インスタンスは実行時に作られるとみられる (クラス参照の値が実行時に設定される形)。そのため「VMT 参照から型を絞る」経路は静的には閉じた。0x72db20 の 243 件の間接呼出しのうちどれが MoveLeftMenu かは、静的には決められない。
- 残り (次の run で扱う): (a) 実行中の vtable 呼出し (0xd0 の受信型の動的確認)、(b) 実行時のクラス参照値の設定箇所 (初期化で VMT を格納する関数) の追跡。いずれも親 #5309 の本文にチェックリストとして残す。
- 測定 commit (コードを変えた最後の commit): `8bcf78522` (probe 追加のみ)。
- 実測 (HEAD `8bcf78522`・素材 fl-win64 の block00031_PE.bin・load 0.86〜):
  - `pe_py348_vmt_d0_callers.py`: real 31.69 秒・終了 0・PASS 4 / FAIL 0。
  - `pe_py351_vmt_writes.py`: real 31.02 秒・終了 0・PASS 3 / FAIL 0。
  - `pe_py325_refs.py`: real 0.11 秒・終了 0・PASS 6 / FAIL 0。
  - `pe_py351b_classref.py`: real 32.75 秒・終了 0・PASS 4 / FAIL 0。
