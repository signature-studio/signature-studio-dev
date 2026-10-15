# KH656 REPORT 付録 — #1821 (KH-29): 閉包 313 の入口 OOB の原因切り分け

本付録は `KH656_REPORT.md` §7 の続き。本文 (§7) は 250 行上限のため、結論と追跡だけを本文に残し、測定の詳細 (呼び出し鎖・VA・逆アセンブル・trap 位置) をここへ移した。

測定 commit: `a65a71ed1` (コードを変えた最後の commit。`gen_globals.py` の修正と検証スクリプト)。そこから HEAD までのコード差分は §7 の確認コマンドで 0 行 (REPORT のみ)。
環境 (作者の測定 run): nproc=4・RAM 15.9GB (空き約 14GB)・素材 `plugins-kilohearts` / `toolchain-retdec` / `toolchain-emsdk` (R2 由来の素材ディレクトリに実在を確認)。
**本 HEAD の確認 run では素材が無く (素材ディレクトリに `fl-win64` のみ)、§1〜§4 の実測値を再測定していない。** 以下の値は作者の測定 run の記録である。

## 1. 結論

| 項目 | 結果 |
|---|---|
| OOB の発生 VA | native `0x180fa76a8` (`cmp byte ptr [rax+rdi],0`・NUL 走査の初回アクセス)・wasm `kh_180fa7678` (§2.1) |
| 走査されたポインタ | `0x1813d2203` = PE `.rdata` の文字列リテラル `"invalid hash bucket count"` の生 VA |
| 原因の分類 | **lift の命令変換の誤りではない**。メモリ配置の問題: PE の絶対 VA (生 VA 定数) を wasm32 のポインタとして使い、切り捨てで線形メモリ外を指す |
| DEFECTS 類型 | **D11** (`PE VA リテラル (i64 0x18…) が wasm32 で切り捨て → OOB`)。loud (trap)。silent miscompile ではない |
| 解消 | 未。子 #3866 (KH-75) (§6) |

## 2. 呼び出し経路 (IR と実行時スタックの照合)

### 2.1 呼び出し鎖と trap 位置

`emcc -g` (同 `final.ll`・同 flags、名前付き wasm) で入口を実行したときの stack:

```
kh_180ef7fc0 → kh_18012e420 → kh_1801d3b60 → kh_180138750 → kh_180138a30 → kh_180f88394 → kh_180fa7678 (trap)
```

- `kh_180fa7678`: 409 行、store/load 174 件、`@rsp` の書換え 10 件。入口の `@rsp` は `kh_stack + 65464` (`kh_stack[65536]`)。`kh_stack_ptr()` の base は wasm 内 `0x39a0` (実測)。
- trap は `kh_180fa7678` の wasm 命令オフセット `0x1262c` (`i32.load8_u`)。
- 逆アセンブル (capstone・`HeartCore.core_64`) で VA を一意に対応付けた: `0x180fa76a8 cmp byte ptr [rax + rdi], 0` (`0x180fa76a5`〜`0x180fa76ac` の NUL 走査ループ)。`rax = [rcx]` (`0x180fa7699`) が wasm32 線形メモリ外のアドレス。lift IR (`kh_180fa7678` の `@rax + @rdi` の byte load) と命令列は一致 (lift の命令誤りは本ループでは見えない)。

### 2.2 段ごとの対応 (IR と実行時スタック)

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

`kh_180f884ac` 経由で渡される生 VA (`rcx` 定数) の 5 件:

| VA | 文字列 | `kh_180f884ac` 経由 | 確認状態 |
|---|---|---|---|
| `0x1813a493a` | "string too long" | `kh_180f884ac` の呼び出し元で `rcx` 定数として現れる | 作者の IR 観察 (`n1s.ll`)。IR は repo に未保存で、本 run では再確認不可 |
| `0x1813a9c7c` | "vector too long" | 同上 | 同上 |
| `0x1813d21e8` | 未記録 | 未記録 | **未確認**。HEAD と全履歴 (`git grep`・`git log -S`) に記録が無い。出所と経路は #3866 の作業で確認する |
| `0x1813d2203` | "invalid hash bucket count" | 経由する: §2.2 の段 1〜3 (`kh_180138a30` が `store i64 6463234563, ptr @rcx` → `kh_180f884ac` → `kh_180f88394`) | 実測 (§2.2 のプローブ・trap 時の `kh_stack`) |
| `0x1813d3b6c` | "map/set too long" | `kh_180f884ac` の呼び出し元で `rcx` 定数として現れる | 作者の IR 観察。本 run では再確認不可 |

## 4. 副次発見: gen_globals.py の負の avail (修正は有効・観測の記録は撤回)

- コード上の不具合 (本 run で確認): `lift/gen_globals.py` の `rd()` は `avail = min(n, 生データ終端 - o)` を使う。`.data` の仮想領域 (生データより後ろのゼロ埋め部分) を指す VA では `avail` が負になる。このとき (a) `data[o:o+avail]` は負の添字として解釈され、無関係なデータを返し得る (`b'0123456789'[5:5-7]` = `b'567'`)、(b) `b'\0' * (n - avail)` は `n` を超える長さになる。作者の run では `global_var_184162a70` がこの経路に当たったと記録されている (本 run では未再確認)。
- 修正: `avail = max(0, min(n, ...))`。宣言長 `n` の出力は変わらない。
- **撤回**: 旧版の本節と PR 本文は「修正前は emcc が RSS 上限 (既定 11000 MB) で kill され、`globals.c` が 681 MB になった」と書いていた。この観測の commit・設定・ログは REPORT に無く、本 run では素材が無く再現できない。さらに同じ 313 集合の修正前 build は `19fd9d73` (KH656_REPORT §7.2) と `9d491eb4` (§7.6) で成功し wasm を記録しており、kill の記録と矛盾する。よって kill・681 MB・「約 2,400 万要素」は根拠にしない。`a65a71ed1` の親 `d5681415e` での再 build は本 run では未実施。
- 記録 (作者の測定 run):

| 集合 | commit | 結果 |
|---|---|---|
| HEAD (lift 8) | `a65a71ed1` (修正前後) | wasm 54,394 B・sha `7ba79e65…7707` で同一 (変化なし) |
| 313 (修正前) | `19fd9d73` | build 成功・wasm 1,543,853 B (KH656_REPORT §7.2) |
| 313 (修正前) | `9d491eb4` | build 成功・wasm 1,543,901 B (§7.6。§7.2 と 48 B 異なる。原因は未切り分け) |
| 313 (修正後) | `a65a71ed1` | build 成功 (14.6 s・emcc peak 315 MB・`globals.c` 約 20 KB)・wasm 1,543,853 B・sha `8935ad14…287c6e`・undefined import 0・lift 313 |

## 5. 再現手順

1. 素材展開 (`tools/targets/kilohearts/`): `KH_UI_WORK=$PWD/work bash ui_eval/extract_core.sh` (sha256 検証あり・約 27 s)。
2. 閉包 4 ラウンド (license/): `python3 scripts/kh656_closure.py --rounds 4` (約 93 s)。終了時の F の `lift` は 314 件 (`1813846e0` を含む)。
3. 313 集合 (検証用の**未コミット**設定): F の `lift` から `1813846e0` を外し、`shims` に `"1813846e0": "memset"` を追加 (§7.1 と同じ構成。#1817 の方針に従いコミットしない)。
4. `python3 lic_build.py --module F` → `node kh249_check.mjs` (入口 `memory access out of bounds`) → `node scripts/kh29_stack_probe.cjs`。
5. 検証後、`lic_config.json` は HEAD に戻す (本 PR では設定を変えない)。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.rdata` の文字列リテラル等 (`lea` 由来の生 VA) を wasm 線形メモリで参照可能にする (D11 既定修正 `global_var_<VA>` 窓 + PE 実データを、生 VA ポインタの参照へ広げる) | 313 集合の入口 OOB (原因は確定、解消は未) | #3866 (KH-75) |
| `0x1813d21e8` の出所と呼び出し経路 (§3) | #3866 受入 2 の 5 件のうち 1 件が未確認 | #3866 (KH-75) |
| 閉包の収束・round 6 の `dropped_i256` 誤判定 (`1813846e0`)・313 の memset shim 登録 (F) | 閉包の自動化・313 の config | #1817 (KH-28・既存) |

## 7. コード差分の確認 (測定 commit からの差分)

```
git diff a65a71ed1 HEAD -- tools/targets/kilohearts/license ':!*KH656_REPORT*.md'
```

本 commit 時点の出力は 0 行 (コード差分なし)。REPORT 系の追記だけが HEAD までの差分。
