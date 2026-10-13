import sys

from pypdf import PdfReader

reader = PdfReader(sys.argv[1])
sys.stdout.write("\n".join((p.extract_text() or "") for p in reader.pages))
