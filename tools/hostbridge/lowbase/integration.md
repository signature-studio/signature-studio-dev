# integration.md — lowbase を tools/liftlib / tools/icall / hostbridge に取り込むための統合メモ

対象読者: liftlib 統合担当、H2 (OTT closure→VSTPluginMain)・H4 (Wrapper lift)・H7 (shell/core) 担当。
本ディレクトリ外のファイルは編集していない。以下は「どこをどう変えれば lowbase が正式経路になるか」の差分指示。

## A. tools/liftlib

liftlib は既に `passes/remap.shift_va(text, base, newbase)` と pipeline の `shift: {base, newbase}` を持つ。lowbase 化に必要なのは **newbase を 0x30000000 以外にする** ことと、下記の固定値の除去。

| 箇所 | 現状 | 変更 |
|---|---|---|
| `liftlib/passes/dataimage.py:37` | `if 0x400000 <= nt < 0x180000000:` (補正後ポインタの妥当域フィルタ) | **`LB_BASE < 0x400000` で DIR64 補正が黙って落ちる** (nt=0x10000+RVA<0x400000)。条件を `img.base <= v < img.base + SizeOfImage` (元値側の image 範囲判定, `lb_data_gen.py` と同じ) に変更 |
| `liftlib/passes/remap.py shift_va` | `@global_var_(18…)` と `i64 (0x1…\|9-11 桁)` を `maxv=0x1803FFFFF` で shift | OK (newbase 任意)。`maxv` は `base + SizeOfImage` から導出するのが安全 (OTT: 0x308000 で収まる) |
| `liftlib/recipes/ott.py:137-140` | `-sGLOBAL_BASE=268435456`、`--initial-memory=0x36000000`、`--max-memory=0x36000000`、`-sENVIRONMENT=node` | `lb_layout.layout(base, image_size, arena_size, init_mib, max_mib)` の値を使う。`-Wl,--initial-memory` だと emscripten の `initial-heap` 既定 16 MiB が加算されて "initial memory too small" になるので **`-sINITIAL_MEMORY/-sMAXIMUM_MEMORY`** を使う。Web 実行なら `-sENVIRONMENT=node,web,worker` |
| `liftlib/recipes/ott/ir7_argpass_fixed.py:44` | `SHIFT_BASE = 0x30000000` (CLI に `--shift` あり) | pipeline から `--shift <newbase>` を渡す |
| `liftlib/recipes/ott/ir9_bootstraps.py:326` | `v - 0x180000000 + 0x30000000` | `newbase` を引数化 |
| `liftlib/recipes/ott/m6_full_extract.py:121,141` | `BASE, NEWBASE, MAXV = 0x180000000, 0x30000000, 0x1803FFFFF` (2 箇所) | 同上 |
| `liftlib/recipes/ott/{e2e_check,e2e_trap10,m10_coefdump,ott_outhash}.mjs` | `OBJ=0x30310000`, `lin(va)=0x30000000+…` | `LB_BASE`/`LB_ARENA` を env で受ける (lowbase の `x64c/diff/api.mjs` が実装例) |
| C ランタイム (m6_rt.c `M6base`, m8_rt.c `M8BASE`+上限 `0x36000000ull`, m6_stubs_hand.c, m10_boot.c `MSCR=0x35e00000`) | 固定値 | `#ifndef LB_IMG_BASE` 付きマクロ化し `-DLB_IMG_BASE=…`。`MSCR` は静的配列 (lowbase の lb_reloc.py が行う置換と同じ) |

**最短経路**: 既存 chain をそのまま走らせた後で `lowbase/retdec/lb_reloc.py ll|c` を最終段に挟む方式は即使える (リテラル 582 名 + 37 直値 + C 12 箇所を監査 JSON で全数確認済み)。ただし「0x30000000 系に shift 済み」前提の近道なので、liftlib の recipe には上表の引数化を入れて **最初から newbase で作る** のが正式解。

### data 敷設
`x64c/lb_data_gen.py` は liftlib `dataimage.gen_data_c` と同機能 (BASE 引数・DIR64 補正) で、`--m6` モードは `m6_data.c` と **バイト同一** (0x30000000 指定で検証)。liftlib 側にはこの 2 モード (`m6_data_install` 名 / jump-table 窓を含む `ott_data_install`) を統合すればよい。

### レイアウト
`lowbase/lb_layout.py` を liftlib に取り込み、**全 recipe が `LB_*` を参照**する形にする: `0..LB_BASE` 空き → image → ARENA → GLOBAL_BASE。assert: `LB_BASE ≥ 0x10000` かつ 64 KiB 境界。

## B. tools/icall

icall (間接 call 復元) は IR 内の関数ポインタ表を `function_<VA>` 名で解決する。lowbase 化の影響:
- 関数名は**元 VA** のまま (image 位置と無関係) → icall_rewrite の名前解決は無変更。
- 関数ポインタ値 (vtable 内, 即値) は `newbase+RVA` になる。`icall_rewrite.py` が VA 値から target 関数を引く箇所では **`va_orig = v - newbase + 0x180000000`** への逆変換テーブルを 1 箇所持たせる (x64c の `ott_dispatch` `case` は shift 後 VA で生成済み = 同じ規約)。
- 同一 wasm に複数 DLL を static link する場合は `lb_x64c.py --prefix` / `lb_reloc.py --prefix` で `function_` と `global_var_` を `P_` 接頭 (識別子単位; EXPORTED_FUNCTIONS は `lb_reloc.py exports`)。icall の dispatch 関数 (`P_dispatch`) も接頭が必要。runtime ヘルパ (`__asm_*`, `m6_*`) は DLL 非依存なので共有でよい。

## C. hostbridge (H2 / H4 / H7)

- **module 契約は不変**: `hb_plugin_init / hb_scratch / VSTPluginMain / hb_icall` と import `hb_host_call`。lowbase は `hb_scratch` を静的配列 (Balance) か ARENA (OTT surrogate) で返す。ARENA を使う場合 `plugin_ott_entry.c` の `HB_ARENA` を `LB_ARENA_ADDR` にする (lowbase `build_m10_lb.sh` が sed で実施; poc 側を恒久修正する場合は `#ifndef LB_ARENA_ADDR` 付きマクロ化)。
- **H2 で x64c 版を VSTPluginMain まで拡張する時**: `ott_glue.c` の `ott_run(va,…)` を `hb_icall` へ接続し、surrogate の `function_xxx(...)` 呼出を `ott_run(LB_BASE+rva, …)` に置換。ARENA は obj/audio buffer 用に `lb_layout` の `LB_ARENA..+arena_size` を使う。
- **H7 (Kilohearts HeartCore 76.6 MB / Fresh Air SlateCore 36 MB)**: SizeOfImage が 64 MiB 級になる DLL は `LB_MAX_MIB` を image 規模から決める (`lb_layout --max-mib`)。initial は image+arena+static+stack の合計 (`--init-mib`, link 時に不足なら wasm-ld が必要バイト数を出す) で最小化し、heap は `ALLOW_MEMORY_GROWTH`。
- **Memory 個数上限 (CAB-124)**: lowbase は commit を下げるが Memory 個数 (Chrome 154 で計 123 個で OOM) は変えない。個数が足りない場合の同居方式 = `x64c/build_x64c_coresident.sh` (base 割当表 + prefix; 2 DLL / 24 MiB で実証)。CPU 状態 (`R/X/flags`) は同居 module 間で共有なので**逐次実行**が前提。並行実行するなら CPU 状態を module 毎の構造体に分離する (x64c の `R[]`→`cpu->R[]` 化, 機械的)。
- **node 以外の環境**: `poc/hb_bridge.mjs` は `Buffer.from(…, 'latin1')` を使用 (2 箇所)。Worker では `chrome_worker.mjs` のように最小 polyfill (`Uint8Array.from(s, c=>c.charCodeAt(0))`) が必要 → bridge 側で `TextEncoder`/手動変換へ置換が望ましい。emscripten glue は `-sENVIRONMENT=node,web,worker` で Worker 内 `new Function(glueText)` ロード可 (`locateFile` は worker の URL 基準)。

## D. m11 (FLEngine) への示唆 (未実施・数値は audit_va.py の実測)

- FLEngine: ImageBase 0x400000 / SizeOfImage 0x18c0000 (24.75 MiB)。m11 は LVA=RVA (base 0) + GLOBAL_BASE 0x10000000 で initial 288 MiB / max 1.8 GiB。
- DIR64 reloc 278,531 件中 **55,929 件 (20%) の指す先が image 先頭 64 KiB** → LVA=RVA だと値 <0x10000 になり shimx の整数判定 (`MAKEINTRESOURCE`/序数 `GetProcAddress`/`CharUpper(単一文字)`) と衝突しうる。**LVA=RVA+0x10000** (lowbase の `LB_BASE=0x10000`) にすれば全 guest ポインタが ≥0x10000。
- 影響範囲: `m11_image_gen.py`/`m11_data_gen.py` の `-0x400000` 補正 (→ `-0x400000+LB_BASE`)、IR の VA→LVA 変換 pass、`m11_bounds.py` の境界値。GLOBAL_BASE 0x10000000 は image (0x18c0000+0x10000) の後ろにあるため変更不要。initial は image が支配的 (≥ 25 MiB) なので、削減余地は GLOBAL_BASE 以前の空き領域 (256 MiB → image 直後) 分のみ (推定; m11 未実施)。
- `audit_va.py` を FLEngine に実行すると IAT 738 スロットが image 範囲値を持つ (Delphi の bound/thunk の可能性)。m11 の import 解決 (`m11_genstubs.py`) がこれを参照するかを要確認。

## E. 追加すべき検査 (CI)
1. `audit_va.py <dll> <LB_BASE>` — DIR64 先 image 外 0 / IAT に VA 0 / base≥64KiB。
2. 二つ以上の base で同一 scenario matrix が native と bit 一致 (x64c: 0x10000 と 0x1230000)。base 依存バグ (固定アドレス残存) の検出に有効。
3. image のみ低位化した構成との出力差 0 (RetDec chain: `lowbase_e2e.sh` [3b]) — junk が address 依存で比較が崩れる lift 系統でも relocation の正しさだけ切り出せる。
4. wasm64 は `tools/runtime/bench/build_ott_variants.sh` を参照 (本チケットでは雛形を作らない)。
