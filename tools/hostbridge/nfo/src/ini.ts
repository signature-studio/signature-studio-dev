// `Installed\.Plugins.ini` — FL's INI cache of every plugin entry (writer fle:0x912d10, reader fle:0x911e10 via TMemIniFile).
// Real-machine facts (CAB-219, FL Studio 26.1.7 win64): UTF-8 **with BOM**, CRLF, one `[section]` per plugin entry,
// section name = the nfo path relative to `Installed\` without extension, section body = the same `ps_*` lines the
// .nfo writer emits (FUN_00912d10 reuses FUN_00913f40 / the FUN_00911940 header block), and **one blank line after
// every section including the last**. Browser-safe (no Node APIs).

export interface IniSection {
  /** section name as written between `[` and `]` (e.g. `Effects\VST3\Serum 2 FX`) */
  name: string;
  /** raw `key=value` lines in file order (duplicates kept — FL looks keys up case-insensitively, first match wins) */
  lines: string[];
}

export class IniFile {
  sections: IniSection[] = [];

  static parse(text: string): IniFile {
    const ini = new IniFile();
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    for (const line of text.split(/\r\n|\n|\r/)) {
      if (line === '') continue; // separators (one blank line after each section)
      if (line.startsWith('[') && line.endsWith(']')) ini.sections.push({ name: line.slice(1, -1), lines: [] });
      else if (ini.sections.length) ini.sections[ini.sections.length - 1].lines.push(line);
      // lines before the first `[section]` do not exist in FL's writer output and are dropped
    }
    return ini;
  }

  static fromBytes(b: Uint8Array): IniFile {
    return IniFile.parse(new TextDecoder('utf-8').decode(b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf ? b.subarray(3) : b));
  }

  /** Canonical TMemIniFile layout: every line (headers, keys and the blank separator) terminated by CRLF,
   *  one blank line after each section including the last. Reproduces the real .Plugins.ini byte-for-byte. */
  toString(): string {
    let s = '';
    for (const sec of this.sections) {
      s += `[${sec.name}]\r\n`;
      for (const l of sec.lines) s += l + '\r\n';
      s += '\r\n';
    }
    return s;
  }

  /** UTF-8 with BOM (the real file carries EF BB BF even though its content is pure ASCII). */
  toBytes(): Uint8Array {
    const body = new TextEncoder().encode(this.toString());
    const out = new Uint8Array(body.length + 3);
    out.set([0xef, 0xbb, 0xbf], 0);
    out.set(body, 3);
    return out;
  }

  get(name: string): IniSection | undefined {
    const n = name.toUpperCase();
    return this.sections.find((s) => s.name.toUpperCase() === n);
  }
}

/** `Installed/Effects/VST3/Serum 2 FX.nfo` → section name `Effects\VST3\Serum 2 FX` (fle:0x912d10 uses the nfo/fst
 *  path relative to `Installed\` without extension; real sections match this for 406/406). */
export function iniSectionName(nfoRel: string): string {
  return nfoRel.replace(/^Installed\//, '').replace(/\.(nfo|NFO)$/, '').replace(/\//g, '\\');
}
