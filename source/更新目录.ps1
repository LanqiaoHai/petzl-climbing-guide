# Re-crawl current public Petzl categories. Requires Python 3.10+, no pip packages.
$ErrorActionPreference = 'Stop'
$taskPythonCandidates = @(
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
$taskPython = $taskPythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $taskPython) {
    $taskPythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($taskPythonCommand -and $taskPythonCommand.Source -notlike '*WindowsApps*') { $taskPython = $taskPythonCommand.Source }
}
if (-not $taskPython) { throw 'Python 3.10+ is required. Install Python, then run this script again.' }
& $taskPython -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required.' }

$taskBackup = Join-Path $PSScriptRoot ('_抓取校验资料\备份\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $taskBackup -Force | Out-Null
$taskGenerated = @(
    'index.html', 'catalog.json', 'Petzl攀岩教程目录.md', 'Petzl攀岩教程目录.csv',
    '覆盖与链接核验.json', 'crawl_snapshot.json', 'selected_articles.json',
    'verification.json', 'selection_report.json', 'titles_for_translation.json',
    'robots_snapshot.txt', 'title_translations.json', 'resources.json', '使用说明.md'
)
$taskExisting = @{}
foreach ($taskName in $taskGenerated) {
    $taskFile = Join-Path $PSScriptRoot $taskName
    $taskExisting[$taskName] = Test-Path -LiteralPath $taskFile
    if ($taskExisting[$taskName]) { Copy-Item -LiteralPath $taskFile -Destination (Join-Path $taskBackup $taskName) }
}
Push-Location $PSScriptRoot
try {
    & $taskPython -X utf8 (Join-Path $PSScriptRoot 'crawl_petzl.py') --refresh
    if ($LASTEXITCODE -ne 0) { throw 'Crawl failed or a category was incomplete. Previous catalogue is preserved.' }
    & $taskPython -X utf8 (Join-Path $PSScriptRoot 'verify_links.py') --refresh
    if ($LASTEXITCODE -ne 0) { throw 'Link verification failed. See verification_failure.json for details.' }
    & $taskPython -X utf8 (Join-Path $PSScriptRoot 'assemble_catalog.py')
    if ($LASTEXITCODE -ne 0) { throw 'Catalogue assembly failed.' }
    & $taskPython -X utf8 (Join-Path $PSScriptRoot 'build_ui.py')
    if ($LASTEXITCODE -ne 0) { throw 'HTML generation failed.' }
    & $taskPython -X utf8 (Join-Path $PSScriptRoot 'package_catalog.py')
    if ($LASTEXITCODE -ne 0) { throw 'Catalogue packaging failed.' }
    Write-Host 'Updated directory, instructions and current-date ZIP. New titles without Chinese mappings are labelled as pending translation.'
    Write-Host ('Backup: ' + $taskBackup)
}
catch {
    foreach ($taskName in $taskGenerated) {
        $taskSaved = Join-Path $taskBackup $taskName
        $taskDestination = Join-Path $PSScriptRoot $taskName
        if ($taskExisting[$taskName]) {
            Copy-Item -LiteralPath $taskSaved -Destination $taskDestination -Force
        }
        elseif (Test-Path -LiteralPath $taskDestination) {
            # Every destination is an explicitly listed filename under PSScriptRoot.
            Remove-Item -LiteralPath $taskDestination -Force
        }
    }
    throw
}
finally { Pop-Location }

