# Shared PowerShell 7 configuration of dev-kit (Windows). Dot-sourced from
# $PROFILE, which keeps the machine-specific lines. Anything missing (a module,
# starship, WSL) is skipped, so the shell always starts without error.

$DevKitTerminal = Split-Path -Parent $PSScriptRoot

# Completion modules; posh-git's prompt is replaced by starship below
foreach ($module in 'posh-dotnet', 'posh-git', 'PSKubectlCompletion', 'DockerCompletion', 'npm-completion') {
    Import-Module $module -ErrorAction SilentlyContinue
}

# History search on Up/Down, predictions from history and plugins in a list
if (Get-Module PSReadLine) {
    Set-PSReadLineKeyHandler -Key UpArrow -Function HistorySearchBackward
    Set-PSReadLineKeyHandler -Key DownArrow -Function HistorySearchForward
    Set-PSReadLineOption -PredictionSource HistoryAndPlugin
    Set-PSReadLineOption -PredictionViewStyle ListView
    Set-PSReadLineOption -HistorySearchCursorMovesToEnd
}

# Unix commands run through WSL
if ((Get-Command wsl.exe -ErrorAction SilentlyContinue) -and (Get-Command Import-WslCommand -ErrorAction SilentlyContinue)) {
    Import-WslCommand "apt", "awk", "find", "grep", "head", "less", "ls", "man", "sed", "seq", "ssh", "sudo", "tail", "touch", "wget", "curl", "zsh", "bash", "shell", "which", "whois", "df", "du"
}

# Git, same names as on the Mac. The built-in gl (Get-Location) and gp
# (Get-ItemProperty) aliases would win over the functions: remove them.
Remove-Item Alias:gl, Alias:gp -Force -ErrorAction SilentlyContinue

function gr { git rebase @args }
function gs { git status @args }
function gl { git log --oneline @args }
function glog { git log --oneline @args }
function gp { git push @args }
function gpf { git push --force-with-lease @args }

# origin's default branch (origin/main), else origin/main or origin/master
function Get-DevKitMainBranch {
    $default = git rev-parse --abbrev-ref --quiet origin/HEAD 2> $null
    if ($LASTEXITCODE -eq 0 -and $default) { return $default }
    git rev-parse --verify --quiet origin/main *> $null
    if ($LASTEXITCODE -eq 0) { 'origin/main' } else { 'origin/master' }
}

# The Git rule of AGENTS.md: fetch, then rebase on origin's default branch, local changes kept
function grim { git fetch --quiet && git rebase -i --autostash (Get-DevKitMainBranch) @args }
function grum { git fetch --quiet && git rebase --autostash (Get-DevKitMainBranch) @args }

# Docker Compose
function up { docker compose up -d @args }
function down { docker compose down @args }
function logs { docker compose logs @args }

# .NET aliases, only in a .NET project: a .sln, .csproj or .fsproj in the
# current folder or a parent up to the repository root (outside a repository,
# the current folder only).
$DevKitDotnet = [ordered]@{ dw = 'watch'; db = 'build'; dc = 'clean'; dt = 'test'; dr = 'run' }

function Test-DevKitDotnetProject {
    if ((Get-Location).Provider.Name -ne 'FileSystem') { return $false }
    $dir = (Get-Location).ProviderPath
    $root = git rev-parse --show-toplevel 2>$null
    $root = if ($LASTEXITCODE -eq 0 -and $root) { [IO.Path]::GetFullPath($root) } else { $dir }
    while ($dir) {
        foreach ($pattern in '*.sln', '*.csproj', '*.fsproj') {
            try {
                if ([IO.Directory]::EnumerateFiles($dir, $pattern).GetEnumerator().MoveNext()) { return $true }
            } catch { return $false }  # unreadable folder
        }
        if ($dir.TrimEnd('\', '/') -eq $root.TrimEnd('\', '/')) { return $false }
        $dir = [IO.Path]::GetDirectoryName($dir)
    }
    $false
}

function Update-DevKitDotnetAliases {
    $inProject = Test-DevKitDotnetProject
    foreach ($name in $DevKitDotnet.Keys) {
        if ($inProject) {
            Set-Item "Function:global:$name" -Value ([scriptblock]::Create("dotnet $($DevKitDotnet[$name]) @args"))
        } else {
            Remove-Item "Function:$name" -ErrorAction SilentlyContinue
        }
    }
}

# On every change of folder (cd, Push-Location…): .NET aliases, and the
# folder's .env.ps1 (per-project environment variables) when it has one.
$DevKitPreviousLocationAction = $ExecutionContext.SessionState.InvokeCommand.LocationChangedAction
$ExecutionContext.SessionState.InvokeCommand.LocationChangedAction = {
    param($source, $eventArgs)
    $exitCode = $global:LASTEXITCODE
    try {
        if ($DevKitPreviousLocationAction) { & $DevKitPreviousLocationAction $source $eventArgs }
        Update-DevKitDotnetAliases
        if ((Get-Location).Provider.Name -eq 'FileSystem') {
            $envFile = Join-Path (Get-Location).ProviderPath '.env.ps1'
            if (Test-Path -LiteralPath $envFile) {
                Write-Host "🔄 Loading .env.ps1..."
                . $envFile
            }
        }
    } finally {
        $global:LASTEXITCODE = $exitCode
    }
}
Update-DevKitDotnetAliases

# Background fetch, at most every 5 minutes per repository, so that the prompt
# knows when a pull is needed. Silent, never asks for credentials.
function Start-DevKitFetch {
    $gitDir = git rev-parse --absolute-git-dir 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $gitDir) { return }
    if (-not (git remote 2>$null)) { return }
    $fetchHead = Join-Path $gitDir 'FETCH_HEAD'
    if ((Test-Path -LiteralPath $fetchHead) -and (Get-Item -LiteralPath $fetchHead).LastWriteTime -gt (Get-Date).AddMinutes(-5)) { return }
    if (Test-Path -LiteralPath $fetchHead) { (Get-Item -LiteralPath $fetchHead).LastWriteTime = Get-Date }
    else { New-Item -ItemType File -Path $fetchHead -Force | Out-Null }
    $saved = $env:GIT_TERMINAL_PROMPT, $env:GIT_SSH_COMMAND
    $env:GIT_TERMINAL_PROMPT = '0'
    if (-not $env:GIT_SSH_COMMAND) { $env:GIT_SSH_COMMAND = 'ssh -o BatchMode=yes' }
    try {
        Start-Process git -ArgumentList 'fetch', '--quiet' -WorkingDirectory (Get-Location).ProviderPath -WindowStyle Hidden
    } finally {
        $env:GIT_TERMINAL_PROMPT, $env:GIT_SSH_COMMAND = $saved
    }
}

# Terminal title: the project (nearest folder upward holding a .git, folder or
# file) and, below its root, the current folder's name; elsewhere the path,
# with ~ for the home folder. No git process: it runs at every prompt.
function Get-DevKitTitle {
    $location = Get-Location
    if ($location.Provider.Name -ne 'FileSystem') { return $location.Path }
    $dir = $location.ProviderPath
    $root = $dir
    while ($root -and -not (Test-Path -LiteralPath (Join-Path $root '.git'))) {
        $root = [IO.Path]::GetDirectoryName($root)
    }
    if ($root) {
        $name = Split-Path -Leaf $root
        if ($root -eq $dir) { return $name }
        return "$name : $(Split-Path -Leaf $dir)"
    }
    $homeDir = $HOME.TrimEnd('\', '/')
    if ($dir -eq $homeDir) { return '~' }
    if ($dir.StartsWith("$homeDir\", [StringComparison]::OrdinalIgnoreCase)) { return '~' + $dir.Substring($homeDir.Length) }
    $dir
}

function Update-DevKitTitle {
    try { $Host.UI.RawUI.WindowTitle = Get-DevKitTitle } catch { }  # no console: no title
}

# Prompt shared with the Mac: terminal/starship.toml. Starship saves
# $LASTEXITCODE before calling Invoke-Starship-PreCommand.
if (Get-Command starship -ErrorAction SilentlyContinue) {
    $env:STARSHIP_CONFIG = Join-Path $DevKitTerminal 'starship.toml'
    function Invoke-Starship-PreCommand { Update-DevKitTitle; Start-DevKitFetch }
    Invoke-Expression (& starship init powershell)
} else {
    $DevKitPreviousPrompt = $function:prompt
    function prompt { Update-DevKitTitle; & $DevKitPreviousPrompt }
}
