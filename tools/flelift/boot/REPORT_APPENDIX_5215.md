# PY-4887 (#5215) REPORT: 選択リスト G の初期化 0xe38870 の実起動確認

親: #4528 (PY-363)・上位 #3537 (PY-281)。前段: `tools/python/REPORT_PY173.md` §4・`tools/python/REPORT_PY179.md` §6 (PY-4877 の boot 観測)。既知類型との関係: 該当なし (起動中の観測のみ・lift 作業ではない)。

## 1. 結論

- **G 初期化の箇所は静的に特定: 達成。** `G` (`[[[0x15e35c8]]+0xd34]`) の初期化関数は `0xe38870` (`push rbx` で始まる)。PE 内の直接の `call 0xe38870` は `0xe7081d` の 1 箇所。その関数 `0xe70800` の直接の呼出元は `0xd89cb3` と `0x1245b00` の 2 箇所 (§2)。
- **既定経路の実起動で G 初期化が通るか: 未到達 (観測 0 件)。** 既定 boot (`FLE_IPP` 未指定・mode 3) は units 895/942 で止まり、`0xe38870`・`0xd65ff0` (isPatternSelected)・`0xe70800`・`0xd89c70`・`0x1245ac0` の入口はいずれも 0 件だった。制御 `0x12d0cc0` は 1 件発火しており、probe 機構は動いている。
- **G の意味・null 経路の実行時の値: 未決 (受入の残り)。** 初期化が通らなかったので、`isPatternSelected` の G null 経路が実起動で起きるかは、この経路では判定できない。
- **前段の読みの訂正:** 本 run の初回の静的 scan は `0xe38870` の呼出しを見落とし「PE に呼出しが無い」と報告していた。呼出しは 1 箇所ある (§2)。この訂正は本 REPORT で行い、`REPORT_PY179.md` は書き換えない。

## 2. 静的事実 (PE: `block00031_PE.bin`・`.text` raw 0x400)

| 対象 | VA | 読み |
|---|---|---|
| G 初期化 | `0xe38870` | `push rbx` で始まる関数 |
| `0xe38870` の直接の呼出元 | `0xe7081d` (`f_e70800` 内) | `call 0xe38870` (PE 上で確認) |
| `0xe70800` の直接の呼出元 | `0xd89cb3` (`f_d89c70` 内)・`0x1245b00` (`f_1245ac0` 内) | `call 0xe70800` (PE 上で確認) |

## 3. 実起動の観測 (既定経路・FLE_IPP 未指定・mode 3)

probe の場所: lift 出力 (`work/boot/lift`) に `dbg_lift.py` で入口の probe を挿入し、`build.sh plain` で link して `fle_boot.mjs --boot-only` を実行。発火は stderr のログを数える。

| 観測点 | 入口の発火数 | 備考 |
|---|---|---|
| `0xe38870` (G 初期化) | 0 | 未到達 |
| `0xd65ff0` (isPatternSelected) | 0 | 未到達 |
| `0xe70800` (G 初期化の直接の呼出元) | 0 | 未到達 |
| `0xd89c70` (`0xe70800` の呼出元 1 の関数) | 0 | 未到達 |
| `0x1245ac0` (`0xe70800` の呼出元 2 の関数) | 0 | 未到達 |
| `0x12d0cc0` (制御・PY-4877 で発火済み) | 1 | probe 機構は動作 |

boot の結果 (5 回の実行):

| 実行 | G | SEL | E70800 | D89C70 | 1245AC0 | CTL | 結果 |
|---|---|---|---|---|---|---|---|
| 制御のみ (build `e5215c`・G/SEL 入り) | 未記録 | 未記録 | —  | — | — | 1 | units 895/942・`exit` |
| E70800 入り (build `e5215d`) | 未記録 | 未記録 | 未記録 | — | — | 1 | units 895/942・`exit` |
| 呼出元 2 と 3 入り (build `e5215e`) | 未記録 | 未記録 | 未記録 | 未記録 | 未記録 | 1 | units 895/942・`exit` |
| 再現スクリプト `py5215_g_init_probe.sh` (committed HEAD・全観測点入り・1 回目) | 未記録 | 未記録 | 未記録 | 未記録 | 未記録 | 1 | units 895/942・**`oob memory access out of bounds`** |
| 同 (committed HEAD・2 回目) | 0 | 0 | 0 | 0 | 0 | 1 | units 895/942・`exit` |

「未記録」は、その実行の stderr ログを保存していないため数えられなかった行。「—」は、その build に観測点を入れていないこと。`e5215c`〜`e5215e` の build は手で作ったもので、コミットされたスクリプトでは再現できない。

終わり方は 1 回目だけ `oob` で、他は `exit`。停止点 (units 895) は同じ。`oob` と `exit` のどちらが既定かは切り分けていない。
判定 (未到達) の全観測点の記録が揃っているのは committed HEAD の 2 回目だけ (全 0 件)。他の行は CTL の発火数 (全行 1) しか記録していないため、「全 5 回で同じ」とは言えない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `G` = `[[[0x15e35c8]]+0xd34]` の意味と、初期化の実行時の値 | isPatternSelected の G null 経路が実起動で起きるかの判定 | #5215 の残り (受入の未達部分) |
| 既定 boot が units 895 で止まり、G 初期化の呼出元へ届かない原因 | 起動中に G 初期化へ届く経路が無いのか、途中で止まっているだけかが分からない | `tools/flelift/boot/REPORT.md` の既存の停止点の記録 (#672・#3770 系) |
| 停止の終わり方が `exit` と `oob` で揺れる | 同じ units 895 でも終了の理由が違う | 本 PR の範囲外 (既定 boot の既存の挙動) |
| FLE_IPP=1 (shim 有) 経路での G 初期化 | 既定経路は未到達。shim 経路は units 209 で止まる (REPORT.md §6) | 既存の測定 (REPORT.md) |

## 5. 再現

```
FL_WIN64_DIR=<fl-win64 展開先> bash tools/flelift/boot/fle6_measure.sh   # work/boot/lift を作る (先に実行する)
FL_WIN64_DIR=<fl-win64 展開先> SS_EMSDK_ENV=<emsdk_env.sh> bash tools/flelift/boot/py5215_g_init_probe.sh
# 期待: [py5215] 観測 (発火数): G=0 SEL=0 E70800=0 CTL=1 (D89C70・1245AC0 も 0)
```

素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` の `*block00031_PE.bin` を `tar --zstd -xf` で展開して使った。emsdk は `docs/REFERENCES.md` の `[EMSDK]` (本 run の runner 既定位置)。

## 6. 検証

測定 commit: `242418d70` (probe 追加 = `tools/flelift/boot/py5215_g_init_probe.sh` の追加)。`9dbad80b1` は文書のみ (`REPORT_APPENDIX_5215.md` の emsdk 参照 1 行の修正)。レビュー対応の commit (`8762fe294`) は文書の修正と、`py5215_g_init_probe.sh` の挿入数検査 (挿入数が 6 でなければ exit 3) の追加。検査は計測の観測値を変えない (観測点は同じ・失敗時に止まるだけ)。ただし測定後のコード変更なので、差分を下に示す。
`git diff 242418d70 HEAD -- tools/flelift` の出力: `tools/flelift/boot/py5215_g_init_probe.sh` (+3 −1 行: 挿入数 `INS` の検査追加・`echo` の変数化)・`REPORT_APPENDIX_5215.md` (文書)。

| 項目 | 実測 |
|---|---|
| `fle6_measure.sh` (`FLE_BOOT_RUNS=default`) | rc 0・lift 81 s・clang plain 98 s・boot default 9 s・units 895/942 (`REPORT.md` §0 行 15 と §13 の units 895 と一致) |
| 静的 PE 解析 (`0xe38870` の呼出元) | 1 箇所 (`0xe7081d`)・その関数の呼出元 2 箇所 (§2) |
| `py5215_g_init_probe.sh` (committed HEAD・2 回目) | スクリプトの終了コード 0 は boot の成否を示さない (`node ... \|\| true` で常に 0)。観測 CTL=1 G=0 SEL=0 E70800=0 D89C70=0 1245AC0=0・実行 1 m 44.3 s (real)・load は実行前 2.43 (fle6 の boot の値) |
