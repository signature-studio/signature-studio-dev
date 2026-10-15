# 付録: icall #2302 (ICALL-71) — 0x1810553d0 の戻り値と cookie 修復 (i64 load) の既定化

> 親: #2280 (ICALL-70・PR #2305 merge 済み)。前付録: `REPORT_APPENDIX_2280.md`。
> 2280 付録の未確認 3 点 (cookie 初期値の出所・修復の効果・既定 OFF の理由) を本付録で解消する。
> 測定 commit: `d49760bf` (修復の既定を ON にした commit。コードを変えた最後の commit)。§6 参照。

## 1. 結論

- **cookie 初期値は PE 実値で確定**: `SlateCore.core_64` の VA `0x18125eaa8` (8 byte) は `0x2b992ddfa232` (`.data` の実体)。`tools/icall/ir_fix_cookie.py` の `COOKIE_INIT` と一致する。2280 §3 の「出所未確認」はこれで解消。
- **native 判定 (受入 1)**: `0x1810553d0` は `0x181055400` の戻り値 (`ror(cookie ^ slot, cookie & 0x3f)`) が 0 のとき indirect call を飛ばして `eax=0` を返す。enc 初期化 (`slot = cookie`、UCRT の enc(NULL)=cookie 相当) を入れた native は `rax=0` (call-skip 経路)。enc 初期化なしの native は indirect call 先で SIGSEGV する (§3)。
- **wasm 修正 (受入 2)**: cookie の i64 load 修復が必要。修復なし (OFF) は `fa_cmp 1810553d0 --n 2` が `wasm_err=2` (Aborted)。修復あり (ON) は match 2/2、wasm の戻り値 rax も native と同じ 0。`tools/icall/fa_route_build.sh` の `FA_FIX_COOKIE` 既定を 1 に変えた (`d49760bf`)。
- **sweep (受入 3)**: ON/OFF をそれぞれ 2 回ずつ取った。同一 build の 2 回は行単位で完全一致し、揺れは再現しなかった。47/48 の揺れの原因は、再現しないため特定できない (§5・未解決)。

## 2. cookie 初期値の出所 (PE 実値)

- 方法: `pefile` で `SlateCore.core_64` (`plugins-freshair` の `Fresh Air.Win.zip` を展開した `FA_DL` 配下) を開き、ImageBase `0x180000000` から VA `0x18125eaa8` の 8 byte を読んだ。
- 結果: `32 a2 df 2d 99 2b 00 00` (little endian) = `0x2b992ddfa232`。`.data` (`0x18125c000`〜) の実体。
- 2280 §3 では RetDec の i32 (`0x2ddfa232`) しか見えず、上位 32bit `0x2b99` は根拠が無かった。PE 実値がその根拠になる。
- 補足: `0x2b992ddfa232` は MSVC の既定 security cookie として知られる定数と同じ値 (参考。CRT 側の照合は未実施)。

## 3. native の判定 (受入 1)

- `0x181055400` の機械語: `mov rbx,[0x18125eaa8]` (cookie 8byte) → `mov ecx,ebx; and ecx,0x3f` → `xor rbx,[0x1813068f8]` (encoded slot) → `ror rbx,cl`。戻り値は `rbx` (rax)。slot が cookie に等しい (enc(NULL)=cookie) とき戻り値は 0。
- `0x1810553d0` は `test rax,rax` が 0 なら `eax=0` を返して終わる (indirect call を飛ばす)。非 0 なら `call [0x1810806a0 の thunk]`。
- 測定 (native `ottnat`、SlateCore.core_64、seed 3、入力 2 点):

| native の条件 | `0x181055400` の rax | `0x1810553d0` の rax | `0x1810553d0` の xmm0 |
|---|---|---|---|
| enc 初期化あり (`FA_ENC_INIT=1`) | 0 (2/2) | 0 (2/2・call-skip) | 入力と一致 (2/2) |
| enc 初期化なし | — | SIGSEGV (`rip=0x1810806a0`) | — |

- 判定: enc 初期化の無い native は decode が非 0 になり、未解決の thunk (`0x1810806a0`) を呼んで落ちる。よって native 側の正しい値 (戻り値 0) は enc 初期化ありの条件でのみ得られる。`0x1810553d0` の戻り値は call-skip 経路の `eax=0` である。
- xmm0 は関数が書かないため入力の素通し。`fa_cmp.py` は xmm0 のみを比べるので、この関数の戻り値 (eax) は fa_cmp では見えない (§8)。

## 4. wasm 側の修復 (受入 2)

`FA_ENC_INIT=1` で route を作り、`fa_cmp.py 1810553d0 --n 2` と wasm の戻り値 (`mod._ott_run` の戻り値 = rax) を取った。

| build | `fa_cmp 1810553d0 --n 2` | wasm rax |
|---|---|---|
| OFF (`FA_FIX_COOKIE=0`) | match 0 / wasm_err 2 (`Aborted(native code called abort())`) | 取得不可 (abort) |
| ON (既定 `FA_FIX_COOKIE=1`) | match 2/2 / wasm_err 0 | 0 (native の rax 0 と一致) |

- 修復は `ir_fix_cookie.py` が `loads_fixed` 13・`sext_fixed` 13 件 (`fix_cookie.json`)。
- ON と OFF の差は、`FA_ENC_INIT=1` の sweep で 2 関数だけ: `0x1810553d0` と `0x181065928` が wasm_err 8/8 → bit 一致 8/8 (他 129 関数の class は不変)。

## 5. fa_sweep 8 60 の ON/OFF (受入 3)

`bash tools/icall/diff/fa_sweep.sh 8 60` (131 関数、1 並列)。列は bit一致 / native crash・timeout / wasm のみ err / 値の不一致。

| build | 1 回目 | 2 回目 | 2 回の行差分 |
|---|---|---|---|
| ON, enc なし | 55/65/9/2 | 55/65/9/2 | 0 行 |
| OFF, enc なし | 55/65/9/2 | 55/65/9/2 | 0 行 |
| ON, `FA_ENC_INIT=1` | 57/63/9/2 | 57/63/9/2 (HEAD `d49760bf`) | 0 行 |
| OFF, `FA_ENC_INIT=1` | 55/63/11/2 | 55/63/11/2 (HEAD `d49760bf` は 1 回) | 0 行 |

- enc なしでは、`0x1810553d0` は native 側が落ちる (§3) ため、ON/OFF で class が変わらない。ON/OFF の差は enc ありの sweep に現れる。
- 値の不一致 2 件は全 build で同じ: `0x1803dee20` と `0x180da4030` (native 0 / wasm 入力。xmm0 の出所は 2508 付録 §3.4 で未解決のまま)。
- 揺れ: 2280 の記録 (47/48) と 2508 付録 §3.5 の記録 (`0x1803dee20` の 1 件が 55 ↔ 54) は、この tree では再現しなかった。`fa_cmp 1803dee20 --n 8` の単独 3 回も毎回 0/8 一致で同じ。原因は特定できない。2280 の 47/64/11/9 は ICALL-78/79 (harness の出力スロット・PTR 正規化) より前の tree の値で、本表と直接比べられない。

## 6. 測定 commit と差分

- 測定 commit: `d49760bf` (`fix(icall): enable cookie i64 load fix by default (ICALL-71 #2302)`)。修正は `tools/icall/fa_route_build.sh` (既定 `FA_FIX_COOKIE` 0→1) と `tools/icall/ir_fix_cookie.py` (docstring の出所注記)。
- 測定経路 (`fa_route_build.sh`・`ir_fix_cookie.py`・`ir_fix_mask.py`・`ir_fix_vstore.py`・`ir_flatten.py`・`ir_override.py`・`vex_gen.py`・`simd_merge.py`・`diff/fa_cmp.py`・`diff/fa_sweep.sh`・`frame_slot_restore.py`・`frame_slot_probe.py`・`rt/`・`tools/ott/native`・`tools/ott/lift/data_gen.py`・`tools/m2/ir_normalize.py`・`tools/m5/ir5_patch.py`・`tools/m11/m11_simd2.py`・`tools/m11/msimd11_core.h`) の `git diff d49760bf HEAD -- <上記>` は 0 行。
- main 取り込み: `origin/main` (`a9733bbb`) を merge した HEAD `66be2919` で、ON の `fa_cmp 1810553d0 --n 2` (match 2/2) と `fa_sweep 8 60` (57/63/9/2) を再測定し、d49760bf 時点と同じ結果。取り込みで増えた差分は測定経路の外 (`lea_index_scan`・`chain_chunk`・`tools/m11/ldfix` など)。

## 7. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .          # リポジトリ直下 (tools/icall/work/)
mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh   # SlateCore.core_64 を work/win へ
bash tools/ott/native/build.sh
FA_ENC_INIT=1 bash tools/icall/fa_route_build.sh                  # 既定 = ON (FA_FIX_COOKIE=1)
FA_ENC_INIT=1 python3 tools/icall/diff/fa_cmp.py 1810553d0 --n 2   # 期待: match 2 / mismatch 0
FA_ENC_INIT=1 bash tools/icall/diff/fa_sweep.sh 8 60 | tail -1      # 期待 (ON): 57/63/9/2 (fa_sweep の表示順)
FA_ENC_INIT=1 FA_FIX_COOKIE=0 bash tools/icall/fa_route_build.sh  # OFF
FA_ENC_INIT=1 python3 tools/icall/diff/fa_cmp.py 1810553d0 --n 2   # 期待: wasm_err 2
```

PE 実値の読み取り: `python3 -c "import pefile; pe=pefile.PE('<SlateCore.core_64>', fast_load=True); print(pe.get_data(0x18125eaa8 - pe.OPTIONAL_HEADER.ImageBase, 8).hex())"` → `32a2df2d992b0000`。

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| fa_sweep の揺れ (47/48・55 ↔ 54) の原因 | 現 tree で 8 回の行差分 0 件・単独 3 回も一致。原因を特定できない | 未起票 (再現条件が無い。再現したら新 issue。PR 本文の未解決表で追跡) |
| `fa_cmp.py` は xmm0 のみ比較。戻り値が eax の関数 (`0x1810553d0` など) の rax は見ていない | 本付録では rax を別途確認 (wasm は `_ott_run` の戻り値)。sweep の rax 比較は未実施 | 未起票 (判定を変えると sweep 数値が動くため PM 判断) |
| `0x1803dee20` の native 0 / wasm 入力 (xmm0 の出所) | 値の不一致 1 件 (全 build) | #2695 (ICALL-81・OPEN) |
| `0x180da4030` の native 0 / wasm 入力 (xmm0 の出所) | 値の不一致 1 件 (全 build) | #2708 (ICALL-83・CLOSED) の後続 PR #3202 (ICALL-83・open) |
