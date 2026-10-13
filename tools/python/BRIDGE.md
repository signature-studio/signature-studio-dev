# FL wasm ⇄ Python wasm ⇄ MCP ブリッジ設計 (実装済み PoC 部分は ✔)

## 1. 構成

```
 main thread (UI/Canvas/WebMIDI)
   │ postMessage (run / call / midi)                       ※ Atomics.wait は main で不可 → Python は Worker 必須
   ▼
 Worker B  ── flpy.wasm = CPython 3.12.1 (static) + _flhost(C) + fl_api/fl_rt(Py)      ✔
   │  FL 側 Python module (channels/mixer/…/ilmcp) = fl_api が生成する薄いラッパ(435 関数)  ✔
   │  _flhost.call(fn_id, args) → flhost_call(JS import) → RpcClient.call (Atomics.wait)   ✔
   ▼  SAB mailbox (ctrl Int32[4] + JSON 1MiB)  ※ postMessage 不使用 / server は Atomics.waitAsync   ✔
 FLEngine 側 (Worker A or main): RpcServer → engine.call("mixer.getTrackName",[i])         ✔(mock)
   └ 実装版: FLEngine wasm の flapi provider (後述 §5)
```

- 利用者の FL 由来ファイル (`midi.py` `utils.py` `MCPTools.pyc` / device script) は **実行時にユーザの FL インストールから供給** (`files:{}`)。リポジトリには同梱しない。
- Python → ホストは単一境界 `_flhost.call(fn_id, tuple)` のみ。FL ロジックは Python 側に無い (データ駆動: `flapi_table.json` → `fl_api.install()`)。fn_id は `flapi_ids.json` の列挙順で Python/JS 共通 ✔。

## 2. ABI (flpy.c ⇄ flhost_lib.js)

| 方向 | 形式 |
|---|---|
| 引数 | 16B スロット × argc(≤32): tag(u8@0) + payload(@8)。`N`one `B`ool `I`nt64 `D`ouble `S`tr(ptr,len UTF-8) `Y`bytes `F`=Python callable → `{__cb:id}` |
| 戻り | 16B スロット: `N B I D S Y` + `J`(JSON: list/dict 等の構造値, C が json.loads) + `E`(code,msg → `_flhost.HostError`) |
| 例外 | code 1..8 = FLEngine 文言(Invalid value / Range error / Operation unsafe at current time / Wrong parameter type …)。`fl_api` が ValueError/IndexError/TypeError/RuntimeError に写像 |
| float | JS の number は整数値なら int になるため float は `{t:'D',v}` で明示 (mock の `F()`)。実 FLEngine provider は戻り型を C 側で持つので曖昧さ無し |
| callable | `ilmcp.showHighlight(item,name,caption,whenDone,True)` が実際に関数を渡す (実測)。C が `_flhost._cbs[id]` に保持 → ホストは `fl_rt:invoke_cb(id)` で呼戻し ✔ |

host→Python 入口 (flpy.c export): `flpy_init(syspath)` `flpy_run(src,file)` `flpy_call_json("mod:func", args_json)` `flpy_last_error` `flpy_free` `flpy_finalize`。
`call_json` が MCP tools/call・MIDI callback・callback 呼戻しの共通口 (`fl_rt.call_json`)。

## 3. 呼出し経路

| 経路 | 実装 |
|---|---|
| MCP `tools/list` `tools/call` | `host/mcp_rpc.mjs` (JSON-RPC 2.0, 応答は FLEngine の固定テンプレート形) → `py.call("__main__:<tool>")`。MCPTools.pyc は FL と同じく **`__main__` として実行** (`get_mcp_tools_json` が `sys.modules['__main__']` を走査するため) ✔ |
| アプリ UI / devtools (PY-4 #77) | `src/runtime/mcp_panel.ts` が `window.flMcp` (`start(files)` / `rpc(req)` / `list()` / `call(name,args)` / `stop()`) を常時公開、`/?mcp=1` で UI パネル (MCPTools.pyc・midi.py・utils.py を選択/ドロップ → 起動 → tool 選択 → tools/call)。`tools/python` の host/・dist/flpy.*・flapi_ids.json だけを Vite が `/py/` で配信 (`vite.config.ts` `pyAssets`、許可リスト方式。`work/` = FL 由来ファイルは配信しない)。flapi の提供側は FLEngine 未完成の間 `fl_mock.mjs` (実エンジン結合時は engine を差替)。`tools/call` は `tools/list` に出る name のみ受理 (未知 / 非 tool は isError=true) ✔ |
| MIDI scripting (PY-6 #76) | `host/midi_host.mjs` `MidiScriptHost`: device script (.py) を `fl_rt.load_device_script` で script ごとの module namespace に読込み (利用者が FL から供給、非同梱)、`init()` で OnInit→OnInitAll、Web MIDI の全入力を `attachWebMidi` で `midiIn` に結線 (直列キュー・port 採番)。受信は FL 順 OnMidiIn → OnMidiMsg → 型別 (handled で停止)、非 MIDI の 27 callback は `fl_rt.CALLBACKS` 表 (個数不一致は reject) で `callback()`。アプリ側は `window.flMidi` / `/?midi=1` (`src/runtime/midi_script.ts`)。`flmidimsg` 23 フィールド ✔。実エンジンからの host 通知 (OnIdle/OnRefresh…) の発火は FLEngine 側 (未結線) |
| Piano roll scripting | `.pyscript` の `createDialog()` / `apply(form)` + `flpianoroll` module (Note/Marker/score/Utils/ScriptDialog)。**実装済 ✔** (`src/flpianoroll.py` + `fl_rt.load_pyscript` / `run_pyscript`、#79。詳細は REPORT §14) |
| stdout/stderr | FL は `fl.FLTextOutput` で Script output へ。本 PoC は Worker→main の `stdout/stderr` メッセージ ✔ |

## 4. スレッド/リアルタイム

- FL の Python は UI/MIDI スレッドで動き、audio スレッドには入らない (API が "Operation unsafe at current time" を返す設計)。→ Python Worker は **AudioWorklet から完全分離**。FLEngine 側 RpcServer は UI/メッセージループの tick で処理 (waitAsync のため待ち行列は自然に直列化)。
- 往復コスト実測 (node, JSON RPC, Worker↔main): **bimodal: 約 15µs (速い時) 〜 約 100〜130µs (遅い時、検収再計測の大半)** (channelCount ×20,000, `tests/rtt_bench.mjs`)、コールド 65〜134µs (最初の 500〜2,000 回)。MCP 48 tool 全実行は 37,424 呼出し (うち `get_session_context` 18,056 と `get_mixer_routing` 16,381 が 127 トラック×127 宛先の走査) で全体 2.2 秒 (起動込み)。MIDI 1 イベント当り数十呼出しなら 100µs/呼出しでも数 ms: 許容。ホット経路が出たら §6 の B 案か binary ABI。

## 5. FLEngine 側の実装案 (provider)

A. **別 Worker + SAB RPC (現行 PoC)** ✔ C provider 実装済み (`provider/`, REPORT §7b): provider = `engine.call(name,args)` を FLEngine wasm の C ABI `int fl_api_call(fn_id, const slot* argv, int argc, slot* ret)` に差し替えるだけ。Python 側無変更。クラッシュ/無限ループを Worker 破棄で隔離でき、FLEngine 未完成でも先行開発可 (mock)。
B. **CPython を FLEngine wasm に静的リンク (最終形)**: `_flhost.call` を同一 wasm 内の C 呼出しに (JS 往復・JSON 無し, <1µs)。FL 本来の「同一プロセス・同一スレッドで callback」と一致。`libpython3.12.a`(9.6MB .a / +5.9MB wasm) をリンクし `PyImport_AppendInittab` で `_flhost` を登録する点は flpy.c と同じ (再利用可)。FLEngine lift 後に移行。
C. FL 側に固有の Python C API 使用 (`PythonSession`/`TMCPPythonSession`, `PyInterpreterConfig`=サブインタプリタ示唆, `pycb*`) は rodata から確認できるが、呼出し関数名は dlopen/dlsym 経由で平文に残らず未抽出 (§REPORT 未解決)。サブインタプリタ分離は wasm で動く (REPORT §11 の実測) が、`_flhost` が static 状態を持つため現状は不可 (isolated は import 拒否、legacy は main を壊す)。device script は module namespace 分離で足りる判断で採用しない。

## 6. 既知の限界 / 次の拡張

- 戻り値の float/int 区別はモックのみ `F()` が必要。構造値は JSON (getTrackInfo 等)。
- `Atomics.wait` を使うため COOP/COEP 必須 (本プロジェクト全体の前提と同一)。`Worker` は module worker (Chrome ✔ 実測)。
- ilmcp 9 関数 (PluginDB/Browser/PRScript/highlight) は FLEngine 内部機能で、mock は最小の偽実装。実装は T3。
- `mixer.getCurrentTempo(1)` の意味: MCPTools は素の BPM として扱う (clamp 10..522)。公式 docs の asInt=×1000 と食い違う可能性 → 実機未検証 (mock は MCPTools に合わせた)。
