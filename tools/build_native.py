"""Compile the Windows WebView2 launcher; optionally embed the portable backend."""
import argparse
import hashlib
import json
import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK_VERSION = '1.0.4191.47'
VERSION = '1.1.4'

def _ensure_webview2_sdk(cache):
    sdk = cache/'webview2-sdk'/'sdk'
    if not (sdk/'lib/net462/Microsoft.Web.WebView2.Core.dll').exists():
        url = f'https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{SDK_VERSION}/microsoft.web.webview2.{SDK_VERSION}.nupkg'
        archive = cache/'webview2-sdk.zip'
        urllib.request.urlretrieve(url, archive)
        sdk.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            z.extractall(sdk)
    return sdk


def _compress_backend(cache):
    backend = cache/'backend'
    if not (backend/'python/python.exe').exists():
        raise RuntimeError('Prepare the backend first')
    archive = cache/'native-backend.zip'
    print('Compressing the scanner runtime (without Chromium)...', flush=True)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for p in sorted(backend.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
                z.write(p, p.relative_to(backend).as_posix())
    digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    payload_id = cache/'native-payload.id'
    payload_id.write_text(digest, encoding='ascii')
    print(f'Runtime archive: {archive.stat().st_size/1024**2:.1f} MiB', flush=True)
    return [f'/resource:{archive},backend.zip', f'/resource:{payload_id},payload.id'], digest


def _compile_command(csc, output, sdk, cache, files):
    assembly = cache/'native-version.cs'
    assembly.write_text('using System.Reflection;\n[assembly:AssemblyTitle("Hascone")]\n[assembly:AssemblyProduct("Hascone")]\n[assembly:AssemblyVersion("'+VERSION+'.0")]\n')
    cmd = [str(csc), '/nologo', '/target:winexe', '/platform:x64', '/optimize+', f'/out:{output}', f'/win32manifest:{ROOT / "native/app.manifest"}']
    for reference in ['System', 'System.Core', 'System.Drawing', 'System.Windows.Forms', 'System.IO.Compression', 'System.Web.Extensions']:
        cmd.append('/reference:'+reference+'.dll')
    for name in ['Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll']:
        path = sdk/'lib/net462'/name
        cmd += [f'/reference:{path}', f'/resource:{path},{name}']
    loader = sdk/'runtimes/win-x64/native/WebView2Loader.dll'
    cmd += [f'/resource:{loader},WebView2Loader.dll']+files
    icon = ROOT/'native/icon.ico'
    if icon.exists():
        cmd.append(f'/win32icon:{icon}')
    cmd += [str(ROOT/'native/Launcher.cs'), str(ROOT/'native/Updates.cs'), str(assembly)]
    return cmd


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dev',action='store_true')
    parser.add_argument('--reuse-backend',action='store_true')
    args=parser.parse_args()
    cache=ROOT/'.build'
    cache.mkdir(exist_ok=True)
    sdk = _ensure_webview2_sdk(cache)
    if not args.dev and not args.reuse_backend:
        import sys
        subprocess.run([sys.executable,str(ROOT/'tools/prepare_bundle.py')],check=True,cwd=ROOT)
    output=cache/'native-dev'/'Hascone.exe' if args.dev else ROOT/'dist'/f'Hascone-Portable-{VERSION}.exe'
    output.parent.mkdir(parents=True,exist_ok=True)
    files, digest = ([], None) if args.dev else _compress_backend(cache)
    csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not csc.exists():
        raise RuntimeError('The Windows .NET Framework compiler was not found')
    cmd = _compile_command(csc, output, sdk, cache, files)
    subprocess.run(cmd,check=True,cwd=ROOT)
    print(f'Built {output} ({output.stat().st_size/1024**2:.1f} MiB)',flush=True)
    if not args.dev:
        (ROOT/'dist'/f'Hascone-Portable-{VERSION}.build.json').write_text(json.dumps({'version':VERSION,'shell':'Windows WebView2','sdk':SDK_VERSION,'payload_sha256':digest,'bytes':output.stat().st_size},indent=2))

if __name__=='__main__':
    main()

