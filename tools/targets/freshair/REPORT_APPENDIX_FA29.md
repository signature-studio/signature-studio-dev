# freshair FA-29 (#2145): ca1480 の out[0] の由来 (部分達成)

FA-28 (#2097) まで未解決だった「probe 下 `out[0]=0` / probe 無し `out[0]=Z+0x2b0`」の食い違いを扱う付録。
`REPORT_APPENDIX_FA16.md` §10〜§11 の続き。判定基準 (`run_fa9.sh` (a) の期待値) は変更していない。

## 1. 結論 (実測)

- **probe 無しの `out[0]=Z+0x2b0` は、key 無しの分岐が返す `C+0x2b0` である。** `0x180ca1651: lea rax,[rcx+0x2b0]` で、`C` が node Z のときに `Z+0x2b0` になる。
- **食い違いの原因は probe が呼出結果を変えたことではない。** `FA_P9MIN` (観測なし・call-through のみ) でも、呼出 2 回目の `out[0]=Z+0x2b0` が再現する。
- full probe (`FA_PROBE9`) が `out[0]=0` しか見ていなかったのは、**2 回目の呼出で ERR になり、1 回目の呼出しか観測できなかった**ため。
  full probe は呼出前に `[C+0x318]+0xa8` を読むが、2 回目の呼出では `C=Z` の `+0x318` が poison (`a5a5…`) で、ここを読むと ERR になる (`FA_P9RD=1` で `ctl=a5a5a5a5a5a5a5a5` を確認。SIGSEGV の記録は無い)。

## 2. 呼出の内訳 (`FA_NODE1=1`, 8 epf 本, 実測)

| 観測 | 呼出数 (8 シナリオ) | out[0] の値 |
|---|---|---|
| `FA_P9MIN=1 FA_PROBE9=1 FA_NODE1=1` (call-through) | 16 (1 シナリオ 2 回) | 奇数回目 0 / 偶数回目 `Z+0x2b0` (8/8) |
| `FA_PROBE9=1 FA_NODE1=1` (full probe) | 8 (1 回目のみ、2 回目で ERR) | 全 0 (`found=0`) |
| `FA_OUT0=1 FA_NODE1=1` (probe 無し、setter 内で fault 時に [rsp+0x48] を読む) | - | `Z+0x2b0` (k=0 の Z と一致。先頭 6 本で確認) |

- 1 回目の呼出は `C` が子 `C_k` (`NODEZ k=0 C=...d50` 等)、out[0]=0 (map 経路・found=0)。
- 2 回目の呼出は `C=Z` (node 値オブジェクト)。key 無しの分岐に入り、`out[0]=C+0x2b0=Z+0x2b0`。
- probe 無しの fault (`ERR rip=180c9d741 addr=0 rcx=a5a5…`) は、この `out[0]` の `+0x10` (= `Z+0x2c0`、poison) を setter が読んだもの。`si_addr` の不一致は FA-25 (§10〜§11) の記述どおり。

## 3. Z との一致/不一致 (受入 2)

- `out[0]` は node Z の値そのものではなく、**`Z+0x2b0` (Z 領域の外)**。`Z` (node の値オブジェクト) を `out[0]` とする想定とは一致しない。
- `Z+0x2b0` は `C+0x2b0` の式そのもの。`C` が Z のときだけ Z 側に見える。よって「node Z の値が out[0] に入った」という想定は、この 2 回目の呼出では成立しない。

## 4. 測定 (測定 commit `a9a9311d`, lift2 のコードを変えた最後の commit)

- `bash tools/targets/freshair/lift2/run_fa9.sh`: load 0.11→0.26, wall 5 s, **GATE PASS**
  - (a) base: ERR=0・ca1480=72・path=map・eq=1・found=0・da6c00=0
  - (b) alt: ERR=8/8 path=static / (b-wasm) alt: wasm ERR=8/8
  - (c) pert: 差分 395 トークン・L/R 同一 40 呼出・差分 0 呼出
- `bash tools/targets/freshair/lift2/run_fa9.sh` の `run_ctrl 2 5`: **BIT-EXACT 15/15** (wall 5 s, rc=0)
- 観測 (1 回): `FA_P9MIN` 呼出 16・out0≠0 8 / full probe 呼出 8・out0≠0 0
- 測定 commit から HEAD までの lift2 差分: `git diff a9a9311d HEAD -- tools/targets/freshair/lift2` (本付録のコミットは docs のみ)

## 6. 2 回目呼出の観測 (FA-29 追補・ガード付き full probe)

- 追加: `FA_P9GUARD=1` (既定 OFF)。`ctl` (`[C+0x318]`) が poison `a5a5…` のときは `+0xa8` を読まない。既定の probe 挙動は不変。
- 実測 (`FA_PROBE9=1 FA_NODE1=1`, 8 epf 本):
  - guard 無し: FA9CA 8 行 (1 回目のみ)、ERR 8 行 (`S900..S907 |ERR`)。
  - guard 有り (`FA_P9GUARD=1`): FA9CA **16 行** (2 回目 `path=nokey` まで観測)、ERR 8 行 (同じ)。
- 2 回目 (`kc=0 k0=1 path=nokey`) の `out[0]` は 8/8 で `FA9OBJ out0_is_Z=0` (`out[0]` は node Z の値オブジェクトそのものではない)。この実行は `C` を出力していないため、`out[0]=Z+0x2b0` との一致は本追補では再確認していない (§2 の `FA_CHAIN9` 観測による)。
- ERR 8 行は guard に依らず残る (rip 等は未解析)。本追補では原因を判定しない。
- 判定基準 (`run_fa9.sh` (a)) は変更していない。既定ゲートは `FA_P9GUARD` を使わないため、従来どおり 1 回目のみを見る。

### 6.1 測定 commit と実測値 (転記)

- 測定 commit: `962de2fb` (コード変更の最後の commit)。以下の数値は実装側が `962de2fb` で実行したログからの転記。レビュー run では素材 (plugins-freshair) が無く再実行していない。
- 差分 0 の証跡: `git diff 962de2fb HEAD -- tools/targets/freshair/lift2` は、転記時点 (HEAD = `962de2fb`) で 0 行。その後の `native_ctrl.c` のコメント修正 (1 行) は下記 6.2 の commit に含まれ、この差分は 0 行ではない。
- `bash tools/targets/freshair/lift2/run_fa9.sh` (転記): rc=0, **GATE PASS**
  - (a) base: ERR=0・ca1480=72・path=map・eq=1・found=0・da6c00=0
  - (b) alt: ERR=8/8 path=static / (b-wasm) alt: wasm ERR=8/8
  - (c) pert: 差分 395 トークン・差分 0 呼出
- `run_ctrl 2 5` (転記): **BIT-EXACT 15/15**, rc=0
- wall: 単発値 (5 s と 4 s) は 1 回だけの観測のため REPORT からは外し、**未測定** (WORKFLOW §5 の n≥3 レンジ未取得)。
- load average: 開始時 0.47 のみ記録。終了時の値は記録が無いため **未記録**。

### 6.2 未再測定

- 素材 `plugins-freshair` が無いため、6.1 の GATE・run_ctrl は本セッションでは再実行していない。
- 本 commit (コメントと §1 の表現修正) を含む HEAD で `run_fa9.sh` / `run_ctrl 2 5` を再測定するのは、素材を指定した再実行が必要 (未実施)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 2 回目の `ca1480` 呼出 (`C=Z`) の呼出元と引数 `C=Z` の由来。実機の setter がこの呼出を持つかどうか | `out[0]=Z+0x2b0` が harness の配線不備か実機の挙動か未判定 (受入 1・2) | #2187 (FA-30) |
| full probe の 2 回目呼出の deref ガード (全 72 呼出で found/out0 を観測) | 既存 probe の「out0=0」は 1 回目のみ。既定ゲートの found=0 の根拠を全呼出で再確認できない | 未起票 (#2187 の観測で併せて扱う。PR 本文の未解決表に記載) |
