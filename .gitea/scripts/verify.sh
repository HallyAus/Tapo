#!/usr/bin/env bash
set -euo pipefail
unset SOURCE_TOKEN GITEA_TOKEN GITHUB_TOKEN
python3 - <<'PY'
import ast,json,pathlib,re
component=pathlib.Path('custom_components/tapo_cloud')
sources=list(component.rglob('*.py'))
assert sources
for path in sources:
    ast.parse(path.read_text(encoding='utf8'),filename=str(path))
json_files=list(component.rglob('*.json'))+[pathlib.Path('hacs.json')]
for path in json_files:
    json.loads(path.read_text(encoding='utf8'))
manifest=json.loads((component/'manifest.json').read_text())
assert manifest['domain']=='tapo_cloud' and re.fullmatch(r'\d+\.\d+\.\d+',manifest['version'])
print(json.dumps({'python_sources_parsed':len(sources),'json_files_parsed':len(json_files),'integration_imported':False,'physical_or_account_requests':0}))
PY
