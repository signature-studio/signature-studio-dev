# #736 (LD-14): 旧 F3c (block-local) が修復した 15 関数の正しさの再点検

**判定: 部分達成**。旧 F3c-block の 16 関数のうち、戻り値 reg へのコピーだけを修復していた **12 関数の誤修復を門で外した**。残る 3 関数 (10165c0 / 1016970 / 1017ad0) は機械語と一致する修復で、維持した。liftdiff による動的確認は未実施 (§4)。

先行: #509 (`REPORT_509.md` §2.1・§6)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 15 関数の戻り値の由来と修復後 IR の戻り値の突合 | **達成** (§2。逆アセンブルで `rax` の由来を確認) |
| 誤っていたものは門を絞る / 修復を外し、差分を記録 | **達成** (§3。12 関数の門を外した。差分は 12 関数のみ) |
| 動的確認 (native 比較) が必要なものは liftdiff | **未達**。§4 |

## 2. 突合 (機械語 vs 修復後 IR)

`ldmach.Machine.disasm_fn` で fl-win64 の `block00031_PE.bin` を逆アセンブルし、15 関数の全命令列を見た (capstone 5.x / pefile、検証用 venv)。

- **誤り (12 関数)**: 5c1030 / 607b90 / 6088a0 / 60f010 / 6214a0 / 737d10 / 73b300 / 7cbc20 / 7ff6e0 / 840720 / d243c0 / e404e0。
  11 関数は戻り値が `mov rax,rcx` (引数ポインタ自身) で、`mov rbx,[rcx]` は `call [rbx+X]` の vtable 読みにしか使われない。e404e0 は `mov rax,[rcx+0x7f8]` を読み、早期 return では `rax` = その値 (0)、通常経路では `call [rbx+0x178]` の戻り値を返す。どちらも `*arg1` を戻す形ではない。旧修復は `store i64 %arg1, %rax.N.reg2mem` を `load i64 [%arg1]` 経由に変えており、戻り値が `*arg1` に化けていた。
- **正しい (3 関数)**: 10165c0 / 1016970 / 1017ad0。機械語 `mov rax,[r8]` (= `*arg3`) を stack slot に保存しており、修復 (`store *arg3`) と一致。
- **正しい (409c80)**: §2.1 の 4B path。REPORT_509 §4.4 の動的確認で PASS 済み。

## 3. 門の変更 (`ldfix.py` `fix_f3c_block`)

読んだ値 `rD` が同幅で memory に store されない site を見送る (`f3c_no_val_store`)。`mov rax,rcx` (reg コピー) と call 先は値の store ではないので対象外。

同じ修復前 IR に HEAD 版と変更版を適用し、SSA 名 (`ldfx[a-z]*\d+`) を正規化して比較 (`ldfix_509_e2e.sh` の 2/7 の出力に対する同じ正規化):

| 比較 | 結果 |
|---|---|
| 本体が異なる関数 | **12** (= 上記の誤り 12 関数。他は一致) |
| `f3c_fns` (block-local の 16 → ) | 修復対象から 12 関数が外れ、残りは 10165c0 / 1016970 / 1017ad0 / 409c80 |
| `audit_lsf.py` の summary (`b5eeb32^` の旧門 → HEAD の新門) | `suspect_use_fns` 23 → 23、`suspect_mixed_fns` 118 → 119 (実測 2026-10-14、HEAD `aa50dfa`)。`SUSPECT_VAS` 空 (両版) |

注: `fix_f3c_fn` (関数単位収支門) の結果は変更していない。HEAD 版と変更版で `f3c_fns` の総数は 48 → 36 と減るが、それは block-local の 12 を外した分。

### 3.1 コミット済み HEAD (`aa50dfa`) での再現

`ldfix_509_e2e.sh` (HEAD `aa50dfa`、`EMSDK_ENV` は `docs/REFERENCES.md` の `[EMSDK]` の emsdk_env.sh、1 回実行、所要 176 s、開始時 load 0.43。素材 `fl-win64` / `work-m11` 展開済み):

- steps 1–5 完走。`ldfix` 旧版 (009e823) F1=902 / F1v=4 / F2=30 / F3a=3 / F3b=5 / F3c=16。新版 (HEAD) F1=902 / F1v=4 / F2=30 / F3a=3 / F3b=5 / F3c=36 (errors=0)。F2 は旧版・新版とも 30 (PR 本文の 29 は誤記)。
- `audit_lsf.py` (修復前 → 新版): store 形 SUSPECT 8 関数 / 12 site → **0**。消費者形 pure 52 → **23**、mixed 124 → 119。
- `audit_lsf.py` (旧版 009e823 → 新版): `suspect_use_fns` 49 → 23、`suspect_mixed_fns` 120 → 119。009e823 以降の変更 (#509 等) を含むため、この差は本 issue の門だけの効果ではない。本 issue の門だけの効果は §3 の `b5eeb32^` → HEAD の比較 (use 23 → 23、mixed 118 → 119) で見る。
- ネガコン (step 5): NC:nc_store で 806740 が戻る (1 関数 / 1 site)、NC:nc_use で 1063090 が戻る。

**未実施**: step 6 (wasm 再ビルド・survey) と step 7 (動的確認) は失敗。原因は e2e の設計: 修復前 IR を `M11_LDFIX=0` で作るため `ir_conditions.json` が `ldfix=disabled` となり、`m11_build.sh` が fail-closed で拒否する (`build_base.log`: `ir_conditions.json に ldfix=applied の記録無し`)。修復前後の wasm 比較 (受入条件 2 の動的確認) は未実施。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修復 (旧) を外した 12 関数の wasm 側の動的確認。liftdiff で native と突合していない | 門の変更が survey / liftdiff の結果を変えるかは未測定 | #1064 (LD-29、親 #736) |
| `ldfix_509_e2e.sh` steps 6–7 が `ir_conditions.json` の `ldfix=disabled` で build 拒否される (`build_base.log`: `ir_conditions.json に ldfix=applied の記録無し`) | 動的確認 (wasm 比較) が再現できない | #1065 (LD-30、親 #736) |
