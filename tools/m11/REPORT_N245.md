# M11 REPORT (#5481 / [M11-N245] / 親 #5425): sigfix40c 4 variant の survey が build 状態で揺れるかの切り分け

結論: 同じ IR (variant ごと) で、各回 `work/obj` と `boot_final3.ll` を消して clean build し survey を 2 回取ると、4 variant (only40c・ctlB・ctlC・sigzero) とも 2 回の結果が一致した (ok 135 / trap 8 / miss 797 / noproc 1 / clobber 1)。clean build 同士の再現性 (受入 1) は満たした。ただし「build 履歴 (stamp・obj キャッシュ) を残した build と clean build の一致」は測っていない。一方、同じ系統の base (`M11_XMM_ARGS=0`) は ok 873 / trap 21 / miss 47 / noproc 1 で、135 との差 (738 件) の原因は未特定。残件は #5482 (N246) に移す。

## 1. 入力と手順

- 素材: `work-m11` (`tools/m11/work/`) の `boot_final.ll` は sha256 `69c774ded8aaf717…`。ただし `ir_conditions.json` が素材に無く、`m11_build.sh` は ldfix 記録が無い IR を拒否する (`m11_build.sh` 54 行)。記録を手で作ると ldfix 適用の事実を偽ることになるため、素材 IR では build していない。
- 入力 IR: `m11_gen_ir2.sh` で再生成した `work/boot_final.ll` (490,791 行・sha256 `e48c31d2…`・`ldfix=applied` `ld108=applied` `ld115=applied` `r8b=applied` `450560=applied`)。素材 (`69c774…`) と 8,024 行の差がある。
- 生成器: `python3 m11_sigfix40c_ab.py work/boot_final.ll work/sigfix40c --pe $ANALYSIS_DIR/win64/extracted/block00031_PE.bin` (rc 0・`fixed=1`)。
- 測定 commit: `86f9a1448` (`tools/m11/m11_sigfix_repro.sh` を追加。コードを変えた最後の commit)。
- 再現: `bash tools/m11/m11_sigfix_repro.sh only40c ctlB ctlC sigzero` (PE・emsdk は `docs/REFERENCES.md` の `[WIN64]`・`[EMSDK]` 経由)。出力は `tools/m11/work/repro5481/` (gitignore)。
- 測定環境: 素材 `fl-win64`・`toolchain-emsdk`・`work-m11` を展開 (`docs/WORKFLOW.md` §11)。load average は測定中 0.8〜1.0 (`uptime`)。

## 2. 結果 (受入 1)

各行は clean build (`work/obj`・`boot_final3.ll` を削除してから `M11_XMM_ARGS=1 m11_build.sh`) の後に survey を 1 回取った値。

| variant | run | build 秒 | survey 秒 | ok | trap | miss | noproc | clobber | boot_final3.ll sha256 |
|---|---|---|---|---|---|---|---|---|---|
| only40c | 1 | 26 | 3 | 135 | 8 | 797 | 1 | 1 | 07ddf9d9… (前回の値・同一 IR) |
| only40c | 2 | 26 | 3 | 135 | 8 | 797 | 1 | 1 | 同上 |
| ctlB | 1 | 25 | 4 | 135 | 8 | 797 | 1 | 1 | f98b0862… |
| ctlB | 2 | 25 | 4 | 135 | 8 | 797 | 1 | 1 | f98b0862… |
| ctlC | 1 | 25 | 4 | 135 | 8 | 797 | 1 | 1 | fee2eb10… |
| ctlC | 2 | 26 | 3 | 135 | 8 | 797 | 1 | 1 | fee2eb10… |
| sigzero | 1 | 26 | 3 | 135 | 8 | 797 | 1 | 1 | d1f27529… |
| sigzero | 2 | 26 | 4 | 135 | 8 | 797 | 1 | 1 | d1f27529… |

- 各 variant の 2 回は unit 別の結果 (JSON) も一致 (only40c の 2 回は `md5sum` 一致 `7156c506…`)。
- variant 間の IR sha は互いに異なり、variant ごとに build が差し替えた IR を使っていることを `cmp` で確認 (`work/boot_final.xa.ll` = `work/sigfix40c/<variant>.ll`)。

## 3. 基準 (base) と差分 (受入 2 の判断)

| 設定 | run | ok | trap | miss | noproc | clobber |
|---|---|---|---|---|---|---|
| base (`M11_XMM_ARGS=0`) | 1 | 873 | 21 | 47 | 1 | 0 |
| base (`M11_XMM_ARGS=0`) | 2 | 873 | 21 | 47 | 1 | 0 |
| 全関数変換 (`M11_XMM_ARGS=1`・fixed=46) | 1 | 873 | 21 | 47 | 1 | 0 |
| 全関数変換 (`M11_XMM_ARGS=1`・fixed=46) | 2 | 873 | 21 | 47 | 1 | 0 |

- base と全関数変換は 2 回ずつ一致し、どちらも 873。
- sigfix40c の 4 variant は 135。同じ IR 系統でも、only40c の差し替えを入れた build だけが 135 に落ちる。

## 4. 落とし穴 (計測中に見つけたこと)

- `m11_build.sh` は `work/xmm_args.stamp` が `M11_XMM_ARGS` の値と合わないと `boot_final.xa.ll` を `fix_xmm_args.py` の全関数変換版で作り直す (171 行付近の `xmm_args.stamp` 判定)。差し替えた variant をそのまま `boot_final.xa.ll` に置いて build すると、variant ではなく全関数変換の IR で build される。最初に取った `873/1/47/21/0` の値は、この全関数変換の IR によるものだった (ログに `fix_xmm_args] fixed=46` が出る)。以後の値 (135) は差し替えた variant の IR で build したもの。
- 対策: `m11_sigfix_repro.sh` は build 前に `xmm_args.stamp` を `1:` に合わせ、build 後に `cmp` で `boot_final.xa.ll` が variant と一致することを確認する (不一致なら `ERROR` を出す)。ERROR は本測定では出ていない。
- only40c の IR は素材系 IR と 5,692 行違う。スタック変数の alloca 型 (`[40 x i64]` → `i64` 等) まで変わっており、`fix_xmm_args.py --only-funcs` の変換が想定より広く効いている可能性がある。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| sigfix40c 4 variant の 135 と base・全関数変換の 873 の差 (738 件) の原因 | variant の survey 数値 (REPORT_N210 との比較) を使えない | #5482 (N246) |
| 素材 IR (`69c774…`) の ir_conditions.json 欠落 (build gate で拒否) | 素材 IR では build・survey できない。再生成 IR (`e48c31…`) で測るしかない | 本 REPORT §1 (素材の記録作り直しは PM 判断) |
