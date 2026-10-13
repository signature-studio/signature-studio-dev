# M11-N82 (#1318): 10 進 inttoptr 4364 件の VA→LVA 仕分け

親: #1076 / #860 / #417。対象は `M11_M2P=1` (`pass_m2p_dec_inttoptr`) が remap する命令形の 10 進 `inttoptr`。
再現スクリプト: [m11_inttoptr_class.py](m11_inttoptr_class.py) (1 コマンド・実測 0.95 s)。
実行: `FL_WIN64_DIR=<展開先> python3 tools/m11/m11_inttoptr_class.py tools/m11/work/boot_allfx.ll --list-other`

## 1. 結論

| 分類 | 件数 | 判定 |
|---|---:|---|
| VA→LVA にすべき (全使用がメモリ参照・code/data アドレス) | **4344** | remap する (M2p の現行動作と一致) |
| VA→LVA にすべき (範囲内・非アドレス用途 19 件、§4) | **19** | remap する (コード/データ アドレスと判定) |
| VA のまま正しい (VA 範囲外・整数定数) | **85** | remap しない (M2p は範囲外を無視する) |
| VA のまま正しい (手動判定: QPF 周波数の整数データ、§3) | **1** | **remap しない。M2p は誤って remap する** |
| 合計 (decimal instr inttoptr 全件) | **4449** | |

- VA 範囲 `[0x400000, 0x1abf400)` 内は **4364 件** で、#1076 / #417 の分母と一致する。
- 範囲内 4364 件のうち VA→LVA が正しいのは **4363 件**、VA のままが正しいのは **1 件** (QPF 周波数)。
- 「VA のまま正しい」の残り 85 件は範囲外 (小さい整数・ビット列・`0x7fffffff`・`0x7ff0000000000000`・`0x64684c46` 等)。
  現行の M2p もこれらは触らないので、既存の挙動で正しい。

## 2. 基準 IR と分母

- 基準: `tools/m11/work/boot_allfx.ll` (work-m11 スナップショット、`m11_passes.py` の M2p 直前の IR)。
  命令形 10 進 `%x = inttoptr i64 N to ptr` は **4449 件** (`grep -cE` の実測と一致)。
- 範囲 `[0x400000, 0x1abf400)` (`m11_passes.py` の `IMG_LO`/`IMG_HI`) 内は **4364 件** = #1076 の分母。
- PE: `block00031_PE.bin` (ImageBase `0x400000`)。section 境界 (実測): `.text` `0x401000–0x13a44b0` (実行可)・
  `.data` `0x13a5000–0x15e5008`・`.bss` `0x15e6000–0x196ee9c`・`.rsrc` `0x1ab1000–0x1cbf400`。
- 範囲内の PE section 分布: `.text` 3737 件 / `.data` 626 件 / `.bss` 1 件。

## 3. 判定規則と根拠

判定は**定数の全使用箇所**で行う (1 箇所でも非アドレス用途があれば §4 の要確認に回す)。

- **アドレス用途**: `load ptr` / `store ... , ptr %x` (アドレス側) / `getelementptr` / `select` の被演算子。
  4344 件は全使用がこれに当たる。代表例は `.data` の `0x15e3360` (line 12777) と `.text` の `0x10040ac` (line 12887)。
- **整数データ (手動)**: line 185227 `inttoptr i64 10000000` (`0x989680`)。
  `dec_label_pc_47fb50` の `QueryPerformanceFrequency` 結果 (10 MHz) を `ptr` 型 global `@global_var_15f25a8` に入れ、
  読み側は `ptrtoint` → `cvtsi2sd` で周波数として使う (line 185236〜185246 で確認)。
  VA ではないので remap は誤り。自動規則では store 値として要確認に入るため、この 1 件だけ手動で VA のまま判定した
  (スクリプトの `MANUAL_INT`)。

## 4. 要確認 19 件 (VA→LVA 側と判定)

- **call 引数 (12 件)**: `CreateThread` の起動関数 (`0x412ae0`, line 125305)・`EnumDisplayMonitors` の
  コールバック (`0x85df70`, line 333404/334381)・`EnumCalendarInfoW` のコールバック (`0x4476d0`/`0x4477a0`, line 157888 系)
  等、コールバックとして渡される PE `.text` 内 VA。残りの call 引数 (`function_11ff410` 内の line 60141 `%ce5n11_function_11ff410` 等。`function_414da0` へ渡す引数) は
  用途を個別には確認していない。いずれも整数データではなく code 範囲のアドレスであるため、LVA 化の対象と判定する。
- **store 値 (7 件)**: `.data` の `0x15e4568`/`0x15e1b40`/`0x15e0590`/`0x15e4f60` (line 245611–262915) と
  `.text` の `0x788141`–`0x788143` (line 302838–302874)。`function_680790` / `function_6a40b0` / `function_787f20` では
  `store ptr <定数>, ptr %…reg2mem` で register 変数に格納され、後続で読まれてアドレスとして使われる
  (`680790` は同じ関数内で `inttoptr` 定数 `22957344` を `load` のアドレスとして読むことを確認)。
  整数ではないので VA→LVA 側。

## 5. M2p 有効化時の影響

- 既存 `M11_M2P=1` は範囲内 **4364 件すべて** を LVA にする。このうち 4363 件は正しく、
  1 件 (`10000000` = line 185227) は誤変換になる (`10000000 − 0x400000` = 5805696 になる)。
  M2p を既定 ON にするには、この 1 件の除外 (M2p 側で許可リスト化) が前提になる。
- unit 503 のハング・survey 完走不可 (#417 / #860) は本件の分類では説明できない。
  件数の仕分けと survey の停止原因は別問題で、本 issue の受入条件には含まれない (#1076 の受入 1・3 は未達のまま)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| M2p の 1 件誤変換 (line 185227 の QPF 周波数定数) を M2p 側で除外する修正 | M2p ON 時に `QueryPerformanceFrequency` 後の周波数が壊れる | #1076 (N63) 受入 4 に積む (既定 OFF のまま) |
| §4 の 19 件の LVA 化後の動的検証 (ネガコン) | 分類は静的判定。動的な ok/oob 変化は未測定 | #1076 / #417 の survey 受入 |
| M2p ON 時の survey 停止 (unit 503・880) の原因 | 本 issue の範囲外 | #1076 受入 1・3 |
