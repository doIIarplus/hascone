using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Web.Script.Serialization;

internal static class UpdateChecks {
    static void Assert(bool value,string label){if(!value)throw new Exception(label);}
    public static int Main(string[] args){
        if(args[0]=="--apply-update")return Updates.Apply(args[1]);
        if(args[0]=="--data-dir"){File.WriteAllText(Path.Combine(args[1],"restarted"),"ok");return 0;}
        if(args[0]=="--parent"){
            string folder=args[1],job=Path.Combine(folder,"job.json");
            File.WriteAllText(job,new JavaScriptSerializer().Serialize(new{target=Assembly.GetExecutingAssembly().Location,download=Path.Combine(folder,"download.exe"),data=Path.Combine(folder,"data with spaces"),pid=Process.GetCurrentProcess().Id,hash=Updates.FileHash(Path.Combine(folder,"download.exe"))}));
            Process.Start(new ProcessStartInfo(Path.Combine(folder,"helper.exe"),"--apply-update "+Updates.Quote(job)){UseShellExecute=false,CreateNoWindow=true});
            for(int i=0;i<100;i++){if(File.Exists(job+".ready"))return 0;Thread.Sleep(100);}
            return 1;
        }
        string directory=args[1];Directory.CreateDirectory(directory);
        string digest=new string('a',64);
        var asset=new Dictionary<string,object>{{"name","Hascone-Portable-1.2.0.exe"},{"state","uploaded"},{"size",123},{"digest","sha256:"+digest},{"browser_download_url",Updates.Repository+"/releases/download/v1.2.0/Hascone-Portable-1.2.0.exe"}};
        var release=new Dictionary<string,object>{{"tag_name","v1.2.0"},{"body","Friendly patch notes <script>not HTML</script>"},{"draft",false},{"prerelease",false},{"assets",new[]{asset}}};
        var serializer=new JavaScriptSerializer();
        Assert(Updates.Parse(serializer.Serialize(release),"1.1.2").Notes==(string)release["body"],"notes retained");
        Assert(Updates.Parse(serializer.Serialize(release),"1.2.0")==null,"same version");
        Assert(Updates.Parse(serializer.Serialize(release),"1.10.0")==null,"numeric ordering");
        release["prerelease"]=true;Assert(Updates.Parse(serializer.Serialize(release),"1.1.2")==null,"prerelease ignored");release["prerelease"]=false;
        asset["digest"]="";Assert(Updates.Parse(serializer.Serialize(release),"1.1.2")==null,"missing digest ignored");asset["digest"]="sha256:"+digest;
        asset["browser_download_url"]="https://example.org/file.exe";Assert(Updates.Parse(serializer.Serialize(release),"1.1.2")==null,"wrong repository ignored");
        Assert(Updates.ParseVersion("v1.2.0-beta")==null,"nonstable tag ignored");
        Assert(Updates.Quote("C:\\")=="\"C:\\\\\"","root path quoting");
        string file=Path.Combine(directory,"checksum");File.WriteAllText(file,"original");
        var expected=new UpdateRelease{Size=new FileInfo(file).Length,Digest=Updates.FileHash(file)};Updates.Verify(file,expected);
        File.WriteAllText(file,"modified");bool rejected=false;try{Updates.Verify(file,expected);}catch(IOException){rejected=true;}Assert(rejected,"corrupt download rejected");
        string self=Assembly.GetExecutingAssembly().Location;
        foreach(string name in new[]{"parent.exe","helper.exe","download.exe"})File.Copy(self,Path.Combine(directory,name));
        using(var output=new FileStream(Path.Combine(directory,"download.exe"),FileMode.Append))output.WriteByte(42);
        string newHash=Updates.FileHash(Path.Combine(directory,"download.exe"));
        string data=Path.Combine(directory,"data with spaces");Directory.CreateDirectory(data);File.WriteAllText(Path.Combine(data,"profile.json"),"keep me");
        using(var parent=Process.Start(new ProcessStartInfo(Path.Combine(directory,"parent.exe"),"--parent "+Updates.Quote(directory)){UseShellExecute=false,CreateNoWindow=true})){
            Assert(parent.WaitForExit(15000)&&parent.ExitCode==0,"installer handshake");
        }
        for(int i=0;i<150&&!File.Exists(Path.Combine(data,"restarted"));i++)Thread.Sleep(100);
        Assert(File.Exists(Path.Combine(data,"restarted")),"updated app restarted");
        Assert(Updates.FileHash(Path.Combine(directory,"parent.exe"))==newHash,"new executable installed");
        Assert(File.ReadAllText(Path.Combine(data,"profile.json"))=="keep me","data preserved");
        Console.WriteLine("Updater checks passed: versions, patch notes, source validation, checksum, executable replacement, restart, and saved data.");return 0;
    }
}
