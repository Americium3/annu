"""Minimal Databricks SQL Statement Execution API client (stdlib only).

Environment:
  DATABRICKS_HOST          e.g. https://dbc-xxxx.cloud.databricks.com
  DATABRICKS_TOKEN         personal access token (any placeholder works behind a
                           credential-injecting proxy)
  DATABRICKS_CLIENT_ID /   OAuth machine-to-machine credentials, used when no
  DATABRICKS_CLIENT_SECRET token is set (Databricks Apps inject these for the
                           app's own service principal)
  DATABRICKS_WAREHOUSE_ID  SQL warehouse id
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request


class DatabricksSQL:
    def __init__(self, host: str | None = None, token: str | None = None, warehouse_id: str | None = None):
        self.host = (host or os.environ["DATABRICKS_HOST"]).rstrip("/")
        if not self.host.startswith("http"):
            self.host = "https://" + self.host
        self._static_token = token or os.environ.get("DATABRICKS_TOKEN")
        self._client_id = os.environ.get("DATABRICKS_CLIENT_ID")
        self._client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET")
        self._oauth_token: str | None = None
        self._oauth_expires = 0.0
        self.warehouse_id = warehouse_id or os.environ["DATABRICKS_WAREHOUSE_ID"]

    @property
    def token(self) -> str:
        """A personal token if one is set; otherwise an OAuth token for the app's service principal."""
        if self._static_token:
            return self._static_token
        if not (self._client_id and self._client_secret):
            return "placeholder"
        if self._oauth_token is None or time.time() > self._oauth_expires - 60:
            body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "all-apis"}).encode()
            req = urllib.request.Request(f"{self.host}/oidc/v1/token", method="POST", data=body,
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            basic = f"{self._client_id}:{self._client_secret}".encode()
            import base64
            req.add_header("Authorization", "Basic " + base64.b64encode(basic).decode())
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            self._oauth_token = data["access_token"]
            self._oauth_expires = time.time() + float(data.get("expires_in", 3600))
        return self._oauth_token

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.host + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)

    def put_file(self, volume_path: str, data: bytes) -> None:
        """Upload bytes to a Unity Catalog volume path (Files API), overwriting any existing file."""
        req = urllib.request.Request(
            f"{self.host}/api/2.0/fs/files{volume_path}?overwrite=true",
            method="PUT",
            data=data,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/octet-stream"},
        )
        with urllib.request.urlopen(req, timeout=300):
            pass

    def query(self, statement: str) -> tuple[list[str], list[list]]:
        """Run a read-only statement and return (column_names, rows). Results must fit INLINE (25 MiB)."""
        res = self._request("POST", "/api/2.0/sql/statements", {
            "statement": statement,
            "warehouse_id": self.warehouse_id,
            "wait_timeout": "50s",
            "disposition": "INLINE",
            "format": "JSON_ARRAY",
        })
        while res["status"]["state"] in ("PENDING", "RUNNING"):
            time.sleep(2)
            res = self._request("GET", f"/api/2.0/sql/statements/{res['statement_id']}")
        if res["status"]["state"] != "SUCCEEDED":
            raise RuntimeError(f"Statement failed: {json.dumps(res['status'])}")
        cols = [c["name"] for c in res["manifest"]["schema"]["columns"]]
        result = res.get("result") or {}
        rows = list(result.get("data_array") or [])
        link = result.get("next_chunk_internal_link")
        while link:
            chunk = self._request("GET", link)
            rows += chunk.get("data_array") or []
            link = chunk.get("next_chunk_internal_link")
        return cols, rows
