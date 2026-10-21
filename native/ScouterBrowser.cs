using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// A visible verification browser. Its same-site session is handed to the local
// HTTP transport in memory, then the actual window and WebView are disposed.
internal sealed class ScouterBrowser : IDisposable {
    const string SiteOrigin = "https://maplescouter.com";
    const string Api = "https://api.maplescouter.com";
    readonly Form owner;
    readonly string origin, token, profile;
    readonly string consumer = Guid.NewGuid().ToString("N");
    WebView2 web;
    Label status;
    internal Form Window { get; private set; }
    internal bool IsDisposed { get { return stop.IsCancellationRequested; } }
    readonly CancellationTokenSource stop = new CancellationTokenSource();
    readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 32000000 };
    readonly Action<CoreWebView2> setup;
    readonly Action<string> log;
    TaskCompletionSource<Dictionary<string, object>> response;
    Task abortFetch = Task.FromResult(true);
    string activeId, fetchNonce;
    string publicApiKey;
    bool running, challenge, navigationReady, verifying;

    internal ScouterBrowser(Form owner, string origin, string token, string profile, Action<CoreWebView2> setup = null, Action<string> log = null) {
        this.owner = owner; this.origin = origin; this.token = token; this.profile = profile; this.setup = setup; this.log = log;
    }

    internal void Close() {
        stop.Cancel();
        if (response != null) response.TrySetCanceled();
        CloseWindow();
    }

    public void Dispose() { Close(); }

    void CloseWindow() {
        if (Window == null) return;
        var closing = Window;
        Window = null; web = null; navigationReady = false; publicApiKey = null;
        closing.Dispose();
        if (!owner.IsDisposed) owner.Activate();
    }

    internal async void Connect() {
        if (running || IsDisposed) return;
        running = true;
        try {
            await Local("connect", new { client = consumer });
            while (!stop.IsCancellationRequested) {
                var envelope = await Local(web == null ? "jobs?idle=1" : "jobs");
                var job = envelope["job"] as Dictionary<string, object>;
                if (job == null) {
                    object busy;
                    if (!envelope.TryGetValue("busy", out busy) || !(bool)busy) CloseWindow();
                    continue;
                }
                activeId = Get(job, "id");
                object result;
                try { await EnsureBrowser(); result = await Run(job); }
                catch (Exception ex) { result = new { error = stop.IsCancellationRequested ? "Verification window closed. Retry to reconnect." : ex.Message }; }
                await Local("jobs/" + activeId + "/result", result, true);
                activeId = null;
                await abortFetch;
            }
        } catch (Exception ex) {
            if (log != null) log("SCOUTER_BROWSER " + ex.GetType().Name + ": " + ex.Message);
            // The backend may have closed or replaced this connection. Any
            // in-flight request is failed by disconnect, never replayed.
        }
        if (activeId != null) {
            try { await Local("jobs/" + activeId + "/result", new { error = "MapleScouter browser disconnected. Retry to reconnect." }, true); } catch { }
        }
        try { await Local("disconnect", new { }, true); } catch { }
        if (!IsDisposed) Close();
    }

    async Task EnsureBrowser() {
        if (web != null) return;
        stop.Token.ThrowIfCancellationRequested();
        Window = new Form {
            Text = "Hascone - MapleScouter", Size = new Size(1100, 800),
            StartPosition = FormStartPosition.CenterParent, Font = new Font("Segoe UI", 11)
        };
        status = new Label { Dock = DockStyle.Top, Height = 54, Padding = new Padding(12),
            Text = "Connecting to MapleScouter. Close this window to cancel." };
        web = new WebView2 { Dock = DockStyle.Fill };
        Window.Controls.Add(web); Window.Controls.Add(status);
        Window.FormClosing += (s, e) => {
            stop.Cancel(); if (response != null) response.TrySetCanceled();
        };
        Window.FormClosed += (s, e) => { web = null; Window = null; navigationReady = false; };
        // The user always has a visible window and a working Close button before
        // WebView2 or the remote page is created. Only profile data survives closure.
        Window.Show(owner);
        var options = new CoreWebView2EnvironmentOptions {
            AllowSingleSignOnUsingOSPrimaryAccount = false,
            // WebView2Feedback #5722: suppress the reported startup password
            // check. This is separate from HTTP authentication cancellation.
            AdditionalBrowserArguments = "--disable-features=AutofillAiWalletPrivatePasses"
        };
        var environment = await CoreWebView2Environment.CreateAsync(null, profile, options);
        stop.Token.ThrowIfCancellationRequested();
        await web.EnsureCoreWebView2Async(environment);
        stop.Token.ThrowIfCancellationRequested();
        web.CoreWebView2.IsMuted = true;
        web.CoreWebView2.Settings.AreHostObjectsAllowed = false;
        web.CoreWebView2.BasicAuthenticationRequested += (s, e) => {
            e.Cancel = true;
            if (log != null) log("SCOUTER_BROWSER blocked an HTTP authentication request.");
        };
        web.CoreWebView2.NewWindowRequested += (s, e) => e.Handled = true;
        web.CoreWebView2.NavigationStarting += (s, e) => {
            navigationReady = false;
            Uri uri;
            if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out uri) || uri.GetLeftPart(UriPartial.Authority) != SiteOrigin) e.Cancel = true;
        };
        // Session readiness doesn't require waiting for images and other page
        // assets to finish. Ready still checks the site's actual session marker.
        web.CoreWebView2.DOMContentLoaded += (s, e) => navigationReady = true;
        web.CoreWebView2.WebMessageReceived += (s, e) => {
            if (response == null || e.Source != SiteOrigin + "/en/input") return;
            try {
                var message = json.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
                if (Get(message, "nonce") == fetchNonce) response.TrySetResult(message);
            } catch { /* Ignore unrelated site messages. */ }
        };
        web.CoreWebView2.WebResourceResponseReceived += (s, e) => {
            if (activeId == null || e.Request.Uri != activeUrl) return;
            try { if (e.Response.Headers.GetHeader("cf-mitigated") == "challenge") challenge = true; }
            catch { /* Header is absent on ordinary responses. */ }
        };
        var currentWeb = web;
        web.CoreWebView2.WebResourceResponseReceived += async (s, e) => {
            if (publicApiKey != null || e.Request.Method != "GET" || e.Response.StatusCode != 200 ||
                !e.Request.Uri.EndsWith(".js", StringComparison.Ordinal) || !Allowed("GET", e.Request.Uri)) return;
            try {
                // Observe the public scripts already loaded by the site. This
                // avoids fetching the page and each script again via the bridge.
                using (var stream = await e.Response.GetContentAsync()) {
                    if (stream == null) return;
                    using (var reader = new StreamReader(stream)) {
                        var text = new StringBuilder(); var buffer = new char[8192]; int read;
                        while ((read = await reader.ReadAsync(buffer, 0, buffer.Length)) > 0) {
                            if (text.Length + read > 16000000) return;
                            text.Append(buffer, 0, read);
                        }
                        string content = text.ToString();
                        var match = Regex.Match(content, "\"api-key\"\\s*:\\s*\"([^\"\\n]+)\"");
                        if (web == currentWeb && !IsDisposed && match.Success && content.Contains(Api))
                            publicApiKey = match.Groups[1].Value;
                    }
                }
            } catch { /* A failed script response must not interrupt verification. */ }
        };
        if (setup != null) setup(web.CoreWebView2);
        web.CoreWebView2.Navigate(SiteOrigin + "/en/input");
    }

    static string Get(Dictionary<string, object> value, string key) {
        object result; return value.TryGetValue(key, out result) ? result as string : null;
    }

    internal static bool Allowed(string method, string address) {
        Uri uri;
        if (!Uri.TryCreate(address, UriKind.Absolute, out uri) || uri.UserInfo != "" || uri.Fragment != "" || address.Contains("..")) return false;
        string host = uri.GetLeftPart(UriPartial.Authority);
        if (method == "SESSION" || method == "CONFIG") return address == SiteOrigin + "/en/input";
        if (method == "GET" && host == SiteOrigin && uri.Query == "")
            return uri.AbsolutePath == "/en/input" || Regex.IsMatch(uri.AbsolutePath, @"^/_next/static/chunks/[A-Za-z0-9_./%()\-]+\.js$");
        return method == "POST" && host == Api && (uri.AbsolutePath == "/api/calc/dmg" || uri.AbsolutePath == "/api/calc/hexa-order" || uri.AbsolutePath == "/api/calc/dmg-simulator");
    }

    async Task<Dictionary<string, object>> Local(string path, object body = null, bool finishing = false) {
        using (var client = new WebClient()) {
            client.Proxy = null; client.Encoding = Encoding.UTF8;
            client.Headers["X-Hascone-Browser-Token"] = token;
            client.Headers["X-Hascone-Browser-Client"] = consumer;
            using (var timeout = new CancellationTokenSource(25000))
            using (timeout.Token.Register(client.CancelAsync))
            using (stop.Token.Register(() => { if (!finishing) client.CancelAsync(); })) {
                string text;
                try {
                    if (body == null) text = await client.DownloadStringTaskAsync(origin + "/api/scouter/browser/" + path);
                    else {
                        client.Headers[HttpRequestHeader.ContentType] = "application/json";
                        text = await client.UploadStringTaskAsync(origin + "/api/scouter/browser/" + path, "POST", json.Serialize(body));
                    }
                } catch (WebException ex) {
                    if (log != null) log("SCOUTER_BRIDGE " + path + ": " + ex.Message);
                    throw;
                }
                return json.Deserialize<Dictionary<string, object>>(text);
            }
        }
    }

    async Task Active(bool verifying) {
        stop.Token.ThrowIfCancellationRequested();
        var result = await Local("jobs/" + activeId + "/progress", new { verifying = verifying });
        if (!result.ContainsKey("active") || !(bool)result["active"]) throw new Exception("Calculation cancelled or timed out.");
    }

    async Task Ready(bool reload = false) {
        if (!reload && navigationReady) {
            // The site's own session module renews its verification on page load.
            // Read only its expiry marker; the HttpOnly session stays in WebView2.
            reload = await web.CoreWebView2.ExecuteScriptAsync("(()=>{const e=Number(localStorage.getItem('sc_tok_exp'));return e>0&&e<=Date.now()+60000})()") == "true";
        }
        if (reload) { navigationReady = false; web.CoreWebView2.Navigate(SiteOrigin + "/en/input"); }
        var deadline = DateTime.UtcNow.AddSeconds(280);
        while (DateTime.UtcNow < deadline) {
            await Active(verifying);
            if (navigationReady) {
                var state = await web.CoreWebView2.ExecuteScriptAsync(@"(()=>{
                    const challenge=!!document.querySelector('#challenge-running,#challenge-stage')||/just a moment|attention required/i.test(document.title);
                    const interactive=[...document.querySelectorAll('[role=dialog]')].some(e=>
                        (e.getAttribute('aria-label')==='\uc0ac\ub78c \ud655\uc778'||e.querySelector('iframe[src*=""challenges.cloudflare.com""]'))&&
                        getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none'&&e.getBoundingClientRect().height>0);
                    const ready=location.origin==='https://maplescouter.com'&&!!document.querySelector('script[src*=""/_next/static/""]')&&!challenge&&Number(localStorage.getItem('sc_tok_exp'))>Date.now()+60000;
                    return ready?'ready':challenge||interactive?'verify':'loading';
                })()");
                if (state == "\"ready\"") {
                    verifying = false;
                    status.Text = "Connected to MapleScouter. Finishing the session setup, then this window will close.";
                    return;
                }
                verifying = state == "\"verify\"";
                if (verifying) status.Text = "Complete verification below. Close this window to cancel.";
            }
            await Task.Delay(100, stop.Token);
        }
        throw new Exception("MapleScouter verification timed out. Retry when the site is available.");
    }

    string activeUrl;
    async Task<object> Run(Dictionary<string, object> job) {
        string method = Get(job, "method"), url = Get(job, "url");
        if (!Allowed(method, url)) throw new Exception("Unsupported MapleScouter request.");
        await Ready();
        if (method == "SESSION" || method == "CONFIG") {
            var options = job["body"] as Dictionary<string, object>;
            object renew;
            if (options != null && options.TryGetValue("renew", out renew) && renew is bool && (bool)renew) {
                await web.CoreWebView2.ExecuteScriptAsync("localStorage.removeItem('sc_tok_exp')");
                await Ready(true);
            }
            if (method == "CONFIG") {
                var deadline = DateTime.UtcNow.AddSeconds(20);
                while (publicApiKey == null && DateTime.UtcNow < deadline) {
                    await Active(false);
                    await Task.Delay(100, stop.Token);
                }
                if (publicApiKey == null) throw new Exception("MapleScouter client configuration could not be loaded. Retry when the site is available.");
            }
            await Active(false);
            var cookies = new List<object>();
            foreach (string address in new[] { SiteOrigin, Api })
                foreach (var cookie in await web.CoreWebView2.CookieManager.GetCookiesAsync(address)) {
                    string domain = cookie.Domain.TrimStart('.');
                    if (domain == "maplescouter.com" || domain == "api.maplescouter.com")
                        cookies.Add(new { name = cookie.Name, value = cookie.Value, domain = cookie.Domain, path = cookie.Path });
                }
            var agent = json.Deserialize<string>(await web.CoreWebView2.ExecuteScriptAsync("navigator.userAgent"));
            string resultText = method == "CONFIG" ? json.Serialize(new { api_key = publicApiKey }) : "{}";
            await Local("session", new { user_agent = agent, cookies = cookies });
            CloseWindow();
            return new { status = 200, text = resultText };
        }
        var result = await Fetch(job);
        if (challenge || SessionExpired(result)) {
            // Only explicit verification failures can retry. Network errors and
            // ordinary API errors may have been processed and are never replayed.
            await web.CoreWebView2.ExecuteScriptAsync("localStorage.removeItem('sc_tok_exp')");
            await Ready(true);
            result = await Fetch(job);
        }
        if (challenge || SessionExpired(result)) throw new Exception("MapleScouter still requires verification. Retry or export your inputs to MapleScouter.");
        return result;
    }

    bool SessionExpired(Dictionary<string, object> result) {
        object code;
        if (!result.TryGetValue("status", out code) || Convert.ToInt32(code) != 401) return false;
        try {
            var body = json.Deserialize<Dictionary<string, object>>(Get(result, "text"));
            return Get(body, "humanToken") != null;
        } catch { return false; }
    }

    async Task<Dictionary<string, object>> Fetch(Dictionary<string, object> job) {
        await Active(verifying);
        activeUrl = Get(job, "url"); challenge = false;
        fetchNonce = Guid.NewGuid().ToString("N");
        response = new TaskCompletionSource<Dictionary<string, object>>();
        var headers = new Dictionary<string, object>();
        var supplied = job["headers"] as Dictionary<string, object>;
        if (supplied != null) foreach (var pair in supplied)
            if (new[] { "api-key", "content-type", "accept" }.ContainsLower(pair.Key)) headers[pair.Key] = pair.Value;
        var request = new { url = activeUrl, method = Get(job, "method"), headers = headers, body = job["body"], nonce = fetchNonce };
        string script = @"(async r=>{
            const c=new AbortController();globalThis.__hasconeRequest=c;
            const timer=setTimeout(()=>c.abort(),45000);
            try{
                const v=await fetch(r.url,{method:r.method,headers:r.headers,credentials:'include',redirect:'error',signal:c.signal,...(r.body===null?{}:{body:JSON.stringify(r.body)})});
                const text=await v.text();
                if(text.length>16000000)throw new Error('Response too large');
                window.chrome.webview.postMessage({nonce:r.nonce,status:v.status,text});
            }catch(e){window.chrome.webview.postMessage({nonce:r.nonce,error:'Could not reach MapleScouter from the verification session. Retry when the site is available.'});}
            finally{clearTimeout(timer);delete globalThis.__hasconeRequest;}
        })(" + json.Serialize(request) + ");";
        try {
            await web.CoreWebView2.ExecuteScriptAsync(script);
            var deadline = DateTime.UtcNow.AddSeconds(50);
            while (!response.Task.IsCompleted) {
                if (DateTime.UtcNow > deadline) throw new Exception("MapleScouter request timed out. Retry when the site is available.");
                await Task.WhenAny(response.Task, Task.Delay(750, stop.Token));
                await Active(verifying);
            }
            return await response.Task;
        } finally {
            response = null; activeUrl = null;
            abortFetch = AbortFetch();
        }
    }

    async Task AbortFetch() {
        if (!IsDisposed && web != null && !web.IsDisposed) {
            try { await web.CoreWebView2.ExecuteScriptAsync("globalThis.__hasconeRequest?.abort()"); } catch { }
        }
    }
}

internal static class ScouterHeaderNames {
    internal static bool ContainsLower(this string[] names, string value) {
        foreach (string name in names) if (String.Equals(name, value, StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }
}
