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

注: 本節の数値は b25edd16 測定時の作者実測で、レビュー run (ae27423d 以降) では未再実行。`work-m11` 素材が無く `BOOT_FINAL` を作れないため。単位は `ldf4_` を含む**行数** (`grep -c`)。関数別は `re.findall` による**出現数**で、1 site が pre の 3 行と load (または zext) の行に現れるため両者は一致しない。

- `ldf4 on=51 off=0` (`ldf4_` 行数)。`xor i64 0, 0 on=3886 off=3886` (xor は両方 3,886 で、F4 は xor を消さず別の read を足す。REPORT_2143 §4 と一致)。
- 関数別 F4 件数 (on / off): 10 関数とも on 8〜9、off 0。`ldfix.py` の標準出力は `F4(frame-read)=10` (F4 有) / `=0` (F4 無)。

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
