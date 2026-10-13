# tools/plugins/f2 REPORT 付録 — §8 (PLG-F2-3 #515: leaf 23 関数の関数単位差分) と §9 (PLG-F2-4 #547: xmm 引数復元 pass)

> **正本**: `tools/plugins/f2/REPORT.md`。本書は同 REPORT §8・§9 を `docs/DOC_MAP.md` §1 (250 行上限) に従い**無変更で分割移動**したもの (本文は削除していない)。

## 8. PLG-F2-3 (#515): 「IR leaf かつ機械語に間接 call 無し」23 関数の関数単位差分試験

- 検証起点 commit: **cb70945** (origin/main 6a0a8c8 を基点とする `515-plg-f2-3-leaf-diff`)。数値は §8 の再現コマンドをこの HEAD (`git status --porcelain=v1 -- tools/plugins/f2` クリーン) で実行して取得。前提 `f2_step1.sh` の work/ は同 run 内で再生成 (§1 と同条件)。
- 既知類型との関係: 不一致 8 関数は全て **(DEFECTS.md) D5** (xmm 引数脱落、`xmm_arg_drop` 8)。重なる類型は **(DEFECTS.md) D4** 系 (`spill_slot_deref` 4)・**(DEFECTS.md) D1a** (`fp_flag_unreflected` 4)。比較系の偽陽性 2 類型は新規 (§8.5 の DEFECTS.md 行案)。
- 範囲: 23 関数の関数単位差分とそのネガティブコントロール。native 参照は FL Studio 実機ではなく **Linux x86-64 上で PE の機械語を ImageBase に mmap して MS x64 ABI で直接実行**した値 (`tools/liftdiff/rt/ld_native.c`)。ホスト・framework・TFruityPlug 実体とのリンク (#195〜#197) は範囲外。

### 8.0 結論 (先出し)

1. 対象 23 関数 = §3 の「IR leaf 55」のうち機械語にも非 IAT 間接 call が無いもの。別算法 (`xcheck_leaf.py`) で **同じ 23 関数を再導出** (集合一致 EQ)。23 関数は位置非依存ハッシュで **18 種類のコード**(5 組が別 block と同一コード)。
2. **最終判定: 一致 15 / 不一致 8 / 実行不能 0**(23 関数)。主採点(9 パターン)だけだと 一致 9 / 不一致 9 / 実行不能 5 で、補助 case(§8.2)を足して 12 関数の判定が確定した。うち主採点の「一致」2 関数 (0x6bfec0・0x6c9b60) は補助 case で不一致に覆った = **9 パターンの一致は検出力が弱い関数がある**。
3. 不一致 8 関数は **全て「機械語が xmm 入力を読むのに IR 署名に float 引数が無い」(D5)**。`batch_lift.sh` → `lift_ranges.sh` の鎖に ARG pass (`lift/passes/ir7_argpass.py` は取り込み済みで未接続) が無いことが共通原因。→ [PLG-F2-4] #547。
4. 一致 15 関数は 9 パターン+補助 case の範囲で戻り値・書換えメモリ・entry 列が bit 一致。**入力空間全体の等価性は主張しない**(§8.4 の限界)。
5. ネガティブコントロール (§8.3): 既知の脱落を 1 箇所入れた IR で、一致 15 関数のうち変異できた分の不一致検出を実測。

### 8.1 方式 (1 コマンド再現は §8.6)

`tools/liftdiff` の target 記述 (`docs/FORMAT.md` §1) を block ごとに `mk_targets.py` が生成する。**IR は `batch_lift.sh` の `p.final.ll` そのまま**(下記 ABI アダプタを除き無改変)。

| 項目 | 内容 |
|---|---|
| native | block の PE を ImageBase 0x400000 に mmap、`setarch -R`、MS x64 ABI で `function_<VA>` の機械語を直接実行 (`ld_native`) |
| wasm | `p.final.ll` を entry 計装して `emcc -O0` + `p_simd.c` (SIMD helper) + スタブと link。PE を RVA 配置した image (DIR64 reloc を VA→RVA 補正; 8 block とも reloc 件数 = 補正件数) を線形メモリ 0 番地に載せる (`wasm_origin=0`、delta=0x400000) |
| 比較 | 戻り値 (rax / xmm0 bit)・書換えメモリ (image 書込み可能 section + arena + heap の 8B ブロック)・import 呼出列・関数 entry 列。ptr は delta を許容 |
| 主採点 | 1 関数 9 case (引数パターン z,s,p0,p1,p01,pall,pall2,q0,qall。ptr-rich random の arena) |
| 補助採点 | 主採点が unexec / 時間切れ / 偽陽性 / 検出力不足の 12 関数に、機械語の意味に合わせた手作り case を追加 (`leaf_custom.py`、66 case)。ptr 鎖・count・float 配列・xmm 入力 (native にだけ `f:<bits>` を渡す) |
| ABI アダプタ | IR が `i128` を返す 4 関数 (0x6c8fc0・0x6c9b60・0x6f1650・0x6f23b0。機械語は xmm0 に float を返す) は liftdiff の JS ランナが呼べない。元関数を `.i128` に改名し、同名の `trunc i128→i32; bitcast float` だけのラッパを足した (`mk_targets.py`)。機械語の最後の xmm0 書込み命令の型 (`ss`) で float と決定 |

**採点の定義**(`leaf_report.py` 冒頭と同文): 関数 verdict は match = native 完走 case ≥1 かつ完走した全 case 一致 / mismatch = 完走 case のどれかに差分、または native 完走 + wasm trap / unexec = native 完走 case 0。最終判定は、補助が mismatch なら mismatch、補助が match で主採点が match/unexec なら match、補助が match で主採点が mismatch の場合のみ `leaf_custom.ARTIFACT` に根拠のある偽陽性 3 関数 (§8.5) を match に上書き。数え方: 関数 = 23 (closure_stats の leaf ∩ audit_icall の静的間接 call 0)、case = 主採点 23×9 = 207 + 補助 66。

### 8.2 結果 (`work/f2/leaf_report.md`)

| # | block | plugin | VA | 機械語 B | IR 署名 | 主採点 (9 パターン) | 補助 case | **最終** | タグ |
|--:|--:|---|---|--:|---|---|---|---|---|
| 1 | 18953 | EQUO | 0x6cd8a0 | 8 | `i64(i64)` | mismatch 4/6/9 | match 2/2 | **match** (偽陽性、根拠 §8.1 本体) | memory_semantics |
| 2 | 18975 | Emphasizer | 0x6bfec0 | 56 | `i64(i64)` | match 6/6/9 | mismatch 1/5 | **mismatch** | fp_flag_unreflected,xmm_arg_drop |
| 3 | 18975 | Emphasizer | 0x6c8fc0 | 63 | `float(i64)` | mismatch 0/6/9 | - | **mismatch** | xmm_arg_drop |
| 4 | 18975 | Emphasizer | 0x6c9b60 | 83 | `float(i64,i64)` | match 2/2/9 | mismatch 2/4 | **mismatch** | fp_flag_unreflected,xmm_arg_drop |
| 5 | 18979 | Frequency Splitter | 0x662fc0 | 15 | `i64(i64)` | match 6/6/9 | - | **match** | - |
| 6 | 18979 | Frequency Splitter | 0x73e640 | 29 | `i64(i64)` | unexec(native_fault_all_patterns) 0/0/9 | match 7/7 | **match** | - |
| 7 | 18979 | Frequency Splitter | 0x73fa20 | 65 | `i64(i64,i64,i64)` | mismatch 4/5/9 | match 7/7 | **match** (偽陽性、根拠 §8.1 本体) | wasm_trap |
| 8 | 18979 | Frequency Splitter | 0x73fa70 | 73 | `i64(i64,i32,i64,i64)` | unexec(hang) 0/0/9 | match 7/7 | **match** | - |
| 9 | 18982 | Fruity 7 Band EQ | 0x6b0ef0 | 1554 | `i64(i64,i64)` | mismatch 0/6/9 | - | **mismatch** | arg_drop,spill_slot_deref,xmm_arg_drop |
| 10 | 19005 | Fruity Fast LP | 0x5de300 | 31 | `i64(i64,i64,i64)` | match 1/1/9 | match 4/4 | **match** | - |
| 11 | 19005 | Fruity Fast LP | 0x6c8c90 | 171 | `i64(i64,i64,i64,i64)` | mismatch 0/3/9 | - | **mismatch** | arg_drop,fp_flag_unreflected,spill_slot_deref,xmm_arg_drop |
| 12 | 19006 | Fruity Filter | 0x5de250 | 23 | `i64(i64)` | match 6/6/9 | - | **match** | - |
| 13 | 19006 | Fruity Filter | 0x6cc2e0 | 171 | `i64(i64,i64,i64,i64)` | mismatch 0/3/9 | - | **mismatch** | arg_drop,fp_flag_unreflected,spill_slot_deref,xmm_arg_drop |
| 14 | 19013 | Fruity Free Filter | 0x6ca5c0 | 1554 | `i64(i64,i64)` | mismatch 0/6/9 | - | **mismatch** | arg_drop,spill_slot_deref,xmm_arg_drop |
| 15 | 19059 | Fruity Parametric EQ 2 | 0x6e9440 | 29 | `i64(i64)` | unexec(native_fault_all_patterns) 0/0/9 | match 7/7 | **match** | - |
| 16 | 19059 | Fruity Parametric EQ 2 | 0x6ec2a0 | 65 | `i64(i64,i64,i64)` | mismatch 4/5/9 | match 7/7 | **match** (偽陽性、根拠 §8.1 本体) | wasm_trap |
| 17 | 19059 | Fruity Parametric EQ 2 | 0x6ec2f0 | 73 | `i64(i64,i32,i64,i64)` | unexec(hang) 0/0/9 | match 7/7 | **match** | - |
| 18 | 19059 | Fruity Parametric EQ 2 | 0x6f1650 | 28 | `float()` | mismatch 0/9/9 | - | **mismatch** | xmm_arg_drop |
| 19 | 19059 | Fruity Parametric EQ 2 | 0x6f1c40 | 29 | `i64(i64)` | match 6/6/9 | - | **match** | - |
| 20 | 19059 | Fruity Parametric EQ 2 | 0x6f1c60 | 25 | `i64(i64)` | match 6/6/9 | match 5/5 | **match** | - |
| 21 | 19059 | Fruity Parametric EQ 2 | 0x6f2320 | 20 | `i64(i64)` | match 5/5/9 | - | **match** | - |
| 22 | 19059 | Fruity Parametric EQ 2 | 0x6f2370 | 55 | `i64(i64,i64)` | match 6/6/9 | - | **match** | - |
| 23 | 19059 | Fruity Parametric EQ 2 | 0x6f23b0 | 17 | `float(i64,i64)` | unexec(native_fault_all_patterns) 0/0/9 | match 4/4 | **match** | - |

最終判定 23 関数: **一致 15 / 不一致 8 / 実行不能 0**
主採点のみ: 一致 9 / 不一致 9 / 実行不能 5。 case 207: native 完走 93 (equal 56 / diff 35 / wasm_trap 2)、比較不能 114
補助採点 12 関数: case 66 (equal 60 / diff 6 / wasm_trap 0 / 比較不能 0)
最終 mismatch のタグ (該当関数数): xmm_arg_drop 8, fp_flag_unreflected 4, arg_drop 4, spill_slot_deref 4
最終 mismatch のうち callee 無しで差分 (自己欠陥確定): 8
比較に使った equal case 数が 3 未満の match (検出力弱): なし

- 列「主採点」= `verdict equal/native完走/全case`、「補助 case」= `verdict equal/全case`。
- 最終 mismatch の機械語側の所見(全て `xmm_arg_drop`):入力の float を IR が持たない。0x6f1650 は機械語 `movaps xmm0,xmm1` が IR で `__asm_movaps(0)` (xmm1 の代わりに 0) になる。0x6bfec0 は補助 case 5 のうち 4 で不一致、0x6c9b60 は 4 のうち 2 で不一致 (xmm 入力の値次第で結果が変わる経路)。
- 0x6c9b60 (native 完走 2/9 case で一致)・0x6bfec0 (完走 6/9 case で一致) の主採点「一致」は、xmm 入力が `xfill` の固定値のままの 9 パターンでは差が出なかっただけで、補助 case (xmm 入力を振る) で初めて不一致を検出した(差が出なかった理由の詳細解析は未実施)。他の match 関数は §8.3 のネガコンで検出力を確認した。
- **一致 15 関数は全て `arity_x`=0 (機械語が xmm0..3 を入力に読まない)、不一致 8 関数は全て `arity_x`≥2**(liftdiff の機械語静的解析: 命令の read-before-write)。「xmm 入力を取る関数 = 不一致」と完全に分かれる。
- 同一コードの組は同じ結果: 0x73e640=0x6e9440・0x73fa20=0x6ec2a0・0x73fa70=0x6ec2f0・0x6b0ef0=0x6ca5c0・0x6c8c90=0x6cc2e0。

### 8.3 ネガティブコントロール (`nc_leaf.py`)

ベースライン最終 match の関数だけを対象に、block・kind ごとに IR を複製して**対象関数にだけ変異を 1 箇所**入れ、同じ主採点+補助採点で再採点する。

| 変異 (kind) | 一致 15 関数のうち変異箇所がある関数 | 変異後 mismatch (検出) | match のまま (未検出) |
|---|--:|--:|--:|
| `store_drop`: alloca 以外へ書く最初の `store` を削除 (D3 (DEFECTS.md) 型) | 6 | **6** | 0 |
| `load_drop`: alloca 以外から読む最初の整数/float `load` を 0 に置換 (D4 (DEFECTS.md) 型) | 11 | **11** | 0 |
| `offset_shift`: 最初の `add i64 %v, N` (N>0) を N+8 に (フィールド/配列オフセット誤り) | 13 | **13** | 0 |

- 合計 30 変異 / 30 検出。ベースライン (無変異) の同関数は全て match なので、不一致は変異に帰属する。変異箇所の行番号・変異前後は `work/f2/nc/nc_result_*.json`。
- **選択バイアスの開示**: 最初の実行 (補助 case 追加前) は 3 変異が未検出だった (`load_drop`: 0x6bfec0・0x6f1c60、`offset_shift`: 0x6f1c60)。0x6bfec0 は補助 case で不一致に覆り対象外になり、0x6f1c60 (`[this+0x360]==1 && [this+0x361]!=0` 型) は 2 byte を振る補助 case を足して検出した。上表は追加後の再実行値で、**ネガコンを見て case を足した分、検出力の評価としては楽観的**。
- 変異の検出信号は戻り値・書換えメモリの差分 (`ret` / `mem`)。変異ごとの主採点だけの検出か補助 case での検出かは区別していない。

### 8.4 限界・範囲外

- native 参照は Linux 上の機械語直接実行。Windows 実機・FL Studio 内の呼出しとは別 (`PEB/TEB` は ld_core の偽 TEB)。leaf 23 関数は import を呼ばない (強い leaf、`xcheck_leaf.py`)。
- match は「9 パターン + 補助 case で bit 一致」。ネガコンの未検出が示すとおり、真偽フラグ型の関数は random では検出力が弱く補助 case で補った。**全 15 関数について入力空間の網羅は未実施**(一致 15 関数は 8 B〜73 B の小関数。大きい 1554 B の 2 関数 (0x6b0ef0・0x6ca5c0) は不一致)。
- xmm 入力を取る関数は IR 署名に float 引数が無いため、native にだけ `f:<bits>` で渡す補助 case でしか検出できない(0x6bfec0・0x6c9b60 の例)。一致 15 関数は xmm 入力を取らないので、この限界の対象外。float をメモリから読む 0x5de300 (`cvtss2sd` 2 本) と 0x6f23b0 は、補助 case (1.5 / -2.25 / 3 / 1e10 / -0 / NaN / denormal / inf を含む) で全て bit 一致。
- icall 復元 (#514) 後の IR は対象外 (本件の 23 関数は機械語に間接 call が無いので #514 の影響を受けない)。

### 8.5 未解決 (起票先) と DEFECTS.md 行案

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 不一致 8 関数は xmm 引数脱落 (D5)。`lift_ranges.sh` 鎖に ARG pass 未接続。うち 4 は `spill_slot_deref`、4 は `fp_flag_unreflected` | eq-filter の float 入力を取る leaf が全滅。Eff_Render 側も同じ原因を持つ可能性が高い (§3 の入口は間接 call 脱落が先) | **#547 [PLG-F2-4]** (親 #199) |
| liftdiff 比較系の偽陽性 2 類型: (a) 部分上書きされた ptr 入り 8B ブロックを `cmp_mem` が正規化できない (0x6cd8a0)、(b) wasm 1 s 打切りによる偽 `wasm_trap` (0x73fa20・0x6ec2a0) | 主採点だけだと 3 関数が不一致に見える。補助 case と `ARTIFACT` 表で上書きしている | **#548 [LD-11]** (親 #122) |
| 主採点 9 パターンの検出力不足 (真偽フラグ・ptr 鎖・float 入力型の関数で native 全滅/偶然一致) | 補助 case を手で足した。他 block の leaf 拡大時に再発 | #235 ([LD-4], 被覆拡大) にコメント |
| 手順 2〜4 (framework link・Host shim・Render test .flp E2E) と `Eff_Render` の差分 | 出口条件 (差分試験 bit-exact) の残り | 既存 #195 / #196 / #197 完了待ち。#199 に残す |

DEFECTS.md 行案 (PM 判断で追記): `D17 | ours (harness) | 新規 (#515) | 部分上書きされた ptr 入りワードが偽の mem 差分になる | compare.cmp_mem が書込み後の語を ptr と認識できず delta (0x400000) 差を不一致とする | EQUO 0x6cd8a0 (byte 1 を [this+0x35af] へ) 主採点 2/9 case で偽 diff、ptr 無し arena では equal | native−wasm = delta かつ書込み byte 以外同値 | byte 単位比較`、`D18 | ours (harness) | 新規 (#515) | ループ長が引数依存の関数が wasm 1 s 上限で偽 wasm_trap | ld_runner.mjs の vm timeout=1000 ms (native 上限は 10 s) | 0x73fa20 / 0x6ec2a0 (count 下位 32bit ≒ 5.7e8 回) pall | native 完走 + wasm timeout で loop 幅が引数由来 | timeout の target 指定`。

### 8.6 再現

```sh
source tools/shared/env.sh && source tools/plugins/f2/env.sh
bash tools/plugins/f2/f2_step1.sh        # 前提 work/ (§1)。済みなら 51 秒
bash tools/plugins/f2/leaf_diff.sh       # 23 関数の列挙 → target 生成 → liftdiff 主採点 → 補助採点 → 集計 → 別算法検算
python3 tools/plugins/f2/nc_leaf.py      # ネガティブコントロール (kind ごとに並列なら --kinds X --run-only を 3 本 → --reuse)
```

| ファイル | 役割 |
|---|---|
| `leaf_list.py` | 対象 23 関数の列挙 (`--expect 23` で件数を assert) |
| `mk_targets.py` | block ごとの liftdiff target JSON・wasm image・VA 一覧・i128 ABI アダプタ |
| `leaf_diff.sh` | 上記の 1 コマンド駆動 |
| `leaf_custom.py` | 補助採点の手作り case と `ARTIFACT` 表 |
| `leaf_report.py` | 主採点+補助採点の集計 (表・件数) |
| `nc_leaf.py` | ネガティブコントロール (store 脱落 / load 脱落 / オフセット誤り) |
| `xcheck_leaf.py` | 別算法検算 (IR 本文の独立走査 + 機械語の関数別線形 sweep で 23 関数を再導出、同一コード判定) |

### 8.7 実測時間・再現性

測定環境: GitHub Actions runner 4 core (`nproc`=4)、他の重い処理なし。`leaf_diff.sh` = 23 関数の列挙 → target 生成 → 主採点 (block ごとに shard 4) → 補助採点 → 集計 → 別算法検算の全体。

| 実行 | 所要 (秒) | load average (1 分) 開始 → 終了 | `leaf_report.md` md5 先頭 12 桁 |
|---|--:|---|---|
| warm 1 | 129 | 0.27 → 0.31 | 8a33cc049389 |
| warm 2 | 128 | 0.31 → 0.91 | 8a33cc049389 |
| warm 3 | 129 | 0.91 → 0.33 | 8a33cc049389 |
| cold (`tools/liftdiff/work/eqf*` を削除して実行) | 133 | 0.20 → 0.57 | 8a33cc049389 |

- warm 3 回は **128〜129 秒**、cold は **133 秒**。`leaf_report.md` と最終判定 JSON (`functions` の md5) は 3 回とも一致 = 決定的。warm の内訳: liftdiff の wasm ビルドは mtime ガード (`newer(ir, ...)`) で再利用され、`mk_targets.py` が image を毎回再生成する。
- 前提 `f2_step1.sh` を `tools/plugins/work/` 無しで実行した初回 = **6 分 55.8 秒** (`time` 実測、`win_funcs.py` が支配的; load average は Pool(14) で最大 16.3)。work/ があれば §1 のとおり 51 秒。
- `nc_leaf.py`: kind ごとに並列 (3 プロセス) で 55.4 秒 (`store_drop`) / 65.1 秒 (`load_drop`) / 81.3 秒 (`offset_shift`)。
- `find tools/plugins/f2 -type f -size +20M` = 0 件、`git status --porcelain=v1 -- tools/plugins/f2` はコミット前にクリーン。

### 8.8 HEAD faacabb での再実測 (差し戻し修正後、4 core runner、逐次、同一 run)

| コマンド | rc | 所要 (秒) | load average (1 分) 開始 → 終了 | 結果 |
|---|--:|--:|---|---|
| `f2_step1.sh` | 0 | 302 | 0.18 → 8.31 | IR leaf 55 / 機械語でも間接 call 無し 23、dispatch 549 + waived 1 = 550 |
| `leaf_diff.sh` | 0 | 131 | 7.64 → 1.22 | 最終判定 一致 15 / 不一致 8 / 実行不能 0。主採点 一致 9 / 不一致 9 / 実行不能 5、case 207 (native 完走 93)、補助 66 |
| `nc_leaf.py` | 0 | 194 | 1.13 → (終了時 未採取) | store_drop 6/6、load_drop 11/11、offset_shift 13/13 検出 |

- `f2_step1.sh` の 302 秒は §8.7 の 51 秒 (work/ あり) と異なる。この worktree では `tools/plugins/work/` を再生成したため (win_funcs が支配的)。

## 9. PLG-F2-4 (#547): xmm 引数復元 pass の接続 (**未達: 不一致 8 のまま・中間報告**)

- 検証起点 commit: **1191aef** (`547-plg-f2-4-xmm-argpass`、#553 の branch `515-plg-f2-3-leaf-diff` 758a06b 基点)。`git status --porcelain=v1` は 0 行 (コミット済み HEAD で実測)。数値は下記 9.4 の 3 コマンドをこの HEAD で実行して取得 (初版は 875ab8e で、レビュー指摘の修正 (9.5) 後に再測した)。
- 既知類型との関係: **(DEFECTS.md) D5** (xmm 引数脱落)。D4 系 `spill_slot_deref` 4 / D1a `fp_flag_unreflected` 4 は本件では未着手。
- 範囲: pass の実装と鎖への opt-in 接続、eq-filter 6 block での lift/`emcc -c`/`leaf_diff.sh` 実測。既定鎖への ON 化・ablation 完走は範囲外 (下記)。

### 9.1 結論
1. `ir7_argpass.py` は OTT `setParameter` (function_180120af0) 専用 (jump table を dsm から再生成する) で、汎用の xmm 復元ではない。鎖に繋げても eq-filter には効かない。汎用品は kernel 向け `p0c/k80_argfix.py` + `p0c/k80abi.py` (#254 系) だったので、その [A]/[C] を再利用する `lift/passes/fix_xmm_args.py` を新規作成した。k80abi の `scan_function` で関数ごとの xmm 入力 slot を機械語から求め、IR 署名の slot 位置 N に `float`/`double` 引数を足す (隙間は `i64 %padN`)。closure 内の呼出し元には 0 / 0.0 を渡す。
2. `lift_ranges.sh` に **opt-in `PLUG_XMMARG=1` (既定 0)** で接続した。既定 ON にしていないのは、下記 3 の結果が出ておらず全 plugin への影響を測っていないため。
3. **受入条件 1 は未達**: `PLUG_XMMARG=1 PLUG_ICALL=0` で 6 block (18975 18982 19005 19006 19013 19059) を lift し直した `leaf_diff.sh` の最終判定は **一致 15 / 不一致 8 / 実行不能 0** (接続前と同一)。タグ集計は `xmm_arg_drop 7`・`ret_only 1` (接続前は `xmm_arg_drop 8`; 差の 1 は 0x6f1650 の分類が分類器修正 (9.5 の C1) で変わったもので、不一致自体は残っている)。
4. 受入条件 2 (回帰) は、一致 15 が一致のままであることだけ確認 (上記 3 の同判定)。**ablation (pass を外すと 8 関数が戻る) は無意味**: pass 有無で不一致が同数のため、ネガコンとして成立していない。
5. 受入条件 3 (#232 / #233 の適用可否判定) は未実施。

### 9.2 実測 (`PLUG_XMMARG=1`、block ごとの `p.xa.json`、HEAD 1191aef)
| block | 復元した関数 | skip した関数 (内訳) | call site に 0 を渡した数 | `emcc -c` rc |
|--:|--:|--:|--:|--:|
| 18975 | 3 | 12 (`slot_occupied` 6 / `no_placeholder` 5 / `partial_slots` 1) | 4 | 0 |
| 18982 | 1 | 2 (`slot_occupied` 1 / `no_placeholder` 1) | 1 | 0 |
| 19005 | 2 | 3 (`slot_occupied` 2 / `partial_slots` 1) | 3 | 0 |
| 19006 | 2 | 2 (`slot_occupied` 2) | 2 | 0 |
| 19013 | 3 | 1 (`slot_occupied` 1) | 3 | 0 |
| 19059 | 1 | 11 (`slot_occupied` 6 / `no_placeholder` 4 / `partial_slots` 1) | 1 | 0 |

- 875ab8e 版 (初版) は 18975 が 4 関数・19005 が 3 関数・19059 が 2 関数を「復元」としていたが、うち 3 関数 (`function_6c1580` recovered=xmm0,xmm1 / machine=xmm0..3、`function_6c86b0` recovered=xmm2 / machine=xmm1,xmm2、`function_6f1f30` recovered=xmm1,xmm2 / machine=xmm0..2) は機械語が読む slot の一部しか placeholder に接続できていない半端な復元だった (Copilot 指摘)。現行版は `partial_slots` として署名を変えずに skip する。
- 不一致 8 関数の内訳: IR 署名が機械語 ABI と一致するようになったのは **3 関数** (0x6b0ef0 `i64(i64,i64,double)`、0x6ca5c0 同、0x6f1650 `float(i64,float)`)。0x6bfec0・0x6c8fc0・0x6c9b60 は `no_placeholder` で署名が変わらない (RetDec の placeholder が `xor i128 0,0` の形をしていない: 0x6bfec0 は `__asm_movss__4` 結果を `ucomiss` に渡す形、0x6c8fc0 は `__asm_addss(i128 %1, ...)` の %1 が `xor i128 0,0` だが [C] の突合が不成立)。0x6c8c90・0x6cc2e0 は `slot_occupied` (RetDec が slot 3 を整数 `%arg4` で宣言済み)。
- 署名が直った 0x6f1650 でも、case z で native x0=0x3f11c71c、wasm x0=0xffc00000 (NaN) で不一致のまま。引数が値として届いていない。**原因は未特定** (候補: `mk_targets.py` の i128 ABI アダプタが `%pad0` を含む仮引数をそのまま実引数に使う / liftdiff の float 引数の割当て位置 / `__asm_movaps` の i128 上位ビット)。
- **2 つの機械語解析の食い違い (新規所見)**: 0x6b0ef0 は pass が使う `k80abi.scan_function` では xmm 入力 slot = `xmm2` のみ (幅 64) だが、liftdiff の `ldlib/pe.py` の解析では `xmm_slots=[1,2,3]` (`arity_x`=4)。pass は xmm2 だけを `double` で足すので、liftdiff の見方では slot 1・3 が未復元のまま残り、0x6b0ef0・0x6ca5c0 は分類器修正後も `xmm_arg_drop` が付く (上表の 7 のうち 2)。どちらの解析が正しいかは未確認 (起票: 9.3)。

### 9.3 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 署名が直った 0x6f1650 / 0x6b0ef0 / 0x6ca5c0 でも差分が残る原因の特定 | 受入条件 1 | 新規 [PLG-F2-5] = #613 |
| k80abi (`scan_function`) と liftdiff (`ldlib/pe.py`) の xmm 入力 slot 解析の食い違い (0x6b0ef0: xmm2 のみ vs xmm1..3) の解消 | pass の復元 slot 集合の妥当性。どちらかが誤り | #613 |
| `no_placeholder` (計 10 関数 = 5+1+4 の block 別合計; 同一コードの重複あり)・`slot_occupied` (RetDec が xmm 位置を整数引数で宣言) の復元 | 受入条件 1 | #613 |
| `partial_slots` 3 関数 (6c1580 / 6c86b0 / 6f1f30) の全 slot 復元 | 部分復元を適用しないことにしたため未復元のまま | #613 |
| 呼出し元の xmm 値の接続 (現状 0 を渡す) | closure 内の呼出し経由では float 値が失われたまま | #613 |
| call 以外の `@function_xxx` 参照 (関数ポインタ・ptrtoint 定数式・他関数の引数) を持つ関数は `non_call_ref` で skip する (署名を変えると参照側の型と食い違うため)。参照側の型更新は未対応 | 該当関数は復元できない (今回の 6 block では `non_call_ref` skip 0 件) | #613 |
| spill_slot_deref 4 / fp_flag_unreflected 4 の #232 / #233 適用可否 | 受入条件 3 | #613 |
| PLUG_XMMARG 既定 ON 化と、全 block での `emcc -c`・matrix 突合の回帰 (6 block のみ実測) | 既定化の可否 | #613 |

### 9.4 再現と実測 (HEAD 1191aef、4 core Actions runner)
```sh
source tools/shared/env.sh && source tools/plugins/f2/env.sh
time bash tools/plugins/f2/f2_step1.sh                                                              # 前提 (PLUG_ICALL=0 の既定鎖)
cd tools/plugins && time PLUG_XMMARG=1 PLUG_ICALL=0 bash lift/batch_lift.sh 18975 18982 19005 19006 19013 19059; cd ../..
time bash tools/plugins/f2/leaf_diff.sh                                                             # 最終判定の再計算
bash tools/plugins/f2/nc_leaf.py の 3 kind 並列 (--kinds K --run-only) → python3 tools/plugins/f2/nc_leaf.py --reuse
```
| コマンド | `time` の real | 開始時 load average (1 分) | 結果 |
|---|--:|--:|---|
| `f2_step1.sh` (`work/` 生成済み。`win_funcs.py` 初回は別途 **517 秒**、終了時 load 16) | 0m51.042s | 8.78 | exit 0、matrix DIFF count = 0 |
| `PLUG_XMMARG=1 PLUG_ICALL=0 batch_lift.sh` (6 block) | 0m21.675s | 4.49 | 6/6 lift_rc=0・`emcc -c` rc=0 |
| `leaf_diff.sh` | 2m22.983s (スクリプト内の `LEAF_DIFF elapsed` = 143 s) | 3.30 (終了時 0.97) | exit 0。一致 15 / 不一致 8 / 実行不能 0。別算法 `xcheck_leaf.py` 集合一致 EQ |
| `nc_leaf.py` (3 kind 並列 → `--reuse` 集計) | 87 s (並列部) | 0.88 | rc=0。`store_drop` 6/6・`load_drop` 11/11・`offset_shift` 13/13 検出、未検出 0・unexec 0 |

- 初版の「133 秒、load 0.29」は §8.7 の cold 実行 (133 s) と秒数が偶然一致していたが、初版時に `time` 出力を残していなかった。上表は今回の再測で、`time` の出力そのもの。
- ネガコン `nc_leaf.py` は、変異が 1 つでも match のまま / unexec なら exit 1 (9.5 の C2)。上記は全検出で rc=0。

### 9.5 レビュー指摘への対応 (oc-reviewer / Copilot)
| ID | 指摘 | 対応 |
|---|---|---|
| R1 | REPORT 250 行上限超過 | §8・§9 を本付録へ無変更で分割。本体 208 行、DOC_MAP 更新 |
| R2 | §5 表の行が壊れている | セル内に収めた (指摘の「§1」は実際は §5 の表) |
| P1 | `fix_xmm_args.py` の call 書換え regex が定数式で切れる | 括弧の対応を取る書換えに変更。call 以外の `@function_xxx` 参照を持つ関数は `non_call_ref` で skip。未使用の `done`・`if True:` を削除 |
| P2 | 半端な slot 復元を `fixed` にする (Copilot) | 復元 slot 集合が機械語の slot 集合と一致しなければ `partial_slots` で skip し、k80_argfix が数えた件数も戻す |
| C1 | 分類器が slot 位置でなく個数で `xmm_arg_drop` を付ける (Copilot) | `ldlib/pe.py` が `xmm_slots` を出し、`classify.py` は全 slot が IR 署名の同位置で float/double ならタグを付けない |
| C2 | ネガコンが未検出でも exit 0 (Copilot) | 未検出・unexec があれば exit 1 |
| C3 | 古い生成物が再実行・集計に混ざる (Copilot) | `leaf_diff.sh` が targets / leaf / leaf_custom の生成物を消してから再生成 |
| C4 | `/opt/emsdk` の直書き (Copilot) | `[EMSDK]` (docs/REFERENCES.md) 参照に変更 |
