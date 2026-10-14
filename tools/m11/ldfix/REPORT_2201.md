# REPORT_2201 — 名前付き stack_var の read を監査に入れ F4 ネガコンを成立させる (#2201 / 親 #2143)

親: #2143 / 前提: `REPORT_2143.md` §5 (監査が名前付き stack_var を見ないため検出数差 0)

## 1. 測定条件

- 測定 commit: `b25edd16` (`feat(ldfix): audit escaped named stack_var reads (F4 shape) (#2201)`)。コードを変えた最後の commit。
- 測定は commit 済み HEAD で `repro_2143.sh f4` と `repro_2143.sh named` を実行して取った (n=1)。
- 入力 IR:
  - pre IR: `tools/m11/work/boot_final.ll` (`M11_LDFIX=0` で作られた ldfix 前。`ldf4_` 0 件・`xor i64 0, 0` 3,886 件を確認)。
  - F4 有: `ldfix.py` 既定。F4 無: `ldfix.py --no-f4`。
- 素材: `fl-win64` `extracted/block00031_PE.bin` (22,227,016 B)、`work-m11` (`tools/m11/work/`)。
- 実行環境: 4 vCPU・load average 0.27〜0.9 (測定中)。
- 所要時間 (実測):
  - `repro_2143.sh f4` (ldfix 2 本 + 集計): real 1m20.9s
  - `ldfix.py` F4 有: real 40.9s / F4 無: real 38.8s
  - `repro_2143.sh named` (F4 有・無の監査 2 本): real 8.1s + 8.2s
- 検証 (差分の入力): `git diff b25edd16 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh` は本 REPORT の commit 後も 0 行 (§6)。

## 2. 変更内容

- `audit_undefload_dest.py`
  - `named_stack_reads`: `bitcast` 別名・`ptrtoint`/`add`/`inttoptr` 経由を含め、escape 済み名前付き `stack_var_-N` の load を返す (F4 が書く形を読む)。
  - `scan_named_text` / `run_named`: その load ごとに consumer (`!insn.addr`) を集めて JSON に出す。`--named PE OUT.json IN.ll...` で起動する。
  - 既存の norm0 監査 (`main`) の出力形式は変えていない。
- `repro_2143.sh named` を追加 (F4 有無の差を出す)。`all` の末尾にも加えた。

## 3. 受入条件の結果 (実測)

| 受入条件 | 結果 |
|---|---|
| 監査が F4 有 IR で 132e8e0 / 44d1c0 / 69c360 / 977e40 / 865020 を検出する | **達成**。F4 有で各 1 件 (`named 132e8e0 on 1` 他)。F4 無では各 0 件 |
| F4 無 IR で同じ監査を実行し、検出数差 (F4 有 − F4 無) を実測 | **達成**。named sites: F4 有 3,170 / F4 無 3,160。差 **10** (F4 有のみ 10 件、F4 無のみ 0 件) |
| 差の関数が F4 修復の関数と一致 | **一致**。差の 10 関数は 132e8e0・41ca30・44d1c0・52a7f0・666c30・69c360・71dd80・864f60・865020・977e40 (F4 修復 10 関数と同一集合) |
| 測定 commit と HEAD までの差分を REPORT に書く | §6 に記載 |

注: F4 無 IR でも named sites は 3,160 あり、監査は F4 以外の名前付き stack_var read も拾う (escape 済みの既存 read)。F4 の寄与は絶対数ではなく **F4 有無の差分 (10)** で見る。

## 4. F4 件数の再確認 (`repro_2143.sh f4`)

注: 本節は b25edd16 測定時の値。素材で再実行した値 (§7) も同一。単位は次の表のとおり、`ldf4_` の行数 (`grep -c`) と関数別の出現数 (`re.findall`) は別の数え方。

| 単位 | 数え方 | on | off |
|---|---|---|---|
| `ldf4_` の行数 (全体) | `grep -c 'ldf4_'` | 51 | 0 |
| `ldf4_` の出現数 (全体) | `grep -o 'ldf4_' \| wc -l` | 81 | 0 |
| 関数別 行数 (10 関数の合計) | 関数ごとに `ldf4_` を含む行を数える | 51 | 0 |
| 関数別 出現数 (10 関数の合計) | `re.findall('ldf4_')` を関数ごとに数える | 81 | 0 |

- 行数 51 = 出現数 81 の差は、1 site が pre の 3 行と load (または zext) の行に現れ、1 行に複数回 `ldf4_` が出るため。
- 関数別 (出現数): 10 関数とも on 8〜9、off 0 (内訳は §7)。`ldfix.py` の標準出力は `F4(frame-read)=10` (F4 有) / `=0` (F4 無)。
- `xor i64 0, 0 on=3886 off=3886` (xor は両方 3,886 で、F4 は xor を消さず別の read を足す。REPORT_2143 §4 と一致)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `uselistorder` 行による `scan_text` の alloca 除外 (scan records +2,339) | norm0 監査の site が実際より少ない。本 issue の named 監査は `scan_text` を使わないため直接の影響は無い | #2143 (親) に残す。新規起票はしない。本 PR では `scan_text` を変えないため未着手 |
| 69c360 型 (read-modify-write を挟んだ writer chain の先を辿らない) | REGLIVE の偽陰性が残る | #2202 [LD-86] (既存) |
| 旧監査 sites・ldfix 再生成 IR での数値 | 本 REPORT は素材の norm0 / pre IR での実測。REPORT_1866 の値と直接比べられない | #2144 [LD-80] (既存) |

## 6. 測定 commit 以降のコード差分

測定 commit `b25edd16` から HEAD までのコード差分 (`tools/m11/ldfix/*.py` `*.sh`):

```
(出力 0 行。本 REPORT のみが後続 commit)
```

## 7. 素材での再実行 (fix run・HEAD 013a14ff 相当のコード)

- 素材: `fl-win64` `extracted/block00031_PE.bin` (22,227,016 B)、`work-m11` (`tools/m11/work/`: `boot_final.ll` 19,787,837 B、`boot0..4.norm0.ll`)。両 tarball を `$ARTIFACTS_DIR` で確認した。
- コード: `tools/m11/ldfix/*.py` `*.sh` は測定 commit b25edd16 と同一 (§6 で 0 行)。
- 実行: `PE=... NORM0=tools/m11/work BOOT_FINAL=tools/m11/work/boot_final.ll bash tools/m11/ldfix/repro_2143.sh f4` / `... named`。
- 実行環境: 4 vCPU・load average 1.55 (開始時)。
- 所要時間 (実測): `named` の 2 本: real 6.495 s + 6.283 s。`f4` は出力の tail のみ取得し時間は未計測 (§1 の b25edd16 測定では real 1m20.9s)。

### 7.1 `repro_2143.sh f4`

```
ldf4 on=51 off=0
xor i64 0,0 on=3886 off=3886
F4 function_132e8e0 on 8 off 0
F4 function_41ca30 on 8 off 0
F4 function_44d1c0 on 8 off 0
F4 function_52a7f0 on 8 off 0
F4 function_666c30 on 8 off 0
F4 function_69c360 on 8 off 0
F4 function_71dd80 on 8 off 0
F4 function_864f60 on 8 off 0
F4 function_865020 on 9 off 0
F4 function_977e40 on 8 off 0
```

`ldfix.py` 標準出力: `F4(frame-read)=10` (F4 有) / `=0` (F4 無)。

### 7.2 `repro_2143.sh named`

```
named sites 3170 functions 720   (named_f4on.json)
named sites 3160 functions 710   (named_f4off.json)
named on 3170 off 3160 diff(on-off) 10 diff(off-on) 0
named 132e8e0 on 1 off 0
named 44d1c0 on 1 off 0
named 69c360 on 1 off 0
named 977e40 on 1 off 0
named 865020 on 1 off 0
named diff functions ['132e8e0', '41ca30', '44d1c0', '52a7f0', '666c30', '69c360', '71dd80', '864f60', '865020', '977e40']
```

JSON の `functions` 比較 (`named_f4on.json` と `named_f4off.json` の `functions` 集合):
- off ⊆ on: True (710 ⊆ 720)
- on − off の集合 = 10 関数 = F4 修復の 10 関数 (`{132e8e0, 41ca30, 44d1c0, 52a7f0, 666c30, 69c360, 71dd80, 864f60, 865020, 977e40}`)、一致: True

### 7.3 §4 の件数 (行数と出現数を同じ表で)

| 関数 | 行数 | 出現数 |
|---|---|---|
| 132e8e0 / 41ca30 / 44d1c0 / 52a7f0 / 666c30 / 69c360 / 71dd80 / 864f60 / 977e40 (各) | 5 | 8 |
| 865020 | 6 | 9 |
| 合計 (10 関数) | 51 | 81 |

全体の `grep -c` (行数) は 51、`grep -o | wc -l` (出現数) は 81 で、関数別の合計と一致する。

### 7.4 数値の対応

§1 の測定 (b25edd16) と §7 の再実行は、`ldf4` 51 / 81、`named` 3170 / 3160 / 差 10、関数集合で一致した。
