[CmdletBinding()]
param(
    [switch]$Setup,
    [switch]$ShowToken,
    [switch]$RebuildExtension
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

$script:RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:DotEnvPath = Join-Path $script:RepoRoot ".env"
$script:BackendUrl = "http://127.0.0.1:8765"
$script:SupportedEnvironmentKeys = @(
    "MEMORA_ENV", "MEMORA_LOG_LEVEL", "MEMORA_DATABASE_URL", "MEMORA_CORS_ORIGINS",
    "MEMORA_LOCAL_TOKEN", "MEMORA_USER_ID", "MEMORA_EMBEDDING_PROVIDER",
    "OPENAI_API_KEY", "OPENAI_EMBEDDING_MODEL", "MEMORA_SYNTHESIS_PROVIDER",
    "MEMORA_SYNTHESIS_MODEL", "MEMORA_FACT_PROVIDER", "MEMORA_RELEVANCE_MIN_SIMILARITY",
    "MEMORA_PDF_MAX_FILES", "MEMORA_PDF_MAX_FILE_BYTES", "MEMORA_PDF_MAX_TOTAL_BYTES",
    "MEMORA_PDF_MAX_PAGES", "MEMORA_PDF_MAX_TEXT_CHARS", "MEMORA_PDF_MAX_CHUNKS",
    "MEMORA_CHATGPT_MAX_UPLOAD_BYTES", "MEMORA_CHATGPT_MAX_UNCOMPRESSED_BYTES",
    "MEMORA_CHUNK_SIZE_TOKENS", "MEMORA_CHUNK_OVERLAP_TOKENS", "MEMORA_RETRIEVAL_LIMIT",
    "MEMORA_CONTEXT_MAX_CHARS", "MEMORA_RETRIEVAL_RATE_LIMIT",
    "MEMORA_RETRIEVAL_RATE_WINDOW_SECONDS", "MEMORA_IMPORT_RATE_LIMIT",
    "MEMORA_IMPORT_RATE_WINDOW_SECONDS"
)

function Write-Step([string]$Message) { Write-Host "  [ok] $Message" -ForegroundColor Green }
function Write-Info([string]$Message) { Write-Host "  [..] $Message" -ForegroundColor Cyan }
function Stop-Launcher([string]$Message, [string]$Action) {
    Write-Host "`nMemora could not start: $Message" -ForegroundColor Red
    if ($Action) { Write-Host $Action -ForegroundColor Yellow }
    exit 1
}

function Test-VersionAtLeast([version]$Actual, [version]$Minimum) {
    return $Actual -ge $Minimum
}

function ConvertTo-ToolVersion([string]$Output, [string]$ToolName) {
    $match = [regex]::Match($Output, '^\s*(?:Python\s+)?v?(\d+\.\d+(?:\.\d+)?)\s*$',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $match.Success) {
        throw "$ToolName version output was malformed. Expected a value such as Python 3.11.9, v20.0.0, or 10.0.0."
    }
    return [version]$match.Groups[1].Value
}

function Get-CommandVersion(
    [string]$Command,
    [string[]]$Arguments,
    [string]$ToolName = "Executable"
) {
    if (-not (Test-Path -LiteralPath $Command -PathType Leaf)) {
        throw "$ToolName executable was not found at the discovered path: $Command"
    }
    try {
        # Capture the native process completely before reading LASTEXITCODE. Piping
        # through Select-Object -First can close stdout early and produce a false
        # nonzero native exit status in Windows PowerShell 5.1.
        $output = @(& $Command @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } catch {
        throw "$ToolName executable was found but invocation failed: $Command"
    }
    if ($exitCode -ne 0) {
        throw "$ToolName executable was found but invocation failed with exit code $exitCode."
    }
    $text = (($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine).Trim()
    return ConvertTo-ToolVersion $text $ToolName
}

function Get-ApplicationPaths([string]$Name) {
    $commands = @(Get-Command $Name -All -CommandType Application -ErrorAction SilentlyContinue)
    $paths = [Collections.Generic.List[string]]::new()
    foreach ($command in $commands) {
        $path = [string]$command.Source
        if (-not [string]::IsNullOrWhiteSpace($path) -and -not $paths.Contains($path)) {
            $paths.Add($path)
        }
    }
    return @($paths)
}

function Select-VersionedExecutable(
    [string[]]$Candidates,
    [string[]]$Arguments,
    [string]$ToolName,
    [version]$MinimumVersion,
    [switch]$SkipWindowsAppsAliases
) {
    $existing = 0
    $invocationFailures = 0
    $malformedOutputs = 0
    $oldVersions = [Collections.Generic.List[version]]::new()
    $skippedAliases = 0
    foreach ($candidate in @($Candidates)) {
        if ([string]::IsNullOrWhiteSpace($candidate) -or
            -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $existing++
        if ($SkipWindowsAppsAliases -and $candidate -match '(?i)\\Microsoft\\WindowsApps\\') {
            $skippedAliases++
            Write-Verbose "Skipping Windows App Execution Alias candidate: $candidate"
            continue
        }
        try {
            $version = Get-CommandVersion $candidate $Arguments $ToolName
        } catch {
            if ($_.Exception.Message -match 'malformed') { $malformedOutputs++ }
            else { $invocationFailures++ }
            Write-Verbose "$ToolName candidate rejected: $candidate ($($_.Exception.Message))"
            continue
        }
        if ($MinimumVersion -and $version -lt $MinimumVersion) {
            $oldVersions.Add($version)
            Write-Verbose "$ToolName candidate below minimum: $candidate ($version)"
            continue
        }
        return [pscustomobject]@{ Path = [string]$candidate; Version = $version }
    }
    if (@($Candidates).Count -eq 0) { throw "No $ToolName command candidates were found on PATH." }
    if ($existing -eq 0) { throw "$ToolName command candidates were found, but none points to an existing executable." }
    if ($oldVersions.Count -gt 0 -and $invocationFailures -eq 0 -and $malformedOutputs -eq 0) {
        $highest = ($oldVersions | Sort-Object -Descending | Select-Object -First 1)
        throw "$ToolName candidates were found, but the highest usable version $highest is below required version $MinimumVersion."
    }
    if ($malformedOutputs -gt 0 -and $invocationFailures -eq 0) {
        throw "$ToolName candidates invoked, but their version output was malformed."
    }
    $aliasNote = if ($skippedAliases -gt 0) { " WindowsApps aliases were skipped." } else { "" }
    throw "$ToolName command candidates were found, but none invoked successfully.$aliasNote"
}

function Find-PythonInterpreter([string[]]$PythonCandidates, [string[]]$PyCandidates) {
    $pythonError = $null
    try {
        $selected = Select-VersionedExecutable $PythonCandidates @("--version") "Python" ([version]"3.11") -SkipWindowsAppsAliases
        return [pscustomobject]@{ Path = [string]$selected.Path; PrefixArguments = @(); Version = $selected.Version; Source = "python" }
    } catch { $pythonError = $_.Exception.Message }

    try {
        # -3 asks the Windows launcher for its default Python 3 interpreter; the
        # reported version is still enforced as 3.11 or newer.
        $selected = Select-VersionedExecutable $PyCandidates @("-3", "--version") "Python launcher" ([version]"3.11")
        return [pscustomobject]@{ Path = [string]$selected.Path; PrefixArguments = @("-3"); Version = $selected.Version; Source = "py" }
    } catch {
        $pyError = $_.Exception.Message
        if (@($PythonCandidates).Count -eq 0 -and @($PyCandidates).Count -eq 0) {
            throw "No Python command candidates were found, and the Windows py launcher is unavailable."
        }
        throw "$pythonError Windows py launcher fallback failed: $pyError"
    }
}

function Read-DotEnv([string]$Path) {
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $values }
    $lineNumber = 0
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        $lineNumber++
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $match = [regex]::Match($line, '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$')
        if (-not $match.Success) {
            throw ".env line $lineNumber must use KEY=VALUE syntax. PowerShell expressions are not allowed."
        }
        $name = $match.Groups[1].Value
        $value = $match.Groups[2].Value.Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            if ($value.Length -lt 2) { throw ".env line $lineNumber has an invalid quoted value." }
            $value = $value.Substring(1, $value.Length - 2)
        } elseif ($value.StartsWith('"') -or $value.StartsWith("'") -or
                  $value.EndsWith('"') -or $value.EndsWith("'")) {
            throw ".env line $lineNumber has unmatched quotes."
        }
        if ($script:SupportedEnvironmentKeys -contains $name) {
            $values[$name] = $value
        } else {
            Write-Verbose "Ignoring unsupported .env key: $name"
        }
    }
    return $values
}

function Import-DotEnv([string]$Path) {
    $values = Read-DotEnv $Path
    foreach ($name in $values.Keys) {
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, "Process"))) {
            [Environment]::SetEnvironmentVariable($name, [string]$values[$name], "Process")
        }
    }
}

function Set-DotEnvValue([string]$Path, [string]$Name, [string]$Value) {
    if ($Value -match '[\r\n]') { throw "$Name cannot contain a line break." }
    $lines = [Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $lines.AddRange([string[]][IO.File]::ReadAllLines($Path))
    }
    $replacement = "$Name=$Value"
    $found = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match ('^\s*' + [regex]::Escape($Name) + '\s*=')) {
            $lines[$index] = $replacement
            $found = $true
            break
        }
    }
    if (-not $found) { $lines.Add($replacement) }
    [IO.File]::WriteAllLines($Path, $lines, [Text.UTF8Encoding]::new($false))
}

function Set-BaseConfigurationDefaults {
    $defaults = [ordered]@{
        MEMORA_DATABASE_URL = "sqlite:///./memora.sqlite3"
        MEMORA_USER_ID = "demo-user"
        OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
        MEMORA_SYNTHESIS_MODEL = "gpt-5.6-luna"
    }
    foreach ($entry in $defaults.GetEnumerator()) {
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($entry.Key, "Process"))) {
            Set-DotEnvValue $script:DotEnvPath $entry.Key $entry.Value
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
        }
    }
}

function Remove-DotEnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $pattern = '^\s*' + [regex]::Escape($Name) + '\s*='
    $lines = @([IO.File]::ReadAllLines($Path) | Where-Object { $_ -notmatch $pattern })
    [IO.File]::WriteAllLines($Path, $lines, [Text.UTF8Encoding]::new($false))
}

function Test-ProviderConfigurationPresent {
    foreach ($name in @("MEMORA_EMBEDDING_PROVIDER", "MEMORA_SYNTHESIS_PROVIDER", "MEMORA_FACT_PROVIDER")) {
        if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, "Process"))) {
            return $true
        }
    }
    return $false
}

function Get-ProcessingMode {
    $embedding = [Environment]::GetEnvironmentVariable("MEMORA_EMBEDDING_PROVIDER", "Process")
    $synthesis = [Environment]::GetEnvironmentVariable("MEMORA_SYNTHESIS_PROVIDER", "Process")
    $facts = [Environment]::GetEnvironmentVariable("MEMORA_FACT_PROVIDER", "Process")
    if ([string]::IsNullOrWhiteSpace($embedding)) { $embedding = "local" }
    if ([string]::IsNullOrWhiteSpace($synthesis)) { $synthesis = "deterministic" }
    if ([string]::IsNullOrWhiteSpace($facts)) { $facts = $synthesis }
    $embedding = $embedding.Trim().ToLowerInvariant()
    $synthesis = $synthesis.Trim().ToLowerInvariant()
    $facts = $facts.Trim().ToLowerInvariant()
    if ($embedding -eq "openai" -and $synthesis -eq "openai" -and $facts -eq "openai") { return "Enhanced" }
    if ($embedding -eq "local" -and $synthesis -eq "deterministic" -and $facts -eq "deterministic") { return "Local" }
    return "Custom"
}

function Read-ProcessingModeChoice([scriptblock]$ReadChoice = { param($Prompt) Read-Host $Prompt }) {
    Write-Host "`nChoose how Memora should process memory:" -ForegroundColor White
    Write-Host "`n[1] Enhanced - Recommended" -ForegroundColor Cyan
    Write-Host "    Best intended Memora quality using OpenAI-powered semantic embeddings,"
    Write-Host "    MemoryFact extraction, and MemoryBrief synthesis. Requires an OpenAI API key."
    Write-Host "`n[2] Local" -ForegroundColor Cyan
    Write-Host "    No API key required. Best for testing and offline development."
    Write-Host "    Memory quality may differ from Enhanced mode."
    while ($true) {
        $choice = [string](& $ReadChoice "Select [1/2] (default: 1)")
        switch ($choice.Trim()) {
            "" { return "Enhanced" }
            "1" { return "Enhanced" }
            "2" { return "Local" }
            default { Write-Host "Please enter 1 or 2." -ForegroundColor Yellow }
        }
    }
}

function Resolve-ProcessingMode(
    [bool]$ConfigurationPresent,
    [string]$CurrentMode,
    [bool]$ReviewSetup,
    [scriptblock]$ReadChoice = { param($Prompt) Read-Host $Prompt },
    [scriptblock]$ReadKeep = { param($Prompt) Read-Host $Prompt }
) {
    if (-not $ConfigurationPresent) {
        return @{ Mode = Read-ProcessingModeChoice $ReadChoice; Changed = $true }
    }
    if (-not $ReviewSetup) { return @{ Mode = $CurrentMode; Changed = $false } }
    while ($true) {
        $keep = [string](& $ReadKeep "Current mode: $CurrentMode. Keep current mode? [Y/n]")
        if ([string]::IsNullOrWhiteSpace($keep) -or $keep -match '^(?i:y|yes)$') {
            return @{ Mode = $CurrentMode; Changed = $false }
        }
        if ($keep -match '^(?i:n|no)$') { break }
        Write-Host "Please enter Y or N." -ForegroundColor Yellow
    }
    return @{ Mode = Read-ProcessingModeChoice $ReadChoice; Changed = $true }
}

function Set-ProcessingMode([string]$Mode, [string]$Path) {
    $values = if ($Mode -eq "Enhanced") {
        [ordered]@{
            MEMORA_EMBEDDING_PROVIDER = "openai"
            MEMORA_SYNTHESIS_PROVIDER = "openai"
            MEMORA_FACT_PROVIDER = "openai"
        }
    } elseif ($Mode -eq "Local") {
        [ordered]@{
            MEMORA_EMBEDDING_PROVIDER = "local"
            MEMORA_SYNTHESIS_PROVIDER = "deterministic"
            MEMORA_FACT_PROVIDER = "deterministic"
        }
    } else {
        throw "Processing mode must be Enhanced or Local."
    }
    foreach ($entry in $values.GetEnumerator()) {
        Set-DotEnvValue $Path $entry.Key $entry.Value
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }
    if ([string]::IsNullOrWhiteSpace($env:OPENAI_EMBEDDING_MODEL)) {
        Set-DotEnvValue $Path "OPENAI_EMBEDDING_MODEL" "text-embedding-3-small"
        $env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
    }
    if ([string]::IsNullOrWhiteSpace($env:MEMORA_SYNTHESIS_MODEL)) {
        Set-DotEnvValue $Path "MEMORA_SYNTHESIS_MODEL" "gpt-5.6-luna"
        $env:MEMORA_SYNTHESIS_MODEL = "gpt-5.6-luna"
    }
    if ($Mode -eq "Local") {
        Remove-DotEnvValue $Path "MEMORA_RELEVANCE_MIN_SIMILARITY"
        Remove-Item Env:MEMORA_RELEVANCE_MIN_SIMILARITY -ErrorAction SilentlyContinue
    }
}

function Get-ConfiguredDatabaseFile([string]$DatabaseUrl, [string]$BasePath) {
    if ([string]::IsNullOrWhiteSpace($DatabaseUrl) -or -not $DatabaseUrl.StartsWith("sqlite:///")) { return $null }
    $path = $DatabaseUrl.Substring("sqlite:///".Length)
    if ([IO.Path]::IsPathRooted($path)) { return $path }
    return [IO.Path]::GetFullPath((Join-Path $BasePath $path))
}

function Test-DatabaseHasContent([string]$DatabaseUrl, [string]$BasePath) {
    $path = Get-ConfiguredDatabaseFile $DatabaseUrl $BasePath
    return $path -and (Test-Path -LiteralPath $path -PathType Leaf) -and (Get-Item $path).Length -gt 0
}

function Confirm-EmbeddingModeSwitch(
    [string]$CurrentEmbedding,
    [string]$SelectedEmbedding,
    [string]$DatabaseUrl,
    [string]$BasePath,
    [scriptblock]$ReadConfirmation = { param($Prompt) Read-Host $Prompt }
) {
    if ($CurrentEmbedding -eq $SelectedEmbedding -or -not (Test-DatabaseHasContent $DatabaseUrl $BasePath)) {
        return $true
    }
    Write-Host "`nYour existing database file may contain vectors created with a different embedding provider." -ForegroundColor Yellow
    Write-Host "Changing providers requires re-indexing compatible memory. Memora will not rewrite or delete the database."
    $answer = [string](& $ReadConfirmation "Change processing mode anyway? [y/N]")
    return $answer -match '^(?i:y|yes)$'
}

function Write-ProcessingModeSummary([string]$Mode) {
    Write-Host "`nMemora processing mode: $Mode" -ForegroundColor White
    if ($Mode -eq "Enhanced") {
        Write-Step "OpenAI semantic embeddings"
        Write-Step "OpenAI MemoryFact extraction"
        Write-Step "OpenAI MemoryBrief synthesis"
        Write-Host "  Best intended Memora quality configuration enabled."
    } elseif ($Mode -eq "Local") {
        Write-Step "Local embeddings"
        Write-Step "Deterministic MemoryFacts"
        Write-Step "Deterministic MemoryBriefs"
        Write-Host "  No OpenAI API key is required."
        Write-Host "  Recommended for testing and offline development; memory quality may differ from Enhanced mode."
    } else {
        Write-Host "  Existing custom provider configuration preserved."
    }
}

function New-MemoraToken {
    $bytes = [byte[]]::new(32)
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return ([BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
}

function Read-Secret([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Ensure-ProviderConfiguration(
    [scriptblock]$ReadApiKey = { param($Prompt) Read-Secret $Prompt },
    [scriptblock]$ReadSaveChoice = { param($Prompt) Read-Host $Prompt },
    [scriptblock]$ReadThreshold = { param($Prompt) Read-Host $Prompt }
) {
    $embedding = [Environment]::GetEnvironmentVariable("MEMORA_EMBEDDING_PROVIDER", "Process")
    $synthesis = [Environment]::GetEnvironmentVariable("MEMORA_SYNTHESIS_PROVIDER", "Process")
    $facts = [Environment]::GetEnvironmentVariable("MEMORA_FACT_PROVIDER", "Process")
    if ([string]::IsNullOrWhiteSpace($embedding)) { $embedding = "local" }
    if ([string]::IsNullOrWhiteSpace($synthesis)) { $synthesis = "deterministic" }
    if ([string]::IsNullOrWhiteSpace($facts)) { $facts = $synthesis }
    $embedding = $embedding.Trim().ToLowerInvariant()
    $synthesis = $synthesis.Trim().ToLowerInvariant()
    $facts = $facts.Trim().ToLowerInvariant()
    if ($embedding -notin @("local", "openai")) {
        throw "MEMORA_EMBEDDING_PROVIDER must be local or openai."
    }
    if ($synthesis -notin @("deterministic", "openai")) {
        throw "MEMORA_SYNTHESIS_PROVIDER must be deterministic or openai."
    }
    if ($facts -notin @("deterministic", "openai")) {
        throw "MEMORA_FACT_PROVIDER must be deterministic or openai."
    }
    $needsOpenAI = @($embedding, $synthesis, $facts) -contains "openai"
    if ($needsOpenAI -and [string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        $key = [string](& $ReadApiKey "Enter your OpenAI API key (input is hidden)")
        if ([string]::IsNullOrWhiteSpace($key)) { throw "OPENAI_API_KEY is required by the selected OpenAI provider." }
        $env:OPENAI_API_KEY = $key
        Write-Host "The .env file is local plaintext configuration and is excluded from Git." -ForegroundColor DarkGray
        $save = [string](& $ReadSaveChoice "Save this API key locally for future Memora launches? [Y] Yes / [N] No (default: N)")
        if ($save -match '^(?i:y|yes)$') {
            Set-DotEnvValue $script:DotEnvPath "OPENAI_API_KEY" $key
            Write-Info "OpenAI key saved to the gitignored local .env file."
        } else {
            Write-Info "OpenAI key will be used only for this launch."
        }
    }
    if ($embedding -eq "openai" -and [string]::IsNullOrWhiteSpace($env:MEMORA_RELEVANCE_MIN_SIMILARITY)) {
        Write-Host "OpenAI embeddings require a relevance floor measured for the intended index." -ForegroundColor Yellow
        Write-Host "Memora does not ship a universal threshold. Use scripts.calibrate_relevance for guidance." -ForegroundColor Yellow
        $threshold = ([string](& $ReadThreshold "Enter the calibrated MEMORA_RELEVANCE_MIN_SIMILARITY, or press Enter to stop")).Trim()
        if ([string]::IsNullOrWhiteSpace($threshold)) {
            throw "Enhanced mode needs a calibrated MEMORA_RELEVANCE_MIN_SIMILARITY. No provider or database data was modified automatically."
        }
        $number = 0.0
        if (-not [double]::TryParse($threshold, [Globalization.NumberStyles]::Float,
                [Globalization.CultureInfo]::InvariantCulture, [ref]$number) -or $number -lt -1 -or $number -gt 1) {
            throw "MEMORA_RELEVANCE_MIN_SIMILARITY must be a number between -1 and 1."
        }
        $env:MEMORA_RELEVANCE_MIN_SIMILARITY = $threshold
        Set-DotEnvValue $script:DotEnvPath "MEMORA_RELEVANCE_MIN_SIMILARITY" $threshold
    }
    if ($embedding -eq "openai") {
        $configuredThreshold = 0.0
        if (-not [double]::TryParse($env:MEMORA_RELEVANCE_MIN_SIMILARITY,
                [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture,
                [ref]$configuredThreshold) -or $configuredThreshold -lt -1 -or $configuredThreshold -gt 1) {
            throw "MEMORA_RELEVANCE_MIN_SIMILARITY must be a number between -1 and 1."
        }
    }
}

function ConvertTo-NativeArgument([string]$Value) {
    if ($Value -notmatch '[\s"]') { return $Value }
    # Windows CommandLineToArgvW quoting: double backslashes before quotes and
    # at the end of a quoted argument, while preserving every other character.
    return '"' + ([regex]::Replace($Value, '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}

function Invoke-NativeResult(
    [string]$FilePath,
    [string[]]$Arguments,
    [int]$TimeoutSeconds = 30,
    [string]$WorkingDirectory = $script:RepoRoot
) {
    Write-Verbose "$FilePath $($Arguments -join ' ') (working directory: $WorkingDirectory)"
    if ([string]::IsNullOrWhiteSpace($WorkingDirectory) -or
        -not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) {
        return @{
            ExitCode = -1
            Lines = @("Working directory does not exist: $WorkingDirectory")
            InvocationFailed = $true
            TimedOut = $false
        }
    }
    $process = $null
    try {
        $startInfo = [Diagnostics.ProcessStartInfo]::new()
        $nativeArguments = (@($Arguments | ForEach-Object { ConvertTo-NativeArgument ([string]$_) }) -join ' ')
        if ([IO.Path]::GetExtension($FilePath) -match '^(?i:\.cmd|\.bat)$') {
            $startInfo.FileName = $env:ComSpec
            $commandLine = (ConvertTo-NativeArgument $FilePath) + $(if ($nativeArguments) { " $nativeArguments" } else { "" })
            $startInfo.Arguments = '/d /s /c "' + $commandLine + '"'
        } else {
            $startInfo.FileName = $FilePath
            $startInfo.Arguments = $nativeArguments
        }
        $startInfo.WorkingDirectory = $WorkingDirectory
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        if (-not $process.Start()) {
            return @{ ExitCode = -1; Lines = @("The child process did not start."); InvocationFailed = $true; TimedOut = $false }
        }
        # Begin both reads before waiting so neither redirected pipe can fill and
        # deadlock the child process under Windows PowerShell 5.1.
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch { }
            $process.WaitForExit()
            return @{ ExitCode = -1; Lines = @("Command timed out after $TimeoutSeconds seconds."); InvocationFailed = $true; TimedOut = $true }
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $lines = @(($stdout, $stderr) | ForEach-Object { if ($_){ $_ -split '\r?\n' } } | Where-Object { $_ -ne '' })
        return @{ ExitCode = $process.ExitCode; Lines = @($lines); InvocationFailed = $false; TimedOut = $false }
    } catch {
        return @{ ExitCode = -1; Lines = @($_.Exception.Message); InvocationFailed = $true; TimedOut = $false }
    } finally {
        if ($null -ne $process) { $process.Dispose() }
    }
}

function Get-MeaningfulDiagnostic([string[]]$Lines) {
    $clean = @($Lines | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
    if ($clean.Count -eq 0) { return "No diagnostic output was returned." }
    $meaningful = @($clean | Where-Object {
        $_ -match '^(ModuleNotFoundError|ImportError|ERROR:|Error:|Exception:|[A-Za-z]+Error:)'
    })
    if ($meaningful.Count -gt 0) { return [string]$meaningful[-1] }
    return [string]$clean[-1]
}

function Write-BoundedVerboseDiagnostic([string[]]$Lines) {
    if ($VerbosePreference -ne "Continue") { return }
    @($Lines | Select-Object -Last 20) | ForEach-Object { Write-Verbose ([string]$_) }
}

function Invoke-Quiet(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$FailureMessage,
    [string]$WorkingDirectory = $script:RepoRoot,
    [int]$TimeoutSeconds = 300
) {
    $result = Invoke-NativeResult $FilePath $Arguments $TimeoutSeconds $WorkingDirectory
    if ($result.ExitCode -ne 0) {
        Write-BoundedVerboseDiagnostic $result.Lines
        throw "$FailureMessage $(Get-MeaningfulDiagnostic $result.Lines)"
    }
}

function Test-PythonRuntimeDependencies(
    [string]$PythonPath,
    [scriptblock]$InvokeCommand = { param($Path, $CommandArguments, $Timeout) Invoke-NativeResult $Path $CommandArguments $Timeout }
) {
    $probe = @'
import backend, fastapi, httpx, openai, multipart, pypdf, uvicorn
'@
    $result = & $InvokeCommand $PythonPath @("-c", $probe) 30
    return @{
        Ready = $result.ExitCode -eq 0
        Diagnostic = if ($result.ExitCode -eq 0) { "" } else { Get-MeaningfulDiagnostic $result.Lines }
        Lines = @($result.Lines)
    }
}

function Test-MemoraDistribution(
    [string]$PythonPath,
    [scriptblock]$InvokeCommand = { param($Path, $CommandArguments, $Timeout) Invoke-NativeResult $Path $CommandArguments $Timeout }
) {
    $probe = @'
from importlib.metadata import version
value = version("memora-backend")
if value is None or not str(value).strip() or str(value).strip().lower() == "none":
    raise RuntimeError("memora-backend has invalid or empty distribution metadata")
print(str(value).strip())
'@
    $result = & $InvokeCommand $PythonPath @("-c", $probe) 30
    $value = (@($result.Lines | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ }) -join "").Trim()
    return @{
        Valid = $result.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($value) -and $value -notmatch '^(?i:none)$'
        Diagnostic = if ($result.ExitCode -eq 0) { "Invalid or empty memora-backend distribution metadata." } else { Get-MeaningfulDiagnostic $result.Lines }
        Lines = @($result.Lines)
    }
}

function Test-PipConsistency(
    [string]$PythonPath,
    [scriptblock]$InvokeCommand = { param($Path, $CommandArguments, $Timeout) Invoke-NativeResult $Path $CommandArguments $Timeout }
) {
    $result = & $InvokeCommand $PythonPath @("-m", "pip", "check") 30
    return @{ Consistent = $result.ExitCode -eq 0; Lines = @($result.Lines) }
}

function Get-DependencyFingerprint([string]$ProjectRoot) {
    $projectFile = Join-Path $ProjectRoot "pyproject.toml"
    $stream = [IO.File]::OpenRead($projectFile)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($sha.ComputeHash($stream)) -replace '-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

function Ensure-PythonProjectEnvironment(
    [string]$PythonPath,
    [string]$ProjectRoot,
    [scriptblock]$InvokeCommand = { param($Path, $CommandArguments, $Timeout) Invoke-NativeResult $Path $CommandArguments $Timeout }
) {
    Write-Verbose "Checking virtual environment Python..."
    $pip = & $InvokeCommand $PythonPath @("-m", "pip", "--version") 30
    if ($pip.ExitCode -ne 0) {
        Write-BoundedVerboseDiagnostic $pip.Lines
        throw "pip is unavailable in the local virtual environment. $(Get-MeaningfulDiagnostic $pip.Lines)"
    }
    Write-Verbose "Virtual environment Python OK."

    $fingerprint = Get-DependencyFingerprint $ProjectRoot
    $marker = Join-Path (Split-Path -Parent (Split-Path -Parent $PythonPath)) ".memora-pyproject.sha256"
    $markerCurrent = (Test-Path -LiteralPath $marker -PathType Leaf) -and
        ([IO.File]::ReadAllText($marker).Trim() -eq $fingerprint)
    Write-Verbose "Checking installed Memora distribution..."
    $distribution = Test-MemoraDistribution $PythonPath $InvokeCommand
    Write-Verbose "Memora distribution check complete."
    Write-Verbose "Checking required runtime imports..."
    $runtime = Test-PythonRuntimeDependencies $PythonPath $InvokeCommand
    Write-Verbose "Runtime import check complete."
    # pip check only verifies compatibility among distributions that already
    # exist. An empty venv can pass it, so it is never the readiness gate.
    Write-Verbose "Running pip consistency check..."
    $consistency = Test-PipConsistency $PythonPath $InvokeCommand
    Write-Verbose "Pip consistency check complete."
    $needsInstall = -not $distribution.Valid -or -not $runtime.Ready -or -not $consistency.Consistent -or -not $markerCurrent

    if ($needsInstall) {
        Write-Verbose "Dependency installation required."
        if (-not $distribution.Valid -or -not $runtime.Ready) {
            Write-Info "Python environment incomplete."
            if (-not $runtime.Ready) { Write-Verbose "Runtime diagnostic: $($runtime.Diagnostic)" }
            if (-not $distribution.Valid) { Write-Verbose "Distribution diagnostic: $($distribution.Diagnostic)" }
        } elseif (-not $consistency.Consistent) {
            Write-Info "Python dependency consistency needs repair."
        } else {
            Write-Info "Python project metadata changed; refreshing local dependencies."
        }
        Write-Info "Installing Memora Python dependencies..."
        Write-Verbose "Starting editable project installation..."
        $install = & $InvokeCommand $PythonPath @("-m", "pip", "install", "-e", ".") 900
        if ($install.ExitCode -ne 0) {
            Write-BoundedVerboseDiagnostic $install.Lines
            throw "Memora could not install Python dependencies. $(Get-MeaningfulDiagnostic $install.Lines) Run with -Verbose for bounded details."
        }
        Write-Verbose "Editable project installation completed."
        Write-Verbose "Checking installed Memora distribution..."
        $distribution = Test-MemoraDistribution $PythonPath $InvokeCommand
        Write-Verbose "Memora distribution check complete."
        if (-not $distribution.Valid) {
            Write-BoundedVerboseDiagnostic $distribution.Lines
            throw "Memora dependency installation completed, but distribution verification failed: $($distribution.Diagnostic)"
        }
        Write-Verbose "Checking required runtime imports..."
        $runtime = Test-PythonRuntimeDependencies $PythonPath $InvokeCommand
        Write-Verbose "Runtime import check complete."
        if (-not $runtime.Ready) {
            Write-BoundedVerboseDiagnostic $runtime.Lines
            throw "Memora dependency installation completed, but runtime verification failed: $($runtime.Diagnostic)"
        }
        Write-Verbose "Running pip consistency check..."
        $consistency = Test-PipConsistency $PythonPath $InvokeCommand
        Write-Verbose "Pip consistency check complete."
        if (-not $consistency.Consistent) {
            Write-BoundedVerboseDiagnostic $consistency.Lines
            throw "Memora dependencies were installed, but pip reported an inconsistent environment. $(Get-MeaningfulDiagnostic $consistency.Lines)"
        }
        [IO.File]::WriteAllText($marker, $fingerprint, [Text.UTF8Encoding]::new($false))
        return @{ Installed = $true; Diagnostic = "" }
    }
    return @{ Installed = $false; Diagnostic = "" }
}

function Test-NodeDependenciesNeedInstall([string]$ExtensionRoot) {
    if (-not (Test-Path -LiteralPath $ExtensionRoot -PathType Container)) {
        throw "Chrome extension directory was not found: $ExtensionRoot"
    }
    $modules = Join-Path $ExtensionRoot "node_modules"
    $installedLock = Join-Path $modules ".package-lock.json"
    $projectLock = Join-Path $ExtensionRoot "package-lock.json"
    if (-not (Test-Path -LiteralPath (Join-Path $ExtensionRoot "package.json") -PathType Leaf)) {
        throw "Chrome extension package.json was not found."
    }
    if (-not (Test-Path -LiteralPath $projectLock -PathType Leaf)) {
        throw "Chrome extension package-lock.json was not found."
    }
    if (-not (Test-Path -LiteralPath $modules -PathType Container)) { return $true }
    if (-not (Test-Path -LiteralPath $installedLock -PathType Leaf)) { return $true }
    return (Get-Item $projectLock).LastWriteTimeUtc -gt (Get-Item $installedLock).LastWriteTimeUtc
}

function Test-ExtensionBuildNeeded([string]$ExtensionRoot) {
    $required = @("background.js", "content.js", "popup.js", "popup.html", "popup.css", "manifest.json")
    $dist = Join-Path $ExtensionRoot "dist"
    foreach ($name in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $dist $name) -PathType Leaf)) { return $true }
    }
    $stamp = Join-Path $dist ".memora-build-stamp"
    if (-not (Test-Path -LiteralPath $stamp -PathType Leaf)) { return $true }
    $inputs = @(
        Get-ChildItem (Join-Path $ExtensionRoot "src") -Recurse -File -ErrorAction SilentlyContinue
        Get-Item (Join-Path $ExtensionRoot "manifest.json"), (Join-Path $ExtensionRoot "popup.html"),
            (Join-Path $ExtensionRoot "popup.css"), (Join-Path $ExtensionRoot "package.json"),
            (Join-Path $ExtensionRoot "package-lock.json"), (Join-Path $ExtensionRoot "tsconfig.json"),
            (Join-Path $ExtensionRoot "vitest.config.ts"),
            (Join-Path $ExtensionRoot "scripts\build.mjs") -ErrorAction SilentlyContinue
    )
    $latestInput = ($inputs | Measure-Object LastWriteTimeUtc -Maximum).Maximum
    $verifiedBuildTime = (Get-Item -LiteralPath $stamp).LastWriteTimeUtc
    return $latestInput -gt $verifiedBuildTime
}

function Assert-ExtensionBuildOutputs([string]$ExtensionRoot) {
    $required = @("background.js", "content.js", "popup.js", "popup.html", "popup.css", "manifest.json")
    $missing = @($required | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $ExtensionRoot "dist\$_") -PathType Leaf)
    })
    if ($missing.Count -gt 0) {
        throw "Chrome extension build completed without required output: $($missing -join ', ')"
    }
}

function Set-ExtensionBuildStamp([string]$ExtensionRoot) {
    $dist = Join-Path $ExtensionRoot "dist"
    if (-not (Test-Path -LiteralPath $dist -PathType Container)) {
        throw "Chrome extension build output directory was not created."
    }
    $stamp = Join-Path $dist ".memora-build-stamp"
    [IO.File]::WriteAllText(
        $stamp,
        [DateTime]::UtcNow.ToString("o", [Globalization.CultureInfo]::InvariantCulture),
        [Text.UTF8Encoding]::new($false)
    )
}

function Test-ExtensionBuildRequested([string]$ExtensionRoot, [bool]$ForceBuild) {
    return $ForceBuild -or (Test-ExtensionBuildNeeded $ExtensionRoot)
}

function Invoke-ExtensionNpm(
    [string]$NpmPath,
    [string[]]$Arguments,
    [string]$ExtensionRoot,
    [string]$FailureMessage,
    [scriptblock]$InvokeCommand = {
        param($Path, $CommandArguments, $Timeout, $Directory)
        Invoke-NativeResult $Path $CommandArguments $Timeout $Directory
    }
) {
    if (-not (Test-Path -LiteralPath $ExtensionRoot -PathType Container)) {
        throw "Chrome extension directory was not found: $ExtensionRoot"
    }
    $result = & $InvokeCommand $NpmPath $Arguments 300 $ExtensionRoot
    if ($result.ExitCode -ne 0) {
        Write-BoundedVerboseDiagnostic $result.Lines
        throw "$FailureMessage Run with -Verbose for details."
    }
    return $result
}

function Invoke-ExtensionProductionBuild(
    [string]$NpmPath,
    [string]$ExtensionRoot,
    [scriptblock]$InvokeCommand = {
        param($Path, $CommandArguments, $Timeout, $Directory)
        Invoke-NativeResult $Path $CommandArguments $Timeout $Directory
    }
) {
    Invoke-ExtensionNpm $NpmPath @("run", "build") $ExtensionRoot `
        "Memora could not build the Chrome extension." $InvokeCommand | Out-Null
    Assert-ExtensionBuildOutputs $ExtensionRoot
    Set-ExtensionBuildStamp $ExtensionRoot
}

function Test-PortOpen([int]$Port, [int]$TimeoutMilliseconds = 500) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Dispose() }
}

function Invoke-LocalRequest([string]$Path, [string]$Token, [int]$TimeoutSeconds = 3) {
    try {
        $headers = if ($Token) { @{ Authorization = "Bearer $Token" } } else { @{} }
        $body = Invoke-RestMethod -Uri "$script:BackendUrl$Path" -Headers $headers -Method Get -TimeoutSec $TimeoutSeconds
        return @{ Status = 200; Body = $body }
    } catch {
        $status = 0
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        return @{ Status = $status; Body = $null }
    }
}

function Get-Readiness([string]$Token) {
    $response = Invoke-LocalRequest "/api/v1/memory/stats" $Token 3
    if ($response.Status -eq 200) {
        $count = 0
        foreach ($property in $response.Body.PSObject.Properties) { $count += [int]$property.Value }
        return @{ State = if ($count -eq 0) { "Empty" } else { "Ready" }; Count = $count }
    }
    if ($response.Status -eq 401) { return @{ State = "Authentication"; Count = 0 } }
    if ($response.Status -eq 409 -or $response.Status -eq 503) { return @{ State = "Configuration"; Count = 0 } }
    return @{ State = "Offline"; Count = 0 }
}

function Copy-MemoraToken([string]$Token) {
    try {
        Set-Clipboard -Value $Token
        return $true
    } catch {
        Write-Verbose "Clipboard copy failed: $($_.Exception.Message)"
        return $false
    }
}

if ($env:MEMORA_LAUNCHER_TEST_MODE -eq "1") { return }

Write-Host "`nMemora" -ForegroundColor White
Write-Host "Local AI Memory Layer`n" -ForegroundColor DarkGray
Write-Host "Checking environment..." -ForegroundColor White

$pythonCandidates = Get-ApplicationPaths "python"
$pyCandidates = Get-ApplicationPaths "py"
try { $pythonSelection = Find-PythonInterpreter $pythonCandidates $pyCandidates }
catch { Stop-Launcher $_.Exception.Message "Install or repair Python 3.11+, then reopen PowerShell. WindowsApps aliases are not treated as installed interpreters." }
$pythonExecutable = [string]$pythonSelection.Path
$pythonPrefixArguments = @($pythonSelection.PrefixArguments)
$pythonVersion = $pythonSelection.Version
Write-Step "Python $pythonVersion available"
Write-Verbose "Selected Python executable: $pythonExecutable"

$nodeCandidates = Get-ApplicationPaths "node"
try { $nodeSelection = Select-VersionedExecutable $nodeCandidates @("--version") "Node.js" ([version]"20.0") }
catch { Stop-Launcher $_.Exception.Message "Run node --version directly and repair PATH or the executable as indicated; do not reinstall solely for a launcher parsing error." }
$nodeExecutable = [string]$nodeSelection.Path
$nodeVersion = $nodeSelection.Version

$npmCandidates = Get-ApplicationPaths "npm.cmd"
try { $npmSelection = Select-VersionedExecutable $npmCandidates @("--version") "npm" ([version]"0.0") }
catch { Stop-Launcher $_.Exception.Message "Confirm npm is included with Node.js and available on PATH, then try again." }
$npmExecutable = [string]$npmSelection.Path
$npmVersion = $npmSelection.Version
Write-Step "Node.js $nodeVersion and npm $npmVersion available"

try {
    Set-Location $script:RepoRoot
    $venvPython = Join-Path $script:RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Write-Info "Creating local Python environment..."
        Invoke-Quiet $pythonExecutable @($pythonPrefixArguments + @("-m", "venv", ".venv")) "The local Python environment could not be created."
    }
    Ensure-PythonProjectEnvironment $venvPython $script:RepoRoot | Out-Null
    Write-Step "Python environment ready"

    Import-DotEnv $script:DotEnvPath
    $providerConfigurationPresent = Test-ProviderConfigurationPresent
    Set-BaseConfigurationDefaults
    Import-DotEnv $script:DotEnvPath

    $currentMode = Get-ProcessingMode
    $modeResolution = Resolve-ProcessingMode $providerConfigurationPresent $currentMode $Setup
    if ($modeResolution.Changed) {
        $currentEmbedding = [Environment]::GetEnvironmentVariable("MEMORA_EMBEDDING_PROVIDER", "Process")
        if ([string]::IsNullOrWhiteSpace($currentEmbedding)) { $currentEmbedding = "local" }
        $selectedEmbedding = if ($modeResolution.Mode -eq "Enhanced") { "openai" } else { "local" }
        if ($providerConfigurationPresent -and
            -not (Confirm-EmbeddingModeSwitch $currentEmbedding $selectedEmbedding $env:MEMORA_DATABASE_URL $script:RepoRoot)) {
            Write-Info "Keeping the current processing mode and database unchanged."
            $modeResolution = @{ Mode = $currentMode; Changed = $false }
        }
        if ($modeResolution.Changed) { Set-ProcessingMode $modeResolution.Mode $script:DotEnvPath }
    }

    $tokenGenerated = $false
    if ([string]::IsNullOrWhiteSpace($env:MEMORA_LOCAL_TOKEN)) {
        $env:MEMORA_LOCAL_TOKEN = New-MemoraToken
        Set-DotEnvValue $script:DotEnvPath "MEMORA_LOCAL_TOKEN" $env:MEMORA_LOCAL_TOKEN
        $tokenGenerated = $true
    }
    if ($env:MEMORA_LOCAL_TOKEN.Length -lt 32) {
        throw "MEMORA_LOCAL_TOKEN must contain at least 32 characters. Correct the local .env value; it was not replaced."
    }
    Ensure-ProviderConfiguration
    $activeMode = Get-ProcessingMode
    Write-ProcessingModeSummary $activeMode
    Write-Step "Local configuration ready"
    Write-Step "Stable Memora token ready"

    if ($tokenGenerated) {
        if (Copy-MemoraToken $env:MEMORA_LOCAL_TOKEN) {
            Write-Info "Your new Memora token was copied to the clipboard."
        } else {
            Write-Info "Clipboard access was unavailable. Re-run with -ShowToken when you are ready to copy it manually."
        }
    }
    if ($ShowToken) {
        Write-Host "`nMemora token (shown because -ShowToken was requested):" -ForegroundColor Yellow
        Write-Host $env:MEMORA_LOCAL_TOKEN
    }

    $extensionRoot = Join-Path $script:RepoRoot "extension"
    if (Test-NodeDependenciesNeedInstall $extensionRoot) {
        Write-Info "Installing locked extension dependencies..."
        Invoke-ExtensionNpm $npmExecutable @("ci") $extensionRoot `
            "Memora could not install Chrome extension dependencies." | Out-Null
    }
    Write-Step "Extension dependencies ready"

    if (Test-ExtensionBuildRequested $extensionRoot $RebuildExtension.IsPresent) {
        Write-Info "Building the production extension..."
        Invoke-ExtensionProductionBuild $npmExecutable $extensionRoot
    } else {
        Assert-ExtensionBuildOutputs $extensionRoot
    }
    Write-Step "Extension build ready"
} catch {
    Stop-Launcher $_.Exception.Message "Review docs\SETUP.md, correct the reported item, and try again."
}

if ($Setup) {
    Write-Host "`nSetup complete." -ForegroundColor Green
    Write-Host "Load extension\dist in chrome://extensions, then run .\start-memora.ps1 to start Memora."
    exit 0
}

$existing = Get-Readiness $env:MEMORA_LOCAL_TOKEN
if ($existing.State -eq "Ready" -or $existing.State -eq "Empty") {
    Write-Host "`nMemora is already running at $script:BackendUrl." -ForegroundColor Green
    if ($existing.State -eq "Empty") { Write-Host "No memory is imported yet. Use the extension popup to import history." }
    Write-Host "Open ChatGPT and use the Memora panel."
    exit 0
}
if (Test-PortOpen 8765) {
    $health = Invoke-LocalRequest "/health" "" 2
    $isMemora = $health.Status -eq 200 -and $health.Body -and
        ($health.Body.PSObject.Properties.Name -contains "service") -and
        $health.Body.service -eq "memora"
    if ($isMemora -and $existing.State -eq "Authentication") {
        Stop-Launcher "Port 8765 is running Memora with a different token." "Stop the other Memora process or restore its matching token; no process was killed."
    }
    if ($isMemora -and $existing.State -eq "Configuration") {
        Stop-Launcher "Memora is already running, but its provider or local configuration is unavailable." "Stop that process, correct .env, and start Memora again."
    }
    Stop-Launcher "Port 8765 is already in use." "Stop or reconfigure the other local process; Memora did not kill it."
}

Write-Host "`nStarting Memora..." -ForegroundColor White
$process = [Diagnostics.Process]::new()
$process.StartInfo.FileName = $venvPython
$process.StartInfo.Arguments = '-m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765 --log-level warning --no-access-log'
$process.StartInfo.WorkingDirectory = $script:RepoRoot
$process.StartInfo.UseShellExecute = $false
$process.StartInfo.RedirectStandardOutput = $true
$process.StartInfo.RedirectStandardError = $true
$process.StartInfo.CreateNoWindow = $true

try {
    if (-not $process.Start()) { throw "The backend process could not be started." }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $readiness = @{ State = "Offline"; Count = 0 }
    while ([DateTime]::UtcNow -lt $deadline -and -not $process.HasExited) {
        Start-Sleep -Milliseconds 500
        $readiness = Get-Readiness $env:MEMORA_LOCAL_TOKEN
        if ($readiness.State -ne "Offline") { break }
    }
    if ($process.HasExited) {
        $diagnostic = $process.StandardError.ReadToEnd().Trim()
        Write-Verbose $diagnostic
        throw "The backend stopped during startup. Re-run with -Verbose for bounded diagnostics."
    }
    switch ($readiness.State) {
        "Ready" { Write-Step "Backend ready with memory available" }
        "Empty" { Write-Step "Backend ready; no memory imported yet" }
        "Authentication" { throw "The backend rejected the configured local token." }
        "Configuration" { throw "The backend started, but its provider or local configuration is unavailable." }
        default { throw "Backend readiness timed out after 30 seconds." }
    }

    Write-Host "`nBackend: $script:BackendUrl" -ForegroundColor Cyan
    Write-Host "Status:  $($readiness.State)" -ForegroundColor Green
    Write-Host "`nFirst run: load extension\dist in chrome://extensions and paste the copied token into Memora settings."
    Write-Host "Closing this launcher stops the local Memora backend. Press Ctrl+C to stop.`n" -ForegroundColor Yellow
    while (-not $process.HasExited) { Start-Sleep -Seconds 1 }
} catch {
    Stop-Launcher $_.Exception.Message "Review docs\SETUP.md and re-run with -Verbose if diagnostics are needed."
} finally {
    if ($process -and -not $process.HasExited) {
        try { $process.Kill() } catch { Write-Verbose "The backend child process had already stopped." }
    }
    $process.Dispose()
}
