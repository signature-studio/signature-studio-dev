/**
 * FL audio shim — 入力デバイス管理 (main thread)。
 *
 * ASIO/WASAPI の入力 (FL の "Input" 設定) をブラウザの getUserMedia に対応づける:
 *   - 権限の状態取得 / 要求 (ユーザジェスチャ内で requestPermission を呼ぶ)
 *   - audioinput デバイス列挙 (権限が無い間は label が空)
 *   - 選択 (deviceId, null = ブラウザ既定) と、動作中のライブ切替
 *   - MediaStreamSource → FlAudioShim の worklet node 接続 (FlAudioShimOptions.input)
 *   - 使用中デバイスの喪失 (track ended / 選択 deviceId の消失) の通知 → shim が kAsioResetRequest を発行
 * 設計: tools/audio/docs/PROTOCOL.md
 */

export interface FlInputDevice { deviceId: string; label: string; groupId: string }
export type FlInputPermission = "granted" | "denied" | "prompt" | "unsupported";
export type FlInputEvent =
  | { type: "devices"; devices: FlInputDevice[] }
  | { type: "selected"; deviceId: string | null; label: string }
  | { type: "permission"; state: FlInputPermission }
  | { type: "lost"; reason: string }
  | { type: "error"; message: string };

export interface FlAudioInputOptions {
  mediaDevices?: MediaDevices;
  /** 選択 deviceId の永続化先 (既定: localStorage があれば使う) */
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
  storageKey?: string;
  log?: (msg: string) => void;
}

const BASE_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 2,
};

export class FlAudioInput {
  private md: MediaDevices | undefined;
  private storage: FlAudioInputOptions["storage"];
  private key: string;
  private listeners = new Set<(e: FlInputEvent) => void>();
  private selected: string | null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private target: { ctx: AudioContext; node: AudioNode } | null = null;
  private permStatus: PermissionStatus | null = null;
  private disposed = false;
  private onDeviceChange = () => { void this.handleDeviceChange(); };

  constructor(private opts: FlAudioInputOptions = {}) {
    this.md = opts.mediaDevices ?? (typeof navigator !== "undefined" ? navigator.mediaDevices : undefined);
    this.storage = opts.storage !== undefined ? opts.storage : (typeof localStorage !== "undefined" ? localStorage : null);
    this.key = opts.storageKey ?? "fl-audio-input-device";
    let saved: string | null = null;
    try { saved = this.storage?.getItem(this.key) ?? null; } catch { /* storage 不可 */ }
    this.selected = saved || null;
    this.md?.addEventListener?.("devicechange", this.onDeviceChange);
  }

  private log(m: string) { this.opts.log?.(`[audio-input] ${m}`); }
  private emit(e: FlInputEvent) { for (const l of [...this.listeners]) l(e); }

  /** イベント購読。戻り値で解除 */
  on(cb: (e: FlInputEvent) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  get supported(): boolean { return !!this.md?.getUserMedia; }
  get selectedId(): string | null { return this.selected; }
  get connected(): boolean { return !!this.stream; }
  get activeTrack(): MediaStreamTrack | null { return this.stream?.getAudioTracks()[0] ?? null; }

  async permission(): Promise<FlInputPermission> {
    if (!this.supported) return "unsupported";
    try {
      const st = await navigator.permissions.query({ name: "microphone" as PermissionName });
      if (this.permStatus !== st) {
        this.permStatus = st;
        st.onchange = () => this.emit({ type: "permission", state: st.state as FlInputPermission });
      }
      return st.state as FlInputPermission;
    } catch {
      return "prompt"; // Permissions API の microphone 未対応 (Safari 等): 要求してみるまで不明
    }
  }

  /** getUserMedia を 1 度呼んでブラウザの権限ダイアログを出す。ユーザジェスチャ内から呼ぶこと */
  async requestPermission(): Promise<FlInputPermission> {
    if (!this.supported) return "unsupported";
    try {
      const s = await this.md!.getUserMedia({ audio: true });
      for (const t of s.getTracks()) t.stop();
    } catch (e) {
      const name = (e as DOMException).name;
      this.log(`permission request failed: ${name}`);
      const state: FlInputPermission = name === "NotAllowedError" || name === "SecurityError" ? "denied" : await this.permission();
      this.emit({ type: "permission", state });
      return state;
    }
    this.emit({ type: "permission", state: "granted" });
    await this.listDevices();
    return "granted";
  }

  async listDevices(): Promise<FlInputDevice[]> {
    if (!this.md?.enumerateDevices) return [];
    const all = await this.md.enumerateDevices();
    const devices = all.filter((d) => d.kind === "audioinput")
      .map((d) => ({ deviceId: d.deviceId, label: d.label, groupId: d.groupId }));
    this.emit({ type: "devices", devices });
    return devices;
  }

  /**
   * デバイスを選ぶ (null = 既定)。接続中ならライブで切り替える (チャンネル数差は node の speakers 変換が吸収)。
   * 切替に失敗したら旧デバイスは稼働したまま選択と保存値を元に戻し、error を emit して reject する (selected は emit しない)。
   */
  async select(deviceId: string | null): Promise<void> {
    const prev = this.selected;
    this.selected = deviceId || null;
    if (this.target) {
      try { await this.open(); } catch (e) { this.selected = prev; throw e; }
    }
    try {
      if (this.selected) this.storage?.setItem(this.key, this.selected); else this.storage?.removeItem(this.key);
    } catch { /* storage 不可 */ }
    this.emit({ type: "selected", deviceId: this.selected, label: this.activeTrack?.label ?? "" });
  }

  /** worklet node の入力へ MediaStreamSource を接続する (OPEN 毎に ATTACH から呼ばれる) */
  async connect(ctx: AudioContext, node: AudioNode): Promise<void> {
    this.release();
    this.target = { ctx, node };
    await this.open();
  }

  disconnect(): void {
    this.release();
    this.target = null;
  }

  dispose(): void {
    this.disposed = true;
    this.disconnect();
    this.md?.removeEventListener?.("devicechange", this.onDeviceChange);
    if (this.permStatus) this.permStatus.onchange = null;
    this.listeners.clear();
  }

  private release(): void {
    this.source?.disconnect();
    this.source = null;
    const tr = this.activeTrack;
    if (tr) tr.onended = null;
    for (const t of this.stream?.getTracks() ?? []) t.stop();
    this.stream = null;
  }

  private async getStream(): Promise<MediaStream> {
    const md = this.md;
    if (!md?.getUserMedia) throw new Error("getUserMedia unsupported");
    if (this.selected) {
      try {
        return await md.getUserMedia({ audio: { ...BASE_CONSTRAINTS, deviceId: { exact: this.selected } } });
      } catch (e) {
        const name = (e as DOMException).name;
        if (name !== "OverconstrainedError" && name !== "NotFoundError") throw e;
        this.log(`selected device ${this.selected} is gone (${name}); falling back to default`);
        this.selected = null;
        try { this.storage?.removeItem(this.key); } catch { /* storage 不可 */ }
      }
    }
    return md.getUserMedia({ audio: BASE_CONSTRAINTS });
  }

  private async open(): Promise<void> {
    const target = this.target;
    if (!target) return;
    let stream: MediaStream;
    try {
      stream = await this.getStream();
    } catch (e) {
      const name = (e as DOMException).name ?? "Error";
      this.log(`getUserMedia failed: ${name}`);
      this.emit({ type: "error", message: name });
      if (name === "NotAllowedError") this.emit({ type: "permission", state: "denied" });
      throw e;
    }
    if (this.disposed || this.target !== target) { for (const t of stream.getTracks()) t.stop(); return; }
    this.release();
    this.stream = stream;
    const track = stream.getAudioTracks()[0];
    track.onended = () => this.lost("track ended");
    this.source = target.ctx.createMediaStreamSource(stream);
    this.source.connect(target.node);
    const s = track.getSettings();
    this.log(`input open: "${track.label}" ch=${s.channelCount} sr=${s.sampleRate}`);
    await this.listDevices();   // 権限取得後は label が埋まる
  }

  private lost(reason: string): void {
    this.log(`input lost: ${reason}`);
    this.release();
    this.emit({ type: "lost", reason });
  }

  private async handleDeviceChange(): Promise<void> {
    const devices = await this.listDevices();
    if (!this.stream || !this.selected) return;
    const labelled = devices.some((d) => d.label);
    if (labelled && !devices.some((d) => d.deviceId === this.selected)) this.lost("selected device removed");
  }
}
