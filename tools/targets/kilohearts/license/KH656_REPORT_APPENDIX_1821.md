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
| 解消 | **#3866 で解消** (§8)。入口の OOB は消え、次の trap は未 lift callee `0x180fc61dc` |

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
| `0x1813d21e8` | "unordered_map/set too long" | `kh_18011feb0`・`kh_18012a280`・`kh_180138750` が `store i64 ptrtoint (@global_var_1813d21e8), ptr @rcx` で渡す (313 集合の IR・§8) | 実測 (#3866): `.rdata` の文字列を PE から読んで確認。窓化後は `global_var_1813d21e8` が 116 窓の一つ |
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
2. 閉包 4 ラウンド (license/): `python3 scripts/kh656_closure.py --rounds 4` (約 93 s)。終了時の F の `lift` は 314 件 (`1813846e0` を含む)。**#4272 の再測定では 4 ラウンドで収束せず `FAIL` (lift 8→42→80→166)。§8.4 参照。**
3. 313 集合 (検証用の**未コミット**設定): F の `lift` から `1813846e0` を外し、`shims` に `"1813846e0": "memset"` を追加 (§7.1 と同じ構成。#1817 の方針に従いコミットしない)。
4. `python3 lic_build.py --module F` → `node kh249_check.mjs` (入口 `memory access out of bounds`) → `node scripts/kh29_stack_probe.cjs`。
5. 検証後、`lic_config.json` は HEAD に戻す (本 PR では設定を変えない)。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 次の trap: 未 lift callee `0x180fc61dc` (入口から到達) | 313 集合の入口がこの callee で止まる | #4254 (KH-92) |
| `.rdata` の文字列以外の生 VA (vtable・関数ポインタの「値」) の窓化は行わない (`raw_va` の byte parity を保つため) | 文字列以外の生 VA を deref する経路が将来現れたら OOB になり得る | #4257 (KH-93) |
| 閉包の収束・round 6 の `dropped_i256` 誤判定 (`1813846e0`)・313 の memset shim 登録 (F) | 閉包の自動化・313 の config | #1817 (KH-28・既存) |

## 7. コード差分の確認 (測定 commit からの差分)

```
git diff 091c68915 HEAD -- tools/targets/kilohearts/license ':!*KH656_REPORT*.md'
```

測定 commit `091c68915` から HEAD `e49a091a7` までの差分: 5 ファイル・1,433 行追加 / 21 行削除 (`lic_config.json` +1,306 を含む。main 取り込みで入った)。lift-8 は HEAD で一致 (§8.1)。313 の HEAD 値は未測定 (§8.2・#4670)。

## 8. #3866 の実測 (D11 の窓化・`rdata_str`)

測定 commit: `56254af13` (コードを変えた最後の commit。`kh_lower.py` の `--rdata-str`・`lic_build.py` の配線・`lic_config.json` の `rdata_str`)。
素材 (本 run で展開): `plugins-kilohearts` (`extract_core.sh` sha256 一致)・`toolchain-emsdk`・`toolchain-retdec`。環境: nproc=4・RAM 15 GB。

**方式**: `--raw-va` の既定は素の VA リテラルを生のまま残す (vtable・関数ポインタの値を native と byte 一致させるため)。その中で、`.rdata` の NUL 終端・印字可能な文字列 (2〜63 字) を指す VA だけを窓 `@global_var_<VA>` へ置換する。窓の中身は `gen_globals.py` が PE の実バイトから埋める (`--window 64`)。文字列以外の VA は従来どおり生のまま。文字列の窓化で `raw_va` の値 store が変わるか: 変わる (文字列 VA を指す store の 84 行だけ。§8.2 で実測)。313 集合の on/off 差 +3,196 B (`56254af13` と HEAD で同じ) の section 単位の内訳は未測定 (§8.2 で値 store の変化 84 行を確認したのみ)。

| 集合 | 条件 | wasm sha256 | bytes | globals | 入口 `function_180ef7fc0` の結果 |
|---|---|---|---|---|---|
| 313 (修正前) | `rdata_str` 無し | `8935ad14…287c6e` | 1,543,853 | 82 | `memory access out of bounds` |
| 313 (修正後) | `rdata_str` 有り | `68936e80…42e1e` | 1,547,049 | 116 | 未 lift callee `0x180fc61dc` |
| 313 (ネガコン) | 修正後の build から `rdata_str` を外す | `8935ad14…287c6e` | 1,543,853 | 82 | `memory access out of bounds` (戻る) |
| lift-8 (HEAD 集合) | `rdata_str` 無し | `7ba79e65…7707` | 54,394 | 9 (#4272 実測。§8.1) | (未測定) |
| lift-8 (HEAD 集合) | `rdata_str` 有り | `3d2bc6fd…e77287` | 54,487 | 10 | (未測定) |

- 受入 1: 入口の `memory access out of bounds` は消えた。次に現れる trap は未 lift callee `0x180fc61dc` (`kh249_check.mjs` の `NG 入口実行が最初の未 lift callee 0x180112a30 に到達しない` の理由に表示される)。`0x180fc61dc` の lift は本 issue の範囲外 (#4254)。
- 受入 2: 付録 §3 の 5 件 (`0x1813a493a` "string too long"・`0x1813a9c7c` "vector too long"・`0x1813d21e8` "unordered_map/set too long"・`0x1813d2203` "invalid hash bucket count"・`0x1813d3b6c` "map/set too long") は全て `.rdata` の文字列で、全て窓化された。`0x1813d21e8` の出所は `kh_18011feb0`・`kh_18012a280`・`kh_180138750` の `store ... @rcx` (§3)。
- 受入 3 (#4272 で測定): 下表 §8.1〜§8.3。sha 変化の原因は文字列窓 (`rdata_str`) と、測定 commit 後に入った `gen_simd.py` の変更 (#3307) の 2 つで、切り分け済み。
- 受入 4: ネガコン済み (上表)。`rdata_str` を外すと入口は OOB に戻る。

**kh249_check の前提**: `product_index.json` は `KH_SRC=<素材の展開先>` で `scripts/kh249_product_index.py` を走らせて生成する (素材の所在は既定 `~/ダウンロード`)。

測定 commit から HEAD までのコード差分 (`git diff 56254af13 HEAD -- tools/targets/kilohearts/license ':!*KH656_REPORT*.md'`) は 0 行ではない (#3307 の `lift/gen_simd.py` 等。§8.3 で 313 の sha を動かすことを確認)。§8 の値は測定 commit `091c68915` 時点の値。HEAD `e71682521` (main 取り込み後の `lic_build.py`・`kh_lower.py`・`lic_config.json` の差分込み) では未測定。

### 8.1 #4272: lift-8 の sha 差分の内訳 (実測)

測定 commit: `091c68915` (測定 driver `scripts/kh656_window_measure.py` の追加 commit。コードを変えた最後の commit)。再現: `python3 scripts/kh656_window_measure.py lift8 on|off`。

driver は #4670 で LIFT8 の 8 件固定に修正済み (`lic_config.json` の F lift 1305 件は使わない)。

| 条件 | wasm bytes | sha256 | globals |
|---|---|---|---|
| lift-8 `rdata_str` 無し | 54,394 | `7ba79e65…8c7707` | 9 |
| lift-8 `rdata_str` 有り | 54,487 | `3d2bc6fd…e77287` | 10 |

HEAD `e49a091a7` で `lift8 off/on` を再測定: off 54,394 B・`7ba79e65…8c7707`・globals 9 / on 54,487 B・`3d2bc6fd…e77287`・globals 10 (driver `lift8`・`rdata_raw_allow` 付き。測定 commit `091c68915` の値と一致)。

section 単位の内訳 (#4547 実測。HEAD で `lift8 off/on` を再生成した wasm を `scripts/kh4547_section_diff.py` で比較):

| section (id) | off | on | 差 |
|---|---|---|---|
| 6 global | 80 | 86 | +6 |
| 7 export | 1,383 | 1,406 | +23 |
| 10 code | 50,025 | 50,025 | 0 |
| 11 data | 2,460 | 2,524 | +64 |
| 合計 (wasm 全体) | 54,394 | 54,487 | **+93** |

- **global (+6 B) = 窓 1 件 (+6 B) + 並べ替え (0 B)**: 窓 1 件は型 2 B + init (`i32.const 0x640`) 4 B = 6 B で、差 +6 B と一致する。並べ替えは寄与 0 B: off の global 値に `≥0x640` で +0x40 を加えて窓 (`0x640`) を外すと、on の多重集合と一致する (13 件)。on 側で値 `0x640` の位置が 7 番目なのが窓 1 件の挿入位置。
- **data (+64 B) = 窓 64 B の挿入**: data segment は `0x400`(576 B→640 B) の後ろに続く。off では `0x640` に 4 B の段があり、on ではその 4 B 段が `0x680` に移る (+0x40)。以降の `0x644`(1,859 B)→`0x684` も同じ +0x40 ずれ。差 +64 B (= 0x40) と一致。
- **export (+23 B) = 追加 1 件**: `global_var_1813d47fe` (`kind 3`・index 11) の追加。name 20 B + len 1 + kind 1 + index 1 = 23 B で一致。既存 export の index は繰り下げ (`__start_em_asm`・`__stop_em_asm` ほか)。`final.ll` の差は `@global_var_1813d47fe = external global i8` の 1 行だけ。
- **code (0 B・内容は 71 関数で変化)**: 関数 96 件の長さは全て一致。差分 3,771 B は全て命令の即値の中 (メモリ offset 3,672 B・`i32.const` 99 B)。`i32.const` の対 3,762 組を見ると、3,691 組は不変、71 組は `on = off + 0x40` (data/global の絶対アドレスが +0x40 ずれた分)、その他 0 組。opcode は変わらない。
  - export 名 `function_<VA>` で VA が引けたのは 41 関数。差分の大きい上位: `180ef7fc0` (101 B)・`18004c780` / `1800524e0` / `1800b4ac0` / `1800b4b10` (各 101 B)・`1800b4ae0` (69 B)・`180045130` (57 B)・`180054bd0` (6 B)。lift 8 件のうち `180045130`・`18004c780`・`1800524e0`・`180054bd0`・`1800b4ac0`・`1800b4ae0`・`1800b4b10`・`180ef7fc0` の 8 件は全て差分あり。
  - export されていない 30 関数は name section 無しでは VA が引けない。対応は下の #5164 の表で実測する。
- **sha 差の原因の切り分け**: 窓の追加 (data の +0x40 ずれと global の値の移動) が code の即値を動かし、それが 93 B の大半を作る。文字列 VA の置換 (raw_va の値 store 84 行) とは別経路。

**name section 付きビルドでの対応 (#5164・実測)**: `python3 scripts/kh5164_name_map.py` (`emcc -g2` で name section を出す。`-sEMIT_NAME_SECTION` は内部設定で指定できない)。on/off とも code 本体は name 無し build と一致 (関数 96)。wasm 56,278 B (off・`7d799b40…`) / 56,371 B (on・`deb15155…`)。差分 71 関数・3,771 B。全 71 行の対応表 (code_idx・name・VA・LIFT8・off_B・diff_B) は付録 `KH656_REPORT_APPENDIX_5164.md` (測定 commit `ffc8840a9`)。

| 区分 | 関数数 | 差分 B |
|---|---|---|
| VA あり: `kh_<VA>` 7 件 (name section の名前から VA を実測で引いた。VA は LIFT8 の 8 件から `180054bd0` を除いた 7 件と一致) | 7 | 2,653 |
| VA あり: `function_<VA>` (export 名) | 41 | 692 |
| VA なし: runtime・libc・生成補助 (`emscripten_builtin_*`・`dlmalloc` 系・`sbrk`・`kh_stack_ptr`・`kh_icall` 等) | 23 | 426 |
| 合計 | 71 | 3,771 |

- `sum(diff_B)` = 3,771 B と一致。`sum(off_B)` = 48,363 B。
- 旧「未対応 30 関数 (3,079 B)」は、`kh_<VA>` 7 件 (2,653 B) と VA なし 23 件 (426 B) の合計。
- LIFT8 の 8 VA のうち `180054bd0` は `kh_` 名を持たず `function_180054bd0` のみ。7 VA は `kh_` と `function_` の 2 行が同じ VA で並ぶ (別の code index・別の body。同一元関数かは未確認)。
- VA なし 23 件は lift の出力ではなく runtime・生成補助由来で、VA を持たない。

### 8.2 #4272 / #5286: 313 集合の on/off と raw_va の値 store (HEAD 再測定の結果を先頭に置く)

HEAD 再測定 (#5286・測定 commit `c8a99163e`・`lic_build` の `CORE` は `work/winpkg/HeartCore.core_64` 76,642,304 B、driver は `scripts/kh656_window_measure.py set313 off|on`):

| 条件 | HEAD wasm bytes | HEAD sha256 | HEAD globals | HEAD undefined import |
|---|---|---|---|---|
| 313 `rdata_str` 無し (off) | 1,543,976 | `422c129f…81a8e3` | 82 | 0 |
| 313 `rdata_str` 有り (on) | **HEAD 未測定** (`lic_build` が `.rdata` 生 VA 許可外 129 件で停止。`rdata 生 VA が窓化されず残った (許可外・deref され得る)`) | — | — | — |

- off は HEAD で測定し、測定 commit `091c68915` の値と一致する (受入 2 の off 側)。
- on は HEAD 未測定。許可外 129 件は `rdata_raw_allow` に足していない (R7 (a) の既定。PM 判断 #5286)。
- 下の表の on 値 (1,547,172 B) は、検査の無い `091c68915` で測った値。HEAD の値ではなく、HEAD の on 値として使わない。

以下は測定 commit `091c68915` 時点の値 (HEAD ではない)。

313 集合: F の初期 lift 8 件 + `kh656_rounds.json` の new_lift (全 4 ラウンド) − `1813846e0` (memset shim)。`kh656_closure.py` は 4 ラウンドで収束せず `FAIL` (lift 8→42→80→166 の途中)。313 はその記録から復元した (lift 件数の記録と一致)。

| 条件 (測定 commit `091c68915`) | wasm bytes | sha256 | globals |
|---|---|---|---|
| 313 `rdata_str` 無し | 1,543,976 | `422c129f…81a8e3` | 82 |
| 313 `rdata_str` 有り (検査無し・参考) | 1,547,172 | `1f9ad82f…39590f` | 116 |

- `raw_va` の値 store (`store i64 <9 桁以上の即値>`): off 2,606 行 → on 2,522 行。消えた値は 34 種類・84 行 (全て `.rdata` の文字列 VA)、追加は 0 件。文字列以外の値 store は変わらない。
- よって「文字列窓化で `raw_va` の値 store が変わらない」は**偽**。変わるのは文字列 VA を指す store の 84 行だけで、vtable・関数ポインタの値は変わらない (受入 3 の答え)。
- 313 の窓の件数は on 116 件・off 82 件 (`globals.c`)。

### 8.3 #4272: sha 変化の原因の切り分け (`gen_simd.py` の影響)

`rdata_str` 以外に、測定 commit `56254af13` から HEAD までで 313 の sha を動かす変更があった: `lift/gen_simd.py` (+12 行、SSE 語彙 `pcmpeqd`・`pcmpeqw`・`pmovmskb`・`tzcnt` の追加、#3307 KH-52 `a441a3654`)。

| 条件 | commit | wasm bytes | sha256 |
|---|---|---|---|
| 313 `rdata_str` 有り | `56254af13` (REPORT 測定 commit) | 1,547,049 | `68936e80…42e1e` (REPORT 値と一致) |
| 313 `rdata_str` 無し | `56254af13` | 1,543,853 | `8935ad14…287c6e` (REPORT 値と一致) |
| 313 `rdata_str` 有り | 測定 commit `091c68915` | 1,547,172 | `1f9ad82f…39590f` |
| 313 `rdata_str` 無し | 測定 commit `091c68915` | 1,543,976 | `422c129f…81a8e3` |
| 313 `rdata_str` 有り | 測定 commit `091c68915` の `gen_simd.py` だけ `56254af13` 版に戻す | 1,547,049 | `68936e80…42e1e` (`56254af13` と一致) |

- したがって 313 の sha 変化 (`68936e80` → `1f9ad82f`、+123 B) は `gen_simd.py` (#3307) が原因。`rdata_str` の窓化は両 commit で同じ差 (+3,196 B 相当の文字列窓込み) を持つ。
- 本 REPORT の §3 の 313 値 (`56254af13`) は再現済み。上の表の値は測定 commit `091c68915` 時点の値で、HEAD の値は未測定。
- lift-8 の `56254af13` での値は未測定。測定 commit `091c68915` の lift-8 の値は §8.1 (`gen_simd.py` の影響の有無は未確認)。

### 8.4 #4272: 検証の範囲と未解決

- 受入 1: lift-8 の off 側 globals (9 件) を記録 (§8.1)。
- 受入 2: #4547 で測定 (§8.1)。section 内訳・global の寄与 (窓 6 B + 並べ替え 0 B)・code の差の位置 (71 関数・即値のみ) を実測。export されていない 30 関数の VA 対応は #5164 で実測し、全 71 行の表を `KH656_REPORT_APPENDIX_5164.md` に置いた (§8.1)。
- 受入 3: 313 で `raw_va` の値 store の比較 (§8.2)。文字列 VA の 84 行だけが変わる。
- 受入 4: 未測定の箇所は本文に未測定と明記した。未測定の範囲: lift-8 の `56254af13` での値 (`gen_simd.py` の lift-8 への影響の有無)・sha 差の section 内訳。結論に使うのは測定 commit `091c68915` 時点の値だけ (HEAD `e71682521` での再測定は未実施)。
- `kh656_closure.py --rounds 4` は収束せず `FAIL` になる (`lic_config.json` の F ブロックを書き換えた状態で終わるため、測定後は HEAD に戻した)。収束の再確認は本 issue の範囲外。
- 閉包の 4 ラウンド不収束は #1817 (KH-28) の範囲。

## 9. #4257 の実測 (`.rdata` 生 VA の検出・許可リスト)

測定 commit: `557154c14` (コードを変えた最後の commit。module E の検査を `rdata_str` 持ちに限定 + テスト定数名)。E の「検出あり」行だけ前の commit `728eab8b9` で測った。
素材: `plugins-kilohearts` (installer zip → `windows.zip` → `work/winpkg`)・`toolchain-emsdk` ([EMSDK])。環境: nproc=4・RAM 15 GB。

| module | 条件 | 結果 | wasm bytes | wasm sha256 |
|---|---|---|---|---|
| E | merge-base `f2c86e136` (検出なし) | build 成功 | 364,770 | `0cf066d1…6fed8` |
| E | `728eab8b9` (検出あり・検査が `raw_va` のみ) | 停止: `rdata 生 VA が窓化されず残った` (許可外 8 件: `1813af278`・`1813af778`・`1813b0e98`・`1813b10d8`・`1813d26f8`・`1813d4828`・`1813d48c8`・`1813d6e18`) | — | — |
| E | 修正後 (検査を `rdata_str` 持ちに限定) | build 成功・検査は走らない | 364,770 | `0cf066d1…6fed8` (不変) |
| F (lift-8) | 修正後 | build 成功・undefined import 0 | 54,487 | `3d2bc6fd…e77287` (不変) |

- E の 8 件は `.rdata` 上の vtable・RTTI の値 (E は `raw_va` で値を生 VA のまま残す設計)。窓化対象外のため、検査は窓化を行う `--rdata-str` の module に限定した。
- テスト: `python3 lift/test_rdata_raw.py -v` → OK (3 件・skip 0)。
