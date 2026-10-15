# REPORT_3418 — 複雑型の誤り 2 箇所 (0x47b4a0・0xc40770) の site 修復 (#3418 / CI-156)

親 #3372 の残り。REPORT_2555 表 #13 (0x47b4a0) と表 #16 (0xc40770) の IR 修復。機械照合付きの `fix_site_3418.py` を、`ldfix_e2e.sh` step 1f に配線した。

## 1. 機械語と IR の対応 (修復前の形)

**0x47b4a0 (表 #13)**: 機械語 `0x47b4f0〜0x47b503` で `call 0x409c80` の第 2 引数 (rdx) は `[*arg1] + rsi*r8`。`*arg1` は `mov rdx,[rsp+0x40]; mov rdx,[rdx]` で 1 回読む。
IR は `%24 = add i64 %23, %arg2` で、基底が arg2 になり `*arg1` の読出しが無い。

**0xc40770 (表 #16)**: 機械語 `0xc40770` の本体で、`*arg4` (`[rsp+0x30]` 経由) は次の 3 箇所で使う。
- 0xc409ab〜0xc409b3: `rax = [*arg4]`、`rax ≠ 0` なら count = `[rax-8]`
- 0xc409c0〜0xc409cb: 第 2 引数 `[*arg4] + 52*(count-1) - 24 + 28` (`lea rdx,[rdx+rax*4+0x1c]`、rax = (count-1)*13)
- 0xc409f1: 格納先の `[*arg4]`

IR は、null 判定 (`%183`)・count (`%184`)・第 2 引数の基底 (`%189`)・格納 (`%199`) に `%173` (0x4776e0 の戻り値) を使う。`%173` は 1063780 の第 4 引数にだけ残すべき値で、機械語の `*arg4` とは一致しない。
null 経路 (`dec_label_pc_c409ec.critedge`) の `-24` は `*arg4 == 0` の分岐条件の下にあるため、IR の定数のままで正しい。

## 2. 修復の形 (`fix_site_3418.py`)

- 0x47b4a0: `%a1h = load [arg1]` を挿入し、`%24` の基底をそれにする。
- 0xc40770: `%a4v = load [arg4]` を null 判定・count・基底の前に挿入し (`%183`・`%184`・`%189`)、格納の直前で `%a4w = load [arg4]` を読み直して `%199` の基底にする。修復後の `%173` の残りは `%182` (1063780 の引数) だけで、これは機械語の `*arg4` を渡す形と違うが、既存の対応 (#2555 の範囲外) として触らない。

`fix_site_3372.py` の `check_machine` / `rewrite_site` を再利用し、機械照合 13 件 (2 関数)・IR 置換 5 行。

## 3. ネガティブコントロール (入力: step 1e までの IR)

| 種類 | 操作 | 結果 |
|---|---|---|
| 二重適用 | 修復を 2 回適用 | rc=1 (`function_47b4a0 base row count 0 (want 1)`) |
| 機械照合の改変 | 0x47b4f5 の期待 operand を `[rcx]` に変更 | rc=1 (`machine mismatch at 0x47b4f5`) |
| IR base 形の改変 | `%24` の基底を `%arg1` に変更 | rc=1 (`base row count 0 (want 1)`) |

## 4. 一次分類 (`verify_deref_sites_2555.py`) の変化

入力は `ldfix_fixed.ll` (step 1 〜 1e まで)。修復の前後で比べる。

| 判定 | 修復前 (step 1f なし) | 修復後 (step 1f あり) |
|---|---|---|
| LOAD | 10 | 11 |
| ADDR | 3 | 3 |
| MISMATCH | 2 | 2 |
| OTHER | 1 | 0 |
| SCAN_MISS | 1 | 1 |

- 0x47b4a0: `OTHER` → `LOAD` (`%24 = add i64 %23, %a1h`・`%a1h = load [arg1]`)。
- 0xc40770: `MISMATCH` のまま。分類器は「IR 呼出し 2 件 / 機械語 1 件」で数える。0xc40770 の IR 呼出しは 1063780 とは別に 409c80 を 2 回 (null / 非 null) 呼ぶため、分類器の対応 (機械語の呼出し順 k 番目) が合わない。null 経路を別の呼出しとして数えれば一致するが、分類器の定義は変えない (#2555 の範囲外)。

## 5. e2e 実測 (`ldfix_e2e.sh`)

測定 commit: **`4e6478372`** (コードを変えた最後の commit)。

- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh`
- 所要 **38.6 s**・rc=0。load average 実行前 `0.26 0.33 0.26`、実行後 `0.77 0.45 0.30` (4 vCPU)。
- step 1f の出力: `fix_site_3418: machine checks 13 ok (2 sites), IR edits 5 applied`。
- judge: `STAGE4_JUDGE {"pass": true, "stage_base": 4, "stage_fix": 4, "getmem_base": 16, "getmem_fix": 16, "survey_ok_base": 136, "survey_ok_fix": 136}` → **PASS**。
- stage4 の wasm_size: base 6025478 → fix 6025723 (+245 B)。
- survey (942 unit): ok 136 / noproc 0 / miss 14 / trap 9 (base / fix 同一)。trap_kinds 同一 (oob 8・halt0 1)。23 キーのうち差は `top_frame_idx` のみ (IR 行数の変化による wasm 関数 index のずれ。件数同一)。

**1f の寄与の A/B** (同じ素材・同じ HEAD で、step 1f を除いた版と比較): 1f なし `wasm_size 6025707` / 1f あり `6025723` (差 +16 B)。stage4 は両方 4/4、survey は両方 ok 136。実行時の挙動 (trap 件数) は、この 2 箇所では変わらなかった。

## 6. 検証範囲

- 範囲内: 2 箇所の IR 修復・機械照合 13 件・NC 3 種・step 1f の配線・ldfix_e2e の完走 (4e6478372) と 1f の A/B。
- 範囲外: 0xc40770 の分類器上の `MISMATCH` (分類器の対応規則。#2555 の定義)、stage4 の `memory access out of bounds` の原因 (#942 系、従来どおり)。
- `--batch` (liftdiff closure 全数) は未実行。
- 測定 commit `4e6478372` から HEAD までのコード差分 (`git diff 4e6478372 HEAD -- tools/m11/ldfix ':(exclude)*.md'`) は **0 行**。

## 7. 再現

```
PE=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
python3 tools/m11/ldfix/fix_site_3418.py tools/m11/ldfix/work/ldfix_fixed.ll tools/m11/ldfix/work/ldfix_fixed_3418.ll --pe $PE
python3 tools/m11/ldfix/fix_site_3418.py IN.ll /dev/null --pe $PE --negctl {double,mach,ir}   # rc=1 が期待値
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
```
