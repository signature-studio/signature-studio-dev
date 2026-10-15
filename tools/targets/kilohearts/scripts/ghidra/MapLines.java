// Ghidra headless postScript: 関数ごとに、C 行 → (トークン, そのトークンの PC 命令) を TSV で出す。
// 使い方: analyzeHeadless ... -postScript MapLines.java <outdir> <va> [<va> ...]
//@category Analysis

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;

import ghidra.app.decompiler.ClangBreak;
import ghidra.app.decompiler.ClangNode;
import ghidra.app.decompiler.ClangToken;
import ghidra.app.decompiler.ClangVariableToken;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class MapLines extends GhidraScript {
    private BufferedWriter out;
    private int line;
    private String fname;
    private String prev = "";

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        File dir = new File(args[0]);
        dir.mkdirs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        out = new BufferedWriter(new FileWriter(new File(dir, "tokens.tsv")));
        out.write("func\tline\ttoken\tpcode\ttoken_va\tinsn\tprev\n");
        for (int i = 1; i < args.length; i++) {
            Address a = toAddr(Long.decode(args[i]));
            Function f = getFunctionContaining(a);
            if (f == null) continue;
            fname = f.getName();
            line = 1;
            new ghidra.app.cmd.disassemble.DisassembleCommand(f.getBody(), null, true).applyTo(currentProgram);
            DecompileResults res = di.decompileFunction(f, 120, monitor);
            if (res == null || res.getCCodeMarkup() == null) continue;
            walk(res.getCCodeMarkup());
        }
        out.close();
    }

    private void walk(ClangNode n) throws Exception {
        if (n instanceof ClangBreak) {
            line++;
            return;
        }
        if (n instanceof ClangToken) {
            ClangToken t = (ClangToken) n;
            String txt = t.getText();
            String before = prev;
            prev = txt;
            if (txt.contains("dVar") || txt.contains("dStack")) {
                String op = "-";
                String tva = "-";
                String insn = "-";
                if (t instanceof ClangVariableToken) {
                    PcodeOp p = ((ClangVariableToken) t).getPcodeOp();
                    if (p != null) {
                        op = p.getMnemonic();
                        Address pc = p.getSeqnum().getTarget();
                        tva = pc.toString();
                        Instruction in = getInstructionAt(pc);
                        if (in != null) insn = in.toString();
                    }
                }
                out.write(fname + "\t" + line + "\t" + txt + "\t" + op + "\t" + tva + "\t" + insn + "\t" + before + "\n");
            }
            return;
        }
        for (int i = 0; i < n.numChildren(); i++) {
            walk(n.Child(i));
        }
    }
}
