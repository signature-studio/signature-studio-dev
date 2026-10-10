// Ghidra headless postScript: 指定アドレス群に関数を作成し decompile 結果 (C) と関数 body size を出力する。
// 範囲限定 Ghidra 解析 (full analysis を回さない) 用:  -noanalysis で import 後、本 script のみ実行。
// 使い方: analyzeHeadless <proj> <name> -import <PE> -noanalysis -scriptPath <dir> \
//           -postScript DecompAt.java <out.txt> 0x1804b0380 [0x... ...]
//@category Analysis

import java.io.BufferedWriter;
import java.io.FileWriter;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;

public class DecompAt extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        try (BufferedWriter bw = new BufferedWriter(new FileWriter(outPath))) {
            bw.write("// image base " + currentProgram.getImageBase() + "\n");
            for (int i = 1; i < args.length; i++) {
                Address a = toAddr(Long.decode(args[i]));
                new DisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
                Function f = getFunctionAt(a);
                if (f == null) f = createFunction(a, null);
                if (f == null) { bw.write("// FAIL createFunction " + a + "\n"); continue; }
                DecompileResults r = di.decompileFunction(f, 120, monitor);
                bw.write("// ==== " + f.getName() + " @ " + a + " body=" + f.getBody().getNumAddresses() + " ====\n");
                if (r.decompileCompleted()) bw.write(r.getDecompiledFunction().getC() + "\n");
                else bw.write("// decompile failed: " + r.getErrorMessage() + "\n");
            }
        }
    }
}
