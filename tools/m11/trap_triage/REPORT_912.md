# REPORT_912 — ClassCreate ON の ok 退行 4 件 (101 190 291 296) の oob 経路の切り分け (#912, 親 #704)

結論: 4 件の oob は、`410360` (ClassCreate ON 時の AfterConstruction 呼出し stub) が **不正な `inst` を受けて `Q(inst)` の読みで trap** することから始まる。
`inst` が不正になる上流の経路は未特定。受入条件 1 は未達。転記ミスではなく、上流での値の破損 (または上流 lift の欠陥) を疑うが、未検証。

## 1. 基準 (本 run で再生成・再測定)

- 検証起点: `origin/main` (99b87bc2)。素材: fl-win64 (`FL_WIN64_DIR`)・work-m11 (スナップショット、`m11_gen_ir2.sh` で IR を作り直した)。
- `m11_gen_ir2.sh`: 37.9 s (rc=0)。ldfix=applied (F1=902、errors=0)。
- `m11_build.sh` ON: 22.9 s (rc=0、signature mismatch 0・undefined symbol 0)。OFF: rc=0。
- `survey_units.mjs`: ON 9.3 s (rc=0)、OFF (rc=0)。load average 0.24–0.49。

## 2. 測定 (同一 IR・同一 build 系列)

| 構成 | ok | oob | halt0 | miss | noproc | other |
|---|--:|--:|--:|--:|--:|--:|
| OFF | 869 | 16 | 8 | 47 | 1 | 1 |
| ON | 867 | 18 | 8 | 47 | 1 | 1 |

- `survey_diff.py` (OFF→ON): ok→oob 4 (101 190 291 296)、oob→ok 2 (304 555)。ok 退行 unit: 101, 190, 291, 296。
- REPORT_704 の表 (OFF oob 17 / ON oob 19) とは 1 ずつ違う (本 run は OFF oob 16 / ON oob 18)。原因は未切り分け (基準 IR の差の可能性)。ok 数 (869 / 867) は一致。
- ON では 0x41037d が 1049 ok / miss 2 (OFF は 0)。4 件の unit ではいずれも 0x41037d が 1 hit 立つ。

## 3. 4 件の trap 位置 (SV_RAW の生 frame を `oob_insn.py` で逆引き)

| unit | 最上位 frame | 命令 (wasm offset) | 備考 |
|--:|---|---|---|
| 101 | `function_410360` | `i64.load` (`[ptr-80]` 相当) | 直前に VA-big 125.3 MB (#20) |
| 190 | `function_412e40` | `i32.load` (`[ptr-8]` 相当) | 呼出し元 `function_6cf480` ほか。410360 を経由しない |
| 291 | `function_410360` | 同上 | 直前に VA-big 125.3 MB (#23) |
| 296 | `function_410360` | 同上 | 直前に VA-big 125.3 MB (#24) |

## 4. 410360 の入力値 (C 側に一時 probe を入れて実測。probe は取り除き済み)

- `function_410360` の入口で `inst` を記録した。unit 101 では `inst=0x10bb93a0` (正常な heap 値) の呼出しが通った後、VA-big が出て、次の呼出しで `inst=0x000f2b18` になり trap した。291 / 296 も同じ形 (`0x10bb9520` / `0x10bb9580` → `0xf2b18`)。
- 190 は `inst=0x10bd4d10` の 1 回で trap し、410360 の入口はこの 1 回だけ。
- 上流の `410320` (ClassCreate) の戻り値を記録すると、unit 101 の VA-big 直前の最後の `410320` は `ret=0x10bb93a0` を返していた (記録の末尾 8 行で確認。全 unit・全呼出しでは未確認)。`0xf2b18` を返した `410320` は、記録した範囲では見えていない。
- 呼出し元 `function_4fa070` は、`dl != 0` のとき `410320` の戻り値を `[rbp+0x70]` に保存し (4fa09f)、後段 4fa0f3 で `rcx=[rbp+0x70]` を `410360` に渡す。`0xf2b18` はこの経路の戻り値ではない。

## 5. 未特定の点 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xf2b18` が `410360` の `inst` に入る経路 (`function_4fa070` の 2 回目の invocation の入力、または VA-big 直後の `[rbp+0x70]` 上書き) | 4 件の oob の直接原因 | #912 (本 issue) |
| 190 の `412e40` 経由の trap (410360 を経由しない) | 同上の 4 件の一部。別経路の可能性 | #912 (本 issue) |
| `Q(inst)` が指す値の中身 (ON で `0xf2b18` の内容) を未測定 | 値の破損元の切り分け | #912 (本 issue) |

## 6. 次の一手 (提案・未検証)

- `function_4fa070` の 2 回目の呼出しの入力 (rcx, dl, r8) を、呼出し元 (4fb090 / 4fb8a0 の `call 0x4fa070` 位置) で記録する。
- VA-big 直後に `[rbp+0x70]` (4fa070 の frame) が書き換わるかを、frame 先頭の値の before/after で見る (stack 破壊の有無)。
