# M11 REPORT (#1373 / [M11-N87] / 親 #1154): sigfix 0 詰め inherit の呼出元までの def 追跡

結論: **実値化 0 件**。inherit (窓外 live-in の 0 詰め引数) 1,172 件はすべて「復元不能」に分類した (未分類 0)。主因は、call を跨いだ引数レジスタの値が Win64 ABI で volatile になり、直前の call 先 (間接 call・IAT を含む opaque な関数が 2,005 回の走査で現れた) から値を決められないこと。fix 集合は main と同一 (33 件)。survey は #3124 の再測定で ok 873 (基準 870 以上・canonical 873)。#3124 で defchain の 2 つの穴 (間接 jmp・pdata 外の呼出元) を塞いだ (§9)。fix 33 件・復元不能 1,172 件は不変で、1 値に決まった候補は 0 件。

既知類型との関係: 該当なし (lift 欠陥ではなく sigfix の引数復元の範囲に関する話。DEFECTS.md の類型とは別)。

## 1. 入力と再現

- 入力 IR: `tools/m11/work/boot_final.ll` (`work-m11` 展開物・sha256 `69c774…`・REPORT_N98 と同一)。
  e2e 実行後の `boot_final.ll` の sha256 は `de46cad…` で、#3124 より前の e2e 経路の入力 IR の指紋 (`ir_sha256`)。#3124 の e2e の IR は `9a9cfa06…` (§9 注記 1)。stats 経路は書き換え前の IR (原因は未切り分け)。
- PE: `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。
- stats 経路: `bash tools/m11/m11_sigfix_stats.sh` (`FL_WIN64_DIR` 指定・単発 33 秒)。e2e は同じ `boot_final.ll` を書き換えるため、stats を回す前に work-m11 から `tools/m11/work/boot_final.ll` を展開し直す (展開直後の sha256 `69c774…`。書き換え後に回すと inherit が 1,185 件になる)。
- e2e 経路: `work/lift_pe.sha256` を現 PE の指紋で作成 (REPORT_N53 と同じ。RetDec 再 lift を省く) → `M11_SIGFIX_RECOVER=1 bash tools/m11/m11_e2e.sh` (3 分 7 秒)。

## 2. 方式 (`m11_argrecover.py` の `Defchain`)

1. 窓 (`classify_set`) で代入が見つからない inherit 引数 (pos < 4) を、基本ブロック単位の後ろ向き到達定義で再追跡する (全経路の和集合)。
2. 関数入口まで届いた live-in は、その関数の直接 call と tail jmp の呼出元で同じ追跡を再帰する (深さ上限 8)。アドレスが取られている関数 (`addr_taken`)・呼出元の無い関数 (`no_caller`)・pdata 外の呼出元を持つ関数 (`no_pdata_caller`。pdata 外の `.text` 区間の呼出元は、値を追わずに理由として残す・§9) は不明とする。
3. call を跨ぐときは、callee が引数レジスタを書きうるかの推移閉包 (`mod`) で判定する。callee が書かず、間接 call・間接 jmp も含まないときだけ通過する。間接 call・間接 jmp・pdata 関数以外への直接 call / jmp を含む関数は opaque として書くものとみなす。
4. 値が 1 つに決まり、理由が無いときは候補 (理由 `unsound_cand`) として件数だけ残し、fix には載せない。候補を fix にしない理由は §6 の穴 (レビュー round 1 の B1)。それ以外は `inherit_unres` と理由 (優先順位つき) を残す。

## 3. 実測 (stats 経路・計測 commit `0fc7d986`・#3124 の再測定)

測定 commit: `0fc7d986` (#3124 で `build_mod` / `build_index` を直した後のコード)。修正前との比較は §9 (修正前は `ab717ca0` 系と同じ入力で、origin/main `624fca112` を再計測した値)。

| 分類 | 件数 |
|---|---|
| inherit 実値化 (fix に載せた件数) | **0** |
| 1 値に決まった候補 (`unsound_cand`・fix に載せない。計測時の `inherit_const` と同じ 0 件) | 0 |
| 復元不能 (`inherit_unres`) | **1,172** |
| 未分類 | 0 |

窓での理由別 (`why`) と、復元不能の理由 (主因。1 引数につき 1 つ):

| 窓での理由 | 件数 | call_clobber | nonconst_def | no_caller | partial_def | addr_taken | xmm_callee |
|---|---|---|---|---|---|---|---|
| boundary (窓が分岐・call で切れた) | 1,119 | 1,021 | 66 | 26 | 3 | 1 | 2 |
| entry (関数入口まで代入なし) | 53 | 25 | 26 | 2 | 0 | 0 | 0 |
| 計 | 1,172 | 1,046 | 92 | 28 | 3 | 1 | 2 |

理由の語: `call_clobber` = 到達定義の代わりに call があり、引数レジスタが call 後の値になる / `nonconst_def` = 非定数の代入 (load・レジスタ由来の演算) / `no_caller` = 直接の呼出元が無い / `partial_def` = dl 等の部分書込 (上位ビットが旧値依存) / `addr_taken` = 関数アドレスが取られ間接呼出しがありうる / `xmm_callee` = callee が xmm 引数を読む (復元しない方針)。

call_clobber の走査内訳 (追跡中に現れた call 先の種別。走査回数): opaque 2,026 / 引数レジスタを書く直接 call 258 / 間接 call 318 (修正前は 2,005 / 270 / 318。§9)。

旧 IR (`de46cad`) の e2e 経路の値 (e2e 実行後・`work/sigfix_pads.json`・#3124 より前): 0 詰め 1,061 site / 1,983 引数、inherit 1,185 件 (boundary 1,128 / entry 57)。復元不能の内訳は call_clobber 1,047・nonconst_def 96・no_caller 36・partial_def 3・addr_taken 1・xmm_callee 2 で、実値化 0・未分類 0。#3124 の e2e (IR `9a9cfa06…`) の内訳は未集計 (注記 1)。

## 4. 検証

| 項目 | 結果 |
|---|---|
| fix 集合が main と同一 | main の `m11_argrecover.py` (`3e8c8d25`) と同じ pads (e2e 経路) で fix 33 件を再計算し、新旧の `fixes` の list が一致 (`identical True`)。計測時の候補 (inherit_const) は 0 件のため追加 0 件。候補を fix に載せる経路は §8 で削除した |
| 既存 fix の独立検算 `m11_argrecover_verify.py` | 33/33 一致 (mismatch 0) |
| 正の対照 1 (window 内で定数と決まる引数に `resolve` を適用) | 66/66 で定数が一致 |
| 正の対照 2 (入口経路。直接 call 元で定数が決まる 4,000 件) | 4,000/4,000 で、`entry` の値集合がその定数を含む (理由無し 1,669・他の呼出元の理由付き 2,331) |
| 旧 IR (`de46cad`) の参考値: survey `M11_SIGFIX_RECOVER=1` (`m11_e2e.sh`, rc 0, 3 分 7 秒・測定 commit は `ab717ca0` 以降) | ok=872 noproc=1 miss=46 trap=23 clobber=0・units_run 53/942・reached_stage 4。`ab717ca0` 以降のコード差分はカウンタ追加のみ (fix 出力は不変)。tools/m11 のコードは 4 commit 後の `ce0c0ed0` まで同一 |
| 旧 IR (`de46cad`) の参考値: survey 既定 `M11_SIGFIX_RECOVER=0` (同じ IR, rc 0, 1 分 0 秒) | ok=872 noproc=1 miss=46 trap=23 clobber=0・units_run 53/942・reached_stage 4 |
| 旧 IR の指紋 (両者) | `ir_sha256` `de46cad…` で一致 (#3124 より前) |
| `post_report.json` の const 復元 | 既定 0 件 → フラグ 1 で 24 件 (既存の set_const 系 fix の適用。本件の新規はない) |
| #3124 の修正後 (commit `0fc7d986`・IR `9a9cfa06…`) の survey `M11_SIGFIX_RECOVER=1` と fix 集合 | survey ok=873 (canonical `M11_EXPECT_SURVEY_OK_EXACT=873` と一致・受入 3 の基準 870 以上)・fix 33 件は修正前と同一。詳細と注記は §9 |

判定: #3124 の実測 survey ok=873 ≥ 870 で満たす (IR `9a9cfa06…`・上の行と §9)。旧 IR (`de46cad`) の行は参考値で、判定には使わない。旧 IR の run の `NEGCTL` 3 件は「退行入力を検出」。#3124 の NEGCTL 結果は §9。

## 5. 製品 KPI (launch・boot に関わる検証)

- 通過 unit 数 (stage 5 の units_run): #3124 の実測 (commit `0fc7d986`・フラグ 1・IR `9a9cfa06…`) で units_run 98/942 + skipped 3 = 完了 101。canonical の `M11_EXPECT_STRICT_DONE=101` と一致 (`tools/m11/e2e_expect.env`・REPORT_3520 §2)。既定 (フラグ 0) の同一 IR での値は未測定 (work-m11 が無く再実行できない)。
- 旧 IR (`de46cad`・#3124 より前) の値: 既定 53/942 → フラグ 1 でも 53/942 (変化なし)。旧 IR の値で、比較の基準には使わない。survey ok の比較の基準は canonical の 873 (`M11_EXPECT_SURVEY_OK_EXACT`)。
- 最初のウィンドウ: 動かしていない (e2e は audio/GUI なしの部分起動 PoC)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| call 越しの引数値 (call_clobber 1,046 / 1,172・§3) | ABI 上 volatile の値を呼出元から決められない。0 詰めは復元されず 0 のまま | 起票なし。PM agent の判断待ち: 「復元不能」として確定してよいか・既定案: 確定 (実値化は別 issue) |
| defchain の穴 (issue の 2 点): 間接 jmp を opaque にしない (`build_mod`)・pdata 関数だけの呼出元走査 (`build_index`) | 修正済み (#3124・§9)。この 2 点に限る。1 値に決まった候補は 0 件のまま。候補は fix に載せない (§8) | — |
| 関数アドレスの取得 (`addr_taken`) は `lea [rip+...]` と非 `.text` セクションの 8 バイト値しか見ない。`.text` 内の関数ポインタ・`mov r64, imm64` は未対応 | taken と判定されない関数は呼出元の走査だけで値を決める。取り逃しがあると誤った値が残りうる (fix 33 件は候補を載せない §8 で保護) | 未起票 (既存の穴・PM 判断) |
| 非定数の代入 (nonconst_def 92 / e2e 96) | 実値化には SSA 値の接続が要る (set_other 系の範囲) | #1154 (親 #953・SSA 接続基盤) |
| 部分書込 (partial_def 3) | 上位ビットが旧値依存で定数にならない | #1154 (N98 と同じ扱い) |
| xmm 引数の callee (xmm_callee 2) | 復元しない方針 (IR に xmm 引数が無い。REPORT_APPENDIX §9) | 既存の未解決 (#131 へ提案済み) |

## 7. 再現メモ

- `m11_sigfix_stats.sh` は `tools/m11/results/sigfix_zeropad_remaining.tsv` を再生成する。kind 名 `inherit` は `inherit_unres` に変わった (1,172 行)。
- e2e は `work/lift_pe.sha256` が無いと全再生成 (RetDec・Ghidra 中間物 `functions_dll.csv` を要求) に入る。本計測は現 PE の指紋を書き込んで再 lift を省いた (REPORT_N53 §2 と同じ注記)。lift 込みの再現ではない。

## 8. 測定後のコード変更 (レビュー round 1 への対応)

測定 commit `ab717ca0` の後に、`tools/m11/m11_argrecover.py` を次の commit で変えた (`1b420d82`)。`git diff ab717ca0 HEAD -- tools/m11/m11_argrecover.py tools/m11/results` の出力:

```diff
diff --git a/tools/m11/m11_argrecover.py b/tools/m11/m11_argrecover.py
index 0a04d40d..09735bef 100644
--- a/tools/m11/m11_argrecover.py
+++ b/tools/m11/m11_argrecover.py
@@ -285,7 +285,7 @@ class Defchain:
     """窓の外の live-in (inherit) を呼出元まで追跡して値を決める (M11-N87 / #1373).
     at(f, i, pos): 関数 f の命令 i 直前で reg(pos) の到達定義を後ろ向きに集める (基本ブロック単位・全経路の和).
     entry(f, pos): f 入口の値 = 直接 call / tail jmp の呼出元で at() を取った値の集合 (f のアドレスが取られていれば不明).
-    結果は (値の集合 {(kind, val)}, 復元不能の理由の集合)。値が 1 つで理由が空のときだけ実値化する。"""
+    結果は (値の集合 {(kind, val)}, 復元不能の理由の集合)。値が 1 つで理由が空のときは候補 (unsound_cand) として件数だけ残し、fix には載せない。"""
 
     def __init__(self, mach, F, lb):
         self.m, self.F, self.lb = mach, F, lb
@@ -373,11 +373,11 @@ class Defchain:
                     changed = True
         self.mod = {va: (mod[va], opaque[va]) for va in fns}
 
-    def clob_kind(self, x, reg):
+    def clob_kind(self, x):
         op = x.op_str
         if not op.startswith('0x') or int(op, 16) not in self.mod:
             return 'indirect'
-        mods, o = self.mod[int(op, 16)]
+        _, o = self.mod[int(op, 16)]
         return 'opaque' if o else 'writes'
 
     def passes(self, x, reg):
@@ -402,10 +402,10 @@ class Defchain:
                 if x.mnemonic == 'call':
                     if self.passes(x, reg):
                         continue
-                    self.clob[self.clob_kind(x, reg)] += 1
+                    self.clob[self.clob_kind(x)] += 1
                     out.add(('clobber', j)); killed = True; break
                 try:
-                    rd, wr = x.regs_access()
+                    _, wr = x.regs_access()
                 except capstone.CsError:
                     out.add(('unknown', j)); killed = True; break
                 hit = [fn.cs.reg_name(r) for r in wr if reg_family(fn.cs, r) == reg]
@@ -543,14 +543,12 @@ def main():
                             c2, why2 = dc.resolve(cva, ci, pos)
                             if c2 is not None and xmm:
                                 why2 = ['xmm_callee']
-                            if c2 is not None and not xmm:
-                                kind = 'inherit_const'
-                                fixes.append({'caller': p['caller'], 'callee': p['callee'], 'k': p['k'], 'pos': pos, 'const': c2, 'via': 'defchain'})
-                            else:
-                                kind = 'inherit_unres'
-                                stats['dc:%s' % why2[0]] += 1
-                                stats['dcx:%s:%s' % (why, why2[0])] += 1
-                                rec.setdefault('dc', {})[pos] = why2[0]
+                            elif c2 is not None:
+                                why2 = ['unsound_cand']  # 1 値に決まっても fix にしない (defchain の穴。REPORT_N87 §6)
+                            kind = 'inherit_unres'
+                            stats['dc:%s' % why2[0]] += 1
+                            stats['dcx:%s:%s' % (why, why2[0])] += 1
+                            rec.setdefault('dc', {})[pos] = why2[0]
                         elif c is not None:
                             kind = 'set_const'
                             fixes.append({'caller': p['caller'], 'callee': p['callee'], 'k': p['k'], 'pos': pos, 'const': c})
@@ -574,7 +572,7 @@ def main():
     # site 単位の最終状態 (全引数が callee_unused / set_const なら「解決」)
     resolved = 0
     for r in sites:
-        r['resolved'] = r['status'] == 'matched' and all(k in ('callee_unused', 'set_const', 'inherit_const') for k in r['args'].values())
+        r['resolved'] = r['status'] == 'matched' and all(k in ('callee_unused', 'set_const') for k in r['args'].values())
         resolved += r['resolved']
     out = {'sites': len(sites), 'resolved_sites': resolved, 'stats': dict(stats), 'fixes': fixes, 'site_detail': sites}
     json.dump(out, open(a.out, 'w'))
```

- 変更の内容: 1 値に決まった候補を fix に載せる経路 (`inherit_const`) を削除し、理由 `unsound_cand` で `inherit_unres` に残す。未使用の引数・変数 (`clob_kind` の `reg`・`mods`、`reach` の `rd`) を削除。
- 測定への影響: 計測時 (`ab717ca0`) の 1 値に決まる候補は 0 件だったため、削除前後で計測の経路は同じ。`inherit_unres` 1,172・理由別の内訳・fix 33 件・TSV (kind 名 `inherit_unres`) は変わらない。TSV は再生成していない。
- 未実施: HEAD での `m11_sigfix_stats.sh` と survey の再実行 (`work-m11` 素材がこの run に無い)。穴の修正と再測定は #3124 (`[M11-21]`) で行う。 → §9 で実施済み。

## 9. #3124 (`[M11-21]`): defchain の穴 (間接 jmp・pdata 外の呼出元) の修正と再測定

修正 (commit `0fc7d986`・`tools/m11/m11_argrecover.py` のみ):

1. `build_mod`: 間接 jmp (`jmp qword ptr [...]`・`jmp rax`) を間接 call と同じく opaque にする。jump table と区別しない。
2. `build_index`: pdata の関数範囲の外の `.text` 区間 (`gaps()`: 55,666 区間・5.84 MB / `.text` 16.40 MB) を線型 disasm し、そこからの直接 call / jmp を呼出元に入れる (不正命令で止まったら次のバイトから再開)。pdata 外の呼出元は `at()` で理由 `no_pdata_caller` を返す (PRIO に追加)。pdata 外からの索引は 711 件 (361 callee)。rip 相対 lea の taken も同じ走査で拾う。

修正前後 (同じ IR・同じ PE。修正前は origin/main `624fca112` で再計測):

| 項目 | 修正前 (624fca112) | 修正後 (0fc7d986) |
|---|---|---|
| inherit_unres (復元不能) | 1,172 | 1,172 |
| 1 値に決まった候補 (`unsound_cand`) | 0 | 0 |
| 第一理由 call_clobber | 1,038 | 1,046 |
| 第一理由 no_caller | 36 | 28 |
| 第一理由 nonconst_def / partial_def / addr_taken / xmm_callee | 92 / 3 / 1 / 2 | 92 / 3 / 1 / 2 |
| 第一理由 no_pdata_caller | (理由なし) | 0 |
| fix 集合 | 33 件 | 33 件 (修正前と同一) |
| `m11_argrecover_verify.py` | 33/33 一致 | 33/33 一致 |

- `no_caller` → `call_clobber` の 8 件は、間接 jmp の opaque 化で `passes()` が呼出しを通過させなくなった分と推定 (未検証)。`clob:opaque` 2,005 → 2,026・`clob:writes` 270 → 258。
- `no_pdata_caller` が第一理由になった件数は 0。pdata 外の呼出元が判定を変えた件数は未計測。

受入条件の判定:

1. 間接 jmp を opaque にする: 済 (`build_mod`)。
2. `.text` 全域の直接 call / jmp 走査: 済 (pdata 関数の走査 + gap の線型 sweep)。線型 sweep は、gap にデータが混じると命令境界を取り違える可能性がある。取り違えによる検出漏れは残る限界 (下の未解決)。
3. stats と survey の再実行: 済 (下記)。survey ok 873 ≥ 870 で満たす。`results/sigfix_zeropad_remaining.tsv` は再生成し、差分 0 (kind 名 `inherit_unres` のまま)。
4. `unsound_cand` (1 値に決まった候補) が 1 件以上: 該当 0 件。検算の対象が無いので、fix に載せるかの判断は不要 (§8 の方針を維持)。

測定 (commit `0fc7d986`):

- stats: `bash tools/m11/m11_sigfix_stats.sh` 29.8 秒 (修正前) / 35.3 秒 (修正後)・rc 0。
- survey: `M11_SIGFIX_RECOVER=1 bash tools/m11/m11_e2e.sh` 3 分 7 秒。`work/lift_pe.sha256` に現 PE の指紋 (`b2c64da4…`) を書き、lift 込みの再生成は省いた (§7 と同じ注記)。load は未記録 (runner は 4 vCPU・15 GiB)。
- 結果: reached_stage 4。survey ok=873 noproc=1 miss=46 trap=22 clobber=0 (合計 942)。通常起動 units_run 98/942 (trap "memory access out of bounds" @ function_535c11)。寛容起動 ok=875 skipped=66。judge・tolerant gate は rc 0。NEGCTL は 3 件とも退行を検出。
- 注記 1: IR はこの run で `m11_e2e.sh` が `work-m11` の `boot*.lift.ll` から再生成した (`ir_sha256` `9a9cfa06…`)。§4 の `de46cad…` と異なるため、872 と 873 は退行の比較にならない。修正前の同一条件 survey は未実施。fix 集合は同一なので、fix 経由の IR の差は無い。
- 注記 2: e2e の終了コードは 1。原因は未確認。実行 A (`node m11_run.mjs`) の `boot_rc=1` の停止理由 (trap か ptrcheck の不合格か) を確認する `work/e2e_full.out` は、本 run に work-m11 が無く得られていない。記録に残るのは judge・tolerant gate の rc 0 のみで、ptrcheck ゲートの値は記録していない。候補は (a) 通常起動の trap (units_run 98/942 の停止点と同系統かは未確認)、(b) ptrcheck の pin 超過 (`M11_EXPECT_PTR_NEW_MAX=69359`。main の修正前でも run ptr 69,669 が超過する (REPORT_3520 §2)。pin 不一致 (#3520) による可能性)。本 PR の変更と rc 1 の関係は切り分けていない。
- 製品 KPI: m11 の検証ツールの変更で、起動・GUI の変更ではない。最初のウィンドウ: 動かしていない。

未解決:

| 未解決 | 影響 | 起票先 |
|---|---|---|
| e2e の終了コード 1 の原因 (未確認。ptrcheck pin 不一致の可能性) | 本 PR の e2e rc の解釈。stats・fix 集合には影響しない | #3520 (既存) |
| 線型 sweep の命令境界の取り違え (pdata 外の gap にデータが混じる場合) | 呼出元の検出漏れの可能性。候補は 0 件のため現時点で fix への影響は無い | §8 の方針 (候補は fix に載せない) を維持 |
| 線型 sweep は不正命令ごとに `data[off:]` を複製する (O(n²)・`sweep` の注記) | 不正命令が多い区間で遅くなる。今回の gap 5.84 MB では stats 全体 35.3 秒 | 未起票 (限界の注記のみ・PM 判断) |

§9 の後の commit (引数の未使用の削除 `index_ins`・docstring の注記) の同値確認: 測定 commit `0fc7d986` と HEAD の `m11_argrecover.py` で `build_index` / `build_mod` の出力 (`callers` 23,407 キー・`taken` 3,492・`mod` 57,816 件) を JSON 化して比較し、byte 一致 (sha256 `1d62c0ca…` 両者)。PE は `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)。stats 全体と e2e は work-m11 が無いため、この commit では再実行していない。

測定 commit から HEAD までのコード差分 (`git diff 0fc7d986 HEAD -- tools/m11/m11_argrecover.py`):

```diff
@@ -302,8 +302,8 @@ class Defchain:
             self.bl[va] = Blocks(fn) if fn.ins else None
         return self.bl[va]
 
-    def index_ins(self, x, src, own, size, rip):
-        """命令 x を索引に入れる。直接 call / jmp の呼出先は callers (src = (呼出元 VA, 命令 index))、rip 相対 lea の指す先は taken。
+    def index_ins(self, x, src, own, size):
+        """命令 x を索引に入れる。直接 call / jmp の呼出先は callers (src = (呼出元 VA, 命令 index)。pdata 外の gap では (命令 VA, None))、rip 相対 lea の指す先は taken。
         own = 呼出元の関数 VA (pdata 外は None)。"""
         fns = self.m.fns
         mn, op = x.mnemonic, x.op_str
@@ -341,7 +341,8 @@ class Defchain:
         return out
 
     def sweep(self, cs, lo, hi):
-        """RVA [lo, hi) の線型 disasm。不正命令で止まったら次のバイトから再開する。"""
+        """RVA [lo, hi) の線型 disasm。不正命令で止まったら次のバイトから再開する。
+        注記: 再開のたびに data[off:] を複製するため、不正命令が多い区間では O(n²) になる (#3124 の gap 5.84 MB では stats 全体 35.3 秒)。"""
         data = self.m.read(lo, hi - lo)
         va0 = self.m.base + lo
         off = 0
@@ -365,10 +366,10 @@ class Defchain:
             self.taken |= set(q) & set(fns)
         for va, (rva, size) in fns.items():
             for i, x in enumerate(cs.disasm(self.m.read(rva, size), va)):
-                self.index_ins(x, (va, i), va, size, RIP_RE)
+                self.index_ins(x, (va, i), va, size)
         for lo, hi in self.gaps():
             for x in self.sweep(cs, lo, hi):
-                self.index_ins(x, (x.address, None), None, 0, RIP_RE)
+                self.index_ins(x, (x.address, None), None, 0)
         self.build_mod()
 
     def build_mod(self):
```
