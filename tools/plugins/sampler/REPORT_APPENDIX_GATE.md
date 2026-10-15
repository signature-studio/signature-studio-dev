# sampler REPORT 付録 (§6 の gate 設計・ネガティブコントロールの全文)

> 正本: `tools/plugins/sampler/REPORT.md` §6。 250 行上限のため無変更で分割移動 ([PLG-F3-14] #1774 の PR で移動)。

### gate の設計 (#506 の reviewer 指摘への対応)

- 判定は `judge.py` に切り出し、不合格が 1 件でもあれば **exit 1** (入力不正は exit 2)。 `sampler_e2e.sh` は `set -e` で判定の直後に中断し、`[sampler_e2e] OK` は全工程を通った時だけ出る。
- `declares_unimpl` も判定に含める。 許容は `targets.py` の `ALLOW_UNIMPL` と名前の許可リストで、本 PR では両方空 (#629 で `rep_stosb_memset` が消えたため)。 未実装 helper が 1 件でもあれば不合格。 -1 (計測不能)・非整数・行欠落・header のみ・空は全て不合格。
- lift 実行時は、その run が `work/batch/status.csv` に追記した行だけを判定する (過去 run の合格行で通さない)。
- 突合 (`matrix_check.py` / `ids_crosscheck.py` / `unreached_unique.py`) は期待件数と照合した件数が一致しなければ不合格 (facts が空・欠落でも vacuous に通さない)。 `unreached_unique.py` は正の対照が落ちると exit 1。
- engine の判定 = lift_rc 0 / defines>0 / pdata>0 / 行が揃う / 最終 IR の `emcc -c` rc 0 (`emcc_c_rc_after_f80`) / `missing_ref` 0。 不合格は exit 1 (NC8 で 1 列ずつ壊して確認)。

### ネガティブコントロール (`sampler_nega.sh`、exit 0、10.49 s、HEAD 53c2eb6)

| NC | 内容 | 対照 → 壊した入力 (実測) |
|---|---|---|
| NC1 | FL Keys の `final.ll` の関数 1 つの `ret` を除去 → `emcc -c` | rc 0 → **rc 1** |
| NC2 | FL Keys の閉包 ranges の末尾 1 つを落として再 lift | 落とした関数 `function_7268d0` が 1 → **0**、define 29 → 27 |
| NC3 | `judge.py shells` に合成 CSV 10 種 (emcc_c_rc=1 / lift_rc=1 / f80=3 / 許容 0 の block に未実装 1 / 許容 1 の block に未実装 2 / 未実装 -1 / 許可外の helper 名 / FPC の行欠落 / 全行欠落 / header 不正) | 対照 rc 0 → 9 種が **rc 1**、header 不正が **rc 2** |
| NC4 | e2e 本体 (`--skip-lift --judge-only`) に `emcc_c_rc=1` の行を足した status.csv を渡す | 対照 rc 0 → **rc 1**、不合格側の出力に `[sampler_e2e]` 行 0 本 (OK 行が出ない) |
| NC5 | `matrix_check.py` に壊した入力 4 種 (FPC の closure_funcs +1 / Slicex の facts 欠落 / 空 facts / FL Keys の batch emcc_c_rc=1) | 対照 rc 0 → **4 種とも rc 1** |
| NC6 | `ids_crosscheck.py` に taint 側の ID 件数を +1 (FL Keys ID 2: 1 → 2) した facts | 対照 rc 0 → **rc 1** |
| NC7 | `judge.py engines` に lift_rc=1 の行 / 末尾行欠落の engines.csv | 対照 rc 0 → **2 種とも rc 1** |

NC4 は #506 の reviewer が再現した「不合格行を追記しても exit 0」と同じ入力 (emcc_c_rc=1 の追記) で、本 PR は exit 1 になる。
