# Installing NEXUS

## 1. Choose how you will run it

| You are... | Use |
|---|---|
| A user with the installer | [Installer](#installer) |
| A developer / running from source | [From source](#from-source) |

Supported: **Windows 10 or 11, 64-bit.** You do not need Python when using the installer.

## Installer

> The installer is produced by `scripts\build.ps1` (see [RELEASE.md](RELEASE.md)). If you were given a
> `NEXUS-Setup-<version>.exe`, that is what these steps use.

1. Run `NEXUS-Setup-<version>.exe`. It installs for **your Windows user only** (no administrator rights).
   Windows SmartScreen may warn about an unrecognised publisher until the installer is code-signed;
   choose *More info → Run anyway* only if you trust where you got the file.
2. Optional checkboxes: a desktop shortcut, and "Install natural voice (Kokoro)" (see [VOICE.md](VOICE.md);
   roughly 1-2 GB (estimate), needs Python 3.10-3.12).
3. Start **NEXUS** from the Start menu. The first-run wizard asks which AI engine you want, lets you test it,
   and offers voice and privacy choices. Nothing is saved until you press **Finish**; **Skip setup** keeps
   safe defaults.

NEXUS never adds itself to Windows startup on its own. That is a switch in **Settings → Windows startup**.

**Uninstall:** Settings → Apps → NEXUS. You are asked whether to also delete your data
(`%LOCALAPPDATA%\NEXUS`). Choose *No* to keep conversations and reminders for a future reinstall.
A Gemini key you saved lives in Windows Credential Manager under the name `NEXUS`; remove it there if you
want it gone.

**Upgrade:** run the newer installer over the old one. Your data is stored outside the install folder, so
it is kept.

## Set up the AI engine

You need **one** of these (you can set up both).

### Local AI (private, works offline)

1. Install Ollama from <https://ollama.com/download> and start it.
2. In a terminal:

   ```powershell
   ollama pull llama3.1:8b
   ollama create nexus -f "<path to models\Modelfile>"
   ```

   * From source: `models\Modelfile` inside the project folder.
   * Installed app: `<install folder>\_internal\models\Modelfile`
     (default `%LOCALAPPDATA%\Programs\NEXUS\_internal\models\Modelfile`).

   `nexus` is *built locally* from that file. It is not downloadable, so `ollama pull nexus` will not work.
   The app tells you the exact command, with the right path, if the model is missing.
3. Settings → **AI engine → Local**, then use the **Test** button in the wizard or Settings.

NEXUS only *checks* for Ollama and the models. It never downloads software or model weights by itself.
The `llama3.1:8b` model is about 5 GB; allow 8 GB RAM minimum (16 GB is comfortable). Speed depends on your CPU/GPU.

### Online AI (Google Gemini)

1. Create an API key in Google AI Studio.
2. Settings → **Gemini API key** → paste it → **Save key & use Gemini**. It is stored in Windows
   Credential Manager. (Or set the `GEMINI_API_KEY` environment variable; see [CONFIGURATION.md](CONFIGURATION.md).)
3. Gemini usage may be rate-limited or billed by Google according to your account. NEXUS retries a small,
   fixed number of times and then tells you what happened; it never loops forever.

### Which mode?

| Mode | Text goes to | Needs |
|---|---|---|
| Local | Your PC only | Ollama + models |
| Online | Gemini (except requests that need your PC's tools, which stay local) | Key + internet |
| Automatic | Your PC, except a few "research / long document"-style requests when a key exists | Either |

Local mode is the only mode where nothing can leave your computer. See [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md).

## From source

Requirements: Windows 10/11, Python **3.11 or 3.12** (64-bit), Git.

```powershell
git clone https://github.com/12nshuti-cpu/1nexus
cd 1nexus
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Run the checks:

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python app.py --selftest
```

Notes:

* Python 3.13 is fine for running NEXUS itself, but **Kokoro** (the optional voice) needs Python 3.10-3.12 and
  runs in its own environment, so it never constrains the main app. See [VOICE.md](VOICE.md).
* `requirements.txt` holds only what NEXUS needs at run time. PyTorch/Kokoro and the Ollama models are **not**
  in it on purpose.
* Settings live in the Windows registry (`HKEY_CURRENT_USER\Software\NEXUS\NEXUS`); data lives in
  `%LOCALAPPDATA%\NEXUS`.
