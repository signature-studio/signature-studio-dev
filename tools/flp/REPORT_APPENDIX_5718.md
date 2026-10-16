# flp #5718 (PY-5384): pred (0x12d8d30) の実行時命中と loop (0x12d94f0) の入口

親: #5717 (PY-5383) → #4921 (PY-403)。前提: #5649 (wine64 + gdb の attach 実測)。結果の参照先: PY-229 (#3659)。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| 関数 `0x12d94f0` の loop の入力述語を確定し REPORT に書く | **未達** (loop の入口は未命中。述語は未確定) | §3・§4 |
| (段 1) `pred` (0x12d8d30) の命中を確認する | 達成 (2 回の測定とも 6000 件の命中) | §2 |

## 2. 測定

- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 6.68 s)。インストール木は `tools/flp/s1_wine_probe.sh` (S1 の起動: real 2 m 09 s・GUI 継続で rc=124)。
- 道具: apt の wine64 9.0・gdb 15.1・xvfb を導入。`kernel.yama.ptrace_scope=0` (sudo) に設定 (このランナー限り)。
- VA の対応: REPORT の VA は `RVA + 0x400000` (`FLEngine_x64.dll` の PE image base は `0x400000`)。`pred` (0x12d8d30) と loop (0x12d94f0) は DLL の `.text` 内。FL64.exe の base は使わない (`tools/flp/s3_gdb_attach_probe.sh` は FL64.exe 向けのため流用せず、新規 `tools/flp/s6_pred_hit_probe.sh`)。
- 実行時 base: `FLEngine_x64.dll` は `0x7a730000` にロード (ASLR で変わる)。ブレーク先は `pred=0x7b608d30`・loop=`0x7b6094f0`。
- 測定 1 (WAIT=180 s・real 3 m 01 s): `pred` 6000 件・loop 0 件 (`timeout` で終了。gdb は件数の上限を設けていない)。
- 測定 2 (WAIT=90 s・real 1 m 31 s・呼出し元の戻り先を記録する版): `pred` 6000 件・loop 0 件 (同じく時間切れで終了)。
- 2 回とも 6000 件で止まった。止まった理由 (pred の呼出しが 6000 回で終わる・別の条件) は未確認。

## 3. pred の命中の内訳 (測定 2)

- 呼出し元の戻り先 (`ret`・実行時 VA → RVA。`pred` の VA は `RVA + 0x400000`):

| 戻り先 (実行時) | RVA | 件数 |
|---|---|---|
| `0x7b1f3699` | `0xac3699` | 1998 |
| `0x7b1f362b` | `0xac362b` | 1998 |
| `0x7b1f27c3` | `0xac27c3` | 1998 |
| その他 (`0x7b1f378c`・`0x7b1f33ef`・`0x7b1f31c7` 等) | — | 各 2 件 (計 6 件) |

- 引数 (`rcx`=G1 相当・`rdx`・`r8`・`r9`): `rcx` は 1 から増える (測定の範囲で `0x1`〜`0x3e7`)。先頭の約 2000 件は `rdx=r8=r9=1` (REPORT_PY394 の `dl=1, r8b=1, r9b=1` と一致)。残りは別の引数の組。
- 上の戻り先 3 系統の VA (`0xec3699`・`0xec362b`・`0xec27c3`) は loop 関数の起点 VA `0x12d94f0` と一致しない。関数の終端は未確認のため、loop 関数の内側かどうかは未確認。呼出し元の関数名・所属は未特定。

## 4. loop (0x12d94f0) の入口

- 測定 1・2 とも loop の入口に命中しなかった (`HIT loop` 0 件)。
- 判定: loop の入力述語は**未確定**。GUI 起動 (S1 と同じ起動) だけでは、`0x12d94f0` の loop に入る経路が通っていない。REPORT_PY394 の loop 形 `while (G1 > 1 && pred(G1)) G1--;` は静的な読みのままで、実行で確認できていない。
- 次に要るもの: loop に入るトリガ (GUI 操作・プロジェクトの読込みのどれか)。GUI 操作の自動化は本 issue の範囲外。呼出し元 (`0x12d94f0` を call する関数) を静的に特定し、その上位の経路に break を張る方が手段として早い。

## 5. 再現手順

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
sudo apt-get install -y wine64 xvfb gdb
sudo sysctl -w kernel.yama.ptrace_scope=0
WINEDEBUG=-all,+module bash tools/flp/s1_wine_probe.sh   # インストール木 $RUNNER_TEMP/fl-install
WAIT=90 bash tools/flp/s6_pred_hit_probe.sh               # pred・loop にブレーク、結果 $RUNNER_TEMP/s6_gdb_session.txt
```

## 6. 未確認

- loop (0x12d94f0) の命中: 未確認 (2 測定 計 270 s で 0 件)。
- `pred` の戻り値 al と loop の継続条件: 未確認 (loop に入っていないため)。
- 戻り先 `0xac3699`・`0xac362b`・`0xac27c3` の所属関数: 未特定。
- 呼出し元で G1 を rax で返す経路 (#5717 残作業 3): 未確認。

## 7. 静的解析: loop (0x12d94f0) の直接呼出し元 (実行なし)

- 素材: `block00031_PE.bin` (FLEngine_x64.dll・ImageBase `0x400000`) を `objdump -d --no-show-raw-insn` で逆アセンブル (raw バイトを消さないと `s7_callgraph.py` が `call` を拾えない)。wine64 / gdb はこの runner に無く、実行時確認は行っていない。
- `0x12d94f0` を直接 `call` する箇所は 2 つだけ (`tools/flp/s7_callgraph.py` で列挙):

| 呼出し箇所 (RVA) | 所属関数 (RVA) | 形 |
|---|---|---|
| `0xed2c96` | `0xed2ac0` | 配列 `(%rdi)` の要素を 1 つずつ渡す前向きループ (`0xed2c71`〜`0xed2ca7`)。直前で `0x11f2ff0` を呼ぶ |
| `0x1004db5` | `0x1004a20` | 配列 `0x70(%rbp)` を末尾 (`ebx`) から走査する逆向きループ (`0x1004da9`〜`0x1004dc0`)。直後に `0x423980` |

- `0xed2ac0` は直接の呼出し元 0 件 (`call 0xed2ac0` の逆アセンブル上の参照 0 件)。`0x1004a20` は直接 `call` が 38 件・直接の呼出し元の関数が 31 件 (`0xc307e0`・`0xd9b290`・`0xe1d090`・`0xe71980`・`0xe72cd0`・`0xe7d520`・`0xeb3a60` 等)。関数ポインタ経由の呼出しは見ていない。
- 上位側: `1004a20` の上位閉包 (呼出し元を再帰で辿った関数集合) は 1550 関数。そのうち呼出し元を持たない根は 640 個 (算出: `objdump` の `call` 辺を `s7_callgraph.py` と同じ関数境界で集計)。どの根が GUI 起動で実行されるかは未確定。
- `pred` (`0x12d8d30`) を呼ぶ関数は `0xd640a0`・`0xd66060`・`0xe7a470`・`0xea4240`・`0xebf8a0`・`0xec2740`・`0xec35f0`・`0xec3190` 等で、`ec2740`・`ec35f0`・`ec3190` から `0xea7f40`・`0xea7ae0` への直接 `call` は 0 件 (推移的な繋がりは未確認)。`pred` の呼出し元 (`ebf8a0` 等) と loop の呼出し元 (`ed2ac0`・`1004a20`) が同じ上位に乗るかは未確認。
- 結論: loop に入る経路は「直接 call の 2 関数 (`ed2ac0`・`1004a20`)」まで確定。その上位の実行時トリガは未確定 (実行で確認するまで述語は確定しない)。
- 次の一手: wine64 + gdb の環境で `ed2ac0` と `1004a20` の entry に break を張り、命中の有無と直前のスタック (戻り先) を記録する (`tools/flp/s6_pred_hit_probe.sh` の LOOP を `ed2ac0`・`1004a20` に替える)。

## 8. 実行時確認: 直接呼出し元 2 関数 (`ed2ac0`・`1004a20`) の entry

- 測定 commit: 3d27fcbb0ddcc29ed2da780ad0d0a26495885b04 (測定はこの commit の script で実施)。以後 HEAD までの `tools/flp` の差分は script のコメント・エラー処理 (`cd ... || exit`・ループ変数名) のみで、測定経路は変えていない。差分の出力は PR 本文に添付 (`git diff 3d27fcbb HEAD -- tools/flp`)。
- 測定 (`tools/flp/s8_loop_caller_probe.sh`)。素材 `fl-win64` を展開 (real 10.6 s)、`s1_wine_probe.sh` で GUI 起動 (real 2 m 12 s・rc=124 = GUI 継続)、その後 gdb attach。
- ランナー: wine64 9.0・gdb 15.1 を apt で導入、`kernel.yama.ptrace_scope=0` (sudo)。`FLEngine_x64.dll` base は `0x7a730000` (§2 と同じ)。
- ブレーク先 (実行時): `ed2ac0` = `0x7b202ac0`・`1004a20` = `0x7b334a20`。gdb は両方に挿入できた (`Breakpoint 1 at` / `Breakpoint 2 at`)。gdb の命令列は末尾が `continue` で、`detach` コマンドには到達していない (`timeout` で強制終了)。
- 測定 1 (WAIT=90 s): 両方とも 0 件 (gdb rc=124 = `timeout` による終了)。
- 測定 2 (WAIT=240 s・attach 10:14:37 〜 timeout 終了 10:18:40): 両方とも 0 件 (gdb rc=124 = `timeout` による終了)。
- 判定: GUI 起動だけでは `ed2ac0` にも `1004a20` にも入らない。よって loop `0x12d94f0` に至る経路は、GUI 起動の範囲では通っていない。`pred` (6000 件命中) は起動時に通るが、loop の上位には届かない。
- 未確認: GUI 操作 (プロジェクトの読込み・再生・ミキサ操作など) で上位が通るか。関数ポインタ経由の呼出し。
- 次に要るもの: 上位のトリガを起こす操作。GUI 操作の自動化は本 issue の範囲外のため、受入 (loop の入力述語の確定) は未達のまま。
