// Ghidra headless postScript: 全関数の address/size/名前を CSV に出力する。
// 使い方: analyzeHeadless <proj> <name> -import <file> -scriptPath tools/m2/ghidra_scripts
//         -postScript DumpFunctions.java <out.csv>
// 関数境界合意検証 (M2-2) 用。program 開始アドレスベースを含めて exit code 0 で終了。
//@category Analysis

import java.io.BufferedWriter;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

public class DumpFunctions extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = (args.length > 0) ? args[0] : "functions.csv";

        List<String[]> rows = new ArrayList<>();
        rows.add(new String[] { "name", "entry", "size" });

        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        while (it.hasNext()) {
            Function f = it.next();
            Address e = f.getEntryPoint();
            long size = f.getBody().getNumAddresses();
            rows.add(new String[] { f.getName(), e.toString(true), Long.toString(size) });
        }

        try (BufferedWriter bw = new BufferedWriter(new FileWriter(outPath))) {
            for (String[] r : rows) {
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < r.length; i++) {
                    if (i > 0) {
                        sb.append(',');
                    }
                    sb.append('"').append(r[i].replace("\"", "\"\"")).append('"');
                }
                bw.write(sb.toString());
                bw.write("\n");
            }
        }

        println("DumpFunctions: " + (rows.size() - 1) + " functions -> " + outPath);
        println("image base: " + currentProgram.getImageBase());
    }
}
