using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static class Program {
    internal static string[] Args;
    internal static string Data;
    internal static Stopwatch Clock = Stopwatch.StartNew();
    internal static readonly DateTime Started = DateTime.UtcNow;
    internal static Mutex Instance;
    internal static EventWaitHandle Activate;
    internal static bool Smoke;
    internal static string Option(string name) {
        for (int i=0;i<Args.Length-1;i++) if (Args[i]==name) return Args[i+1];
        return null;
    }
    internal static string Hash(string text) {
        using (var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-","").ToLowerInvariant();
    }
    internal static Stream Resource(string name) { return Assembly.GetExecutingAssembly().GetManifestResourceStream(name); }
    [STAThread]
    public static int Main(string[] args) {
        AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling",false);AppContext.SetSwitch("Switch.System.IO.BlockLongPaths",false);Args=args;Smoke=args.Contains("--smoke-test");
        AppDomain.CurrentDomain.AssemblyResolve += (s,e) => {
            var name=new AssemblyName(e.Name).Name+".dll";
            using(var stream=Resource(name)) {
                if(stream==null)return null;
                using(var buffer=new MemoryStream()){stream.CopyTo(buffer);return Assembly.Load(buffer.ToArray());}
            }
        };
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        if(Option("--apply-update")!=null)return Updates.Apply(Option("--apply-update"));
        try {
            string customData=Option("--data-dir");
            string folder=Path.GetDirectoryName(Application.ExecutablePath);
            Data=Path.GetFullPath(customData??Path.Combine(folder,"Hascone-data"));
            Directory.CreateDirectory(Data);
            string key=Hash(Data.ToUpperInvariant()).Substring(0,24);
            bool first;
            Instance=new Mutex(true,"Local\\Hascone.Native."+key,out first);
            Activate=new EventWaitHandle(false,EventResetMode.AutoReset,"Local\\Hascone.Activate."+key);
            if(!first){Activate.Set();return 0;}
            Run();
            Instance.ReleaseMutex();
            return Environment.ExitCode;
        } catch(Exception ex) {
            MessageBox.Show("Hascone could not start. Use a writable folder.\n\n"+ex.Message,"Hascone",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 1;
        } finally {if(Activate!=null)Activate.Dispose();if(Instance!=null)Instance.Dispose();}
    }
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    private static void Run(){Application.Run(new Launcher());}
}

internal sealed class Launcher : Form {
    Panel splash=new Panel(); Label title=new Label(); Label detail=new Label(); Label elapsed=new Label();
    ProgressBar progress=new ProgressBar(); Button retry=new Button();Button logs=new Button();Button install=new Button();
    WebView2 web;Process backend;ProcessJob processJob;CancellationTokenSource cancel=new CancellationTokenSource();
    string logPath;string root;string origin;bool running;bool missingWebView;bool cached;bool repair;
    long shownMs;long readyMs;bool failed;System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer();
    readonly object logLock=new object();
    UpdateRelease availableUpdate;string updateDownload;bool updateBusy;
    void UpdateState(string state,string message="",int percent=0){
        if(IsDisposed||cancel.IsCancellationRequested)return;
        if(InvokeRequired){BeginInvoke((Action)(()=>UpdateState(state,message,percent)));return;}
        web.CoreWebView2.PostWebMessageAsJson(new JavaScriptSerializer().Serialize(new{type="update",state=state,message=message,percent=percent,current=Updates.Current,version=availableUpdate==null?null:availableUpdate.Version,notes=availableUpdate==null?null:availableUpdate.Notes}));
    }
    async Task CheckUpdate(bool manual){
        if(updateBusy)return;
        if(updateDownload!=null){UpdateState("ready");return;}
        updateBusy=true;if(manual)UpdateState("checking");
        try{availableUpdate=await Task.Run(()=>Updates.Check(cancel.Token));UpdateState(availableUpdate==null?"current":"available");}
        catch(Exception ex){Log("UPDATE_CHECK "+ex.Message);if(manual)UpdateState("error","Could not check for updates. Check your connection and try again.");}
        finally{updateBusy=false;}
    }
    async Task DownloadUpdate(){
        if(updateBusy||availableUpdate==null||updateDownload!=null)return;updateBusy=true;UpdateState("downloading");
        try{updateDownload=await Task.Run(()=>Updates.Download(availableUpdate,Path.Combine(Program.Data,"updates"),p=>UpdateState("downloading","",p),cancel.Token));UpdateState("ready");}
        catch(Exception ex){Log("UPDATE_DOWNLOAD "+ex.Message);UpdateState("error","Download failed. "+ex.Message);}
        finally{updateBusy=false;}
    }
    async Task InstallUpdate(){
        if(updateBusy||updateDownload==null)return;updateBusy=true;UpdateState("installing");
        try{await Task.Run(()=>Updates.Verify(updateDownload,availableUpdate));await Updates.StartInstaller(updateDownload,Program.Data,cancel.Token);Close();}
        catch(Exception ex){Log("UPDATE_INSTALL "+ex.Message);UpdateState("ready","Could not restart to update. "+ex.Message);}
        finally{updateBusy=false;}
    }
    public Launcher(){
        Text="Hascone";Size=new Size(1440,1000);MinimumSize=new Size(900,650);StartPosition=FormStartPosition.CenterScreen;
        BackColor=Color.FromArgb(13,17,23);ForeColor=Color.FromArgb(230,237,243);Font=new Font("Segoe UI",11);
        try{Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);}catch{}
        splash.Dock=DockStyle.Fill;splash.Padding=new Padding(48);Controls.Add(splash);
        title.Text="Starting Hascone";title.Font=new Font("Segoe UI",27,FontStyle.Bold);title.AutoSize=true;title.Location=new Point(48,64);
        detail.Text="Getting ready...";detail.AutoSize=false;detail.Size=new Size(760,120);detail.Location=new Point(50,125);
        progress.Location=new Point(50,270);progress.Size=new Size(680,16);progress.Style=ProgressBarStyle.Marquee;
        elapsed.Location=new Point(50,305);elapsed.AutoSize=true;elapsed.ForeColor=Color.FromArgb(154,167,184);
        retry.Text="Try again";retry.Location=new Point(50,355);retry.Size=new Size(120,38);retry.Visible=false;
        logs.Text="Open logs";logs.Location=new Point(182,355);logs.Size=new Size(120,38);logs.Visible=false;
        install.Text="Get WebView2";install.Location=new Point(314,355);install.Size=new Size(160,38);install.Visible=false;
        foreach(Button b in new[]{retry,logs,install}){b.BackColor=Color.FromArgb(36,48,66);b.FlatStyle=FlatStyle.Flat;}
        splash.Controls.AddRange(new Control[]{title,detail,progress,elapsed,retry,logs,install});
        var menu=new MenuStrip{BackColor=Color.FromArgb(22,28,38),ForeColor=ForeColor};
        var file=new ToolStripMenuItem("File");file.DropDownItems.Add("Open data folder",null,(s,e)=>OpenFolder(Program.Data));
        file.DropDownItems.Add("Quit",null,(s,e)=>Close());menu.Items.Add(file);MainMenuStrip=menu;Controls.Add(menu);menu.Visible=false;
        logs.Click+=(s,e)=>OpenFolder(Path.GetDirectoryName(logPath));
        install.Click+=(s,e)=>OpenExternal("https://developer.microsoft.com/en-us/microsoft-edge/webview2/#download-section");
        retry.Click+=async(s,e)=>{repair=true;await Start();};
        timer.Interval=500;timer.Tick+=(s,e)=>elapsed.Text=String.Format("Elapsed: {0:0}s",Program.Clock.Elapsed.TotalSeconds);
        Shown+=async(s,e)=>{
            shownMs=Program.Clock.ElapsedMilliseconds;
            logPath=Path.Combine(Program.Data,"logs","native.log");Directory.CreateDirectory(Path.GetDirectoryName(logPath));
            if(File.Exists(logPath)&&new FileInfo(logPath).Length>2000000){File.Copy(logPath,logPath+".previous",true);File.Delete(logPath);}
            Log("WINDOW_VISIBLE "+shownMs+"ms");
            timer.Start();
            ThreadPool.QueueUserWorkItem(_=>{
                while(!cancel.IsCancellationRequested){if(Program.Activate.WaitOne(500)&&!IsDisposed)BeginInvoke((Action)(()=>{WindowState=FormWindowState.Normal;Show();Activate();}));}
            });
            await Start();
        };
        FormClosing+=(s,e)=>{cancel.Cancel();StopBackend();if(web!=null)web.Dispose();timer.Stop();};
    }
    void Log(string message){lock(logLock){if(logPath!=null)File.AppendAllText(logPath,DateTime.UtcNow.ToString("o")+" "+message+Environment.NewLine);}}
    void Status(string message,int percent=-1){
        if(IsDisposed||cancel.IsCancellationRequested)return;
        if(InvokeRequired){BeginInvoke((Action)(()=>Status(message,percent)));return;}
        detail.Text=message;progress.Style=percent<0?ProgressBarStyle.Marquee:ProgressBarStyle.Continuous;
        if(percent>=0)progress.Value=Math.Min(100,Math.Max(0,percent));
    }
    async Task Start(){
        if(running)return;running=true;failed=false;missingWebView=false;
        retry.Visible=logs.Visible=install.Visible=false;progress.Visible=true;title.Text="Starting Hascone";
        try {
            Status("Checking the Windows web display...");
            await Task.Delay(100);
            string loader=Path.Combine(Program.Data,"runtime","webview2");Directory.CreateDirectory(loader);
            using(var source=Program.Resource("WebView2Loader.dll")){
                string destination=Path.Combine(loader,"WebView2Loader.dll");
                if(source!=null&&(!File.Exists(destination)||new FileInfo(destination).Length!=source.Length))
                    using(var output=File.Create(destination))source.CopyTo(output);
            }
            CoreWebView2Environment.SetLoaderDllFolderPath(loader);
            try{CoreWebView2Environment.GetAvailableBrowserVersionString();}
            catch(Exception ex){missingWebView=true;throw new Exception("Microsoft WebView2 is missing. Install the WebView2 Runtime, then choose Try again. Your profiles are unchanged.",ex);}
            root=Program.Option("--backend-root");
            if(root==null)root=await Task.Run(()=>PrepareRuntime(cancel.Token));
            else root=Path.GetFullPath(root);
            cancel.Token.ThrowIfCancellationRequested();
            Status("Starting the scanner...");
            origin=await StartBackend(root);
            readyMs=Program.Clock.ElapsedMilliseconds;Log("BACKEND_READY "+readyMs+"ms");
            Status("Opening your character scanner...");
            var options=new CoreWebView2EnvironmentOptions();
            var environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(Program.Data,"webview2"),options);
            if(web!=null){Controls.Remove(web);web.Dispose();}
            web=new WebView2{Dock=DockStyle.Fill,Visible=false};Controls.Add(web);web.BringToFront();MainMenuStrip.BringToFront();
            await web.EnsureCoreWebView2Async(environment);
            web.CoreWebView2.Settings.IsStatusBarEnabled=false;
            web.CoreWebView2.Settings.AreHostObjectsAllowed=false;
            web.CoreWebView2.Settings.IsWebMessageEnabled=true;
            web.CoreWebView2.WebMessageReceived+=async(s,e)=>{
                Uri source;
                if(!Uri.TryCreate(e.Source,UriKind.Absolute,out source)||source.GetLeftPart(UriPartial.Authority)!=origin)return;
                string command;try{command=e.TryGetWebMessageAsString();}catch{return;}
                if(command=="open-data-folder")OpenFolder(Program.Data);
                else if(command=="check-updates")await CheckUpdate(true);
                else if(command=="download-update")await DownloadUpdate();
                else if(command=="install-update")await InstallUpdate();
                else if(command=="quit")BeginInvoke((Action)(()=>Close()));
            };
            web.CoreWebView2.NewWindowRequested+=(s,e)=>{e.Handled=true;OpenExternal(e.Uri);};
            web.CoreWebView2.NavigationStarting+=(s,e)=>{
                Uri uri;if(!Uri.TryCreate(e.Uri,UriKind.Absolute,out uri)||uri.GetLeftPart(UriPartial.Authority)!=origin){e.Cancel=true;OpenExternal(e.Uri);}
            };
            web.CoreWebView2.PermissionRequested+=(s,e)=>e.State=CoreWebView2PermissionState.Deny;
            var loaded=new TaskCompletionSource<bool>();
            web.CoreWebView2.NavigationCompleted+=(s,e)=>{if(e.IsSuccess)loaded.TrySetResult(true);else loaded.TrySetException(new Exception("Could not display the scanner: "+e.WebErrorStatus));};
            web.CoreWebView2.Navigate(origin);
            if(await Task.WhenAny(loaded.Task,Task.Delay(30000,cancel.Token))!=loaded.Task)throw new Exception("The scanner page took too long to load. Try again or open the logs.");
            await loaded.Task;
            timer.Stop();web.Visible=true;splash.Visible=false;
            Log("UI_READY "+Program.Clock.ElapsedMilliseconds+"ms");
            // Smoke tests close right away, so clean up before reporting; otherwise stay off the startup path.
            if(Program.Smoke)CleanUp();
            else new Thread(CleanUp){IsBackground=true,Priority=ThreadPriority.BelowNormal}.Start();
            if(!Program.Smoke)await CheckUpdate(false);
            if(Program.Smoke){
                string health=await web.CoreWebView2.ExecuteScriptAsync("fetch('/api/health').then(r=>r.json())");
                // ExecuteScriptAsync serializes a Promise rather than awaiting it; use XHR for the smoke assertion.
                health=await web.CoreWebView2.ExecuteScriptAsync("(()=>{const r=new XMLHttpRequest();r.open('GET','/api/health',false);r.send();return JSON.parse(r.responseText)})()");
                if(!health.Contains("hascone"))throw new Exception("Backend health check failed");
                var result=new Dictionary<string,object>{{"ok",true},{"window_ms",shownMs},{"backend_ms",readyMs},{"ui_ms",Program.Clock.ElapsedMilliseconds},{"cached",cached},{"data",Program.Data},{"root",root}};
                File.WriteAllText(Path.Combine(Program.Data,"native-smoke.json"),new JavaScriptSerializer().Serialize(result));
                Close();
            }
        } catch(OperationCanceledException){} catch(Exception ex){
            StopBackend();failed=true;Log(ex.ToString());
            if(!IsDisposed){splash.Visible=true;splash.BringToFront();MainMenuStrip.BringToFront();title.Text="Couldn't start Hascone";detail.Text=ex.Message;progress.Visible=false;retry.Visible=logs.Visible=true;install.Visible=missingWebView;}
            if(Program.Smoke){Environment.ExitCode=1;File.WriteAllText(Path.Combine(Program.Data,"native-smoke.json"),new JavaScriptSerializer().Serialize(new{ok=false,error=ex.Message,window_ms=shownMs}));Close();}
        } finally{running=false;}
    }
    string PrepareRuntime(CancellationToken token){
        string key;
        using(var input=Program.Resource("payload.id")){
            if(input==null)throw new Exception("The scanner runtime is missing from this executable. Download the complete portable build.");
            using(var reader=new StreamReader(input))key=reader.ReadToEnd().Trim();
        }
        if(key.Length!=64||key.Any(c=>!Uri.IsHexDigit(c)))throw new Exception("Invalid runtime package identifier");
        string parent=Path.Combine(Program.Data,"runtime");Directory.CreateDirectory(parent);
        string destination=Path.Combine(parent,key.Substring(0,16));
        if(!repair&&File.Exists(Path.Combine(destination,"ready"))&&File.ReadAllText(Path.Combine(destination,"ready"))==key&&File.Exists(Path.Combine(destination,"python","python.exe"))&&File.Exists(Path.Combine(destination,"app.py"))){cached=true;Log("RUNTIME_CACHE_HIT");return destination;}
        cached=false;repair=false;Log("RUNTIME_EXTRACT_BEGIN");Status("Preparing the app for first use. This is only needed after an update.",0);
        string partial=destination+".partial";
        DeleteRuntime(partial,parent);Directory.CreateDirectory(partial);
        using(var source=Program.Resource("backend.zip")){
            if(source==null)throw new Exception("The scanner package is incomplete");
            using(var archive=new ZipArchive(source,ZipArchiveMode.Read)){
                long total=archive.Entries.Sum(e=>e.Length),done=0;var clock=Stopwatch.StartNew();
                byte[] buffer=new byte[1024*1024];
                foreach(var entry in archive.Entries){
                    token.ThrowIfCancellationRequested();
                    string target=Path.GetFullPath(Path.Combine(partial,entry.FullName.Replace('/',Path.DirectorySeparatorChar)));
                    if(!target.StartsWith(Path.GetFullPath(partial)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid runtime archive path");
                    if(entry.Name.Length==0){Directory.CreateDirectory(target);continue;}
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    using(var input=entry.Open())using(var output=File.Create(target)){
                        int count;while((count=input.Read(buffer,0,buffer.Length))>0){token.ThrowIfCancellationRequested();output.Write(buffer,0,count);done+=count;
                            if(clock.ElapsedMilliseconds>150){Status("Preparing the app for first use. This is only needed after an update.",(int)(done*100/Math.Max(1,total)));clock.Restart();}}
                    }
                }
            }
        }
        token.ThrowIfCancellationRequested();File.WriteAllText(Path.Combine(partial,"ready"),key);
        DeleteRuntime(destination,parent);Directory.Move(partial,destination);Log("RUNTIME_EXTRACT_COMPLETE");return destination;
    }
    // Each build unpacks its own runtime and each update leaves its helper behind. Keep only what
    // this build uses. A helper that just installed this update may still be exiting, so retry briefly.
    void CleanUp(){
        try{
            if(Program.Option("--backend-root")==null&&root!=null){
                string parent=Path.GetDirectoryName(root),keep=Path.GetFileName(root);int removed=0;
                foreach(string folder in Directory.GetDirectories(parent)){
                    string name=Path.GetFileName(folder);
                    if(name.Equals(keep,StringComparison.OrdinalIgnoreCase)||name.Equals("webview2",StringComparison.OrdinalIgnoreCase))continue;
                    try{DeleteRuntime(folder,parent);removed++;}catch(Exception ex){Log("RUNTIME_CLEANUP "+name+": "+ex.Message);}
                }
                if(removed>0)Log("RUNTIME_CLEANUP removed "+removed);
            }
            string updates=Path.Combine(Program.Data,"updates");
            for(int attempt=0;!Updates.Clean(updates,Program.Started)&&attempt<5&&!Program.Smoke&&!cancel.IsCancellationRequested;attempt++)Thread.Sleep(5000);
        }catch(Exception ex){Log("CLEANUP "+ex.Message);}
    }
    static void DeleteRuntime(string target,string parent){
        string full=Path.GetFullPath(target);string allowed=Path.GetFullPath(parent)+Path.DirectorySeparatorChar;
        if(!full.StartsWith(allowed,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid runtime cache path");
        if(Directory.Exists(full)){
            if((File.GetAttributes(full)&FileAttributes.ReparsePoint)!=0)throw new Exception("Runtime cache cannot be a directory link");
            Directory.Delete(full,true);
        }
    }
    async Task<string> StartBackend(string directory){
        string python=Path.Combine(directory,"python","python.exe");
        if(!File.Exists(python))python=Path.Combine(directory,".venv","Scripts","python.exe");
        if(!File.Exists(python))throw new Exception("The scanner runtime is incomplete. Download the portable build again.");
        var ready=new TaskCompletionSource<string>();
        var info=new ProcessStartInfo(python,"-u \""+Path.Combine(directory,"app.py")+"\" --desktop"){
            WorkingDirectory=directory,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
        foreach(var pair in new Dictionary<string,string>{{"HASCONE_DATA_DIR",Program.Data},{"HASCONE_PORT","0"},{"PYTHONUTF8","1"},{"PYTHONNOUSERSITE","1"},{"PADDLE_PDX_CACHE_HOME",Path.Combine(Program.Data,"cache","paddlex")},{"HF_HOME",Path.Combine(Program.Data,"cache","huggingface")},{"MODELSCOPE_CACHE",Path.Combine(Program.Data,"cache","modelscope")}})info.EnvironmentVariables[pair.Key]=pair.Value;
        backend=new Process{StartInfo=info,EnableRaisingEvents=true};
        backend.OutputDataReceived+=(s,e)=>{if(e.Data==null)return;if(e.Data.StartsWith("HASCONE_READY ")){int port;if(Int32.TryParse(e.Data.Substring("HASCONE_READY ".Length),out port)&&port>0&&port<65536)ready.TrySetResult("http://127.0.0.1:"+port);}else if(!e.Data.StartsWith("INFO:"))Log(e.Data);};
        backend.ErrorDataReceived+=(s,e)=>{if(e.Data!=null&&!e.Data.StartsWith("INFO:"))Log(e.Data);};
        backend.Exited+=(s,e)=>{
            Log("BACKEND_EXIT " + ((Process)s).ExitCode);
            ready.TrySetException(new Exception("The scanner stopped unexpectedly. Open logs for details."));
            if(!cancel.IsCancellationRequested&&!running&&!failed&&!IsDisposed)BeginInvoke((Action)(()=>{failed=true;splash.Visible=true;splash.BringToFront();title.Text="Scanner stopped";detail.Text="The scanner stopped. Choose Try again to restart it.";retry.Visible=logs.Visible=true;progress.Visible=false;}));
        };
        backend.Start();processJob=new ProcessJob(backend);backend.BeginOutputReadLine();backend.BeginErrorReadLine();
        if(await Task.WhenAny(ready.Task,Task.Delay(60000,cancel.Token))!=ready.Task){cancel.Token.ThrowIfCancellationRequested();throw new Exception("The scanner took too long to start. Choose Try again or open logs.");}
        return await ready.Task;
    }
    void StopBackend(){if(processJob!=null){processJob.Dispose();processJob=null;}if(backend!=null){try{if(!backend.HasExited)backend.Kill();}catch{}backend=null;}}
    static void OpenFolder(string path){Process.Start(new ProcessStartInfo(path){UseShellExecute=true});}
    static void OpenExternal(string value){Uri uri;if(Uri.TryCreate(value,UriKind.Absolute,out uri)&&uri.Scheme=="https")Process.Start(new ProcessStartInfo(uri.AbsoluteUri){UseShellExecute=true});}
}

internal sealed class ProcessJob : IDisposable {
    IntPtr handle;
    [StructLayout(LayoutKind.Sequential)]struct Basic {public long a,b;public uint flags;public UIntPtr min,max;public uint count;public UIntPtr affinity;public uint priority,scheduling;}
    [StructLayout(LayoutKind.Sequential)]struct Io {public ulong a,b,c,d,e,f;}
    [StructLayout(LayoutKind.Sequential)]struct Extended {public Basic basic;public Io io;public UIntPtr a,b,c,d;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr CreateJobObject(IntPtr attr,string name);
    [DllImport("kernel32.dll")]static extern bool SetInformationJobObject(IntPtr job,int type,IntPtr value,uint size);
    [DllImport("kernel32.dll")]static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
    public ProcessJob(Process process){handle=CreateJobObject(IntPtr.Zero,null);var data=new Extended();data.basic.flags=0x2000;int size=Marshal.SizeOf(data);IntPtr pointer=Marshal.AllocHGlobal(size);
        try{Marshal.StructureToPtr(data,pointer,false);if(!SetInformationJobObject(handle,9,pointer,(uint)size)||!AssignProcessToJobObject(handle,process.Handle)){CloseHandle(handle);handle=IntPtr.Zero;}}finally{Marshal.FreeHGlobal(pointer);}}
    public void Dispose(){if(handle!=IntPtr.Zero){CloseHandle(handle);handle=IntPtr.Zero;}}
}
