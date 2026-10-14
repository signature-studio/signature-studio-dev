# REPORT_2143 — F4 偽陰性 4 件の機械語切り分けと F4 ネガコン (#2143 / 親 #1866)

親: #1866 / 関連: #1647・#564 / 前提の一覧: `REPORT_1866.md` §3

## 1. 測定条件

- 測定 commit: `6444b186` (測定に使った main 作業ツリー)。本 PR の起点は `76168f2a` (origin/main)。
  `git diff 6444b186 76168f2a -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/m11_gen_ir2.sh tools/m11/m11_lift.sh tools/m2 tools/m5` の出力は 0 行
  (差分は #2141 の REPORT・結果 JSON のみ)。本 PR のコード差分は `repro_2143.sh` の追加 (69 行) のみ。計測対象 (`audit_undefload*.py`・`ldfix.py`・`m11_gen_ir2.sh`) の差分は 0。
- 入力 IR は 2 種類。**監査 (§1・§3) は norm0、F4 (§4・§5) は pre IR** で、混ぜない。
  - norm0: `work-m11` 素材の `tools/m11/work/boot0..4.norm0.ll` (`NORM0` に渡す)。
  - pre IR: `M11_LDFIX=0 bash tools/m11/m11_gen_ir2.sh` が出す `work/boot_final.ll` (ldfix 適用前)。`BOOT_FINAL` に渡す。§4 に作成手順を書く。
  - `ir_conditions.json` は素材に無い。`boot5`・`boot6`・`functions_dll.csv` も素材に無く、`m11_gen_ir2.sh` の完全再生成は行っていない。
    したがって本 REPORT の数値は **素材の norm0 を入力とした監査の実測** であり、`REPORT_1866.md` の再生成 IR (sites 2,737) とは直接比べない。
- PE: `fl-win64` `extracted/block00031_PE.bin` (22,227,016 B)。
- 監査: `audit_undefload_dest.py` 5 入力 (boot0〜boot4 の norm0)。**55.4 秒** (user 55.0 秒)、load average 0.52〜0.64 (4 vCPU)、rc 0。
  **n=1 (1 回測定)。min–max は未取得。** 再現: `repro_2143.sh audit` (`time` 付き)。
  出力: sites 2,729、`DEST_FRAME_IN_ESCAPED` 18・`REGLIVE` 2,502・`NOADDR` 193・`DEST_FRAME_OTHER` 9・`DEST_MEMREAD` 6・`DEST_RIPREAD` 1。
- 旧監査 `audit_undefload.py` の sites は本セッションで測っていない (数値は引かない)。
- **単位と分母** (数値ごとに 1 行。数え方は `audit_undefload.py` `scan_text` と `audit_undefload_dest.py` `main` の実装):

  | 数値 | 単位 | 分母・除外 | 再現 |
  |---|---|---|---|
  | scan records 2,846 (元入力) / 5,185 (`uselistorder` 除去後) | 名前無し alloca からの load 1 件 (`scan_text` の yield 1 件)。consumer 0 件も含む | 5 入力 norm0 の合計。`alloca` が `uselistorder` 等の load 以外の行で使われる関数の alloca は除外 | `repro_2143.sh strip` の `scan norm0` / `scan stripped` 行 |
  | sites 2,729 (audit 出力) | 上の load 1 件のうち、直接 memop の無い consumer (REGLIVE 扱い等) を 1 件以上持つもの (`audit_undefload_dest.py` `main` の `sites.append`。直接 memop の consumer は分類から除く) | 区分の合計 18+2,502+193+9+6+1 = 2,729 | `repro_2143.sh audit` の `sites` 行 |
  | sites 4,910 (`uselistorder` 除去後の dest 版) | 上と同じ (dest 版 audit 出力) | 5 入力 norm0 の合計 (除去後) | `repro_2143.sh strip` の `audit stripped` |
  | `DEST_FRAME_IN_ESCAPED` 18 / 97、関数 18 / 61 | 分類された load 1 件 / 関数 (`fns_by_class`) | 上の sites の内訳 | 同上 |
  | F4 件数 10 / 0 | `fix_f4` が書いた `ldf4_*` 読み出しの件数 | F4 有 IR / F4 無 IR の 1 本ずつ | `repro_2143.sh f4` の `ldf4 on=` 行 |

  注 (推定。コードの読みで、実測していない): scan records 2,846 と sites 2,729 の差は、scan が consumer 0 件の load も数え、audit が「直接 memop の無い consumer が 1 つも無い」record を落とすことによると読める。
  §3 の旧記載「関数 2,729 → 3,442」は、2,729 が sites の件数と同じで単位が混ざっているため、**未検証として引用しない**。関数数は `repro_2143.sh strip` の `scan records ... functions` 行で確定する (本 run では未実行)。

## 2. 受入条件 1: REGLIVE になる原因の機械語切り分け

受入条件の分類は、`trace_dest` (`audit_undefload_dest.py`) の結果を機械語で手で確かめた。

| 関数 | consumer (IR `!insn.addr`) | 機械語 | consumer が読むレジスタ | 直前に書いた命令 | 判定 |
|---|---|---|---|---|---|
| 44d1c0 | `44d1d0` | `mov sil, 1` | なし (`sil` は書き込みのみ。`reads_of` は `[]`) | — | REGLIVE は正しい。undef の値は `and i64 %1, -256` の `%1` だが、機械語では `sil` の部分書き込みで、undef 読みの命令にならない |
| 69c360 | `69c381` | `not eax` | `eax` | `69c37e sub eax, 1` (read-modify-write。`eax` のメモリ read は無い) | 直前の writer が `sub eax,1` のため、`trace_dest` は `mem_read_of` が None を返して REGLIVE。writer chain の先 (`69c378 mov eax,[rip+0xf58576]`) まで辿らない |
| 977e40 | `977e4b` | `movdqa [rbp+0x30], xmm6` | `xmm6`・`rbp` | 直前の writer が無い (関数先頭 `977e40`〜`977e48` は push/sub/mov rbp) | `xmm6` は関数入口の live-in (`GPR_SET`・xmm の追跡を持たない)。REGLIVE は近似として正しい。値の出所は関数外 |

ここから分かる原因は次の 2 つ。

- **44d1c0・977e40**: consumer 命令が「値を読む」ではなく「部分書き込み」か「入口 live-in の xmm 転送」であり、dest 追跡の対象 (GPR の直前 writer) に当たらない。F4 の監査は GPR の writer だけを見るため、ここは仕様どおり REGLIVE。
- **69c360**: 直前 writer が `sub eax,1` という **read-modify-write** で、`trace_dest` は「メモリ read を持つ writer」だけを返す。
  `sub` は `mem_read_of` の対象外のため、`BACK_MAX` (16 命令) 内でも writer chain を続けない。これが REGLIVE の直接原因。

本節の機械語の確認は手作業 (作者の逆アセンブル読み)。本 run では再実行していない。

## 3. 受入条件 1 (続き): 132e8e0 の consumer が監査の site 抽出に載らない理由

- 132e8e0 の undef load は `boot3.norm0.ll` の `%1 = load i64, ptr %0`・`%2 = load i64, ptr %0` (`%0 = alloca i64`)。
  `%1`・`%2` の使われ方は `call @function_8087c0(%13, %stack_var_-40, %1)` と `call @function_808b50(%13, %2)` の 2 箇所だけ。
- 機械語上の consumer は `132e9b8 call 0x8087c0` と `132e95e call 0x808b50` で、どちらも **call の引数渡し** (`reads_of` は `rip`・`rsp` のみ)。
  メモリ read を持たないので、監査は REGLIVE (`trace_dest` の結果も REGLIVE)。
- **監査の site 抽出で落ちる直接原因**: `boot3.norm0.ll` の `function_132e8e0` 本文に `uselistorder ptr %0, { 1, 0 }` 行がある。
  `scan_text` (`audit_undefload.py`) は、`%0` を含み `load` 以外の行を見つけると alloca を「bad」として除外する。
  `uselistorder` 行はその「load 以外の使われ方」に当たるため、132e8e0 の `%0` は site 抽出から外れ、関数ごと 0 件になる (`scan_text` の結果が空)。
  - 実測 (作者記録): `uselistorder` を含む元の norm0 では `function_132e8e0` の scan 結果は 0 件。同じ関数から `uselistorder` 行だけを除くと、`%1`・`%2` の 2 site が出る (`cons` 1 件ずつ)。
    再現: `repro_2143.sh strip` の `function_132e8e0 scan sites (consumers >= 1) per input` 行で、元入力 0・除去後 2 を見る (本 run では未実行)。
  - 全体: `uselistorder` 行を全 norm0 から除くと、scan records (単位は §1 の表) は **2,846 → 5,185 (+2,339)**。関数数は §1 の注のとおり未検証。
    `uselistorder` は LLVM の use-list order の注記で、値の意味は変えない。監査が注記で site を落としている。
  - 同じ 5 入力で `uselistorder` 行を除いた dest 版の実測 (単位は §1 の表): sites 4,910・`DEST_FRAME_IN_ESCAPED` 97 (元入力は 18)・`REGLIVE` 4,461 (元入力は 2,502)。
    関数単位では `DEST_FRAME_IN_ESCAPED` 61 関数 (元入力は 18 関数)。増えた分は F4 修復対象 10 関数以外の関数。
    F4 修復 10 関数のうち dest 版で検出されるのは、元入力・除去後ともに 865020 の 1 件 (差 0)。
    再現: `repro_2143.sh strip` の `audit stripped` (n=1)。

再現 (§1・§3・§4・§5): `tools/m11/ldfix/repro_2143.sh`。環境変数 `PE`・`NORM0`・`BOOT_FINAL` を渡し、`bash tools/m11/ldfix/repro_2143.sh [all|audit|strip|f4|neg]`。
  `audit` = §1 の監査、`strip` = §3 の `uselistorder` 除去実験 (scan records と dest 版)、`f4` = §4 の F4 有無 IR 作成と件数、`neg` = §5 の検査 (`f4` の出力を前提とする)。
  **注: 本 run では素材 (`work-m11` の norm0・pre IR) が無く、`repro_2143.sh` は構文チェック (`bash -n`) のみ。数値は作者の実測で、再実行はしていない。**

## 4. 受入条件 2 (F4 の対象の構造): F4 が何を書き換えるか

F4 (`ldfix/ldfix.py` `fix_f4`) の修復は、`xor i64 0, 0` 残骸を **escape 済み名前付き `stack_var_*` の load** に置き換える。
`norm0` (F4 適用前) には名前付き `stack_var_*` の load が無い (`stack_var_*` は alloca として存在するが、監査は名前無し alloca だけを見る)。

入力: pre IR = `M11_LDFIX=0 bash tools/m11/m11_gen_ir2.sh` が出す `work/boot_final.ll` (ldfix 適用前)。`repro_2143.sh f4` の `BOOT_FINAL` に渡す。
`repro_2143.sh f4` は、この pre IR に F4 有 (既定) と F4 無 (`--no-f4`) の ldfix を掛けた 2 本 (`$OUT/2143_f4on.ll`・`2143_f4off.ll`) を作る。

以下の表は作者の実測 (本 run では未再実行)。関数別の件数は `repro_2143.sh f4` の `F4 <関数> on <n> off <m>` 行で再確認する。

| 関数 | F4 有 (`ldf4_*_v = load`) | F4 無 | F4 の参照先 |
|---|---|---|---|
| 132e8e0 | 1 | 0 | `stack_var_-40` |
| 44d1c0 | 1 | 0 | `stack_var_-48` |
| 69c360 | 1 | 0 | `stack_var_-56` |
| 977e40 | 1 | 0 | `stack_var_-64` |
| 865020 | 1 | 0 | `stack_var_-48` |
| 52a7f0・41ca30・666c30・71dd80・864f60 | 1 | 0 | 各 stack_var |

- `ldfix.py` の標準出力の F4 件数は、F4 有で 10、F4 無で 0 (作者実測。`repro_2143.sh f4` の `ldf4 on=... off=...` 行で `ldf4_` の行数として再確認できる)。
- F4 無の IR でも `xor i64 0, 0` の総数は 3,886 で、F4 有と同数 (作者実測。`repro_2143.sh f4` の `xor i64 0,0 on=... off=...` 行)。F4 は `xor` を消すのでなく、**別の位置の read (`ldf4_*`) を追加**する。

## 5. 受入条件 3: F4 無し IR での検出数差 (ネガコン)

**結論: 監査の検出数は F4 の有無で変わらない (差 0)。** 理由は 2 点。

1. 監査の入力は `boot*.norm0.ll` (B1 前・ldfix 前) で、F4 は ldfix の後段で入るため、監査の入力は F4 の有無と無関係。
   `m11_gen_ir2.sh` の監査入力は `boot*.norm0.ll` 固定。
2. 実測 (作者記録): F4 有無の ldfix 出力 (`$OUT/2143_f4on.ll`・`$OUT/2143_f4off.ll`、既定 `${RUNNER_TEMP}/2143`) に dest 版監査を掛けると、どちらも **sites 0 / by_class {}**。
   再現: `repro_2143.sh f4` の後に `repro_2143.sh neg` (単独では前提ファイルが無く失敗する)。
   F4 が追加する `ldf4_*` の load は名前付き `stack_var_*` の read で、監査の site (名前無し alloca の undef load) に現れない。
   したがって検出数差は 0 (F4 有 0 件・F4 無 0 件)。

したがって「F4 を外した IR で同じ監査を実行して検出数差を見る」という受入条件は、**監査の設計上、差が出ない** (ネガコンとして成立しない)。
ネガコンとして成立させるには監査を「名前付き stack_var の read」を対象に拡張する必要があり、これは別の作業 (下記 §7 の子)。

## 6. 本 issue の判定

| # | 受入条件 | 状態 |
|---|---|---|
| 1 | 44d1c0・69c360・977e40 の REGLIVE 原因 (遡り範囲・書き手の形) を機械語で切り分ける | **達成** (§2) |
| 2 | 132e8e0 の consumer が監査の site 抽出に載らない理由 | **達成** (§3: `uselistorder` 行による除外。call 引数は REGLIVE) |
| 3 | F4 を外した IR で同じ監査を実行し、F4 修復関数の検出数差 (ネガコン) | **未達** → §5 で「差 0・監査設計上ネガコンが成立しない」を実測。成立させる作業は子 issue |

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `uselistorder` 行で `scan_text` が alloca を除外する (scan records +2,339) | 監査の site が実際より少ない。F4 系以外の脱落も見えない | #2201 [LD-85] (open。監査の site 抽出の変更として、コメントで範囲に追加を依頼。#2141 [LD-78] は CLOSED のため不可) |
| 監査が名前付き `stack_var_*` の read を見ない (F4 が対象とする型) | F4 のネガコンが監査で成立しない | #2201 [LD-85] |
| 69c360 型 (read-modify-write を挟んだ writer chain の先を辿らない) | REGLIVE の偽陰性が残る | #2202 [LD-86] |
| 旧監査 sites・ldfix 再生成 IR (`ir_conditions.json` 付き) での数値 | 本 REPORT は素材 norm0 での実測。REPORT_1866 の 2,737 と直接比べられない | #2144 [LD-80] |
