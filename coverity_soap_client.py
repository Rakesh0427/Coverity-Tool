#!/usr/bin/env python3
"""
Coverity Connect SOAP v9 client.
Uses DefectService and ConfigurationService WSDLs exposed by every
Coverity Connect installation at /ws/v9/<service>?wsdl.
"""
import threading
import requests
import urllib3

# Suppress InsecureRequestWarning when SSL verify is disabled for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from zeep import Client, Settings
    from zeep.transports import Transport
    from zeep.wsse.username import UsernameToken
    from zeep.exceptions import Fault
    ZEEP_AVAILABLE = True
except ImportError:
    ZEEP_AVAILABLE = False

WS_VERSION = "v9"

# Maps tool classification strings → Coverity Connect triage store values
CLASSIFICATION_MAP = {
    "Bug":            "Bug",
    "False positive": "False Positive",
    "Intentional":    "Intentional",
    "Needs review":   "Pending",
    "Accepted":       "Bug",
}


def zeep_available():
    return ZEEP_AVAILABLE


def _event_file(ev):
    """Extract the file path from an eventDataObj (lives in fileId.filePathname)."""
    try:
        fid = getattr(ev, "fileId", None)
    except Exception:
        fid = None
    if fid is not None:
        try:
            return str(getattr(fid, "filePathname", "") or "")
        except Exception:
            return ""
    return ""


def _flatten_events(evs):
    """Recursively flatten eventDataObj trees (event sets may nest sub-events)."""
    flat = []
    for ev in evs or []:
        flat.append(ev)
        flat.extend(_flatten_events(getattr(ev, "events", None) or []))
    return flat


def _unwrap_stream_defects(response):
    """
    Normalise the getStreamDefects response into a list of streamDefectDataObj.

    zeep usually unwraps the WSDL 'return' element into a plain list, but some
    versions return a wrapper object with a '.return' / '.streamDefects' list.
    """
    if response is None:
        return []
    if isinstance(response, (list, tuple)):
        return list(response)
    for attr in ("return", "streamDefects", "streamDefectDataObj"):
        val = getattr(response, attr, None)
        if val is not None:
            return list(val) if isinstance(val, (list, tuple)) else [val]
    return [response]


def _line_from_events(events):
    """Derive the defect's main line from its event trace."""
    if not events:
        return 0
    # Prefer the event explicitly marked as the defect's main event.
    for ev in events:
        if ev.get("main"):
            line = ev.get("line", 0)
            if line:
                return line
    # Otherwise use the last event in the trace (highest step number).
    last = max(events, key=lambda e: e.get("step", 0))
    return last.get("line", 0)


class CoveritySOAPClient:
    def __init__(self, host, port, username, password, use_ssl=True, verify_ssl=False):
        self.host       = host.strip()
        self.port       = int(port)
        self.username   = username
        self.password   = password
        self.use_ssl    = use_ssl    # controls http vs https scheme
        self.verify_ssl = verify_ssl # controls certificate validation
        self._defect_client = None
        self._config_client = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _base_url(self):
        scheme = "https" if self.use_ssl else "http"
        return f"{scheme}://{self.host}:{self.port}"

    def _make_session(self):
        session = requests.Session()
        session.verify = self.verify_ssl
        return session

    def _defect_wsdl(self):
        return f"{self._base_url()}/ws/{WS_VERSION}/defectservice?wsdl"

    def _config_wsdl(self):
        return f"{self._base_url()}/ws/{WS_VERSION}/configurationservice?wsdl"

    def _build_client(self, wsdl_url):
        transport = Transport(session=self._make_session(), timeout=30)
        settings  = Settings(strict=False, xml_huge_tree=True)
        return Client(
            wsdl_url,
            wsse=UsernameToken(self.username, self.password),
            transport=transport,
            settings=settings,
        )

    def _get_defect_client(self):
        with self._lock:
            if self._defect_client is None:
                self._defect_client = self._build_client(self._defect_wsdl())
        return self._defect_client

    def _get_config_client(self):
        with self._lock:
            if self._config_client is None:
                self._config_client = self._build_client(self._config_wsdl())
        return self._config_client

    # ------------------------------------------------------------------
    def test_connection(self):
        """
        Returns (True, info_string) on success or (False, error_message).
        Calls getProjects() with a filter that returns no results — fast and safe.
        """
        if not ZEEP_AVAILABLE:
            return False, "zeep library not installed. Run: pip install zeep"
        try:
            client = self._get_config_client()
            result = client.service.getProjects(filterSpec={"namePattern": None})
            count  = len(result) if result else 0
            return True, f"Connected  ({count} project(s) visible)"
        except Fault as e:
            msg = str(e.message) if hasattr(e, "message") else str(e)
            # A "no results" fault still means we authenticated successfully
            if any(k in msg.lower() for k in ("not found", "no project", "0 results")):
                return True, "Connected"
            return False, f"SOAP Fault: {msg}"
        except Exception as e:
            return False, str(e)

    def get_projects(self):
        """Returns list of dicts: {name, triage_store}. Empty list on error."""
        if not ZEEP_AVAILABLE:
            return []
        try:
            client   = self._get_config_client()
            projects = client.service.getProjects(filterSpec={"namePattern": None})
            result   = []
            for p in (projects or []):
                name  = p.id.name if p.id else ""
                store = ""
                # triageStoreId may be nested as .id.name or directly as .name
                ts = getattr(p, "triageStoreId", None)
                if ts:
                    store = getattr(ts, "name", None) or ""
                    if not store:
                        ts_id = getattr(ts, "id", None)
                        store = getattr(ts_id, "name", None) or ""
                if name:
                    result.append({"name": name, "triage_store": store})
            return result
        except Exception:
            return []

    def get_triage_store_for_project(self, project_name):
        """
        Best-effort fetch of the triage store name for a project.
        1. Try getProjects triageStoreId field.
        2. Try getStreamsForProject — each stream object may carry triageStoreId.
        3. Fall back to derived name: <project>-TS.
        """
        if not ZEEP_AVAILABLE:
            return f"{project_name}-TS"
        try:
            client   = self._get_config_client()
            projects = client.service.getProjects(filterSpec={"namePattern": None})
            for p in (projects or []):
                pname = p.id.name if p.id else ""
                if pname != project_name:
                    continue
                ts = getattr(p, "triageStoreId", None)
                if ts:
                    name = getattr(ts, "name", None) or ""
                    if not name:
                        ts_id = getattr(ts, "id", None)
                        name  = getattr(ts_id, "name", None) or ""
                    if name:
                        return name
        except Exception:
            pass
        # Try stream objects — they sometimes carry triageStoreId
        try:
            client  = self._get_config_client()
            streams = client.service.getStreamsForProject(
                projectId={"name": project_name},
                filterSpec={"namePattern": None})
            for s in (streams or []):
                ts = getattr(s, "triageStoreId", None)
                if ts:
                    name = getattr(ts, "name", None) or ""
                    if name:
                        return name
        except Exception:
            pass
        # Derive from naming convention: project name + "-TS"
        return f"{project_name}-TS"

    def get_streams_for_project(self, project_name):
        """Returns list of stream name strings for a given project."""
        if not ZEEP_AVAILABLE:
            return []
        try:
            client  = self._get_config_client()
            proj_id = {"name": project_name}
            streams = client.service.getStreamsForProject(
                projectId=proj_id, filterSpec={"namePattern": None})
            return [s.id.name for s in (streams or []) if s.id and s.id.name]
        except Exception:
            # Fall back to listing all streams if per-project call fails
            return self.get_streams()

    def get_streams(self):
        """Returns list of stream name strings, empty list on error."""
        if not ZEEP_AVAILABLE:
            return []
        try:
            client  = self._get_config_client()
            streams = client.service.getStreams(filterSpec={"namePattern": None})
            return [s.id.name for s in (streams or []) if s.id and s.id.name]
        except Exception:
            return []

    def get_triage_stores(self):
        """Returns list of triage store name strings."""
        if not ZEEP_AVAILABLE:
            return []
        for kwargs in [{}, {"filterSpec": {}}, {"filterSpec": None}]:
            try:
                client = self._get_config_client()
                stores = client.service.getTriageStores(**kwargs)
                names  = [s.id.name for s in (stores or []) if s.id and s.id.name]
                if names:
                    return names
            except Exception:
                continue
        return []

    def get_defects_for_stream(self, stream_name, max_defects=5000):
        """
        Fetch merged defects for a stream.

        Different Coverity Connect servers enforce different pageSpec rules
        (some require pageSize <= 2000/1000/500, some require a sortField, some
        reject a bare call without pageSpec with "Invalid value for parameter
        pageSize"). This tries a matrix of pageSpec shapes x page sizes and
        paginates with the first configuration the server accepts.

        Returns (list_of_dicts, error_string_or_None).
        Each dict: {cid, checker, file, function, line, type, severity}.
        """
        if not ZEEP_AVAILABLE:
            return [], "zeep not installed"

        client   = self._get_defect_client()
        last_err = None

        # pageSpec shapes to try, most standard first.
        shapes = [
            ("standard",         lambda ps, si: {"pageSize": ps,
                                                 "sortAscending": True,
                                                 "startIndex": si}),
            ("with-sortField",   lambda ps, si: {"pageSize": ps,
                                                 "sortAscending": True,
                                                 "sortField": "cid",
                                                 "startIndex": si}),
            ("no-sortAscending", lambda ps, si: {"pageSize": ps,
                                                 "startIndex": si}),
            ("pageSize-only",    lambda ps, si: {"pageSize": ps}),
        ]
        page_sizes = (2000, 1000, 500, 250, 100, 50)

        for label, shape in shapes:
            for page_size in page_sizes:
                collected  = []
                start_index = 0
                page_err   = None
                while start_index < max_defects:
                    try:
                        result = client.service.getMergedDefectsForStreams(
                            streamIds=[{"name": stream_name}],
                            filterSpec={},
                            pageSpec=shape(page_size, start_index),
                        )
                    except Fault as e:
                        msg = str(e.message if hasattr(e, "message") else e)
                        page_err = f"[{label}, pageSize={page_size}, startIndex={start_index}] {msg}"
                        break
                    except Exception as e:
                        page_err = f"[{label}, pageSize={page_size}, startIndex={start_index}] {str(e)}"
                        break

                    defects = self._parse_defect_result(result)
                    if not defects:
                        break
                    collected.extend(defects)
                    if len(collected) >= max_defects:
                        return collected[:max_defects], None
                    if len(defects) < page_size:
                        break
                    start_index += len(defects)

                if collected:
                    return collected, None
                if page_err:
                    last_err = page_err
                    continue
                # Server accepted this configuration and the stream has no
                # defects — report that clearly instead of masking it.
                return [], f"No defects returned for stream '{stream_name}'"

        # Very last resort: some servers accept a call without a pageSpec.
        try:
            result  = client.service.getMergedDefectsForStreams(
                streamIds=[{"name": stream_name}], filterSpec={})
            defects = self._parse_defect_result(result)
            if defects:
                return defects, None
        except Fault as e:
            if not last_err:
                last_err = str(e.message if hasattr(e, "message") else e)
        except Exception as e:
            if not last_err:
                last_err = str(e)

        return [], last_err or f"No defects returned for stream '{stream_name}'"

    def get_defects_for_project(self, project_name, max_defects=5000):
        """
        Fetch defects across ALL streams in a project by aggregating per-stream results.
        Returns (list_of_dicts, error_string_or_None).
        """
        streams   = self.get_streams_for_project(project_name)
        all_defs  = {}  # cid → defect dict (deduplicate across streams)
        last_err  = None

        for stream in streams:
            defs, err = self.get_defects_for_stream(stream, max_defects)
            if err and not defs:
                last_err = err
                continue
            for d in defs:
                all_defs[d["cid"]] = d

        if all_defs:
            return list(all_defs.values()), None
        return [], last_err or f"No defects found in any stream of project '{project_name}'"

    # Sentinels
    ALL_STREAMS = "— All streams in project —"

    def get_defect_events(self, cid_list, stream_name):
        """
        Best-effort fetch of per-defect event traces via getStreamDefects.

        Returns (events_map, error_string_or_None).
        events_map: cid (int) -> list of event dicts, each
            {"step": int, "type": str, "description": str, "file": str,
             "line": int, "main": bool}
        Also stores defectInstance.lineNumber in events_map under the key
        ("_inst_line", cid) so the caller can use it when events are absent.
        Processes 50 CIDs per SOAP call to avoid server timeouts.
        """
        events_map = {}
        if not ZEEP_AVAILABLE or not cid_list:
            return events_map, None

        # includeDefectInstances must be True or the server omits event traces.
        filter_spec = {
            "includeDefectInstances": True,
            "includeHistory": False,
            "includeTotalDefectInstanceCount": False,
            "maxDefectInstances": 1,
        }

        last_error = None
        try:
            client = self._get_defect_client()
            for i in range(0, len(cid_list), 50):
                batch = cid_list[i:i + 50]
                merged_ids = [{"cid": c, "mergeKey": ""} for c in batch]
                response = None
                batch_err = None
                # Try with filterSpec first; older servers may reject it.
                # This server's getStreamDefects takes no streamId argument.
                for kwargs in [
                    {"mergedDefectIdDataObjs": merged_ids,
                     "filterSpec": filter_spec},
                    {"mergedDefectIdDataObjs": merged_ids},
                ]:
                    try:
                        response = client.service.getStreamDefects(**kwargs)
                        batch_err = None
                        break
                    except Exception as exc:
                        batch_err = str(exc)
                        continue

                if response is None:
                    last_error = batch_err or "getStreamDefects returned no response"
                    continue

                for sd in _unwrap_stream_defects(response):
                    try:
                        cid = int(sd.cid)
                    except Exception:
                        continue
                    instances = getattr(sd, "defectInstances", None) or []
                    # Probe once: if instances empty, record available attributes
                    # so the diagnostic log shows the real SOAP field names.
                    if not instances and not last_error:
                        available = [a for a in dir(sd) if not a.startswith("_")]
                        last_error = (f"defectInstances empty for CID {cid}; "
                                      f"available attrs: {available}")
                    inst = instances[0] if instances else None

                    # Extract the instance-level line number (more accurate than
                    # the merged-defect level which is always 0 for multi-location defects).
                    if inst is not None:
                        inst_line = int(getattr(inst, "lineNumber", 0) or 0)
                        if inst_line:
                            events_map[("_inst_line", cid)] = inst_line

                    evs = []
                    for ev in _flatten_events(getattr(inst, "events", None) or []):
                        evs.append({
                            "step":        int(getattr(ev, "eventNumber", 0)      or 0),
                            "type":        str(getattr(ev, "eventTag", "")         or ""),
                            "description": str(getattr(ev, "eventDescription", "") or ""),
                            "file":        _event_file(ev),
                            "line":        int(getattr(ev, "lineNumber", 0)        or 0),
                            "main":        bool(getattr(ev, "main", False)         or False),
                        })
                    events_map.setdefault(cid, evs)

        except Exception as exc:
            last_error = str(exc)

        return events_map, last_error

    def get_defects_with_events(self, stream_name, max_defects=5000,
                                project_name=None, progress_cb=None):
        """
        Orchestrate a defect fetch + per-defect event-trace fetch.

        stream_name may be the ALL_STREAMS sentinel when project_name is supplied,
        in which case defects are aggregated across all the project's streams and
        event traces are fetched per stream (gap-filling so a defect only gets
        events from the first stream that lists it).

        Returns (defects_list, error_or_None).
        Each defect dict gains an "events" key (possibly []).
        """
        try:
            if stream_name == self.ALL_STREAMS and project_name:
                defects, err = self.get_defects_for_project(project_name, max_defects)
            else:
                defects, err = self.get_defects_for_stream(stream_name, max_defects)

            if err and not defects:
                return [], err
            if not defects:
                return [], "No defects returned from the server"

            cids = [d["cid"] for d in defects]
            total = len(cids)

            if stream_name == self.ALL_STREAMS and project_name:
                target_streams = self.get_streams_for_project(project_name)
                if not target_streams:
                    target_streams = [stream_name]
            else:
                target_streams = [stream_name]

            events_map = {}
            events_errors = []
            for st in target_streams:
                remaining = [c for c in cids if c not in events_map]
                if not remaining:
                    break
                for i in range(0, len(remaining), 50):
                    batch = remaining[i:i + 50]
                    ev, ev_err = self.get_defect_events(batch, st)
                    if ev_err:
                        events_errors.append(ev_err)
                    for cid, evlist in ev.items():
                        events_map.setdefault(cid, evlist)
                    if progress_cb:
                        fetched = sum(1 for k in events_map if not isinstance(k, tuple))
                        pct = int(fetched * 100 / total) if total else 100
                        progress_cb(min(pct, 100),
                                    f"Fetching events… {fetched}/{total}")

            if events_errors and progress_cb:
                # Surface the first error so the UI log shows it as a warning.
                progress_cb(-1, f"Events fetch warning: {events_errors[0]}")

            for d in defects:
                cid = d["cid"]
                events = events_map.get(cid, [])
                # Fill missing file paths from the defect's primary file.
                for ev in events:
                    if not ev.get("file"):
                        ev["file"] = d.get("file", "")
                d["events"] = events

                # mergedDefectDataObj.lineNumber is always 0 for multi-location
                # defects. Prefer: instance line → event-trace line → keep 0.
                if not d.get("line"):
                    inst_line = events_map.get(("_inst_line", cid), 0)
                    if inst_line:
                        d["line"] = inst_line
                    elif events:
                        d["line"] = _line_from_events(events)

            return defects, None
        except Exception as e:
            return [], str(e)

    def _parse_defect_result(self, result):
        """Extract defect dicts from a SOAP result object. Returns None if empty/unparseable."""
        if result is None:
            return None
        items = None
        if hasattr(result, "mergedDefects"):
            items = result.mergedDefects
        elif hasattr(result, "return"):
            r = getattr(result, "return")
            items = getattr(r, "mergedDefects", None) or r
        elif hasattr(result, "__iter__") and not isinstance(result, str):
            items = list(result)
        else:
            items = [result]

        if not items:
            return None

        defects = []
        for d in items:
            try:
                cid = getattr(d, "cid", None)
                if cid is None:
                    continue
                cid   = int(cid)
                fpath = str(getattr(d, "filePathname", "")        or "")
                func  = str(getattr(d, "functionDisplayName", "")  or "")
                line  = int(getattr(d, "lineNumber", 0)            or 0)
                chk   = str(getattr(d, "checkerName", "")          or "")

                # Sub-checker type string, e.g. "Improper use of negative value"
                type_str = str(getattr(d, "displayType", "") or "")
                if not type_str:
                    # plain string on mergedDefectDataObj (v9); some versions nest it
                    type_str = str(getattr(d, "checkerSubcategory", "") or "")
                    if not type_str:
                        sub = getattr(d, "checkerSubcategoryId", None)
                        if sub is not None:
                            type_str = str(getattr(sub, "name", "") or "")

                # Impact / severity string (High / Medium / Low)
                severity_str = str(getattr(d, "displayImpact", "") or "")

                defects.append({"cid": cid, "checker": chk, "file": fpath,
                                "function": func, "line": line,
                                "type": type_str, "severity": severity_str})
            except Exception:
                continue
        return defects if defects else None

    # ------------------------------------------------------------------
    def update_triage(self, cid_list, triage_store_name, classification, comment):
        """
        Push classification + comment for each CID in cid_list.

        Returns (success_count, failed_cid_list, error_message_or_None).
        Batches 100 CIDs per SOAP call (server limit).
        """
        if not ZEEP_AVAILABLE:
            return 0, list(cid_list), "zeep library not installed. Run: pip install zeep"

        mapped_cls = CLASSIFICATION_MAP.get(classification, classification)

        try:
            client = self._get_defect_client()
            failed      = []
            last_error  = None

            for i in range(0, len(cid_list), 100):
                batch = cid_list[i: i + 100]
                # mergedDefectIdDataObj requires cid + mergeKey (empty string = match by CID only)
                merged_ids = [{"cid": c, "mergeKey": ""} for c in batch]
                # defectStateSpecDataObj takes a list of attribute name→value pairs
                attr_values = [
                    {
                        "attributeDefinitionId": {"name": "Classification"},
                        "attributeValueId":      {"name": mapped_cls},
                    },
                    {
                        "attributeDefinitionId": {"name": "Comment"},
                        "attributeValueId":      {"name": comment},
                    },
                ]
                try:
                    client.service.updateTriageForCIDsInTriageStore(
                        triageStore={"name": triage_store_name},
                        mergedDefectIdDataObjs=merged_ids,
                        defectState={"defectStateAttributeValues": attr_values},
                    )
                except Fault as e:
                    last_error = str(e.message) if hasattr(e, "message") else str(e)
                    failed.extend(batch)
                except Exception as e:
                    last_error = str(e)
                    failed.extend(batch)

            success = len(cid_list) - len(failed)
            err_msg = f"SOAP Fault: {last_error}" if last_error else None
            return success, failed, err_msg

        except Fault as e:
            msg = str(e.message) if hasattr(e, "message") else str(e)
            return 0, list(cid_list), f"SOAP Fault: {msg}"
        except Exception as e:
            return 0, list(cid_list), str(e)
