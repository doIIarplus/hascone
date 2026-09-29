# Writing patch notes

Before tagging a version, add `release-notes/<version>.md` (for example, `1.1.3.md`) and update the version in `tools/build_native.py`, `app.py`, and `native/app.manifest`.

Describe changes users will notice: what they can do now, what was fixed, and any action they need to take. Keep notes short and use plain-text paragraphs and bullets; the in-app viewer displays the text without executing HTML. Avoid commit hashes, implementation details, and generic headings like “Various improvements.”

The publishing workflow requires this file and uses it as the GitHub release description. The app reads that same description for the update's patch notes. Edit a published release description on GitHub to correct its notes.
