# tools/plugins/modulation/REPORT_APPENDIX.md — PLG-F5-2 (#527) f80 段の追補

> **正本**: `tools/plugins/modulation/REPORT.md`。測定値 (表・lift 秒・`emcc -c` の結果) の正本は本体 §4 だけで、本付録には再掲しない。

REPORT 本体 §4 から分割移動した経緯と実行条件 (内容は削除していない)。

## A. 変更内容

- `engine_lift.sh` に、fixcmp 後の `emcc -c` (erc2) が失敗し、かつ `final.ll` に `x86_fp80` を含む define があるときだけ、`p0c/f80_lower.py` (x86_fp80 → f64、#197 の既存 pass) を適用して `emcc -c` を再試行する段を追加した。
- 出力 `summary.csv` の最終列 `erc3` に再試行の結果を出す。f80 が無い、または erc2 が 0 の場合は `erc3 = erc2`。
- 失敗時は `first_errors.txt` に `[f80.ll]` の最初のエラー行を追記する。

## B. 19266・19268 の失敗内容

- fixcmp 後の `emcc -c` の最初のエラーは `fp_extend` (soften) で、f80 型の演算の legalize 失敗。
- f80 関数 1 本ずつ (19266 は `function_18001c320`、19268 は `function_1800218a0`) を lowering すると rc 0 になった。
- f80→f64 は bit-exact ではない (#197 で未検証)。未実装 helper (VEX 含む) は残るため、`emcc -c` の通過は stub を含む通過で、正しさは未確認。

## C. 未実装 helper と `emcc -c` の経緯

- 未実装 helper は main の m11_simd2 変更 (a824a1d / 9b5ea38、#535 / #538) で変わった。8603db1 の値は 86 (60) / 75 (57) / 64 (53) / 104 (77) (括弧は VEX)。648383c 以降は本体 §4 の値。
- `emcc -c` は 8603db1・648383c では 0/4 本だったが、main の lift 鎖変更 (`fix_icmp_ptr.py` P-E1 / `ir5_patch.py` P-F1・P-F2、`PLUG_F80_LOWER` は既定 0) を取り込んだ b9fe1d8 で 2/4 本になった。

## D. 実行条件 (35d8f3d5 の f80 段)

- 実行: `bash tools/plugins/modulation/engine_lift.sh <block> 300` を 4 本 (18977・19143・19266・19268) 順次実行。実測値は本体 §4 の表と直下の段落に記録した。
- 上記は emsdk 入りの環境で行われた。修正 run の runner には `emcc` と `/opt/emsdk` が無いため、再実行していない。
- #527 レビュー差し戻し対応 (fix run): `work/modulation/engine<N>/` (lift 出力・`ranges.txt`・`summary.csv`) が無く、`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ。4 本の `engine_name_gap.py` stdout と `ranges.txt` 件数は**取得不可**で、本付録にも REPORT にも実機値を載せない。`engine_name_gap.py` の検証は合成入力のみ (注釈 1 件・関数名 `helper_x`/`lookup` の 2 件照合、件数不一致で exit 1)。

## E. 受入条件の状態 (PR #804 本文より)

1. 4 本の `emcc -c` rc 0: 達成 (f80 段を含む)。`judge.py` 相当の exit code 化と NC は未実装。
2. E1/E2 の共有鎖修復: 対象外 (本 PR は engine 側の段のみ。共有 `lift/passes/` は未変更)。
3. VEX helper の SSE 固定判定と実装: 判定は完了 (§F。深さ 3 の直接 call 鎖では guard 無し、間接 call は未追跡)。実装は未達で、起票先は #534 (VEX helper) と #779 (VEX-256 語彙)。受入 3 の範囲変更は PM 判断待ち。
4. define 無し range (各 2 件) の原因特定: 未達 (未調査)。起票先 #527。
5. 殻との結合方式 (LoadLibrary 経路・`VSTPluginMain` 呼出) の解析: 静的解析で §G に記録 (呼出箇所の特定は未了)。
6. f80 2 関数の #197 `f80_lower.py` 適用可否: 達成 (適用可、`emcc -c` は通過。bit-exact は未検証 → #197)。

## F. VEX helper の SSE 固定判定 (受入 3)

- 結論: `sampler/vex_guard.py` の深さ 3 の直接 call 鎖 (即値の `call`/`jmp` のみ追跡) では、VEX 関数の caller に cpuid/xgetbv 関数が届かなかった (4 本)。間接 call (`call [rip+...]`・関数ポインタ・vtable) は未追跡で、動的な分岐は未実測。したがって SSE 固定の可否は未確定。
- 測定値・再現手順: `tools/plugins/modulation/REPORT.md` §4 (VEX 関数数・cpuid/xgetbv 関数数・未実装 helper 数はそこに 1 箇所だけ記載)。
- 実装は未達。追跡先は #534 (9 本の C++ DLL の VEX helper) と #779 (VEX-256 の lift 語彙拡張)。新規起票はしない (重複回避)。受入 3 の実装をこの 2 件へ移すかは PM 判断待ち。

## G. 殻と engine の結合方式 (受入 5、静的解析)

結論: 殻が `LoadLibraryExW` → `GetProcAddress` で engine を動的ロードする (推定)。測定値 (アドレス・export・件数) の正本は本体 `REPORT.md` §4.1。未解析 (殻内の `GetProcAddress` 呼出箇所) は #527 に残す。

## H. 判定 (gate) の設計と PR #506 の reviewer 指摘への対応 (REPORT.md §5 から分割移動)

#506 の指摘は (a) 判定が不合格でも exit 0 になる、(b) 判定そのものにネガティブコントロール (NC) が無い、の 2 点。本書では次のように作った。

| 検査 | 実装 | 不合格時 | NC (`modulation_nega.sh`) |
|---|---|---|---|
| 殻 8 本の合否 | `judge.py <status.csv> --blocks … --batch-dir work/batch`: lift_rc = 0 / f80 = 0 / `emcc -c` rc = 0 / declares_unimpl = 0 (-1 = 集計行なしも不合格) / define = 閉包関数数 / 全列が整数 / ヘッダ一致 / `p.final.ll` の define 数が行と一致 / `p.o` が非空 | exit 1 (入力不正は 2)。e2e は `||` で受けて `FAIL` を出し exit 1。**`OK` 行は全判定通過後の最終行にだけ出る** | NC3: 15 ケース (§6) |
| e2e スクリプト自身の終了コード | 判定を `--judge-only` で単独実行でき、 `STATUS_CSV` で入力を差し替えられる | 不合格行入りの CSV で exit 1 かつ出力に `[modulation_e2e] OK` を含まない | NC6 |
| stale な結果で合格しない | lift 前に `work/batch/<block>` を消す (`lift_ranges.sh` は `drc.ll` の存在だけを見る)。判定対象は今回の実行で `status.csv` に追記された行だけ | — | (設計) |
| `PLUGIN_MATRIX.json` との突合 | `matrix_check.py`: 閉包 6 項目 + matrix に `batch` 欄のある 5 本は 4 項目を status と比較 (計 68)。プラグイン数 ≠ 8 は exit 2 | exit 1 | NC4 |
| Dispatcher ID の別算法検算 | `ids_crosscheck.py` | exit 1 | NC5 |
| `emcc -c` ゲート / ranges が lift 範囲を決めること | — | — | NC1 / NC2 (#506 と同方式) |
| 間接 call 脱落の検出 | `icall_check.py --gate` (IR 側 = 元の間接 call + 復元 dispatch が静的 site に満たなければ FAIL。audit と別算法の不一致も FAIL) | exit 1 | NC7 |
| 閉包の境界 (測定) | `reach_check.py` (leak 自体は判定外。A ⊆ B' と前向き ⇒ 逆向きの検算が崩れたら FAIL、`--gate` は leak 1 本で exit 1) | exit 1 | NC8 |
