# tools/shared/lift/rex 付録 — movnti (閉包内 24 箇所) の到達と x64c 対応の要否 — T-SH-90 (#3589)

測定 commit: `24903929f` (`tools/shared/lift/rex/` の `.c`・`.mjs`・`.py`・`.sh` を変えた最後の commit)。測定 HEAD: `55fe773b2` (§2 の実測ログ 1 本はこの HEAD で取った)。以降の差分は本付録と REPORT の文書だけ (`git diff 24903929f HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力は 0 行)。
既知類型との関係: 該当なし (不一致 0)。

## 結論 (1 行)
movnti は memset (`f_18001c8f0`・8 箇所) の大ブロック経路にだけあり、実測では a1 (= memset の長さ) ∈ [0x70000, 0x80000) の入力 16 件で入力だけで到達する (fn=0・16/16 で wasm が trap)。閾値 0x70000 は静的読み (`count>>6 ≥ 0x1c00`) で、実測はその範囲の一部だけ。a1 ∈ [0x10000, 0x70000) の info 4 件は movnti 以外で trap し、原因は未解明。memcpy (`f_18001ca80`・16 箇所) は、直接 call と定数参照では `f_18001bde8` (長さ 0x40 固定) からしか呼ばれず、入力では到達しない (静的読み)。間接 call 経路は未確認。**x64c 対応は memset の 8 箇所について要** (未実装・子 #3893)。

## 1. 静的な経路 (`lift/fle_lifted.c`・測定 HEAD で読んだ)
| 関数 | movnti | 呼出し元 | 長さ (r8) | movnti に入る条件 |
|---|---|---|---|---|
| `f_18001c8f0` (memset: rcx=dst・rdx=val・r8=count) | 8 | `f_1800011c0` (fn=0・`call` 0x1800022cb) と `f_180001130` (fn=1・`call` 0x18000213a) | `sext32(a1)` (`movsxd` で a1 を符号拡張) | `count>>6 ≥ 0x1c00` ⇒ count ≥ 0x70000 (静的読み) |
| `f_18001ca80` (memmove) | 16 | 直接 call と定数参照では `f_18001bde8` のみ (`mov r8d, 0x40` 固定・0x18001be04) | 0x40 | `count>>5 ≥ 0x2000` ⇒ count ≥ 0x10000。0x40 では不成立 |

- `f_18001bde8` の呼出し元は `f_180016160`・`f_180016170` だけで、どちらも `WaitForSingleObject` の戻りが 0 / 0x80 以外のときの**エラー経路** (直後に `int3`)。harness の `imp_WaitForSingleObject` は 0 を返すので、直接 call の範囲では、この経路は入力でも import でも movnti に届かない。
- 間接 call: 閉包には register 間接 call がある (`f_18001f260` = `ott_dispatch` の呼出し 6 箇所)。その表 (`case 0x3001ca80`) には memmove が入っている。この経路で memmove に入る入力は**未確認** (§4)。
- fn=0 は木の検索 (`f_180001de0`) の直後に memset を呼ぶ (`key_of` は rdi を壊さない・`f_1800019f0` を確認)。fn=1 は memset の前に `f_180012b50`・`f_180012b60`・`f_180012b70`・`f_1800042b0` で node の実体を辿るため、入力の値 (ランダムなポインタ) で先に落ちる (native の fault が arena 末尾 0x30110000 でなく 0x50fb16c0 などになる・推定)。

## 2. 実測 (fix run・1 本のログ)
- 測定: GitHub Actions run 38683492403 (2026-10-15 04:53Z 開始)。HEAD `55fe773b2` で `FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_x64c.sh all` を 1 回 (rc 0・ALL OK・全体 real 12 s)。
- 素材: fl-win64 の `extracted/block24351_PE.bin` (321848 B) のみ。toolchain-emsdk は本 run の素材に無いため、上流 `emsdk install 6.0.12` で代替した (版は `tools/m1/flags.sh` の `EMCC_VERSION_PIN` と同じ 6.0.12)。
- load は `/proc/loadavg` の 1 分・5 分・15 分値の開始→終了。elapsed は整数秒。

| モード | 結果 | elapsed | load 開始 → 終了 |
|---|---|---|---|
| ok (本検査) | PASS・比較 175・一致 175・不一致 0・arena 書込 42・`.data` 書込 0・traps 0 (248 case) | 3 s | 0.41 0.34 0.17 → 0.46 0.35 0.18 |
| neg-cmp | 期待どおり FAIL (不一致 1・case 2・offset 21) | 2 s | 0.46 0.35 0.18 → 0.46 0.35 0.18 |
| neg-ctx | 期待どおり FAIL (不一致 175) | 2 s | 0.46 0.35 0.18 → 0.50 0.36 0.18 |
| neg-owner | 期待どおり FAIL (配信物の一覧が期待と不一致) | 3 s | 0.50 0.36 0.18 → 0.50 0.36 0.18 |
| movnti | PASS (reach 16/16)・info 4/4 は movnti 以外で trap | 0 s (1 s 未満) | 0.50 0.36 0.18 → 0.54 0.37 0.19 |

- reach 16 件 (fn=0・a1 ∈ [0x70000, 0x80000)): wasm は 16/16 が `0x18001c9a0` (`movnti qword ptr [rcx], rdx`・memset の movnti 先頭) で `ott_unsup` に入って trap。native は 16/16 が `0x30110000` (arena 末尾 = 64 KiB の外) で落ちる。movnti 経路でだけ arena を越えて書く。
- info 4 件 (fn=0・a1 = 0x27878・0x2d324・0x3d429・0x3ffa3 ∈ [0x10000, 0x70000)): wasm は 4/4 が trap するが、`ott_unsup` を経由しない (trap VA 0)。movnti ではない。想定 (trap しない) と食い違う。原因未特定 (推定: 通常の memset が arena を越えて書き、後段が壊れる。未確認。子 #3894)。
- 測定の注意: `run_wasm.mjs` は元の機械語が落ちた case を既定で実行しない。movnti モードは `REX_RUN_CRASHED=1` で実行する (元が落ちる入力でも wasm の経路を見るため)。
- 補修 (本 PR): WASI の `fd_write` が 0 を返していたため、trap 前の `fprintf(stderr)` で stdio が戻らなくなっていた。書いた長さを返し、fd 2 の内容を stderr へ流すように直した。`rex_glue.c` で `fle_ff_hook` を使い、trap した未対応命令の VA を `rex_unsup_get` で返す。

## 3. x64c 対応の要否 (判断)
- **memset の movnti 8 箇所: 要。** 入力だけで到達する (実測 16/16。閾値 0x70000 は静的読み)。到達すると fail-fast で trap するため、そういう長さの入力が本番で来るなら x64c の対応が要る。movnti は単一スレッドの意味では普通の store と同じなので、対応は x64c で ST 系へ写すだけで済む見込み (推定。未実装・子 #3893)。本番の host が a1 に何を渡すかは [未確認]。
- **memcpy の movnti 16 箇所: 直接 call の範囲では不要。** 唯一の直接の呼出し元 (`f_18001bde8`) が長さ 0x40 固定で、movnti の閾値 0x10000 に届かない (静的読み・未実測)。「不要」は、間接 call 経路 (§1) が未確認である限り、この限定付きで書く。
- 本付録では x64c を変えない (`tools/flelift/` は触らない)。

## 3.5 `REX_RUN_CRASHED=1` で 296 件を流す停止の修復 — #3895 (T-SH-95)
- 測定 commit: `4d7b8316b` (`tools/shared/lift/rex/run_wasm.mjs` を変えた最後の commit。修復は `52cde16ed`・`4d7b8316b` の 2 本)。測定 HEAD: `4d7b8316b`。
- 原因: wasm の `rex_run` は同期実行で、JS 側から途中で止められない。元の機械語は `native_ref.c` の `ualarm(300 ms)` で止まるが、wasm 側に時間制限が無かった。case 101 (fn=1・a1=0x6dd) が wasm で戻らず、全件の実行が時間切れになった (120 s 超・rc 124)。native 側でも case 101 は落ちる入力 (native で打ち切られる。stderr での SIGALRM は未確認)。
- 修復: `run_wasm.mjs` を case ごとの worker_threads で走らせ、`REX_CASE_MS` (既定 2000 ms) を超えて戻らない case は捨て (`timeout.txt`)、次の case から worker を作り直して続ける。`trap_kind.txt` を新設し、VA が 0 の trap の種類 (JS の例外メッセージ) を case 単位で残す。`trap.txt` の形式は変えていない (`movnti_check.py` が読む)。
- 実測 (HEAD `4d7b8316b`・`REX_RUN_CRASHED=1`・`ok` で作り直した cases.bin 296 件): rc 0・elapsed 2 s・load `0.25 0.38 0.35 → 0.31 0.39 0.36`・cases=296 traps=38 timeouts=1 (case 101)。戻らなかった case は 1 件。
- trap の内訳 (38 件): `memory access out of bounds` 36 件 (VA 0)、`unreachable` 2 件 (VA `0x18001788f` = `idiv by zero`)。境界外 36 件の原因は未特定。36 件はいずれも元の機械語が落ちた case (比較対象外) で、wasm 側だけ trap する。`ok` モードの wasm trap は 0 件 (確認済み)。
- 受入 1 の 248 件との差: 旧 cases.bin (248 件) は `ok` で作り直したため、本測定は 296 件。
- 戻らなかった case (受入 2・§2 と同じ形式):
  - 件数: 1 件 (case 101・fn=1・a1=0x6dd)。
  - 原因: wasm の同期実行が止まらず、worker の時間制限 (`REX_CASE_MS`) で捨てた。native 側では case 101 は落ちる入力 (native で打ち切られる) で、比較対象外。
  - 影響: 他の 295 件は戻った。
- `lift_x64c.sh all` (HEAD `4d7b8316b`): ALL OK (本検査 PASS・ネガコン 3 件 FAIL 期待通り・movnti 到達 16/16)。elapsed 14 s。
- 未解決: 境界外 trap 36 件の VA と原因 (子 #4358 [T-SH-118]・#4324・#4326。子 #3894 の info 4 件と同系の可能性は未確認)・`idiv by zero` の未対応 (VA `0x18001788f`・子 #4359 [T-SH-119])。

## 4. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| movnti (memset 8 箇所) の x64c 対応の実装。到達時は fail-fast で trap | a1 ≥ 0x70000 の入力で wasm が trap | 子 #3893 [T-SH-93] |
| info 4 件 (a1 ∈ [0x10000, 0x70000)) が `ott_unsup` 以外で trap (VA 0)。閾値 0x70000 の静的読みと食い違う。原因未特定 | 閾値の静的読みの反証が未了 | 子 #3894 [T-SH-94] |
| 境界外 (`memory access out of bounds`) の trap 36 件で VA が出ない。原因は未特定 | 元が落ちる入力の wasm 側の trap 原因が未確認 | 子 #4358 [T-SH-118] (VA の取得)・#4324 [T-SH-117]・#4326 (#3894 の修正 PR) |
| `idiv by zero` (VA `0x18001788f`) の未対応。wasm が `unreachable` で trap | 2 件の trap | 子 #4359 [T-SH-119] |
| `REX_RUN_CRASHED=1` で wasm が戻らない (case 101 が時間切れ) | 修復済み (§3.5。case 単位の時間切れ) | 完了 (#3895 の範囲) |
| fn=1 (REXGetInfo) では movnti に到達しなかった (memset の前の node 参照で落ちる) | fn=1 からの到達は未確認 | #3587 [T-SH-88] (open。fn=1 の成功経路の入力を扱う。閉じた #3588 から付け替え) |
| memcpy 16 箇所の間接 call 経路 (`f_18001f260` = `ott_dispatch` の register 間接 call 6 箇所の表・`case 0x3001ca80` に memmove) からの到達 | 「memcpy は不要」は直接 call と定数参照の静的読みに限る | 未起票 (追跡のみ。子は起票しない。本表で追跡) |
| 本番の host が REXGetCreatorInfo に渡す a1 の値域 | 到達が本番で起きるかの判断 | [未確認]。依頼者が FL 側の呼出し値で確認する |
