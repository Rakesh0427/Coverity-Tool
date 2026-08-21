#!/usr/bin/env python3
"""
Coverity Connect SOAP v9 client.
Uses DefectService and ConfigurationService WSDLs exposed by every
Coverity Connect installation at /ws/v9/<service>?wsdl.
"""
import threading
import requests
import urllib3
import warnings as _warnings

# Only suppress InsecureRequestWarning when verify is explicitly disabled per-session
# (see _make_session). Do not disable globally — keeps warnings for secure sessions.

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


def _line_from_events(events, checker=""):
    """Derive the defect's Coverity-Connect UI line from its event trace.

    SOAP ``lineNumber`` / the first event is the *path start* (e.g. var_decl at
    706). The UI shows the *main event* (e.g. overrun-local at 710).
    """
    try:
        from coverity_events import line_from_events as _resolve
        return _resolve(events, checker=checker)
    except Exception:
        if not events:
            return 0
        mains = [e for e in events if e.get("main") and e.get("line")]
        if mains:
            return max(mains, key=lambda e: e.get("step", 0)).get("line", 0)
        with_line = [e for e in events if e.get("line")]
        if not with_line:
            return 0
        return max(with_line, key=lambda e: e.get("step", 0)).get("line", 0)


def _soap_event_dict(ev, default_file=""):
    """Normalise a SOAP eventDataObj (or similar) into the pipeline event dict."""
    desc = (getattr(ev, "eventDescription", None)
            or getattr(ev, "covLStrEventDescription", None)
            or "")
    tag = (getattr(ev, "eventTag", None)
           or getattr(ev, "eventType", None)
           or "")
    line = 0
    for attr in ("lineNumber", "eventLineNumber", "strippedLineNumber"):
        try:
            line = int(getattr(ev, attr, 0) or 0)
        except (TypeError, ValueError):
            line = 0
        if line:
            break
    main_raw = getattr(ev, "main", False)
    if isinstance(main_raw, str):
        main = main_raw.strip().lower() in ("true", "1", "yes")
    else:
        main = bool(main_raw)
    try:
        step = int(getattr(ev, "eventNumber", 0) or 0)
    except (TypeError, ValueError):
        step = 0
    fpath = _event_file(ev) or default_file
    return {
        "step": step,
        "type": str(tag or ""),
        "tag": str(tag or ""),
        "description": str(desc or ""),
        "file": str(fpath or ""),
        "line": line,
        "main": main,
    }


# One-shot diagnostic captures for the pull log: the raw SOAP object attributes of
# the first merged defect (line==0) and the first defect instance (no acceptable
# lineNumber). Lets a failing pull reveal the real server field names.
_PULL_DIAG_MERGED_ATTRS = None
_PULL_DIAG_INSTANCE_ATTRS = None


def _rest_event_dict(ev, default_file=""):
    """Normalise a REST event JSON object into the pipeline event dict."""
    try:
        ev_line = int(ev.get("lineNumber") or ev.get("eventLineNumber") or 0)
    except (TypeError, ValueError):
        ev_line = 0
    main_raw = ev.get("main") if ev.get("main") is not None else ev.get("isMain")
    if isinstance(main_raw, str):
        main = main_raw.strip().lower() in ("true", "1", "yes")
    else:
        main = bool(main_raw)
    tag = str(ev.get("eventTag") or ev.get("eventType") or "")
    try:
        step = int(ev.get("eventNumber") or ev.get("stepNumber") or 0)
    except (TypeError, ValueError):
        step = 0
    return {
        "step": step,
        "type": tag,
        "tag": tag,
        "description": str(ev.get("eventDescription") or ev.get("description") or ""),
        "file": str(ev.get("filePathname") or ev.get("filePath") or default_file or ""),
        "line": ev_line,
        "main": main,
    }


def _rest_defect_from_issue(issue, is_v1=False):
    """Map a REST issue/defect JSON object to the pipeline defect dict.

    ``is_v1`` marks the older GET /api/v1/defects shape (no embedded events).
    Prefer ``mainEventLineNumber`` (Connect UI) over ``lineNumber`` (often the
    first event in the path — the 706-vs-710 mismatch).
    """
    filepath = str(issue.get("mainEventFilePath")
                   or issue.get("mainEventFilePathname")
                   or issue.get("filePathname") or "")
    func     = str(issue.get("functionDisplayName") or "")
    rest_main = 0
    occ_line = 0
    try:
        rest_main = int(issue.get("mainEventLineNumber") or 0)
    except (TypeError, ValueError):
        rest_main = 0
    try:
        occ_line = int(issue.get("lineNumber") or 0)
    except (TypeError, ValueError):
        occ_line = 0
    line = rest_main or occ_line
    events = []
    if not is_v1:
        for ev in (issue.get("events") or []):
            if isinstance(ev, dict):
                events.append(_rest_event_dict(ev, filepath))
    if events:
        ev_line = _line_from_events(events, str(issue.get("checkerName") or ""))
        if ev_line:
            line = ev_line
    return {
        "checker": str(issue.get("checkerName") or ""),
        "type": str(issue.get("displayType")
                    or issue.get("checkerSubcategoryLongDescription") or ""),
        "severity": str(issue.get("displayImpact") or ""),
        "file": filepath,
        "line": line,
        "function": func,
        "events": events,
        "_rest_main_line": rest_main,
        "_line_src": "rest_main" if rest_main else "rest",
    }


# Column names requested from /api/v2/issues/search (tabular response).
# Requesting exactly these names lets us reuse _rest_defect_from_issue
# unchanged.
_SEARCH_COLUMNS = [
    "cid", "checkerName", "displayType", "displayImpact",
    "mainEventFilePath", "mainEventLineNumber", "functionDisplayName",
]


def _issues_search_items(data):
    """Map an /api/v2/issues/search response to (items, totalRows).

    The search endpoint returns ``{"offset":..., "totalRows":N,
    "columns":[{name:...}, ...], "rows":[[v1, v2, ...], ...]}`` where
    each row is positional. Zip rows with column names to rebuild dicts.
    """
    if not isinstance(data, dict):
        return [], None
    cols = []
    for c in (data.get("columns") or []):
        if isinstance(c, dict):
            cols.append(str(c.get("name") or c.get("id") or ""))
        else:
            cols.append(str(c))
    items = []
    for row in (data.get("rows") or []):
        if isinstance(row, (list, tuple)):
            items.append(dict(zip(cols, row)))
        elif isinstance(row, dict):
            items.append(row)
    return items, data.get("totalRows")


def _is_signin_response(resp):
    """Coverity answers unauthenticated REST calls with HTTP 200 and its
    Sign-in page JSON (cspNonce/availableSamlSsoConfigurations/...). Treat
    such responses as unusable instead of a successful API answer."""
    try:
        body = resp.json()
    except Exception:
        text = (resp.text or "")
        return "Sign in" in text[:400] or "cspNonce" in text[:400]
    if isinstance(body, dict):
        return bool(body.get("cspNonce")
                    or body.get("availableSamlSsoConfigurations")
                    or body.get("ldapConfigured"))
    return False


class CoveritySOAPClient:
    def __init__(self, host, port, username, password, use_ssl=True,
                 verify_ssl=True, rest_token=None, api_key=None):
        self.host       = host.strip()
        self.port       = int(port)
        self.username   = username
        self.password   = password
        self.use_ssl    = use_ssl    # controls http vs https scheme
        self.verify_ssl = bool(verify_ssl) # controls certificate validation (secure by default)
        self._defect_client = None
        self._config_client = None
        self._rest_token = rest_token  # pre-provided session/API token for REST auth
        self._api_key = api_key         # optional API key sent as X-API-Key header
        self._rest_session = None       # requests.Session for cookie-based auth
        self._rest_authenticated = False  # whether session auth succeeded
        self._lock = threading.Lock()
        # If caller explicitly disables verification, suppress warning for that session only
        if not self.verify_ssl:
            _warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
        self._rest_base_discovered = None  # cached REST base probe result

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
        # NOTE: exact element casing matters ("sortAscending", "pageSize",
        # "startIndex", "sortField"). This server's WSDL requires sortAscending,
        # so all paged variants include it.
        shapes = [
            ("standard",  lambda ps, si: {"pageSize": ps, "sortAscending": True, "startIndex": si}),
            ("with-sortField-cid", lambda ps, si: {"pageSize": ps, "sortAscending": True,
                                                    "sortField": "cid", "startIndex": si}),
            ("ascFalse",   lambda ps, si: {"pageSize": ps, "sortAscending": False, "startIndex": si}),
            ("with-sortField-checkerName", lambda ps, si: {"pageSize": ps, "sortAscending": True,
                                                    "sortField": "checkerName", "startIndex": si}),
            ("with-sortField-mergedDefectId", lambda ps, si: {"pageSize": ps, "sortAscending": True,
                                                    "sortField": "mergedDefectId", "startIndex": si}),
            ("no-startIndex", lambda ps, si: {"pageSize": ps, "sortAscending": True}),
        ]
        page_sizes = (2000, 1000, 500, 250, 100, 50)
        first_err = None

        for label, shape in shapes:
            for page_size in page_sizes:
                collected    = []
                seen         = set()
                start_index  = 0
                page_err     = None
                while len(collected) < max_defects:
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

                    defects = self._parse_defect_result(result) or []
                    if not defects:
                        break

                    # Deduplicate by CID and stop paginating when a page adds no
                    # new rows. Some servers ignore `startIndex` (and the last
                    # fallback page-spec omits it), so without this guard every
                    # "page" returns the same first page and the defect count is
                    # inflated with duplicates.
                    added_any = False
                    for d in defects:
                        c = d.get("cid")
                        if c is not None and c not in seen:
                            seen.add(c)
                            collected.append(d)
                            added_any = True
                    if not added_any:
                        break  # duplicate page -> we already have every unique row

                    if len(collected) >= max_defects:
                        return collected[:max_defects], None
                    if len(defects) < page_size:
                        break
                    start_index += len(defects)

                if collected:
                    return collected, None
                if page_err:
                    if first_err is None:
                        first_err = page_err
                    last_err = page_err
                    continue
                # Server accepted this configuration and the stream has no
                # defects (or only duplicates) — report it instead of masking.
                return [], f"No defects returned for stream '{stream_name}'"

        # Last resort: some servers only accept a bare call; others REQUIRE the
        # pageSpec (with sortAscending) even for a single-page fetch, so try the
        # small pageSpec first and only then the bare call.
        for last_spec in (
            {"pageSize": 50, "sortAscending": True, "startIndex": 0},
            {"pageSize": 50, "sortAscending": True, "sortField": "cid", "startIndex": 0},
            None,
        ):
            try:
                kwargs = {"streamIds": [{"name": stream_name}], "filterSpec": {}}
                if last_spec is not None:
                    kwargs["pageSpec"] = last_spec
                result = client.service.getMergedDefectsForStreams(**kwargs)
                defects = self._parse_defect_result(result)
                if defects:
                    return defects, None
            except Fault as e:
                if not last_err:
                    last_err = str(e.message if hasattr(e, "message") else e)
            except Exception as e:
                if not last_err:
                    last_err = str(e)

        return [], first_err or last_err or f"No defects returned for stream '{stream_name}'"

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
        # includeHistory + a larger maxDefectInstances makes the server return the
        # per-snapshot instances; Coverity orders them oldest -> newest, so the
        # LAST instance is the defect's CURRENT location (the server UI shows this
        # line). The first instance is the stale first-detection trace.
        filter_spec = {
            "includeDefectInstances": True,
            "includeHistory": True,
            "includeTotalDefectInstanceCount": False,
            "maxDefectInstances": 20,
        }

        last_error = None
        try:
            client = self._get_defect_client()
            for i in range(0, len(cid_list), 50):
                batch = cid_list[i:i + 50]
                merged_ids = [{"cid": c, "mergeKey": ""} for c in batch]
                response = None
                batch_err = None
                # Prefer encoding streamId — without it the server can return a
                # DIFFERENT instance of the merged defect, giving the wrong event
                # trace and a wrong line (e.g. an old revision's line that is now a
                # comment). Try streamId first, then progressively more minimal
                # variants for servers whose WSDL omits streamId/filterSpec.
                for kwargs in [
                    {"mergedDefectIdDataObjs": merged_ids,
                     "streamId": {"name": stream_name},
                     "filterSpec": filter_spec},
                    {"mergedDefectIdDataObjs": merged_ids,
                     "streamId": {"name": stream_name}},
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
                    events_map[("_n_instances", cid)] = len(instances)

                    # One-shot: capture all field values from sd and inst so the
                    # pull log reveals every line-number field on this server.
                    if not events_map.get(("_probed",)):
                        events_map[("_probed",)] = True
                        events_map[("_sd_probe",)] = {
                            a: getattr(sd, a, None)
                            for a in dir(sd) if not a.startswith("_")
                        }
                        inst_tmp = instances[-1] if instances else None
                        events_map[("_inst_probe",)] = (
                            {a: getattr(inst_tmp, a, None)
                             for a in dir(inst_tmp) if not a.startswith("_")}
                            if inst_tmp else {}
                        )

                    # Instances are ordered oldest -> newest snapshot. Pick the LAST
                    # one so events/line reflect the defect's CURRENT location.
                    inst = instances[-1] if instances else None

                    # Try every known field name variant for the primary line number.
                    inst_line = 0
                    if inst is not None:
                        for _ln_field in ("lineNumber", "checkerLineNumber",
                                          "primaryLineNumber", "mainEventLineNumber"):
                            _v = getattr(inst, _ln_field, None)
                            if _v:
                                try:
                                    inst_line = int(_v)
                                except (TypeError, ValueError):
                                    pass
                                if inst_line:
                                    break
                    if inst_line:
                        events_map[("_inst_line", cid)] = inst_line

                    # Extract function name from instance.function.functionDisplayName
                    # (more reliable than the merged-defect level field).
                    inst_func = getattr(inst, "function", None) if inst else None
                    if inst_func:
                        fn = (getattr(inst_func, "functionDisplayName", None) or
                              getattr(inst_func, "functionMangledName", None) or "")
                        if fn:
                            events_map[("_inst_func", cid)] = str(fn)

                    # Extract sub-type and severity from instance fields.
                    if inst is not None:
                        _t = getattr(inst, "type", None)
                        if _t:
                            events_map[("_inst_type", cid)] = str(
                                getattr(_t, "displayName", None) or "")
                        _imp = getattr(inst, "impact", None)
                        if _imp:
                            events_map[("_inst_sev", cid)] = str(
                                getattr(_imp, "displayName", None) or "")

                    evs = []
                    for ev in _flatten_events(getattr(inst, "events", None) or []):
                        evs.append(_soap_event_dict(ev))
                    events_map.setdefault(cid, evs)

        except Exception as exc:
            last_error = str(exc)

        return events_map, last_error

    # ── REST API v2 ────────────────────────────────────────────────────────
    # Coverity Connect v2020+ exposes a REST API that returns mainEventLineNumber
    # which exactly matches the web UI. We try REST first; SOAP is the fallback.

    def _rest_authenticate(self):
        """Authenticate via the REST session endpoint using a requests.Session.

        If a pre-provided ``rest_token`` was passed to the constructor, it is
        used directly (no session-endpoint login needed).

        Otherwise, POSTs credentials to /api/{v}/session.  The server may set
        a session cookie (e.g. COVJSESSIONID) and/or return a token in the
        JSON body.  Cookies are persisted via the session for subsequent
        requests.

        Returns True if any form of authentication succeeded.
        """
        if getattr(self, "_rest_authenticated", False):
            return True
        # If a pre-provided token was given, use it directly
        if self._rest_token:
            self._rest_session = requests.Session()
            self._rest_session.verify = self.verify_ssl
            self._rest_session.headers["tns-cnct-api-authenticate-token"] = self._rest_token
            # Mirrors curl -u user:token: some servers only honour Basic auth.
            self._rest_session.auth = (self.username, self._rest_token)
            if self._api_key:
                self._rest_session.headers["X-API-Key"] = self._api_key
            self._rest_authenticated = True
            return True
        self._rest_session = requests.Session()
        self._rest_session.verify = self.verify_ssl
        for version in ("v2", "v1"):
            url = f"{self._base_url()}/api/{version}/session"
            try:
                resp = self._rest_session.post(
                    url,
                    json={"username": self.username, "password": self.password},
                    timeout=15,
                    headers=self._rest_headers(),
                )
                if resp.status_code in (200, 201, 204):
                    try:
                        data = resp.json()
                    except Exception:
                        data = {}
                    if isinstance(data, dict):
                        token = (data.get("token") or data.get("sessionId")
                                 or data.get("authToken"))
                        if token:
                            self._rest_token = str(token)
                            self._rest_session.headers["tns-cnct-api-authenticate-token"] = token
                            self._rest_authenticated = True
                            return True
                    # Session cookies set by the server indicate auth
                    if self._rest_session.cookies:
                        xsrf = self._rest_session.cookies.get("XSRF-TOKEN", "")
                        if xsrf:
                            self._rest_session.headers["X-XSRF-TOKEN"] = xsrf
                        self._rest_authenticated = True
                        return True
            except Exception:
                pass
        # Session auth failed -- clear so we fall back to Basic auth
        self._rest_session = None
        return False

    def _rest_headers(self):
        """Build standard REST headers, including optional API key."""
        hdrs = {"Accept": "application/json"}
        if getattr(self, "_api_key", None):
            hdrs["X-API-Key"] = self._api_key
        return hdrs

    def _rest_basic_auth(self):
        """Basic-auth tuple for REST.

        Coverity accepts the API auth token in place of the password for
        Basic auth, so prefer it whenever a token is available.
        """
        secret = self._rest_token or self.password
        return (self.username, secret)

    def _rest_get(self, path, params=None):
        """GET request to the Coverity REST API v2. Returns parsed JSON or raises."""
        url = f"{self._api_base('v2')}/{path.lstrip('/')}"
        if self._rest_authenticate() and self._rest_session:
            resp = self._rest_session.get(
                url, params=params, timeout=60,
                headers=self._rest_headers())
        else:
            resp = requests.get(
                url, params=params,
                auth=self._rest_basic_auth(),
                verify=self.verify_ssl, timeout=60,
                headers=self._rest_headers())
        resp.raise_for_status()
        return resp.json()

    def _rest_post_v2(self, path, json_body=None):
        """POST to the REST API v2 (the issue-query endpoint is POST-capable)."""
        url = f"{self._api_base('v2')}/{path.lstrip('/')}"
        if self._rest_authenticate() and self._rest_session:
            resp = self._rest_session.post(
                url, json=json_body, timeout=60,
                headers=self._rest_headers())
        else:
            resp = requests.post(
                url, json=json_body,
                auth=self._rest_basic_auth(),
                verify=self.verify_ssl, timeout=60,
                headers=self._rest_headers())
        resp.raise_for_status()
        return resp.json()

    def _rest_search_issues(self, path, stream_name, limit, offset):
        """POST an issue-search query to /api/v2/issues/search.

        Body uses CQL ``streams['<name>']`` plus the requested columns.
        The server returns the tabular columns/rows format parsed by
        :func:`_issues_search_items`.
        """
        body = {
            "queryType": "cql",
            "cql": f"streams['{stream_name}']",
            "columns": list(_SEARCH_COLUMNS),
            "limit": int(limit),
            "offset": int(offset),
        }
        return self._rest_post_v2(path, body)

    def _rest_get_v1(self, path, params=None):
        """GET to the legacy REST API v1 (/api/v1/defects)."""
        url = f"{self._api_base('v1')}/{path.lstrip('/')}"
        if self._rest_authenticate() and self._rest_session:
            resp = self._rest_session.get(
                url, params=params, timeout=60,
                headers=self._rest_headers())
        else:
            resp = requests.get(
                url, params=params,
                auth=self._rest_basic_auth(),
                verify=self.verify_ssl, timeout=60,
                headers=self._rest_headers())
        resp.raise_for_status()
        return resp.json()

    def _api_base(self, version):
        """REST base for `version` ('v1'/'v2'), using a discovered base when the
        REST API lives under a different port/web-root than the default."""
        base = getattr(self, "_rest_base_discovered", None) or {}
        if base.get(version):
            return f"{base[version]}/api/{version}"
        return f"{self._base_url()}/api/{version}"

    def _candidate_rest_bases(self):
        """Candidate server bases to probe for the REST API (ports x roots).

        Ordered by likelihood: primary port+root first, so fast-path succeeds
        without scanning all combinations.
        """
        scheme = "https" if self.use_ssl else "http"
        roots = ["", "/connect", "/ngweb", "/coverity", "/rest"]
        ports = [self.port, 443, 8443, 8080]
        seen, out = set(), []
        for p in ports:
            for r in roots:
                c = f"{scheme}://{self.host}:{p}{r}"
                if c not in seen:
                    seen.add(c)
                    out.append(c)
        return out

    def discover_rest_base(self, timeout_secs=3.0, max_workers=8):
        """Probe candidate REST bases concurrently; returns (v1_base, v2_base, info_string).

        A base is 'found' when /api/<v>/streams answers with a 2xx/3xx success
        (404/401/403 are treated as unusable). The result is cached so the pull
        uses it automatically after the first probe. Uses ThreadPoolExecutor for
        ~8x faster discovery (previously 40 sequential * 5s = 200s worst-case).
        """
        if getattr(self, "_rest_base_discovered", None):
            cached = self._rest_base_discovered
            if cached and (cached.get("v1") or cached.get("v2")):
                return cached.get("v1"), cached.get("v2"), "cached"
        import concurrent.futures as _cf
        candidates = self._candidate_rest_bases()
        tasks = []
        for base in candidates:
            for version in ("v2", "v1"):
                url = f"{base}/api/{version}/streams"
                tasks.append((base, version, url))
        v1 = v2 = ""
        tried = []
        tried_lock = threading.Lock()
        def _probe(task):
            base, version, url = task
            try:
                resp = requests.get(
                    url, params={"limit": 1},
                    auth=self._rest_basic_auth(),
                    verify=self.verify_ssl, timeout=timeout_secs,
                    headers=self._rest_headers())
                is_ok = resp.status_code < 400 and not _is_signin_response(resp)
                with tried_lock:
                    tried.append(f"{url} -> {resp.status_code}")
                if is_ok:
                    return (base, version)
            except Exception as exc:
                with tried_lock:
                    tried.append(f"{url} -> {str(exc)[:36]}")
            return None
        with _cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_probe, t): t for t in tasks}
            for fut in _cf.as_completed(futures):
                res = fut.result()
                if res:
                    base, version = res
                    if version == "v1" and not v1:
                        v1 = base
                    elif version == "v2" and not v2:
                        v2 = base
                    if v1 and v2:
                        for f in futures:
                            f.cancel()
                        break
        self._rest_base_discovered = {"v1": v1 or None, "v2": v2 or None}
        return (v1 or None), (v2 or None), "; ".join(tried[:20])

    def _probe_issue_endpoint(self, stream_name=None):
        """Locate the v2 defect-list path under the discovered base.

        Returns (path, method, status_log). Optimized: try the known
        ``issues/search`` endpoint first with short timeout; only if it fails
        probe swagger and other candidates concurrently (previously sequential
        12*10s could stall pull for >2 min).
        """
        base = (getattr(self, "_rest_base_discovered", None) or {}).get("v2")
        if not base:
            return None, None, ""
        log = []
        # Authenticate via session endpoint to get cookies/token
        self._rest_authenticate()
        sess = getattr(self, "_rest_session", None)
        hdrs = self._rest_headers()

        def _req(method, url, **kw):
            """Send a request using session auth, falling back to Basic auth."""
            if sess:
                if method == "get":
                    return sess.get(url, verify=self.verify_ssl, **kw)
                return sess.post(url, verify=self.verify_ssl, **kw)
            kw["auth"] = self._rest_basic_auth()
            if method == "get":
                return requests.get(url, verify=self.verify_ssl, **kw)
            return requests.post(url, verify=self.verify_ssl, **kw)
        # Fast-path: issues/search is the documented endpoint on most servers.
        # Try it first with 4s timeout before any swagger probes.
        try:
            url = f"{base}/api/v2/issues/search"
            r = _req("post", url, json={
                "limit": 1, "columns": list(_SEARCH_COLUMNS),
                "queryType": "cql", "cql": f"streams['{stream_name}']" if stream_name else "",
                "offset": 0}, headers=hdrs, timeout=4)
            log.append(f"{url} [post] -> {r.status_code}")
            if r.status_code not in (404, 405) and not _is_signin_response(r):
                return "issues/search", "post", "; ".join(log)
        except Exception as exc:
            log.append(f"{base}/api/v2/issues/search [post] -> {str(exc)[:30]}")
        # Swagger discovery — shorten timeout to 4s and single attempt
        discovered_names = []
        for spec in ("/api/v2/swagger.json", "/api/v2/openapi.json"):
            try:
                r = _req("get", base + spec, headers=hdrs, timeout=4)
                log.append(f"{base + spec} -> {r.status_code}")
                if r.status_code == 200:
                    try:
                        doc = r.json()
                    except Exception:
                        doc = None
                    if isinstance(doc, dict):
                        paths = set((doc.get("paths") or {}).keys())
                        for p in paths:
                            norm = p.rstrip("/").split("/")[-1]
                            if any(t in norm.lower() for t in
                                   ("defect", "issue", "finding")):
                                discovered_names.append(norm)
                        log.append(f"swagger paths with defect/issue found: "
                                   f"{sorted(discovered_names)[:8]}")
                    break
            except Exception as exc:
                log.append(f"{base + spec} -> {str(exc)[:30]}")
        candidates = discovered_names or ["issues", "defects", "query/issues"]
        # Probe remaining candidates concurrently (4s timeout, 4 workers)
        import concurrent.futures as _cf2
        probe_params = {"limit": 1}
        if stream_name:
            probe_params["streamNames[]"] = stream_name
        tasks = []
        for path in candidates:
            url = f"{base}/api/v2/{path}"
            tasks.append((path, "get", url, dict(probe_params)))
            tasks.append((path, "post", url, {"limit": 1, "streamNames": [stream_name] if stream_name else []}))
        def _probe_task(item):
            path, method, url, payload = item
            try:
                if method == "get":
                    r = _req("get", url, params=payload, headers=hdrs, timeout=4)
                else:
                    r = _req("post", url, json=payload, headers=hdrs, timeout=4)
                return (path, method, r.status_code, _is_signin_response(r))
            except Exception as exc:
                return (path, method, str(exc)[:30], False)
        with _cf2.ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(_probe_task, t): t for t in tasks}
            for fut in _cf2.as_completed(futures):
                path, method, code, is_signin = fut.result()
                if isinstance(code, int):
                    log.append(f"{base}/api/v2/{path} [{method}] -> {code}")
                    if code not in (404, 405) and not is_signin:
                        # Cancel remaining
                        for f in futures:
                            f.cancel()
                        return path, method, "; ".join(log)
                else:
                    log.append(f"{base}/api/v2/{path} [{method}] -> {code}")
        return None, None, "; ".join(log)

    def test_rest_available(self):
        """Returns True if the REST API v2 is reachable on this server."""
        try:
            self._rest_get("streams", {"limit": 1})
            return True
        except Exception:
            return False

    def get_defects_rest(self, stream_name, max_defects=5000, progress_cb=None):
        """
        Fetch defects via REST API v2 (Coverity Connect v2020+).

        Returns (defects_list, error_or_None).
        Each defect dict includes:
          cid, checker, type, severity, file, line (mainEventLineNumber — exact
          web UI value), function, events (with step/type/description/file/line).

        Raises no exceptions; returns ([], error_string) on failure so the caller
        can fall back to SOAP automatically.
        """
        try:
            limit = min(500, max_defects)
            # Locate the actual v2 defect-list path (some versions use a different
            # resource than /api/v2/issues, which can 404 even when /streams works).
            path, method, _p = self._probe_issue_endpoint(stream_name)
            _v2_items = lambda d: (d.get("items") or d.get("defects") or [],
                                   d.get("totalRows") or d.get("totalDefects"))
            attempts = [
                ("v2 POST /api/v2/issues/search",
                 lambda off, lim: self._rest_search_issues(
                     "issues/search", stream_name, lim, off),
                 _issues_search_items, False),
            ]
            if path and method == "get":
                attempts.append((
                    f"v2 GET /api/v2/{path}",
                    lambda off, lim, p=path: self._rest_get(p, {
                        "streamNames[]": stream_name, "includeDetails": "true",
                        "limit": lim, "offset": off}),
                    _v2_items, False))
            elif path and method == "post" and path != "issues/search":
                attempts.append((
                    f"v2 POST /api/v2/{path}",
                    lambda off, lim, p=path: self._rest_post_v2(p, {
                            "streamNames": [stream_name] if stream_name else [],
                        "limit": lim, "offset": off}),
                    _v2_items, False))
            attempts.extend([
                ("v2 GET /api/v2/issues",
                 lambda off, lim: self._rest_get("issues", {
                     "streamNames[]": stream_name, "includeDetails": "true",
                     "limit": lim, "offset": off}),
                 _v2_items, False),
                ("v2 POST /api/v2/issues",
                 lambda off, lim: self._rest_post_v2("issues", {
                            "streamNames": [stream_name] if stream_name else [],
                     "limit": lim, "offset": off}),
                 _v2_items, False),
                ("v1 GET /api/v1/defects",
                 lambda off, lim: self._rest_get_v1("defects", {
                     "streamId": stream_name, "limit": lim, "offset": off}),
                 lambda d: (d.get("defects") or [], d.get("totalDefects")), True),
            ])
            errors = []
            for label, fetch, items_fn, is_v1 in attempts:
                all_defects = []
                offset = 0
                total = None
                while True:
                    try:
                        data = fetch(offset, limit)
                    except Exception as exc:
                        errors.append(f"{label}: {exc}")
                        break
                    items, raw_total = items_fn(data)
                    if total is None and raw_total:
                        try:
                            total = int(raw_total)
                        except (TypeError, ValueError):
                            total = None
                    if not items:
                        break
                    for issue in items:
                        if not isinstance(issue, dict):
                            continue
                        cid = issue.get("cid")
                        if cid is None:
                            cid = (issue.get("mergedDefectId") or {}).get("cid")
                        if cid is None:
                            continue
                        d = _rest_defect_from_issue(issue, is_v1)
                        d["cid"] = int(cid)
                        all_defects.append(d)
                    offset += len(items)
                    if offset >= max_defects or (total and offset >= total) \
                       or len(items) < limit:
                        break
                if all_defects:
                    if progress_cb:
                        progress_cb(100, f"REST({label}): {len(all_defects)} defects fetched.")
                    return all_defects, None

            return [], (" | ".join(errors) if errors
                        else f"REST API returned 0 defects for stream '{stream_name}'")
        except Exception as exc:
            return [], str(exc)

    def get_defects_rest_events(self, cid, stream_name):
        """
        Fetch the full event trace for a single CID via REST.
        Falls back to empty list on any error.
        Returns list of event dicts.
        """
        try:
            data = self._rest_get(f"issues/{cid}", {"streamName": stream_name})
            raw_events = data.get("events") or []
            return [_rest_event_dict(ev) for ev in raw_events if isinstance(ev, dict)]
        except Exception:
            return []

    # ───────────────────────────────────────────────────────────────────────

    def get_defects_with_events(self, stream_name, max_defects=5000,
                                project_name=None, progress_cb=None):
        """
        Orchestrate a defect fetch + per-defect event-trace fetch.

        Tries REST API v2 first (accurate mainEventLineNumber).
        Falls back to SOAP + getStreamDefects when REST is unavailable.

        REST listings typically omit the event trace, so SOAP getStreamDefects
        is always used to fill events. The defect line is then taken from the
        *main event* (Coverity Connect UI), never the first path event.

        stream_name may be the ALL_STREAMS sentinel when project_name is supplied,
        in which case defects are aggregated across all the project's streams and
        event traces are fetched per stream (gap-filling so a defect only gets
        events from the first stream that lists it).

        Returns (defects_list, error_or_None).
        Each defect dict gains an "events" key (possibly []).
        """
        try:
            from coverity_events import apply_events_to_defect

            defects = []
            rest_err = None

            # ── Try REST API first — mainEventLineNumber matches the web UI ──
            if stream_name != self.ALL_STREAMS:
                if progress_cb:
                    progress_cb(2, "Trying REST API…")
                # Locate the REST base once (auto-probes ports/web-roots if the
                # standard /api/v1 & /api/v2 paths 404).
                if not getattr(self, "_rest_base_discovered", None):
                    self.discover_rest_base()
                rest_defects, rest_err = self.get_defects_rest(
                    stream_name, max_defects, progress_cb)
                if rest_defects:
                    defects = rest_defects
                    if progress_cb:
                        progress_cb(20, f"REST: {len(rest_defects)} defects listed; fetching events…")
                else:
                    if progress_cb:
                        progress_cb(-1, f"REST unavailable ({rest_err}), falling back to SOAP…")

            # ── SOAP list if REST produced nothing ──────────────────────────
            if not defects:
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

            # REST v2 issues/search (and REST v1 /defects) typically omit the
            # event trace. Always fill missing events via SOAP getStreamDefects
            # so analysis sees Coverity's path (and the main-event line).
            events_map = {}
            events_errors = []
            have_events = {d["cid"] for d in defects if d.get("events")}
            missing = [c for c in cids if c not in have_events]
            for st in target_streams:
                remaining = [c for c in missing if c not in events_map]
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
                        pct = 20 + int(fetched * 80 / total) if total else 100
                        progress_cb(min(pct, 99),
                                    f"Fetching events… {fetched}/{total}")

            if events_errors and progress_cb:
                # Surface the first error so the UI log shows it as a warning.
                progress_cb(-1, f"Events fetch warning: {events_errors[0]}")

            for d in defects:
                cid = d["cid"]
                events = d.get("events") or events_map.get(cid, [])
                d["_n_instances"] = events_map.get(("_n_instances", cid), d.get("_n_instances", 0))
                # Enrich with instance-level fields that are more reliable than
                # the merged-defect level (function name, sub-type, severity).
                if not d.get("function"):
                    d["function"] = events_map.get(("_inst_func", cid), d.get("function", ""))
                else:
                    d["function"] = events_map.get(("_inst_func", cid), d["function"]) or d["function"]
                if not d.get("type"):
                    d["type"] = events_map.get(("_inst_type", cid), d.get("type", ""))
                if not d.get("severity"):
                    d["severity"] = events_map.get(("_inst_sev", cid), d.get("severity", ""))
                # Fill missing file paths from the defect's primary file.
                for ev in events:
                    if not ev.get("file"):
                        ev["file"] = d.get("file", "")

                # Keep every raw line source so the pull log can show which
                # value each source contributed.
                d["_merged_line"] = d.get("_merged_line", d.get("line", 0))
                d["_inst_line_val"] = events_map.get(("_inst_line", cid),
                                                     d.get("_inst_line_val", 0))
                main_ev = next((e for e in events if e.get("main")), None)
                d["_main_event_line"] = (main_ev.get("line") if main_ev else 0) or 0
                d["_last_event_line"] = (max(events, key=lambda e: e.get("step", 0)).get("line")
                                         if events else 0) or 0

                # Main event line (Connect UI) ALWAYS wins over instance /
                # merged lineNumber, which is the first event in the path.
                apply_events_to_defect(d, events)

            # Attach probe data to first defect so the pull log can dump it.
            if defects:
                defects[0]["_sd_probe"]   = events_map.get(("_sd_probe",),   {})
                defects[0]["_inst_probe"] = events_map.get(("_inst_probe",), {})

            if progress_cb:
                with_ev = sum(1 for d in defects if d.get("events"))
                progress_cb(100, f"Fetched {len(defects)} defects, {with_ev} with events.")
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
                try:
                    rest_main = int(getattr(d, "mainEventLineNumber", 0) or 0)
                except (TypeError, ValueError):
                    rest_main = 0
                if rest_main:
                    line = rest_main

                if not line:
                    # merged lineNumber is 0 on this server; the defect's CURRENT
                    # line (what the server UI shows) lives on the first instance.
                    for _di in (getattr(d, "defectInstances", None) or [])[:1]:
                        try:
                            _il = int(getattr(_di, "lineNumber", 0) or 0)
                        except Exception:
                            _il = 0
                        if _il:
                            line = _il
                        break
                    global _PULL_DIAG_MERGED_ATTRS
                    if not line and _PULL_DIAG_MERGED_ATTRS is None:
                        _PULL_DIAG_MERGED_ATTRS = ",".join(
                            a for a in dir(d) if not a.startswith("_"))

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
