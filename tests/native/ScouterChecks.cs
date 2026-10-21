using System;
using System.IO;
using System.Text;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

class ScouterChecks {
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var owner = new Form { Opacity = 0, ShowInTaskbar = false };
        string folder = args[2], mode = args[3];
        ScouterBrowser browser = null;
        int windows = 0;
        int posts = 0;
        owner.Shown += (s,e) => {
            browser = new ScouterBrowser(owner,args[0],args[1],Path.Combine(folder,"profile"),core => {
                windows++;
                File.WriteAllText(Path.Combine(folder,"windows.txt"),windows.ToString());
                var window=browser.Window;
                File.WriteAllText(Path.Combine(folder,"shown.txt"),window.Visible&&window.ControlBox&&window.ShowInTaskbar?"controllable":"hidden");
                // Keep mock test windows from interrupting the desktop. These
                // settings are test-only, after checking production visibility.
                window.Opacity=0;window.ShowInTaskbar=false;
                window.Disposed += (sender,eventArgs) => File.WriteAllText(Path.Combine(folder,"closed.txt"),windows.ToString());
                File.WriteAllText(Path.Combine(folder,"initialized.txt"), core.IsMuted ? "muted" : "audible");
                core.NavigationCompleted += (sender,eventArgs) => {
                    if(eventArgs.IsSuccess)File.WriteAllText(Path.Combine(folder,"page-loaded.txt"),"loaded");
                };
                core.AddWebResourceRequestedFilter("*",CoreWebView2WebResourceContext.All);
                core.WebResourceRequested += (sender,request) => {
                    if(browser.Window==null||!browser.Window.Visible)File.WriteAllText(Path.Combine(folder,"hidden-work.txt"),"unexpected");
                    string body = "", type = "text/html"; int code = 200;
                    if(request.Request.Uri.EndsWith("/delayed.png")) {
                        // Hold an unrelated image until disposal. A verified
                        // session must close without waiting for the load event.
                        request.Response=core.Environment.CreateWebResourceResponse(new MemoryStream(new byte[0]),200,"Test","Content-Type: image/png\r\n");
                        var deferred=request.GetDeferral();
                        window.Disposed+=(a,b)=>{try{deferred.Complete();}catch{}};
                        return;
                    }
                    if(request.Request.Uri.StartsWith("https://api.maplescouter.com/")) {
                        if(request.Request.Method == "POST") {
                            posts++;File.WriteAllText(Path.Combine(folder,"posts.txt"),posts.ToString());
                            code = mode == "failure" ? 503 : mode == "invalid-input" ? 888 : 200;
                            body = "{\"calculatedData\":{\"score\":123}}";type="application/json";
                            if(mode=="session-loop" || (mode=="session-expired" && posts==1)) {
                                code=401;body="{\"humanToken\":\"expired\"}";
                            }
                        } else code = 204;
                    } else if(request.Request.Uri.EndsWith(".js")) {
                        File.AppendAllText(Path.Combine(folder,"script-requests.txt"),"script\n");
                        type="application/javascript";body="window.testConfig={\"api-key\":\"public-test-key\",\"api\":\"https://api.maplescouter.com\"};";
                    } else if(request.ResourceContext == CoreWebView2WebResourceContext.Document) {
                        body=mode=="valid"?"<title>Loading MapleScouter</title>":"<title>Just a moment</title><div id='challenge-stage'>Local mock verification</div>";
                        if(mode=="interactive") body="<title>MapleScouter</title><div role='dialog' aria-label='&#49324;&#46988; &#54869;&#51064;'>Local mock human check</div>";
                        if(mode=="slow-resource") body+="<img src='/delayed.png'>";
                        if(mode != "cancel" && mode != "close") body+="<script>const finish=()=>{document.title='Mock verified';document.querySelector('#challenge-stage,[role=dialog]')?.remove();localStorage.setItem('sc_tok_exp',String(Date.now()+600000));const s=document.createElement('script');s.src='/_next/static/chunks/8153-test.js';document.head.append(s);};if(Number(localStorage.getItem('sc_tok_exp'))>Date.now()+60000)finish();else setTimeout(finish,1600)</script>";
                    } else body="<script src='/_next/static/chunks/8153-test.js'></script>";
                    request.Response=core.Environment.CreateWebResourceResponse(new MemoryStream(Encoding.UTF8.GetBytes(body)),code,"Test","Content-Type: "+type+"\r\nAccess-Control-Allow-Origin: https://maplescouter.com\r\nAccess-Control-Allow-Credentials: true\r\nAccess-Control-Allow-Headers: api-key, content-type\r\nAccess-Control-Allow-Methods: POST, GET, OPTIONS\r\n");
                };
            });
            var timer=new Timer {Interval=100};
            timer.Tick += (sender,eventArgs) => {
                if(mode=="close" && browser.Window!=null && File.Exists(Path.Combine(folder,"initialized.txt")))browser.Window.Close();
                if(File.Exists(Path.Combine(folder,"stop"))) {timer.Stop();browser.Close();owner.Close();}
            };
            timer.Start();browser.Connect();
        };
        Application.Run(owner);
    }
}
