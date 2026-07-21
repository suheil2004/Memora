# Setting Up Memora

This guide is only for getting Memora running. For a full explanation of the product and how the memory system works, see [README.md](../README.md) and [PRODUCT.md](PRODUCT.md).

## Before you start

You need:

- Windows with Windows PowerShell 5.1 or newer PowerShell
- Python 3.11 or newer
- Node.js 20 or newer with npm
- Google Chrome
- An OpenAI API key only if you want to use Enhanced mode

## Start Memora

Open PowerShell in the root of the repository and run:

```powershell
.\start-memora.ps1
```

The first launch may take a little longer because Memora sets up the Python environment, installs missing dependencies, and builds the Chrome extension.

During setup, choose:

- **Enhanced** for the full OpenAI-backed experience
- **Local** to run without an OpenAI API key

Keep the PowerShell window open while using Memora. Closing it stops the local backend.

## Install the Chrome extension

After the launcher finishes:

1. Open `chrome://extensions`.
2. Turn on **Developer mode**.
3. Select **Load unpacked**.
4. Choose:

   ```text
   <repository>\extension\dist
   ```

5. Open the Memora extension popup.
6. Keep the backend URL as:

   ```text
   http://127.0.0.1:8765
   ```

7. Paste the local Memora token copied by the launcher.
8. Select **Save settings**.

The Memora token is not your OpenAI API key.

After rebuilding the extension, reload Memora in `chrome://extensions` and refresh ChatGPT.

## Import your memory

Open the Memora popup and use **Import memory** to import a supported ChatGPT JSON or ZIP export.

You can also use **Import additional PDFs** for supported text-based PDFs.

Memora only imports files you explicitly choose.

## Use Memora

1. Open ChatGPT.
2. Write a prompt without sending it.
3. Open the Memora panel.
4. Select **Retrieve memory**.
5. Review the MemoryBriefs.
6. Select **Use This Context** on the memory you want.
7. Review the updated draft and send it yourself.

Use **Search current prompt** to retrieve memory for a new topic.

Use **Clear results** to clear the current cards without deleting stored memory.

## Start Memora again later

Run:

```powershell
.\start-memora.ps1
```

Your existing setup is reused.

Keep the terminal open while using Memora. Press `Ctrl+C` when you are done.

## Useful launcher options

```powershell
.\start-memora.ps1 -Setup
.\start-memora.ps1 -RebuildExtension
.\start-memora.ps1 -ShowToken
.\start-memora.ps1 -Verbose
```

## Troubleshooting

### Backend is offline

Run:

```powershell
.\start-memora.ps1
```

and keep the terminal open.

### Authentication failed

The token saved in the extension does not match the backend token.

Run:

```powershell
.\start-memora.ps1 -ShowToken
```

Then paste that token into the Memora popup and save the settings.

### Extension changes do not appear

Run:

```powershell
.\start-memora.ps1 -RebuildExtension
```

Then reload Memora in `chrome://extensions` and refresh ChatGPT.

### Python or Node.js is missing

Check:

```powershell
python --version
node --version
npm.cmd --version
```

Make sure the supported versions are installed, then reopen PowerShell and run the launcher again.

### Something else failed

Run:

```powershell
.\start-memora.ps1 -Verbose
```

The extra output should show which setup stage failed.