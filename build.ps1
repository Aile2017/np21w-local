<#
 Build np21w with the local patches.
   1. read base.conf
   2. extract BASE_REF of the upstream repository into build\src
   3. apply patches\*.patch (git apply --ignore-whitespace: the .rc files are CRLF)
   4. remove SUPPORT_NPDISP_W2K from PreprocessorDefinitions of the np21 project
   5. build exe (np21 / np2, x64 / Win32) and the language DLLs
   6. collect them under out\
 Nothing outside this repository is touched; copy out\ into the bin directory yourself.
#>
param(
    [string]$MSBuild = 'C:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\MSBuild.exe',
    [switch]$SkipLanguage,
    [switch]$ExeOnlyX64        # np21x64w.exe only (quick build)
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$conf = @{}
Get-Content "$root\base.conf" | Where-Object { $_ -match '^\s*[A-Z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; $conf[$k.Trim()] = $v.Trim()
}
$repo = Join-Path $root $conf.BASE_REPO
if (-not (Test-Path "$repo\.git")) {
    $repo = "$root\build\upstream"
    if (-not (Test-Path "$repo\.git")) { git clone -q $conf.BASE_URL $repo; if ($LASTEXITCODE) { throw 'git clone failed' } }
    else { git -C $repo fetch -q origin }
}
$ref = $conf.BASE_REF
git -C $repo cat-file -e "$ref^{commit}" 2>$null
if ($LASTEXITCODE) { git -C $repo fetch -q origin; git -C $repo cat-file -e "$ref^{commit}"; if ($LASTEXITCODE) { throw "BASE_REF not found: $ref" } }

$src = "$root\build\src"
# mspdbsrv.exe (started by the compiler) keeps the previous build tree open
Get-Process mspdbsrv -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
if (Test-Path $src) { Remove-Item $src -Recurse -Force }
New-Item -ItemType Directory "$root\build" -Force | Out-Null
# local clone + checkout instead of "git archive | tar": bsdtar cannot extract the Japanese file name in LICENSES\
git clone -q --no-checkout $repo $src
if ($LASTEXITCODE) { throw 'git clone failed' }
git -C $src -c core.autocrlf=false checkout -q --detach $ref
if ($LASTEXITCODE) { throw 'git checkout failed' }
# keep $src\.git: build\ lives inside this repository, and git apply only patches paths under the repository it runs in

Push-Location $src
try {
    foreach ($p in Get-ChildItem "$root\patches\*.patch" | Sort-Object Name) {
        Write-Host "apply $($p.Name)"
        git -c core.autocrlf=false apply --ignore-whitespace --unsafe-paths -p1 $p.FullName   # the system gitconfig may set autocrlf=true, which rewrites patched files to CRLF
        if ($LASTEXITCODE) { throw "patch failed: $($p.Name)" }
    }
    # W2K npdisp is switched off (it is a script step, not a patch, so it does not conflict between versions)
    $proj = "$src\win9x\np21vs2019.vcxproj"
    $enc = New-Object System.Text.UTF8Encoding($true)
    $lines = [IO.File]::ReadAllText($proj) -split "(?<=\n)"
    $n = 0
    $out = foreach ($l in $lines) {
        if ($l -match '<PreprocessorDefinitions>' -and $l -match 'SUPPORT_NPDISP_W2K;') { $n++; $l -replace 'SUPPORT_NPDISP_W2K;', '' } else { $l }
    }
    [IO.File]::WriteAllText($proj, ($out -join ''), $enc)
    Write-Host "SUPPORT_NPDISP_W2K removed from $n PreprocessorDefinitions"

    function Invoke-Build($projFile, $platform, $extra) {
        & $MSBuild $projFile "-p:Configuration=Release" "-p:Platform=$platform" -m -nodeReuse:false -nologo -v:m @extra | Where-Object { $_ -notmatch 'warning' }
        if ($LASTEXITCODE) { throw "build failed: $projFile $platform" }
    }
    Set-Location "$src\win9x"
    Invoke-Build 'np21vs2019.vcxproj' 'x64' @()
    if (-not $ExeOnlyX64) {
        Invoke-Build 'np21vs2019.vcxproj' 'Win32' @()
        Invoke-Build 'np2vs2019.vcxproj' 'x64' @()
        Invoke-Build 'np2vs2019.vcxproj' 'Win32' @()
        if (-not $SkipLanguage) {
            foreach ($cp in 932, 1252, 936, 950) {
                Push-Location "resources\$cp"
                foreach ($pf in 'x64', 'Win32') { Invoke-Build "np2vs2008_$cp.vcxproj" $pf @('-p:PlatformToolset=v145') }
                Pop-Location
            }
        }
    }
} finally { Pop-Location }

$o = "$root\out"
if (Test-Path $o) { Remove-Item $o -Recurse -Force }
New-Item -ItemType Directory "$o\language" | Out-Null
foreach ($f in 'x64\Release\np21x64w.exe', 'Win32\Release\np21w.exe', 'x64\Release\np2x64w.exe', 'Win32\Release\np2w.exe') {
    if (Test-Path "$src\bin\$f") { Copy-Item "$src\bin\$f" $o }
}
Get-ChildItem "$src\bin\*\Release\np2*_*.dll" -ErrorAction SilentlyContinue | Copy-Item -Destination "$o\language"
Get-ChildItem $o -Recurse -File | ForEach-Object { '{0,10:N0}  {1}' -f $_.Length, $_.FullName.Substring($o.Length + 1) }
