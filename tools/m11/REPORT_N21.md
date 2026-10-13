# REPORT — #572 [M11-N21]: m11_data_gen.py の DIR64 補正境界 (`lo <= r < lo+len-8`) = off-by-one、確定・修正

**結論**: off-by-one と確定し `<=` に修正 (`m11_data_gen.py`)。FL 本体 PE の DIR64 278,531 件のうち境界で落ちるのは **1 件** (`.data` 末尾 RVA `0x11e5000`, 値 `0x425f00`)。修正後は補正漏れ 0。修正で units_run / survey は回帰しない (下記, 実行時の挙動は変わらず)。
`m11_image_gen.py` / `lb_check.py` (E2E の実イメージ側) は元から `r + 8 <= top` で正しく、この slot は補正済 (LVA `0x25f00`)。`m11_data.c` (`m11_data_install()` が `.data` 上書き) だけが未補正だった。同条件は m6 / liftlib にも複製されている (`tools/m6/m6_data_gen.py:42` / `tools/liftlib/liftlib/passes/dataimage.py:35`, 本 PR では未変更 → 未解決)。

## 11-1. 全数照合 (`m11_reloc_audit.py`; PE=block00031_PE.bin, LB=0; 結果 `results/n21/audit_{before,after}_lb0.json`)
| 区間 | lo | len | DIR64 | 旧条件 `<` の選択 | 新条件 `<=` の選択 | 実出力の補正 (旧→修正後) | 補正漏れ (旧→修正後) |
|---|---|---|---|---|---|---|---|
| .data | 0xfa5000 | 2,359,304 (末尾 slot = RVA 0x11e5000) | 10,284 | 10,283 | 10,284 | 10,283 → 10,284 | 1 → 0 |
| .rdata | 0x1579000 | 69 | 0 | 0 | 0 | 0 | 0 |
| 補正対象外 (.text 268,133 / .didata 114) | | | 268,247 | | | | |
区間境界の内訳: `.data` 末尾 16B 内の DIR64 は `0x11e4ff8` (補正される) と `0x11e5000` (旧条件のみ落ちる) の 2 件。先頭 16B 内は 0 件。`.rdata` は末尾 slot が 69B 区間に 8B 整列で収まらず該当なし。値条件 (`IMG < v < IMG+0x1ac0000`) は 10,284 件全て満たす。旧実出力は式 `<` と、新実出力は式 `<=` と、それぞれ全 slot で一致 (矛盾 0 件)。

## 11-2. 落ちる slot の実行時参照 (静的調査 `m11_reloc_xref.py`, 実行時 `m11_slot_probe.mjs`; 結果 `results/n21/xref_slot_0x11e5000.json`, `slot_probe_*.json`)
- 静的 (**確定**: 機械語と表から直接読めたもの): slot の値 `0x425f00` = `.text` RVA `0x25f00` の **関数ではなくデータ** (`.pdata` 関数開始でない。内容は `{0x15ec298, 0xffb5}` 形 16B の繰返し = `TResStringRec` 風)。slot は `.text` 内静的表 (RVA `0x2d3b8`〜, 24B×26 レコード `{dest, src, type}`) のレコード #1 (RVA `0x2d3d0`) の **src 欄が指す変数** (`src` = slot のアドレス `0x11e5000`)。表を走査するのは `0x4123c0` (type 2 = `0x4123a0(&tmp, *src)` → `0x41c820(dest, TResStringRec*)`)。呼び出し元は unit #12 (InitTable 12 番) の Init `0x42d870` (カウンタ 0→-1 で 1 回) / Fini `0x42d830` (`0x412560`)。→ 実行時に slot を読む経路は **ある** (間接 call/関数ポインタではなく表参照)。
- 静的 (限界): capstone 線形走査 (関数 57,816・命令 2,566,540) では slot 直接の RIP 相対参照 0 件 (表の `lea rcx,[rip-0x4a0]` 経由のみ)。見つからないことは参照無しの証明ではない。
- 実行時 (**実測**, survey モードで boot 後に unit #12 を 1 回実行): 旧 `m11_data.c` → slot = `0x425f00` (未補正)、修正後 → `0x25f00`。unit #12 は両者とも ret=1・trap 無し・カウンタ 0→-1。slot が指す先の `+8` を `0x41c820` が読むので、未補正では VA `0x425f08` (= linear memory 上の無関係な内容 `0xd989483875f68548`)、補正後は `0xffb5` (resource id)。ただし **dest `0xfa9a58` の最終値は両者とも 0 で、観測できた実行結果は同じ** (`LoadStringW` は m11_win.c で常に 0 を返す stub だが、`0x41c820` がそこまで到達したかは未測)。→ 現時点で結果に出ない潜在バグ。顕在化の条件は未確認 (推定: 文字列資源が実装された後)。
- 未確認: `0x41c820` は `[rsi+8] >= 0x10000` なら別経路 (`0x4148e0`) に入る。未補正の誤値 `0xd989…` はこの分岐に入り得るが、実行時にどちらを通ったか (`LoadStringW` stub の手前でどこまで進むか) は未測。

## 11-3. 検証 (実測; 修正コードはコミット済み HEAD `10c8278`。以降は docs/results のみ。runner 4 vCPU, FL_WIN64_DIR 展開済み, capstone+pefile 入り venv)
| 検査 | 結果 |
|---|---|
| `bash tools/m11/m11_reloc_gate.sh` (新設; fixed LB=0 / LB=0x10000 で補正漏れ 0 を要求 + ネガコン = 条件を旧 `<` に戻した複製で補正漏れ 1 を要求) | rc 0 / ALL PASS 3 件 / 4.07 秒 |
| `bash tools/m11/m11_e2e.sh` 修正前 (旧 `m11_data.c`; 初回 gen_ir2 から走る) | 66 秒 (開始時 load average 0.02): reached_stage 4 / units_run 22 / survey ok 816 trap 79 miss 46 / GetMem 33 FreeMem 20 |
| 同 修正後 (`m11_data.c` 再生成, 2 回: 36.9 秒 (load 0.16→0.57) / 37.2 秒 (load 0.27→0.60)) | reached_stage 4 / units_run 22 / survey ok 816 trap 79 miss 46 / GetMem 33 FreeMem 20。`M11_SUMMARY` は修正前と完全一致 (wasm_bytes 6,022,560・trampolines 7,399 も同値) |
| `m11_slot_probe.mjs --expect-slot-fixed` (修正後) / `--expect-slot-unfixed` (ネガコン: 旧 `m11_data.c` で再 build) | 修正後 slot=0x25f00 rc 0 / 旧 slot=0x425f00 でネガコン成立 rc 0 (どちらも期待と逆なら rc 1) |

`m11_e2e.sh` 自体は未達でも exit 0 の設計 (冒頭コメント) のため、この修正の pass/fail の gate は `m11_reloc_gate.sh` (非 0 で FAIL) と `m11_slot_probe.mjs` が担う。e2e は回帰 (SUMMARY 完全一致) の確認用。

## 11-4. 未解決
| 未解決 | 起票先 |
|---|---|
| m6 (`tools/m6/m6_data_gen.py:42`)・liftlib (`dataimage.py:35`) に同条件が複製。FLEngine 以外の対象で末尾 slot が落ちるかは未測 | 各 owner の子チケット (PM 起票依頼) |
| 実行時差の顕在化は `LoadStringW` stub (常に 0) が実装された後。unit #12 の dest `0xfa9a58` の最終値の比較は未実施 | #132 系 (LoadStringW 実装時に回帰確認) |
