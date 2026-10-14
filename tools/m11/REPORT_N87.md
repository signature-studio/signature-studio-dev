# M11 REPORT (#1373 / [M11-N87] / 親 #1154): sigfix 0 詰め inherit の呼出元までの def 追跡

結論: **実値化 0 件**。inherit (窓外 live-in の 0 詰め引数) 1,172 件はすべて「復元不能」に分類した (未分類 0)。主因は、call を跨いだ引数レジスタの値が Win64 ABI で volatile になり、直前の call 先 (間接 call・IAT を含む opaque な関数が 2,005 回の走査で現れた) から値を決められないこと。fix 集合は main と同一 (33 件)。survey は既定と同じ ok 872 で、退行は無い。

既知類型との関係: 該当なし (lift 欠陥ではなく sigfix の引数復元の範囲に関する話。DEFECTS.md の類型とは別)。

## 1. 入力と再現

- 入力 IR: `tools/m11/work/boot_final.ll` (`work-m11` 展開物・sha256 `69c774…`・REPORT_N98 と同一)。
  e2e 実行後の `boot_final.ll` の sha256 は `de46cad…` で、e2e 経路の入力 IR の指紋 (`ir_sha256`)。stats 経路は書き換え前の IR (原因は未切り分け)。
- PE: `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。
- stats 経路: `bash tools/m11/m11_sigfix_stats.sh` (`FL_WIN64_DIR` 指定・単発 33 秒)。e2e は同じ `boot_final.ll` を書き換えるため、stats を回す前に work-m11 から `tools/m11/work/boot_final.ll` を展開し直す (展開直後の sha256 `69c774…`。書き換え後に回すと inherit が 1,185 件になる)。
- e2e 経路: `work/lift_pe.sha256` を現 PE の指紋で作成 (REPORT_N53 と同じ。RetDec 再 lift を省く) → `M11_SIGFIX_RECOVER=1 bash tools/m11/m11_e2e.sh` (3 分 7 秒)。

## 2. 方式 (`m11_argrecover.py` の `Defchain`)

1. 窓 (`classify_set`) で代入が見つからない inherit 引数 (pos < 4) を、基本ブロック単位の後ろ向き到達定義で再追跡する (全経路の和集合)。
2. 関数入口まで届いた live-in は、その関数の直接 call と tail jmp の呼出元で同じ追跡を再帰する (深さ上限 8)。アドレスが取られている関数 (`addr_taken`) と呼出元の無い関数 (`no_caller`) は不明とする。
3. call を跨ぐときは、callee が引数レジスタを書きうるかの推移閉包 (`mod`) で判定する。callee が書かず、間接 call も含まないときだけ通過する。間接 call を含む関数は opaque として書くものとみなす。
4. 値が 1 つに決まり、理由が無いときは候補 (理由 `unsound_cand`) として件数だけ残し、fix には載せない。候補を fix にしない理由は §6 の穴 (レビュー round 1 の B1)。それ以外は `inherit_unres` と理由 (優先順位つき) を残す。

## 3. 実測 (stats 経路・計測 commit `ab717ca0`)

測定 commit: `ab717ca0` (計測時のコード。直前の `4d3efded` が分類の本体)。その後の変更 (`1b420d82`) は §8 の差分の通り、計測結果に影響しない。

| 分類 | 件数 |
|---|---|
| inherit 実値化 (fix に載せた件数) | **0** |
| 1 値に決まった候補 (`unsound_cand`・fix に載せない。計測時の `inherit_const` と同じ 0 件) | 0 |
| 復元不能 (`inherit_unres`) | **1,172** |
| 未分類 | 0 |

窓での理由別 (`why`) と、復元不能の理由 (主因。1 引数につき 1 つ):

| 窓での理由 | 件数 | call_clobber | nonconst_def | no_caller | partial_def | addr_taken | xmm_callee |
|---|---|---|---|---|---|---|---|
| boundary (窓が分岐・call で切れた) | 1,119 | 1,014 | 66 | 33 | 3 | 1 | 2 |
| entry (関数入口まで代入なし) | 53 | 24 | 26 | 3 | 0 | 0 | 0 |
| 計 | 1,172 | 1,038 | 92 | 36 | 3 | 1 | 2 |

理由の語: `call_clobber` = 到達定義の代わりに call があり、引数レジスタが call 後の値になる / `nonconst_def` = 非定数の代入 (load・レジスタ由来の演算) / `no_caller` = 直接の呼出元が無い / `partial_def` = dl 等の部分書込 (上位ビットが旧値依存) / `addr_taken` = 関数アドレスが取られ間接呼出しがありうる / `xmm_callee` = callee が xmm 引数を読む (復元しない方針)。

call_clobber の走査内訳 (追跡中に現れた call 先の種別。走査回数): opaque 2,005 / 引数レジスタを書く直接 call 270 / 間接 call 318。

e2e 経路の IR (e2e 実行後・`work/sigfix_pads.json`): 0 詰め 1,061 site / 1,983 引数、inherit 1,185 件 (boundary 1,128 / entry 57)。復元不能の内訳は call_clobber 1,047・nonconst_def 96・no_caller 36・partial_def 3・addr_taken 1・xmm_callee 2 で、実値化 0・未分類 0。

## 4. 検証

| 項目 | 結果 |
|---|---|
| fix 集合が main と同一 | main の `m11_argrecover.py` (`3e8c8d25`) と同じ pads (e2e 経路) で fix 33 件を再計算し、新旧の `fixes` の list が一致 (`identical True`)。計測時の候補 (inherit_const) は 0 件のため追加 0 件。候補を fix に載せる経路は §8 で削除した |
| 既存 fix の独立検算 `m11_argrecover_verify.py` | 33/33 一致 (mismatch 0) |
| 正の対照 1 (window 内で定数と決まる引数に `resolve` を適用) | 66/66 で定数が一致 |
| 正の対照 2 (入口経路。直接 call 元で定数が決まる 4,000 件) | 4,000/4,000 で、`entry` の値集合がその定数を含む (理由無し 1,669・他の呼出元の理由付き 2,331) |
| survey `M11_SIGFIX_RECOVER=1` (`m11_e2e.sh`, rc 0, 3 分 7 秒・測定 commit は `ab717ca0` 以降) | ok=872 noproc=1 miss=46 trap=23 clobber=0・units_run 53/942・reached_stage 4。`ab717ca0` 以降のコード差分はカウンタ追加のみ (fix 出力は不変)。tools/m11 のコードは 4 commit 後の `ce0c0ed0` まで同一 |
| survey 既定 `M11_SIGFIX_RECOVER=0` (同じ IR, rc 0, 1 分 0 秒) | ok=872 noproc=1 miss=46 trap=23 clobber=0・units_run 53/942・reached_stage 4 |
| 入力 IR の指紋 (両者) | `ir_sha256` `de46cad…` で一致 |
| `post_report.json` の const 復元 | 既定 0 件 → フラグ 1 で 24 件 (既存の set_const 系 fix の適用。本件の新規はない) |

判定: 受入 2 (survey ok ≥ 既定 870) は 872 ≥ 872 で満たす。`NEGCTL` 3 件はすべて「退行入力を検出」。

## 5. 製品 KPI (launch・boot に関わる検証)

- 通過 unit 数 (stage 5 の units_run): 既定 53/942 → フラグ 1 でも 53/942 (変化なし)。
- 最初のウィンドウ: 動かしていない (e2e は audio/GUI なしの部分起動 PoC)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| call 越しの引数値 (call_clobber 1,038 / 1,172) | ABI 上 volatile の値を呼出元から決められない。0 詰めは復元されず 0 のまま | 起票なし。PM agent の判断待ち: 「復元不能」として確定してよいか・既定案: 確定 (実値化は別 issue) |
| defchain の穴: 間接 jmp を辺・opaque にしない (`build_mod`)・pdata 関数だけの呼出元走査 (`build_index`) | 1 値に決まった候補が偽の定数になり得る。現 IR では候補 0 件のため fix 0 件に影響なし。候補は fix に載せない (§8) | #3124 (`[M11-21]`・受入で再測定) |
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
- 未実施: HEAD での `m11_sigfix_stats.sh` と survey の再実行 (`work-m11` 素材がこの run に無い)。穴の修正と再測定は #3124 (`[M11-21]`) で行う。
