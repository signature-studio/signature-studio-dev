# PY-32 (#1336): channels / playlist / patterns の未実装 flapi 103 関数の棚卸しと分割

親: #1137 (PY-26)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- C provider (`provider/fl_engine.c`) で未実装の関数は計 103 件 (channels 34・playlist 38・patterns 31)。issue 本文の件数と一致。
- mock (`host/fl_mock.mjs`) にも意味論が無いため、戻り値・引数の意味論は実機 (FL 26.1.7 の PE バイナリ) から決める必要がある。
  1 run (60 分) で 103 件の意味論を決めて実装すると、根拠の無い推測実装になるため、本 PR では実装しない。
- 本 PR は 103 件の一覧 (シグネチャと docstring)・実装済み判定の根拠・分割先を確定する。コード変更は 0 件 (`provider/` `host/` `tests/` は未変更)。

## 測定 (実装済み判定)

- 実装済み判定の根拠: `provider/fl_engine.c` の `FL_H(<module>, <name>)` 定義を `grep -oE "FL_H\((channels|playlist|patterns), *[A-Za-z_]+\)"` で抽出し、`analysis/flapi/flapi_table.json` の `modules` と突き合わせ。

| module | flapi 公開数 | 実装済み | 未実装 | `fl_engine.c` 側の余剰定義 |
|---|---|---|---|---|
| channels | 54 | 20 | 34 | 0 |
| playlist | 42 | 4 | 38 | 0 |
| patterns | 31 | 0 | 31 | 0 |

- 測定 commit: `96e608df` (worktree `ws-1336` の起点 = `origin/main`)。
- `git diff 96e608df HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (コード差分 0)。
- コード差分 0 のため、`provider_check.mjs` (実装数 70) と `all_tools.mjs` (48/48) は再測定していない。

## 未実装 103 件の一覧

シグネチャは `flapi_table.json` の `sig` (params の型と名前・returns)。

### channels (34)

- channelNumber(bool canBeNone, int offset) -> int : Get channel number
- closeGraphEditor() -> None : Close graph editor
- focusEditor(int index, bool useGlobalIndex) -> None : focus channel editor
- getActivityLevel(int index, bool useGlobalIndex) -> float : Get channel activity level
- getChannelColor(int index, bool useGlobalIndex) -> int : Get channel color
- getChannelIndex(int index) -> int : Get channel index
- getChannelMidiInPort(int index, bool useGlobalIndex) -> int : Get channel midi in port
- getChannelPitch(int index, int mode, bool useGlobalIndex) -> 'float | int' : Get channel pitch
- getChannelType(int index, bool useGlobalIndex) -> int : get channel type
- getCurrentStepParam(int index, int step, int param, bool useGlobalIndex) -> int : Get current step param
- getGridBit(int index, int position, bool useGlobalIndex) -> bool : Get channel grid bit
- getGridBitWithLoop(int index, int position, bool useGlobalIndex) -> bool : Get grid bit with loop
- getRecEventId(int index, bool useGlobalIndex) -> int : Get channel rec event id
- getStepParam(int step, int param, int index, int startPos, int padsStride, bool useGlobalIndex) -> int : Get step param
- getSwing() -> None : Get swing
- incEventValue(int eventId, int step, float res) -> int : increase event value
- isChannelMuted(int index, bool useGlobalIndex) -> bool : Get channel mute state
- isChannelSolo(int index, bool useGlobalIndex) -> bool : Get channel solo state
- isGraphEditorVisible() -> bool : Returns true if graph editor is visible
- isGridBitAssigned(int index, bool useGlobalIndex) -> bool : Is grid bit assigned
- isHighLighted() -> bool : Is higlight rectangle defined
- midiNoteOn(int indexGlobal, int note, int velocity, int channel) -> None : Set midi note on for channel
- processRECEvent() -> int : Process rec event
- rerollLoopStarterLoop() -> None : Reroll LoopStarter audio loop (use index -1 for all loops)
- rerollLoopStarterSample() -> None : Reroll LoopStarter kit sample (use index -1 for all step channels)
- rerollLoopStarterSteps() -> None : Reroll LoopStarter steps (use index -1 for all step channels)
- selectAll() -> None : Select all channels
- selectOneChannel(int index, bool useGlobalIndex) -> None : Select channel exclusively
- setChannelPitch(int index, float value, int mode, int pickupMode, bool useGlobalIndex) -> None : Set channel pitch
- setStepParameterByIndex(int index, int patNum, int step, int param, int value, bool useGlobalIndex) -> None : Set step parameter by index
- setSwing() -> None : Set swing
- showCSForm(int index, int state, bool useGlobalIndex) -> None : Show cs form
- showGraphEditor(bool temporary, int param, int step, int index, bool useGlobalIndex) -> None : Show graph editor
- updateGraphEditor() -> None : Update graph editor

### playlist (38)

- deselectAll() -> None : Deselect all tracks
- getDisplayZone() -> int : Get display zone number
- getLiveBlockColor(int index, int blockNum) -> int : Get live block color
- getLiveBlockStatus(int index, int blockNum, int mode) -> int : Get live block status
- getLiveLoopMode(int index) -> int : Get live loop mode
- getLivePosSnap(int index) -> int : Get live pos snap
- getLiveStatus(int index, int mode) -> int : Get live status
- getLiveTrigSnap(int index) -> int : Get live trig snap
- getLiveTriggerMode(int index) -> int : Get live trigger mode
- getPerformanceModeState() -> bool : Get performance mode state
- getSongStartTickPos() -> int : Get song start tick position
- getTrackActivityLevel(int index) -> float : Get track activity level
- getTrackActivityLevelVis(int index) -> float : Get track visual activity level
- getTrackColor(int index) -> int : Get track color
- getVisTimeBar() -> int : Get time bar
- getVisTimeStep() -> int : Get time step
- getVisTimeTick() -> int : Get time tick
- incLiveLoopMode(int index, int value) -> None : Increase live loop mode
- incLivePosSnap(int index, int value) -> None : Increase live pos snap
- incLiveTrigMode(int index, int value) -> None : Increase live trig mode
- incLiveTrigSnap(int index, int value) -> None : Increase live trig snap
- isTrackMuteLock(int index) -> bool : Get track mute lock state
- isTrackMuted(int index) -> bool : Get track mute state
- isTrackSelected(int index) -> bool : Get track selected state
- isTrackSolo(int index) -> bool : Get track solo state
- liveBlockNumToTime(int index) -> int : Live block number to time
- liveDisplayZone(int left, int top, int right, int bottom, int duration) -> None : Live display zone
- liveTimeToBlockNum(int time) -> int : Live time to block number
- lockDisplayZone(int index, int value) -> None : Lock display zone
- muteTrack(int index, int value) -> None : Toggle track mute state
- muteTrackLock(int index) -> None : Toggle track mute lock state
- refreshLiveClips() -> None : Refresh live clips
- scrollTo(int a, int b, int c, int d) -> None : Scroll to
- selectAll() -> None : Select all tracks
- selectTool() -> None : Select playlist tool
- selectTrack(int index) -> None : Set track selected state
- soloTrack(int index, int value, bool inGroup) -> None : Toggle track solo state
- triggerLiveClip(int index, int subNum, int flags, int velocity) -> None : Trigger live clips

### patterns (31)

- burnLoop(int index, int storeUndo, int updateUi) -> None : Burn loop
- clearPattern() -> None : Clear pattern
- clonePattern(int | None index) -> None : Clone pattern
- deselectAll() -> None : Deselect all patterns
- duplicatePatternData() -> None : Duplicate pattern data
- ensureValidNoteRecord() -> int : Ensure Valid Note Record
- findFirstNextEmptyPat(int flags, int x, int y) -> None : Find first next empty pattern
- getActivePatternGroup() -> int : Get active pattern group
- getBlockSetStatus(int left, int top, int right, int bottom) -> int : Get block set status
- getChannelLoopStyle() -> int : Get channel loop style
- getPatternColor(int index) -> int : Get pattern color
- getPatternGroupCount() -> int : Get pattern group count
- getPatternGroupName() -> str : Get pattern group name
- getPatternLength(int index) -> int : Get pattern length
- getPatternName(int index) -> str : Get pattern name
- getPatternsInGroup() -> tuple[int, ...] : Get patterns in group
- incrementPatternLength() -> None : Increment pattern length
- isPatternDefault(int index) -> bool : Get pattern default state
- isPatternSelected(int index) -> bool : Get pattern selected state
- jumpToPattern(int index) -> None : Jump to pattern
- movePattern() -> None : Move pattern
- patternCount() -> int : Get patterns count
- patternMax() -> int : Get max pattern id
- patternNumber() -> int : Get current pattern number
- selectAll() -> None : Select all patterns
- selectPattern(int index, int value, bool preview) -> None : Select pattern
- setChannelLoop() -> str : Set channel loop
- setLoopStarterRootNote() -> None : Set the root note of Loopstarter, when its enabled
- setPatternColor(int index, int color) -> None : Set pattern color
- setPatternLength() -> None : Set pattern length
- setPatternName(int index, str name) -> None : Set pattern name

## 分割先 (未解決)

残り 103 件の意味論決定と C provider 実装は、次の子 issue に分割する (親: #1336)。

- channels 34 件 → #1343 (`[PY-33]`)
- playlist 38 件 → #1344 (`[PY-34]`)
- patterns 31 件 → #1345 (`[PY-35]`)

## 受入条件の判定 (#1336)

- [ ] 上記 103 関数の実機意味論を決め、根拠を REPORT に残す — 未達 (本 PR は棚卸しのみ。意味論は #1343・#1344・#1345)。
- [ ] 決めた関数を `provider/fl_engine.c` に実装し、`provider_check.mjs` の実装数を更新 — 未達 (#1343・#1344・#1345)。
- [ ] mock に追加した関数を差分検査で mock と C の diffs 0 — 未達 (#1343・#1344・#1345)。
- [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok を維持 — 未達ではないが未再測定 (コード差分 0)。
