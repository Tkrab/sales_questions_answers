$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$mongod = Get-ChildItem -Path (Join-Path $root ".tools") -Recurse -Filter mongod.exe | Select-Object -First 1
if (-not $mongod) { throw "mongod.exe not found under .tools" }
$db = Join-Path $root ".mongo-data"
New-Item -ItemType Directory -Force -Path $db | Out-Null
& $mongod.FullName --dbpath $db --bind_ip 127.0.0.1 --port 27017 --logpath (Join-Path $db "mongod.log")
