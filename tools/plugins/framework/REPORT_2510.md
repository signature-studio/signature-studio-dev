# #2510 REPORT — stage-2 の InitUnits idx 16 RunError: `"$"` 番地の fold は BLK 領域と relocate 済みコードの重なりが原因 (修復は未着手・子へ移管)

- 担当 issue: #2510 `[PLG-P0b-18]` (親 #2425)。
- 既知類型との関係: `docs/DEFECTS.md` D21 (呼出し引数が `ptrtoint` の値に化ける) と**表層は同じ** (`ptrtoint @N` が分岐条件に入る) だが、**機構は別**。D21 の dl=0 仮説とは対応を確認していない。本件の機構は「memory-ABI の固定 block (BLK) の初期値が、同じセクションに relocate された関数のコードバイトになる」(§3)。`docs/DEFECTS.md` の既存行 (D1a〜D23) には該当が無い → 新類型候補の行案は §6。icall §4 の D1〜D13 との対応は未確認。
- **結論 (1 行)**: 根本原因は `tools/icall/icall_rewrite.py` の BLK 配置 (`blk = image_base + image_size + 0x100000`) が、新 `.icall` セクション (5.6 MB) の relocate 範囲と重なること。BLK の先頭 `0x8A1000` は関数 `0x494cf0` の再配置先 `[0x8A0FE0, 0x8A1271)` の中にあり、RetDec はそのコードバイト (`24 00` = `"$"`) を BLK slot の `constant` 初期値として扱う。stage-1 出力の段階で入口分岐が畳み込まれ、stage-2 の pass はそれを作っていない (§2)。**修復は生成側 (`icall_rewrite.py`) で行う必要がある**。本 run は修復まで到達せず、受入 1〜4 は未達 (§5)。

## 0. 検証起点と測定 commit

- 検証起点 = 測定 commit: `origin/main` `3dbb35e0` (worktree `../ws-2510`・branch `2510-plg-p0b-18-stage2-fold`)。本 PR はコードを変えない (REPORT と DOC_MAP の追記のみ)。
- 素材: `work-fw-stage1` を `tools/plugins/work/fw/` に、`work-liftlib` を `tools/liftlib/work/` に展開 (`tar --zstd -xf`・gitignore)。`[EMSDK]`・`[RETDEC]` (`docs/REFERENCES.md` §4) は runner に既存 (確認: `ls` で `emsdk_env.sh`・`retdec-decompiler` の実在を確認) のため展開しなかった。`fl-win64` は stage-2 が `fw_icall.dll` (work-fw-stage1 同梱) を使うため未展開。
- 実行環境: runner 4 vCPU・RAM 15 GiB。

## 1. stage-2 の再現 (n=1)

| 手順 | commit | 結果 | 所要 (real) | load (1 分値・開始 → 終了) |
|---|---|---|---|---|
| `bash tools/plugins/framework/fw_stage2.sh` (stage-1 成果物を再利用・stage-2 中間物を全て再生成・emcc・smoke) | `3dbb35e0` | rc 1・`SMOKE` 新基準 FAIL: `runerr=1 (got)` `init_reach=16 (got)`・`ff=0` OK | 5 分 40 秒 (14:53:39 → 14:59:19) | 1.17 → 2.53 |

- smoke.log の該当行 (`tools/plugins/work/fw/smoke.log` 23 行): `[fw][MessageBoxA] Error: Runtime 268436792 at 0000000010000710`。旧基準 (`dispatch=38`) の PASS 行は 42 行目に出る (`SMOKE PASS (Halt0/RestoreContext 到達)`)。REPORT_2425 §1 の結果と一致。
- **n=1 のみ**。受入 4 の n≥3 は未達 (子 [PLG-P0b-21] へ)。

## 2. fold の位置と、その発生段 (stage-1 か stage-2 か)

| 段 | ファイル (行) | 観測 |
|---|---|---|
| native | `fw_icall.dll` (`objdump -d -M intel`) `0x40ea20` | `test edi,edi; jle` → `call 0x40e5e0` (ecx=edi)。`edi` = `r8d` (count)。Delphi 文字列確保系の入口 |
| native 呼出元 | `0x407a10` 内の `call 0x40ea20` (`0x407a49`) | IR (`fw_flat4_canon3.ll` 11508 行) では直前に `function_404c80(NULL, buf, 261)` (API 呼出し相当・native 側は未確認) の戻り値を r8 (BLK+0x18) に格納 |
| stage-1 restored | `fw6.restored.ll` 1229 行 | `@global_var_8a1018 = local_unnamed_addr constant i8* getelementptr (@1)`。`@1 = c"$\00"` (1228 行) |
| stage-1 restored | `fw6.restored.ll` 5125 行〜 `function_40ea20` の入口 | `br i1 or (icmp eq (and (ptrtoint @1 ...)...` = **既に定数式**。`load @global_var_8a1018` が `@1` の番地へ畳み込まれている |
| stage-2 中間 | `fw_flat4_canon3.ll` 38146〜38163 | 同じ分岐が `ptrtoint ptr @342` (名前は pass で変わる)。`function_40ea20` 38158〜38163 で BLK+8/+0x10/+0x18 に `"$"` 系を格納 |
| stage-2 中間 | `fw_flat4_canon3.ll` 11515 | 呼出元 `function_407a10` が BLK+0x18 (`9048088`) に `%19` (= `function_404c80` の戻り値) を格納し、11530 行で `call @function_40ea20()` |

- 結論: `"$"` 番地の fold は **stage-1 出力 (RetDec + restore) の段で入る**。stage-2 の pass は fold を作っていない。よって stage-2 の pass 側だけを直しても、この分岐は戻らない (`fw6` の定数式を戻す pass は無い)。
- 呼出元の値 (`%19`) は正しく保存されているのに、callee `function_40ea20` は caller の store を使わず初期値 `"$"` を読む。これが RetDec の `constant` 扱い (§3) と整合する。

## 3. 根本原因: BLK 領域が relocate 済みコードと重なる

### 3.1 BLK の配置と新セクションの範囲

| 項目 | 値 | 出典 |
|---|---|---|
| BLK (memory-ABI の固定 block) | `0x8A1000` (9048064) | `work/fw/fw_map.json` `blk` |
| 新 `.icall` セクション | `0x7A1000`〜`0xD01E8D` (サイズ `0x560E8D` = 5.6 MB) | `fw_map.json` `section_va`・`section_size`。PE 実測も一致 (`.icall va=0x3a1000` は image base 0x400000 からの RVA) |
| BLK の決め方 | `blk = img.base + image_size + 0x100000` = `0x400000 + 0x3A1000 + 0x100000` = `0x8A1000` | `tools/icall/icall_rewrite.py` 673 行。`sect_end` (669 行で計算済み) を参照しない |

- 関数の再配置は `sect_va` (= `0x7A1000`) から `sect_end` まで詰めて置かれる (`icall_rewrite.py` 660〜669 行)。BLK は `sect_va + 0x100000` 固定で、新セクション 5.6 MB の中央付近に当たる。

### 3.2 重なりの検出 (`fw_map.json` `func_range_new`)

| 検出条件 | 件数 | 内容 |
|---|---|---|
| `blk = 0x8A1000` (現行) | **1** | 関数 `0x494cf0` → 新範囲 `[0x8A0FE0, 0x8A1271)`。BLK の先頭 0x280 byte と重なる |
| 反事実 1: `blk = 0xCA1000` (セクション内部の別番地) | 3 | 検出器は内部の重なりを数える (負のコントロール: 検出器が 0 固定でないこと) |
| 反事実 2: `blk = sect_end` を 16 byte 境界に切上げ (`0xD01E90`) | **0** | 修復の候補: BLK をコードの後ろに置くと重なりは消える |

- 検出コード: `python3` で `fw_map.json` の `func_range_new` (文字列の 16 進) を整数化し、`[a, c)` が `[blk, blk+0x280)` と交わるものを数えた (BLK の使用域 0x000〜0x27F を保守的に取った。`icall_rewrite.py` の `BLK_STKBUF = 0x100` の配列は 0x100 以降を使う)。

### 3.3 BLK の初期値がコードバイトになる

| 対象 | バイト (`objdump -s -j .icall`) | RetDec 復元 (`fw6.restored.ll`) |
|---|---|---|
| `0x8A1000` | `24 00 00 00 f2 0f 10 0d` | `@global_var_8a1000 = constant i64 941269854176935972` (= `0x0D100FF200000024`。上のバイトを LE で読んだ値と一致) |
| `0x8A1008` | `24 00 00 00 f2 0f 10 15` | `@global_var_8a1008 = constant i8* gep(@2)`・`@2 = c"$\00"` (`24 00` を文字列として取った) |
| `0x8A1010` | `24 00 00 00 f2 0f 10 1d` | `@global_var_8a1010 = constant i8* gep(@3)`・`@3 = c"$\00"` |
| `0x8A1018` | `24 00 00 00 55 41 55 57`… (`push rbp; push r13; push rdi`) | `@global_var_8a1018 = constant i8* gep(@1)`・`@1 = c"$\00"` |

- BLK の各 slot の先頭は `24 00` (`'$'` + NUL) で、RetDec の文字列検出がそれを `"$"` の定数として拾う。BLK は初期化されていない (0 でない) コードバイトであり、本来の memory-ABI の初期値 (未定義・書込み前提) とは別物。
- RetDec は BLK slot を `constant` の global として宣言する。機構 (`.icall` が CODE 属性を持つことによる判定か、他の要因か) は RetDec 側の判定で、本 run では未特定 (未検証)。書込み可能属性 (`write=Y`) は PE で確認済み (`.icall` flags `0xE0000060`)。

### 3.4 畳み込みの結果

- `function_40ea20` の入口分岐 `test edi,edi` は、caller が BLK+0x18 に入れた値 (`%19`) ではなく、`@global_var_8a1018` の初期値 `"$"` の番地で決まる。count が正と判定され、`call 0x40e5e0` 側の経路に入る (RunError 経路へつながる観測は REPORT_2425 §2 のとおり)。
- `fw6.restored.ll` に `ptrtoint ([2 x i8]* @1 to i32)` (`"$"` の番地を整数化する行) が 123 行ある (`grep -c` の実測。定義: 行単位の一致数)。このうち BLK slot 由来の fold の内訳は未分類。`function_407010` (REPORT_2425 §2 の 8742 行) も同じ型の入力を受ける。

## 4. 検証範囲 / 範囲外

- 範囲内: stage-2 の fresh 再生成 (n=1)、native 逆アセンブル (`objdump`)、IR の行番号特定、BLK と新セクションの重なりの検出 (3.2)、BLK 初期値のバイト照合 (3.3)、stage-1 出力での fold の有無 (§2)。
- 範囲外: 修復の実装 (`icall_rewrite.py` の変更・stage-1 の RetDec 再実行)、smoke PASS の確認、n≥3 の実測、`init_reach` の直接呼出の計測 (受入 3)、RetDec が `constant` を付ける機構の特定。
- 「scratch の戻り値差替え (`fw_hostfix.py` 型)」は修復として採らない (issue の方針どおり)。

## 5. 受入条件の状態 (issue #2510 の 4 項目)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. smoke の `runerr=0 ff=0 init_reach=288` PASS | **未達** | §1 (rc 1・runerr=1)。修復は未着手 |
| 2. 上流の `"$"` 番地の経路を IR 行で特定し、生成側で修復 | **部分** (経路の特定は達成。修復は未達) | §2・§3。呼出元 `function_407a10` 11515 行 → `function_40ea20` 入口。原因は `icall_rewrite.py` 673 行の BLK 配置 |
| 3. `init_reach` の直接呼出の計測 | **未達** | 本 run では計測せず (`init_reach` は下限 16 のまま) |
| 4. n≥3 の実測を REPORT に記録 | **部分** (n=1 のみ) | §1。n≥3 は修復後に測る |

## 6. 生成側の修復方針 (子 issue の入力) と DEFECTS 行案

修復方針 (未実装・子 [PLG-P0b-20] の入力):

1. `icall_rewrite.py` で BLK を relocate 済みの関数範囲の**後ろ** (`sect_end` の後) に置く。または BLK を別の書込み可能セクションに置く。
2. BLK と relocate 範囲の重なりを**fail-closed** にする (重なれば `icall_rewrite.py` が exit 1)。
3. BLK の初期値は 0 (`.icall` の該当域を 0 埋めする) とし、コードバイトを残さない。

DEFECTS.md への行案 (**PM 判断**・DEFECTS.md は直接編集しない):

- 類型名 (案): **D24 (候補)**: memory-ABI の固定 block (BLK) が relocate 済みコードと重なり、RetDec がコードバイトを BLK の `constant` 初期値として畳み込む。
- 症状: 呼出し先が caller の store を見ず、初期値 (`"$"` の番地) で分岐する。stage-2 の smoke で `Runtime error` (RunError) に出る。
- 根本原因: `icall_rewrite.py` の `blk = image_base + image_size + 0x100000` が、新セクションの 5.6 MB の範囲と重なる (§3.2)。
- 検出信号: `fw_map.json` の `blk` と `func_range_new` の交差 (§3.2) が 0 件であること。
- 修復: 方針 1〜3 (§6 の上)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 2 の修復 (`icall_rewrite.py` の BLK 配置を重なりの無い位置へ・fail-closed の検査・BLK の 0 埋め) | idx 16 で RunError が継続 (`runerr=1`) | 子 **[PLG-P0b-20]** (本 PR の後に起票。`親: #2510`) |
| 修復後の stage-1 再生成 (RetDec) と stage-2 smoke PASS・n≥3 の実測・`init_reach` の直接呼出の計測 (受入 1・3・4) | 修復の効果が未確認 | 子 **[PLG-P0b-21]** (`親: #2510`。[PLG-P0b-20] の PR 後に着手) |
| RetDec が BLK slot を `constant` にする機構 | 修復の範囲 (生成側で BLK を外すだけで足りるか) が未確定 | 子 [PLG-P0b-21] の調査項目 |
| DEFECTS.md への類型行 (D24 候補) | 類型が未登録 | PM 判断 (§6) |
| `fw6.restored.ll` の `"$"` 番地の整数化 (123 行) のうち、BLK slot 由来の fold の内訳 | 同型の fold が他の関数にも残る可能性 | 子 [PLG-P0b-21] の検証項目 |

## 8. 再現手順

```sh
git worktree add ../ws-2510 -b 2510-plg-p0b-18-stage2-fold origin/main          # (済)
cd ../ws-2510 && tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64      # stage-2 本体は fw_icall.dll (work-fw-stage1) を使う。fl-win64 は不要
timeout 840 bash tools/plugins/framework/fw_stage2.sh     # §1 の 5 分 40 秒。最後の smoke 判定が FAIL で rc 1
cd tools/plugins/work/fw
objdump -d -M intel --start-address=0x40ea20 --stop-address=0x40ea80 fw_icall.dll   # §2 (native)
grep -n 'global_var_8a1018 = ' fw6.restored.ll                                     # §2 (stage-1 の定数)
grep -n 'i64 9048088 to ptr' fw_flat4_canon3.ll | head                             # §2 (BLK+0x18 の store)
python3 - <<'PY'   # §3.2: BLK と relocate 範囲の重なり (fw_map.json)
import json
m=json.load(open('fw_map.json')); blk=m['blk']
print([k for k,v in m['func_range_new'].items() if int(v[0],16)<blk+0x280 and int(v[1],16)>blk])
PY
```

## 9. コード差分 (測定 commit 以降)

測定 commit `3dbb35e0` 以降のコード変更は無し (本 PR は REPORT と DOC_MAP の追記のみ)。

```sh
git diff 3dbb35e0 HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'   # 空 = 実行コード差分 0
```

- 出力は空 (本 commit 後に実行して確認する)。
