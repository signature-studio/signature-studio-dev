# REPORT #2958 — `1046a30` の cell 22946304 (10 進 VA) を 1 件 remap し、`1047556` を OK_LOAD に再分類 (LD-142)

親: #2923 (LD-140)。既知類型との関係: `docs/DEFECTS.md` D11 (10 進 `inttoptr` の VA 漏れ・M11 変種) と同型。`pass_m2q_fn980ed0` (#1043) と同じ 1 件 remap の形。

## 1. 結論

- `m11_passes.py` に `pass_m2r_fn1046a30` を追加し、`1046a30` の cell 参照 `inttoptr i64 22946304` (VA 0x15e2200) を LVA 18752000 に 1 件だけ直した。機械語の rip 先と一致する番地になる。
- `1047556` は段数 2 と番地が機械語と一致したので **OK_LOAD (確定)** に再分類した。
- `10479c7` は判定不能のまま。(i)(iv) は機械語と IR で確認したが、上流 X `[rbp+0x4e8]` が 1 段不足しているため判定の根拠が無い。上流は子 #3675 (LD-172)。
- 本番 build・unit e2e は**動かしていない** (§6)。

## 2. 測定 (実測)

- 測定 commit: `58cf52f9a` (コードを変えた最後の commit。`m11_passes.py`・`spill_classify_1161.py`・`results/candidate_verdicts_2958.jsonl`・`results/spill178_1161.tsv`)。基点 `origin/main` = `96e72d1c1`。
- 測定後の差分: `git diff 58cf52f9a HEAD -- tools/m11/m11_passes.py tools/m11/ldfix/*.py tools/m11/ldfix/results` → 出力なし (本 REPORT の commit だけが後から増える)。

### 2-1. 本番 pass の 1 行差分 (受入 1)

`boot_allfx.ll` (work-m11) を HEAD 版と新版の `m11_passes.py` に通し、出力を比べた (入力・引数は同一、`--init-list work/inits_text.txt`):

```
$ diff out_base.ll out_new.ll
17121c17121
<   %ce12n11_function_1046a30 = inttoptr i64 22946304 to ptr
---
>   %ce12n11_function_1046a30 = inttoptr i64 18752000 to ptr
```

- 差分は 1 行 (`diff | wc -l` = 4 行・変更 1 件)。stage 出力は `[ir11][M2r] function_1046a30 VA->LVA remap: 1 sites`。
- 同じ入力で `22937624` (§5 の別件) は両方とも残る (count 1・変化なし)。

### 2-2. 番地の一致 (機械語 ↔ IR ↔ 画像)

- 機械語 `104754c mov rax,[rip+0x59acad]` の rip 先 = **0x15e2200** (capstone 実測・`m11_image.bin` の VA−0x400000 がオフセット)。LVA = 0x15e2200 − 0x400000 = **18752000**。
- 修正前の IR 定数 22946304 (= 0x15e2200 の 10 進) は VA 形で、画像長 **22515781** B の外。修正後の定数 18752000 は画像内で、qword = `0x12bcaf0` (実測)。
- 同関数の他の cell (例 `18752024` = 0x11e2218) は LVA 形。一方、関数 `1046a30` (16267〜24296 行) の命令形 `inttoptr i64 N to ptr` は 73 件すべてが VA 範囲 (0x400000〜0x1abf400) の 10 進で、修正したのは 22946304 の 1 件だけ (残り 72 件は §5)。

### 2-3. 監査 e2e (受入 2・3 の検証)

`boot_final3.ll` (素材の解析用 IR・`m11_passes` の出力ではない) の 17451 行に、`pass_m2r_fn1046a30` と同じ 1 行置換を当てた複製で実行した (`$RUNNER_TEMP/m11w_new`・素材本体の `tools/**/work/` は未変更)。

```
TMPDIR=$RUNNER_TEMP M11_WORK=$RUNNER_TEMP/m11w_new/tools/m11/work LD_WORK=$RUNNER_TEMP/ldw/tools/liftdiff/work bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

- HEAD `58cf52f9a`: rc=0・real 2m44.7s・load average 0.35 0.49 0.35 → 0.96 0.71 0.46・7/7 完走。`drops_510.tsv` と `spill178_1161.tsv` は `results/` と `cmp` で一致。
- step 7 (HEAD): spill 宛 unk site 178 / 71 関数。status 確定 **148** (2958 の判定を入れる前は 147)・判定不能 **29** (前 30)・未判定 1 (同)。
- `results/spill178_1161.tsv` の差分は 1 行のみ: `1046a30 1047556 cand UNDETERMINED→OK_LOAD 確定 CELL_DEEP`。他の 177 行は不変。
- 脱落関数の和集合 (step 8) は 69 (不変)。

### 2-4. ネガティブコントロール

- NC1 (番地): 修正前の定数 22946304 は機械語の rip 先 0x15e2200 の 10 進表記と同じ数で、LVA とは一致しない (§2-2)。修正後の定数 18752000 だけが LVA と一致する。
- NC2 (1 行): `diff` で 1 行以外の変化は無い (§2-1)。全件 remap (M2P) を有効にしたときは対象が増える (`M11_M2P=1` は既定 OFF・#417)。本 PR では有効化していない。

## 3. 判定結果 (`1046a30`)

| site | 判定 | 根拠 (要点) |
|---|---|---|
| 1047556 | **OK_LOAD** (前 判定不能) | 機械語 `104754c` (rip 先 0x15e2200) → `1047553` `mov rax,[rax]` → `1047556` `mov [rbp+0x520],rax`。値は [[cell]] の 2 段。M2r 後の IR: `%ce12n11 = inttoptr 18752000` (機械語と同番地) → `%378 = load` → `%storemerge54.pre = load [%378]` (2 段) → reg2mem → 17461 行 `%storemerge54.reload` (以後 `add` の基点)。段数と番地が一致。消費者の全箇所の突合はしていない |
| 10479c7 | 判定不能 (維持) | 確認: (i) `[rbp+0x4d8]` への書込は 1047942 の 1 箇所だけ (1046a30〜1048000 の全数)・アドレスを取る `lea` も無い。(iv) IR の `dec_label_pc_10479be` の preds は `dec_label_pc_10479b1` のみで、機械語の到達元 (`10479b1` ← `104797a` の je) と一致。段数 1 は一致。未確認: (ii) `%492` と slot の対応の SSA 根拠、(iii) `stack_var_16` の後続の読み。さらに上流 X が 1 段不足 (§4) で P の値が機械語と一致する根拠が無い |

判定の根拠行: `tools/m11/ldfix/results/candidate_verdicts_2958.jsonl` (2 行)。

## 4. 上流の段数 (受入 5 相当・不一致)

- X `[rbp+0x4e8]` (機械語 `10474bf`→`10474c6`→`10474c9`→`10474d4`): cell (`C` の値) → `[C]` → `[C+8]` → `[..+idx*8]` の **4 段**。IR は `%351` (cell を i32 load) → `%359` (`[C+8]`) → `%363` (`[%361]`) の **3 段**。`[C]` の 1 段が IR に無い。
- `10474a6`〜`10474b6` (`cmp ecx,[rax+0x10]`): cell → `[C]` → `[[C]+0x10]` の **3 段**。IR は `%351` → `%355` (`[C+16]`) の **2 段**。
- 同じ cell `0x15e2218` (LVA 18752024)。`%351` の i32 load は 8 B のポインタを 4 B で読む型違いも含む。範囲が別関数の修復に広がるため、子 #3675 (LD-172) に切った。

## 5. 別件: 十進 VA の残り 1 件

- `boot_final3.ll` 16640 行: `%ce0n11_function_1046a30 = inttoptr i64 22937624` (VA 0x15e0018・LVA 18743320)。機械語 `1046dad` の rip 先 0x15e0018 と段数 3 は IR と一致 (`%16`・`%18`・`%21`)。LVA 18743320 の qword は `0x12bacd8` (実測)。
- 同型 (D11) の命令形は関数 `1046a30` (16267〜24296 行) に **73 件**ある (`grep` で数えた。`inttoptr i64 N to ptr`・N が VA 範囲)。本 PR で直したのは 22946304 の 1 件のみ。残り 72 件のうち 22937624 (16640 行) は段数が機械語と一致する (上記)。
- 残り 72 件の内訳 (73 件から 22946304 を除く): 0x15e0000〜0x15e4fff 系 (cell 候補・LVA 換算 0x11e0000〜0x11e4fff) 24 件、0x104c000〜0x104cfff 系 (VA 0x104cxxx・コード範囲に入る) 48 件。個別に機械語の rip 先と段数を突合していない。
- 全件 remap (`M11_M2P=1`) は既定 OFF (#417・unit 503 で survey がハング)。本 PR では有効化していない。子 #3677 (LD-173) で、件ごとの突合のうえ一致する件だけを直す。

## 6. 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 本番の `m11_gen_ir2.sh` → `m11_build.sh` → unit e2e を**動かしていない** (fl-win64 の展開と build を 1 run に収めていない) | `1046a30` の読み値が IR 上で変わることは確認したが、unit の結果 (ok/halt0 など) への影響は未実測 | #3675 (受入 3 に含めた) |
| `boot_final3.ll` は `m11_passes.py` の出力ではない (解析用 IR)。監査は同じ 1 行置換を当てた複製で検証した | 本番経路の `boot_final.ll` は未再生成。`pass_m2r` の出力行は §2-1 で確認済み | #3675 (受入 3) |
| `10479c7` の (ii)(iii)、上流 X・cmp の 1 段不足 | `10479c7` は判定不能のまま | #3675 (LD-172) |
| 関数 `1046a30` の命令形 10 進 VA `inttoptr` が残り 72 件 (22937624 を含む) | 件ごとに読み先が画像の外・別の番地になりうる。段数の突合は未実施 | #3677 (LD-173) |

## 7. 再現

```sh
# 1 行差分 (受入 1)
python3 tools/m11/m11_passes.py work/boot_allfx.ll out_new.ll --init-list work/inits_text.txt   # M2r 入り
# 監査 (素材を $RUNNER_TEMP に展開して指定)
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst -C $RUNNER_TEMP/m11w
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst -C $RUNNER_TEMP/ldw
TMPDIR=$RUNNER_TEMP M11_WORK=$RUNNER_TEMP/m11w/tools/m11/work LD_WORK=$RUNNER_TEMP/ldw/tools/liftdiff/work bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

- 注: 候補判定は `(fn, site)` で引き、IR の番地を見ない。そのため修正前の `boot_final3.ll` でも `spill178_1161.tsv` は一致する。M2r の効果は §2-1 (IR の 1 行差分) と §2-2 (番地) で示した。監査は修正後の IR の複製で 7/7 を確認した。
