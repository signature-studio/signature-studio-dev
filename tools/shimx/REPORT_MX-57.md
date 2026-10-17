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

## 3. 未測定 (この run で再現できなかったもの)

- emcc (6.0.12) による ST/MT ビルドと `test.sh` の全段。この runner に emcc が無い。前 run (測定 commit `3d5753b9c`・コードは同一) では ST/MT とも `fh3 OK`・`ALL PASS` の記録がある。ただし今回の HEAD では再実行していない。
- 実 PE の FH3 FuncInfo に対する `shimx_fh3_scopes` の照合 (IP map 範囲と try 範囲の実数)。次の run の課題 (#4928)。
