// FLP event dictionary (independently written; ids/sizes validated against the Demo/Template/Render-test/FST/FSC corpus and the
// FLEngine_x64.dll writer call sites -- see REPORT.md). `src` records provenance of the label:
//   upstream = id is also modelled by PyFLP 2.2.1 (see id_sets.ts)   legacy = long-documented FL SDK-era id
//   observed = label inferred from the engine writer order + corpus structure only (low confidence; semantics not verified)
import { UPSTREAM_IDS, ENGINE_WRITTEN_IDS } from './id_sets.ts';

export type ValType = 'u8' | 'i8' | 'bool' | 'u16' | 'i16' | 'u32' | 'i32' | 'color' | 'wstr' | 'astr' | 'blob' | 'rec';
export type Scope =
  | 'project'
  | 'channel'
  | 'plugin'
  | 'pattern'
  | 'arrangement'
  | 'playlist'
  | 'mixer'
  | 'insert'
  | 'slot'
  | 'timemarker'
  | 'track'
  | 'group'
  | 'any';
export type Conf = 'high' | 'med' | 'low';

export interface EventDef {
  id: number;
  name: string;
  type: ValType;
  scope: Scope;
  src: 'upstream' | 'legacy' | 'observed';
  conf: Conf;
  note?: string;
  /** fixed record stride for 'rec' payloads */
  recSize?: number;
}

const defs: EventDef[] = [];
function d(id: number, name: string, type: ValType, scope: Scope, src: EventDef['src'], conf: Conf, note?: string, recSize?: number): void {
  defs.push({ id, name, type, scope, src, conf, note, recSize });
}

// ---- BYTE (0..63) ----
d(0, 'ChannelEnabled', 'bool', 'channel', 'upstream', 'high');
d(1, 'NoteOn', 'u8', 'channel', 'legacy', 'low', 'legacy preview note (FST only)');
d(2, 'ChanVolByte', 'u8', 'channel', 'upstream', 'med', 'legacy; superseded by ChannelLevels(219)');
d(3, 'ChanPanByte', 'u8', 'channel', 'upstream', 'med');
d(4, 'MidiChannel', 'u8', 'channel', 'legacy', 'low');
d(9, 'LoopActive', 'bool', 'project', 'upstream', 'high', 'song/pattern mode');
d(10, 'ShowInfo', 'bool', 'project', 'upstream', 'high');
d(11, 'Swing', 'u8', 'project', 'upstream', 'med');
d(12, 'MainVolByte', 'u8', 'project', 'upstream', 'low', 'legacy');
d(13, 'FitToSteps', 'u8', 'channel', 'upstream', 'low', 'legacy');
d(14, 'Pitchable', 'bool', 'channel', 'legacy', 'low');
d(15, 'Zipped', 'bool', 'channel', 'upstream', 'med');
d(16, 'DelayFlags', 'u8', 'channel', 'legacy', 'low');
d(17, 'TimeSigNum', 'u8', 'project', 'upstream', 'high');
d(18, 'TimeSigBeat', 'u8', 'project', 'upstream', 'high');
d(19, 'UseLoopPoints', 'bool', 'channel', 'legacy', 'low');
d(20, 'PingPongLoop', 'bool', 'channel', 'upstream', 'med', 'channel loop type');
d(21, 'ChannelType', 'u8', 'channel', 'upstream', 'high', 'upstream enum: 0 sampler, 2 native, 3 layer, 4 instrument, 5 automation (corpus value histogram in REPORT.md)');
d(22, 'RoutedTo', 'i8', 'channel', 'upstream', 'high', 'mixer insert index; -1 = none');
d(23, 'PanLaw', 'u8', 'project', 'upstream', 'med');
d(24, 'Unk24', 'u8', 'channel', 'observed', 'low', 'FST channel presets only');
d(25, 'Unk25', 'u8', 'pattern', 'observed', 'low', 'written next to PatternLooped(26)');
d(26, 'PatternLooped', 'bool', 'pattern', 'upstream', 'med');
d(27, 'Unk27', 'u8', 'insert', 'observed', 'low', 'high count (6198); present when RTF comment(198)/older mixer layouts');
d(28, 'Licensed', 'bool', 'project', 'upstream', 'high');
d(29, 'Apdc', 'bool', 'mixer', 'upstream', 'med', 'automatic plugin delay compensation');
d(30, 'PlayTruncatedNotes', 'bool', 'project', 'upstream', 'med');
d(31, 'Unk31', 'u8', 'mixer', 'observed', 'low', 'mixer-prelude flag');
d(32, 'ChannelLocked', 'bool', 'channel', 'upstream', 'med');
d(33, 'TimeMarkerNum', 'u8', 'timemarker', 'upstream', 'high');
d(34, 'TimeMarkerDenom', 'u8', 'timemarker', 'upstream', 'high');
d(35, 'Unk35', 'u8', 'project', 'observed', 'low', 'project header flag');
d(36, 'Unk36', 'u8', 'project', 'observed', 'low');
d(37, 'Unk37', 'u8', 'project', 'observed', 'low', 'follows Licensed(28)/FlStudioVersionText; value 1');
d(38, 'Unk38', 'u8', 'mixer', 'observed', 'low', 'mixer-prelude flag');
d(39, 'Unk39', 'u8', 'mixer', 'observed', 'low', 'mixer-prelude flag');
d(40, 'Unk40', 'u8', 'mixer', 'observed', 'low', 'mixer-prelude flag');
d(41, 'PluginFlag41', 'u8', 'plugin', 'observed', 'low', 'written between PluginColor(128) and PluginData(213)');
d(42, 'InsertFlag42', 'u8', 'insert', 'observed', 'low');
d(43, 'TrackFlag43', 'u8', 'track', 'observed', 'low', '500 per arrangement, written after TrackData(238)');
d(44, 'Unk44', 'u8', 'project', 'observed', 'low');
d(45, 'TimeMarkerFlag45', 'u8', 'timemarker', 'observed', 'low');
d(46, 'TimeMarkerFlag46', 'u8', 'timemarker', 'observed', 'low');
d(47, 'Unk47', 'u8', 'project', 'observed', 'low', 'written after MixerData243');
d(48, 'ChannelFlag48', 'u8', 'channel', 'observed', 'low');
d(49, 'InsertFlag49', 'u8', 'insert', 'observed', 'low');
d(50, 'ChannelFlag50', 'u8', 'channel', 'observed', 'low');
d(51, 'ChannelFlag51', 'u8', 'channel', 'observed', 'low');
d(52, 'PatternFlag52', 'u8', 'pattern', 'observed', 'low', 'last property of a pattern block');
d(54, 'Unk54', 'u8', 'any', 'observed', 'low', 'FST only');
d(56, 'Unk56', 'u8', 'any', 'observed', 'low', 'FST only');

// ---- WORD (64..127) ----
d(64, 'NewChannel', 'u16', 'channel', 'upstream', 'high', 'opens a channel; value = channel iid');
d(65, 'NewPattern', 'u16', 'pattern', 'upstream', 'high', 'opens a pattern (1-based); FSC: score');
d(66, 'TempoCoarse', 'u16', 'project', 'upstream', 'med', 'legacy BPM (pre-3.4)');
d(67, 'CurrentPattern', 'u16', 'project', 'upstream', 'high');
d(69, 'ChanFreqTilt', 'u16', 'channel', 'upstream', 'med');
d(70, 'ChanFxFlags', 'u16', 'channel', 'upstream', 'med');
d(71, 'ChanCutoff', 'u16', 'channel', 'upstream', 'high');
d(72, 'ChanVolWord', 'u16', 'channel', 'upstream', 'med');
d(73, 'ChanPanWord', 'u16', 'channel', 'upstream', 'med');
d(74, 'ChanPreamp', 'u16', 'channel', 'upstream', 'med');
d(75, 'ChanFadeOut', 'u16', 'channel', 'upstream', 'med');
d(76, 'ChanFadeIn', 'u16', 'channel', 'upstream', 'med');
d(78, 'Unk78', 'u16', 'any', 'observed', 'low');
d(80, 'MainPitch', 'i16', 'project', 'upstream', 'high', 'cents');
d(83, 'ChanResonance', 'u16', 'channel', 'upstream', 'med');
d(85, 'ChanStereoDelay', 'u16', 'channel', 'upstream', 'med');
d(86, 'ChanPogo', 'u16', 'channel', 'upstream', 'med');
d(89, 'ChanTimeShift', 'u16', 'channel', 'upstream', 'med');
d(91, 'Dot91', 'u16', 'any', 'legacy', 'low');
d(92, 'Dot92', 'u16', 'any', 'legacy', 'low');
d(93, 'TempoFine', 'u16', 'project', 'upstream', 'med', 'legacy fine tempo');
d(94, 'LayerChildren', 'u16', 'channel', 'upstream', 'med');
d(95, 'InsertIcon', 'i16', 'insert', 'upstream', 'med');
d(97, 'ChanSwing', 'u16', 'channel', 'upstream', 'med');
d(98, 'SlotIndex', 'u16', 'slot', 'upstream', 'high', 'opens an effect slot of the current insert (0..9)');
d(99, 'NewArrangement', 'u16', 'arrangement', 'upstream', 'high');
d(100, 'CurrentArrangement', 'u16', 'mixer', 'upstream', 'high');
d(101, 'TimeMarkerWord101', 'u16', 'timemarker', 'observed', 'low');
d(103, 'MixerWord103', 'u16', 'mixer', 'observed', 'low', 'mixer prelude');
d(104, 'ChanWord104', 'u16', 'channel', 'observed', 'low');
d(111, 'Unk111', 'u16', 'any', 'observed', 'low', 'FST only');
d(114, 'Unk114', 'u16', 'any', 'observed', 'low', 'FST only');

// ---- DWORD (128..191) ----
d(128, 'PluginColor', 'color', 'plugin', 'upstream', 'high');
d(131, 'ChanRingMod', 'u32', 'channel', 'upstream', 'med');
d(132, 'ChanCutGroup', 'u32', 'channel', 'upstream', 'med');
d(133, 'WindowHeight', 'u32', 'project', 'upstream', 'med');
d(135, 'ChanRootNote', 'u32', 'channel', 'upstream', 'med');
d(138, 'ChanDelayMod', 'u32', 'channel', 'upstream', 'med');
d(139, 'ChanReverb', 'u32', 'channel', 'upstream', 'med');
d(140, 'ChanStretchTime', 'u32', 'channel', 'upstream', 'low', 'float32 in upstream');
d(142, 'ChanFineTune', 'i32', 'channel', 'upstream', 'med');
d(143, 'ChanSamplerFlags', 'u32', 'channel', 'upstream', 'med');
d(144, 'ChanLayerFlags', 'u32', 'channel', 'upstream', 'med');
d(145, 'ChanGroupNum', 'i32', 'channel', 'upstream', 'med');
d(146, 'CurGroupId', 'i32', 'project', 'upstream', 'med');
d(147, 'InsertOutput', 'i32', 'insert', 'upstream', 'high');
d(148, 'NewTimeMarker', 'u32', 'timemarker', 'upstream', 'high', 'position (+type in high bits); opens a time marker');
d(149, 'InsertColor', 'color', 'insert', 'upstream', 'high');
d(150, 'PatternColor', 'color', 'pattern', 'upstream', 'high');
d(152, 'SongLoopPos', 'u32', 'arrangement', 'upstream', 'med');
d(153, 'AuSampleRate', 'u32', 'channel', 'upstream', 'med');
d(154, 'InsertInput', 'i32', 'insert', 'upstream', 'med');
d(155, 'PluginIcon', 'u32', 'plugin', 'upstream', 'high');
d(156, 'Tempo', 'u32', 'project', 'upstream', 'high', 'BPM*1000');
d(157, 'PatternDword157', 'u32', 'pattern', 'observed', 'low', '0xFFFFFFFF when unset');
d(158, 'PatternDword158', 'u32', 'pattern', 'observed', 'low', '0xFFFFFFFF when unset');
d(159, 'FlBuild', 'u32', 'project', 'upstream', 'high');
d(160, 'PatternChannelIid', 'u32', 'pattern', 'upstream', 'med');
d(161, 'PatternDword161', 'i32', 'pattern', 'upstream', 'low');
d(162, 'PatternDword162', 'u32', 'pattern', 'upstream', 'low');
d(164, 'PatternLength', 'u32', 'pattern', 'upstream', 'high');
d(165, 'InsertDword165', 'u32', 'insert', 'observed', 'low');
d(166, 'InsertDword166', 'u32', 'insert', 'observed', 'low');
d(167, 'ProjectDword167', 'u32', 'project', 'observed', 'low');
d(168, 'TimeMarkerDword168', 'u32', 'timemarker', 'observed', 'low');
d(169, 'ProjectDword169', 'u32', 'project', 'observed', 'low', 'value 7 in 25.x projects');
d(170, 'ChannelDword170', 'u32', 'channel', 'observed', 'low', '0xFFFFFFFF when unset');
d(171, 'PatternDword171', 'u32', 'pattern', 'observed', 'low');

// ---- TEXT (192..207) / DATA (208..255) ----
d(192, 'ChannelNameLegacy', 'wstr', 'channel', 'upstream', 'med');
d(193, 'PatternName', 'wstr', 'pattern', 'upstream', 'high');
d(194, 'ProjectTitle', 'wstr', 'project', 'upstream', 'high');
d(195, 'ProjectComments', 'wstr', 'project', 'upstream', 'high');
d(196, 'SamplePath', 'wstr', 'channel', 'upstream', 'high', 'may start with %FLStudioFactoryData%');
d(197, 'ProjectUrl', 'wstr', 'project', 'upstream', 'high');
d(198, 'CommentsRtf', 'astr', 'project', 'upstream', 'med', 'legacy RTF');
d(199, 'FlVersion', 'astr', 'project', 'upstream', 'high', 'ASCII "major.minor.patch.build"');
d(200, 'Licensee', 'blob', 'project', 'upstream', 'med', 'XOR-scrambled (FLEngine 0xa9ece0), 36B in all samples');
d(201, 'PluginInternalName', 'wstr', 'plugin', 'upstream', 'high');
d(202, 'ProjectDataPath', 'wstr', 'project', 'upstream', 'high');
d(203, 'PluginName', 'wstr', 'plugin', 'upstream', 'high');
d(204, 'InsertName', 'wstr', 'insert', 'upstream', 'high');
d(205, 'TimeMarkerName', 'wstr', 'timemarker', 'upstream', 'high');
d(206, 'ProjectGenre', 'wstr', 'project', 'upstream', 'high');
d(207, 'ProjectArtists', 'wstr', 'project', 'upstream', 'high');
d(208, 'Data208', 'blob', 'any', 'observed', 'low', 'single sample (251B)');
d(209, 'ChannelDelay', 'blob', 'channel', 'upstream', 'high', '20B = 5*u32');
d(210, 'Data210', 'blob', 'any', 'observed', 'low', 'FST only (132/140B)');
d(212, 'PluginWrapper', 'blob', 'plugin', 'upstream', 'high', '52B; flags u16@16, page u8@20, w/h u32@44/48');
d(213, 'PluginData', 'blob', 'plugin', 'upstream', 'high', 'native state or VST/CLAP chunk list');
d(215, 'ChannelParameters', 'blob', 'channel', 'upstream', 'high');
d(216, 'ProjectData216', 'blob', 'project', 'observed', 'low', 'multiples of 12B (rack layout?)');
d(217, 'PlaylistSelection', 'blob', 'project', 'upstream', 'med', '8B');
d(218, 'EnvelopeLfo', 'blob', 'channel', 'upstream', 'high', '68B (56B older); 5 per channel');
d(219, 'ChannelLevels', 'blob', 'channel', 'upstream', 'high', '24B (12B older)');
d(220, 'Data220', 'blob', 'any', 'observed', 'low', 'FST only (12B)');
d(221, 'ChannelPolyphony', 'blob', 'channel', 'upstream', 'high', '9B');
d(223, 'PatternControllers', 'rec', 'pattern', 'upstream', 'high', '12B records', 12);
d(224, 'PatternNotes', 'rec', 'pattern', 'upstream', 'high', '24B records', 24);
d(225, 'MixerParams', 'rec', 'mixer', 'upstream', 'high', '12B records', 12);
d(226, 'MidiController', 'blob', 'project', 'upstream', 'high', '20B');
d(227, 'RemoteController', 'blob', 'project', 'upstream', 'high', '20B');
d(228, 'ChannelTracking', 'blob', 'channel', 'upstream', 'high', '16B; 2 per channel');
d(229, 'ChannelLevelAdjusts', 'blob', 'channel', 'upstream', 'high', '20B');
d(230, 'Text230', 'wstr', 'any', 'observed', 'low', 'UTF-16 text, formula-like (e.g. "1-Input*1.6"); engine writes it with the text helper');
d(231, 'DisplayGroupName', 'wstr', 'group', 'upstream', 'high', 'always UTF-16');
d(233, 'PlaylistItems', 'rec', 'playlist', 'upstream', 'high', '32B records', 32);
d(234, 'ChannelAutomation', 'blob', 'channel', 'upstream', 'high');
d(235, 'InsertRouting', 'blob', 'insert', 'upstream', 'high', 'one byte per target insert');
d(236, 'InsertFlags', 'blob', 'insert', 'upstream', 'high', '12B (8B / 5B variants)');
d(237, 'ProjectTimestamp', 'blob', 'project', 'upstream', 'high', '16B = 2*f64 (Delphi TDateTime created, days spent)');
d(238, 'TrackData', 'blob', 'track', 'upstream', 'high', '66-70B in FL21+');
d(239, 'TrackName', 'wstr', 'track', 'upstream', 'high', 'always UTF-16');
d(240, 'MixerGroupText240', 'wstr', 'mixer', 'observed', 'low', 'UTF-16 text near the mixer end ("Instruments", "Drums", "Bass", "Sidechain", "SFX"); likely insert group names');
d(241, 'ArrangementName', 'wstr', 'arrangement', 'upstream', 'high', 'always UTF-16');
d(242, 'MixerData242', 'blob', 'mixer', 'observed', 'low', '28B prelude');
d(243, 'MixerData243', 'blob', 'mixer', 'observed', 'low', '8B');
d(251, 'Data251', 'blob', 'channel', 'observed', 'low', '43B');
d(252, 'PatternText252', 'wstr', 'pattern', 'observed', 'low', 'UTF-16 text, empty (2B) in all samples');
d(253, 'PatternText253', 'wstr', 'pattern', 'observed', 'low', 'UTF-16 text "0,0,0,..." (48B)');

// Extended ids (0xAC escape, FL 25.2+). Only ids observed in the corpus or written by FLEngine.
d(0x100, 'ExtByte100', 'u8', 'project', 'observed', 'low', 'FL 25.2+ extended id; written after 0xC0000100');
d(0xc0000100, 'ExtText100', 'wstr', 'project', 'observed', 'low', 'written after ProjectUrl when the engine has a value (not in corpus)');
d(0xc0000101, 'FlStudioVersionText', 'wstr', 'project', 'observed', 'med', '"FL Studio <ver>.<build>"; first event after Licensed(28)');
d(0xc0000102, 'ExtText102', 'wstr', 'channel', 'observed', 'low', 'written by FLEngine after channel flags (not in corpus)');

export const EVENT_DEFS: ReadonlyMap<number, EventDef> = new Map(defs.map((x) => [x.id, x]));

export function defOf(id: number): EventDef | undefined {
  return EVENT_DEFS.get(id);
}

export function eventName(id: number): string {
  const e = EVENT_DEFS.get(id);
  if (e) return e.name;
  if (id > 255) return `Ext_0x${id.toString(16)}`;
  return `Unk${id}`;
}

export function isUpstreamKnown(id: number): boolean {
  return UPSTREAM_IDS.has(id);
}
export function isEngineWritten(id: number): boolean {
  return ENGINE_WRITTEN_IDS.has(id);
}

/** documentation status used for the unknown-event census */
export function docStatus(id: number): 'named-upstream' | 'named-observed' | 'undocumented' {
  const e = EVENT_DEFS.get(id);
  if (UPSTREAM_IDS.has(id) && e && e.src !== 'observed') return 'named-upstream';
  if (e && e.conf !== 'low') return 'named-observed';
  return 'undocumented';
}
