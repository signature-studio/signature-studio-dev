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

測定 commit: `086abd95a` (コードを変えた最後の commit。`trap_triage/watch_arg1_5695.c` の追加のみ)。
`git diff 086abd95a HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (測定時のコードと HEAD が一致)。

手順: `m11_gen_ir2.sh` (ldfix applied) → `ALLOCA_SKIP=1 M11_WATCH_SRC=trap_triage/watch_arg1_5695.c bash trap_triage/store_watch_1783.sh <tag>`
(全 store 計装 15,028 site・survey は全 942 unit を順に実行)。`[a1]` は範囲 `[0x12ba808+0x778, 0x12ba808+0x814)` と store の範囲が重なる書込み。

| 測定 | 値 | 備考 |
|---|---|---|
| HEAD `086abd95a` の survey (計装 ON) | 62 s・ok 873 / miss 47 / halt0 6 / oob 15 / noproc 1・`[a1]` 0 件 | load 0.94 (開始前)・0.94 (終了後) |
| 陽性対照 `0x10aa1428` (4B 範囲) | `[a1]` 20 件 (unit -1 / 134 / 144 ほか) | 監視 C の範囲だけを変えた (非コミット)。監視関数は動いている |
| 陰性対照 `0x10a9f910` (REPORT_1046 の番地) | `[a1]` 0 件 | この build では書込みが観測されない (REPORT_1046 の番地は本 build の対照にならない) |
| 範囲 `[0x12ba808, +0x1000)` | `[a1]` 88 件。store offset は 0x818・0x81c・0x820・0x840・0x848・0x850・0x858・0x868・0x878・0x888 | 5 フィールド (+0x778・+0x7d8・+0x7f0・+0x808・+0x810) への書込みは 0 件 |

解釈:
- 監視の仕組みは動いている (陽性対照で検出)。5 フィールドは全 942 unit の survey 中に **IR の store 命令では 1 回も書かれていない**。
- つまり「フィールドが書込みで 0 になる」という前提は本 build では成り立たない。`initial= 0 0 0 0 0` (boot 後) から 0 のまま。書込み元の特定は、書込みの無い対象に対しては行えない。
- 残る書込み経路は C 側 (`memcpy`・`rep movs` 等の runtime 関数)。store 計装 (`watch_store_682.py`) はそれを映さない (`rep_watch_3972.py` の注記)。C 側を見るには `m11_rt`/`m11_win` の copy に監視を入れる必要がある (未実施)。
- 本 build の survey (ok 873 / oob 15) は PR #5707 の測定 (ok 875 / oob 14) と一致しない。`m11_gen_ir2.sh` を作り直したためで、計装の影響ではない (計装 OFF の基準は未測定)。

## 6. 次の一手 (未解決)

1. `e3ef60` の arg1 (0x12ba808) を誰が確保・初期化するか (boot 中の alloc / 0 初期化の位置)。フィールドが「0 のまま」なら、e3ef60 が非 0 を期待する根拠の側を見る。
2. C 側 (`memcpy`・`rep movs`) の書込みを監視する (`rep_watch_3972.py` の方式)。
3. `40ffe0` の引数 (リスト先頭) の出所 (受入の残り)。
