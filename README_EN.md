========================================================================
  Google AI Pro (5 TB) Zero Cost for Two Years (US$0.00 -> 24 months) Fully Automated Console
========================================================================

The main English guide is [README.md](README.md). See its
[Usage section](README.md#2-usage) for launch commands, console controls, and
troubleshooting, and its [language notes](README.md#language-and-automation-compatibility)
for why Google-page matching strings remain multilingual.

[1. Runtime Requirements]
1. Linux (tested on x86_64 with Chromium); macOS should also work
2. Chromium or Google Chrome installed and on PATH (`chromium`, `google-chrome` or `chrome`),
   or point the CHROME_PATH environment variable at the binary
3. Python 3.10 or higher installed
4. Network: enable a US proxy on this machine, or fill in the proxy template on the left of the console

[2. Quick Start]
1. Run the launcher once: ./run.sh
   It creates a .venv, installs the dependencies, and starts the console.
2. Later runs: ./run.sh again
3. The console page opens automatically: http://127.0.0.1:8765
   (If your desktop has no default browser opener, open that URL manually.)

[Linux notes]
- Chromium runs with `--no-sandbox` automatically when needed, and
  `--password-store=basic --use-mock-keychain` so it never asks for a keyring.
- Port cleanup uses `ss`/`lsof` and signals instead of netstat/taskkill.
- Chromium adds `--headless=new` when no X11/Wayland display is available.
  `HEADLESS=1` is not a supported setting in the current code.
- The original Windows .bat launchers are kept and still work on Windows.

[3. Entering Your Payment Card & Running Accounts]
1. Enter the payment card (required):
   - In the [Global configuration & inline tax-exempt card binding] area on the left of the page, enter your own Visa or Mastercard foreign-currency card:
     * Card number (16 digits)
     * Expiry (month / year, e.g. 08 / 29)
     * Security code (3-digit CVC)
     * Cardholder name in Latin letters
     * The tax-exempt ZIP code is pre-filled with 97201 (Oregon, a US tax-free state); no change needed
   - Then click [💾 Save config].
   - Note: the script has a strict zero-charge guard. It only clicks subscribe when the checkout popup confirms US$0.00, so nothing is charged.

2. Bulk import Google accounts:
   - Paste accounts (one per line) into the [Batch account import] area on the right of the page. Any of these formats works:
     * email----password----recovery email
     * email----password----recovery email----2FA secret
     * email----password----2FA secret
   - Click [➕ Import accounts].

3. Start the fully automated run:
   - Click [▶ Run] next to a single account, or [▶ Run all pending accounts] at the top.
   - The script automatically does:
     Step 1: Sign in to Google and pass recovery-email / 2FA verification
     Step 2: Inline tax-exempt card binding + first-layer 12-month free bundle (US$0.00)
     Step 3: Stack the second-layer 6-month free bundle (US$0.00 -> 18 months)
     Step 4: Stack the third-layer 6-month free bundle (US$0.00 -> 24 months, the cap)
     Step 5: Go to Google Play, cancel auto-renewal, lock in the 2-year entitlement and save a verification screenshot


# Card shop: https://faka.cdkey.si
# Blog: https://blog.caowo.de
# Telegram group: @Hello_Florence

[Local configuration and Git privacy]
- `config.example.json` is a template with no saved accounts or payment details.
- The app creates a local `config.json` when settings are saved; it is intentionally ignored by Git.
- Browser profiles, screenshots, local artifacts, logs, and Python environments are also ignored.
- Keep private runtime data local; do not force-add ignored files.
