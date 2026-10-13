# 付録: M11 REPORT §8 — LB_BASE=0x10000 適用 (#222) — tools/m11/

> **正本**: `tools/m11/REPORT.md`。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため、本体から**そのまま分割移動**した §8 の全文
> (節見出し・表・数値は無変更。節番号は本体の参照と一致)。移動元の本体 commit: PR #411 (#132) の REPORT 整理。

## 8. LB_BASE=0x10000 適用 (#222, 達成: 静的層 + `m11_e2e.sh` 実行で LB=0 と同水準を確認)

既知類型との関係: 該当なし (関連: DEFECTS.md D11 = PE VA リテラルの wasm32 切捨て。本件は VA→LVA 規約の変更で別件)。

`M11_LB_BASE` (既定 0 = 従来 LVA=RVA / `0x10000` で LVA=RVA+0x10000) で全層を切替可能にした。既定 0 は従来と byte 一致。

| 層 | 変更 |
|---|---|
| `lb_base.py` | `M11_LB_BASE` の単一定義 (64KiB 境界を assert) |
| `m11_image_gen.py` / `m11_data_gen.py` | reloc 補正 `-0x400000` → `-0x400000+LB`、image 先頭に LB 分の 0 領域 / data の memcpy 先に +LB |
| `m11_passes.py` | IR の VA→LVA remap (M1/M2/M2b) の差分 `BASE_VA = 0x400000 - LB` |
| `m11_ov.c` `m11_rt.c` `shimx_link/trace_rt.c` | 手書き RVA 定数 (`R()` 経由)・icall 表引き `target+(0x400000-LB)`・`hinst` を `-DM11_LB_BASE` で補正 |
| `ldfix/ldfix.py` `ldfix/halt0_map.py` `shimx_link/analyze.py` `run_trace.mjs` | LVA↔VA 換算に LB を反映 |
| `m11_build.sh` / `m11_e2e.sh` | `-DM11_LB_BASE`・stamp 不一致時の再生成/拒否・GLOBAL_BASE 衝突 assert・`lb_check.py` 実行 |

`m11_bounds.py` / `m11_tail.py` / `m11_icall_audit.py` は VA 空間 (LB 非依存) なので変更不要。GLOBAL_BASE 0x10000000 は image 終端 0x18c0000+0x10000 より後ろで変更不要 (assert 済み)。initial 288MiB / max 1.8GiB も未変更。

### 実測 静的層 (コミット済み HEAD `95054de`, FLEngine_x64.dll 22,227,016 B)

| 項目 | 実測 |
|---|---|
| DIR64 reloc 総数 / 指す先 RVA<0x10000 (LB 適用前) | 278,531 / 55,929 (`lb_check.py` が別実装で再計算し `audit_va.py` と一致) |
| LB=0x10000 適用後 linear<0x10000 の reloc 先 | **0** (全 278,531 が >=0x10000; 値は `v-0x400000+0x10000` と全件一致, 不一致 0) |
| 非 reloc バイト不一致 / 先頭 64KiB の非 0 バイト | 0 / 0 |
| LB=0 の image | 旧 `m11_image_gen.py` 出力と `cmp` 一致 (22,515,781 B) |
| LB=0x10000 の image | 22,581,317 B (+65,536 B) |
| 実行 (HEAD, n=3, load 0.17–0.36, 直列) | image_gen + lb_check: 8.21–8.40 秒, 3/3 PASS |
| ネガティブコントロール | reloc 1 件の LB 補正を落とすと `dir64_value_mismatch=1` で FAIL; LB=0 image を LB=0x10000 で検査すると FAIL (長さ不足) |
| IR remap pass 単体 | 試料 IR で store 即値 4096 (LB=0) → 69632 (LB=0x10000) を確認 (全 IR での件数は未計測) |

再現: `M11_LB_BASE=0x10000 python3 tools/m11/m11_image_gen.py <PE> && uv run --with pefile python tools/m11/lb_check.py <PE> work/m11_image.bin 0x10000`

### IAT 738 スロット (要確認項目 4)
全 738 スロットは `.idata` 内の hint/name RVA を持ち (IAT==ILT 738/738, by-name 738)、`.reloc` に載るのは 0 件、image 範囲値に見えるのは RVA を VA と誤認しているだけ。m11 の image は `.idata` を敷設せず (`KEEP` に無し)、`m11_genstubs.py` / `m11_win.c` は IAT を参照しない (grep 0 件; Win32 は IR の declare 名で stub 化)。**LVA 化への追従は不要**。`audit_va.py` の IAT 判定 (exit 1) は Delphi 側ではなく PE 標準の bound 前 IAT の誤検知で、FLEngine には不適。

### 実測 `m11_e2e.sh` (LB=0 vs LB=0x10000; コミット済み HEAD `3162415`)
GitHub Actions runner (4 core, load 0.6–0.9)。素材は work-m11 スナップショット (lift 成果物 `boot*.lift.ll` は LB 非依存で再利用; `gen_ir2` で IR の VA→LVA remap・data/image・emcc 増分ビルド・実行 A/B を再実行)。各 1 回, 直列。

| 項目 | LB=0 | LB=0x10000 |
|---|---|---|
| `m11_e2e.sh` 所要 (実行 A/B 込み) | 38 秒 (boot/data 等の全 obj を emcc; gen_ir2 は直前の失敗実行で済) | 61 秒 (gen_ir2 + 全 obj を emcc) |
| lb_check | PASS | PASS (linear<0x10000 の reloc 先 0) |
| 到達 stage | 4/6 | 4/6 |
| 通常起動 | unit 17/942 完走後 `memory access out of bounds` | 同 |
| FastMM4 (通常起動) GetMem / FreeMem / VirtualAlloc | 13 / 1 / 3 | 13 / 1 / 3 |
| survey ok / noproc / miss / trap | 812 / 1 / 46 / 83 | 812 / 1 / 46 / 83 |
| trap 内訳 (OOB / Halt0 / abort) | 34 / 48 / 1 | 34 / 48 / 1 |
| wasm サイズ / image | 6,010,298 / 22,515,781 B | 6,010,681 / 22,581,317 B |

**stage 進行・survey 集計は一致**。unit 別 (942 本) に結果種別 (ok / noproc / miss / trap 種別) を比較すると差 0 (frame idx は unit 477 の `5385`→`5386` のみ。LB 依存の関数番号ずれで、同一 unit 477 の trap 種別は OOB のまま)。unit 別の副次カウンタ (GetMem / VirtualAlloc / stub 呼出) の差は 2 unit のみ:
* unit 745 (VA 0xacb3b0, `function_ebb3b0`): LB=0x10000 だけ `SelectObject` stub が 3 回追加で呼ばれる (stub は 0 を返して継続; どちらも後続で OOB trap し種別は同一)。呼出元は未特定。原因 (LB 依存の分岐か、未初期化読みの値差か) は未調査。
* unit 873 (VA 0xe61210): LB=0 は `VirtualAlloc` 1914MB 要求が 2GiB 上限で OOM → NULL → `Halt0`、LB=0x10000 は VirtualAlloc 要求自体が無く `Halt0` (どちらも Halt0→longjmp で種別同一)。要求サイズが LB で変わる原因は未調査。
どちらも終了種別は不変で、集計 (ok 812 / trap 83) には影響しない。

ネガティブコントロール (wasm と image の LB 不一致が実行で検出できること = 比較が鈍感でないこと):
| 組合せ | 通常起動 | survey |
|---|---|---|
| wasm LB=0x10000 + image LB=0 | `init_count` 0, `units_run` 0, icall_miss 717 | ok 0 / miss 920 / noproc 21 |
| wasm LB=0 + image LB=0x10000 | `units_run` 8, icall_miss 12,213, OOB | ok 2 / miss 939 |

再現 (m11_build.sh は `llvm-nm` を PATH から引くので `export PATH=/opt/emsdk/upstream/bin:$PATH` 相当が要る。runner では emsdk_env.sh が `llvm-nm` を PATH に載せず build が rc=127 で FAILED になるため `llvm-nm` の symlink を PATH に置いた): `M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh` (PE パスは `/home/ubuntu/work/...` ハードコードのため symlink で回避)。

### 軽微修正 (本 PR の同梱)
* `lb_check.py`: image が `LB + 節末` より短いとき `struct.error` になっていたのを、先に長さを判定して `errors` を出し FAIL (exit 1) するよう修正 (長さ 1000 B の image で FAIL 出力を確認)。
* `ldfix/ldfix.py` / `ldfix/halt0_map.py`: `M11_LB_BASE` の個別 parse をやめ `lb_base.py` (`LB`, `IMG_BASE`) を使う。`M11_LB_BASE=0x10000` で `ldfix.BASE == 0x3f0000` を確認。

### 未検証 / 範囲外
* 全 IR での remap 件数・実行後の guest ポインタ assert は未計測 (stage / survey が一致することで代替確認)。IR の VA→LVA remap の regex (`m11_passes.py` M2b) は VA 側を見るので LB 非依存の見立ては、e2e 結果と整合 (補正漏れがあれば上記ネガティブコントロールのように崩れる)。
* `#221` (liftlib `dataimage.py:37` フィルタ) は別 issue のまま。
* 上記 unit 745 / 873 の副次差の原因調査は未実施 (集計に影響しないため本 PR の範囲外)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 745 / 873 の副次カウンタ差 (SelectObject 3 回 / VirtualAlloc 要求有無) の原因 | 集計には無影響。LB 依存の分岐が残っていないかの確認 | #222 コメントに記録 (未起票。要なら PM が起票) |
| `audit_va.py` の IAT 判定が FLEngine で常に exit 1 | CI 検査に使えない | #91 にコメント (PE 標準 IAT は除外すべき) |
