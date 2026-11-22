#!/usr/bin/env bash
# Build the CarePath web app and deploy it to Databricks Apps.
#
#   DATABRICKS_HOST=https://<workspace>.cloud.databricks.com \
#   DATABRICKS_TOKEN=<personal access token> \
#   APP_NAME=carepath web/databricks-app/deploy.sh
#
# Builds with demo data by default (no backend needed). Set USE_DEMO=false to
# build against /api once a backend is reachable from the app.
set -euo pipefail
cd "$(dirname "$0")"
: "${DATABRICKS_HOST:?set DATABRICKS_HOST}"
APP_NAME="${APP_NAME:-carepath}"
USE_DEMO="${USE_DEMO:-true}"
AUTH=(-H "Authorization: Bearer ${DATABRICKS_TOKEN:-proxy-injected}")
API="${DATABRICKS_HOST%/}/api/2.0"

echo "Building web (demo data: ${USE_DEMO})"
(cd .. && VITE_USE_DEMO="$USE_DEMO" pnpm build)
rm -rf dist && cp -r ../dist dist

ME=$(curl -fsS "${AUTH[@]}" "$API/preview/scim/v2/Me" | python3 -c 'import sys,json;print(json.load(sys.stdin)["userName"])')
DEST="/Workspace/Users/$ME/apps/$APP_NAME"
echo "Uploading to $DEST"
curl -fsS "${AUTH[@]}" -X POST "$API/workspace/delete" -d "{\"path\":\"$DEST\",\"recursive\":true}" >/dev/null 2>&1 || true
while IFS= read -r -d '' f; do
  rel="${f#./}"
  dir="$DEST/$(dirname "$rel")"
  curl -fsS "${AUTH[@]}" -X POST "$API/workspace/mkdirs" -d "{\"path\":\"$dir\"}" >/dev/null
  python3 - "$f" "$DEST/$rel" > /tmp/carepath-import.json <<'PY'
import base64, json, sys
src, dest = sys.argv[1], sys.argv[2]
print(json.dumps({"path": dest, "format": "RAW", "overwrite": True,
                  "content": base64.b64encode(open(src, "rb").read()).decode()}))
PY
  curl -fsS "${AUTH[@]}" -X POST "$API/workspace/import" -H "Content-Type: application/json" \
    --data-binary @/tmp/carepath-import.json >/dev/null
done < <(find . -type f \( -path './dist/*' -o -name server.js -o -name package.json -o -name app.yaml \) -print0)

if ! curl -fsS "${AUTH[@]}" "$API/apps/$APP_NAME" >/dev/null 2>&1; then
  echo "Creating app $APP_NAME"
  curl -fsS "${AUTH[@]}" -X POST "$API/apps" \
    -d "{\"name\":\"$APP_NAME\",\"description\":\"CarePath: find a hospital that offers the care you need\"}" >/dev/null
fi
echo "Waiting for app compute"
for _ in $(seq 1 60); do
  state=$(curl -fsS "${AUTH[@]}" "$API/apps/$APP_NAME" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("compute_status",{}).get("state",""))')
  [ "$state" = "ACTIVE" ] && break
  sleep 10
done
echo "Deploying"
curl -fsS "${AUTH[@]}" -X POST "$API/apps/$APP_NAME/deployments" \
  -d "{\"source_code_path\":\"$DEST\",\"mode\":\"SNAPSHOT\"}" >/dev/null
curl -fsS "${AUTH[@]}" "$API/apps/$APP_NAME" | python3 -c 'import sys,json;print("App URL:", json.load(sys.stdin).get("url"))'
