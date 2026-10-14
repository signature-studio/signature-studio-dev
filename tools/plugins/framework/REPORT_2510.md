# #2510 REPORT — stage-2 の InitUnits idx 16 RunError: `"$"` 番地の fold は BLK 領域と relocate 済みコードの重なりが有力な原因 (因果は未確認・修復は未着手・子へ移管)

- 担当 issue: #2510 `[PLG-P0b-18]` (親 #2425)。
- 既知類型との関係: `docs/DEFECTS.md` D21 (呼出し引数が `ptrtoint` の値に化ける) と**表層は同じ** (`ptrtoint @N` が分岐条件に入る) だが、**機構は別**の候補。D21 の dl=0 仮説とは対応を確認していない。本件の候補機構は「memory-ABI の固定 block (BLK) の初期値が、同じセクションに relocate された関数のコードバイトになる」(§3)。`docs/DEFECTS.md` の既存行 (D1a〜D23) には該当が無い → 新類型候補の行案は §6。icall §4 の D1〜D13 との対応は未確認。
- **結論 (1 行)**: 有力な原因は `tools/icall/icall_rewrite.py` の BLK 配置 (`blk = sect_va + 0x100000` = `0x8A1000`) が、新 `.icall` セクション (`0x7A1000`〜`0xD01E8D`) の relocate 範囲と重なること。BLK の先頭 `0x8A1000` は関数 `0x494cf0` の再配置先 `[0x8A0FE0, 0x8A1271)` の中にあり、BLK slot の初期値はそのコードバイト (`24 00` = `"$"`) と一致する。`function_40ea20` の入口分岐は、呼出元が書いた値ではなくこの定数 global の初期値で畳み込まれる (§2)。**因果は未確認**: 重なりを外せば fold が消えるか、RetDec が BLK を `constant` にする機構は #2566 で確認する。本 run は修復まで到達していない (§5)。

## 0. 検証起点と測定 commit

- 検証起点 = 測定 commit: `origin/main` `3dbb35e0` (worktree `../ws-2510`・branch `2510-plg-p0b-18-stage2-fold`)。本 PR はコードを変えない (REPORT と DOC_MAP の追記のみ)。
- 素材: `work-fw-stage1` を `tools/plugins/work/fw/` に、`work-liftlib` を `tools/liftlib/work/` に展開 (gitignore。`tar --zstd -xf`)。`[EMSDK]`・`[RETDEC]` (`docs/REFERENCES.md` §4) は runner に既存 (確認: `ls` で `emsdk_env.sh`・`retdec-decompiler` の実在を確認) のため展開しなかった。`fl-win64` は stage-2 が `fw_icall.dll` (work-fw-stage1 同梱) を使うため未展開。
- 素材の照合: 上記の展開物で §2.1・§3.1・§3.2・§3.3 の IR 行と PE 値を照合した (§10)。stage-2 は再実行していない。
- 実行環境: runner 4 vCPU・RAM 15 GiB。

## 1. stage-2 の再現 (n=1)

| 手順 | commit | 結果 | 所要 (real) | load (1 分値・開始 → 終了) |
|---|---|---|---|---|
| `bash tools/plugins/framework/fw_stage2.sh` (stage-1 成果物を再利用・stage-2 中間物を全て再生成・emcc・smoke) | `3dbb35e0` | rc 1・`SMOKE` 新基準 FAIL: `runerr=1 (got)` `init_reach=16 (got)`・`ff=0` OK | 5 分 40 秒 (14:53:39 → 14:59:19) | 1.17 → 2.53 |

- smoke.log の該当行 (`tools/plugins/work/fw/smoke.log` 23 行): `[fw][MessageBoxA] Error: Runtime 268436792 at 0000000010000710`。旧基準 (`dispatch=38`) の PASS 行は 42 行目に出る (`SMOKE PASS (Halt0/RestoreContext 到達)`)。REPORT_2425 §1 の結果と一致。
- **smoke.log は `work-fw-stage1` に含まれない**。照合していない (§1 の記録は測定時のまま)。
- **n=1 のみ**。受入 4 の n≥3 は未達 (子 #2566 へ)。

## 2. fold の位置と、その発生段 (stage-1 か stage-2 か)

| 段 | ファイル (行) | 観測 |
|---|---|---|
| native | `fw_icall.dll` (`objdump -d -M intel`) `0x40ea20` | `test edi,edi; jle` → `call 0x40e5e0` (ecx=edi)。`edi` = `r8d` (count)。Delphi 文字列確保系の入口 |
| native 呼出元 | `0x407a10` 内の `call 0x40ea20` (`0x407a49`) | (測定時の観測・今回は未再実行) |
| stage-1 restored | `fw6.restored.ll` 1229 行 | `@global_var_8a1018 = local_unnamed_addr constant i8* getelementptr (@1)`。`@1 = c"$\00"` (1228 行) |
| stage-1 restored | `fw6.restored.ll` 5141 行 (`function_40ea20` 5125 行の入口) | `br i1 or (icmp eq (and (ptrtoint @1 ...)...` = **既に定数式**。`load @global_var_8a1018` が `@1` の番地へ畳み込まれている |
| stage-2 中間 (**素材に無く未検算**) | `fw_flat4_canon3.ll` 38146〜38163 | 同じ分岐が `ptrtoint ptr @342` (名前は pass で変わる)。`function_40ea20` 38158〜38163 で BLK+8/+0x10/+0x18 に `"$"` 系を格納 |
| stage-2 中間 (**素材に無く未検算**) | `fw_flat4_canon3.ll` 11515 | 呼出元 `function_407a10` が BLK+0x18 (`9048088`) に `%19` (= `function_404c80` の戻り値) を格納し、11530 行で `call @function_40ea20()` |

- 結論: `"$"` 番地の fold は **stage-1 出力 (RetDec + restore) の段で入る** (fw6 1229・5141 行で確認)。stage-2 の pass は fold を作っていないとみられるが、これは stage-2 中間物の比較によるもので、その行番号は未検算。
- 呼出元の値 (`%19` や `%36`) は正しく保存されているのに、callee `function_40ea20` は caller の store を使わず、`@global_var_8a1018` の初期値 `"$"` を読む。これが RetDec の `constant` 扱い (§3) と整合する。
- `407a10` は `40ea20` の直接呼出元の一つだが、idx 16 から RunError に至る観測連鎖 (§2.1) には現れない。

## 2.1 上流経路 (受入 2 の対応)

素材 `work-fw-stage1` の stage-1 IR で、issue #2510 が指定する呼出元 3 関数と、直接呼出元 `407a10` の格納行を確認した。行番号は `tools/plugins/work/fw/*.restored.ll`。`"$"` 定数 (`[2 x i8] c"$\00"`) の `@N` 番号はファイルごとに異なるので、ファイル名と併記する。

| 関数 (定義 IR 行) | BLK への格納 (行: スロット ← 値) | BLK 経由の呼出し (行) |
|---|---|---|
| `function_43db30` (`fw5.restored.ll` 14121) | 14141 +0x8 ← `@4` (`"$"`)・14142 +0x10 ← `@3` (`"$"`)・14143 +0x18 ← `@1` (`"$"`)。分岐 14138 の偽側 `dec_label_pc_80d694` 内で、呼出し 14153 の直前 | `call function_43d9a0` 14153 (InitTable idx 16 の Init) |
| `function_43d9a0` (`fw3.restored.ll` 19155) | 19166 +0x8 ← `@global_var_427ed0` (data の番地)・19167 +0x10 ← `@3` 由来の式 `(&@3 & -256) \| 1` (`"$"` の厳密な番地ではない)・19168 +0x18 ← `@global_var_41f5e0` (data)・19183 +0x8 ← `@global_var_4291d8` (data)・19184 +0x10 ← 19167 の式をさらに `& -256`・`\| 1` した `@3` 由来の式 (`"$"` の厳密な番地ではない)・19185 +0x18 ← `@global_var_41f6e0` (data) | `call function_43c780` 19178・19195 |
| `function_43c780` (`fw3.restored.ll` 18614) | 18635 +0x8 ← `@4` の番地 (`"$"`)・18636 +0x10 ← `@3` 由来・18637 +0x18 ← `@2` (`"$"`)・18663 +0x8 ← `%20` (計算値)・18664 +0x10 ← `@2`・18665 +0x18 ← `@2` (`"$"`)・18683〜18685 (+0x8 ← `%.reload`、+0x10・+0x18 ← `@2`) | `call function_40bce0` 18647・`call function_417bc0` 18675・`call function_40bd20` 18695 |
| `function_417bc0` (`fw7.restored.ll` 7719) | 7798 より前の格納のみ: 7737 +0x0 ← `%11`・7738 +0x8 ← `@3` (`"$"`)・7739 +0x10 ← `@2`・7740 +0x18 ← `@1` (`"$"`)・7765〜7767 (+0x8 ← `%23`、+0x10 ← `@2`、+0x18 ← `@1`)・7784 +0x8 ← `@3`・7786 +0x10 ← `%35`・7788 +0x18 ← `%36` (= 7782〜7787 の `function_404c60` 戻り値の `inttoptr`。非定数) | `call function_40ea20` 7798 |
| `function_40ea20` (`fw6.restored.ll` 5125) | 読み側: 5141 の `br` の条件が `@global_var_8a1018` (fw6 1229 で `constant`・初期値 `@1` = `"$"`) の番地式に畳み込まれている。呼出元の格納 (7788 など) は読まれない | `call function_40e5e0` 5156 (§2 の RunError 経路へ) |
| `function_407a10` (`fw2.restored.ll` 4015)・観測連鎖の**外** | 4030〜4032 +0x8/+0x10/+0x18 ← `@4`/`@3`/`@1` (`"$"`)・4050〜4054 (+0x8 ← `@4`、+0x10 ← `%18`、+0x18 ← `%19` (4053 `%19 = inttoptr %17`。`%17` は 4049 `%17 = and %16`、`%16` は 4048 `%16 = call function_404c80` の戻り値)) | `call function_40ea20` 4064。呼出元は `function_6b37e0` (`fw0.restored.ll` 154428)・`function_5c6a20` (`fw5.restored.ll` 108806) |

- **正しい上流経路**: `function_43db30` → `43d9a0` → `43c780` → `417bc0` → `40ea20`。stage-1 IR に 4 本の呼出し辺 (14153・19178/19195・18675・7798) があり、`REPORT_2008.md` §8.3 の scratch 観測の連鎖 (`0x43db30 → 0x43d9a0 → 0x43c780 → 0x417bc0 → 0x40ea20 → 0x40e5e0 → 0x407010`) と一致する。ただし §8.3 は診断ビルドの一度の観測で、今回は再観測していない。
- `417bc0` の格納列は呼出し 7798 より前の行だけ。呼出し後の 7804・7806・7807 (別ブロック `dec_label_pc_7d7865`) は表に含めない。
- `"$"` の厳密な番地の格納は、この連鎖では `43db30` (14141〜14143)・`43c780` (18635・18637・18664・18665・18684・18685)・`417bc0` (7738〜7740・7784) にある。`43d9a0` は data の番地 (19166・19168・19183・19185) と `@3` 由来の式 (19167・19184) を格納し、`"$"` の厳密な番地は格納しない。
- `407a10` は `40ea20` の別の直接呼出元で、同じ BLK+0x18 に `"$"` 系を格納するが、観測連鎖には無い。fold は `40ea20` の読み側で起きるため、どの呼出元も同じ fold を受ける。修復の対象は呼出元ごとではなく、BLK 領域の定義 (配置・初期値) と、その上で `constant` になる機構 (§3.3)。
- 受入 2 の「経路の特定」はこれで IR 行まで確定した。生成側の修復は未達 (§5・#2565)。

## 3. 有力な原因: BLK 領域が relocate 済みコードと重なる

### 3.1 BLK の配置と新セクションの範囲

| 項目 | 値 | 出典 |
|---|---|---|
| BLK (memory-ABI の固定 block) | `0x8A1000` (9048064) | `fw_map.json` `blk` (`work-fw-stage1` から再確認) |
| 新 `.icall` セクション | VA `0x7A1000`〜`0xD01E8D` (VirtualSize `0x560E8D` = 5.6 MB)。`.icall` は PE の**最後のセクション** (後続なし) | `objdump -h fw_icall.dll`・`fw_map.json` `section_va`・`section_size` |
| BLK の決め方 | `icall_rewrite.py` 673 行 (全文): `blk = a.blk_va if a.blk_va else (img.base + image_size + 0x4000000 if img.base > 0x100000000 else img.base + image_size + 0x100000)`。`a.blk_va` (`--blk-va`) の指定が優先。本 PE は image base `0x400000` (4 GiB 未満) なので `+ 0x100000` の側 (`0x400000 + 0x3A1000 + 0x100000` = `0x8A1000`)。`sect_va` は 653 行 `img.base + ((image_size + 0xfff) & ~0xfff)` = `0x7A1000` | `tools/icall/icall_rewrite.py` 653・673 行 |

- 関数の再配置は `sect_va` (= `0x7A1000`) から `sect_end` (672 行で計算) まで詰めて置かれる。BLK は `sect_va + 0x100000` の固定位置で、新セクションの**先頭から約 1 MB** の位置に当たる。

### 3.2 重なりの検出 (`fw_map.json` `func_range_new`)

| 検出条件 | 件数 (使用域 `0x280`・保守的上限) | 件数 (使用域 `0x160`) | 内容 |
|---|---|---|---|
| `blk = 0x8A1000` (現行) | **1** | **1** | 関数 `0x494cf0` → 新範囲 `[0x8A0FE0, 0x8A1271)`。BLK の先頭に重なる |
| 負のコントロール: `blk = 0xCA1000` (セクション内部の別番地) | 3 | 2 | 検出器は内部の重なりを数える (検出器が 0 固定でないことの確認) |
| 配置の計算: `blk = sect_end` を 16 byte 境界に切上げ (`0xD01E90`) | **0** | **0** | BLK をコードの後ろに置いた場合の交差の計算。**再ビルドによる反事実ではない** |

- BLK の実使用域は `NSTK = 12` (`icall_rewrite.py` 38 行) から `0x000`〜`0x160` (`BLK_STKBUF` 0x100 + 8 × 12)。`0x280` は保守的な上限で、表の右列で `0x160` でも数えた。
- 検出コード: `python3` で `fw_map.json` の `func_range_new` (文字列の 16 進) を整数化し、`[a, c)` が `[blk, blk+span)` と交わるものを数えた。

### 3.3 BLK の初期値がコードバイトになる

| 対象 | バイト (`objdump -s -j .icall`) | RetDec 復元 (`fw6.restored.ll`) |
|---|---|---|
| `0x8A1000` | `24 00 00 00 f2 0f 10 0d` | `@global_var_8a1000 = constant i64 941269854176935972` (= `0x0D100FF200000024`。上のバイトを LE で読んだ値と一致) |
| `0x8A1008` | `24 00 00 00 f2 0f 10 15` | `@global_var_8a1008 = constant i8* gep(@2)`・`@2 = c"$\00"` (`24 00` を文字列として取った) |
| `0x8A1010` | `24 00 00 00 f2 0f 10 1d` | `@global_var_8a1010 = constant i8* gep(@3)`・`@3 = c"$\00"` |
| `0x8A1018` | `24 00 00 00 55 41 55 57`… (`push rbp; push r13; push rdi`) | `@global_var_8a1018 = constant i8* gep(@1)`・`@1 = c"$\00"` |

- BLK の各 slot の先頭は `24 00` (`'$'` + NUL) で、RetDec の文字列検出がそれを `"$"` の定数として拾う。BLK は初期化されていない (0 でない) コードバイトであり、本来の memory-ABI の初期値 (未定義・書込み前提) とは別物。
- RetDec は BLK slot を `constant` の global として宣言する。**機構は未特定 (未検証)**。`.icall` が CODE 属性を持つことによる判定か、他の要因かは #2566 の受入 5 で確認する。書込み可能属性 (`write=Y`) は PE で確認済み (`.icall` flags `0xE0000060`)。

### 3.4 畳み込みの結果

- `function_40ea20` の入口分岐 `test edi,edi` は、caller が BLK+0x18 に入れた値 (`%19`・`%36`) ではなく、`@global_var_8a1018` の初期値 `"$"` の番地で決まる。count が正と判定され、`call 0x40e5e0` 側の経路に入る (RunError 経路へつながる観測は REPORT_2425 §2 のとおり)。
- `fw6.restored.ll` に `ptrtoint ([2 x i8]* @1 to i32)` (`"$"` の番地を整数化する行) が 123 行ある (`grep -c` の実測)。このうち BLK slot 由来の fold の内訳は未分類。`function_407010` (REPORT_2425 §2 の 8742 行) も同じ型の入力を受ける。
- **重なりを外したときに fold が消えるかは未確認** (#2566)。本 REPORT の実測が支えるのは「BLK slot の初期値が重なったコードバイトと一致する」「fold が stage-1 の段で入る」までで、それが RunError の原因であることは確定していない。

## 4. 検証範囲 / 範囲外

- 範囲内: stage-2 の fresh 再生成 (n=1)、native 逆アセンブル (`objdump`)、IR の行番号特定 (stage-1 は素材で再確認)、BLK と新セクションの重なりの検出 (3.2)、BLK 初期値のバイト照合 (3.3)、stage-1 出力での fold の有無 (§2)、上流の呼出し辺 (§2.1)。
- **範囲外 (未検算)**: stage-2 中間物 (`fw_flat4_canon3.ll` の行番号)・`smoke.log` の行番号。これらは `work-fw-stage1` に含まれず、今回は再現していない。
- 範囲外: 修復の実装 (`icall_rewrite.py` の変更・stage-1 の RetDec 再実行)、smoke PASS の確認、n≥3 の実測、`init_reach` の直接呼出の計測 (受入 3)、RetDec が `constant` を付ける機構の特定、重なりを外したときの fold の消失の確認。
- 「scratch の戻り値差替え (`fw_hostfix.py` 型)」は修復として採らない (issue の方針どおり)。

## 5. 受入条件の状態 (issue #2510 の 4 項目)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. smoke の `runerr=0 ff=0 init_reach=288` PASS | **未達** | §1 (rc 1・runerr=1)。修復は未着手 (→ #2565)。PASS の確認は #2566 |
| 2. 上流の `"$"` 番地の経路を IR 行で特定し、生成側で修復 | **部分** (経路の特定は達成・修復は未達) | 経路は §2.1 で確定 (`43db30`→`43d9a0`→`43c780`→`417bc0`→`40ea20`、各辺の IR 行)。修復は #2565 |
| 3. `init_reach` の直接呼出の計測 | **未達** | 本 run では計測せず (`init_reach` は下限 16 のまま) → #2566 |
| 4. n≥3 の実測を REPORT に記録 | **部分** (n=1 のみ) | §1。n≥3 は修復後に測る → #2566 |

## 6. 生成側の修復方針 (子 issue の入力) と DEFECTS 行案

修復方針 (未実装・子 #2565 の入力):

1. `icall_rewrite.py` で BLK を relocate 済みの関数範囲の**後ろ** (`sect_end` の後) に置く。または BLK を別の書込み可能セクションに置く。
   - `sect_end` は `0xD01E8D` (`.icall` の VirtualSize の終端) の**外**。`.icall` は PE の最後のセクションで、`0xD01E90`〜`0xD01FFF` は `.icall` の raw data (SizeOfRawData `0x561000`) と、ページ末尾 (SizeOfImage `0x902000` の RVA = VA `0xD02000`) の内側に当たる。残りは `0x170` byte で、使用域 `0x160` は収まる。ただし rewriter の出力バッファは `sect_end - sect_va` で作るため、置く場合は `.icall` の VirtualSize の扱いを #2565 で決める。別セクションへ置く場合は PE への新セクション追加が必要 (未検討)。
2. BLK と relocate 範囲の重なりを**fail-closed** にする (重なれば `icall_rewrite.py` が exit 1)。
3. BLK の初期値は 0 (`.icall` の該当域を 0 埋めする) とし、コードバイトを残さない。**ただし RetDec が BLK を `constant` とする機構が未特定のため、0 でも 0 に畳まれる可能性が残る。#2566 の受入 5 で確認する。**

DEFECTS.md への行案 (**PM 判断**・DEFECTS.md は直接編集しない):

- 類型名 (案): **D24 (候補)**: memory-ABI の固定 block (BLK) が relocate 済みコードと重なり、RetDec がコードバイトを BLK の `constant` 初期値として畳み込む (有力な原因。因果は #2566 で確認)。
- 症状: 呼出し先が caller の store を見ず、初期値 (`"$"` の番地) で分岐する。stage-2 の smoke で `Runtime error` (RunError) に出る。
- 有力な原因: `icall_rewrite.py` の `blk = image_base + image_size + 0x100000` が、新セクションの 5.6 MB の範囲と重なる (§3.2)。
- 検出信号: `fw_map.json` の `blk` と `func_range_new` の交差 (§3.2) が 0 件であること。
- 修復: 方針 1〜3 (§6 の上)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 2 の修復 (`icall_rewrite.py` の BLK 配置を重なりの無い位置へ・重なりの fail-closed・BLK の 0 埋め) | idx 16 で RunError が継続 (`runerr=1`) | 子 **#2565 `[PLG-P0b-20]`** (open・`親: #2510`) |
| 修復後の stage-1 再生成 (RetDec) と stage-2 smoke PASS・n≥3 の実測・`init_reach` の直接呼出の計測・重なりを外したときの fold の消失 (受入 1・3・4) | 修復の効果が未確認 | 子 **#2566 `[PLG-P0b-21]`** (open・`親: #2510`。#2565 の PR merge 後に着手) |
| RetDec が BLK slot を `constant` にする機構 | 修復の範囲 (生成側で BLK を外すだけで足りるか) が未確定 | 子 #2566 の受入 5 |
| DEFECTS.md への類型行 (D24 候補) | 類型が未登録 | PM 判断 (§6) |
| `fw6.restored.ll` の `"$"` 番地の整数化 (123 行) のうち、BLK slot 由来の fold の内訳 | 同型の fold が他の関数にも残る可能性 | 子 #2566 の検証項目 |
| stage-2 中間物 (`fw_flat4_canon3.ll`・`smoke.log`) の行番号の検算 | §2 の stage-2 行は未検算 | 本 PR の範囲外 (§4)。次回の stage-2 再実行で確認 |

## 8. 再現手順

```sh
git worktree add ../ws-2510 -b 2510-plg-p0b-18-stage2-fold origin/main          # (済)
cd ../ws-2510 && tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64      # stage-2 本体は fw_icall.dll (work-fw-stage1) を使う。fl-win64 は不要
timeout 840 bash tools/plugins/framework/fw_stage2.sh     # §1 の 5 分 40 秒。最後の smoke 判定が FAIL で rc 1
cd tools/plugins/work/fw
objdump -d -M intel --start-address=0x40ea20 --stop-address=0x40ea80 fw_icall.dll   # §2 (native)
grep -n 'global_var_8a1018 = ' fw6.restored.ll                                     # §2 (stage-1 の定数)
sed -n '14153p' fw5.restored.ll; sed -n '19178p;19195p;18675p' fw3.restored.ll; sed -n '7798p' fw7.restored.ll   # §2.1 (呼出し辺)
python3 - <<'PY'   # §3.2: BLK と relocate 範囲の重なり (fw_map.json)
import json
m=json.load(open('fw_map.json')); blk=m['blk']
print([k for k,v in m['func_range_new'].items() if int(v[0],16)<blk+0x280 and int(v[1],16)>blk])
PY
```

## 9. コード差分 (測定 commit 以降)

測定 commit `3dbb35e0` 以降のコード変更は無し (本 PR は REPORT と DOC_MAP の追記・訂正のみ)。

```sh
git diff 3dbb35e0 HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'   # 空 = 実行コード差分 0
```

- 出力は空 (検証 HEAD で実行して確認。§10)。

## 10. 素材との照合 (検証の記録)

- 検証 HEAD: PR 本文の「検証結果」を参照。
- 照合 (素材 `work-fw-stage1`・展開先 `tools/plugins/work/fw/`):
  - §2.1 の 4 本の呼出し辺 (`fw5.restored.ll` 14153、`fw3.restored.ll` 19178・19195・18675、`fw7.restored.ll` 7798) と定義行 (14121・19155・18614・7719)。
  - `fw5.restored.ll` 14141〜14143 (43db30 の `"$"` 格納)、`fw3.restored.ll` 19166〜19185 (43d9a0 の格納。data の番地と `@3` 由来の式の区別)、`fw3.restored.ll` 18635〜18685 (43c780 の格納)。
  - `fw7.restored.ll` 7782〜7808 (417bc0 の格納と 7798 の呼出し。7804・7806・7807 は呼出し後の行)。
  - `fw6.restored.ll` の `@global_var_8a1018` 定義 (1229) と 40ea20 の入口分岐 (5141)。
  - `fw2.restored.ll` 4046〜4054 (407a10 の格納。4048 → 4049 → 4053 の経由)、その呼出元 (`fw0` 154428・`fw5` 108806)。
- `icall_rewrite.py` 653・673 行の全文、NSTK (38 行)、`fw_map.json` の `blk`・`func_range_new` からの交差再計算 (§3.2 の 0x160 列)。
- PE: `objdump -h` で `.icall` が最後のセクション (VA `0x7A1000`・VirtualSize `0x560E8D`)。ヘッダで SizeOfImage `0x902000`・SizeOfRawData `0x561000`・FileAlignment `0x200`。
