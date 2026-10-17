# tools/shimx REPORT 付録 — MX-57 (#4928): FH3 try/IP map → ShxSehScope 表

> 正本: 本ファイル。親の REPORT は `tools/shimx/REPORT.md` (250 行上限のため本節を分割)。
> 対象 issue: #4928 (題名 `[MX-57]`)。PR: #6069。

## 1. 結論

- `shimx_fh3_scopes` (`tools/shimx/src/seh_fh3.c`): FH3 FuncInfo の try map と IP-to-state map から `ShxSehScope` 表を作る。合成 FuncInfo の単体テスト `t_scopes` で、catch-all・typed・out_cap 超過・IP 昇順違反・magic 不一致を検査し、全て期待どおり。
- 受入 1 (SjLj 形の pad 呼出し) は**未達**。本節は FH3 → ShxSehScope 変換と単体テストまで。unwind map (kind 0/1) と pad resolver への接続は未実装。
- 実 PE の FH3 FuncInfo に対する照合は未実施 (合成入力のみ)。

## 2. 測定

- 測定 commit: `20d8eaad6` (コードを変えた最後の commit。`tools/shimx/src/seh_fh3.c` のコメント修正)。
- 環境: clang (ASan + UBSan)・`-D__EMSCRIPTEN__` を立て、`emscripten_get_now` だけ clock_gettime で置換したスタブ (`/tmp/opencode/fh3`・work 外)。`threading_primitives.h` は空。
- 手順: `clang -D__EMSCRIPTEN__ -fsanitize=address,undefined -O1 -fno-strict-aliasing -Itools/shimx/src -Itools/shimx/test test_fh3.c seh_fh3.c main.c` → 実行。
- 結果: ビルド rc=0・`[shimx-test] fh3 OK`・`ALL PASS (build=native-clang)`・exit 0。
- 所要時間・load: テスト実行 real 0.011 s (user 0.002 s・sys 0.007 s)、load average 0.34 (1 分)。ビルド時間は未計測。

## 2b. 測定 (unwind map → kind 0 scope 変換・受入 1 の一部)

- 変更: `shimx_fh3_unwind_scopes` (`tools/shimx/src/seh_fh3.c`)。IP 範囲ごとに、state から prev を辿って action を持つ state を内側から順に kind 0 scope にする。単体テスト `t_unwind_scopes` (`test/test_fh3.c`) を追加。
- 測定 commit: `573444dba` (コードと生成物を変えた最後の commit。以降は本 REPORT の更新のみ)。
- コード差分 (`git diff 573444dba HEAD -- tools/shimx/src tools/shimx/test`): 空。
- 環境: emcc 6.0.12 (emsdk, `[EMSDK]` 参照)・node 22.23.3・load average 0.95 0.53 0.25 (test.sh 実行中)。
- 結果:
  - ST: `fh3 OK`・`ALL PASS (build=st)`・exit 0 (単体の node 実行 real 178 ms)。
  - MT: `fh3 OK`・`ALL PASS (build=mt(pthreads))`・exit 0。
  - `bash test.sh --quick`: exit 0・122 s (全 7 段 PASS・MT 9 グループ・M4 互換 PASS・sig_test ALL PASS・guard 全 OK)。
- 生成物: `data/sigs.json` と `exports.txt` に `shimx_fh3_scopes`・`shimx_fh3_unwind_scopes` の 2 件を追加 (`gen_sigs.py` で再生成)。
- 未確認: `shimx_fh3_unwind_scopes` の出力を `seh_run_pads` (pad 実行) に接続した実行は無い。実 PE の FH3 FuncInfo での照合も未実施 (合成入力のみ)。

## 3. 未測定 (この run で再現できなかったもの)

- emcc (6.0.12) による ST/MT ビルドと `test.sh` の全段。この runner に emcc が無い。前 run (測定 commit `3d5753b9c`・コードは同一) では ST/MT とも `fh3 OK`・`ALL PASS` の記録がある。ただし今回の HEAD では再実行していない。
- 実 PE の FH3 FuncInfo に対する `shimx_fh3_scopes` の照合 (IP map 範囲と try 範囲の実数)。次の run の課題 (#4928)。
