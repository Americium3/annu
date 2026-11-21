"""Minimal Databricks SQL Statement Execution API client (stdlib only).

Environment:
  DATABRICKS_HOST          e.g. https://dbc-xxxx.cloud.databricks.com
  DATABRICKS_TOKEN         personal access token (any placeholder works behind a
                           credential-injecting proxy)
  DATABRICKS_WAREHOUSE_ID  SQL warehouse id
"""
from __future__ import annotations

import json
import os
import time
import urllib.request


class DatabricksSQL:
    def __init__(self, host: str | None = None, token: str | None = None, warehouse_id: str | None = None):
        self.host = (host or os.environ["DATABRICKS_HOST"]).rstrip("/")
        if not self.host.startswith("http"):
            self.host = "https://" + self.host
        self.token = token or os.environ.get("DATABRICKS_TOKEN", "placeholder")
        self.warehouse_id = warehouse_id or os.environ["DATABRICKS_WAREHOUSE_ID"]

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.host + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)

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
