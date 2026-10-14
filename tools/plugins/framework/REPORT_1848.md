# #1848 REPORT — fail-soft 3 件の戻り値の読解と Phase B 再測定 (途中経過)

> 注 (#2008 §8 で訂正): `0x710030`・`0x710038`・`0x710040` は FL 本体の export table ではなく Delphi RTL の例外フック (`0x40d6e0` = raise の参照先)。下記の「export table」前提の記述は誤りで、正本は `tools/plugins/framework/REPORT_2008.md` §8.1。

- 担当 issue: #1848 `[PLG-P0b-7]` (親 #1609)。受入 1 (fold deref 解消と `plug != 0`) は未達・子へ移管。
  受入 2 (fail-soft 3 件の戻り値の意味) は部分達成。受入 3 (REPORT 実測) は達成 (§2)。
- 起点: `origin/main` 47ee8a17。worktree `ws-1848`・branch `1848-plg-failsoft-retval`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-fw-stage1`・`work-liftlib`・`work-icall` は repo ルート展開。
  `toolchain-emsdk` / `toolchain-retdec` は runner 側に既設の `[EMSDK]`・`[RETDEC]` を使用 (展開せず)。
  `plugins-ott` は本 run の手順では未使用。
  `ANALYSIS_DIR=$RUNNER_TEMP/analysis` を設定 (`shared/env.sh` の既定値 (`[ANALYSIS-DIR]`) は runner に無い)。

## 1. 受入条件の達成状況

| 出典 | 受入条件 | 結果 |
|---|---|---|
| 旧 #1848 項目 1 (移管) | fold deref を塞ぎ `hs_e2e.sh --fresh` の Phase B で `plug != 0` | **未達**。`0x710030` / `0x710040` の正しい値は FL 本体 export table 由来 (REPORT_1609 §3)。本 run では塞いでいない。子へ移管 (§5) |
| 旧 #1848 項目 2 (一部移管) | fail-soft 3 件 (`0x52cf40` / `0x4e6060` / `0x4181e0`) の戻り値の意味を呼出側読解で確定 | **部分達成**。`0x52cf40` と `0x4181e0` は「0 = 該当なし」と一致しない可能性が高い (§3)。`0x4e6060` は未確定。確定は子へ移管 |
| 旧 #1848 項目 3 (本 REPORT で達成) | REPORT に実測値 (所要時間・load・PASS/FAIL) | **達成** (§2) |

## 2. 実測

環境: 4 vCPU・メモリ 15 GiB。load は `uptime` の開始時値と終了時値。
測定 commit: `47ee8a17` (origin/main、コード変更なし)。

| 手順 | 結果 | 所要時間 (real) | load (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用・`FL_WIN64_DIR` 指定) | exit 0・smoke PASS (`dispatch=38 units_done=0 va=1 heap=1 ff=0`)・`fw_smoke_check` PASS | 7 分 23.66 秒 | 1.29 / 0.64 / 0.27 → 2.33 / 2.28 / 1.14 |
| `hs_e2e.sh --fresh` | exit 1 / Phase A `dispatch=38 ff=0` (回帰 OK) / `[hs] Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` / `E2E FAIL: 1 項目` | 2 分 38.46 秒 | 2.14 / 2.24 / 1.14 → 1.08 / 1.72 / 1.10 |

- Phase A の回帰 `dispatch=38 ff=0` を stage2 と e2e の両方で確認。
- REPORT_1609 §2 の e2e 結果 (exit 1・Phase B OOB・`plug=0x0 rec=7`) と一致。再現。
- 所要時間は各 n=1。REPORT_1609 §2 の値 (stage2 7 分 12 秒・e2e 2 分 37.6 秒) とほぼ同じ。

## 3. fail-soft 3 件の戻り値 (呼出側 IR の読解)

スタブ本体 (`fw_hostfix.py` 178〜193 行) は全て `store i64 0 → slot 9048192 (0x8A1080)`・`ret i64 0`。
つまり「戻り値」は呼出側が読む状態スロット `9048192` (`BLK+0x80`) の値で、スタブは 0 を書く。
呼出側 IR は `hs_flat3.ll` (本 run で生成) を読んだ。

### 3.1 `0x52cf40` (RTL ハッシュ表検索) — 呼出 1 箇所で確認

- 呼出元 `function_52d230` (`hs_flat3.ll` 625849 行付近)。戻り値 `%16` (= スロット 9048192 の値) を
  `%10` と比較する。`%10` は `@442+24` のロード値で、`@442` は `zeroinitializer` の定数なので **0**。
- よって戻り値 0 は `icmp eq` が真となり `dec_label_pc_9a499d` に分岐する。
- この分岐先が「見つからない」に対応するかは **未確認** (分岐先の読解が残る)。
  REPORT_1229 §2 の「見つからない = 0」は、この分岐の意味づけとしてはまだ証拠が足りない。

### 3.2 `0x4181e0` — 0 = 「該当なし」と合わない可能性が高い

- 呼出元 (9072 行付近・31416 行付近など計 40 箇所以上) は、戻り値 (スロット 9048192) を **ポインタの基底** として使う。
  例 (9072 行): `%15` (= スロット値) に `or(…, 24)` を加えて `inttoptr` し、1 バイト読む。
  31416 行付近: `%184` (= スロット値) に `+520` を加えて `inttoptr` し、8 バイト読み書きする。
- よって 0 を返すと呼出側は **アドレス 0 + オフセット** を読み書きする。「該当なし」(空の結果) として扱われるわけではない。
- 注釈 (`fw_hostfix.py` 188〜189 行「該当なし = 0」) は、このアドレス読みと整合しない。これは #1848 本文の注記
  (`0x4181e0` は 0 = 「該当なし」の注釈と合わない可能性) を裏付ける。
- 正しい戻り値の値 (例: 有効なオブジェクトポインタ) は、呼出側の基底が何を指すかを確定してから決める。**未確定**。

### 3.3 `0x4e6060` (自己再帰) — 呼出 1 箇所で確認、意味は未確定

- 呼出元 `function_4e6140` (`hs_flat3.ll` 406491 行付近)。戻り値 (スロット 9048192) の下位 1 バイトを `icmp eq 0` で判定し、0 のとき `dec_label_pc_8f3aa6` に分岐する。
- 0 は「真」側の分岐になる。分岐先の意味 (「該当なし」など) は **未確認**。

### 3.4 native 側の確認 (補助・不完全)

- `hs_callee_disasm.py` で `0x52cf40` / `0x4181e0` を逆アセンブルしたが、VA が命令境界に合わず先頭が壊れて見えた
  (`0x52cf40` は `adc` で始まる)。`0x4e6060` は出力無し。
- したがって native 側は本 run では根拠に使わない。呼出側 IR の読みだけを §3.1〜3.3 の根拠とする。

## 4. 残作業

- `0x52cf40` / `0x4181e0` / `0x4e6060` の**分岐先**の読解 (0 のとき何をするか)、および「正しい戻り値」の確定 (受入 2 の残り)。
- `0x710030` / `0x710040` の値を FL 本体 export table から求める、または呼出元 `0x40d820` の引数を復元する (受入 1 = fold deref)。
- native 逆アセンブルの VA 境界の修正 (`hs_callee_disasm.py` は命令境界を外したまま出す)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1: fold deref (`0x40d6e0` / `[0x710040]`) の解消と `plug != 0` | Phase B が OOB のまま。`TFruityPlug*` 実体が生成されない | #1890 `[PLG-P0b-8]` |
| 受入 2 残り: 3 件の分岐先と正しい戻り値の確定 | `0x4181e0` の 0 が誤った基底になっている可能性。Phase B 到達の障害 | #1891 `[PLG-P0b-9]` |
| `hs_callee_disasm.py` の VA 境界 | native 読解の精度 | 本 PR では未対応 (REPORT のみ) |

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $HOME/artifacts/work-fw-stage1.tar.zst       # repo ルート
tar --zstd -xf $HOME/artifacts/work-liftlib.tar.zst         # repo ルート
tar --zstd -xf $HOME/artifacts/work-icall.tar.zst           # repo ルート
bash tools/plugins/framework/fw_stage2.sh                   # exit 0・smoke PASS (7 分 23 秒)
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh     # FAIL (Phase B OOB) が期待値 (2 分 38 秒)
```
