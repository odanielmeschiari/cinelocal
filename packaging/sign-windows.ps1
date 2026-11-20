# Signs the Windows binaries with Azure Artifact Signing (SignTool + the Artifact Signing dlib).
# Smart App Control (Windows 11) blocks every unsigned program, so the app, its libraries and the installer must
# carry a signature from a trusted certificate authority.
#
#   sign-windows.ps1 -Setup                   download the tools and write the metadata (once per job)
#   sign-windows.ps1 -Folder dist\CineLocal   sign every .exe/.dll/.pyd of the folder that is not signed yet
#   sign-windows.ps1 -Path a.exe,b.exe        sign the given files (Inno Setup's SignTool calls this)
#
# Needs SIGN_ENDPOINT, SIGN_ACCOUNT and SIGN_PROFILE (account endpoint, account name, certificate profile) and a
# signed-in Azure session (azure/login in GitHub Actions, or `az login` locally).
param(
    [switch]$Setup,
    [string]$Folder,
    [string[]]$Path
)
$ErrorActionPreference = "Stop"

function Sign-Files([string[]]$Files) {
    for ($i = 0; $i -lt $Files.Count; $i += 40) {
        $batch = @($Files[$i..([Math]::Min($i + 39, $Files.Count - 1))])
        & $env:SIGNTOOL sign /v /fd SHA256 /tr "http://timestamp.acs.microsoft.com" /td SHA256 `
            /dlib $env:SIGN_DLIB /dmdf $env:SIGN_METADATA @batch
        if ($LASTEXITCODE -ne 0) { throw "signtool failed with exit code $LASTEXITCODE" }
    }
}

if ($Setup) {
    foreach ($name in "SIGN_ENDPOINT", "SIGN_ACCOUNT", "SIGN_PROFILE") {
        if (-not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) { throw "$name is not set" }
    }
    $root = Join-Path ($(if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP })) "signing"
    New-Item -ItemType Directory -Force $root | Out-Null
    $nuget = Join-Path $root "nuget.exe"
    Invoke-WebRequest "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe" -OutFile $nuget
    & $nuget install Microsoft.Windows.SDK.BuildTools -x -OutputDirectory $root | Out-Null
    & $nuget install Microsoft.ArtifactSigning.Client -x -OutputDirectory $root | Out-Null

    $signtool = Get-ChildItem $root -Recurse -Filter signtool.exe | Where-Object { $_.FullName -match "\\x64\\" } |
        Sort-Object FullName -Descending | Select-Object -First 1
    $dlib = Get-ChildItem $root -Recurse -Filter Azure.CodeSigning.Dlib.dll | Where-Object { $_.FullName -match "\\x64\\" } |
        Select-Object -First 1
    if (-not $signtool) { throw "signtool.exe not found after installing Microsoft.Windows.SDK.BuildTools" }
    if (-not $dlib) { throw "Azure.CodeSigning.Dlib.dll not found after installing Microsoft.ArtifactSigning.Client" }

    $metadata = Join-Path $root "metadata.json"
    @{
        Endpoint               = $env:SIGN_ENDPOINT
        CodeSigningAccountName = $env:SIGN_ACCOUNT
        CertificateProfileName = $env:SIGN_PROFILE
    } | ConvertTo-Json | Set-Content -Encoding ASCII $metadata

    $vars = @{ SIGNTOOL = $signtool.FullName; SIGN_DLIB = $dlib.FullName; SIGN_METADATA = $metadata }
    foreach ($k in $vars.Keys) {
        Set-Item "env:$k" $vars[$k]
        if ($env:GITHUB_ENV) { Add-Content $env:GITHUB_ENV "$k=$($vars[$k])" }   # for the next steps of the job
    }
    Write-Host "signtool: $($signtool.FullName)"
    Write-Host "dlib:     $($dlib.FullName)"
}
elseif ($Folder) {
    # Third-party files that already carry a valid signature (Python, Qt, VLC...) are left as they are.
    $todo = Get-ChildItem $Folder -Recurse -File -Include *.exe, *.dll, *.pyd |
        Where-Object { (Get-AuthenticodeSignature $_.FullName).Status -eq "NotSigned" } |
        ForEach-Object { $_.FullName }
    Write-Host "Signing $(@($todo).Count) file(s) in $Folder"
    if (@($todo).Count -gt 0) { Sign-Files @($todo) }
}
elseif ($Path) {
    Sign-Files $Path
}
else {
    throw "Use -Setup, -Folder <dir> or -Path <files>"
}
