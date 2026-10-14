# 付録: icall #1606 (ICALL-34) — Fresh Air SlateCore の native 側 CRT 初期化の切り分け

> 親: #1451 (ICALL-28)。本付録は受入条件 1 (native SIGSEGV 66 関数の原因切り分け) の結果を記録する。
> CRT 初期化そのものは未実装 (下記 §4)。値不一致 9 関数 (#1632) と closure 外 wasm err 15 関数 (#1633) は子 issue のまま。

## 1. 結論

- 測定 commit: `e709df66` (`origin/main` 取り込み後)。`bash tools/icall/diff/fa_sweep.sh 8 60` = **bit 一致 41 / native crash・timeout 66 / wasm のみ err 15 / 値の不一致 9** (131 関数、70.7 s、開始時 load 0.84)。前回 `d16d7f5d` 基準と同値。
- native の 66 件 SIGSEGV は、**大半が SlateCore の api-set 遅延解決表が未初期化**であることに起因する。CFG dispatch `jmp rax` で `rax=0xae64b77e88c8000` を踏む。これは OTT で確認済みの fail-fast と同一の値 (§3)。
- ただし SlateCore の cookie・api-set 表の VA は OTT と異なり、解決機械語も同じパターンでは見つからなかった。**OTT の `crtinit` 手法 (固定 VA の enc(NULL) 事前初期化) は流用できない**。CRT 初期化の実装は未了 (§4)。
- 引数規約の誤り (`fa_cmp.py` の 4 ポインタが近接する問題) は 66 件中 1 件 (`1803de310`) にしか効かない。主因ではない (§2)。

## 2. 引数規約の検証

`fa_cmp.py` は rcx..r9 に別々の 0x400 バイトのヒープを渡す。`1803de310` は `rdx`〜`r8` の区間を 0x28 刻みで複写するため、`rdx != r8` だと領域外まで走って SIGSEGV する。

| 呼び出し | 結果 |
|---|---|
| `1803de310` distinct (現行 harness) | SIGSEGV rip=`0x1803de3a5` addr=`0x60100000` |
| `1803de310` `rdx==r8` | 正常終了 xmm0 = `0x3ff0000000000000` |
| 66 件全部を `rdx==r8` に変更 | 正常終了 **1 件のみ** |

→ 規約誤りは 1 件 (`1803de310`) の原因であり、残り 65 件は別原因。harness の入力規約を直す優先度は低い。

## 3. native クラッシュ地点 (66 件)

probe (`distinct` 規約・プロセス分離) で各関数の SIGSEGV 地点を集計した。56 件で地点を取得 (残りは出力を読めなかった)。

| 地点 | 件数 | 内容 |
|---|---|---|
| `0x1810806a0` `jmp rax` | 10 | CFG dispatch。`rax=0xae64b77e88c8000` |
| `0x7ffff72029xx` | 9 | 間接 jmp で image 外へ |
| `0x180c8b9c0`・`0x180da6e99`・他 | 残り | 単発・未切り分け |

`0x1810806a0` の `rax` は、SlateCore の `__security_cookie` (`0x18125eaa8`、file raw 値 `0x2b992ddfa232` = UCRT 既定) で未初期化の encoded slot を decode した値 `ror(0 ^ cookie, cookie & 0x3f) = 0xae64b77e88c8000` と一致する。OTT の `crtinit/REPORT.md` §2.2 と同じ機構。

`1803b3fc0` は別経路。`call 0x18102f728` の先が `.text` 内で、IAT の import ではない。その先で image 外 (`0x7ffff7...`) の間接 jmp に落ちる。

## 4. 未了と次の一手

- **未了 (CRT 初期化の実装)**: SlateCore の api-set 表の VA、解決機械語 (`ror`/`rol` by `cl` の resolver) がどれか未特定。`.text` の `ror`/`rol cl` 走査は 0 件で、OTT の `0x1801c38c8` 相当の関数を機械的に見つけられなかった。`.data` 内で cookie と同値の連続領域も 0 件。
- **次の一手**: (a) SlateCore の resolver を `0x1810806a0` の `jmp rax` 呼出元から逆に辿って特定 → (b) その表を enc(NULL) で初期化する `ott_crt_init_tables` 相当を `crt_native.c` 方式で書く → (c) `fa_sweep.sh 8 60` で native crash 件数の変化を測定。この作業は子 issue に切る (§5)。

## 5. 再現

```
bash tools/icall/fa_route_build.sh                  # wasm route
bash tools/ott/native/build.sh                      # work/libottnative.so
bash tools/icall/diff/fa_sweep.sh 8 60              # 4 区分の件数 (末尾行)
python3 tools/icall/diff/fa_cmp.py 1803de310 --n 2  # 規約誤りの再現 (distinct)
```
