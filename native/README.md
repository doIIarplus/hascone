# Native Windows shell

The default desktop app uses .NET Framework Windows Forms and the installed
Microsoft WebView2 Runtime.

The native window appears before runtime verification, extraction or backend startup.
First use extracts the embedded backend into Hascone-data/runtime/<payload hash>/.
Later launches reuse the complete cache. A ready marker is written only after
successful extraction. Partial extractions are discarded and retried, while
profiles and settings stay untouched. Keep Hascone-data with the executable when moving.

Closing the window cancels preparation and terminates the owned backend. A Windows
job object also terminates it if the shell crashes. Repeat launches activate the
existing window. Failures show a retry button, logs and a WebView2 download link
when that runtime is missing.

Build: python tools/build_native.py (or build.ps1).
Developer shell only: python tools/build_native.py --dev.
Diagnostic launch: Hascone.exe --smoke-test --data-dir <isolated test folder>.
Successful diagnostics write native-smoke.json including startup times and cache status.
The --backend-root option uses a prepared backend or development checkout.

WebView2 SDK source: https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.4191.47
Runtime documentation: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution
