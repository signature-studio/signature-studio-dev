# 付録: icall #1921 (ICALL-51) — SlateCore の encoded 関数ポインタ表・cookie と native CRT 初期化相当

> 親: #1874 (ICALL-47)。前付録: `REPORT_APPENDIX_1874.md`。本 run は受入条件 1 の一部・3 の実測まで。
> 残り (wasm 側の同等初期化・api-set 表の完全特定) は子 issue へ移管 (§4)。

## 1. 結論

- 受入条件 1 (encoded 表・cookie の特定と REPORT 記録): **部分達成**。cookie と、`fa_sweep` の decode 経路が読む
  encoded slot 12 件を特定した (§2)。api-set 表の範囲と完全な slot 数は未確定。
- 受入条件 2 (native で enc(NULL)=cookie の CRT 初期化相当を再現): **部分達成**。`ott_enc_slots`
  (`tools/ott/native/ott_native.c`) と `FA_ENC_INIT=1` (`fa_cmp.py`) で再現した。OTT 向け `tools/ott/crtinit/` は流用していない (方式の参照のみ)。
- 受入条件 3 (`fa_sweep.sh 8 60` の件数変化の実測): **達成**。§3。
- 受入条件 4 (wasm route `fa_route_build.sh` は変更しない): **達成**。本 PR は `tools/ott/native` と `tools/icall/diff` のみ変更。

## 2. 特定結果 (SlateCore.core_64)

| 項目 | 値 |
|---|---|
| security cookie | VA `0x18125eaa8` (`.data` RVA `0x125eaa8`)。load config の `SecurityCookie` と一致。静的既定 `0x2b992ddfa232`、rot = cookie & 0x3f = 50 |
| decode 形式 | `xor reg,[cookie]` 後に `ror reg,cl` (cl = cookie & 0x3f)。`objdump -d -M intel` で 23 箇所を確認 |
| decode が読む `.data` slot | 12 件: `0x1813068d0` `0x1813068f8` `0x181306900` `0x181306908` `0x181306910` `0x1813072b0` `0x1813073f0` `0x1813073f8` `0x181307400` `0x181307408` `0x181307410` `0x181307418` |
| slot の所在 | 全 12 件が `.data` の **zero-fill 部** (raw 無し・仮想のみ)。生値 0 を decode すると `ror(cookie,50)` の garbage 非 0 になる |

- 本 appendix の 12 slot は、decode 命令の近傍 (直前 40 命令) の RIP-relative 参照から集めたもの。
  全 encoded 表 (UCRT の api-set 表 相当の連続配列) は未特定。`.data` zero-fill には BSS 的な参照が多数あり、
  参照だけでは表の境界を切り出せなかった。
- OTT (`tools/ott/crtinit/REPORT.md`) の api-set 表 `0x18026c9f0` (32 entry) や slot `0x18026c028` 等とは
  **別バイナリの別アドレス**。形式 (cookie で encode・zero-fill) は同じ。

## 3. fa_sweep 実測 (`bash tools/icall/diff/fa_sweep.sh 8 60`)

測定 commit: `214df2d6` (コードを変えた最後の commit・ブランチ `1921-icall-crt-init`)。
HEAD までのコード差分は 0 のため、再測定は不要 (`docs/WORKFLOW.md` §6)。

| 項目 | OFF (既定) | ON (`FA_ENC_INIT=1`) |
|---|---|---|
| 所要 | 73 s (real) | 73 s (real) |
| bit一致 | 46 | **47** |
| native crash/timeout | 66 | **64** |
| wasm のみ err | 9 | 9 |
| 値の不一致 | 10 | 11 |
| 合計 | 131 | 131 |

- 状態が変わった関数 (OFF→ON):
  - `0x181065928`: crash → **bit一致**
  - `0x1810553d0`: crash → 値の不一致 (native は `c000c5300342457c` を返し、wasm は `0`)
- 値の不一致が 1 件増えた `0x1810553d0` は、wasm 側に同じ encoded 初期化が無いことが原因と見ている。
  wasm の state を揃えるまで、この件は「不一致」として数える。
- 直接の目標だった crash 3 件 (`0x1803b3fc0`・`0x1803b5b60`・`0x1803b9ff0`) は、ON でも解消しなかった。
  `0x1803b3fc0`/`0x1803b5b60` は libc 側 SIGSEGV (`addr=nil`) のまま。原因は cookie 系の slot 以外にある可能性が高い。

素材: `work-icall` (`tools/icall/work/`)・`work-liftlib` (`tools/liftlib/work/`)・`plugins-freshair`
(`FA_DL=$RUNNER_TEMP/fa_dl bash tools/targets/freshair/fetch.sh`・win 17 files・factory .epf 8 本)・`toolchain-*` は未使用
(`fa_route_build.sh` は `/opt/emsdk` を使用)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側 (`fa_route` の data install) に同じ encoded slot 初期化を入れ、native と state を揃える。あわせて api-set 表の完全な範囲を特定する | 値の不一致 `0x1810553d0` (ON で増加)・crash 残 64 関数の切り分け | ICALL-55 (子) |
| 残る crash 3 件 (`0x1803b3fc0` 等) の原因特定 | 同上 | ICALL-55 (子) |
| 実経路で必要な未実装 import の実装 | 同上 | #1922 (ICALL-52) |

## 5. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60                 # OFF
FA_ENC_INIT=1 bash tools/icall/diff/fa_sweep.sh 8 60   # ON
python3 tools/icall/diff/fa_cmp.py 1803b3fc0 --n 2     # FA_ENC_INIT=1 を付けて比較
```
