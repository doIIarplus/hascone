# Hascone

A Windows app for scanning MapleStory equipment and comparing upgrades.

## Download

Download the latest portable Windows .exe from the [Releases page](https://github.com/doIIarplus/hascone/releases), then follow the in-app guide.[^Note]

## Run from source

Install Python 3.12, run `setup.ps1`, then `start.bat`.

## MapleScouter browser verification

Both native browser environments include the
`AutofillAiWalletPrivatePasses` workaround for
[WebView2Feedback #5722](https://github.com/MicrosoftEdge/WebView2Feedback/issues/5722).
An isolated launch and actual app startup were checked against the Windows
Security log without new failed logons. Creating `configs/scouter_network_paused`
pauses browser startup and MapleScouter requests during investigation. HTTP
authentication cancellation alone does not address that startup issue.

The Windows app opens a visible, muted MapleScouter browser when verification
or public client configuration is needed. It closes completely once the session
and configuration are ready, before calculations run. Close it to cancel verification.
Calculations reuse the verified session through HTTP; no hidden webpage remains
running. An expired session opens a visible verification window again.

Verification starts automatically when needed. The browser profile is saved;
its MapleScouter cookies are handed to the app's HTTP client in memory only.
**Stop** also cancels a pending request. If verification fails, use
**Export to MapleScouter** to calculate on the site.

[^Note]: Some users have reported Spinning Runes and Lie Detector prompts while using Hascone; I'm looking into it, but it's unclear whether the app is the cause. Hascone only takes screenshots of the game window and never touches the game's process or memory, but that doesn't guarantee MapleStory's anti-cheat won't flag it.
