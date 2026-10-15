# liftlib #1270 (HB-H29) — ott_getparam の入口 this/idx 受渡しと switch 表の敷設で leafspec match 1.0 (付録)

親: #883 (HB-H21・closed)。前提: #1269 (closed・残件は #1583 / #1586 へ分割済み・いずれも closed)。
既知類型との関係: [DEFECTS.md](../../docs/DEFECTS.md) の D1a〜D25 のどれにも直接は当たらない。新規類型の行案は §7 (D26 案)。D5 と近縁だが原因は別 (§7)。

## 0. 結論

| 受入 (#1270 本文・縮小後) | 結果 (実測) |
|---|---|
| 1. 入力の受渡し方式を決め、根拠を書く | **達成**。方式 (a): 入口の BLK+0x08/+0x10 読みを仮引数 `%arg1` / `%arg2` へ張り替える。根拠は §2 |
| 2. `leafspec targets/ott_getparam.json --n 200` が rc=0・match 1.0・idx 0..19 × 200・wasm_trap 0 | **達成** (測定 commit `e13cd45c`: rc=0, match 200 / mismatch 0 / native_crash 0 / wasm_trap 0, §4.1)。以後のコード差分 `6a7010ffc` は未再測定 (§1.1) |
| 4. `liftlib_e2e.sh` の regress に `ott_getparam` を登録 | **達成** (`liftlib_e2e.sh` の (g) 節。PASS の状態で登録) |

本 issue の範囲から外した項目 (本 PR では閉じない。起票先は §6):
- 3. ネガコン: 修正を外した実測は match 147 / 11 (期待値 `0` とは不一致, §4.2)。jtchain 外しは build 不能、leafabi 外しは 15 (§4.3)。
- 5. #883 の受入 4 件 (#883 は closed。残件は §6)。

## 1. 測定 config

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit で測定した commit) | `e13cd45c` (`fix(liftlib): ott_getparam の switch 表 (image 内 .text) を線形メモリへ敷設し leafspec match 1.0 (refs #1270)`) |
| 前段 commit | `896115a7` (入口 this/idx の張り替え)。両 commit は `tools/liftlib/liftlib/{passes/icall.py,pipeline.py}`・`targets/ott_getparam.json`・`liftlib_e2e.sh` のみ |
| 測定後のコード変更 | `6a7010ffc` (`entry_blk_args` の break 正規表現に `tail`/`musttail`/`notail` を追加、`ptr` を `ptrtoint` へ、非対応型を ValueError にする。単体テスト T28〜T31 を追加) |
| 素材 (測定時 e13cd45c) | `$ARTIFACTS_DIR`: `work-liftlib` (→ `tools/liftlib/work/`)・`work-icall` (→ `tools/icall/work/`、`ott_F.txt`)・`work-m6-ott` (→ `tools/m6/work/` ほか)・`analysis-ott-binaries` (→ `[ANALYSIS-PLUGINS]` の `ott/binaries/OTT_vst2_win64.dll`)・`toolchain-emsdk` (→ `[EMSDK]`)・`toolchain-retdec` (→ `[RETDEC]`)。`fl-win64` は本測定に不要 |
| 素材 (本 fix run の検証・検証 HEAD は §5) | `ls $ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ (`analysis-ott-binaries`・`work-*`・`toolchain-*` は無い)。`which emcc` は空で、`/opt` に retdec・emsdk が無い。leafspec は再測定できない (§1.1)。PR 本文の `oc_artifacts:` 行に必要素材を指定した |
| 再現 | `cd tools/liftlib && OTT_DLL=<[ANALYSIS-PLUGINS]>/ott/binaries/OTT_vst2_win64.dll python3 -m liftlib leafspec targets/ott_getparam.json --n 200` |
| 測定値 | wall 61.98 s (`real 1m1.976s`)・開始時 load 0.74 / 0.83 / 0.57 (runner 4 コア, 単発) |

### 1.1 測定後のコード差分 (未再測定)

確認コマンド: `git diff e13cd45c HEAD -- tools/liftlib/liftlib tools/liftlib/targets tools/icall/rt` (HEAD `6a7010ffc`)。差分は **26 行** で、`passes/icall.py` の `entry_blk_args` だけ (`tests/test_unit.py` は測定経路の外):

```diff
diff --git a/tools/liftlib/liftlib/passes/icall.py b/tools/liftlib/liftlib/passes/icall.py
index 69266141b..6c644dd5b 100644
--- a/tools/liftlib/liftlib/passes/icall.py
+++ b/tools/liftlib/liftlib/passes/icall.py
@@ -91,7 +91,7 @@ def entry_blk_args(fn):
         if g:
             gep[g.group(1)] = int(g.group(2))
     for i, ln in enumerate(lines):
-        if re.match(r"^\s*(store|br|ret|switch)\b", ln) or (re.match(r"^\s*(%\S+ = )?call\b", ln) and "@__asm_" not in ln):
+        if re.match(r"^\s*(store|br|ret|switch)\b", ln) or (re.match(r"^\s*(%\S+ = )?(tail |musttail |notail )?call\b", ln) and "@__asm_" not in ln):
             break
         ld = re.match(r"^(\s*)(%\S+) = load i64, ptr (%\S+), align \d+(.*)$", ln)
         if not ld or gep.get(ld.group(3)) not in BLK_ARG_SLOT:
@@ -102,7 +102,11 @@ def entry_blk_args(fn):
         ty, v = params[k]
         if ty == "i64":
             lines[i] = "%s%s = add i64 %s, 0%s" % (ld.group(1), ld.group(2), v, ld.group(4))
-        else:
+        elif ty == "ptr":
+            lines[i] = "%s%s = ptrtoint ptr %s to i64%s" % (ld.group(1), ld.group(2), v, ld.group(4))
+        elif ty in ("i1", "i8", "i16", "i32"):
             lines[i] = "%s%s = zext %s %s to i64%s" % (ld.group(1), ld.group(2), ty, v, ld.group(4))
+        else:
+            raise ValueError("entry_blk_args: unsupported param type %r (%s)" % (ty, v))
         n += 1
     return n
```

- 再測定できない理由: 本 fix run の素材は `fl-win64` のみ。`analysis-ott-binaries`・`work-liftlib`・`work-icall`・`work-m6-ott`・`toolchain-emsdk`・`toolchain-retdec` は無く、`emcc`・retdec も無い (§1)。以下は推定で、差分 0 の証跡ではない。
- 推定 1 (型分岐。根拠はコードの読みと rc=0): `i1`/`i8`/`i16`/`i32`/`i64` の出力文字列は旧 `else` 分岐と同一。`ptr` と非整数型は旧版では `zext ptr`・`zext double` の不正 IR になるため、rc=0 の測定経路では発火していない。`this` (slot 0) は `i32 %arg1` (§2) で、測定経路は zext 分岐。
- 推定 2 (break 正規表現): 旧版の置換数は `function_18011e5a0: 2`。新版で結果が変わるのは、入口ブロック 0 の 2 本目の BLK 読み (`getelementptr @__icall_blk, 8/16` の load) より前に `tail`/`musttail`/`notail` 付き call 行がある場合だけ。raw IR での配置は未確認。tail を書き出すのは `recipes/ott/ir7_argpass_fixed.py` (264 行) だけ (`grep -rn "tail call" tools/liftlib/liftlib --include=*.py` で確認)。RetDec 出力の tail の有無は未確認。
- 確定させる方法: (a) HEAD で §4.1 の leafspec を再測定する (rc=0・200/0/0/0 なら測定経路で無害)。(b) 測定時の入口 IR の block 0 で、2 本目の BLK 読みより前に `grep -nE '(tail|musttail|notail) call'` が 0 件であることを確認する。
- PR 本文の `oc_artifacts:` 行に上の素材を指定した。次の review run がこの行で素材を取得する (§6 の未解決表)。

## 2. 方式 (受入 1): 入口 this/idx は `%arg` から読む

- 機械語 (`OTT_vst2_win64.dll` の `0x18011e5a0`): `sub rsp,0x28; cmp edx,0x1e; ja …; lea r9,[rip-…]; movsxd rax,edx; mov r8d,[r9+rax*4+0x11e6f0]; add r8,r9; jmp r8`。this は rcx (`movss xmm0,[rcx+0x2dc]` 等)、idx は rdx。
- harness (`liftlib/harness/spec.py`): spec `args = [ptr this, int idx]` → 出力 `A 0 ptr this` / `A 1 i <idx>` (slot 0 = this, slot 1 = idx)。
- `native_runner.c` (`M pos` = abi `ms_pos`): slot k → `gpr[k]` (k=0 → rcx, k=1 → rdx)。機械語と一致。
- `wasm_runner.mjs` / `wasm_sig`: slot 0 → `i32 %arg1` (this)、slot 1 → `i64 %arg2` (idx) を wasm 関数の引数として渡す。
- RetDec 由来の IR の入口は `load BLK+0x08` (this) / `load BLK+0x10` (idx) で、引数 `%arg1` / `%arg2` を読まない。`icall_rewrite.py` が rcx/rdx を BLK に退避する約束 (BLK_RCX=0x08, BLK_RDX=0x10) の入口版。
- 選ばなかった方式 (b) (harness が `__icall_blk` へ this/idx を書く): leaf は呼出し元を持たない root のため BLK を埋める主体が無い。wasm 側の `__icall_blk` の番地を harness へ出す export も要る。(a) は native の ABI そのものに合わせるだけなので、こちらを採る。
- 実装: `passes/icall.py` の `entry_blk_args(fn)` (入口ブロックで BLK への store・非 asm の call より前にある `load i64` の BLK+0x08/+0x10 を `zext`/`add` で `%argN` に置換。置換数を log)。`pipeline._repair_ll` が `iargs` の後・`f2` の前に `passes.icall.entry_args: true` のときだけ呼ぶ。`ott_getparam` だけ有効 (`targets/ott_getparam.json`)。置換数は `function_18011e5a0: 2`。

## 3. switch 表の敷設 (受入 2 の残り)

- 入口の `switch` は `movsxd rax,edx` → `[r9+rax*4+0x11e6f0]` の相対オフセット表を読む。表は `.text` の中 (RVA `0x11e6f0`, VA `0x18011e6f0`, 31 entries = 0x7c byte)。
- IR はこれを絶対アドレス `inttoptr (0x3011e6f0 + idx*4)` で読むが、gdata の global (`@global_var_*` 528 件) はこの番地を含まない。`.text` は敷設されていないため、wasm 上の表は 0 → `switch` が default に落ち、`this+0x2dc` を返していた。
- 対応: `cfg.image_bytes = ["0x18011e6f0-0x18011e76c"]` を指定すると、`pipeline.image_bytes_c` が PE の該当バイト列を `passes.shift.newbase` へ写して起動時 (`__attribute__((constructor))`) に `memcpy` する C (`<name>_imgbytes.c`) を書き、emcc の source に加える。`.rdata`/`.data` 全体ではなく範囲を指定するのは、`.text` 全体 (約 2 MB) を C 配列にすると生成物が重すぎるため。
- 範囲は機械語の `cmp edx,0x1e; ja` (idx 0..30) から決めた。他の target には影響しない (`image_bytes` が無いと `image_bytes_c` は None を返し、従来どおり)。

## 4. 実測

### 4.1 HEAD `e13cd45c` (受入 2・測定 commit)

| 設定 | rc | wall | match / mismatch / native_crash / wasm_trap | gate |
|---|---|---|---|---|
| `e13cd45c` (entry_args + image_bytes) | 0 | 61.98 s | **200 / 0 / 0 / 0** | PASS (rate 1.000) |

### 4.2 ネガティブコントロール (測定 commit `e13cd45c` で JSON のみ変更。測定後に削除)

| 設定 | rc | match / mismatch / native_crash / wasm_trap | gate | 解釈 |
|---|---|---|---|---|
| entry_args **off** (image_bytes on) | 1 | 147 / 53 / 0 / 0 | FAIL (0.735) | 表は敷設されるが this=0 のまま。53 件は this に依る戻り値 (xmm0 不一致) |
| image_bytes **off** (entry_args on) | 1 | 11 / 189 / 0 / 0 | FAIL (0.055) | this は正しいが表が 0 → default 分岐。表の敷設が無いと一致は 11 件のみ |
| 両方 off | 1 | 147 / 53 / 0 / 0 | FAIL (0.735) | **未再測定**。`REPORT_APPENDIX_2128.md` の測定 (測定 commit `f8bd2ea0`・2 回とも 147 / 53 / 0 / 0) からの引用。旧版の「bb9530a4 相当・本付録の再測定と一致」は根拠が無いため削除 |

- 本文の想定「修正を外すと match 0」は実測と一致しない (両方 off でも 147。this=0 でも native が 0 を返す scenario は一致する)。期待値 `0` は採らず、上の実測を正とする。

### 4.3 jtchain / leafabi の切り分け (測定 commit `e13cd45c` で JSON のみ変更)

| 外したもの | 結果 | 解釈 |
|---|---|---|
| `passes.icall.jtchain = false` | emcc が失敗 (`wasm-ld: symbol exported via --export not found: function_18011e5a0`) | 入口関数が lift されない。jtchain は leaf の成立条件。match の寄与は測れない |
| `passes.leafabi` (`ret_xmm0`) | rc=1, match 15 / mismatch 185 / wasm_trap 0 | 戻り値 (xmm0) の読み出しに必須。寄与は大 |

## 5. 検証範囲 / 範囲外

- `python3 tests/test_unit.py` (`tools/liftlib`・コード差分の最終 commit `6a7010ffc`・本 fix run の素材は `fl-win64` のみ): **関数 32 件中 FAIL 8** (t1 t2 t3 t4 t6 t7 t9 t26)。出力行 33 件の内訳は ok 17・skip 8・FAIL 8 (T17 関数は T17a ok と T17b skip の 2 行を出す)。
  - FAIL の理由 (出力の例外で確認): t1〜t4・t6・t7・t26 は素材の FileNotFoundError (`m6/work/ott_lift.ll`・`m6/work/ott.drc.ll`・`liftlib/work/fa_gain/fa_gain.drc.ll`・freshair の work・`OTT_vst2_win64.dll`)。t9 は `m6/work/m6_stubs_hand.c` が無く、期待値 `m6_stubs_hand.c: 4` が 0 件になるための AssertionError (`m6_rt.c` 2・`m8_rt.c` 2・`m10_boot.c` 1 は期待値どおり)。レビュー (round 2) の確認環境では t9 が skip だった。素材の有無で結果が変わる。
  - 新規の T28〜T31 は ok。変更前の `icall.py` に対する T28・T29・T30 の FAIL (ネガコン) は前 round の run で確認済み。
- 素材が揃った環境 (測定 commit `e13cd45c` 時点) の記録: 28 件中 27 ok、T6 のみ FAIL。
- `liftlib_e2e.sh` 全体は未実行 (素材 `work-liftlib-targets` 不足のため。(g) 節の leafspec 行は測定 commit の単発測定で代替)。
- `ott_route` / `ott_iargs` の出力は未測定 (新フラグは `ott_getparam` の JSON にしか立てていない。コード上は `entry_args` / `image_bytes` が無い cfg で従来の分岐に入る)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD の leafspec 再測定 (§4.1 の HEAD 版)。必要素材 `analysis-ott-binaries work-liftlib work-icall work-m6-ott toolchain-emsdk toolchain-retdec` は本 fix run に無く、再測定できなかった。PR 本文の `oc_artifacts:` 行に指定済み | 受入 2 の実測は測定 commit `e13cd45c` のまま。コード差分 `6a7010ffc` の影響は §1.1 の推定止まり | #2861 (HB-H49・ott_getparam の leafspec 前後比較を受入に持つ open issue へコメント) |
| 両方 off の再測定 (§4.2)、ネガコンの期待値 `0` と実測 147 の不一致、jtchain の切り分け (jtchain 外しは入口関数が消えて build 不能。代替の切り分け方法は未検討) | #1270 の受入 3 の一部 (本 issue から外した)。#883 の受入 3 の残件 (#883・#415 は closed) | #2861 (同上) |
| `work-liftlib-targets` 素材での T6 (freshair/kilohearts) 回帰。素材依存の T9 (`m6/work/m6_stubs_hand.c`)・T26 の再確認 | 既存 recipe の回帰は素材の要らない T1〜T5・T7〜T27 のみ | #3145 (LIFTLIB-23・liftlib_e2e の再測定の open issue へコメント) |
| `ott_route` / `ott_iargs` の出力は未測定 (新フラグは `ott_getparam` の JSON のみ) | 他 target への影響は未実測 | #2861 (HB-H49・iargs の open issue) |
| 新類型 D26 案 (§7) の DEFECTS.md 登録 | DEFECTS.md の編集は PM 判断 (WORKFLOW §5) | #2446 (SHX-T29・DEFECTS への類型記録の open issue へコメント) |

## 7. 新類型の行案 (DEFECTS.md 形式・採番は PM)

D5 (引数の取り違え・xmm 引数) と近縁だが別。D5 は ABI 解析が xmm 引数を整数 reg と取り違える。本件は ABI 解析 (iargs が `%argN` を足す) は正しく、icall_rewrite の「呼出元が BLK へ rcx/rdx を退避する」規約を、呼出元の無い root (harness が直接呼ぶ leaf) の入口へそのまま残すことで起きる。D4 (deref 脱落)・D7 (stack 引数) とも別。

| 項目 | 内容 |
|---|---|
| ID | D26 (案。採番は PM) |
| 種別 / 状態 | fe+ours (icall 規約の適用範囲) / **新規** (#1270 で観測。修復は `6a7010ffc`・測定 `e13cd45c`) |
| 症状 | 直接呼出し (harness が仮引数で呼ぶ root) の入口が this/idx を BLK+0x08/+0x10 から読み、仮引数 `%arg1`/`%arg2` を読まない。BLK は harness が書かないので 0 が入り、戻り値が静かに狂う (ott_getparam: match 147/200 で FAIL。trap は出ない) |
| 根本原因 | icall_rewrite は rcx/rdx を「呼出元が BLK へ退避する」前提で、入口にも同じ BLK 読みを残す。呼出元の無い leaf の入口では BLK は未初期化のまま読まれる |
| 観測 | ott_getparam の入口 `function_18011e5a0` のブロック 0: `getelementptr @__icall_blk, 8/16` の load が store・非 asm call より前にある (置換数 2)。機械語は rcx/rdx を読む |
| 検出信号 | 入口ブロックで BLK+0x08/+0x10 を読む load が store・非 asm call より前にあり、同じ関数に `%argN` 仮引数がある (`entry_blk_args` と同じ判定) |
| 修復 | `passes/icall.py` `entry_blk_args`: 入口の BLK 読みを `%argN` へ張り替える (`passes.icall.entry_args: true`・ott_getparam のみ) |
