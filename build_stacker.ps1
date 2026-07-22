$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:NUITKA_CACHE_DIR = Join-Path $root ".nuitka-cache"

Set-Location $root

python -m nuitka main.py `
    --standalone `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --windows-icon-from-ico=stacker_ice.ico `
    --include-data-dir=assets=assets `
    --include-data-file=LICENSES.txt=LICENSES.txt `
    --include-data-file=stacker_fire.ico=stacker_fire.ico `
    --include-data-file=stacker_ice.ico=stacker_ice.ico `
    --nofollow-import-to=matplotlib,pandas,tkinter,customtkinter `
    --module-parameter=numba-disable-jit=no `
    --assume-yes-for-downloads `
    --output-dir=build-release `
    --output-filename=Stacker.exe
