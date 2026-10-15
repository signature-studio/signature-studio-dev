# REPORT 付録 (#4871 KH-124): Stereo 閉包 49 関数の emcc 引数なし呼出 22 件を機械語で確定して書き換える (部分: emcc 42 → 20)

親 #4829 の子。手本は `REPORT_APPENDIX_3800.md` §10-7u (#3800 KH-64, Delay の同じ callee 22 件)。

#### 10-7v. #4871 (KH-124) run: Stereo 閉包 (49 関数) の emcc error 42 → 20 件 (部分・Stereo は数値未検証・ビルド未通過)

- **結論**: Stereo 閉包版の emcc error は **42 → 20** (−22)。引数なし呼出 `FUN_180fd4f30()` の 22 件を、呼出元の機械語で確定した delay の ABI 規則 22 本で書き換えた (件数 1 を assert)。受入 1 は **達成** (22 件)。受入 2 (残り arity・型不一致 20 件の解消 → emcc 0) は **未達**。受入 3 (Gain/Haas/Gate の 1000/1000 と生成 C の差分 0 行) は **達成**。
- **注意**: 受入の見出し「26 件」は `param_1` 不足 (single argument) の件数で、そのうち `FUN_180fd4f30()` 呼出は 22 件。残りの 4 件は別 callee (`FUN_180fe3510`・`FUN_180fe5f00`・`FUN_180fd62a8`・`FUN_180fe4394`) の引数不足。
- **測定 commit** (コードを変えた最後の commit): `678386211`。`git diff 678386211 HEAD -- tools/targets/kilohearts/ghidra_route` = 0 行 (本節の commit は REPORT のみ)。
- **検証起点**: `origin/main` = `fc48aa8a5`。

**素材・環境** (作業 dir は repo 外)
- `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip` → `HeartCore.core_64` (76,642,304 B、sha256 先頭 `d55ce8b4`)。
- [GHIDRA] 12.1.4 (公式 release `ghidra_12.1.4_PUBLIC_20260921.zip`、sha256 先頭 `ddac49f9` 一致)。JDK 21。[EMSDK] 6.0.12 (`toolchain-emsdk` を展開)。n=1。

**閉包 (`closure.py stereo`)**: 49 関数 (also 48)・反復 12・FAIL 0・除外参照 3 件 (`FUN_18004cf20`・IAT thunk `81e4`・`81ec`)。wall 5 分 22 秒。親 #4829 の記録と一致。`FUN_180fd8aac` は閉包に入った (`also`)。

**emcc 件数 (`emcc_census.py`・`emcc -c -w -O1 -ferror-limit=0`)**

| 区分 | 基準 (閉包を `also` に入れた直後, `ABI` 規則なし) | 本 PR (`ABI['stereo']` 22 規則あり) |
|---|---|---|
| 引数数不一致 (引数なし呼出を含む) | **30** | **8** |
| 演算・代入・ポインタの型不一致 | **12** | **12** |
| その他 | 0 | 0 |
| **合計** | **42** | **20** |

- 基準の内訳 (emcc 行の対応付け済み): `param_1` 不足 (single argument) 26 件 = `FUN_180fd4f30()` 22 件 + 他の callee 4 件 (`FUN_180fe3510`・`FUN_180fe5f00`・`FUN_180fd62a8`・`FUN_180fe4394`)。その他の arity 不一致 4 件 (`FUN_180fd5bf4`・`FUN_180fe3310`・`FUN_180fd5bcc`・`FUN_180fd8988`)。型不一致 12 件。
- 本 PR で消えた 22 件は、全て `FUN_180fd4f30()` 呼出 (呼出元 `FUN_180fe3690` 13 件・`FUN_180fe3310` 4 件・`FUN_180fe3cd0` 5 件)。`stereo.c` の行番号は生成の都度ずれるため、件数の正本は emcc の census。

**書換えた規則 (`patches.py`・`ABI['stereo'] = ABI['stereo'] + ABI['delay']`)**
- 呼出元は `FUN_180fe3690` (13 件)・`FUN_180fe3310` (4 件)・`FUN_180fe3cd0` (5 件)。VA・機械語が `REPORT_APPENDIX_3800.md` §10-7u の表と同一 (同じ関数の同じ呼出し)。よって、その機械語の根拠 (`mov rcx,[rbx+off]` → `call`) は delay の表が正本。
- 規則 1 件 = 呼出し 1 件 (`ABI` の件数 assert `== 1` が全 22 件で通過)。

**実測**
- Stereo 閉包 emcc: 上表 (`emcc -c` の wall は未計時。load 0.55 0.88 0.62 は Gain/Haas/Gate の突合時)。
- **挙動変更の注意**: `FUN_180fd8aac` は閉包に入り (`also`)、本体を decompile して C 化する。従来の abort stub (`SNAPINS['stereo']['stubs']`) は emit されなくなる (`ghidra_to_c.py` は `va in vas` の stub を出さない)。stub 辞書の行は残してあるが、有効な規則ではない。Inf 入力での到達経路の数値は、突合 (未実施) で確認するまで未検証。
- Gain **1000/1000** bit-exact (calls 4999/4999、wasm 15,161 B)。Haas **1000/1000** (calls 5500/5500、wasm 16,878 B)。Gate **1000/1000** (calls 4999/4999、wasm 17,367 B)。`build_cmp.sh <name> 1000 7 bitcast,intload,stackpair,assoc,concat`。
- 生成 C: `ghidra_to_c.py gain/haas/gate` の出力を、`also` と `ABI` を変える前 (`fc48aa8a5` の `ghidra_route`) の出力と `cmp` → **byte 一致** (3 本とも差分 0)。`also` の変更は stereo のみに効く。

**未解決 (起票先付き)**
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 引数不足・arity 不一致 8 件 (`FUN_180fe3510`・`FUN_180fe5f00`・`FUN_180fd62a8`・`FUN_180fe4394` の引数不足 4 件 + `FUN_180fe3310`・`FUN_180fd5bf4`・`FUN_180fd5bcc`・`FUN_180fd8988` の arity 4 件) | Stereo の emcc が通らない (wasm 不成立) | 子 issue (本 PR で起票) |
| 型不一致 12 件 (`uint`/`float` 二項演算 5・`float` 間接参照 2・`undefined8 ***` 2・`undefined8 **` の代入 2・`undefined1*` の float 代入 1) | 同上 | 子 issue (本 PR で起票) |
| Stereo の数値未検証 (突合 1000 trial・`FUN_180fd8aac` の stub 撤去) | emcc 通過だけでは値の正しさは言えない | #3109 (KH-46)・#3821 [KH-69] (既存・open) |
