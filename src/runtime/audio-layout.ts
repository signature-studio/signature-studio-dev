/**
 * fla_ctl_t (tools/audio/src/flaudio.h) のバイトオフセット表。
 * 単一の真実は C ヘッダ。この表は (1) TS 側の型付きアクセス (2) 実行時自己検証
 * (verifyLayout が wasm の fla_layout_off() と照合し、不一致なら fail-fast) のために持つ。
 */
export const FLA_ABI = 1;
export const FLA_CTL_SIZE = 4488;
export const FLA_QUANTUM = 128;
/** producer の write 記録リングの件数 (flaudio.h FLA_PW_N) */
export const FLA_PW_N = 256;

export const FLA_LAYOUT = {
  magic: 0, state: 8, sample_rate: 16, out_ch: 20, in_ch: 24, ring_frames: 28, ring_mask: 32,
  buffer_frames: 36, depth: 40, rebuffer_frames: 44, out_ring_ptr: 48, in_ring_ptr: 52, flags: 56,
  dev_events: 60, dev_frames: 64, dev_ctx_time_bits: 72, out_read: 80, in_write: 84, underruns: 88,
  silence_frames: 92, quanta: 96, in_overruns: 100, wl_state: 104, clock_seq: 108, play_start_frame: 112, clock_jumps: 120, clock_jump_frames: 124,
  out_write: 128, in_read: 132, wake_target: 136, gen: 140, go: 144, in_wake_target: 148, tick_target: 152, notify_ms: 156, burst_obs: 160,
  clock_skip_frames: 164, clock_dup_frames: 168, clock_jump_max: 172, clock_jump_max_q: 176,
  clock_first_q: 180, clock_last_q: 184, cb_max_q: 188,
  ref_ctx_time_bits: 192, ref_epoch_ms_bits: 200, ref_seq: 208, out_latency_us: 212, base_latency_us: 216,
  cmd_seq: 256, cmd_op: 260, cmd_arg: 264, ack_seq: 280, ack_status: 284, ack_res: 288, ctrl_ready: 304,
  cb_count: 320, cb_late: 324, cb_max_us: 328, cb_sum_us_lo: 332, wake_count: 336, wait_timeouts: 340,
  in_underflows: 344, min_fill: 348, fill_sum_lo: 352, fill_samples: 356, wake_hist: 360,
  pw_n: 384, pw_trace: 388,
} as const;
export type FlaField = keyof typeof FLA_LAYOUT;

/** コマンド番号 (flaudio.h FLA_CMD_*) */
export const FLA_CMD = { NONE: 0, OPEN: 1, CLOSE: 2, RESUME: 3, SET_SR: 4, MIDI_LIST: 5, INPUT_OPEN: 6, ATTACH: 7, CONTROL_PANEL: 8 } as const;
/** dev_events ビット (flaudio.h FLA_EV_*) */
export const FLA_EV = { SUSPENDED: 1, CLOSED: 2, RATE_CHANGED: 4, RESUMED: 8, INPUT_CHANGED: 16 } as const;

/** wasm 側が報告するレイアウトと TS 表が一致することを検証する。不一致は fail-fast (throw) */
export function verifyLayout(
  count: number,
  offOf: (i: number) => number,
  nameOf: (i: number) => string,
): void {
  const seen = new Set<string>();
  for (let i = 0; i < count; i++) {
    const name = nameOf(i) as FlaField;
    const off = offOf(i);
    const exp = (FLA_LAYOUT as Record<string, number>)[name];
    if (exp === undefined) throw new Error(`[audio-layout] wasm フィールド ${name} が TS 表に無い`);
    if (exp !== off) throw new Error(`[audio-layout] ${name}: wasm=${off} TS=${exp} (不一致)`);
    seen.add(name);
  }
  for (const k of Object.keys(FLA_LAYOUT)) {
    if (!seen.has(k)) throw new Error(`[audio-layout] TS フィールド ${k} が wasm 側に無い`);
  }
}
