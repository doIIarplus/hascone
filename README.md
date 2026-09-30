# Hascone

A Windows app for scanning MapleStory equipment and comparing upgrades.

## Download

Download the latest portable Windows .exe from the [Releases page](https://github.com/doIIarplus/hascone/releases), then follow the in-app guide.

## Note

Some users have reported Spinning Runes and Lie Detector prompts while using Hascone. I'm looking into potential solutions, but unclear if this app is the cause.

Hascone captures screenshots of the game window using Windows Graphics Capture and reads the images with OCR. It does not hook into or inject code into the game process, or read or modify game memory. Its capture approach is similar to the screen-sharing and recording features of apps such as OBS and Discord. Capture stops when a scan ends.

This design avoids accessing the game process, but it does not guarantee that MapleStory's anti-cheat will never flag its use or trigger additional checks.

## Run from source

Install Python 3.12, run `setup.ps1`, then `start.bat`.
