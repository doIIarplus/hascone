using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal sealed class UpdateRelease {
    internal string Version, Notes, Url, Digest;
    internal long Size;
}

internal static class Updates {
    internal const string Repository = "https://github.com/doIIarplus/hascone";
    internal static string Current { get { return Assembly.GetExecutingAssembly().GetName().Version.ToString(3); } }
    internal static string Text(IDictionary<string,object> obj,string key) { object value;return obj.TryGetValue(key,out value)?Convert.ToString(value):""; }
    internal static Version ParseVersion(string value) {
        Version version;
        return System.Text.RegularExpressions.Regex.IsMatch(value??"",@"^v?\d+\.\d+\.\d+$")&&Version.TryParse(value.TrimStart('v'),out version)?version:null;
    }
    internal static UpdateRelease Parse(string json,string current) {
        var data=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json);
        if(Text(data,"draft")=="True"||Text(data,"prerelease")=="True")return null;
        string tag=Text(data,"tag_name");var version=ParseVersion(tag);
        if(version==null||version<=ParseVersion(current))return null;
        object assets;if(!data.TryGetValue("assets",out assets)||!(assets is IEnumerable))return null;
        string name="Hascone-Portable-"+version+".exe";
        foreach(var entry in (IEnumerable)assets){
            var asset=entry as IDictionary<string,object>;if(asset==null||Text(asset,"name")!=name||Text(asset,"state")!="uploaded")continue;
            string url=Text(asset,"browser_download_url"),digest=Text(asset,"digest");long size;
            if(url!=Repository+"/releases/download/"+tag+"/"+name||!System.Text.RegularExpressions.Regex.IsMatch(digest,@"^sha256:[a-fA-F0-9]{64}$")||!Int64.TryParse(Text(asset,"size"),out size)||size<=0)continue;
            return new UpdateRelease{Version=version.ToString(),Notes=Text(data,"body"),Url=url,Digest=digest.Substring(7).ToLowerInvariant(),Size=size};
        }
        return null;
    }
    internal static HttpWebRequest Request(string url) {
        ServicePointManager.SecurityProtocol|=SecurityProtocolType.Tls12;
        var request=(HttpWebRequest)WebRequest.Create(url);
        request.UserAgent="Hascone/"+Current;request.Accept="application/vnd.github+json";
        request.Timeout=30000;request.ReadWriteTimeout=30000;
        return request;
    }
    internal static UpdateRelease Check(CancellationToken token) {
        var request=Request("https://api.github.com/repos/doIIarplus/hascone/releases/latest");
        using(token.Register(request.Abort)){
            try{using(var response=request.GetResponse())using(var reader=new StreamReader(response.GetResponseStream()))return Parse(reader.ReadToEnd(),Current);}
            catch(WebException ex){var response=ex.Response as HttpWebResponse;if(response!=null&&response.StatusCode==HttpStatusCode.NotFound){response.Dispose();return null;}throw;}
        }
    }
    internal static string FileHash(string path) {using(var sha=SHA256.Create())using(var input=File.OpenRead(path))return BitConverter.ToString(sha.ComputeHash(input)).Replace("-","").ToLowerInvariant();}
    internal static void Verify(string path,UpdateRelease release) {
        if(new FileInfo(path).Length!=release.Size||FileHash(path)!=release.Digest)throw new IOException("The update download did not pass verification. Please try again.");
    }
    internal static string Download(UpdateRelease release,string directory,Action<int> progress,CancellationToken token) {
        Directory.CreateDirectory(directory);string path=Path.Combine(directory,"download-"+Guid.NewGuid().ToString("N")+".exe");
        var request=Request(release.Url);request.Accept="application/octet-stream";
        try{
            using(token.Register(request.Abort))using(var response=request.GetResponse())using(var input=response.GetResponseStream())using(var output=File.Create(path)){
                if(response.ResponseUri.Scheme!="https")throw new IOException("The update download requires HTTPS.");
                byte[] buffer=new byte[1024*128];long total=0;int count,last=-1;
                while((count=input.Read(buffer,0,buffer.Length))>0){token.ThrowIfCancellationRequested();total+=count;if(total>release.Size)throw new IOException("Unexpected update size.");output.Write(buffer,0,count);int percent=(int)(total*100/release.Size);if(percent!=last){last=percent;progress(percent);}}
            }
            token.ThrowIfCancellationRequested();Verify(path,release);return path;
        }catch{if(File.Exists(path))File.Delete(path);throw;}
    }
    internal static string Quote(string value) {
        if(value.Contains("\""))throw new ArgumentException("Invalid path.");
        return "\""+value+new string('\\',value.Reverse().TakeWhile(c=>c=='\\').Count())+"\"";
    }
    internal static async Task StartInstaller(string download,string data,CancellationToken token) {
        string target=Application.ExecutablePath;
        // Probe the destination before closing the running app.
        string probe=target+"."+Guid.NewGuid().ToString("N")+".probe";
        using(File.Create(probe)){}File.Delete(probe);
        string helper=Path.Combine(Path.GetDirectoryName(download),"helper-"+Guid.NewGuid().ToString("N")+".exe");
        File.Copy(target,helper);
        string job=helper+".json";
        File.WriteAllText(job,new JavaScriptSerializer().Serialize(new{target=target,download=download,data=data,pid=Process.GetCurrentProcess().Id,hash=FileHash(download)}));
        Process.Start(new ProcessStartInfo(helper,"--apply-update "+Quote(job)){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden});
        for(int i=0;i<100;i++){token.ThrowIfCancellationRequested();if(File.Exists(job+".ready"))return;await Task.Delay(100,token);}
        throw new IOException("The update helper could not start. Your current app is still running.");
    }
    internal static int Apply(string job) {
        string target=null,backup=null,stage=null;bool replaced=false;
        try{
            var data=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(job));
            target=Path.GetFullPath(Text(data,"target"));string download=Path.GetFullPath(Text(data,"download"));
            string folder=Path.GetDirectoryName(Application.ExecutablePath);
            if(Path.GetDirectoryName(Path.GetFullPath(job))!=folder||Path.GetDirectoryName(download)!=folder||target==download||!target.EndsWith(".exe",StringComparison.OrdinalIgnoreCase)||FileHash(download)!=Text(data,"hash"))throw new IOException("Invalid update package.");
            using(var parent=Process.GetProcessById(Convert.ToInt32(data["pid"]))){
                if(!String.Equals(parent.MainModule.FileName,target,StringComparison.OrdinalIgnoreCase))throw new IOException("Update target does not match the running app.");
                File.WriteAllText(job+".ready","ready");
                if(!parent.WaitForExit(60000))return 1;
            }
            stage=target+"."+Guid.NewGuid().ToString("N")+".new";backup=target+"."+Guid.NewGuid().ToString("N")+".bak";
            File.Copy(download,stage);
            if(FileHash(stage)!=Text(data,"hash"))throw new IOException("The update package changed. Please download it again.");
            for(int i=0;;i++){try{File.Replace(stage,target,backup);replaced=true;break;}catch(IOException){if(i>=29)throw;Thread.Sleep(1000);}}
            try{Process.Start(new ProcessStartInfo(target,"--data-dir "+Quote(Text(data,"data"))){UseShellExecute=false,WorkingDirectory=Path.GetDirectoryName(target)});}
            catch{File.Replace(backup,target,null);replaced=false;throw;}
            try{File.Delete(backup);File.Delete(download);File.Delete(job+".ready");File.Delete(job);}catch{}
            return 0;
        }catch(Exception ex){
            if(stage!=null&&File.Exists(stage))try{File.Delete(stage);}catch{}
            MessageBox.Show("The update could not finish. "+(replaced?"Your previous executable is saved at "+backup:"Your existing app has been kept. You can open it again.")+"\n\n"+ex.Message,"Hascone update",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;
        }
    }
}
