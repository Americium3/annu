#!/usr/bin/env bash
# Build CarePath and deploy it to Databricks Apps: Node serves the site and runs
# the Python recommender, which reads the live tables as the app's own service
# principal. Everyone in the Databricks account can open it (after signing in;
# Databricks Apps cannot be public).
#
#   DATABRICKS_HOST=https://<workspace>.cloud.databricks.com \
#   DATABRICKS_TOKEN=<personal access token> \
#   web/databricks-app/deploy.sh
#
# Optional: APP_NAME (carepath), WAREHOUSE_ID, SCHEMA (workspace.cardinal_virtues),
# LLM_ENDPOINT (databricks-meta-llama-3-3-70b-instruct; must match app.yaml),
# USE_DEMO=true to ship the demo-data build without the recommender.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
: "${DATABRICKS_HOST:?set DATABRICKS_HOST}"
APP_NAME="${APP_NAME:-carepath}"
WAREHOUSE_ID="${WAREHOUSE_ID:-01562a1cdb8d5257}"
SCHEMA="${SCHEMA:-workspace.cardinal_virtues}"
USE_DEMO="${USE_DEMO:-false}"
LLM_ENDPOINT="${LLM_ENDPOINT:-databricks-meta-llama-3-3-70b-instruct}"
API="${DATABRICKS_HOST%/}/api/2.0"
AUTH=(-H "Authorization: Bearer ${DATABRICKS_TOKEN:-proxy-injected}" -H "Content-Type: application/json")
call() { curl -fsS "${AUTH[@]}" "$@"; }
json() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

echo "1/7 Building the web app (demo data: $USE_DEMO)"
(cd "$REPO/web" && VITE_USE_DEMO="$USE_DEMO" pnpm build >/dev/null)

STAGE="$(mktemp -d)"
cp -r "$REPO/web/dist" "$STAGE/dist"
cp "$HERE/server.js" "$HERE/package.json" "$HERE/app.yaml" "$STAGE/"
if [ "$USE_DEMO" != "true" ]; then
  mkdir -p "$STAGE/backend" "$STAGE/pipeline"
  cp "$REPO"/backend/*.py "$STAGE/backend/"
  cp "$REPO/web/src/data/lexicon.json" "$STAGE/backend/lexicon.json"   # shared with the web app (backend/nlu.py)
  cp "$REPO/data/tags/alias_table.csv" "$STAGE/backend/alias_table.csv"   # symptom / disease names (backend/nlu.py)
  cp "$REPO/backend/requirements.txt" "$STAGE/requirements.txt"
  cp "$REPO/pipeline/databricks_sql.py" "$STAGE/pipeline/"
fi

ME=$(call "$API/preview/scim/v2/Me" | json 'd["userName"]')
DEST="/Workspace/Users/$ME/apps/$APP_NAME"
echo "2/7 Uploading to $DEST"
call -X POST "$API/workspace/delete" -d "{\"path\":\"$DEST\",\"recursive\":true}" >/dev/null 2>&1 || true
(cd "$STAGE" && find . -type f -print0) | while IFS= read -r -d '' f; do
  rel="${f#./}"
  call -X POST "$API/workspace/mkdirs" -d "{\"path\":\"$DEST/$(dirname "$rel")\"}" >/dev/null
  python3 - "$STAGE/$rel" "$DEST/$rel" > "$STAGE.import.json" <<'PY'
import base64, json, sys
print(json.dumps({"path": sys.argv[2], "format": "RAW", "overwrite": True,
                  "content": base64.b64encode(open(sys.argv[1], "rb").read()).decode()}))
PY
  call -X POST "$API/workspace/import" --data-binary @"$STAGE.import.json" >/dev/null
done

resources() {  # $1 = LLM endpoint name, or empty for none
python3 - "$WAREHOUSE_ID" "$SCHEMA" "$USE_DEMO" "$1" <<'PY'
import json, sys
wh, schema, demo, llm = sys.argv[1:]
res = [{"name": "sql-warehouse", "sql_warehouse": {"id": wh, "permission": "CAN_USE"}}]
if demo != "true":
    for t in ["serving_service_index", "serving_facilities", "ref_service_tags", "pincode_reference"]:
        res.append({"name": t.replace("_", "-"),
                    "uc_securable": {"securable_full_name": f"{schema}.{t}", "securable_type": "TABLE", "permission": "SELECT"}})
    if llm:  # lets the app's identity query the language model used for free-text understanding
        res.append({"name": "llm-endpoint", "serving_endpoint": {"name": llm, "permission": "CAN_QUERY"}})
print(json.dumps(res))
PY
}
RESOURCES=$(resources "$LLM_ENDPOINT")
NO_LLM_RESOURCES=$(resources "")
set_resources() {  # $1 = resources JSON
  if call "$API/apps/$APP_NAME" >/dev/null 2>&1; then
    call -X PATCH "$API/apps/$APP_NAME" -d "{\"name\":\"$APP_NAME\",\"resources\":$1}" >/dev/null
  else
    call -X POST "$API/apps" -d "{\"name\":\"$APP_NAME\",\"description\":\"CarePath: find a hospital that offers the care you need\",\"resources\":$1}" >/dev/null
  fi
}
echo "3/7 Creating or updating app $APP_NAME"
if ! set_resources "$RESOURCES"; then
  # The workspace may not offer this model endpoint: the app still works, understanding requests by rules only.
  echo "   could not attach model endpoint $LLM_ENDPOINT; continuing with rules-only understanding"
  set_resources "$NO_LLM_RESOURCES"
fi

echo "4/7 Waiting for app compute"
for _ in $(seq 1 90); do
  state=$(call "$API/apps/$APP_NAME" | json 'd.get("compute_status",{}).get("state","")')
  [ "$state" = "ACTIVE" ] && break
  if [ "$state" = "STOPPED" ]; then call -X POST "$API/apps/$APP_NAME/start" >/dev/null; fi
  sleep 10
done
echo "   compute: $state"

if [ "$USE_DEMO" != "true" ]; then
  echo "5/7 Granting the app read access to $SCHEMA"
  SP=$(call "$API/apps/$APP_NAME" | json 'd["service_principal_client_id"]')
  CATALOG="${SCHEMA%%.*}"
  for stmt in "GRANT USE CATALOG ON CATALOG \`$CATALOG\` TO \`$SP\`" \
              "GRANT USE SCHEMA ON SCHEMA $SCHEMA TO \`$SP\`" \
              "GRANT SELECT ON SCHEMA $SCHEMA TO \`$SP\`"; do
    state=$(call -X POST "$API/sql/statements" -d "$(python3 -c 'import json,sys;print(json.dumps({"statement":sys.argv[1],"warehouse_id":sys.argv[2],"wait_timeout":"50s"}))' "$stmt" "$WAREHOUSE_ID")" | json 'd["status"]["state"]')
    echo "   $stmt -> $state"
  done
fi

echo "6/7 Deploying"
DEP=$(call -X POST "$API/apps/$APP_NAME/deployments" -d "{\"source_code_path\":\"$DEST\",\"mode\":\"SNAPSHOT\"}" | json 'd["deployment_id"]')
for _ in $(seq 1 60); do
  st=$(call "$API/apps/$APP_NAME/deployments/$DEP" | json 'd.get("status",{}).get("state","")')
  case "$st" in SUCCEEDED|FAILED|CANCELLED) break ;; esac
  sleep 10
done
echo "   deployment: $st"

echo "7/7 Opening the app to everyone in the Databricks account"
call -X PATCH "$API/permissions/apps/$APP_NAME" \
  -d '{"access_control_list":[{"group_name":"account users","permission_level":"CAN_USE"}]}' >/dev/null \
  || call -X PATCH "$API/permissions/apps/$APP_NAME" \
       -d '{"access_control_list":[{"group_name":"users","permission_level":"CAN_USE"}]}' >/dev/null
call "$API/apps/$APP_NAME" | json '"App URL: " + str(d.get("url"))'
rm -rf "$STAGE" "$STAGE.import.json"
