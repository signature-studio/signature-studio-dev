# M11 × shimx リンク 付録: midiOutShortMsg の HANDLE 幅 (#1628 SHX-T25)

- 本体の要約は `tools/m11/shimx_link/REPORT.md` §12。測定値はこの付録が正本。
- 既知類型との関係: 該当なし。D11 (絶対 VA の i64 定数の切り捨て) と D17 (8B store の 4B 縮小) は wasm32 の幅差を含むが、機構は別。本件は外部関数 (shimx) との宣言の型幅 (IR の `i64` と wasm32 HANDLE の `i32`) の不一致で、切り詰めても HMIDIOUT の値は変わらない (wasm32 のハンドルは i32 に収まる)。

## 12. midiOutShortMsg の HANDLE 幅 (#1628 SHX-T25): IR 側の正規化

測定 commit `e0e35f9a` (修正 pass の測定時点)。その後の変更は §12.4 (fail-closed 化) のみ。

- 原因: IR (`boot_final3.ll`) は `declare i32 @midiOutShortMsg(i64, i32)` と `i64 %hmo` で呼ぶ。shimx 定義 (`tools/shimx/src/midi_conv.c:163`) は wasm32 の HANDLE = i32。`signature mismatch` は trace では `trace_wrap.o` (gen_link.py が IR の型を写す)、plain では IR の import 型そのものから出る。
- 方式: 受入条件 1 の後者 (IR 側の正規化)。plain と trace の両方を直せ、gen_link.py が正規化後の IR から trace_wrap.c を作るため。`trunc i64→i32` は値を変えない (HMIDIOUT は wasm32 のハンドルで i32 に収まる)。
- 実装: `sx_handle_norm.py` (宣言 1 件・呼出し 1 件を変換。想定外の参照が残れば fail-closed)。`build.sh` の 2c (`--fix` の後・gen_link の前、全 variant)。

### 12.1 変換結果 (クリーン build)

| variant (gui=soft) | 修正前 (`26f90ada`) | 修正後 (`e0e35f9a`) |
|---|---|---|
| plain / `--fix` / `--fix --ws` / `--fix --midi` | signature mismatch 1 (×4) | 0 (×4) |
| trace / `--trace --fix` | 1 / 未測定 | 0 / 0 |

undefined / duplicate は全件 0。修正前の値は旧 build.sh を一時コピーして同じ IR で実行した (ネガティブコントロール)。

### 12.2 実 boot と出典 (修正前の値との IR 同一性)

- 修正後 trace `--fix` (`e0e35f9a`): `boot_stage 1 / init_count 18 / units_run 17/942 / icall_ok 24 / icall_miss 1 / threw "memory access out of bounds" / total_calls 97 / distinct 28 / dropped 0`。`midiOutShortMsg` は boot 中 0 件。
- 修正前と並べる値の出典は次のとおり。どれも**本測定の IR と同一ではない**:
  - `units_run 17 / threw OOB / total_calls 97 / distinct_called 28 / dropped 0`: `tools/m11/REPORT_SHX-T27.md` §A-1-2 (main `e051402a`・`build.sh --trace --soft` は `signature mismatch=1`)。同節は **stale な work-m11 IR** での値 (T27 §1・§4-F)。
  - `icall_ok 24`: `tools/m11/REPORT_SHX-T26.md` §1 の表 (D19 ガード版の build・`signature mismatch=1`)。**ガードを加えた別 IR** の値。同じ stale IR の snapshot run は `icall_ok 19 / total_calls 94` (T26 §2)。
- 結論: 修正前後で boot 到達点が同じかは、**同一 IR で修正前を測っていないため確認できていない**。本 run は emcc (`[EMSDK]`) と `work-m11` が無く、IR を作り直せなかった。

### 12.3 e2e (測定 commit `e0e35f9a`)

- `ws_e2e.mjs` (`--fix --ws`): PASS 19 / FAIL 0 (0.40 s)。
- `midi_e2e.mjs` (`--fix --midi`): ALL PASS (0.29 s)。
- `m11_judge.py --require-stage 4 --min-survey-ok 800`: rc 0 (`survey_ok` 812。入力は M11 本体の出力で、shimx_link は入力にならない)。
- 942 unit survey (`survey_trace.mjs`) と plain の boot 到達点は未実施 (未解決: #2444 にコメント)。

### 12.4 測定後の変更 (fail-closed 化) と検証

- 変更 (`763a599d`): `sx_handle_norm.py` で (1) 参照数を `@name(` の部分一致から `@name` の境界一致に変え、関数ポインタ等の `(` を伴わない参照も数える、(2) 参照があるのに素の `declare` が 1 件も無い場合は失敗 (従来は rc 0 で素通り)、(3) 宣言が i32 なのに i64 の呼出しが残る場合は失敗。
- 実 IR への影響 (推定): 測定時の実 IR では宣言の書換えが効いて mismatch が 1 → 0 になっている。つまり宣言は素の形で、新しい失敗分岐は通らない。ただし実 IR の再生成が本 run では不可で、実測していない。
- 合成 IR の検査: `python3 tools/m11/shimx_link/test_sx_handle_norm.py` → `cases=8 fail=0` (rc 0)。
- 旧版 (`e0e35f9a`) と新版の比較 (合成 IR、同じ入力を両版に流した結果):

| 入力 | 旧版 (`e0e35f9a`) | 新版 (`763a599d`) |
|---|---|---|
| 素の `declare` (実 IR と同じ形) | rc 0・i64 呼出し残 0 | rc 0・出力 byte 一致 |
| `declare dso_local ...` (属性付き) | rc 0・i64 呼出し残 3 (無言) | rc 1 (fail-closed) |
| 宣言無し・参照あり | rc 0・i64 呼出し残 2 (無言) | rc 1 (fail-closed) |

- ビルドと e2e の再測定は未実施。`build.sh` の 6 variant・ws/midi/trace の e2e は、emcc ([EMSDK]) と work-m11 が無いため本 run では動かせなかった。fail-closed 化の後の再測定は未解決 (#2444 にコメント)。

コード差分 (測定 commit から HEAD まで・`tools/m11/shimx_link/*.py`): `git diff e0e35f9a 763a599d -- tools/m11/shimx_link/sx_handle_norm.py`

```diff
diff --git a/tools/m11/shimx_link/sx_handle_norm.py b/tools/m11/shimx_link/sx_handle_norm.py
index 28ca1fea..b4fb8f93 100644
--- a/tools/m11/shimx_link/sx_handle_norm.py
+++ b/tools/m11/shimx_link/sx_handle_norm.py
@@ -20,13 +20,17 @@ FN = ('midiOutShortMsg',)   # 第 1 引数が HANDLE (wasm32 = i32) の shimx 
 def norm(lines, name):
     decl_re = re.compile(r'^declare (\S+) @%s\((i64|i32)(, [^)]*)?\)' % re.escape(name))
     call_re = re.compile(r'(\bcall\b[^@\n]*@%s\()i64 ([^,()\s]+), ' % re.escape(name))
+    ref_all = sum(len(re.findall(r'@%s(?![\w.$-])' % re.escape(name), l)) for l in lines)
+    if ref_all == 0:
+        return 0, 0
     decl_idx = [i for i, l in enumerate(lines) if decl_re.match(l)]
-    ref_all = sum(l.count('@' + name + '(') for l in lines)
     if not decl_idx:
-        return 0, 0
+        raise SystemExit('sx_handle_norm: %s の参照 %d 件があるが素の declare が無い (fail-closed)' % (name, ref_all))
     if len(decl_idx) != 1:
         raise SystemExit('sx_handle_norm: %s の宣言が %d 件 (1 件を想定)' % (name, len(decl_idx)))
     if decl_re.match(lines[decl_idx[0]]).group(2) != 'i64':
+        if any(call_re.search(l) for l in lines):
+            raise SystemExit('sx_handle_norm: %s は宣言が i32 だが i64 の呼出しが残る (fail-closed)' % name)
         return 0, 0
     out, n_call = [], 0
     for i, l in enumerate(lines):
```

### 12.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec の IR 生成が HMIDIOUT を `i64` と推定する根本 | 本 PR は link 時の正規化で対処。IR 生成は未修正 | 新規子 #2839 `[SHX-T31]` (親 #1628) |
| 942 unit survey (`survey_trace.mjs`) の再測定と plain の boot 到達点 | 本 run で未実施。midi 呼出は boot 中 0 件 | 既存 issue #2444 にコメント |
| fail-closed 化 (`763a599d`) 後の build.sh 6 variant と e2e の再測定、修正前後の同一 IR での比較 | 本 run で emcc・work-m11 が無く未実施。§12.2・§12.4 の判断は推定を含む | 既存 issue #2444 にコメント |
