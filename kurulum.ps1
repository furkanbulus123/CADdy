# CADdy kurulumu - depoyu FreeCAD'e baglar.
#
# Yonetici GEREKMEZ: /J ile acilan junction yukseltilmis yetki istemiyor
# (olculdu). /D ile acilan symbolic link isterdi, o yuzden junction.
#
# Kopyalamiyoruz, BAGLIYORUZ. Tek kaynak var: bu klasor. "git pull"
# yaptiginda FreeCAD bir sonraki acilista yeni surumu yukler.
#
#     .\kurulum.ps1                 # otomatik bul
#     .\kurulum.ps1 -FreeCadDizini "D:\FreeCAD 1.1"
#     .\kurulum.ps1 -Zorla          # var olan baglantiyi degistir
#
# DIKKAT: bu dosya SAF ASCII kalmali. Windows PowerShell 5.1 BOM'suz bir
# .ps1'i ANSI kod sayfasiyla okuyor; Turkce harf ya da uzun tire koyarsan
# betik ayrisma hatasi veriyor (carpildi).

[CmdletBinding()]
param(
    [string] $FreeCadDizini = "",
    [switch] $Zorla
)

$ErrorActionPreference = "Stop"
$kaynak = $PSScriptRoot
$script:sorun = 0

function Tamam($m)  { Write-Host "  [+] $m" -ForegroundColor Green }
function Uyari($m)  { Write-Host "  [!] $m" -ForegroundColor Yellow }
function Kotu($m)   { Write-Host "  [x] $m" -ForegroundColor Red
                      $script:sorun = $script:sorun + 1 }
function Baslik($m) { Write-Host ""; Write-Host $m -ForegroundColor Cyan }

Write-Host ""
Write-Host "CADdy kurulumu" -ForegroundColor White
Write-Host "kaynak: $kaynak"

# --- 1. Bu klasor gercekten CADdy mi ------------------------------------
Baslik "1) Depo"
if ((Test-Path (Join-Path $kaynak "InitGui.py")) -and
    (Test-Path (Join-Path $kaynak "caddy\conversation.py"))) {
    Tamam "depo dosyalari yerinde"
} else {
    Kotu "bu klasor CADdy deposu degil (InitGui.py / caddy\ yok)"
    Write-Host ""
    exit 1
}

# --- 2. FreeCAD ---------------------------------------------------------
Baslik "2) FreeCAD 1.1"
$adaylar = @()
if ($FreeCadDizini) { $adaylar += $FreeCadDizini }
$adaylar += "$env:ProgramFiles\FreeCAD 1.1"
$adaylar += "${env:ProgramFiles(x86)}\FreeCAD 1.1"
$adaylar += "$env:LOCALAPPDATA\Programs\FreeCAD 1.1"

$fc = $null
foreach ($a in $adaylar) {
    if ($a -and (Test-Path (Join-Path $a "bin\freecadcmd.exe"))) { $fc = $a; break }
}
if ($fc) {
    Tamam "bulundu: $fc"
    # Surumu FreeCAD'in kendisine soruyoruz: exe'nin dosya bilgisi bos geliyor.
    $betik = "import FreeCAD; print('.'.join(FreeCAD.Version()[0:3]))"
    try {
        $v = & (Join-Path $fc "bin\freecadcmd.exe") -c $betik | Select-Object -Last 1
    } catch {
        $v = $null
    }
    if ($v -and $v -match "^1\.1") {
        Tamam "surum $v"
    } elseif ($v) {
        Uyari "surum $v - CADdy 1.1.x icin yazildi"
    } else {
        Uyari "surum sorulamadi (kurulum yine de devam ediyor)"
    }
} else {
    Kotu "FreeCAD 1.1 bulunamadi"
    Write-Host "      https://www.freecad.org/downloads.php adresinden kur, ya da:"
    Write-Host '      .\kurulum.ps1 -FreeCadDizini "D:\FreeCAD 1.1"'
}

# --- 3. Claude Code CLI -------------------------------------------------
Baslik "3) Claude Code CLI"
$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($claude) {
    Tamam "komut bulundu: $($claude.Source)"
    try {
        $cv = & claude --version | Select-Object -First 1
    } catch {
        $cv = $null
    }
    if ($cv) { Tamam "surum $cv" } else { Uyari "claude --version cevap vermedi" }
} else {
    Kotu "claude komutu PATH'te yok"
    Write-Host "      npm install -g @anthropic-ai/claude-code"
    Write-Host "      sonra:  claude     (tarayicida aboneligle giris yap)"
}

# --- 4. Abonelik mi, kredi mi -------------------------------------------
Baslik "4) Abonelik mi, kredi mi"
if ($env:ANTHROPIC_API_KEY) {
    Uyari "ANTHROPIC_API_KEY TANIMLI - CLI aboneligi birakip KREDI harcar."
    Write-Host '      Kalicisini sil:'
    Write-Host '      [Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY",$null,"User")'
} else {
    Tamam "ANTHROPIC_API_KEY tanimli degil - abonelikle calisilacak"
}

# --- 5. Junction --------------------------------------------------------
Baslik "5) FreeCAD'e bagla"
$mod  = Join-Path $env:APPDATA "FreeCAD\v1-1\Mod"
$link = Join-Path $mod "CADdy"

if (-not (Test-Path $mod)) {
    New-Item -ItemType Directory -Force -Path $mod | Out-Null
    Tamam "Mod dizini olusturuldu: $mod"
}

function Junction-Ac($link, $kaynak) {
    cmd /c mklink /J "$link" "$kaynak" | Out-Null
    if (Test-Path $link) { Tamam "baglandi: $link -> $kaynak"; return $true }
    Kotu "junction kurulamadi: $link"
    return $false
}

function Baglantiyi-Kur($link, $hedefDizin, $ad) {
    $mevcut = Get-Item $link -ErrorAction SilentlyContinue
    if ($null -eq $mevcut) {
        Junction-Ac $link $hedefDizin | Out-Null
        return
    }
    $baglanti = [bool] $mevcut.LinkType
    $hedef = $null
    if ($baglanti) { $hedef = ($mevcut.Target | Select-Object -First 1) }

    if ($hedef -and ($hedef.TrimEnd('\') -ieq $hedefDizin.TrimEnd('\'))) {
        Tamam "$ad baglantisi zaten dogru yere bakiyor"
    } elseif (-not $baglanti) {
        # Gercek klasoru ASLA silmiyoruz: icinde kullanicinin isi olabilir.
        Kotu "orada gercek bir klasor duruyor: $link"
        Write-Host "      once onu tasi ya da sil, sonra bu betigi tekrar calistir"
    } elseif ($Zorla) {
        cmd /c rmdir "$link" | Out-Null
        Junction-Ac $link $hedefDizin | Out-Null
    } else {
        Uyari "$ad baglantisi var ama baska yere bakiyor: $hedef"
        Write-Host "      degistirmek icin:  .\kurulum.ps1 -Zorla"
    }
}

Baglantiyi-Kur $link $kaynak "CADdy"


# --- Sonuc --------------------------------------------------------------
Write-Host ""
if ($script:sorun -eq 0) {
    Write-Host "Kurulum tamam." -ForegroundColor Green
    Write-Host "FreeCAD'i baslat; workbench listesinde CADdy gorunecek."
    if ($fc) {
        Write-Host ""
        Write-Host "Dogrulamak istersen:"
        Write-Host "  & '$fc\bin\freecadcmd.exe' '$kaynak\tests\test_yukleme_fc.py'"
    }
    Write-Host ""
} else {
    Write-Host "$script:sorun sorun kaldi - yukaridaki [x] satirlarini coz." -ForegroundColor Red
    Write-Host ""
    exit 1
}
