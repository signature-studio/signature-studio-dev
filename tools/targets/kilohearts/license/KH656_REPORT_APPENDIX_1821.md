# KH656 REPORT 付録 — #1821 (KH-29): 閉包 313 の入口 OOB の原因切り分け

本付録は `KH656_REPORT.md` §7.6・§7.7 の続き。本文 (§7) は 250 行上限のため、結論と追跡だけを本文に残し、詳細をここへ移した。

測定 commit: `a65a71ed1` (コードを変えた最後の commit。`gen_globals.py` の修正と検証スクリプト)。そこから HEAD までのコード差分は §7 の確認コマンドで 0 行 (REPORT のみ)。
環境: nproc=4・RAM 15.9GB (空き約 14GB)・素材 `plugins-kilohearts` / `toolchain-retdec` / `toolchain-emsdk` (`$HOME/artifacts` に実在を確認)。

## 1. 結論

| 項目 | 結果 |
|---|---|
| OOB の発生 VA | native `0x180fa76a8` (`cmp byte ptr [rax+rdi],0`・strlen 型の NUL 走査の初回アクセス)・wasm `kh_180fa7678` (§7.6) |
| 走査されたポインタ | `0x1813d2203` = PE `.rdata` の文字列リテラル `"invalid hash bucket count"` の生 VA |
| 原因の分類 | **lift の命令変換の誤りではない**。メモリ配置の問題: PE の絶対 VA (生 VA 定数) を wasm32 のポインタとして使い、切り捨てで線形メモリ外を指す |
| DEFECTS 類型 | **D11** (`PE VA リテラル (i64 0x18…) が wasm32 で切り捨て → OOB`)。loud (trap)。silent miscompile ではない |
| 解消 | 未 (修正は子 issue へ・§6) |

## 2. 呼び出し経路 (IR と実行時スタックの照合)

| 段 | wasm 関数 | native 番地 | 動作 (`work/licF/n1s.ll`) |
|---|---|---|---|
| 1 | `kh_180138a30` | `0x180138c08` | `store i64 6463234563, ptr @rcx` (= `0x1813d2203`)。`call kh_180f884ac` @`0x180138c0f`。戻り番地 `0x180138c14` |
| 2 | `kh_180f884ac` | `0x180f884b0` | `rdx ← rcx`。`call kh_180f88394` @`0x180f884b8` (戻り `0x180f884bd`) |
| 3 | `kh_180f88394` | `0x180f883a2`〜`0x180f883c3` | `rax ← rdx`・`[rsp+32] ← rax`・`rcx ← rsp+32`・`call kh_180fa7678` (戻り `0x180f883c8`) |
| 4 | `kh_180fa7678` | `0x180fa7699`〜`0x180fa76a8` | `rax ← [rcx]` (= `0x1813d2203`)。`cmp byte [rax+rdi],0` で trap (wasm 命令オフセット `0x1262c`) |

実行時の証拠 (`scripts/kh29_stack_probe.cjs`・313 集合・trap 後の `kh_stack` を 8 byte 単位で走査):

```
entry run -> memory access out of bounds
kh_stack base 0x39a0
  off 64360 value 0x180f883c8   戻り (kh_180f88394 → kh_180fa7678)
  off 64400 value 0x1813d2203   kh_180f88394 の [rsp+32] = 引数 (const char*)
  off 64424 value 0x180f884bd   戻り (kh_180f884ac → kh_180f88394)
  off 64504 value 0x180138c14   戻り (kh_180138a30 → kh_180f884ac)
```

`off 64400` の値が `kh_180fa7678` の `strlen` の対象であり、表の段 3 の `[rsp+32]` と一致する。

## 3. 値の出所と D11 の機構

- lift は `lea` (rip 相対) で得た `.rdata` のアドレスを、生 VA の IR 定数 `i64 6463234563` のまま残す。module F は `raw_va: true` (関数ポインタ・vtable の値を native と byte 一致させるため生 VA を保持) であり、これが文字列ポインタにも効く。
- wasm の線形メモリには `.rdata` が VA どおりには存在しない。`global_var_<VA>` は本集合で 82 件 (memory 命令が直接参照したもの) だけで、`0x1813d2203` はその窓に無い。
- そのため `inttoptr` の先は wasm32 で `0x813d2203` に切り捨てられ、初期メモリ (96MB) の外となって `memory access out of bounds` になる。
- 同じ経路の他の生 VA (5 件の `rcx` 定数のうち、`kh_180f884ac` の呼び出し元に現れるもの): `0x1813a493a` ("string too long")・`0x1813a9c7c` ("vector too long")・`0x1813d3b6c` ("map/set too long")。いずれも `.rdata` の例外メッセージ。

## 4. 副次発見 (環境ブロッカー・本 PR で修正): `gen_globals.py` の負の `avail`

- 症状: 313 集合の `lic_build.py --module F` が emcc の RSS 上限 (既定 11000MB。`KH_EMCC_RSS_CAP_MB`) で kill された (peak 11.1GB → 上限を 13.5GB に上げても 13.5GB 超)。`work/licF/globals.c` は **681 MB**。
- 原因: `lift/gen_globals.py` の `rd()` は `avail = min(n, 生データ終端 - o)` を使う。`.data` の仮想領域 (生データより後ろのゼロ埋め部分) を指す VA では `avail` が負になり、`b'\0' * (n - avail)` が約 2,400 万バイトになる。宣言は `[64]` のまま、初期化子だけ 2,400 万要素の行が出力されていた (例: `global_var_184162a70`・`.data` の仮想領域)。
- 修正: `avail = max(0, min(n, ...))`。宣言長 `n` の出力は変わらず、超過分のゼロは従来も C で無視されていた。
- 検証 (修正後・コミット HEAD):

| 集合 | 修正前 | 修正後 |
|---|---|---|
| HEAD (lift 8・F の設定は HEAD のまま) | wasm 54,394 B・sha `7ba79e65…7707` | **同一** (54,394 B・sha `7ba79e65ec158a711646316579e6f8bc3d8c12f47c61851710a5e2077b8c7707`・入口 `unlifted callee 0x180112a30`・REPORT §3 と一致) |
| 313 (検証用の設定・§5) | 不明 (emcc が RSS 上限で kill・globals.c 681 MB) | build 成功 (**14.6 s**・emcc peak 315 MB・globals.c 約 20 KB)・wasm 1,543,853 B・sha `8935ad14…287c6e`・undefined import 0・lift 313 |

## 5. 再現手順

1. 素材展開 (`tools/targets/kilohearts/`): `KH_UI_WORK=$PWD/work bash ui_eval/extract_core.sh` (sha256 検証あり・約 27 s)。
2. 閉包 4 ラウンド (license/): `python3 scripts/kh656_closure.py --rounds 4` (約 93 s)。終了時の F の `lift` は 314 件 (`1813846e0` を含む)。
3. 313 集合 (検証用の**未コミット**設定): F の `lift` から `1813846e0` を外し、`shims` に `"1813846e0": "memset"` を追加 (§7.1 と同じ構成。#1817 の方針に従いコミットしない)。
4. `python3 lic_build.py --module F` → `node kh249_check.mjs` (入口 `memory access out of bounds`) → `node scripts/kh29_stack_probe.cjs`。
5. 検証後、`lic_config.json` は HEAD に戻す (本 PR では設定を変えない)。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.rdata` の文字列リテラル等 (`lea` 由来の生 VA) を wasm 線形メモリで参照可能にする (D11 の既定修正 `global_var_<VA>` 窓 + PE 実データを、生 VA ポインタの参照へ広げる) | 313 集合の入口 OOB (原因は確定。解消は未) | 子 issue (本 PR と同時に起票) |
| 閉包の収束・round 6 の `dropped_i256` 誤判定 (`1813846e0`) | 閉包の自動化・313 の config | #1817 (KH-28・既存) |
| 313 集合の再現に、F の `memset` shim 登録 (未コミット) が必要 | 設定差分の取り扱い | #1817 (KH-28・既存) |

## 7. コード差分の確認 (測定 commit からの差分)

```
git diff a65a71ed1 HEAD -- tools/targets/kilohearts/license ':!*KH656_REPORT*.md'
```

本 commit 時点の出力は 0 行 (コード差分なし)。REPORT 系の追記だけが HEAD までの差分。
