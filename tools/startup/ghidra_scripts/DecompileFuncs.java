// Ghidra headless postScript: 指定アドレス群 (16進, カンマ区切り or ファイル) の関数を decompile して出力。
// args: <out.c> <addr1,addr2,...|@file>   (アドレスは image-base 込み VA)
// 関数が無ければその位置で createFunction を試みる。
//@category Analysis
import java.io.*;
import java.nio.file.*;
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DecompileFuncs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        String out = a[0];
        List<String> addrs = new ArrayList<>();
        if (a[1].startsWith("@")) {
            for (String l : Files.readAllLines(Paths.get(a[1].substring(1)))) { l = l.trim(); if (!l.isEmpty() && !l.startsWith("#")) addrs.add(l.split("\\s+")[0]); }
        } else addrs.addAll(Arrays.asList(a[1].split(",")));
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        int timeout = a.length > 2 ? Integer.parseInt(a[2]) : 120;
        try (PrintWriter pw = new PrintWriter(new FileWriter(out))) {
            for (String s : addrs) {
                Address ad = toAddr(Long.parseUnsignedLong(s.replace("0x",""), 16));
                Function f = getFunctionAt(ad);
                if (f == null) { f = getFunctionContaining(ad); }
                if (f == null) { disassemble(ad); f = createFunction(ad, null); }
                pw.println("//==== " + s + " " + (f == null ? "NOFUNC" : f.getName() + " entry=" + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses()));
                if (f == null) continue;
                DecompileResults r = di.decompileFunction(f, timeout, monitor);
                if (r.decompileCompleted()) pw.println(r.getDecompiledFunction().getC());
                else pw.println("// decompile failed: " + r.getErrorMessage());
            }
        }
        println("DecompileFuncs: wrote " + out);
    }
}
