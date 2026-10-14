# 付録: icall #2695 (ICALL-81) — 0x180da6e60 の native harness 初期化と候補分類・0x1803dee20 の揺れ

> 親: #2674。前段: `REPORT_APPENDIX_2508.md` §4 (候補 10 件の分類) と §3.5 (0x1803dee20 の揺れ)。
> 測定 commit: `63a82b32` (`fix(icall): native harness init for 0x180da6e60 (#2695)`。コードを変えた最後の commit)。
> 既知類型との関係: 該当なし (`docs/DEFECTS.md` に対応 ID は無い)。harness 由来の**引数構造体の初期化欠落** (rcx の S・A・B を作らず SIGSEGV) であり、D12 (レジスタ比較の欠落) とは別。新類型として追記するかは PM 判断。

## 1. 結論

- **0x180da6e60 の SIGSEGV は harness 側の初期化欠落で、件数 0 の経路に限って解消した** (native が落ちず、native/wasm とも 8/8 一致)。ただし一致は xmm0 の素通し (出力 = 入力) の一致で、構造体への副作用 (`A+0x19a4` の inc・cookie 検査) は比較していない。件数 >0 の loop 本体は harness で実行できていない。
- **6 件の「誤り疑い」は判定できなかった**。件数 0 の経路では 6 件の store のうち No 1 (cookie store) だけが実行され、残り 5 件 (No 2・6・7・9・10) は件数 >0 の loop 内にあり、件数 1 では native が 10 秒以内に戻らない (ゼロ初期化の要素で hang)。miscompile とも無害とも確定しない。
- **0x1803dee20 の揺れは harness 状態で説明できるのは一部**。native の出力は heap 埋め値 (`ott_set_heap_fill`) で 0x00… から 0xcc… に変わる (native 値は harness 状態の産物)。wasm 側は入力素通し (`c000c530…` = 入力) で、その heap 由来値を返さない。wasm 側が欠く理由は未解決。
- **受入の達成状況**: 受入 1 = 部分 / 受入 2 = 未達 (判定 0 件) / 受入 3 = 部分。受入未達のため PR は `Refs #2695`、issue は open のまま。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 測定環境 | runner (Linux x86_64)。並列 1 (単一プロセス)。load は `uptime` の 1 分平均で、sweep 終了直後 0.83 (sweep 前の値は未採取) |
| 素材 | `work-icall` のみ (`tools/icall/work/` へ `tar --zstd -xf` で展開、実測 10〜16 s)。`FA_CORE` は `tools/icall/work/rt_freshair-core/rw.dll` |
| emsdk | 展開せず、runner 既存の `/opt/emsdk` (`[EMSDK]`) を `fa_route_build.sh` が source |
| fixed route 生成 | `FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh`: 10.4 s (単独実行) |
| 単発 fa_cmp | 0.15 s 前後 (n=8)。件数 0 の 0x180da6e60 は 0.14 s |
| fa_sweep | `bash tools/icall/diff/fa_sweep.sh 8 60`: 74.5 s (単独) |
| 件数 1 の確認 | `FA_LOOP_N=1 timeout 10` で出力なし (10 秒以内に完了せず)。前回の確認でも 300 s の timeout まで戻らず |

## 3. 受入 1: 0x180da6e60 の SIGSEGV 条件と harness 初期化

### 3.1 修正前の再現

`FA_CORE=$PWD/tools/icall/work/rt_freshair-core/rw.dll python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8` (修正前の `fa_cmp.py`):

```
[ott_native] SIGSEGV(11) rip=0x180da6e99 (rva 0xda6e99) addr=0x19a4 rsp=0x7fffffffbe30 rcx=0x50000010 rdx=0x50000420 rax=0
```

SIGSEGV はプロセス全体を落とす (`fa_sweep.sh` では 1 関数ずつ別プロセスで実行するため sweep 全体は止まらない)。

### 3.2 rcx の構造体の必要領域と値の出所

機械語 (`before.0.drc.dsm`、`0x180da6e60`) から読める範囲:

| オフセット | 読み方 | 必要な値 | 出所 |
|---|---|---|---|
| `S+0x10` (= A) | `mov rax,[rcx+0x10]` → `inc dword [rax+0x19a4]` (0x180da6e99、SIGSEGV 点) | A は書込み可能な領域 | harness が 0x2000 B 確保 (ゼロ) |
| `A+0x199c` | `cmp dword [rax+0x199c],0` → `jle` (件数 0 で loop を飛ばす) | 件数 | harness: 既定 0 (`FA_LOOP_N`) |
| `S+0xb8` (= B) | loop 内 `rdi = [rsi+0xb8] + rbx` (要素 stride 0x100138) | B は要素配列 | harness が `max(件数,1)*0x100138+0x200` B 確保 |
| `S+0xc8`・`S+0xa0`・`S+0xa8` | `add [rcx+0xc8],rax`・`mov [rcx+0xa8],[rcx+0xa0]` | 0 で可 | S (0x400 B) のゼロ |
| `S+0xec` | type 9 の分岐でのみ読む | 件数 0 では不要 | — |

値の出所はすべて harness の確保と件数の設定で、バイナリ (rw.dll) の内容から得た値ではない。

### 3.3 harness の実装

- `tools/icall/diff/fa_cmp.py`: `LOOP_VA = 0x180da6e60` の 1 VA だけ `init_native()` で上表の構造体を作る (`N.wr` で S+0x10・S+0xb8・A+0x199c を書く)。他の VA は従来どおり `N.alloc(0x400)` × 4 (結果を変えないため VA ごとの表で切り替え)。
- wasm 側は `MK_JS` の `mk(va)` で同じ構造を `_malloc` 領域に作る (ポインタは 8 B で格納、`setBigUint64`)。0x400 B の領域は `HEAPU8.fill(0)` でゼロ化 (native の `N.alloc` のゼロ埋めと揃える)。
- 件数は環境変数 `FA_LOOP_N` (既定 0)。`FA_HEAP_FILL` を追加 (native の `ott_set_heap_fill`、3.5 で使用)。

### 3.4 修正後の結果 (件数 0)

| 側 | 結果 (n=8) |
|---|---|
| native | SIGSEGV なし。全 8 点で正常に戻る |
| wasm | err 0 |
| 比較 | match 8 / mismatch 0 (値は入力 xmm0 の素通し) |

負の対照: 修正前は native が SIGSEGV で落ち (出力なし)、修正後は戻って値を返す。native の出力が変わったことを確認した。

### 3.5 経路の実行確認 (int3 トレース、件数 0)

`tools/icall/diff/hit_180da6e60.py` (`ott_trace_install` で候補命令に int3 を置き、実行を記録。`ott_call_cov` の単歩 coverage は窓 (IMG_BASE + 0x308000) の外の VA を記録しないため使わない):

| VA | 候補 | hit (件数 0) |
|---|---|---|
| 0x180da6e99 | SIGSEGV 点 (inc) | 1 |
| 0x180da6e8e | No 1 (cookie store) | 1 |
| 0x180da7373 | 出口 (cookie 検査 call) | 1 |
| 0x180da6ece | loop 先頭 | 0 |
| 0x180da6f4d | No 2 (type 2 の分岐内) | 0 |
| 0x180da7278・0x180da7280 | No 3・4 (type 8 の分岐内) | 0 |
| 0x180da7293・0x180da7297・0x180da729b | No 5・6・7 (type 8 の分岐内) | 0 |
| 0x180da7308・0x180da730c・0x180da7310 | No 8・9・10 (type 8 で `[rdi+0x100130]=0` の分岐内) | 0 |

件数 0 では loop に入らないため、No 1 以外の 9 件は実行されない。

## 4. 受入 2: 0x180da6e60 の「誤り疑い」6 件の分類

2508 §4.2 の No を使う。判定の根拠は 3.5 の trace (件数 0 の動的実行) と、2508 の静的情報。

| No | VA | 候補の store | 件数 0 の実行 | 分類 | 根拠 |
|--:|---|---|---|---|---|
| 1 | `0x180da6e8e` | `[rbp+0x2f] = rax` (cookie ^ rsp) | **実行 (1 hit)** | **判定できない (保留)** | 実行され、exit の cookie 検査は native で通過 (戻る)、wasm も err 0。xmm0 は不変。ただし route IR に store が無いのに wasm の検査が通る理由 (検査が読む値の出所) は未確定。無害とは断定しない |
| 2 | `0x180da6f4d` | `[rbp-0x29] = rcx` (`[rdx+8]`) | 未実行 | 判定できない | type 2 の分岐内 (件数 >0)。O1 の +8 を読む仮想 callee の object が要る |
| 6 | `0x180da7297` | `[rbp-0x19] = r15` | 未実行 | 判定できない | type 8 の分岐内 (件数 >0)。O2 の +8 の読み先は仮想 callee |
| 7 | `0x180da729b` | `[rbp-0x11] = rcx` | 未実行 | 判定できない | 同上。O2 の +16 |
| 9 | `0x180da730c` | `[rbp-1] = 0` | 未実行 | 判定できない | `[rdi+0x100130]=0` の分岐内 (件数 >0)。値 0 は確定だが、読まれるかは callee 次第 |
| 10 | `0x180da7310` | `[rbp+7] = 0` | 未実行 | 判定できない | 同上 |

補足 (2508 の判定を変えない): No 3・4 は type 8 の分岐内で、件数 0 では実行されない (「この関数内に読みは無い」の判定は分岐を通らないと確かめられない)。No 5・8 は route IR に存在する (2508 で誤検出)。

判定できない理由:

- 6 件はすべて件数 >0 の loop 内 (type 2 または type 8 の要素)。件数 1 を試すと native は 10 秒以内に戻らない (`FA_LOOP_N=1`)。ゼロ初期化の要素は `0x180da41a0` (連結リスト探索) に入り、そこで終わらないと推定 (未確認)。
- 要素の状態機械を正しく作るには、A の vtable (仮想 callee) と O1・O2 を受ける callee の読み先が要る。stub の callee を置けば store の実行は見えるが、callee が値を読むかは分からない (読み先が未確定のまま)。
- 件数 0 の経路では、この関数の出力 (xmm0) に影響する store は無い。

集計: 判定 0 件 (miscompile 0 / 無害 0 / 判定保留 1 / 判定できない 5)。

## 5. 受入 3: 0x1803dee20 の native 0 / wasm 入力の揺れ

harness 状態を変えた native の出力 (n=8、先頭 2 点。wasm は全 8 点で入力値):

| harness 状態 | native xmm0 (先頭) | wasm xmm0 (先頭) | 一致 |
|---|---|---|---|
| 既定 (heap 埋め 0) | `0000000000000000` | `c000c5300342457c` | 0/8 |
| `FA_HEAP_FILL=0xcc` | `cccccccccccccccc` | `c000c5300342457c` | 0/8 |
| `FA_ENC_INIT=1` | `0000000000000000` | `c000c5300342457c` | 0/8 |

結論:

- **説明できた部分**: native の xmm0 は heap 埋め値で変わる (0x00 → 0xcc)。つまり native の値は harness の heap 状態から来る値で、入力の関数ではない。`FA_ENC_INIT` は変えない。
- **説明できない部分 (未解決)**: wasm 側は入力を素通しする (BLK+0x88 の初期化値)。native は callee の残留 xmm0 を heap 内容から取る。wasm の lift がその書込み経路を欠くのか、経路が wasm で実行されないのかは未確定。2508 §3.5 で述べた「PR 初版の一致」(54 → 55) の揺れも、この 1 件の経路で説明できていない。

## 6. fa_sweep (8 60) の集計

`bash tools/icall/diff/fa_sweep.sh 8 60` (fixed route・`FA_FRAME_SLOT=1`、単独実行 74.5 s):

| 集計 | 2508 (測定 `05194cdc`/`50112f92`) | 本 run (`63a82b32`) |
|---|---|---|
| bit 一致 | 54 | **55** |
| native crash/timeout | 66 | **65** |
| wasm のみ err | 8 | 8 |
| 値の不一致 | 3 | 3 |

差 (1 件): 0x180da6e60 が crash から bit 一致へ変わった。他の VA の個別結果は比較していない (2508 の per-VA の sweep 出力は保存されていない)。

## 7. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .            # tools/icall/work/ へ (実測 10〜16 s)
bash tools/ott/native/build.sh                                     # libottnative.so
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"
FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh                 # fixed route (単独 10.4 s)
python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8                 # 期待: match 8 / mismatch 0 (件数 0)
FA_LOOP_N=0 python3 tools/icall/diff/hit_180da6e60.py 180da6e60   # 候補の実行 (件数 0): No 1・SIGSEGV 点・出口のみ 1
python3 tools/icall/diff/fa_cmp.py 1803dee20 --n 8                 # 期待: 0/8 (native 0000…)
FA_HEAP_FILL=0xcc python3 tools/icall/diff/fa_cmp.py 1803dee20 --n 8   # 期待: native cccc…
bash tools/icall/diff/fa_sweep.sh 8 60 | tail -1                   # 期待: bit一致 55 / 65 / 8 / 3
```

`xmm0_probe.py` は作っていない (任意。`fa_cmp.py` の結果で足りたため)。

## 8. 測定 commit からの差分

測定 commit `63a82b32` から HEAD までの `tools/icall`・`tools/ott` の差分は、本付録 (`tools/icall/REPORT_APPENDIX_2695.md`) を除いて 0 行。確認: `git diff 63a82b32 HEAD -- tools/icall tools/ott ':!tools/icall/REPORT_APPENDIX_2695.md'` の出力は空。

## 9. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x180da6e60 の件数 >0 経路 (type 2・8 の要素の状態機械と仮想 callee の object) の harness | 6 件の判定が 0 件。件数 1 は hang (`0x180da41a0` の探索の原因未確認) | #2695 (本 issue に残す。analysis と harness の残件のため子 issue は起票していない) |
| No 1 (cookie store の IR 欠落) の検査が wasm で通る理由 (検査が読む値の出所) | 無害とも誤りとも未確定 | #2695 |
| 0x1803dee20: native 0 は heap 由来の値、wasm は入力素通し。wasm 側が欠く書込み経路の特定 | 値の不一致 1 件。PR 初版の 55 との差も未説明 | #2695 (#2508 から引き継ぎ) |
| 受入 2 の「miscompile か無害か」を判定するための callee 読み先の確定 | 分類結果が 0 件 | #2695 |
