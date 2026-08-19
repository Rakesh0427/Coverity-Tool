import re, os
text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_xsd2.xml"), encoding="utf-8").read()
out = []
def show(name):
    m = re.search(r'<xs:complexType name="' + name + r'".*?</xs:complexType>', text, re.S)
    out.append(f"### {name}:")
    out.append(m.group(0) if m else "NOT FOUND")
    out.append("")
for name in ["getStreamDefectsResponse", "defectInstanceDataObj", "fileIdDataObj",
             "streamDefectsPageDataObj", "getMergedDefectsForStreamsResponse"]:
    show(name)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_xsd2_diag.txt"), "w").write("\n".join(out))
print("WROTE _xsd2_diag.txt")

