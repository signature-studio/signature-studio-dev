# #5695 unit 895: e3ef60 の arg1 (0x12ba808) のフィールド書込み元 (部分達成)

親: #882 (受入 2 の残り)。対象: `tools/m11/trap_triage/REPORT_684.md` §4 の unit 895 (`function_40ff70` の `*(p-144)` OOB)。
素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)・`work-m11` (展開先 `tools/m11/work`)・`[EMSDK]`・`[RETDEC]` (既存)。

## 0. 結論

1. e2e (`m11_e2e.sh`) は 2 回とも全再生成 (Ghidra / RetDec lift) に入り、1 回目は 900 s の timeout で打ち切り、2 回目は 565 s で終了 (rc=1、summary は reached_stage 4/6・trap 停止。受入の判定用ではない)。snapshot に `lift_pe.sha256` と `functions_dll.csv` が無いため毎回全再生成になる。
2. survey (`SV_RAW=1 survey_units.mjs`) の基準: **ok 875 / miss 46 / halt0 6 / oob 14 / noproc 1** (7 s)。REPORT_684 §8 の旧値 (829/55/11) とは一致しない (e2e の build が変わったため)。unit 895 は oob のまま (`function_40ff70` ← `40ffe0` ← `60a270` ← `e3ef60`)。
3. **arg1 (0x12ba808) の 5 フィールド (+0x778・+0x7d8・+0x810・+0x808・+0x7f0) は、boot 後も unit 895 の実行前後も全て 0 のまま** (unit 境界の値)。survey と同順 (0..941) の全 942 unit を実行しても、unit 境界で値が変わる unit は 1 件も無い (`probe5695_arg1.mjs`)。unit 境界の値は 942 unit 後も 0 のまま。unit 内での書込み (書き戻し・同値書込み 0→0 を含む) は観測できないため、書込みの有無は未確定 (書込み元の特定が要る)。
4. 同じ領域 `[0x12ba808, +0x1000)` は boot 終了時に非 0 バイトが 0 件、unit 895 実行後に 320 件 (`probe5695_nz.mjs`)。構造体の領域は後から非 0 になるが、問題の 5 フィールドは unit 境界で値が変わらない (unit 内の書込みの有無は未確定)。
   この 320 件が unit 895 より前の unit で入ったか、895 で入ったかは未測定 (894 以前の時点を取っていない)。

## 1. 未達 (受入条件)

- [ ] 書込み元の特定: JS 観測では unit 境界の値変化が見えない (unit 内の書込みは観測不能。書込みの有無は未確定)。書込み元 (命令番地) を取るには IR 計装 (`watch_store_682.py` 方式の store 監視) が要る。e2e の再生成を含めて 1 run では収まらない。
- [ ] `40ffe0` の引数 (リスト先頭) の出所と `p-144` の構造体: 未実施。
- [ ] DEFECTS.md 行案: 書込み元が未特定のため判定せず。

## 2. 次の一手

1. 5 フィールドの書込み監視: `watch_store_682.py` の仕組みで `[e3ef60 の arg1 + 0x778 等]` への store の IR 位置 (`sites.json`) を出す。
2. 320 バイトの入る unit: `probe5695_nz.mjs` を unit 単位 (894 まで) に広げ、どの unit で非 0 になるかを見る。
3. 再生成を避ける: `work/` に `lift_pe.sha256` と `functions_dll.csv` を残す (e2e の再生成条件の修正は別作業)。

## 3. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$FL_WIN64_DIR"    # 展開先は $FL_WIN64_DIR/extracted/...
tar --zstd -xf "$ARTIFACTS_DIR/work-m11.tar.zst" -C <repo root>
cd tools/m11
bash m11_e2e.sh                                  # 初回は全再生成 (565 s 実測・2 回目)
SV_RAW=1 node trap_triage/survey_units.mjs work/trap_triage/head5695.json   # 7 s
node trap_triage/probe5695_arg1.mjs              # 5 フィールドの変化 (7 s)
node trap_triage/probe5695_nz.mjs                # 0x12ba808 近傍の非 0 バイト数
```

## 4. 測定の記録

| 項目 | 値 | 備考 |
|---|---|---|
| e2e 1 回目 | 900 s で timeout (rc=124) | 全再生成の途中 (lift boot4 #2 まで) |
| e2e 2 回目 | rc=1, 565 s, reached_stage 4/6, units_run_full 98, survey_ok 875, survey_trap 20 | summary の `stop_reason` は trap @ function_535c11 (unit 1 件目の trap) |
| survey | 7 s, ok 875 / miss 46 / halt0 6 / oob 14 / noproc 1 | `head5695.json` (`work/`, 非コミット) |
| probe5695_arg1 | 7 s, unit 境界での変化 0 件、target 895 前後とも全 0 | `initial= 0 0 0 0 0`。unit 内の書込みは未観測 |
| probe5695_nz | boot 終了 0 件 → unit 895 後 320 件 | 894 以前は未測定 |

### 4.1 測定 commit と差分 0 の証跡

- 測定 commit: `13b13c38a` (新規 probe と REPORT のみ。実行コードの変更なし)。
- `git diff 13b13c38a HEAD -- tools/m11 ':(exclude)*.md'` の出力: 空 (実行コードの差分 0)。
- `git diff --stat 13b13c38a HEAD -- tools/m11`: `trap_triage/REPORT_5695.md` のみ (文言修正)。

### 4.2 未解決の起票先

- e2e の全再生成 (`lift_pe.sha256` / `functions_dll.csv` 不在): #5190 (`[M11-N235]` work-m11 の素材を作り直す)。

## 5. 2 回目 run: IR store 計装による arg1 の書込み監視 (結論: IR store の書込みは 0 件)

測定 commit: `09ceb363a` (HEAD のクリーン worktree `git worktree add --detach` で測定。コードを変えた最後の commit は `086abd95a`)。
`git diff 086abd95a HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (実行コードの差分 0)。

手順 (すべてコミット済み HEAD の内容。`work-m11` ・`toolchain-*`・`fl-win64` は本 run の素材から展開):
`m11_gen_ir2.sh` (52 s・rc 0・ldfix applied) → `ALLOCA_SKIP=1 M11_WATCH_SRC=trap_triage/watch_arg1_5695.c bash trap_triage/store_watch_1783.sh <tag>`
(全 store 計装 15,028 site・survey は全 942 unit を順に実行)。`[a1]` は範囲 `[0x12ba808+0x778, 0x12ba808+0x814)` と store の範囲が重なる書込み。

| 測定 | 値 | 備考 |
|---|---|---|
| クリーン HEAD・計装 ON・survey 1 回目 | 60 s・ok 873 / miss 47 / halt0 6 / oob 15 / noproc 1・`[a1]` 0 件 | load 0.78 (開始前) |
| 同・survey 2 回目 | 69 s・ok 871 / miss 47 / halt0 7 / oob 16 / noproc 1・`[a1]` 0 件 | load 1.08 (終了後) |
| 陽性対照 `0x10aa1428` (4B・コミット済み `watch_addr_1046.c` に `M11_WATCH_1783=0x10aa1428`) | `[aw]` 22 件 (unit -1 / 134 / 830 ほか)・ok 870 / oob 17 | HEAD の内容のみで再現 |
| 陰性対照 `0x10a9f910` (同) | `[aw]` 0 件・ok 871 / oob 16 | HEAD の内容のみで再現 |
| 範囲 `[0x12ba808, +0x1000)` の `[a1]` 88 件 | 未再現 | 前 run の値は非コミットの C 由来。本 PR では数値を書かない |

解釈 (クリーン HEAD で 2 回実測):
- 監視の仕組みは動いている (陽性対照で検出、陰性対照で 0 件)。5 フィールドは本 build の survey 中に **IR store では 1 回も書かれない** (2 回とも `[a1]` 0 件)。
- survey の内訳は実行ごとに揺れる (ok 871〜873、oob 15〜17)。基準値は 1 点ではなく、この幅で読む。
- `initial= 0 0 0 0 0` (boot 後) から 0 のまま。IR store に書込みが無いので、書込み元の特定は IR store 計装の範囲では行えない。
- 残る書込み経路は C 側 (`memcpy`・`rep movs` 等の runtime 関数)。store 計装 (`watch_store_682.py`) はそれを映さない (`rep_watch_3972.py` の注記)。C 側を見るには `m11_rt`/`m11_win` の copy に監視を入れる必要がある (未実施)。
- PR #5707 の測定 (ok 875 / oob 14) とは一致しない (e2e・build の差。計装 OFF の基準は未測定)。

## 6. 次の一手 (未解決)

1. `e3ef60` の arg1 (0x12ba808) を誰が確保・初期化するか (boot 中の alloc / 0 初期化の位置)。フィールドが「0 のまま」なら、e3ef60 が非 0 を期待する根拠の側を見る。
2. C 側 (`memcpy`・`rep movs`) の書込みを監視する (`rep_watch_3972.py` の方式)。
3. `40ffe0` の引数 (リスト先頭) の出所 (受入の残り)。

## 7. 3 回目 run: C 側 (copy・rep helper) まで含めた書込み監視 (survey 未測定・次 run)

本 run の結果: 監視 ON の survey は**未測定**。`work-m11` と `toolchain-emsdk` は展開できたが、`fl-win64` が無く `m11_gen_ir2.sh` (PE 必須) で `work/ir_conditions.json` (`ldfix=applied`・指紋) を作れず、`m11_build.sh` の gate で止まった (`ldfix=applied` の記録無し)。gate は迂回していない。したがって 3 経路の結果は本 run では得られていない (旧版の「0 件」結論は根拠が無いため取り下げた)。

監視: `store_watch_5695.sh` (新規)。範囲 `[0x12ba808+0x778, +0x814)` を 3 経路で同時に見る。
- IR store: `watch_arg1_5695.c` (`[a1]`)。
- copy (`409c80` の入口): `watch_copy_5695.c` の `m11_copy_in` (`[a1cp]`)。
- rep 系 helper (movsq/movsb/stosq 35 箇所の入口): 同 C の `m11_rep_in` (`[a1rp]`)。

手順 (次 run で行う): `m11_gen_ir2.sh` (`fl-win64` が要る) → `bash trap_triage/store_watch_5695.sh <tag>` (全 942 unit の survey)。陽性対照は `WATCH_LO=0x10aa1428 WATCH_BASE=0 WATCH_SPAN=32`。

| 測定 | 値 | 備考 |
|---|---|---|
| 監視 ON・survey (arg1 範囲) | 未測定 (次 run) | 本 run は IR 指紋を作れず build 前に停止 |
| 陽性対照 (32 B) | 未測定 (次 run) | 監視が 3 経路で検出するかは未確認 |

測定の記録 (review r4 の指摘への回答):
- 測定 commit: 未確定。本節の監視コードを追加した commit は `42250fabc` と推定するが、測定は行っていないため測定 commit ではない。
- 生の `SURVEY_UNITS` 行・`[a1]`/`[a1cp]`/`[a1rp]` の件数は本 run に存在しない。前 revision の数値は §5 の値と同一で、転記か偶然の一致かを確認できなかったため削除した。
- `git diff 42250fabc HEAD -- tools/m11/trap_triage/store_watch_5695.sh tools/m11/trap_triage/watch_copy_5695.c tools/m11/trap_triage/watch_arg1_5695.c` の出力 (`22de1a37e` の差分のみ。ヘッダと取得行の周辺だけを抜粋):

```diff
diff --git a/tools/m11/trap_triage/store_watch_5695.sh b/tools/m11/trap_triage/store_watch_5695.sh
@@ -2,12 +2,13 @@
-#   usage: store_watch_5695.sh <tag>   (前提: 素材 work-m11 を展開済み・EMSDK_ENV を設定 (旧既定は [EMSDK] の位置))
+#   usage: store_watch_5695.sh <tag>   (前提: 素材 work-m11 を展開済み・EMSDK_ENV を設定 ([EMSDK]・docs/REFERENCES.md §4))
 set -uo pipefail
 HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
-source "${EMSDK_ENV:-<[EMSDK] の既定パス>}" > /dev/null 2>&1   # [EMSDK] (docs/REFERENCES.md)
+: "${EMSDK_ENV:?EMSDK_ENV を設定してください ([EMSDK]・docs/REFERENCES.md §4)}"
+source "$EMSDK_ENV" > /dev/null 2>&1
```

- 差分は EMSDK 取得行だけ。`watch_copy_5695.c`・`watch_arg1_5695.c` は差分 0。監視の範囲・計装・survey の経路は不変。唯一の挙動差は `EMSDK_ENV` 未設定時に `[EMSDK]` の既定へ落とさず停止すること (測定時の環境では設定済みの前提で、経路は同じ)。

解釈:
- 5 フィールド (+0x778・+0x7d8・+0x7f0・+0x808・+0x810) の IR store・copy・rep helper 経由の書込みの有無は、本 run では判定していない (次 run で測定)。§5 の IR store 計装 (クリーン HEAD で 2 回) の結果は有効。
- 残る書込み経路は C runtime 内の直接 store (`m11_rt`/`m11_win`)。この経路は計装していない。
- 「0 のまま」の理由は、監視できた範囲では説明できない。次は `e3ef60` が arg1 を確保・初期化する位置と、`e3f178` の分岐条件を見る。

### 7.1 `40ffe0` 引数の出所 (IR 読取り・受入 (b) の一部)

- `60a270(arg1, arg2)` (IR 208429 行): `arg2 != *(arg1+169)` のとき `40ffe0(arg1, sext((arg2 & 0xFFFF0000) | 65485))` を呼ぶ。`65485 = 0xFFCD`。
- つまり 895 の `40ffe0` の引数は、`60a270` の `arg2` の上位 16 bit を残し、下位を `0xFFCD` にした定数。OOB の原因は `arg2` (`e3ef60` 側の値) の上位 16 bit。
- `40ffe0` (IR 113231) は `*(arg1)` を `40ff70` に渡すだけで、`p-144` の構造体は `40ff70` 側の入口で決まる。
- 未了: `e3ef60` が `60a270` に渡す `arg2` の由来 (9 呼出しのうち 895 に至るもの)。

### 7.2 未解決 (次 run・起票先)

- C runtime 内の直接 store (`m11_rt`/`m11_win`) の監視: 親 #882 の続き。
- `e3ef60` → `60a270` の `arg2` の由来と `e3f178` の分岐条件: 親 #882 の続き。
- DEFECTS.md 行案 (受入 (c)): 書込み元と `arg2` の由来が未確定のため未判定。

## 8. 4 回目 run: C 側の直接 store まで含めた書込み監視 (結論: 942 unit で 0 件)

測定 commit: 本 PR の HEAD (`origin/main` = `58ee21f1e` から派生。計装は `M11_WATCH_C5695` 定義時のみ有効)。
素材: `fl-win64` (PE 抽出)・`work-m11`・`toolchain-emsdk` を本 run で展開。`m11_gen_ir2.sh` rc=0・52 s。

計装 (C 側): `m11_ov.c` の `Q`/`D`/`B` マクロ (約 267 箇所) を `m11_cwatch` 経由に差し替え (`M11_WATCH_C5695` 定義時のみ)。
加えて `function_40fb40` の `memset`・`m11_InitLib` の `memcpy`・`function_40d210` (FillChar) の入口を監視。
IR store (`[a1]`)・copy (`[a1cp]`)・rep helper (`[a1rp]`) は §5・§7 と同じ計装を使う。
集計は `survey_units.mjs` の `printErr` 経由の `work/probe5695/<tag>.aw` で数える (`.err` は unit 進捗行のみ)。

| 測定 (計装 ON・全 942 unit) | ok/miss/halt0/oob/noproc | `[a1]` | `[a1c]` | `[a1cp]` | `[a1rp]` | 備考 |
|---|---|---|---|---|---|---|
| 本命 (5 フィールド範囲 `[0x12ba808+0x778, +0x814)`) | 873 / 47 / 6 / 15 / 1 | 0 | 0 | 0 | 0 | 書込み 0 件 |
| 陽性対照 近傍 `[0x12ba808, +4 KB)` | 871 / 47 / 7 / 16 / 1 | 88 | 0 | 5 | 0 | 検出する |
| 陽性対照 `[0x12000000, +64 MB)` | 871 / 47 / 7 / 15 / 1 | 20,000 (上限) | 1 | 5 | 0 | 検出する |
| 陽性対照 全アドレス | 871 / 47 / 8 / 15 / 1 | 20,000 (上限) | 20,000 (上限) | 2,000 (上限) | 10 | 検出する |

- 本命の `[a1]`・`[a1c]`・`[a1cp]`・`[a1rp]` はすべて 0。対照では同じ判定式で検出するので、0 件は監視が効いた上での 0 件。
- 読取り計装の survey 結果 (ok 873 / oob 15) は、§5・§7 の値と同じ範囲に収まる。
- `[a1]` の件数は、前 run までの `.err` 集計では 0 と読めていた。`.err` は unit 進捗行しか持たず、計数は `.aw` で行うのが正しい (本 run で訂正)。

### 8.1 解釈

- 5 フィールド (+0x778・+0x7d8・+0x7f0・+0x808・+0x810) への書込みは、IR store・copy・rep helper・C runtime の直接 store のどの経路でも、942 unit の survey 中に **1 件も無い**。
- したがって受入 (a)「書込み元の命令番地」は、この範囲の survey では特定できない。書込みが無いなら、前提 (「書込みで 0 になる」) が違う。
- PE の `.data` は `0x13a5000` 以降で、arg1 `0x12ba808` は `.text` 内の低いアドレス。arg1 は PE の静的データではなく、実行時の確保先である。初期値は確保・初期化の時点で決まる。
- `e3ef60` (IR 443418) は arg1 `+0x304` (772) → `+0xb4` (180) → `+0xc` を読む。`+0x778` は読み取り側の入口で、0 のまま読まれるのが通常経路かは未確認。

### 8.2 未解決 (起票先: 親 #882 の続き)

- 受入 (a): 書込みが無いことが分かったため、「書込み元」の前提を外して再定義する必要がある。判断は PM。
- 受入 (a'): `40ffe0` の引数 (`60a270` の arg2 の上位 16 bit) の由来と `e3ef60` の分岐 (`e3f178`) の条件。
- 受入 (b): DEFECTS.md 行案は (a)(a') が決まるまで判定しない。
