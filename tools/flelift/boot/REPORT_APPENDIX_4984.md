# tools/flelift/boot — 付録 (#4984): 既定 boot の unit 境界と ExitProcess(0) の判定

> 正本: 本ファイル。親 #4970 の未判定項目 (unit 895 の exit) の返却先。REPORT.md の 1 行結論は別途 #4970 に書く。
> 診断は `FLE_EXTRA_CCF=-DFLE_UNITLOG` のときだけ有効 (既定 boot の挙動・出力は変えない)。

## 1. 結論

- **前提の訂正**: `exit` は unit 895 の中では起きない。`units_run=895` は「dispatch した unit 数」で、添字は i=0〜940 (dispatch 895・empty 46・noproc 1 = 942)。最後に dispatch した unit は **i=940** (VA `0x13751d0`)。exit の呼出し点は `0x412a0d` (戻り先 `0x412a12`・ログの `call_site=0x412a12` による)。`InitUnits` (`f_4120c0`) が全 unit を回り終えた後に exit が起きたことは、ログの順序 (最後の `[unit] i=940` の後に exit) からのみ言える。静的な根拠は未確定: 今回の逆アセンブル (32 ビット・64 ビット) では命令境界が揃わず、`0x412a0d` の呼出し元と `f_4128b0`・`f_4120c0` の関数境界を確定できなかった (#5028)。
- **判定 (ExitProcess(0))**: **exit code 0 を確認。正常/異常は未確定**。exit code は `0x412a07` で `[0x13a5000]` を読んだ値で、読む時点の値が 0 (`[fleboot][exit] code=0`)。ただし exit 時点の 0 は「途中でエラーが無かった」の証拠ではない。`f_412770` (§3) が終了処理で 0 を書くため、途中の非 0 書込みは exit 時点では見えない。
- **未確定の理由**: `f_4128b0` が ExitProcess に至る枝の条件 `[0x15eac80]`・`[0x15e6068]` の exit 直前の値は測った (§6・全て 0)。`f_4096b0` の 4 呼出し元 (§3) のうち `0x412acf` は boot 中に実行されなかった (§6.1 陰性)。残りの 3 呼出し元 (`0x409553`・`0x409722`・`0x40c841`) は実行有無を未測定。この 3 件が無いと、exit が通った枝 (正常の枝か後始末の枝か) を判定できない。
- **未測定の子 issue**: #5028 (`[FLE-40]`・親 #4984)。#4970 の未判定項目には「正常終了」の判定を返さない。

## 2. 測定

- 測定 commit: `91e9cc35f` (コードを変えた最後の commit)。経路: 既定 (`FLE_IPP` 未指定 = mode 3・補修あり・`FLE_EXTRA_ROOTS` 既定)。
- HEAD 再測定 (`91e9cc35f`・診断なし): units 895・stopped 895・exit・IPP ok・rc 0・boot 5 s・load 1.47〜1.67。
- HEAD 再測定 (`91e9cc35f`・`FLE_EXTRA_CCF=-DFLE_UNITLOG`): unit 行 895・exit-ring 20・i=940 の行あり・rc 0。
- 実行: `FLE_EXTRA_CCF=-DFLE_UNITLOG bash tools/flelift/boot/fle6_measure.sh` (`FLE_BOOT_RUNS=default`)。
  工程: gen-A 5 s / lift 51 s (rss 610 MB) / clang plain 61 s / boot 5 s。load 最大 1.67。rc 0。
- 結果: `units_run=895`・`units_total=942`・`stopped_at=895`・`boot_threw=exit`・`exit=1`・IPP check `ok` (`ptr_15F34A0=0x7f10001c`)。
- 同じ経路の既定 (`-DFLE_UNITLOG` なし) でも units 895・exit・IPP ok (KPI は PR 本文)。

## 3. [0x13a5000] の書込み元 (PE 静的解析・capstone)

`[0x13a5000]` = `.data` の先頭 (RVA `0xfa5000`)。PE 上の初期値は 0。

| 位置 | 命令 | 役割 |
|---|---|---|
| `0x412a07` | `mov ecx, [0x13a5000]` | `ExitProcess` の引数を読む (呼出し点 `0x412a0d`)。注: 本表の番地は前の測定の記録で、今回の逆アセンブルでは再確認できていない (即値 `0xf925f3` が `0x13a5000` と一致しない) |
| `0x4127af` | `mov [0x13a5000], 0` | `f_412770` 内。0 を書く (終了処理の経路) |
| `0x412a44` | `mov [0x13a5000], ecx` | `f_412a40` 内。`ecx` (エラー番号) を書く |
| `0x4125e2` `0x41279e` `0x41293f` `0x412986` | 読出し | 終了処理の条件判定 |

`f_412a40` を呼ぶのは `f_4096b0` (`0x4096b0`: `mov [rdx 保存], rdx; call f_412a40`) で、その呼出し元は次の 4 箇所 (全件):

| 呼出し元 | 渡す ecx (エラー番号) |
|---|---|
| `0x409553` | 0xe7 |
| `0x409722` | (`ecx = [rax+rbx]`・表引き値) |
| `0x40c841` | 0xd2 |
| `0x412acf` | 0xd9 |

## 4. boot 中の値 (dynamic)

- unit 境界の `[0x13a5000]` は 895 行すべて `0x0` (i=0〜940)。測定したのは unit 境界だけで、unit の途中の値は見ていない。
- exit 直前の終了処理 (`f_412770`) が 0 を書くため、途中の非 0 は exit 時点では見えない。非 0 の有無は `f_4096b0` の 4 呼出し元への probe で測る必要がある。`0x412acf` は §6.1 で陰性。残り 3 件は未実施。

## 5. unit 境界 (dispatch 末尾 20 件)

`[unit] i=<添字> va=<proc> w13a5000=<値>` の行 (`FLE_UNITLOG`)。dispatch 順 895 番目が `i=940` (最後)。その直前 20 件 (`i=921`〜`i=939`) と i=940 自身:

| dispatch 順 | i | va | w13a5000 |
|---|---|---|---|
| 876 | 921 | 0x136b370 | 0x0 |
| 877 | 922 | 0x136b390 | 0x0 |
| 878 | 923 | 0x136c660 | 0x0 |
| 879 | 924 | 0x136c6a0 | 0x0 |
| 880 | 925 | 0x136c6c0 | 0x0 |
| 881 | 926 | 0x136c6e0 | 0x0 |
| 882 | 927 | 0x136c720 | 0x0 |
| 883 | 928 | 0x136c740 | 0x0 |
| 884 | 929 | 0x136d1b0 | 0x0 |
| 885 | 930 | 0x136d1d0 | 0x0 |
| 886 | 931 | 0x136d1f0 | 0x0 |
| 887 | 932 | 0x136d210 | 0x0 |
| 888 | 933 | 0x136d670 | 0x0 |
| 889 | 934 | 0x136d7d0 | 0x0 |
| 890 | 935 | 0x1374350 | 0x0 |
| 891 | 936 | 0x1375000 | 0x0 |
| 892 | 937 | 0x1375110 | 0x0 |
| 893 | 938 | 0x1375170 | 0x0 |
| 894 | 939 | 0x13751b0 | 0x0 |
| 895 | 940 | 0x13751d0 | 0x0 |

`ott_dispatch` 経由の直前 20 件 (`[exit-ring]`・古→新): `0x410070` ×3 / `0x1375000` / `0x40f960` / `0x407a50` / `0x40f960` / `0x407a50` / `0x410070` / `0x40f960` / `0x407a50` / `0x410070` / `0x407a50` ×2 / `0x410070` / `0x1375110` / `0x1375170` / `0x13751b0` / `0x13751d0` / `0x1376840`。直接 `call` は含まない (ring は `ott_dispatch` の target だけを記録する)。

## 6. #5028: exit 枝の判定 (diagnostic probe)

- **結論 (lift C の読みによる。実機照合は未実施)**: exit 直前の分岐条件は `[0x15eac80]=0`・`[0x15e6068]=0`・`[0x13a5000]=0` (実測ログ `[EXITBR-412a0d]`)。エラー番号を書く `f_412a40` は boot 中に入っていない (`[EXITBR-412a40]` 0 件)。`f_4096b0` の 4 呼出し元のうち `0x412acf` は boot 中に実行されなかった (§6.1)。残り 3 呼出し元 (`0x409553`・`0x409722`・`0x40c841`) の実行有無は未確定。
- 測定 commit: `916de996d` (コードを変えた最後の commit。以降 `tools/flelift/boot` の差分 0)。経路: 既定 (mode 3・補修あり・`FLE_EXTRA_ROOTS` 既定)。
- 実行: `FL_WIN64_DIR=<展開先> SS_EMSDK_ENV=<emsdk 6.0.12> bash tools/flelift/boot/exit_branch_probe.sh` (`fle6_measure.sh` で作った `work/boot/lift` を再利用し、`work/boot/lift_exitbranch` にだけ probe を入れる)。
  - 結果: `units_run=895`・`stopped_at=895`・`exit=1`・`[fleboot][exit] code=0 call_site=0x412a12`・IPP `ok`・probe 込みでも既定と同じ停止点。
  - 所要 1 分 52 秒 (実測・`measure_load` 相当の 1 秒サンプリング)。load 1 分平均の最大 2.55。
  - 既定 (`fle6_measure.sh`・probe なし) の同 commit 再測定: 所要 3 分 5 秒・load 最大 2.79・units 895・stopped 895・exit・IPP ok。
- probe 着床 (`dbg_lift.py`): 7 件中 6 件が着床。`0x412a0d`→`f_4128b0`, `0x4128b0`→`f_4128b0`, `0x4096b0`→`f_4096b0`, `0x412a40`→`f_412a40`, `0x409722`→`f_4096d0`, `0x409553`→`f_4094f0`, `0x40c841`→`f_40c820`。`0x412acf` は既定 root の lift には無く、`FLE_EXTRA_ROOTS` 経路で着床した (§6.1)。
- ログ行 (判定根拠・実測ログそのまま):
  ```
  [EXITBR-4128b0] ret=1376884
  [EXITBR-412a0d] w15eac80=0 w15e6068=0 w13a5000=0 b15eacb0=0 q15eaca0=0 q15eadb0=0 q15e60a0=0 b15eacb0_raw=0
  [fleboot][exit] code=0 call_site=0x412a12
  ```
  `[EXITBR-412a40]`・`[EXITBR-4096b0]`・`[EXITBR-caller]` は 0 件 (`grep EXITBR` の結果は上の 2 行 + `[exitbranch] EXITBR 行: 2`)。
- 呼出し位置の lift 行 (`work/boot/lift_exitbranch/fle_lifted_s2.c` / `s0.c` 由来・`0x4129f5` 以降):
  - `0x4129f5: jne 0x412a12` — `[0x15eac80]` が非 0 なら `0x412a12` へ飛ぶ (`ExitProcess` の呼出しを飛ばす)。
  - `0x412a07: mov ecx, [0x13a5000]` / `0x412a0d: call ExitProcess` — `ExitProcess` の呼出し。その戻り番地が `0x412a12`。
  - よって `call_site=0x412a12` は `ExitProcess` の戻り番地で、分岐先 `0x412a12` とは同じ番地を指す。exit 直前の条件が `[0x15eac80]=0` なので、ジャンプは取られず `0x412a0d` で exit が呼ばれた。
- `f_4128b0` の入口は boot 中 1 回 (戻り番地 `0x1376884`)。
- §6.1 `0x412acf` の lift 条件: 既定 root の lift 出力には `0x412a82`〜`0x412adf` の命令行が無い (`grep '/\* 412a(82-df):'` 0 件)。`FLE_EXTRA_ROOTS=0x6a7b70,0x412a90` の lift では入る。probe は後者の経路で行った。

### 6.1 `0x412acf` の呼出し元 (FLE-46・#5443)

- **静的**: `0x412a82`〜`0x412adf` は `int3` パディングで、実体は関数 `f_412a90` (`0x412a90`〜`0x412ada`)。`0x412acf` は `call 0x4096b0` (`ecx=0xd9`)。
- **lift 条件**: 既定 root には `f_412a90` が無く、lift 出力に `0x412a82`〜`0x412adf` が出ていなかった (`x64c --closure 2` の既定 root からの到達不可)。`FLE_EXTRA_ROOTS=0x6a7b70,0x412a90` で root に足すと、`f_412a90` と `0x412acf` の `call` が lift 出力に入る (`fle_lifted_s0.c`)。既定ビルドは不変。
- **到達性 (PE 全体・実測)**: 検索は `pefile` で実行セクション (`IMAGE_SCN_MEM_EXECUTE`) を走査し、`E8` (call rel32) / `E9` (jmp rel32) の移動先を `0x412a90` と比較した (`block00031_PE.bin`・`PointerToRawData` からの `E8`/`E9` 1 バイト走査)。再現は `fl-win64` の `extracted/block00031_PE.bin` を入力にこの走査を行う。結果は `E8` が `0x412b24` の 1 件、`E9` は 0 件。`0x412b24` は `0x412b20: jmp 0x412b2f` の直後にあり、この `jmp` で飛び越えられるため実行経路に載らない (死んだコード)。`imm32` の絶対アドレス (`0x412a90`) は 0 件。`.pdata` (例外テーブル) に RVA `0x12a90` (VA `0x412a90`) の 4 バイトが 1 件 (file offset `0x1279390`) あるが、これは `RUNTIME_FUNCTION.BeginAddress` で、呼出し参照ではない。
- **probe 結果** (`tools/flelift/boot/fle46_412acf_probe.sh`・陽性対照 `0x412a0d` 込み・`FLE_IPP=3`・`FLE_EXTRA_ROOTS=0x6a7b70,0x412a90`・測定 commit `35dbc7734`):
  - 着床: `probes: 3 (expect 3)` (`0x412acf`・`0x412a90`・`0x412a0d` の各 1 件。`work/boot/lift_fle46/fle_lifted_s0.c` に 2 件・`s3.c` に 1 件)。
  - boot 中のログ (`work/boot/run_fle46_probe.log`・gitignore・要約はここ):
    ```
    [EXITBR-caller] site=412a0d n=1 (control)
    FLEBOOT_RESULT {"units_run":895,"units_total":942,"stopped_at":895,"boot_threw":"exit",...}
    ```
  - `site=412a90` (f_412a90 入口) と `site=412acf` は **0 件**。陽性対照 `site=412a0d` は 1 件で発火している。
  - JSON: `results/boot_summary_fle46x_default.json` = `FLE_EXTRA_ROOTS=0x6a7b70,0x412a90` の run (probe ログと同一 boot)。`results/boot_summary_fle6def_default.json` = 既定 root の run。`boot_summary_fle46_default.json` は旧 `5e9d18bf6` の run で、本測定では使わない。
- **判定**: `0x412acf` は boot 中に実行されなかった (陰性)。`f_4096b0` の 4 呼出し元のうち `0x412acf` は除外。残りは `0x409553`・`0x409722`・`0x40c841`。この判定は FLE_EXTRA_ROOTS 経路の probe によるもので、既定 root の lift (`exit_branch_probe.sh`) では `0x412acf` を probe できない (上の「lift 条件」)。
- **結果の返却先**: 上の結果を親 #4970 の未判定項目 (exit 枝) に返す (#5443 の受入条件)。
- **測定 (実測・測定 commit `35dbc7734`・HEAD と同一)**:
  - 既定 root (`fle6_measure.sh`・`FLE_BOOT_RUNS=default`・`FLE_BOOT_TAG=fle6def`): units 895・stopped 895・exit・rc 0・IPP ok。工程 lift 76 s・clang-plain 76 s・boot 10 s・load 最大 1.99。JSON: `boot_summary_fle6def_default.json`。
  - `FLE_EXTRA_ROOTS=0x6a7b70,0x412a90` (`FLE_BOOT_TAG=fle46x`): units 895・exit・IPP ok・rc 0。工程 lift 76 s・clang-plain 89 s・boot 10 s・load 最大 1.80。JSON: `boot_summary_fle46x_default.json`。
  - probe 版 (`fle46_412acf_probe.sh`・`work/boot/lift` を再利用): probe 3 件着床・units 895・exit・IPP ok。スクリプト全体 93 s (clang-fle46 + boot 込み・実測 21:27:31〜21:29:04)。
  - 注: `boot_summary_fle46_default.json` は旧測定 (`5e9d18bf6`) のファイルで、今回の run の値ではない。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 「エラー番号 0・後始末無し」の枝が実機 (Windows) の意味どおりか未照合 | 枝の判定は lift C の読みによる。実機照合が無いと「正常終了」とは断定できない | #4970 |
| `f_4096b0` の呼出し元 `0x409553`・`0x409722`・`0x40c841` のどれが boot で実行されたか (`0x412acf` は §6.1 で陰性・解決済み) | 途中のエラー経路の有無。exit 枝の正常/異常判定の入力 | #4970 (親・未判定項目へ返却) |
| 外側の関数の先頭と、`0x412a0d` に至る上位の呼出し経路 (m1) | exit の呼出し位置の静的根拠が閉じない | #4970 |

結果の返却先: `0x412acf` の判定 (§6.1・陰性) を親 #4970 の未判定項目に返す (#5443 の受入条件)。残り 3 呼出し元は #4970 の未判定項目として残す。
