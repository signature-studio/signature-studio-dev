import type { DirEntry, FileEntry, FileStat, Manifest } from './types.ts';
import { CODEC_EXT } from './types.ts';

export interface FileRef {
  name: string;
  size: number;
  first: number;
  off: number;
  stub: boolean;
}

const isFile = (n: DirEntry | FileEntry): n is FileEntry => Array.isArray(n);

/** manifest の読取専用 index (大小無視 lookup)。ツリーは遅延で lowercase index を作る。 */
export class ManifestIndex {
  readonly m: Manifest;
  private lc = new WeakMap<DirEntry, Map<string, string>>();
  constructor(m: Manifest) {
    if (m.v !== 1) throw new Error('unsupported manifest version ' + m.v);
    this.m = m;
  }

  get chunkSize(): number {
    return this.m.chunkSize;
  }
  get chunkCount(): number {
    return this.m.chunks.n;
  }
  chunkId(i: number): string {
    return this.m.chunks.id.substr(i * 32, 32);
  }
  chunkUsize(i: number): number {
    return this.m.chunks.u[i];
  }
  chunkCsize(i: number): number {
    return this.m.chunks.c[i];
  }
  chunkCodec(i: number): number {
    return this.m.chunks.k[i];
  }
  /** 配信オブジェクトの相対キー */
  chunkKey(i: number): string {
    const id = this.chunkId(i);
    return `c/${id.slice(0, 2)}/${id}.${CODEC_EXT[this.chunkCodec(i)]}`;
  }
  groupChunks(name: string): number[] {
    const out: number[] = [];
    for (const [s, n] of this.m.groups[name] ?? []) for (let i = 0; i < n; i++) out.push(s + i);
    return out;
  }

  private child(d: DirEntry, name: string): { key: string; node: DirEntry | FileEntry } | null {
    const n = d[name];
    if (n !== undefined) return { key: name, node: n };
    let map = this.lc.get(d);
    if (!map) {
      map = new Map();
      for (const k of Object.keys(d)) map.set(k.toLowerCase(), k);
      this.lc.set(d, map);
    }
    const k = map.get(name.toLowerCase());
    return k === undefined ? null : { key: k, node: d[k] };
  }

  private walk(path: string): { key: string; node: DirEntry | FileEntry } | null {
    if (path === '') return { key: '', node: this.m.tree };
    let cur: DirEntry | FileEntry = this.m.tree;
    let key = '';
    for (const part of path.split('/')) {
      if (isFile(cur)) return null;
      const c = this.child(cur, part);
      if (!c) return null;
      cur = c.node;
      key = c.key;
    }
    return { key, node: cur };
  }

  stat(path: string): FileStat | null {
    const r = this.walk(path);
    if (!r) return null;
    if (isFile(r.node)) return { type: 'file', size: r.node[0], name: r.key, stub: !!((r.node[3] ?? 0) & 1) };
    return { type: 'dir', size: 0, name: r.key, stub: false };
  }

  readdir(path: string): FileStat[] | null {
    const r = this.walk(path);
    if (!r || isFile(r.node)) return null;
    const out: FileStat[] = [];
    for (const [name, n] of Object.entries(r.node)) {
      out.push(isFile(n) ? { type: 'file', size: n[0], name, stub: !!((n[3] ?? 0) & 1) } : { type: 'dir', size: 0, name, stub: false });
    }
    return out;
  }

  file(path: string): FileRef | null {
    const r = this.walk(path);
    if (!r || !isFile(r.node)) return null;
    const [size, first, off, flags] = r.node;
    return { name: r.key, size, first: first ?? -1, off: off ?? -1, stub: !!((flags ?? 0) & 1) };
  }

  /** ファイルが占める chunk index 列 (小ファイルは 1 個) */
  fileChunks(f: FileRef): number[] {
    if (f.size === 0 || f.stub) return [];
    if (f.off >= 0) return [f.first];
    const n = Math.ceil(f.size / this.m.chunkSize);
    return Array.from({ length: n }, (_, i) => f.first + i);
  }

  /** 前方一致で配下の全ファイル (path, ref) を列挙 */
  *walkFiles(path = ''): Generator<[string, FileRef]> {
    const r = this.walk(path);
    if (!r) return;
    if (isFile(r.node)) {
      yield [path, this.file(path)!];
      return;
    }
    const rec = function* (self: ManifestIndex, d: DirEntry, prefix: string): Generator<[string, FileRef]> {
      for (const [name, n] of Object.entries(d)) {
        const p = prefix ? prefix + '/' + name : name;
        if (isFile(n)) {
          const [size, first, off, flags] = n;
          yield [p, { name, size, first: first ?? -1, off: off ?? -1, stub: !!((flags ?? 0) & 1) }];
        } else yield* rec(self, n, p);
      }
    };
    yield* rec(this, r.node, path);
  }
}
