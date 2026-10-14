# 付録: icall #2695 (ICALL-81) — 0x180da6e60 の native harness 初期化と候補分類・0x1803dee20 の揺れ

> 親: #2674。前段: `REPORT_APPENDIX_2508.md` §4 (候補 10 件の分類) と §3.5 (0x1803dee20 の揺れ)。
> 測定 commit: `0960c8be` (コードを変えた最後の commit。§8・§10)。§1〜§9 の個別の測定は各表・各節に書いた commit の値。初版の測定は `63a82b32`。
> 既知類型との関係: 該当なし (`docs/DEFECTS.md` に対応 ID は無い)。harness 由来の**引数構造体の初期化欠落** (rcx の S・A・B を作らず SIGSEGV) であり、D12 (レジスタ比較の欠落) とは別。新類型として追記するかは PM 判断。

## 1. 結論

- **0x180da6e60 の SIGSEGV は harness 側の初期化欠落で、件数 0 の経路で解消した** (native が落ちず、native/wasm とも 8/8 一致)。件数 1 の hang は §10 で解消した (要素 0 の state 0・4・5・6・9 は戻る)。ただし一致は xmm0 の素通し (出力 = 入力) の一致で、構造体への副作用 (`A+0x19a4` の inc・cookie 検査) は比較していない。件数 >0 の state 1・2・3・7・8 は harness が未了 (SIGSEGV。§10.3)。
- **6 件の「誤り疑い」は判定できなかった** (判定 0 件。§4・§10.5)。件数 0 の経路では 6 件の store のうち No 1 (cookie store) だけが実行され、残り 5 件 (No 2・6・7・9・10) は件数 >0 の loop 内 (type 2・8 の分岐内) にあり、§10 の修正後も 0 hit のまま。miscompile とも無害とも確定しない。
- **0x1803dee20 の native 既定出力は測定ごとに異なり、未解決**。EPYC 9V45 の fix run (`a2c2c126`) では native が入力素通しで 3 条件とも 8/8 一致した。EPYC 7763 (`599f793c`)・EPYC 9V74 (`599f793c`)・初版 (`63a82b32`) では 0/8 (native `0000…`)。本 fix で HEAD (測定経路は `0960c8be` と同一) を EPYC 7763 で直接測ると 0/8 で、2 回・ASLR 無効でも同じだった (§5・§10.4)。以前の §10.4 の「7763 で 8/8」は sweep の件数からの推定で、直接の測定ではなかった (訂正)。0/8 の環境では native の出力が heap 埋め値と一致する (0x00 → `0000…`、0xcc → `cccc…`)。測定経路の差分では説明できず、原因は未検証 (§5)。
- **受入の達成状況**: 受入 1 = 部分 / 受入 2 = 未達 (判定 0 件) / 受入 3 = 未達 (native の既定出力が環境で異なり、harness 状態による説明は未確定)。受入 2・3 が未達のため PR は `Refs #2695`、issue は open のまま。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 測定環境 (§3・§5・§6 の 9V45 の値) | fix run `a2c2c126` の runner (AMD EPYC 9V45、Ubuntu 24.04、gcc 13.3.0、glibc 2.39)。並列 1 (単一プロセス)。load は `uptime` の 1 分平均で、sweep 前 0.26・sweep 後 0.84 |
| 測定環境 (§5・§6 の 9V74 の再確認) | `599f793c` で再測定した runner (AMD EPYC 9V74 80-Core、Ubuntu 24.04、gcc 13.3.0、glibc 2.39)。単一プロセス。sweep は 74.0 s (単独) |
| 測定環境 (§5・§6・§10.4 の本 fix の再測定) | AMD EPYC 7763 64-Core (本 runner・4 vCPU)、`7e23750a` (測定経路は `0960c8be` と同一)。単一プロセス。load は `uptime` の 1 分平均で、fa_cmp の前 0.88、sweep 前 0.75・sweep 後 1.39。sweep は 73.8 s (単独) |
| 素材 | `work-icall` のみ (`tools/icall/work/` へ `tar --zstd -xf` で展開、実測 18.5 s)。`FA_CORE` は `tools/icall/work/rt_freshair-core/rw.dll` (未指定だと既定で `SlateCore.core_64` を探し、素材 plugins-freshair が要る) |
| emsdk | 9V45 (`a2c2c126`) の run の素材に `toolchain-emsdk` は無かった。`[EMSDK]` (`docs/REFERENCES.md` §4) に上流 emsdk を pin 版で入れた: `git clone` の後 `./emsdk install 6.0.12 && ./emsdk activate 6.0.12` (19 s)。`emcc 6.0.12` (`tools/m1/flags.sh` の `EMCC_VERSION_PIN` と一致)。9V74 (`599f793c`) の run は `toolchain-emsdk` 素材を使った (`[EMSDK]` の emcc 6.0.12)。PR 本文の `oc_artifacts` に `toolchain-emsdk` を追加した |
| libottnative | `bash tools/ott/native/build.sh` で本 run に作り直した (`tools/ott/work/libottnative.so`。tarball には無い) |
| fixed route 生成 | `FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh`: 5.6 s (単独実行) |
| 単発 fa_cmp | n=8 で 0.2 s 前後 |
| fa_sweep | `bash tools/icall/diff/fa_sweep.sh 8 60`: 70.4 s (単独) |
| 件数 1 の確認 (`a2c2c126` 時点) | `FA_LOOP_N=1 timeout 10` で時間切れ (終了コード 124)。10 秒以内に完了せず。修正後の件数 1 は §10.3・§10.4 |

## 3. 受入 1: 0x180da6e60 の SIGSEGV 条件と harness 初期化

### 3.1 修正前の再現

初版 (`63a82b32`) の測定。修正前の `fa_cmp.py` で `FA_CORE=$PWD/tools/icall/work/rt_freshair-core/rw.dll python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8` を実行:

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
- 件数は環境変数 `FA_LOOP_N` (既定 0)。`FA_HEAP_FILL` を追加 (native の `ott_set_heap_fill`、§5 で使用)。

### 3.4 修正後の結果 (件数 0、`a2c2c126`)

| 側 | 結果 (n=8) |
|---|---|
| native | SIGSEGV なし。全 8 点で正常に戻る |
| wasm | err 0 (route は `[EMSDK]` の emcc 6.0.12 で再生成) |
| 比較 | match 8 / mismatch 0 (値は入力 xmm0 の素通し) |

負の対照: 修正前は native が SIGSEGV で落ち (出力なし)、修正後は戻って値を返す。native の出力が変わったことを確認した。EPYC 9V74 (`599f793c` の再確認) でも native 戻り・match 8 / mismatch 0 (`python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8`)。

### 3.5 経路の実行確認 (int3 トレース、件数 0、`a2c2c126`)

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

- 6 件はすべて件数 >0 の loop 内 (type 2 または type 8 の要素)。件数 1 の hang は `a2c2c126` 時点の観測 (`FA_LOOP_N=1`、10 秒以内に戻らない)。原因はゼロ初期化の要素が `0x180da41a0` (連結リスト探索) で止まることで、`node[0].next = nil` により解消した (§10.1)。残りの未実行 (No 2・6・7・9・10) は state 2・8 の分岐内。
- 要素の状態機械を正しく作るには、A の vtable (仮想 callee) と O1・O2 を受ける callee の読み先が要る。stub の callee を置けば store の実行は見えるが、callee が値を読むかは分からない (読み先が未確定のまま)。
- 件数 0 の経路で xmm0 を書く命令は確認していない。trace は候補 VA の実行の有無だけを見ており、xmm0 の書込み元は追っていない。xmm0 の素通し一致から、この関数の出力に影響する store が無いとは結論しない。

集計: 判定 0 件 (miscompile 0 / 無害 0 / 判定保留 1 / 判定できない 5)。

## 5. 受入 3: 0x1803dee20 の native 既定出力 (測定環境で異なる)

harness 状態別の結果 (n=8、先頭 1 点。wasm は全環境・全 8 点で入力値と一致した):

| 測定 | commit | 環境 | 既定 | `FA_HEAP_FILL=0xcc` | `FA_ENC_INIT=1` | 一致 (n=8) |
|---|---|---|---|---|---|---|
| fix run | `a2c2c126` | AMD EPYC 9V45 | 入力素通し (`c000c5300342457c`) | 入力素通し | 入力素通し | 8/8 (3 条件) |
| 初版 | `63a82b32` (`175ae662` の REPORT §5) | runner 未記録 | `0000000000000000` | `cccccccccccccccc` | `0000000000000000` | 0/8 (3 条件) |
| review 再現 | `599f793c` (reviewer 報告) | AMD EPYC 7763 | `0000…` | `cccc…` | `0000…` | 0/8 (3 条件) |
| 再確認 | `599f793c` (本 fix) | AMD EPYC 9V74 | `0000000000000000` | `cccccccccccccccc` | `0000000000000000` | 0/8 (3 条件) |
| 旧 §10.4 の run | `0960c8be` | AMD EPYC 7763 | 直接の測定なし | 未測定 | 未測定 | 未確定 (8/8 は推定で書いた。訂正) |
| 本 fix の再測定 (§10.4) | `7e23750a` (測定経路は `0960c8be` と同一) | AMD EPYC 7763 (本 runner) | `0000000000000000` (2 回) | `cccccccccccccccc` | 未測定 | 0/8 (既定・0xcc)。ASLR 無効 (`setarch x86_64 -R`) も 0/8 |

- 9V74 の再確認では、既定・`FA_HEAP_FILL=0xcc`・`FA_HEAP_FILL=0`・`FA_ENC_INIT=1` の各条件とも上表の 0/8 の値になった (既定は 2 回実行して一致)。
- 0/8 の 3 環境 (初版・7763・9V74) では、native の出力が heap 埋め値と一致する (0x00 → `0000…`、0xcc → `cccc…`)。値が heap から読まれたかどうかは未確認。
- 8/8 の 9V45 (`a2c2c126`) では、heap 埋め値を変えても native は入力素通しのままだった。直接の測定で入力素通しを返したのは 9V45 だけで、0/8 の環境と分かれる理由は未確認。
- 同じ 7763 で `599f793c` と本 fix の HEAD はどちらも 0/8 で、反転は無い (旧 `0960c8be` の 8/8 は推定だった)。`ptr_norm` (`3127f774`) は 0x1803dee20 の出力を変えない (native の 0 は PTR の範囲外。§10.4 の sweep 行で確認)。
- `a2c2c126..599f793c` の測定経路の差分は 0 行。したがって、差の原因が測定経路の変更である可能性は低い。測定環境に由来するかは未検証。
- **原因の候補 (未検証)**: 素材の版、`libottnative.so` のビルド条件 (`tools/ott/native/build.sh` は `gcc -O1 -g -fPIC -shared`)。ASLR は除外寄り (ASLR 無効でも 0/8)。同じ 7763 で 0/8 が続くため、CPU 機種だけでは 9V45 との差を説明できない。
- wasm 側は全環境で入力素通しで、この点は環境によらず一致する。
- **issue #2695 の観測との対応 (m2)**: 「#2674 の run では native・wasm が入力素通しで一致」は 9V45 の結果と一致し、0/8 の環境とは一致しない。#2674 の run の環境は記録が無い。heap 内容が入力値だった状態で説明できるかは確認できていない。未解決表に残す。

## 6. fa_sweep (8 60) の集計

`bash tools/icall/diff/fa_sweep.sh 8 60` (fixed route・`FA_FRAME_SLOT=1`):

| 集計 | 2508 (測定 `05194cdc`/`50112f92`) | 初版 (`63a82b32`) | fix run (`a2c2c126`・9V45) | review 再現 (`599f793c`・7763) | 再確認 (`599f793c`・9V74) | 本 fix (`7e23750a`・7763) |
|---|---|---|---|---|---|---|
| bit 一致 | 54 | 55 | 56 | 55 | 55 | 56 |
| native crash/timeout | 66 | 65 | 65 | 65 | 65 | 65 |
| wasm のみ err | 8 | 8 | 8 | 8 | 8 | 8 |
| 値の不一致 | 3 | 3 | 2 | 3 | 3 | 2 |

9V74 の再確認の実行時間は 74.0 s (単独)。9V45 の fix run は 70.4 s (単独)。本 fix は 73.8 s (単独)。

- 0x180da6e60 が crash から bit 一致へ変わったのは、全環境で同じ。
- 0x1803dee20 は、9V45 では bit 一致 (入力素通し)、7763 (`599f793c`・本 fix) と 9V74 では不一致 (native `0000…`)。
- 値の不一致の内訳 (9V74 の再確認): 0x1803dee20 (native `0000…`)、0x180da4030 (native `0000…`・wasm は入力素通し)、0x18105d9fc (native `0000000050400010`・wasm `00000000104af418`、先頭 1 点)。本 fix の不一致は 0x1803dee20 と 0x180da4030 の 2 件で、0x18105d9fc は一致する (下の行)。
- 0x180da4030 は 9V45 では native 正常・wasm 値が異なる (native の値は未記録)。0/8 の環境 (7763・9V74) では native `0000…`。環境差として併記する。
- 0x18105d9fc の不一致は `ptr_norm` (`3127f774`) より前の run にある。`a2c2c126` と `599f793c` には無く、本 fix では PTR 扱いで 8/8 一致する (`FA_PTR_NORM=0` では native `0000000050400010`・wasm `00000000104af418` の 0/8 に戻る)。ポインタの基底差の吸収である。
- 2 件とも本 issue の範囲外で、個別の調査は行っていない。

## 7. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .            # tools/icall/work/ へ (実測 18.5 s)
# toolchain-emsdk: [EMSDK] に上流 emsdk 6.0.12 を入れる (git clone で emsdk を取得し ./emsdk install 6.0.12 && ./emsdk activate 6.0.12)
bash tools/ott/native/build.sh                                     # libottnative.so
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"
FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh                 # fixed route (単独 5.6 s)
python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8                 # 期待: match 8 / mismatch 0 (件数 0)
FA_LOOP_N=0 python3 tools/icall/diff/hit_180da6e60.py 180da6e60   # 候補の実行 (件数 0): No 1・SIGSEGV 点・出口のみ 1
FA_LOOP_N=1 python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8     # 件数 1 (§10.4): match 8 / mismatch 0
FA_LOOP_N=1 FA_ELEM_STATE=0 python3 tools/icall/diff/hit_180da6e60.py 180da6e60   # §10.3 state 0: 41a0・No 1・出口・loop 先頭が各 1
python3 tools/icall/diff/fa_cmp.py 1803dee20 --n 8                 # 9V45: 8/8 (native 入力素通し) / 7763 (本 fix)・9V74: 0/8 (native 0000…)
FA_HEAP_FILL=0xcc python3 tools/icall/diff/fa_cmp.py 1803dee20 --n 8   # 9V45: 8/8 / 7763・9V74: 0/8 (native cccc…)
FA_ENC_INIT=1 python3 tools/icall/diff/fa_cmp.py 1803dee20 --n 8   # 9V45: 8/8 / 7763・9V74: 0/8 (native 0000…)
bash tools/icall/diff/fa_sweep.sh 8 60 | tail -1                   # 9V45: 56 / 65 / 8 / 2 · 7763 (本 fix): 56 / 65 / 8 / 2 · 9V74: 55 / 65 / 8 / 3
```

`xmm0_probe.py` は作っていない (`fa_cmp.py` の結果で足りたため)。issue #2695 の検証方法はこれを名指ししており、これは issue の検証方法からの逸脱である。

## 8. 測定 commit からの差分

測定 commit `0960c8be` から HEAD までの測定経路の差分は 0 行。確認 (本 fix・HEAD): `git diff 0960c8be HEAD -- tools/icall/diff tools/icall/fa_route_build.sh tools/icall/frame_slot_restore.py tools/ott/native` の出力は 0 行。`a2c2c126`→`0960c8be` の変更 (`fa_cmp.py`・`hit_180da6e60.py` で 30 行追加・5 行削除) は nil 初期化と `FA_ELEM_STATE`・41a0 候補。`ptr_norm` (`3127f774`) は `a2c2c126` には無く、`0960c8be` の時点で入っている。`tools/icall/REPORT_APPENDIX_2675.md` と `tools/icall/diff/fa_va_sha.py` は main の取り込みで入った #2675 の成果 (測定経路ではない)。

## 9. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x180da6e60 の件数 >0 経路 (type 2・8 の要素の状態機械と仮想 callee の object) の harness | 6 件の判定が 0 件。件数 1 の hang は §10.1 で解消 (`node[0].next = nil`)。残件は state 2・8 の harness (§10.6) | #2695 (本 issue に残す。analysis と harness の残件のため子 issue は起票していない) |
| No 1 (cookie store の IR 欠落) の検査が wasm で通る理由 (検査が読む値の出所) | 無害とも誤りとも未確定 | #2695 |
| 0x1803dee20: native の既定出力が測定ごとに異なる (9V45 (`a2c2c126`) だけ入力素通し、7763 (`599f793c`・本 fix)・9V74 は `0000…`)。原因は未検証 (素材・libottnative のビルド条件の候補。ASLR は除外寄り)。#2674 の観測 (入力素通し) との対応も未確定 | 受入 3 が未達。0/8 の環境で、heap 埋め値から native 出力が来る経路 (どこから読まれるか) も未確認 | #2695 |
| sweep の値の不一致 (本 fix の HEAD: 0x180da4030 と 0x1803dee20。0x1803dee20 は上の行と同じ) | 本 issue の範囲外の既存残件。0x180da4030 は native の値が環境で異なる (§6)。0x18105d9fc は `ptr_norm` で一致 (§6) | #2508 (既存の残件として引き継ぎ) |
| 受入 2 の「miscompile か無害か」を判定するための callee 読み先の確定 | 分類結果が 0 件 | #2695 |

## 10. 件数 1 の hang の原因と修正 (本 PR)

> 測定 commit: `0960c8be` (コードを変えた最後の commit)。`0960c8be` より後の commit は docs (本付録・DOC_MAP) と main の取り込みだけで、取り込みで入った `tools/m11/ldfix`・`native_ctrl.c` は測定経路の外。`git diff 0960c8be HEAD -- tools/icall/diff tools/icall/fa_route_build.sh tools/ott/native` は 0 行 (§8)。

### 10.1 結論

- 件数 1 の hang は、要素 0 の state 0 が `0x180da41a0` を呼び、その lock-free 読み出し (`0x180da41b0`・`0x180da4215`〜`0x180da421e`) が空判定に進まず spin するため。原因はゼロ初期化の節点表。先頭節点 `node[0]` (= `(B+0xbf)&~63`) の next が nil (`0x4001`) でないと、`rax≠0` で cmpxchg・再試行を繰り返す。§2 の「未確認」の推定を確認した。
- `node[0]` を nil (`0x4001`) にすると、state 0 は `0x180da42d6` で 0 を返し、要素を飛ばして戻る。件数 1 は native・wasm とも戻り、8/8 一致 (値は入力素通し)。件数 0 の既定経路は変わらず 8/8。
- state 1・2・3・7・8 は A (`rcx+0x10`) の vtable・サブオブジェクトが無いため、native で SIGSEGV する。state 4・5・6・9 は state 0 に戻って空判定で戻る。
- **受入 2 は未達のまま**。No 2・6・7・9・10 は trace で 1 hit も無い。これらは state 2 と state 8 の分岐内にあり、A の vtable (slot `+0x08`・`+0x30`) と仮想 callee の stub を作らないと実行されない。

### 10.2 harness 変更

- `tools/icall/diff/fa_cmp.py`: `NIL_NODE = 0x4001`。VA `0x180da6e60` のとき、件数 (`FA_LOOP_N`) に関係なく、native (`init_native`) と wasm (`MK_JS`) の両方で `node[0]` (`(B+0xbf)&~63`) に nil を書く。件数 0 でも書くが loop を飛ばすため結果は変わらない。
- `tools/icall/diff/hit_180da6e60.py`: 環境変数 `FA_ELEM_STATE=S` で要素 0 の state (`+0x100108`) を S にする。候補に `0x180da41a0` (state 0 の 41a0 entry) を追加。

### 10.3 測定 (件数 1・要素 0 の state を指定・単発)

修正前は、state 0・4・5・6・9 が timeout (8 s)、1・2・3・7・8 が SIGSEGV。修正後の結果:

| state | native (修正後) | trace の候補 hit |
|--:|---|---|
| 0 | 戻る (xmm0 = 入力) | 41a0 entry 1・No 1 1・出口 1・loop 先頭 1 |
| 1 | SIGSEGV `rip=0x180da7084` (`[A+8]`=0 を経由した load) | — (落ちる) |
| 2 | SIGSEGV `rip=0x180da6f27` (`[A]` vtable = 0) | — |
| 3 | SIGSEGV `rip=0x180da6fe9` (`[A]` vtable = 0) | — |
| 4 | 戻る | 41a0 entry 1・No 1 1・出口 1 |
| 5 | 戻る | 同上 |
| 6 | 戻る | 同上 |
| 7 | SIGSEGV `rip=0x180da71b8` (`[rdi+0x100128]` = 0) | — |
| 8 | SIGSEGV `rip=0x180da72fc` (`[A]` vtable = 0) | — |
| 9 | 戻る | 同上 |

No 2・6・7・9・10 は 0 hit (state 2・8 の分岐内)。

### 10.4 fa_cmp と sweep (本 fix・HEAD `7e23750a`・EPYC 7763・単発)

| 測定 | 結果 |
|---|---|
| `FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh` | OK (単独 9.9 s) |
| `FA_LOOP_N=0 python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8` | match 8 / mismatch 0 / err 0 (件数 0・不変) |
| `FA_LOOP_N=1 python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8` | match 8 / mismatch 0 / native_err 0 / wasm_err 0 (修正前は hang) |
| `python3 tools/icall/diff/fa_cmp.py 1803dee20 --n 8` (2 回とも同じ) | 0/8。1 行出力: `[{"va": "0x1803dee20", "n": 8, "match": 0, "mismatch": 8, "native_err": 0, "wasm_err": 0, "first": [[0, "0000000000000000", "c000c5300342457c"], [1, "0000000000000000", "3fd6a5368858d8d0"]]}]` |
| 同上の `FA_HEAP_FILL=0xcc` / `setarch x86_64 -R` (ASLR 無効) | どちらも 0/8 (native は `cccccccccccccccc` / `0000000000000000`) |
| `bash tools/icall/diff/fa_sweep.sh 8 60` | 73.8 s (単独)。bit 一致 56 / native crash・timeout 65 / wasm のみ err 8 / 値の不一致 2 (0x1803dee20・0x180da4030、ともに native `0000…`) |

旧 §10.4 (`0960c8be`) の sweep も同じ件数 (56/65/8/2) だったが、不一致の名前は記録していなかった。「0x1803dee20 は 8/8」はその件数からの推定で、直接の測定ではなかった (訂正)。0x18105d9fc は本 fix で 8/8 一致 (`ptr_norm` の PTR 扱い。`FA_PTR_NORM=0` で 0/8 に戻る。§6)。0x1803dee20 の揺れは §5 の未解決に残す。

### 10.5 受入の達成状況 (本 PR)

- 受入 1: 部分。件数 0 と件数 1 (state 0・4・5・6・9) は戻る。件数 >0 の state 1・2・3・7・8 は SIGSEGV のまま (object graph の stub が無い)。
- 受入 2: 未達。6 件の判定は 0 件 (No 2・6・7・9・10 は未実行、No 1 は保留のまま)。
- 受入 3: 未達。本 fix の再測定で 0x1803dee20 は 0/8 (§10.4)。旧 run の 8/8 は推定だった。原因は未検証 (§5)。

### 10.6 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| state 2・8 の harness: A の vtable (`+0x08`・`+0x30`) と仮想 callee の stub、A+8 の table (state 1)、`[rdi+0x100128]` (state 7) | 6 件の判定 0 件のまま | #2695 |
| 0x1803dee20 の native 既定出力の環境差 (§5) | 受入 3 未達 | #2695 |
