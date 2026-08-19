import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coverity_soap_client as sc
from coverity_soap_client import CoveritySOAPClient

out = []

def MD(cid, chk, file, func, dt, impact):
    return types.SimpleNamespace(cid=cid, checkerName=chk, filePathname=file,
        functionDisplayName=func, displayType=dt, displayImpact=impact,
        lineNumber=None, checkerSubcategory=dt)

def EV(n, tag, desc, line, file=None, main=False):
    fid = types.SimpleNamespace(filePathname=file) if file else None
    return types.SimpleNamespace(eventNumber=n, eventTag=tag,
        eventDescription=desc, lineNumber=line, main=main, fileId=fid, events=[])

def INST(evs):
    return types.SimpleNamespace(events=evs)

def SD(cid, instances):
    return types.SimpleNamespace(cid=cid, defectInstances=instances)

class FakeClient:
    def __init__(self, svc):
        self.service = svc
    class Svc:
        def __init__(self, events_by_cid):
            self.events_by_cid = events_by_cid
            self.with_filter = False
        def getStreamDefects(self, mergedDefectIdDataObjs=None, streamId=None, filterSpec=None):
            if filterSpec is not None:
                self.with_filter = True
            return [SD(cid, INST(evs)) for cid, evs in self.events_by_cid.items()
                    if cid in [m["cid"] for m in mergedDefectIdDataObjs]]

def client_with(svc, defects):
    c = CoveritySOAPClient("h","443","u","p")
    c._get_defect_client = lambda: FakeClient(svc)
    c._parse_defect_result = lambda r: ([MD(d["cid"], d["checker"], d["file"],
        d["function"], d["type"], d["severity"]) for d in (r if isinstance(r, list) else [])] or None)
    c.get_defects_for_stream = lambda *a, **k: (defects, None)
    return c

# Events with main + fileId + nesting
events_by_cid = {
    10: [EV(1,"overrun_static","start",40,"a.c"),
         EV(2,"constant","bad index",42,"a.c", main=True)],
    11: [EV(1,"null_returns","deref",0,"")],
    12: [EV(1,"group", "parent",5,"x.c")],
}
evs_10 = events_by_cid[10]
evs_10[1].events = [EV(3,"child","nested",45,"a.c")]  # nest under main event
events_by_cid[12][0].events = [EV(2,"child","sub",6,"x.c")]

svc = FakeClient.Svc(events_by_cid)
defects = [
    MD(10,"BUFFER_SIZE","a.c","foo","Improper use","High"),
    MD(11,"NULL_RETURNS","b.cpp","bar","Deref null","Medium"),
    MD(12,"USE_AFTER_FREE","x.c","baz","UAF","Low"),
]
c = client_with(svc, defects)
emap = c.get_defect_events([10,11,12], "S")
out.append("with_filterSpec_used=%s" % svc.with_filter)
out.append("events10=%r" % emap.get(10))
out.append("events11=%r" % emap.get(11))
out.append("events12=%r" % emap.get(12))

# get_defects_with_events line derivation (merged line from main/last event)
c.get_defect_events = lambda cids, st: emap
defects2 = [
    {"cid":10,"checker":"BUFFER_SIZE","file":"a.c","function":"foo","type":"x","severity":"High","line":0},
    {"cid":11,"checker":"NULL_RETURNS","file":"b.cpp","function":"bar","type":"x","severity":"Med","line":0},
    {"cid":12,"checker":"USE_AFTER_FREE","file":"x.c","function":"baz","type":"x","severity":"Low","line":0},
]
c.get_defects_for_stream = lambda *a, **k: (defects2, None)
d_all, err = c.get_defects_with_events("S")
out.append("err=%r" % (err,))
for dd in d_all:
    out.append("  cid=%s line=%s files=%s n_events=%s" % (
        dd["cid"], dd["line"], sorted({e["file"] for e in dd["events"]}), len(dd["events"])))

# _parse_defect_result unwrapping: object with .return
class Wrap:
    def __init__(self, lst):
        self.return = types.SimpleNamespace(mergedDefects=lst)
c2 = CoveritySOAPClient("h","443","u","p")
parsed = c2._parse_defect_result(Wrap([MD(99,"CHK","f.c","fn","t","High")]))
out.append("parse_return_wrapped: %r" % (parsed,))

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ev_diag.txt"), "w").write("\n".join(out))
print("WROTE _ev_diag.txt")