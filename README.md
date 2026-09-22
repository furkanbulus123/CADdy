# CADdy — FreeCAD içinde AI yardımcısı

FreeCAD 1.1'e yerleşik bir **AI sohbet paneli** ekleyen saf Python eklentisi.

İnsan elle çizer → AI'a sorar → AI devam eder → insan yine devam eder.
Sıra kimde olursa olsun **tek bir canlı FreeCAD belgesi** üzerinde çalışılır;
elle yapılan iş kaybolmaz, AI'ın ürettiği de parametrik kalır ve elle
düzenlenebilir.

```
FreeCAD 1.1 (Python 3.11 + PySide6)
   │
   ├─ CADdy paneli  ──QProcess──>  claude.exe -p --output-format stream-json
   │                                  (mevcut Claude Code aboneliği;
   │                                   API anahtarı YOK, ek ücret YOK)
   │
   └─ üretilen FreeCAD Python'u  ──>  App.setActiveTransaction(..., persist=True)
                                        exec()  ->  doc.recompute()
                                      App.closeActiveTransaction()
                                        \_ tek temiz Ctrl+Z
```

---

## Gereksinimler

| | | bu makinede ölçülen |
|---|---|---|
| Windows | 10 / 11 | 10 Pro 19045 |
| FreeCAD | **1.1.x** | 1.1.1 (build 20260414), Python 3.11.14 |
| Node.js | Claude Code CLI için | — |
| Claude Code CLI | `claude` komutu | npm global kurulumu |
| Claude aboneliği | Pro / Max | OAuth ile giriş |

FreeCAD 1.0 ve öncesi **çalışmaz** — panel PySide6 kullanıyor, 1.0 PySide2 ile
geliyor.

---

## Yeni bir bilgisayarda kurulum

### 1. FreeCAD 1.1

<https://www.freecad.org/downloads.php> → Windows 64-bit installer.
Varsayılan yere kur (`C:\Program Files\FreeCAD 1.1`). Başka bir yere kurarsan
kurulum betiği sorar.

### 2. Claude Code CLI

```powershell
npm install -g @anthropic-ai/claude-code
claude          # açılan tarayıcıda aboneliğinle giriş yap
claude --version
```

> **`ANTHROPIC_API_KEY` ortam değişkenini TANIMLAMA.** CLI o değişkeni
> görürse aboneliği bırakıp krediyle çalışır — yani para harcarsın. CADdy o
> değişkeni asla kendisi yazmaz; makinede varsa sil. (Ayrıntı: `MANTIK.md` §9.)

### 3. Depoyu klonla

```powershell
git clone https://github.com/furkanbulus123/CADdy.git C:\Kaynak\CADdy
```

Yer serbest — Masaüstü de olur. Klasörü sonradan taşırsan 4. adımı tekrarla.

### 4. FreeCAD'e bağla

Depo klasöründe, normal bir PowerShell'de (**yönetici gerekmez** — junction
açmak yükseltilmiş yetki istemiyor, ölçüldü):

```powershell
.\kurulum.ps1
```

Betik şunları yapar ve her birini ekrana yazar: FreeCAD 1.1'i bulur, `claude`
komutunu doğrular, `%APPDATA%\FreeCAD\v1-1\Mod\` altına **iki junction** açar
— `CADdy` ve `Monkey`. Junction = kopya değil bağlantı; depoyu `git pull` ile
güncellersen FreeCAD anında yeni sürümü yükler.

Elle yapmak istersen iki satır bu:

```powershell
cmd /c mklink /J "%APPDATA%\FreeCAD\v1-1\Mod\CADdy"  "C:\Kaynak\CADdy"
cmd /c mklink /J "%APPDATA%\FreeCAD\v1-1\Mod\Monkey" "C:\Kaynak\CADdy\Monkey"
```

**Monkey ayrı bir eklenti.** Depoda CADdy'nin içinde duruyor ama FreeCAD onu
alt klasör olarak yüklemez, kendi junction'ı şart. Kurulum betiği bunu
kendiliğinden yapıyor.

### 5. FreeCAD'i başlat

Workbench listesinde **CADdy** görünür; üzerine geçince panel kendiliğinden
açılır. Üst menü çubuğunda da kalıcı bir CADdy girişi olur.

### Kurulumu doğrula

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" tests\test_yukleme_fc.py
```

`0 basarisiz` görmen lazım. Tamamı için aşağıdaki **Testler** bölümüne bak.

---

## FreeCAD neden bu depoda yok

İstenen buydu ama teknik olarak mümkün değil, sebebi ölçüldü:

* Kurulu FreeCAD 1.1 = **2,05 GB / 30 378 dosya**.
* İçindeki `libclang-13.dll` tek başına **114,1 MB**.

GitHub 100 MB'ı aşan tek bir dosyayı bile kabul etmiyor (Git LFS'siz `push`
doğrudan reddediliyor), 2 GB'lık bir depo da klonlanabilir olmaktan çıkıyor.
Üstelik kurulu FreeCAD makineye kayıtlar yazıyor — kopyalanan klasör başka
bilgisayarda güvenilir çalışmıyor.

Onun yerine yukarıdaki **4 adım + `kurulum.ps1`** var: resmi installer'ı
indirmek dışında elle iş kalmıyor.

---

## Panelde ne görüyorsun

Üst şerit: `Yeni · Geri al · İleri al ─── [Opus ▾] [Hızlı ▾]`

* **Yeni** — bağlamı unutur, sıfırdan başlar.
* **Geri al** — son AI değişikliğini geri alır (tek adım, kaç nesne üretmiş
  olursa olsun).
* **İleri al** — geri aldığını tekrar uygular. **Geri al'a basmadan önce
  kapalıdır.** Üzerine yeni bir işlem yaparsan ileri geçmişi silinir ve panel
  bunu söyler (sessizce kaybolmaz).
* **Model seçici** — Opus / Sonnet. Ölçülen (2026-08-24, aynı iş): Opus tur
  başına 87,5 sn ve Sonnet'ten **%35 daha ucuz**, çünkü daha az turda
  bitiriyor. Sonnet 49,1 sn ama aynı işte kullanıcıdan onay alamadı.
* **Efor seçici** — `Hızlı` / `Derin`. Düşünme miktarını ayarlar; asıl
  gecikme kaynağı bu (aşağıda).
* **Sağ tık** → sohbet kayıtlarının klasörünü açar: `LOG/<tarih>_<oturum>.txt`,
  **bir sohbet = bir dosya**, her mesajdan sonra anında yazılır.

Alt bilgi satırı: `5.7 sn · claude-opus-5 · 6.4k token · 1 kod bloğu`.
Üzerine gelince token dökümü çıkar. **Dolar yazmaz** — abonelikle
çalışıldığı için tahsilat yok.

Canlı yanıt akarken üstteki etiket hangi aşamada olduğunu söyler:
`düşünüyor · 47 sn · ~3.6k düşünce`. Bu sayılar sürekli artar; takılan bir
panelde dururlar, ayırt edebilesin diye böyle.

---

## Nasıl çalışıyor — önce ölç, sonra yap

Büyük bir şey istediğinde tek hamlede yapmaya kalkmaz.

**İlk turda üç ayrı kanıt toplar** ve inşaya başlamadan önce parçanın *ne
olduğunu* söyler:

1. `kesif()` — ağaç, ölçüler, sınırlar.
2. İşe özel en az iki ölçüm — ör. birkaç yükseklikte kesit konturu:
   `kesit_konturu(nesne, [5, 20, 35])`.
3. **Üç açıdan 3B görüntü** — aynı turda `GORSEL-KONTROL 3` ile ister.

Bu üçüncüsü bedava değil ama ölçüldü ki vazgeçilmez: 124,6 saniyelik sayısal
ölçüm bir tavşan modelinde kulak arasını "karın" sandı, ikinci sayısal geçişte
de aynı hatayı yaptı; tek bir kare 4,9 saniyede çözdü. **Sayılarla resim
çelişirse resim kazanır** ve ölçüm yenilenir.

Sonra: *"Bunu 3 adıma bölüyorum; şimdi 1. adımı yapıyorum."* Planı kısaca
yazar, **yalnızca 1. adımın** kodunu verir, her adım sonunda 3B'de ne görmen
gerektiğini söyler. Bir adım = bakıp yargılayabileceğin tek görünür
değişiklik.

Ölçüldü (kupaya kedi kafası logosu): soru turu **28 sn**, 1. adım **55 sn**.
Tek hamlede aynı iş 77–183 sn sürüyordu.

---

## Yanıt neden bazen dakikalarca sürüyor

Takılmıyor — model düşünüyor. İki gerçek oturumun 22 turu ölçüldü:

* Çıktı hızı **sabit**: Sonnet 78,5 · Opus 72,5 token/sn.
* Bağlam gecikmeyi **belirlemiyor**: 93k bağlam + 92 çıktı = 3,9 sn;
  15k bağlam + 2486 çıktı = 36,8 sn. Prompt cache çalışıyor.
* Çıktı token'ının **%91–94'ü düşünme**.

Yani `gecikme ≈ çıktı / 75` ve o çıktının onda dokuzu düşünme. Efor seçici tam
bunu ayarlıyor — aynı istem, 3 tekrar (Sonnet):

| efor | süreler | ortanca | çıktı token |
|---|---|---:|---:|
| **Hızlı** (`low`) | 37 · 43 · 37 sn | **37,0 sn** | 2 774 |
| **Derin** (varsayılan) | 109 · 126 · 116 sn | 116,1 sn | 9 820 |

Opus'ta da geçerli: 87,0 sn → 44,4 sn.

**Varsayılan `Derin` bırakıldı.** Hız kazancı ölçüldü, **kalite kaybı
ölçülmedi**; ölçülmemiş bir şeye dayanarak varsayılan değiştirilmiyor.
(`high` seviyesi denendi ve elendi: varsayılandan *daha yavaş* çıktı —
129,6 sn.)

---

## Güvenlik modeli

* **AI'ın kendi dosya erişimi yok** — CLI `--tools ""` ile başlatılır.
  Diske dokunan tek şey, senin panelde **Çalıştır**'a bastığın koddur.
* Her çalıştırma tek bir FreeCAD transaction'ı içinde koşar; hata olursa
  transaction iptal edilir, yarım nesne belgede kalmaz.
* Kod çalışmadan önce statik denetimden geçer (`caddy/execution/` içindeki
  koruma katmanı); tehlikeli çağrılar engellenir ve sebebi panelde yazar.
* Sohbet kayıtları (`LOG/`) **depoya girmez** — `.gitignore`'da.

Ayrıntı ve elenen alternatifler: `MANTIK.md` §6.

---

## Testler

Testler FreeCAD'in kendi yorumlayıcısıyla koşar, `pytest` yok. Her dosya
bağımsız çalışır ve `0 basarisiz` ile çıkar:

```powershell
$fc = "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"
foreach ($t in Get-ChildItem tests\test_*_fc.py) { & $fc $t.FullName }
```

Bir istisna: `test_initgui_kapsam.py` FreeCAD'in **python.exe**'siyle koşar
(GUI olmadan InitGui'yi denetler):

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\python.exe" tests\test_initgui_kapsam.py
```

Toplam **678 kontrol**. Bir test yazarken kural: *ölçmeden "düzelttim"
denmez* — testler bu yüzden çoğunlukla gerçek geometriyi gerçek FreeCAD
motorunda ölçer, mock kullanmaz.

> `freecadcmd`, betikten **sonraki** argümanları `sys.argv`'ye koymaz — onları
> açılacak dosya sanar. Bu yüzden test betikleri argüman almaz.

---

## Proje yapısı

```
caddy/
  commands.py         FreeCAD komut kaydı
  config.py           ayarlar + model/efor tabloları (ölçümler yorumlarda)
  conversation.py     denetleyici: tur akışı, geri/ileri al, görsel bütçesi
  locate.py           claude.exe'yi bulur (npm / native / PATH)
  log.py              FreeCAD Report view'a yazar
  sohbet_log.py       LOG/<tarih>_<oturum>.txt — bir sohbet bir dosya
  gorunum.py          3B görünüm yakalama
  context/            belgeyi modele anlatan serileştirici
  execution/          kod çalıştırma, koruma, doğrulama, ölçüm yardımcıları
  transport/          claude.exe süreci, kalıcı oturum, stream-json çözümü
  ui/                 dock paneli, kod kartı, üst menü
workspace/CLAUDE.md   modele giden sabit istem (yardımcı tablosu + kurallar)
tests/                FreeCAD motorunda koşan 678 kontrol
Monkey/               daha eski, ayrı bir deneme eklentisi (CADdy'den bağımsız)
```

Katman kuralı: `context/`, `execution/`, `caddy/kaynak.py`, `caddy/belge.py`
**Qt import etmez** — böylece testler GUI'siz koşabiliyor. (`MANTIK.md` §12.)

---

## Sorun çıkarsa

| belirti | ne yap |
|---|---|
| Workbench listesinde CADdy yok | Junction doğru mu: `dir "%APPDATA%\FreeCAD\v1-1\Mod"` |
| Panel açılmıyor, hata var | View → Panels → **Report view** — bütün günlük orada |
| "claude.exe bulunamadı" | Terminalde `claude --version`. Çalışıyorsa yolu Edit → Preferences → CADdy'ye yaz |
| Eklenti FreeCAD'in açılışını bozdu | Klasöre `ADDON_DISABLED` adında boş dosya koy; FreeCAD atlar |
| Bütün eklentileri kapat | `ALL_ADDONS_DISABLED` |

---

## Belgeler

| dosya | ne var |
|---|---|
| `MANTIK.md` | Her kararın gerekçesi ve ölçümü. Projenin asıl belgesi. |
| `workspace/CLAUDE.md` | Modele giden sabit istem — yardımcı tablosu, kurallar. |
| `freecad_yetenekleri.txt` | FreeCAD API envanteri: kullandıklarımız ve kullanmadıklarımız. |
| `log_incelemesi*.txt` | Gerçek oturumların ölçülmüş karnesi. |
| `LOG/` | Yeni sohbetler buraya yazılır (depoya girmez). **Beş eski oturum depoda duruyor** — `MANTIK.md` ve inceleme dosyaları onların saat damgalarına atıf yapıyor. |
| `PLAN.md`, `report.txt` | Eski plan ve açık borç listesi (bir kısmı bayat). |

---

## Lisans

MIT — `package.xml`. Furkan Bulus.
