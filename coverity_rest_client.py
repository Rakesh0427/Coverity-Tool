#!/usr/bin/env python3
"""
coverity_rest_client.py — Coverity Connect REST API client.

Purpose
-------
The Coverity SOAP defect-service on some servers returns NO lineNumber field on
the merged/instance objects (only the first-detected event-trace line). The
Coverity Connect web UI and its REST API expose the defect's CURRENT location
via `lineNumber`. This client logs into Connect's REST API and overlays the
correct current lines onto the SOAP-pulled defects.

Endpoints used
--------------
  POST   {base}/api/v1/session                    -> authenticate (JSON username/password)
  GET    {base}/api/v1/defects?streamId=..&offset=..&limit=.. -> defect list
  DELETE {base}/api/v1/session                    -> logout

The REST defect JSON carries `lineNumber` (current line), `checkerName`,
`filePathname`, `functionDisplayName`, `displayType`, `displayImpact`.
"""
import requests


REST_API_PREFIX = "/api/v1"


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def apply_rest_lines(defects, cid_map):
    """Overlay the REST-derived CURRENT line onto SOAP-pulled ``defects``.

    ``cid_map`` is {cid: {line, checker, file, function, type, severity}} as
    returned by :meth:`CoverityRESTClient.fetch_defect_lines`. For each defect
    whose CID is found and has a non-zero ``line``, that line becomes the
    defect's line (and ``_line_src`` is set to ``rest``). Returns the number of
    defects whose line was updated (marking ``_line_prev`` before overwrite).
    """
    fixed = 0
    for d in defects:
        info = (cid_map or {}).get(d.get("cid"))
        if not info:
            continue
        new_line = info.get("line")
        if not new_line:
            continue
        if d.get("line") != new_line:
            d["_line_prev"] = d.get("line", 0)
            d["line"] = new_line
            fixed += 1
        d["_line_src"] = "rest"
        for key, src in (("checker", "checker"), ("file", "file"),
                         ("function", "function"), ("type", "type"),
                         ("severity", "severity")):
            if info.get(src) and not d.get(key):
                d[key] = info[src]
    return fixed


class CoverityRESTClient:
    """Minimal Coverity Connect REST API client."""

    def __init__(self, host, port, username, password,
                 use_ssl=True, verify_ssl=False, auth_token=None):
        self.host = (host or "").strip()
        try:
            self.port = int(port or 443)
        except (TypeError, ValueError):
            self.port = 443
        self.username = (username or "").strip()
        self.password = password or ""
        self.auth_token = (auth_token or "").strip()
        self.use_ssl = bool(use_ssl)
        self._session = requests.Session()
        self._session.verify = bool(verify_ssl)
        scheme = "https" if self.use_ssl else "http"
        self._base = f"{scheme}://{self.host}:{self.port}"
        self.logged_in = False

    def _url(self, path):
        if not path.startswith("/"):
            path = "/" + path
        return self._base + REST_API_PREFIX + path

    # ------------------------------------------------------------------ auth
    def login(self):
        """Authenticate. Returns (ok, message)."""
        # API auth token: Coverity accepts it as the Basic-auth password.
        if self.auth_token:
            self._session.auth = (self.username, self.auth_token)
            self.logged_in = True
            return True, "REST connected (API token)"
        try:
            resp = self._session.post(
                self._url("/session"),
                json={"username": self.username, "password": self.password},
                timeout=30,
            )
        except Exception as exc:
            return False, f"REST auth error: {exc}"
        if resp.status_code in (200, 201, 204):
            try:
                body = resp.json()
            except Exception:
                body = {}
            token = body.get("token") if isinstance(body, dict) else None
            if token:
                self._session.headers["tns-cnct-api-authenticate-token"] = str(token)
            self.logged_in = True
            return True, f"REST connected ({resp.status_code})"
        return False, f"REST auth failed ({resp.status_code}): {resp.text[:200]}"

    def logout(self):
        try:
            if self.logged_in:
                self._session.delete(self._url("/session"), timeout=10)
        except Exception:
            pass

    def close(self):
        self.logout()
        try:
            self._session.close()
        except Exception:
            pass

    # ----------------------------------------------------------------- data
    def fetch_defect_lines(self, stream_id, limit=50000, page=500):
        """Fetch defect current-lines for a stream (paginated).

        Returns ``{cid: {line, checker, file, function, type, severity}}``.
        ``lineNumber`` is the defect's CURRENT line (what the Connect UI shows).
        """
        cid_map = {}
        offset = 0
        while offset < max(limit, 0):
            resp = self._session.get(
                self._url("/defects"),
                params={
                    "streamId": stream_id,
                    "offset": offset,
                    "limit": page,
                    "sortBy": "cid",
                },
                timeout=60,
            )
            resp.raise_for_status()
            try:
                body = resp.json()
            except Exception:
                body = {}
            entries = (body.get("defects") or []) if isinstance(body, dict) else []
            for d in entries:
                if not isinstance(d, dict):
                    continue
                try:
                    cid = int(d.get("cid"))
                except (TypeError, ValueError):
                    continue
                cid_map[cid] = {
                    "line": _to_int(d.get("lineNumber")),
                    "checker": str(d.get("checkerName") or ""),
                    "file": str(d.get("filePathname") or ""),
                    "function": str(d.get("functionDisplayName") or ""),
                    "type": str(d.get("displayType") or ""),
                    "severity": str(d.get("displayImpact") or ""),
                }
            count = len(entries)
            if count < page:
                break
            offset += count
        return cid_map
