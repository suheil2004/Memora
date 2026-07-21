$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$launcher = Join-Path $repoRoot "start-memora.ps1"
$env:MEMORA_LAUNCHER_TEST_MODE = "1"
. $launcher

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("memora-launcher-" + [Guid]::NewGuid().ToString("N"))
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
$savedDotEnvPath = $script:DotEnvPath
try {
    $envFile = Join-Path $testRoot ".env"
    $script:DotEnvPath = $envFile
    [IO.File]::WriteAllLines($envFile, @(
        "# safe data only",
        "MEMORA_USER_ID=test-user",
        'OPENAI_EMBEDDING_MODEL="text-embedding-3-small"',
        "UNSUPPORTED_VALUE=ignored"
    ))
    $parsed = Read-DotEnv $envFile
    if ($parsed.MEMORA_USER_ID -ne "test-user") { throw "Valid .env values were not parsed." }
    if ($parsed.ContainsKey("UNSUPPORTED_VALUE")) { throw "Unsupported .env values were accepted." }

    Set-DotEnvValue $envFile "MEMORA_USER_ID" "updated-user"
    Set-DotEnvValue $envFile "MEMORA_LOCAL_TOKEN" "stable-token"
    Set-DotEnvValue $envFile "MEMORA_LOCAL_TOKEN" "stable-token"
    $updated = Read-DotEnv $envFile
    if ($updated.MEMORA_USER_ID -ne "updated-user") { throw ".env update failed." }
    if (@(Select-String $envFile -Pattern '^MEMORA_LOCAL_TOKEN=').Count -ne 1) { throw "Token update was not idempotent." }

    $invalid = Join-Path $testRoot "invalid.env"
    [IO.File]::WriteAllText($invalid, 'MEMORA_USER_ID=$(Get-ChildItem)')
    $invalidValue = Read-DotEnv $invalid
    if ($invalidValue.MEMORA_USER_ID -ne '$(Get-ChildItem)') { throw ".env content was executed or transformed." }
    [IO.File]::WriteAllText($invalid, 'not valid dotenv syntax')
    $rejected = $false
    try { Read-DotEnv $invalid | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw "Malformed .env syntax was accepted." }

    $tokenOne = New-MemoraToken
    $tokenTwo = New-MemoraToken
    if ($tokenOne -notmatch '^[a-f0-9]{64}$' -or $tokenOne -eq $tokenTwo) { throw "Secure token generation failed." }
    if ((ConvertTo-ToolVersion "v20.0.0" "Node.js") -ne [version]"20.0.0") { throw "Node 20 with a leading v was not parsed." }
    if ((ConvertTo-ToolVersion "v22.14.1`r`n" "Node.js") -ne [version]"22.14.1") { throw "Node CRLF output was not parsed." }
    if ((ConvertTo-ToolVersion " v24.18.0 `n" "Node.js") -ne [version]"24.18.0") { throw "Node above 20 with whitespace was not parsed." }
    $malformedVersionRejected = $false
    try { ConvertTo-ToolVersion "Node version twenty" "Node.js" | Out-Null } catch { $malformedVersionRejected = $_.Exception.Message -match "malformed" }
    if (-not $malformedVersionRejected) { throw "Malformed Node output did not produce the expected error." }
    if ((ConvertTo-ToolVersion "Python 3.11.9`r`n" "Python") -ne [version]"3.11.9") { throw "Python 3.11 output was not parsed." }
    if ((ConvertTo-ToolVersion "  Python 3.12.4 `n" "Python") -ne [version]"3.12.4") { throw "Python 3.12 output was not parsed." }
    if ((ConvertTo-ToolVersion "Python 3.13.1" "Python") -ne [version]"3.13.1") { throw "Python 3.13 output was not parsed." }
    if (-not (Test-VersionAtLeast ([version]"3.11") ([version]"3.11"))) { throw "Version comparison failed." }
    if (Test-VersionAtLeast ([version]"3.10") ([version]"3.11")) { throw "Unsupported version passed." }

    $spacedTools = Join-Path $testRoot "Program Files\nodejs"
    [IO.Directory]::CreateDirectory($spacedTools) | Out-Null
    $fakeNode = Join-Path $spacedTools "node.cmd"
    [IO.File]::WriteAllText($fakeNode, "@echo v20.0.0`r`n")
    if ((Get-CommandVersion $fakeNode @() "Node.js") -ne [version]"20.0.0") { throw "Executable path containing spaces failed." }
    $failedNode = Join-Path $spacedTools "failed-node.cmd"
    [IO.File]::WriteAllText($failedNode, "@exit /b 7`r`n")
    $invocationRejected = $false
    try { Get-CommandVersion $failedNode @() "Node.js" | Out-Null } catch { $invocationRejected = $_.Exception.Message -match "invocation failed" }
    if (-not $invocationRejected) { throw "Failed executable invocation was not distinguished." }
    $malformedNode = Join-Path $spacedTools "malformed-node.cmd"
    [IO.File]::WriteAllText($malformedNode, "@echo not-a-version`r`n")
    $malformedInvocationRejected = $false
    try { Get-CommandVersion $malformedNode @() "Node.js" | Out-Null } catch { $malformedInvocationRejected = $_.Exception.Message -match "malformed" }
    if (-not $malformedInvocationRejected) { throw "Malformed executable output was not distinguished." }

    $realNode = Get-Command node -CommandType Application -ErrorAction Stop
    $realNodeVersion = Get-CommandVersion $realNode.Source @("--version") "Node.js"
    if (-not (Test-VersionAtLeast $realNodeVersion ([version]"20.0"))) { throw "Discovered Node version is unexpectedly unsupported." }
    $realNpm = Get-Command npm.cmd -CommandType Application -ErrorAction Stop
    if (-not (Get-CommandVersion $realNpm.Source @("--version") "npm")) { throw "Discovered npm command did not report a version." }
    $realPythonSelection = Find-PythonInterpreter (Get-ApplicationPaths "python") (Get-ApplicationPaths "py")
    if ([string]::IsNullOrWhiteSpace($realPythonSelection.Path) -or
        $realPythonSelection.Path -match 'python\.exe\s+.+python\.exe' -or
        $realPythonSelection.Version -lt [version]"3.11") {
        throw "Real multi-candidate Python discovery did not return exactly one supported interpreter."
    }

    $pythonRoot = Join-Path $testRoot "Python Programs"
    $windowsAliasRoot = Join-Path $testRoot "Microsoft\WindowsApps"
    [IO.Directory]::CreateDirectory($pythonRoot) | Out-Null
    [IO.Directory]::CreateDirectory($windowsAliasRoot) | Out-Null
    $python311 = Join-Path $pythonRoot "python311.cmd"
    $python312 = Join-Path $pythonRoot "python312.cmd"
    $badPython = Join-Path $pythonRoot "bad-python.cmd"
    $malformedPython = Join-Path $pythonRoot "malformed-python.cmd"
    $windowsAlias = Join-Path $windowsAliasRoot "python.cmd"
    $pyLauncher = Join-Path $pythonRoot "py.cmd"
    [IO.File]::WriteAllText($python311, "@echo Python 3.11.9`r`n")
    [IO.File]::WriteAllText($python312, "@echo Python 3.12.4`r`n")
    [IO.File]::WriteAllText($badPython, "@exit /b 9`r`n")
    [IO.File]::WriteAllText($malformedPython, "@echo Python unknown`r`n")
    [IO.File]::WriteAllText($windowsAlias, "@exit /b 1`r`n")
    [IO.File]::WriteAllText($pyLauncher, "@echo Python 3.13.1`r`n")

    $aliasAndReal = Find-PythonInterpreter @($windowsAlias, $python311) @()
    if ($aliasAndReal.Path -ne $python311 -or $aliasAndReal.Path -match 'WindowsApps') { throw "WindowsApps alias was not skipped for real Python." }
    $secondValid = Find-PythonInterpreter @($badPython, $python312) @()
    if ($secondValid.Path -ne $python312) { throw "Valid second Python candidate was not selected." }
    $firstOfTwo = Find-PythonInterpreter @($python311, $python312) @()
    if ($firstOfTwo.Path -ne $python311) { throw "First supported Python candidate was not selected deterministically." }
    $fallback = Find-PythonInterpreter @($badPython) @($pyLauncher)
    if ($fallback.Path -ne $pyLauncher -or $fallback.Source -ne "py" -or $fallback.PrefixArguments[0] -ne "-3") {
        throw "Windows py launcher fallback was not selected safely."
    }
    $oldPython = Join-Path $pythonRoot "python310.cmd"
    [IO.File]::WriteAllText($oldPython, "@echo Python 3.10.14`r`n")
    $oldRejected = $false
    try { Find-PythonInterpreter @($oldPython) @() | Out-Null } catch { $oldRejected = $_.Exception.Message -match "below required" }
    if (-not $oldRejected) { throw "Unsupported old Python was not rejected distinctly." }
    $pythonMalformedRejected = $false
    try { Find-PythonInterpreter @($malformedPython) @() | Out-Null } catch { $pythonMalformedRejected = $_.Exception.Message -match "malformed" }
    if (-not $pythonMalformedRejected) { throw "Malformed Python version output was not distinguished." }
    $pythonInvocationRejected = $false
    try { Find-PythonInterpreter @($badPython) @() | Out-Null } catch { $pythonInvocationRejected = $_.Exception.Message -match "none invoked successfully" }
    if (-not $pythonInvocationRejected) { throw "Python invocation failure was not distinguished." }
    $noFallbackRejected = $false
    try { Find-PythonInterpreter @() @() | Out-Null } catch { $noFallbackRejected = $_.Exception.Message -match "No Python command candidates" }
    if (-not $noFallbackRejected) { throw "Missing Python and py fallback were not reported." }

    $bootstrapRoot = Join-Path $testRoot "bootstrap-project"
    $fakeVenv = Join-Path $bootstrapRoot ".venv"
    $fakeScripts = Join-Path $fakeVenv "Scripts"
    [IO.Directory]::CreateDirectory($fakeScripts) | Out-Null
    [IO.File]::WriteAllText((Join-Path $bootstrapRoot "pyproject.toml"), "[project]`nname='memora-backend'`n")
    $fakePython = Join-Path $fakeScripts "python.exe"
    [IO.File]::WriteAllText($fakePython, "synthetic executable marker")

    $freshState = @{ RuntimeReady = $false; InstallCount = 0 }
    $freshInvoker = {
        param($Path, $CommandArgs)
        $command = $CommandArgs -join " "
        if ($command -eq "-m pip --version") { return @{ ExitCode = 0; Lines = @("pip synthetic") } }
        if ($command -eq "-m pip check") { return @{ ExitCode = 0; Lines = @("No broken requirements found.") } }
        if ($command -eq "-m pip install -e .") { $freshState.InstallCount++; $freshState.RuntimeReady = $true; return @{ ExitCode = 0; Lines = @("installed") } }
        if ($CommandArgs[0] -eq "-c") {
            if ($freshState.RuntimeReady) {
                return @{ ExitCode = 0; Lines = @($(if ($CommandArgs[1] -match 'importlib.metadata') { "0.1.0" } else { "" })) }
            }
            return @{ ExitCode = 1; Lines = @("Traceback (most recent call last):", "ModuleNotFoundError: No module named 'fastapi'") }
        }
        return @{ ExitCode = 1; Lines = @("unexpected command") }
    }
    $freshResult = Ensure-PythonProjectEnvironment $fakePython $bootstrapRoot $freshInvoker
    if (-not $freshResult.Installed -or $freshState.InstallCount -ne 1) {
        throw "Fresh venv with successful pip check did not bootstrap missing runtime dependencies."
    }

    $noneMetadataState = @{ Installed = $false }
    $noneMetadataInvoker = {
        param($Path, $CommandArgs)
        $command = $CommandArgs -join " "
        if ($command -eq "-m pip --version" -or $command -eq "-m pip check") { return @{ ExitCode = 0; Lines = @("ok") } }
        if ($command -eq "-m pip install -e .") { $noneMetadataState.Installed = $true; return @{ ExitCode = 0; Lines = @("installed") } }
        if ($CommandArgs[0] -eq "-c" -and $CommandArgs[1] -match 'importlib.metadata') {
            if ($noneMetadataState.Installed) { return @{ ExitCode = 0; Lines = @("0.1.0") } }
            return @{ ExitCode = 0; Lines = @("None") }
        }
        if ($CommandArgs[0] -eq "-c") {
            return @{ ExitCode = $(if ($noneMetadataState.Installed) { 0 } else { 1 }); Lines = @("ModuleNotFoundError: No module named 'fastapi'") }
        }
    }
    Remove-Item -LiteralPath (Join-Path $fakeVenv ".memora-pyproject.sha256") -Force -ErrorAction SilentlyContinue
    Ensure-PythonProjectEnvironment $fakePython $bootstrapRoot $noneMetadataInvoker | Out-Null
    if (-not $noneMetadataState.Installed) { throw "Empty/None distribution metadata did not trigger dependency installation." }

    $nativeNoStart = Invoke-NativeResult (Join-Path $testRoot "missing-python.exe") @("--version") 2
    if (-not $nativeNoStart.InvocationFailed -or $nativeNoStart.TimedOut) { throw "A child-process launch failure was not classified correctly." }

    $timeoutScript = Join-Path $testRoot "timeout.cmd"
    [IO.File]::WriteAllText($timeoutScript, "@ping 127.0.0.1 -n 6 >nul`r`n")
    $nativeTimeout = Invoke-NativeResult $timeoutScript @() 1
    if (-not $nativeTimeout.TimedOut -or -not $nativeTimeout.InvocationFailed) { throw "A timed-out native subprocess was not terminated and classified." }

    $completeState = @{ InstallCount = 0 }
    $completeInvoker = {
        param($Path, $CommandArgs)
        $command = $CommandArgs -join " "
        if ($command -eq "-m pip install -e .") { $completeState.InstallCount++; return @{ ExitCode = 0; Lines = @() } }
        return @{ ExitCode = 0; Lines = @("ready") }
    }
    $completeResult = Ensure-PythonProjectEnvironment $fakePython $bootstrapRoot $completeInvoker
    if ($completeResult.Installed -or $completeState.InstallCount -ne 0) { throw "Complete unchanged environment reinstalled unnecessarily." }

    Remove-Item -LiteralPath (Join-Path $fakeVenv ".memora-pyproject.sha256") -Force
    $partialState = @{ RuntimeReady = $false; InstallCount = 0 }
    $partialInvoker = {
        param($Path, $CommandArgs)
        $command = $CommandArgs -join " "
        if ($command -eq "-m pip --version" -or $command -eq "-m pip check") { return @{ ExitCode = 0; Lines = @("consistent") } }
        if ($command -eq "-m pip install -e .") { $partialState.InstallCount++; $partialState.RuntimeReady = $true; return @{ ExitCode = 0; Lines = @("installed") } }
        if ($CommandArgs[0] -eq "-c") {
            if ($partialState.RuntimeReady) { return @{ ExitCode = 0; Lines = @($(if ($CommandArgs[1] -match 'importlib.metadata') { "0.1.0" } else { "" })) } }
            return @{ ExitCode = 1; Lines = @("ModuleNotFoundError: No module named 'uvicorn'") }
        }
    }
    Ensure-PythonProjectEnvironment $fakePython $bootstrapRoot $partialInvoker | Out-Null
    if ($partialState.InstallCount -ne 1) { throw "Partial environment did not trigger project installation." }

    Remove-Item -LiteralPath (Join-Path $fakeVenv ".memora-pyproject.sha256") -Force
    $failedInstallInvoker = {
        param($Path, $CommandArgs)
        $command = $CommandArgs -join " "
        if ($command -eq "-m pip --version" -or $command -eq "-m pip check") { return @{ ExitCode = 0; Lines = @("ok") } }
        if ($command -eq "-m pip install -e .") { return @{ ExitCode = 1; Lines = @("Collecting dependencies", "ERROR: synthetic installation failure") } }
        return @{ ExitCode = 1; Lines = @("ModuleNotFoundError: No module named 'fastapi'") }
    }
    $installFailureClear = $false
    try { Ensure-PythonProjectEnvironment $fakePython $bootstrapRoot $failedInstallInvoker | Out-Null }
    catch { $installFailureClear = $_.Exception.Message -match "could not install Python dependencies.*synthetic installation failure" }
    if (-not $installFailureClear) { throw "Installation failure did not retain a concise meaningful diagnostic." }

    Remove-Item -LiteralPath (Join-Path $fakeVenv ".memora-pyproject.sha256") -Force -ErrorAction SilentlyContinue
    $postInstallCheckCount = 0
    $inconsistentInvoker = {
        param($Path, $CommandArgs)
        $command = $CommandArgs -join " "
        if ($command -eq "-m pip --version") { return @{ ExitCode = 0; Lines = @("pip") } }
        if ($command -eq "-m pip check") {
            $script:postInstallCheckCount++
            if ($script:postInstallCheckCount -gt 1) { return @{ ExitCode = 1; Lines = @("package conflict detected") } }
            return @{ ExitCode = 0; Lines = @("No broken requirements found.") }
        }
        if ($command -eq "-m pip install -e .") { return @{ ExitCode = 0; Lines = @("installed") } }
        if ($CommandArgs[0] -eq "-c") {
            if ($script:postInstallCheckCount -gt 0) { return @{ ExitCode = 0; Lines = @($(if ($CommandArgs[1] -match 'importlib.metadata') { "0.1.0" } else { "" })) } }
            return @{ ExitCode = 1; Lines = @("ModuleNotFoundError: missing runtime") }
        }
    }
    $consistencyFailureClear = $false
    try { Ensure-PythonProjectEnvironment $fakePython $bootstrapRoot $inconsistentInvoker | Out-Null }
    catch { $consistencyFailureClear = $_.Exception.Message -match "pip reported an inconsistent environment.*package conflict detected" }
    if (-not $consistencyFailureClear) { throw "Post-install pip consistency failure was not reported." }

    $traceDiagnostic = Get-MeaningfulDiagnostic @(
        "Traceback (most recent call last):", "  File '<string>', line 1", "ModuleNotFoundError: No module named 'fastapi'"
    )
    if ($traceDiagnostic -ne "ModuleNotFoundError: No module named 'fastapi'") { throw "Multiline traceback lost its meaningful final exception." }

    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        $port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
        if (-not (Test-PortOpen $port)) { throw "An occupied local port was not detected." }
    } finally { $listener.Stop() }
    if (Test-PortOpen $port 100) { throw "A released local port was still reported occupied." }
    $savedBackendUrl = $script:BackendUrl
    try {
        $script:BackendUrl = "http://127.0.0.1:$port"
        if ((Get-Readiness "synthetic-token").State -ne "Offline") { throw "Offline readiness was misclassified." }
    } finally { $script:BackendUrl = $savedBackendUrl }

    $savedEmbedding = $env:MEMORA_EMBEDDING_PROVIDER
    $savedSynthesis = $env:MEMORA_SYNTHESIS_PROVIDER
    $savedFacts = $env:MEMORA_FACT_PROVIDER
    $savedKey = $env:OPENAI_API_KEY
    $savedThreshold = $env:MEMORA_RELEVANCE_MIN_SIMILARITY
    $savedToken = $env:MEMORA_LOCAL_TOKEN
    try {
        if ((Read-ProcessingModeChoice { param($Prompt) "" }) -ne "Enhanced") { throw "Empty mode choice did not default to Enhanced." }
        if ((Read-ProcessingModeChoice { param($Prompt) "1" }) -ne "Enhanced") { throw "Choice 1 did not select Enhanced." }
        if ((Read-ProcessingModeChoice { param($Prompt) "2" }) -ne "Local") { throw "Choice 2 did not select Local." }
        $choices = [Collections.Generic.Queue[string]]::new()
        $choices.Enqueue("invalid")
        $choices.Enqueue("2")
        if ((Read-ProcessingModeChoice { param($Prompt) $choices.Dequeue() }) -ne "Local") { throw "Invalid mode choice did not reprompt." }

        $normalPrompted = $false
        $normal = Resolve-ProcessingMode $true "Enhanced" $false `
            { param($Prompt) $script:normalPrompted = $true; "2" } `
            { param($Prompt) $script:normalPrompted = $true; "n" }
        if ($normal.Mode -ne "Enhanced" -or $normal.Changed -or $normalPrompted) { throw "Existing normal configuration prompted or changed." }
        $kept = Resolve-ProcessingMode $true "Enhanced" $true { param($Prompt) "2" } { param($Prompt) "" }
        if ($kept.Mode -ne "Enhanced" -or $kept.Changed) { throw "Setup did not keep the current mode by default." }
        $keepChoices = [Collections.Generic.Queue[string]]::new()
        $keepChoices.Enqueue("invalid")
        $keepChoices.Enqueue("y")
        $keptAfterInvalid = Resolve-ProcessingMode $true "Local" $true `
            { param($Prompt) throw "Mode selector should not run when current mode is kept." } `
            { param($Prompt) $keepChoices.Dequeue() }
        if ($keptAfterInvalid.Mode -ne "Local" -or $keptAfterInvalid.Changed) { throw "Invalid keep choice did not reprompt safely." }
        $changed = Resolve-ProcessingMode $true "Enhanced" $true { param($Prompt) "2" } { param($Prompt) "n" }
        if ($changed.Mode -ne "Local" -or -not $changed.Changed) { throw "Setup could not change processing mode." }

        $env:MEMORA_EMBEDDING_PROVIDER = "local"
        $env:MEMORA_SYNTHESIS_PROVIDER = "deterministic"
        $env:MEMORA_FACT_PROVIDER = "deterministic"
        $env:OPENAI_API_KEY = ""
        Ensure-ProviderConfiguration `
            { param($Prompt) throw "Local mode requested an API key." } `
            { param($Prompt) throw "Local mode requested key persistence." } `
            { param($Prompt) throw "Local mode requested a semantic threshold." }

        $env:MEMORA_LOCAL_TOKEN = "unchanged-synthetic-local-token-00000000000000000000000000000000"
        Set-ProcessingMode "Enhanced" $envFile
        if ($env:MEMORA_LOCAL_TOKEN -ne "unchanged-synthetic-local-token-00000000000000000000000000000000") {
            throw "Changing processing mode rotated the Memora token."
        }
        $env:OPENAI_API_KEY = ""
        $env:MEMORA_RELEVANCE_MIN_SIMILARITY = ""
        $captured = & {
            Ensure-ProviderConfiguration `
                { param($Prompt) "synthetic-private-key-not-for-output" } `
                { param($Prompt) "n" } `
                { param($Prompt) "0.17" }
        } 6>&1 | Out-String
        if ($captured.Contains("synthetic-private-key-not-for-output")) { throw "API key appeared in launcher output." }
        if ($env:MEMORA_RELEVANCE_MIN_SIMILARITY -ne "0.17") { throw "Enhanced threshold was not configured." }
        if ((Read-DotEnv $envFile).ContainsKey("OPENAI_API_KEY")) { throw "API key was saved without explicit confirmation." }

        $env:MEMORA_EMBEDDING_PROVIDER = "invalid"
        $providerRejected = $false
        try { Ensure-ProviderConfiguration } catch { $providerRejected = $true }
        if (-not $providerRejected) { throw "An invalid provider was accepted." }
        $env:MEMORA_EMBEDDING_PROVIDER = "openai"
        $env:OPENAI_API_KEY = "synthetic-test-key"
        $env:MEMORA_RELEVANCE_MIN_SIMILARITY = ""
        $thresholdRejected = $false
        try {
            Ensure-ProviderConfiguration `
                { param($Prompt) throw "Unexpected key prompt." } `
                { param($Prompt) throw "Unexpected save prompt." } `
                { param($Prompt) "" }
        } catch { $thresholdRejected = $true }
        if (-not $thresholdRejected) { throw "OpenAI embeddings without a relevance floor were accepted." }

        $database = Join-Path $testRoot "populated.sqlite3"
        [IO.File]::WriteAllText($database, "synthetic database marker")
        $readConfirm = { param($Prompt) "" }
        if (Confirm-EmbeddingModeSwitch "local" "openai" "sqlite:///./populated.sqlite3" $testRoot $readConfirm) {
            throw "A populated incompatible database switched without explicit confirmation."
        }
        if (-not (Confirm-EmbeddingModeSwitch "local" "openai" "sqlite:///./populated.sqlite3" $testRoot { param($Prompt) "y" })) {
            throw "An explicit provider-switch confirmation was ignored."
        }
    } finally {
        $env:MEMORA_EMBEDDING_PROVIDER = $savedEmbedding
        $env:MEMORA_SYNTHESIS_PROVIDER = $savedSynthesis
        $env:MEMORA_FACT_PROVIDER = $savedFacts
        $env:OPENAI_API_KEY = $savedKey
        $env:MEMORA_RELEVANCE_MIN_SIMILARITY = $savedThreshold
        $env:MEMORA_LOCAL_TOKEN = $savedToken
    }

    if (Test-Path -LiteralPath (Join-Path $testRoot "package.json")) { throw "Synthetic repository root unexpectedly has package.json." }
    $extension = Join-Path $testRoot "Extension Project"
    [IO.Directory]::CreateDirectory((Join-Path $extension "src")) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $extension "scripts")) | Out-Null
    foreach ($file in @("manifest.json", "popup.html", "popup.css", "package.json", "package-lock.json", "tsconfig.json", "vitest.config.ts")) {
        [IO.File]::WriteAllText((Join-Path $extension $file), "test")
    }
    [IO.File]::WriteAllText((Join-Path $extension "scripts\build.mjs"), "test")
    [IO.File]::WriteAllText((Join-Path $extension "src\content.ts"), "test")
    [IO.Directory]::CreateDirectory((Join-Path $extension "node_modules")) | Out-Null
    if (-not (Test-NodeDependenciesNeedInstall $extension)) { throw "Missing installed lock was not detected." }
    [IO.File]::WriteAllText((Join-Path $extension "node_modules\.package-lock.json"), "test")
    (Get-Item (Join-Path $extension "node_modules\.package-lock.json")).LastWriteTimeUtc = [DateTime]::UtcNow.AddMinutes(1)
    if (Test-NodeDependenciesNeedInstall $extension) { throw "Current locked dependencies were marked stale." }
    if (-not (Test-ExtensionBuildNeeded $extension)) { throw "A missing build was not detected." }
    [IO.Directory]::CreateDirectory((Join-Path $extension "dist")) | Out-Null
    foreach ($file in @("background.js", "content.js", "popup.js", "popup.html", "popup.css", "manifest.json")) {
        [IO.File]::WriteAllText((Join-Path $extension "dist\$file"), "test")
        (Get-Item (Join-Path $extension "dist\$file")).LastWriteTimeUtc = [DateTime]::UtcNow.AddMinutes(1)
    }
    if (-not (Test-ExtensionBuildNeeded $extension)) { throw "A complete existing build without a stamp did not trigger its one-time migration build." }
    Set-ExtensionBuildStamp $extension
    if (Test-ExtensionBuildNeeded $extension) { throw "Required outputs with a current build stamp were marked stale." }
    if (-not (Test-ExtensionBuildRequested $extension $true)) { throw "-RebuildExtension did not force a build." }

    $originalLocation = (Get-Location).Path
    $npmCalls = [Collections.Generic.List[object]]::new()
    $npmInvoker = {
        param($Path, $CommandArgs, $Timeout, $Directory)
        $npmCalls.Add([pscustomobject]@{ Arguments = $CommandArgs -join " "; Directory = $Directory })
        return @{ ExitCode = 0; Lines = @("ok") }
    }
    Invoke-ExtensionNpm "C:\Program Files\nodejs\npm.cmd" @("ci") $extension "dependency failure" $npmInvoker | Out-Null
    Invoke-ExtensionNpm "C:\Program Files\nodejs\npm.cmd" @("run", "build") $extension "build failure" $npmInvoker | Out-Null
    if ($npmCalls.Count -ne 2 -or $npmCalls[0].Arguments -ne "ci" -or
        $npmCalls[1].Arguments -ne "run build" -or
        $npmCalls[0].Directory -ne $extension -or $npmCalls[1].Directory -ne $extension) {
        throw "npm commands did not receive the extension working directory."
    }
    if ((Get-Location).Path -ne $originalLocation) { throw "Extension subprocess changed the caller's working directory." }

    $cwdScript = Join-Path $testRoot "report-cwd.cmd"
    [IO.File]::WriteAllText($cwdScript, "@echo %CD%`r`n")
    $cwdResult = Invoke-NativeResult $cwdScript @() 5 $extension
    if ($cwdResult.ExitCode -ne 0 -or ([string]$cwdResult.Lines[0]).Trim() -ne $extension -or
        (Get-Location).Path -ne $originalLocation) {
        throw "Native subprocess did not preserve an explicit working directory containing spaces."
    }

    $missingExtensionRejected = $false
    try { Invoke-ExtensionNpm "npm.cmd" @("ci") (Join-Path $testRoot "missing extension") "failure" $npmInvoker | Out-Null }
    catch { $missingExtensionRejected = $_.Exception.Message -match "extension directory was not found" }
    if (-not $missingExtensionRejected) { throw "Missing extension directory was not rejected." }

    $buildFailureRejected = $false
    $failedNpmInvoker = { param($Path, $CommandArgs, $Timeout, $Directory) @{ ExitCode = 1; Lines = @("npm cache detail", "ERROR: synthetic build failure") } }
    try { Invoke-ExtensionNpm "npm.cmd" @("run", "build") $extension "Memora could not build the Chrome extension." $failedNpmInvoker | Out-Null }
    catch { $buildFailureRejected = $_.Exception.Message -eq "Memora could not build the Chrome extension. Run with -Verbose for details." }
    if (-not $buildFailureRejected) { throw "Extension build failure did not use bounded user-facing error text." }

    Remove-Item -LiteralPath (Join-Path $extension "dist\content.js") -Force
    Remove-Item -LiteralPath (Join-Path $extension "dist\.memora-build-stamp") -Force
    $missingOutputRejected = $false
    try { Invoke-ExtensionProductionBuild "npm.cmd" $extension $npmInvoker }
    catch { $missingOutputRejected = $_.Exception.Message -match "content.js" }
    if (-not $missingOutputRejected) { throw "A successful build missing required dist output was accepted." }
    if (Test-Path -LiteralPath (Join-Path $extension "dist\.memora-build-stamp")) {
        throw "An incomplete extension build received a successful build stamp."
    }
    [IO.File]::WriteAllText((Join-Path $extension "dist\content.js"), "test")

    foreach ($staticOutput in @("manifest.json", "popup.html", "popup.css")) {
        (Get-Item (Join-Path $extension "dist\$staticOutput")).LastWriteTimeUtc = [DateTime]::UtcNow.AddDays(-7)
    }
    Invoke-ExtensionProductionBuild "npm.cmd" $extension $npmInvoker
    if (-not (Test-Path -LiteralPath (Join-Path $extension "dist\.memora-build-stamp")) -or
        (Test-ExtensionBuildNeeded $extension)) {
        throw "A successful verified build with preserved old static mtimes was immediately classified stale."
    }

    (Get-Item (Join-Path $extension "src\content.ts")).LastWriteTimeUtc = [DateTime]::UtcNow.AddMinutes(2)
    if (-not (Test-ExtensionBuildNeeded $extension)) { throw "A stale extension source did not trigger a rebuild." }

    $stampBeforeUnrelatedChanges = (Get-Item (Join-Path $extension "dist\.memora-build-stamp")).LastWriteTimeUtc
    $unrelatedBackend = Join-Path $testRoot "backend.py"
    $unrelatedDocs = Join-Path $testRoot "README.md"
    $unrelatedLauncher = Join-Path $testRoot "start-memora.ps1"
    foreach ($unrelated in @($unrelatedBackend, $unrelatedDocs, $unrelatedLauncher)) {
        [IO.File]::WriteAllText($unrelated, "unrelated")
        (Get-Item $unrelated).LastWriteTimeUtc = [DateTime]::UtcNow.AddDays(1)
    }
    # Reset the one intentionally stale extension input; unrelated repository
    # files must not influence the extension freshness decision.
    (Get-Item (Join-Path $extension "src\content.ts")).LastWriteTimeUtc = $stampBeforeUnrelatedChanges.AddSeconds(-1)
    if (Test-ExtensionBuildNeeded $extension) { throw "Backend, docs, or launcher changes incorrectly made the extension stale." }

    Write-Host "Launcher helper checks passed."
} finally {
    $script:DotEnvPath = $savedDotEnvPath
    Remove-Item -LiteralPath $testRoot -Recurse -Force
    Remove-Item Env:MEMORA_LAUNCHER_TEST_MODE -ErrorAction SilentlyContinue
}
