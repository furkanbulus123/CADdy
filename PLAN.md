# CADdy — mimari, ölçümler ve yol haritası

## Neden bu proje var

`3D_Models` projesinde iş Claude Code terminalinden yürüyordu: kullanıcı yazar,
model `.step.py` üretir, FreeCAD sadece görüntüler. İki sınırı vardı — kullanıcı
FreeCAD'in kendi araçlarını kullanamıyor, ve FreeCAD'de elle yaptığı her şey bir
sonraki üretimde siliniyordu.

CADdy'nin istediği şey sıra-sıra çalışma:

> insan elle bir şeyler yapar → AI'a sorar → AI devam eder → insan yine devam eder

Bu, `3D_Models`'in en temel kuralıyla (*"kaynak koddur, çıktı üretilir"*)
doğrudan çelişir. Sıra-sıra çalışma istiyorsan script doğruluk kaynağı olamaz.

**Karar: doğruluk kaynağı canlı FreeCAD belgesidir.** CADdy `3D_Models`'in
yerine geçmez, yanında durur.

---

## Araştırmada çıkan üç sert gerçek

| Bulgu | Sonuç |
|---|---|
| FreeCAD 1.1'de AI adına **hiçbir şey yok** — tüm kaynak ağacında `openai\|anthropic\|llm\|copilot` **0 eşleşme** | Sıfırdan; uyarlanacak bir şey yok |
| Saf Python eklentisi yeterli. C++ yolu: LibPack (GB'lar) + MSVC + 2.236 `.cpp` soğuk derleme | **Derleme yok** |
| FreeCAD Python **3.11.14**, `3D_Models` venv'i **3.12.10**; `numpy/shapely/manifold3d/OCP` hepsi cp312 | venv `sys.path`'e **sokulamaz** — ağır iş `subprocess` ile dışarı |

Kullanıcı verisi `%APPDATA%\FreeCAD\`**`v1-1`**`\` altında (1.1 ile sürümlendi).
`%APPDATA%\FreeCAD\Mod` **yanlış yoldur**, 1.1 oraya bakmaz.

---

## Ölçümler — bu plan tahmine değil bunlara dayanıyor

| Ne | Değer |
|---|---|
| `claude.exe` tek atışlık `-p --output-format json` | **8.7 sn** (4.2 API + ~4.5 açılış) |
| Kalıcı süreç, tur 1 | 8.5 sn |
| **Kalıcı süreç, tur 2** | **2.4 sn** ← M6'nın gerekçesi |
| Tam tur (soru → kod → çalıştır), gerçek test | 8.8 sn · $0.07 |
| `claude.exe` konumu (bu makine) | `%USERPROFILE%\.local\bin\claude.exe` — npm yolu artık geçerli değil, `locate.py` ikisini de arıyor |
| FreeCAD konumu (bu makine) | `%LOCALAPPDATA%\Programs\FreeCAD 1.1\bin\` — `C:\Program Files\` **değil** |

`--verbose`, `-p --output-format stream-json` ile **zorunlu**.
`rate_limit_event` diye bir mesaj tipi var → ayrıştırıcı bilinmeyen `type`
değerlerinde **asla patlamamalı**.

`--bare` **kullanılmaz**: OAuth'u devre dışı bırakıp `ANTHROPIC_API_KEY`
zorunlu kılıyor, yani aboneliği kırar.

---

## Mimari kararlar

### QProcess — `subprocess` + `QThread` değil

Qt olay döngüsünde çalışır: `readyReadStandardOutput` **GUI thread'inde**
tetiklenir. Worker thread yok, `moveToThread` yok, widget'a yanlış thread'den
dokunma riski yok. İptal `kill()`, ölüm bir sinyal. Windows'ta
`CREATE_NO_WINDOW` bedava geliyor (yine de elle de veriliyor).

"JSON'u GUI thread'inde ayrıştırmak dondurur" itirazı geçersiz: bir mesaj birkaç
KB. Burada GUI'yi gerçekten donduran şey `doc.recompute()` ve o **zaten** GUI
thread'inde olmak zorunda (OCC tek thread'li).

### İstem stdin'den gider

Komut satırından değil. Belge bağlamı kilobaytlara çıktığında Windows'un ~32k
argüman sınırı ve tırnak kaçışı sorun olur; stdin'in böyle bir sınırı yok.

### `--tools ""` asıl güvenlik sınırıdır

AI'ın **kendi** dosya erişimi yok. Diske dokunan tek şey, kullanıcının panelde
**Çalıştır**'a bastığı koddur. Bu, herhangi bir AST taramasından güçlü bir
garantidir — AST guard'ı (M7) bir **lint**, sandbox değil:
`getattr(__import__('o'+'s'),'system')` onu kolayca atlar. Amacı **kazayı**
yakalamak.

### `setActiveTransaction(ad, persist=True)`

`persist` şart. Kod bir sinyal geri çağrımında, yani bir `Gui::Command` yığınının
**dışında** çalışıyor; FreeCAD 1.1'de orada açılan işlem komut yığını boşalınca
otomatik kapanıyor ve tek temiz geri alma bozuluyor.

### `linecache` kaydı

`compile()` sonrası kaynağı linecache'e elle koymazsak traceback
`File "<caddy:...>", line 12` der ve **satırı göstermez**; model neyi
düzelteceğini tahmin etmek zorunda kalır. Tek satır, otomatik onarım başarısını
doğrudan yükseltiyor.

### Ön-izleme (diff) yok

CAD'de çalıştırmadan önce "ne olacağını" gösteren anlamlı bir diff **yoktur** —
sonuç geometridir, metin değil. Dürüst ilkel: çalıştır → 3D'de bak → tek Ctrl+Z.

---

## Klasör düzeni

```
CADdy/
  package.xml         <subdirectory>./</subdirectory>  ZORUNLU (asagiya bak)
  InitGui.py          workbench + komut kaydi, mantik yok
  Init.py             konsol modunda no-op
  workspace/CLAUDE.md CLI'in cwd'sinde; cikti kalitesini en cok bu belirler
  caddy/
    config.py  log.py  locate.py  gorunum.py  sohbet_log.py
    transport/  framing.py  process.py  transport.py   (sistem sozlesmesi burada)
    context/    serializer.py
    execution/  blocks.py  executor.py  dogrulama.py  islem.py  kesif.py  olcum.py
    conversation.py
    ui/         dock.py  code_card.py  ust_menu.py
    commands.py
  tests/        freecadcmd ile calisan dogrulamalar (12 dosya)
  LOG/          sohbet gunlukleri — kalite analizinin tek kaynagi (bkz. S3)
  resources/icons/
```

**Katman kuralı:** `ui/` → `conversation` import edebilir, tersi **asla**.
`context/` ve `execution/` QtWidgets görmez → `freecadcmd` ile başsız test
edilebilir. (Bu kural sayesinde aşağıdaki testlerin tamamı arayüzsüz koşuyor.)

> **Yükleme tuzağı:** `package.xml` varsa FreeCAD `InitGui.py`'yi kökten
> **çalıştırmaz**, her `<content><workbench><subdirectory>` altından çalıştırır.
> Düz yerleşimde `<subdirectory>./</subdirectory>` şart.

---

## Durum

| Faz | Ne | Durum |
|---|---|---|
| **M0** | package.xml + InitGui.py + dock | ✅ |
| **M1** | Yürüyen iskelet: sor → kod → çalıştır → tek Ctrl+Z | ✅ |
| **M2** | Streaming (`--include-partial-messages`) + iptal | ✅ |
| **M3** | Bağlam serileştirici (`context/serializer.py`), bütçeli | ✅ |
| **M4** | Hata geri besleme: otomatik onarım turu + bütçe + "aynı hata tekrarsa dur" | ✅ |
| **M5** | Aktör atfı: geri alma yığınında `AI: ` öneki, host yalnız kendi işini geri aldırıyor; `DocumentObserver` dokunulan nesneleri topluyor | 🟡 atıf ve gözlemci var, ayrı bir `ChangeJournal` yok — bugüne kadar gerekmedi |
| **M6** | Kalıcı süreç (tur 1 = 8.5 sn → tur 2 = 2.4 sn) | ✅ |
| M7 | AST guard'ları | ⬜ **yapılmadı** — `--tools ""` zaten daha sert bir sınır, guard yalnızca kazayı yakalar |
| **M7b** | İlk düzenlemede `saveCopy()` yedeği | ✅ (`.caddy-backups/`) |
| M7c | Tercihler sayfası | ⬜ ayarlar panelin üst satırında ve sağ tık menüsünde duruyor |

Sonradan eklenen ve planda hiç yazmayan, çalışan işler: deterministik
doğrulama katmanı (`execution/dogrulama.py`), ölçüm yardımcıları
(`kesif`, `olc`, `kesit_konturu`, `baski_kontrol`…), görsel kontrol
(tek ve üç kare), ileri al, sohbet günlüğü, amaca göre imalat kuralları
(MANTIK §33-35).

### M5 neden asıl kilometre taşı

Makro **kaydı** Python'dan başlatılamıyor (`MacroManager::MacroRedirector`
C++'a kapalı). Desteklenen yol `App.addDocumentObserver`. Üç kural pazarlıksız:

1. **Nesne referansı değil, isim sakla** — silinmiş nesneye referans tutan bir
   kayda dokunmak sert çökme.
2. **Slot içinde asla exception fırlatma** — FreeCAD'in bildirim zincirini bozar.
3. **Değerleri tembel oku** — slot içinde anlık görüntü alma.

`actor="ai"|"user"` atfı sıra-sıra çalışmanın kalbi: prompt'un *"sen düşünürken
insan Pad'i taşıdı"* diyebilmesini sağlar ve AI'ın kendi düzenlemesini kendisine
geri yansıtmasını engeller.

---

## Doğrulama

```powershell
$env:PYTHONUTF8="1"
$fc = "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\freecadcmd.exe"
Get-ChildItem tests\test_*.py | ForEach-Object { & $fc $_.FullName }
```

> `freecadcmd` içinde Qt import edilince `sys.stdout` yönlendiriliyor ve
> `print()` çıktısı **kayboluyor**. Testler bu yüzden raporu ayrıca
> `tests/_son_rapor.txt` ve `tests/_son_tur.txt` dosyalarına yazar — sonuçlara
> oradan bak.

Bu makinede sayıldı (2026-08-26), hepsi sıfır hata:

| Test | Sonuç | Ne kanıtlıyor |
|---|---|---|
| `test_tam_tur_fc.py` | **157** | Tam tur: claude → `freecad-python` bloğu → canlı belgede exec → tek Ctrl+Z; ayrıca sistem sözleşmesinin maddeleri ve boyut tavanı |
| `test_islem_fc.py` | **111 OK** | İşlem (Pad/Pocket/desen) davranışları, sessiz başarısızlıkların yakalanması |
| `test_panel_fc.py` | **91** | Panel genişliği, hiçbir yazının kırpılmaması, düğme boyları, açılışta sessizlik |
| `test_mesh_cikti_fc.py` | **93 OK** | Mesh çıktısı ve sayı uydurmama |
| `test_geri_al_fc.py` | **64** | Geri/ileri al yığını, AI'ın yalnız kendi işini geri alması |
| `test_executor_fc.py` | **50** | İşlem bütünlüğü, iptalde artık bırakmama, sözdizimi hatasında boş undo girdisi olmaması |
| `test_koruma_fc.py` | **45** | Yedek alma, tekrar eden kod, hata bütçesi |
| `test_dogrulama_fc.py` | **40** | Deterministik geometri kontrolleri ve KOŞMAYAN ayrımı |
| `test_baglam_fc.py` | **34** | Serileştirici bütçesi ve seçime yakınlık sıralaması |
| `test_yukleme_fc.py` | **34** | `package.xml` FreeCAD'in *kendi* ayrıştırıcısından geçiyor, modüller Python 3.11'de import ediliyor |
| `test_gorunum_fc.py` | **13** | Üç açılı yakalamada kameranın kullanıcının açısına geri dönmesi |
| `test_initgui_kapsam.py` | — | Özet satırı basmıyor; sayıya dahil değil |

### Riskler ve durumları

| # | Risk | Durum |
|---|---|---|
| R1 | Kalıcı süreç çok turlu çalışmaz | ✅ çürütüldü — tur 2 = 2.4 sn |
| R2 | QProcess FreeCAD olay döngüsünde tuhaflık yapar | ✅ çürütüldü — `test_tam_tur_fc` gerçek Qt döngüsünde geçti |
| R3 | `persist=True` tek temiz geri alma vermez | ✅ çürütüldü — `test_executor_fc` |
| R4 | Model parametrik yerine ölü `Part::Feature` üretir | 🟡 sistem sözleşmesi + `dogrulama` bunu görüyor ve söylüyor; 20 promptluk değerlendirme seti hâlâ yok |
| R5 | Serileştirici bütçeyi taşırır ya da önemliyi atar | ✅ çürütüldü — `test_baglam_fc` bütçeyi ve sıralamayı ölçüyor |
| R6 | Uzun `recompute()` GUI'yi dondurur | ⚠️ **iyi bir çözüm yok** — OCC tek thread'li ve GUI thread'inde olmak zorunda. Meşgul göstergesi + "çalışırken iptal edilemez" dürüstlüğü |
| R7 | Undo sonrası bayat namespace bağlaması **sert çökme** | 🟡 kısmen: `namespace_temizle()` her geri almada çağrılıyor + sistem promptunda "isimle yeniden çöz" kuralı |
| R8 | AST guard meşru CAD kodunu bloklar | ⬜ M7; meşru çıktıda `block` = kural yanlış, **baypas ekleme, kuralı düzelt** |

---

## Sırada ne var (2026-08-26'da kullanıcının istediği üç iş)

Henüz karar verilmiş tasarımlar değil; **incelenecek işler**. Her biri
için bu projede geçerli kural aynı: önce ölç, sonra yaz.

### S1 — Üç açılı görsel gerçekten alınıp doğru işleniyor mu ⏸️ **askıya alındı (2026-08-28) — görsel sistemi kapalı**

S9 deneyinden sonra görsel gönderimi kapatıldı (`GORSEL_ACIK = False`,
MANTIK §47). Bu maddedeki sorular **geçersiz değil, konusuz**: gönderilen
kare yok, dolayısıyla "üçü de modele ulaşıyor mu" diye sorulacak bir şey
yok. Kod duruyor, madde de duruyor.

**Görsel yeniden açılırsa bu madde ilk sıraya döner** — hatta açmadan
önce yapılmalı: kapatma kararı görüntünün faydasının ölçülemediğine
dayanıyordu, ve eğer üç kareden ikisi aynıysa fayda zaten yapısal olarak
eksik ölçülmüş olur. Aşağıdaki liste o gün için duruyor.

<details>
<summary>Açılırsa incelenecekler (2026-08-26'da yazıldı)</summary>

Kanıtlanan şey **çağrı sırası**: `tests/test_gorunum_fc.py` sahte
bir `FreeCADGui` ile animasyonun kapandığını, `setCamera`'nın doğru anda
çağrıldığını ve kameranın geri geldiğini ölçüyor (13 kontrol).
**Kanıtlanmayan** şey görüntünün kendisi — freecadcmd'de 3B görünüm yok.

İncelenecekler:
- Üç kare gerçekten **üç farklı açı** mı, yoksa animasyon/çizim
  gecikmesi yüzünden ikisi aynı mı? (Kareleri diske yazıp bayt/piksel
  farkına bakmak yeter — aynı bayt = aynı kare.)
- `fitAll` sonrası parça kadraja **sığıyor** mu, kırpılıyor mu?
- Üçü de modele gerçekten **ulaşıyor** mu? Günlükte
  `GORSEL-KONTROL: 3 kare gonderildi (N bayt)` satırı var (§32'de 13 kez,
  103–222 KB arası) — ama modelin üçünü de *okuduğu* ayrı bir soru;
  yanıtta üç açıya birden atıf var mı diye günlükten sayılabilir.
- Ölçüm yeri: gerçek FreeCAD oturumu, `_probe_goruntu.py` tarzı bir
  betikle kareleri diske yazıp elle bakmak.

</details>

### S2 — Eski bir sohbete ve modele kaldığı yerden dönmek ✅ **yapıldı (2026-08-27, MANTIK §42)**

Kütüphane düğmesi artık klasör açmıyor, **liste** açıyor: her satırda
tarih, tur sayısı ve ilk mesajın özeti; seçip **Devam et** deyince sohbet
kaldığı yerden sürüyor.

Bağlamı biz taşımıyoruz — kimlik günlük başlığından okunuyor, sonraki tur
`claude --resume <oturum>` ile gidiyor ve geçmişi CLI kendi oturum
dosyasından yüklüyor. Panele geri yüklenen son birkaç mesaj **yalnızca
hatırlatma**; ekranda bunu açıkça yazıyoruz, çünkü "ekranda görünen" ile
"modelin bağlamında olan" karıştırılırsa kullanıcı yanılır.

Yeni: `caddy/kayitlar.py` (Qt'siz), `transport.oturumu_surdur`,
`sohbet_log.dosyaya_devam`, `ConversationController.sohbeti_surdur`.
Kimliği olmayan günlük listede duruyor ama **sürdürülemez** işaretli.

Açık kalan: CLI oturumu ne kadar süre saklıyor. Kayıp bir oturumda
`--resume` hata verecek; o hâlde kullanıcıya dürüstçe söylenmeli — şu an
hata normal tur hatası gibi görünüyor, ayrı bir mesaja değer.

**Kayıt tuşunun yeri sorunu ✅ çözüldü:** düğme ikon olarak üst satıra
döndü (MANTIK §38); ölçüldü, ikon düğmesi metin düğmesinin dörtte biri
kadar yer tutuyor.

### S3 — Boş ve gereksiz günlükler oluşmasın ✅ **yapıldı (2026-08-26, MANTIK §37)**

Aşağıdaki iki sebep de düzeltildi: başlık artık ilk gerçek kayda kadar
yazılmıyor (konuşulmayan oturum dosya üretmiyor) ve testler
`CADDY_LOG_DIR` ile `tests/_gunlukler/` altına yazıyor. Ölçüldü: tam
suite koşusundan sonra `LOG/` 106 → 106 dosya. Yapılmayan tek şey eski
çöpün silinmesi (42 başlık-only + 40 test artığı) — kullanıcının kararı.

<details><summary>İşin başlangıçtaki incelemesi</summary>

Ölçüldü (2026-08-26, `LOG/` klasörü): **106 dosya**, bunların **43'ü
298 bayt** — yani yalnızca başlık, tek satır içerik yok. 98 dosya 6 KB'ın
altında. Gerçek oturumlar 32–126 KB.

İki ayrı sebep var, ikisi de düzeltilebilir:

1. **Başlık hemen yazılıyor.** `sohbet_log.oturum_ac` çağrılır çağrılmaz
   dosyayı açıp başlığı basıyor. Oturum açılıp hiç mesaj yazılmazsa
   geriye 298 baytlık bir hayalet kalıyor. Çözüm: başlığı **ilk gerçek
   kayda kadar ertele** (tembel açılış) — o zaman boş oturum hiç dosya
   üretmez.
2. **Testler gerçek `LOG/` klasörüne yazıyor.** Küçük dosyaların içeriği
   testlerin kendisi: `SilenKutu`, `patlayan`, `birinci hata`… Suite her
   koşuşta ~10 dosya bırakıyor. Çözüm: testler `SohbetGunlugu(kok=...)`
   parametresini geçici klasörle çağırsın — sınıf bunu zaten destekliyor,
   yalnızca testlerde kullanılmıyor.

Bir de temizlik sorusu: `LOG/` sınırsız büyüyor. Eski ve **kısa**
günlükleri (örneğin 1 KB altı, 30 günden eski) silen bir bakım adımı
düşünülebilir — ama gerçek oturum günlükleri bu projede kalite
analizinin tek kaynağı, o yüzden silme kuralı **boyuta** göre olmalı,
yaşa göre değil.

</details>

---

### S4 — Çakışma körlüğü ✅ **yapıldı (2026-08-27, MANTIK §40)**

Beş maddenin hepsi uygulandı ve ölçüldü: `cakisma_kontrol()` yardımcısı
(şekil türüne göre üç ayrı doğru test), doğrulamaya otomatik komşu
taraması (1 nesne 0.018 sn, 8 nesne 0.062 sn — "yavaşlatmıyorsa" şartı
karşılandı), sözleşmede "görüntü bunu kanıtlayamaz" maddesi, yakın çekim
(`GÖRSEL-KONTROL YAKIN <ad>`, tek kare + aynı mesajda çakışma ölçümü) ve
keşif önceliklendirmesi (ilk 8 slotta artık hiç eskiz yok, sınır 8 → 24).
Testler 703 kontrol, sıfır hata.

<details><summary>İşin başlangıçtaki önerileri</summary>

Kullanıcının şüphesi ("görselleri yeterince analiz etmiyor mu?")
ölçüldü ve cevap **hayır, bakıyor ama yanlış yere soruyor**: 8 görsel
kontrolün ikisinde model "çakışma yok" dedi, kullanıcı çakışmayı gördü,
sonra `common()` 2.7 mm³ buldu. 900×640 karede o çakışma ~4 piksel ve
yelkenin arkasında — görüntüyle çözülemezdi.

Öneriler, faydası/maliyeti sırasıyla:

**S4.1 — `cakisma_kontrol()` yardımcısı (en yüksek fayda, en ucuz).**
Model doğru deseni zaten iki kez ELLE yazdı (`common().Volume` +
`distToShape` + bbox). Bunu `baski_kontrol` gibi hazır bir yardımcıya
çevir: verilen nesneler için tüm çiftleri tarar, her çift için en yakın
mesafe / kesişme hacmi / kesişimin bbox'ını basar. Yüzey (kalınlıksız)
parçalarda hacim 0 çıkacağı için **mesafe eşiği** de raporlanmalı —
logda tam bu var: "0.0 mm3 ama temas ediyor".

**S4.2 — Doğrulamaya otomatik komşu taraması.** `dogrulama.py` zaten
dokunulan nesneleri biliyor. Eklenen/değişen her nesne için en yakın
komşuya mesafe ve varsa kesişme hacmi rapora düşsün. O zaman model
sormayı unutsa bile **host söyler** — bu projede işe yarayan desen bu
(bkz. açık kabuk bulgusu). Dikkat: §33'teki dersi tekrarlamamak için
bulgu amaca göre okunmalı ve tekrar eden satır tek satırda toplanmalı.

**S4.3 — Sözleşme: görüntü neyi KANITLAYAMAZ.** Görsel kontrol maddesi
şu an "parçaların gerçekten değip değmediği" sorusunu görüntüye havale
ediyor. Değişmeli: temas/çakışma/iç içe geçme sorusu **ölçümle**
kapanır, görüntü yalnızca *nereye bakacağını* söyler. Ayrıca "tek
cümleyle onayla" kuralı sınırlanmalı — kısalık kalsın ama görüntünün
gösteremeyeceği bir şey görüntüye dayanarak iddia edilmesin.

**S4.4 — Detay karesi (yakınlaştırılmış görsel kontrol).** Global
çözünürlüğü artırmak pahalı (3 kare ~4 kat) ve arkada kalan çakışmayı
yine göstermez. Bunun yerine `GORSEL-KONTROL YAKIN <nesne>`: kamerayı o
nesnenin bbox'ına oturtup tek kare almak. Aynı token ile 4 px/mm yerine
40 px/mm.

**S4.5 — Keşif bütçesi önceliklendirilsin.** Ölçüldü: 52 nesnenin 8'i
ölçüldü, süre bütçesinin (3.0 sn) yalnızca 0.48 sn'i kullanıldı — yani
sınırı **süre değil sayı** koydu, üstelik 8 slotun 3'ü hacimsiz
eskizlere gitti (`doc.Objects` sırası). Öneri: eskizleri/iskeleyi sona
at, hacimli ve görünür nesneleri öne al, sayıyı süre bütçesi dolana
kadar zorla. Kod değişikliği küçük (`kesif.ilgili_nesneler` sıralaması
+ `AZAMI_NESNE`).

</details>

---

### S5 — Tur başına kod bloğu sayısı ✅ **karar verildi (2026-08-27, MANTIK §43)**

Soru: tek istekte 4-5 kod çalıştırmak kaliteyi artırır mı, yoksa çok veri
Claude'u yavaşlatır mı?

Ölçüm (kamyonet oturumu, 16 istek / 40 tur): bağlam 22k → 200k çıkarken
gecikmeyle **korelasyon r = 0.04**. Yavaşlatan bağlam değil. Pahalı olan
**kareler** (20 görsel = 433 KB ≈ bağlamın üçte biri).

> Buradaki "pencerenin tavanı 200 022 token" gerekçesi sonradan **yanlış
> çıktı**: aynı oturum 345 893 bağlama sorunsuz devam etti (MANTIK §44).
> Karar ayakta ama gerekçesi §44.2-44.3'e taşındı.

Karar: ölçüm blokları yoğunlaşsın (bir blokta 5-10 çağrı), yazan bloklar
bağımsızsa en fazla üç, üç kare varsayılan olmaktan çıksın. Sözleşmeye
işlendi; `test_tam_tur_fc` beş yeni kontrolle tutuyor.

### S7 — Görüntü yerine ölçüm ✅ **yapıldı (2026-08-27, MANTIK §44)**

Kullanıcının kararı: *"görüntüyü azaltalım, onun yerine çalıştırdığı kod
sayısını artıralım… görüntüden çok anlamıyor gibi geliyor"*. Günlük onu
doğruladı: görsel dönüşü olan 30 turun 7'sinde model kusur buldu ve
yedisinde de delil **yazdırılan bir sayıydı**, görüntü değil.

Yapılanlar:

- Çakışma raporundaki bulguların %77'si gizli kesme tabanlarıydı;
  `kesif.tuketilmis_mi` ile elendi. Aynı belgede 38 bulgu → 8, 431
  ölçülmeyen çift → 0, 2.04 sn → 0.63 sn.
- `cakisma_kontrol(odak=…)`: yakın çekimde tüm belge yerine yalnızca
  sorulan nesnenin çiftleri (946 → 16 çift).
- Kare sayısı kararı sözleşmeden **host'a** alındı
  (`conversation._kac_kare`): üç kare yalnızca yeni nesne eklendiyse ya
  da ikinci bakışsa; indirim modele **sebebiyle** bildiriliyor.
- Sözleşme: her yazan blok kendi kanıtını aynı blokta basar.

**DOĞRULANDI (2026-08-28, `LOG/2026-08-28_269df7a5.txt`).** Bir sonraki
oturum ölçüldü — 7 istek, 15 tur, 8 kod bloğu, 10 dk 41 sn:

| | 08-27 kamyonet | 08-28 (düzeltmeden sonra) |
|---|---:|---:|
| kod bloğu başarı | 35/37 (%94.6) | **8/8 (%100)** |
| üç kare oranı | 27/30 (%90) | **3/6 (%50)** |
| görsel gönderimi / istek | 1.15 | **0.86** |
| `ICINDEN GECIYOR` satırı | 813 | **11** |
| çakışma taramasında çift | 946 (431'i ölçülmedi) | **22-27, hepsi ölçüldü** |
| tarama süresi | 2.0 sn (bütçe doldu) | **0.08-0.75 sn** |

Kare kararı tam tasarlandığı gibi çalıştı: üç kare **yalnızca** yeni nesne
eklenen üç turda verildi (32 jant parçası, 12 dişli parçası, 3 cam
parçası); değişiklik turlarında tek kare gitti ve indirim notu bir kez
tetiklendi — yani model üç kare istedi, host gerekçesiyle reddetti.

Çakışma bulgularının **tamamı gerçek**: 7 ayrı satır, hepsi kasıtlı
gömmeler (teker ↔ şasi, teker ↔ kabin). Tüketilmiş nesne gürültüsü
sıfır; tarama başına 39-81 nesne elendi.

### S8 — Ölçüm/analiz yardımcılarını genişletmek 🟡 **ilk iki yardımcı yapıldı (2026-08-28), gerisi açık**

Kullanıcının sözü: *"bence kod ağırlıklı çok ölçüm yapmak çok mantıklı bir
işti. bunu daha da arttırabiliriz belki analizler ekleriz vesaire."*

#### Yapılan — `saglik()` ve `simetri()`

Aday listesi tahminle daraltılmadı; **günlükler sayıldı** ve seçimi sayı
yaptı:

| desen | kaç kez | kaç günlükte | karar |
|---|---:|---:|---|
| `isValid` | 156 | 9 | ✅ `saglik` |
| `isSolid` | 125 | 4 | ✅ `saglik` |
| `hasSelfIntersections` | 96 | 4 | ✅ `saglik` |
| `len(Shape.Solids)` | 86 | 7 | ✅ `saglik` |
| `hasNonManifolds` | 48 | 3 | ✅ `saglik` |
| "simetri" | 38 | 5 | ✅ `simetri` |
| `MatrixOfInertia` / atalet | **0** | 0 | ❌ yazılmadı |
| sapma haritası (Inspection) | **0** | 0 | ❌ yazılmadı |
| `removeSplitter` / `Part::Refine` | 0 (kodda) | — | ❌ yazılmadı |

Son üçü **bilerek** yazılmadı: ihtiyaç uydurmamak, S8'in kendi kabul
ölçütünün ta kendisi. Kütle merkezi (aday 3) da elendi — günlükteki 6
`CenterOfMass` çağrısının hepsi **yüz merkezi** bulmak içindi, denge
sorusu için değil. İhtiyaç doğarsa geri gelir.

**`saglik(*nesneler)`** — nesnenin türüne göre doğru testi kendisi seçer:
katıda `isValid` / `Solids` / `isClosed` / hacim işareti, mesh'te
`isSolid` / `hasNonManifolds` / `hasSelfIntersections` / bozuk üçgen.
Argümansız çağrıda tüm belgeyi tarar. Ön kabulü testte kanıtlandı:
**`isValid()` tek başına yetmiyor** — açık kabuk da ters katı da onu
geçiyor (bu ölçüm zaten `test_dogrulama_fc.py` başlığında yazıyordu).
"İki ayrı katı" **kusur değil bilgi** olarak raporlanır; modelin elle
yazdığı `len(Solids) != 1` olduğu gibi alınsaydı bileşik şekillerde
yanlış alarm üretirdi.

**`simetri(nesne, eksen=None)`** — şekli bbox orta düzleminde aynalayıp
**iki yönlü** farkı ölçer (tek yönlü fark yalnızca fazlalığı görür,
eksiği görmez). Katıda fark **hacmi** + fark bölgesinin bbox'ı, mesh'te
en büyük nokta sapması + yeri. Eksen verilmezse üçü birden ölçülür.
Elle yazılana üstünlüğü ölçülebilir: bant sayımı yalnızca *"bu tarafta
hiç nokta var mı"* diye sorar, yani **kaymış ama var olan** bir yarıyı
temiz gösterir — aranan kusur tam da odur.

Doğrulama, elle hesapla karşılaştırıldı: 40×20×10 kutudan tek tarafta
6×6×6 cep kesilince fark hacmi 216 + 216 = **432 mm³**, oran
432/7784 = **%5.5**. Yardımcı birebir bunu yazdı ve bozuk bölgeyi
`x 30..36` diye gösterdi. Maliyet: `saglik` 4 nesnede **0.05 sn**,
`simetri` üç eksende **0.11 sn**.

Testler `test_dogrulama_fc.py`'ye eklendi: 84 → **99 kontrol**.
Tüm takım: **931 kontrol, 0 başarısız.**

**Sözleşme yeri ölçüldü.** İkisi de sisteme eklendi (kullanıcının isteği:
*"bu eklediklerimizi de aktif olarak sistem prompta ekle"*). Sözleşme
25 678 → **26 903** karakter. Doğrulanan tavan tablosu:

| | |
|---|---:|
| sözleşme | 26 903 |
| sabit bayraklar | 300 |
| toplam komut satırı | 27 203 |
| **sert duvara pay** (Windows 32 767) | **5 564** |
| test tavanına pay (28 000) | 1 097 |

Kullanıcının isteminin argv'yi yemediği de doğrulandı — stdin'den
gidiyor (`--input-format stream-json`). Yani 28 000 **gerçek duvar
değil**, projenin kendi emniyet payı; sert duvar §35.1'de ölçülmüştü
(32 000 çalıştı, 40 000 "Argument list too long" ile 63 ms'de öldü).
Bir sonraki büyük ekleme bu payı tüketirse yer belli: uzun kılavuz
`workspace/CLAUDE.md`'ye taşınır, dosyanın argüman sınırı yoktur.

#### Hâlâ açık olan adaylar

Gerekçe elimizde: S7 sonrası oturumda 8 kod bloğunun **8'i de başarılı**
oldu ve blokların yoğunluğu 27-56 satır, blok başına 4-11 `print`, 4-7
ölçüm çağrısıydı. Kalite arttı, hız düşmedi (10 dk 41 sn'de 7 istek).
Yani yön doğru; sıradaki soru **hangi ölçümler eklenmeli**.

Adaylar tahminle değil, günlüklerde modelin ELLE yazdığı desenlerden
çıkarıldı — bir şeyi iki kez elle yazıyorsa o yardımcı olmalı (§24'teki
aynı kural):

1. **`ol(ad)` / toplu ölçüm.** Modelin ilk bloğunda kendi eliyle yazdığı
   şey buydu: `def ol(ad)` tanımlayıp 24 nesne için çağırdı (bbox, hacim,
   katı sayısı, geçerlilik). Her oturumda yeniden yazılıyor. `olc()` bir
   ad listesi kabul etmeli, ya da `kesif(adlar=[...])`.

2. ~~**`simetri_kontrol`**~~ → yukarıda **yapıldı**. (Tetikleyen olay
   duruyor: 08-27'de kullanıcı *"simetrik değil diğer tarafta yok"*
   demek zorunda kalmıştı; model üç kareye bakmış, görememişti.)

3. **Kütle merkezi / denge** → **elemem yanlıştı, geri geldi.** O günkü
   günlüklere göre eleme doğruydu (6 `CenterOfMass` çağrısının hepsi *yüz*
   merkezi bulmak içindi, denge için değil). Ama S9'un üç lamba koşusu
   kanıtı üretti: **üçünde de** ağırlık merkezi hesaplandı (18 / 4 / 9
   geçiş) ve **ikisinde oturumun tek çökmesi tam orada oldu** —
   `'Part.Compound' object has no attribute 'CenterOfMass'`. Model bileşik
   şekilde tökezliyor ve her seferinde elle çözmeye çalışıyor.

   Yazılacak şey: `denge(*nesneler)` — birden çok cismin ortak ağırlık
   merkezi (hacim ağırlıklı), taban destek çokgenine göre içeride mi,
   ve devrilme kenarına kalan pay. Bileşik/mesh/katı ayrımını kendisi
   yapar. Kabul ölçütü sağlandı: iki kezden fazla elle yazıldı, çıktısı
   bulgu ile bilgiyi ayırabiliyor ("merkez taban dışında" kusur, koordinat
   bilgi), ve bilinen cevaplı testi var (düzgün kutunun merkezi tam
   ortasıdır).

4. **Boşluk (clearance) haritası.** `cakisma_kontrol` "geçiyor mu"
   sorusunu kapattı; kalan soru "kaç mm boşluk var" — hareketli parçalar
   ve baskı toleransı için. Aynı çift listesi üzerinden neredeyse bedava.

5. **Ölçü/gabari özeti.** Kullanıcının en sık sorduğu şeylerden biri;
   şu an her seferinde elle bbox birleştiriliyor (o oturumda da öyle
   yapıldı: `gb.add(...)` döngüsü).

**Sınır — bu maddenin kendi tuzağı.** Yardımcı eklemek kolay, gürültü
üretmek daha kolay: §44 tam da fazla ölçümün fazla satır üretip modelin
dikkatini yediğini gösterdi. Her yeni yardımcı için üç şart:

* günlükte **iki kez elle yazılmış** olmalı (uydurma ihtiyaç değil),
* çıktısı **bulgu ile bilgiyi ayırmalı** (§32/§44: değme kusur değildir),
* tipik turda **ölçülmüş** maliyeti yazılmalı; bütçe dolarsa kaç şeye
  bakılmadığını söylemeli.

### S9 — Fotoğraf gerçekten işe yarıyor mu? ✅ **deney yapıldı, görsel KAPATILDI (2026-08-28, MANTIK §47)**

Kullanıcının sözü (2026-08-28): *"fotoğrafların işe yarayıp yaramadığına
hâlâ emin değilim."* Şüphesi haklıydı ve deney koşuldu.

#### Düzenek

Aynı istem (masa lambası — yuvarlak taban, iki parçalı eklemli kol,
konik abajur, içinde ampul, ~400 mm, devrilmesin, parçalar iç içe
geçmesin), aynı model, aynı efor, her koşuda boş yeni belge, aynı tek
yan cevap (`f`). Görüntüyü kapatan anahtar **her iki koşudan önce**
kondu — kodu koşular arasında değiştirmek karşılaştırmayı çöpe atardı.

#### Sonuç

| | A — fotoğraflı | B1 | B2 |
|---|---:|---:|---:|
| yazma bloğu | 6 | **4** | **8** |
| süre | 3:04 | 2:08 | 4:01 |
| token | 48.7k | 37.2k | 50.6k |
| görsel | 129 KB | 0 | 0 |
| iç içe geçme kaldı mı | evet | evet | **hayır** |
| hüküm | iyi | kötü | **en iyi** |

**En iyi ve en kötü koşu aynı koldaydı.** Fotoğrafın etkisi saçılmanın
altında kaldı; bedeli ise ölçüldü — %31 token, %44 süre.

Kullanıcının hükmü: *"görselle alakası yok, tamamen randomluktanmış."*

#### Karar

Görsel sistemi **kapatıldı, silinmedi** (`conversation.GORSEL_ACIK`).
Sözleşmeden görselle ilgili tek madde bırakılmadı — kalsaydı model
olmayan bir şey ister, her turda reddedilir, tur boşa giderdi. Deney
anahtarı da söküldü; ölçüm düzeneği depoda kalmaz.

> **Bu kesin hüküm değil.** Üç koşu fotoğrafın işe yaramadığını
> kanıtlamaz; yalnızca etkisinin gürültünün altında, masrafının ise
> ölçülebilir olduğunu gösterir. Kanıtlanan şey bedel, aklanan şey
> değil. Kod bu yüzden yerinde duruyor: geri açmak iki satır
> (`GORSEL_ACIK = True` + sözleşme maddesi).

#### Deneyin asıl kazancı sorulmayan soruydu

Tabloda fotoğrafla korelasyon yok, **blok sayısıyla tam korelasyon
var**: 4 → kötü, 6 → iyi, 8 → en iyi. Bu bulgu S12'ye taşındı.

### S6 — Parçanın üstüne gelince sol altta ad/konum görünmüyor ✅ **çözüldü (2026-08-28)**

**Sebep yazılımda değildi: durum çubuğu ekranın dışında kalıyordu.**

Kullanıcının gerçek `user.cfg`'i okundu — hiçbir ayar kapalı değildi:

```
View grubu   : EnablePreselection / EnableSelection anahtarı YOK → varsayılan (açık)
Selection    : yalnızca AutoShowSelectionView=0 (ilgisiz)
MainWindow   : StatusBar = 1
Tema         : yalnızca PreSelectColor tanımlı
Araba.FCStd  : 54 nesnenin hepsinde Selectable = true
CADdy/Monkey : ikisi de statusBar/showMessage/SelectionGate'e dokunmuyor
```

Asıl ipucu aynı dosyanın başka bir satırındaydı:

```
Geometry: 0 0 1280 760      Maximized: 0      Ekran: 1280x800
```

Pencere maksimize değil, y=0'dan başlıyor ve 760 px yüksekliğinde. Durum
çubuğu pencerenin en altında, yani ekranın 760. pikselinde — görev
çubuğunun altında kalıyordu. Yazı hep yazılıyordu, görünmüyordu.
Kullanıcı pencereyi büyüttü, yazı geldi.

**Ders.** Üç tur boyunca üç aday elendi (nesne `Selectable`, ayar
anahtarları, eklenti müdahalesi) ve üçü de *yazılımın içinde* aranmıştı.
Sebep dışarıdaydı: pencere geometrisi ile ekran yüksekliği. Bir şeyin
"görünmemesi" ile "üretilmemesi" ayrı sorular; önce hangisi olduğu
sorulmalıydı. Bunu `statusBar().isVisible()` / `height()` tek satırda
söylerdi.

### S10 — Gerçek mühendislik analizi (FEM / modal) ⬜ **açık, ÖLÇÜM BEKLİYOR**

Kullanıcının sorusu: *"kullanıcı analiz yapmak isterse ne yapabiliriz?
analizleri de yaptırma şansımız var mı, mesela modal analiz."*

#### Ne ölçüldü

Kurulum dizini okundu (tahmin değil). FreeCAD 1.1.3'ün üç parçası da bu
makinede **kurulu**:

| gereken | var mı | nerede |
|---|---|---|
| FEM Python API | ✅ | `Mod/Fem` |
| ağ üretici | ✅ | `bin/gmsh.exe`, `NETGENPlugin.dll` |
| çözücü | ✅ | `bin/ccx.exe` (CalculiX) |

Yani modal analiz **teorik olarak mümkün**. Çalıştığı ve ne kadar
sürdüğü **ölçülmedi** — kullanıcı o an koşturmayı durdurdu, doğru olan da
buydu: önce B grubu bitecekti.

#### Analiz türleri ve zorlukları

| analiz | ne verir | zorluk |
|---|---|---|
| **modal (frekans)** | doğal frekanslar + mod şekilleri | ⭐ en kolayı — **yük gerekmez** |
| statik gerilme | von Mises, deplasman, emniyet katsayısı | orta — yük yüzeyi + yön |
| burkulma | kritik yük çarpanı | orta |
| termal / termomekanik | sıcaklık, ısıl gerilme | zor — çok sınır şartı |
| temas / doğrusal olmayan | parçalar birbirini nasıl eziyor | zor + yavaş |

**Neden modal ile başlanmalı.** Frekans analizi yük istemez. Modelin
karar vermesi gereken tek şey *hangi cisim* ve *hangi yüzeyden sabit*.
Diğer hepsinde "kuvvet kaç newton, hangi yöne" sorusu var ve model bunu
uydurmaya çok müsait — projenin en sevmediği şey.

**Bedava kalibrasyon.** Ankastre kirişin ilk doğal frekansı elle
hesaplanabiliyor:

    f1 = (1.875104^2 / 2pi) * sqrt(E*I / (rho*A*L^4))

100×10×10 mm çelik (E=210 GPa, rho=7900) için **≈ 833 Hz**. Yardımcı bu
sayıyı vermiyorsa yalan söylüyordur. Yani `simetri`nin 432 mm³'ü gibi,
bunun da bilinen cevaplı bir testi var — projenin kabul şartı sağlanıyor.

#### Gerçek riskler

* **Süre.** Ağ üretimi + çözüm saniyeler değil **on saniyeler** sürebilir.
  Mevcut `blogu_calistir` bütçesine sığmaz; ayrı bir iş olarak koşmalı ve
  panelin donmaması gerekir (§8b'deki sessizlik saati dersi).
* **Sessiz yanlış cevap.** FEM'in en tehlikeli tarafı: kötü ağ hata
  vermez, **yanlış sayı** verir. Bu, projenin "ölçemediğini uydurma"
  kuralının en zor sınavı.
* **Malzeme.** Atanmamışsa sonuç anlamsız. `Mod/Material` kütüphanesi
  kurulu, oradan çekilebilir; ama modelin malzeme *seçmesi* de bir
  uydurma noktası.

#### Sıradaki adım — tek bir ölçüm

Plana "yapılacak" yazmadan önce başsız bir tur koşturulup şu üç sayı
alınacak: (a) `ccx.exe` gerçekten çalışıyor mu, (b) ankastre kiriş kaç Hz
veriyor (833 bekleniyor), (c) bir tur kaç saniye sürüyor. Bu üçü
olmadan madde ilerlemez.

---

### S11 — Üretim ve çıktı tezgâhları ⬜ **açık, analiz değil ÇIKTI**

Analizle karışmasın diye ayrı madde. Kurulu olduğu **ölçülen** tezgâhlar
(`Mod/` listesi) içinden bu proje için anlamlı olanlar:

| tezgâh | ne yapar | değeri |
|---|---|---|
| **TechDraw** | teknik resim, ölçülendirme, PDF/SVG/DXF | yüksek — *"çizimini ver"* gerçek bir istek |
| **CAM** | takım yolu, G-kodu, talaş simülasyonu | yüksek ama derin bir alan |
| **Assembly** | bağlantı, kısıt çözümü, kinematik | 1.0'da geldi; hareketli mekanizma demek |
| Mesh / MeshPart | STL, OBJ, 3MF; katı↔ağ | 3B baskı hattı (kısmen var) |
| Import | STEP, IGES | dışarıdan parça alma |
| Spreadsheet | parametrik tablo | ölçüleri tabloya bağlama |
| **Plot** | grafik | modal frekans / gerilme eğrisini görsel yapar (S10'a bağlı) |
| Points, ReverseEngineering | nokta bulutu → yüzey | tarama işi |
| BIM, Robot, Idf, OpenSCAD | yapı, robot, elektronik kart, OpenSCAD köprüsü | bu proje için uzak |

**En yakın aday TechDraw.** Sebebi B grubunun sebebiyle aynı olmalı:
plana geçmeden önce günlüklerde *"çizim / ölçülendirilmiş resim / pdf"*
isteğinin kaç kez geçtiği **sayılacak**. Sayı düşükse madde beklemede
kalır — S8'de kütle merkezini eleyen kuralın aynısı.

**Sözleşme payı sınırı bu maddeyi de bağlıyor.** S8'de ölçüldü: sert
duvara 5 564 karakter pay kaldı. Yeni bir tezgâhı modele *anlatmak*
sözleşmede yer ister; yer bitince uzun anlatım `workspace/CLAUDE.md`'ye
taşınacak.

### S12 — Adım sayısı arttırıldı ✅ **yapıldı (2026-08-28, MANTIK §49)**

S9 deneyinin yan ürünü ve asıl kazancı. Üç koşuda kaliteyi belirleyen
tek değişken **yazma bloğu sayısı** çıktı:

    4 blok -> kötü (reddedildi)    6 blok -> iyi    8 blok -> en iyi

Mekanizma tahmin değil: her yazma bloğu kendi doğrulama raporunu
doğuruyor, yani daha çok adım = daha çok bulgu = kusurun hâlâ ucuzken
yakalanması. 8 bloklu koşuda model bir adımı `GERİ-AL` edip teğet
temasla yeniden kurdu; 4 bloklu koşuda aynı tür bulgular tek cümleyle
aklandı.

**Ne değişti:**

* Yazma bloğu artık **kesin olarak bir tane**. Eski *"bağımsızsalar en
  fazla üçe kadar"* izni kaldırıldı — ters yöne çekiyordu.
* 4/6/8 tablosu mekanizmasıyla sözleşmeye yazıldı.
* Karar kuralı: *"tek adım mı iki adım mı emin değilsen, iki yap."*
* Planlama maddesi: *"işi gerektiğinden daha ince kes; ikiden üç
  parçadan fazlası altı veya daha çok adım ister."*

**Gerekçe kullanıcının:** *"insanlar 1-2 dakika geç bitirebilir ama
tasarım güzel olmazsa hiçbir işe yaramaz. önceliğimiz kalite."* Ölçülen
ek maliyet gerçekten o mertebede (2:08 → 4:01).

**İzlenecek şey.** Bu kural bir üst sınır tanımıyor. Blok sayısı 15-20'ye
çıkarsa hem kullanıcı yorulur hem bağlam şişer — bir sonraki günlük
incelemesinde blok sayısı ve tur süresi sayılacak, gerekirse tavan
konacak. Şu an tavan koymuyoruz çünkü **ölçülmüş bir zarar yok**, yalnızca
teorik bir endişe var.

---

### S13 — Bulgu satırlarının kalitesi ✅ **yapıldı (2026-08-28, MANTIK §48)**

Kullanıcının isteği: *"bulgu satırlarının kalitesini arttırmamız lazım."*
Tetikleyen olay S9'un B1 koşusunda kayda geçti.

**Kusur.** Host `BULGU Abajur: icinden geciyor — ortak hacim 5.791e+04
mm3 (Ampul ile)` dedi; model bunu *"ampul abajurun tam içinde"* diye
**onay** olarak okudu. Oysa o hacim ampulün tamamıydı: abajur içi boş
kabuk olması gerekirken dolu koniydi. Aynı oturumda 2872 mm³'lük bir
mafsal geçmesi gerçekten kasıtlıydı. İki durumu ayıran şey hacmin
büyüklüğü değil, **küçük parçanın ne kadarının yutulduğu** — ve o oran
raporda yoktu.

**Üç düzeltme:**

1. **Oran eklendi.** `ortak hacim 57906 mm3, Ampul TAMAMEN GOMULU
   (hacminin %100'u iceride)` / `ortak hacim 4145 mm3, Eklem hacminin
   %45'i`. Eşik %98.
2. **Bilimsel gösterim kaldırıldı.** `%.4g` 10 000 üstünü `5.791e+04`
   yapıyordu ve CAD'de mm³ değerleri rutin olarak orada.
3. **Kesme artık keyfi değil.** 5 satırlık tavan belge sırasına göre
   kesiyordu, yani en ağır geçiş dışarıda kalabiliyordu — B1'de tam bu
   oldu. Artık yutulma oranına göre sıralı: %100 → %77 → %45 → %7 → %1.
   Kesilen kısım da kalanların en büyüğünü adıyla yazıyor.

**Sözleşme tarafı:** bulgular tek tek karşılanacak; *"kalanlar kasıtlı"*
bir cevap değil, bakmama biçimi. Kullanıcı "içine geçmesin" dediyse
kasıtlı bağlantı bile ihlaldir — açıklanmaz, teğet temas olarak yeniden
kurulur.

**Hâlâ açık olan.** Bu düzeltme yalnızca **katı–katı** çakışmaları
kapsıyor. Yüzey–katı ve yüzey–yüzey geçişlerinde oran hesaplanmıyor
(hacim yok, ölçü alan/eğri uzunluğu). Orada da bir "ne kadarı" sayısı
gerekiyor mu — günlükte kanıt çıkınca bakılacak, S8'in kabul ölçütü
burada da geçerli.

### S14 — Sürdürülen sohbet doğru belgeye bağlandı ✅ **yapıldı (2026-08-31, MANTIK §50)**

Kullanıcının sözü: *"kaldığı yerden yanlış başlıyor... tamam doğru chati
düzeltiyor ama kaldığı model o değil."* S2 sohbeti getiriyordu, **belgeyi**
getirmiyordu; kod her zaman o an aktif olan belgede koşuyor ve adlar
çakışırsa (`Kutu`, `Govde`, `Taban`) sessizce yanlış model değişiyordu.

**Ölçüm planı değiştirdi.** Bu maddenin ilk taslağı *"günlüğe belge adını
yaz, karşılaştır"* diyordu. `freecadcmd` ile ölçünce `doc.Name`'in
oturumlar arası **sabit olmadığı** çıktı (`ProbeAc` → `caddy_probe_ac`;
ad dosya adından yeniden türetiliyor). Kimlik **dosya yolu** oldu. Aynı
ölçümde: zaten açık dosyayı `openDocument` ile açmak ikinci kopya
üretmiyor, olmayan dosya `OSError` veriyor.

**Yapılan:**

* Günlük başlığına `belge :` ve `dosya :` satırları (etiket + iç ad, çünkü
  yedek dosyası `doc.Name` ile adlandırılıyor). Yol oturum ortasında
  doğabildiği için bulunana kadar tazeleniyor.
* Sürdürülen günlüğün başlığına **dokunulmuyor** — maddenin tek dayanağı
  o satır.
* `kayitlar.belge_durumu()` (Qt'siz, test edilebilir) dört dal veriyor:
  **açık** → sessizce o sekmeye geç · **kapalı** → sor · **kayıp** → uyar ·
  **kaydedilmemiş** → uyar + yedek kopyanın yolu · **bilinmiyor** → sus.
* Otomatik açmıyoruz: belge açmak ekranı değiştiren, geri alınmayan bir
  hareket; sormanın maliyeti tek tık. GUI'de açmak mevcut belgeyi
  kapatmıyor, yanına sekme geliyor.

**Yedek AÇMA hedefi değil.** `.caddy-backups` kopyası işin *başındaki*
hâl; "modelin geldi" diye açmak yapılan her şeyi silinmiş göstermek olurdu.

Testler: `test_kayitlar_fc.py` 24 → **50 kontrol**; takım **965, 0 hata**
(12 paket).

#### ⬜ ELLE DENENDİ, ÇALIŞMADI (kullanıcı, 2026-08-31)

> *"şimdi boş bir freecadde denedim gelmedi. lambayı çektim, sohbet geldi
> ama model gelmedi."*

Boş FreeCAD → kütüphaneden lamba sohbeti sürdürüldü → **sohbet geldi,
belge gelmedi, soru da sorulmadı.** Yani dört daldan hiçbiri görünür bir
şey yapmadı.

**En kuvvetli şüphe — henüz DOĞRULANMADI:** lamba günlüğü bu değişiklikten
ÖNCE yazıldı, dolayısıyla başlığında `belge :` / `dosya :` satırı yok.
`belge_durumu` o günlükte doğru davranıp `BILINMIYOR` döndü ve bilerek
sustu. Öyleyse kod yanlış değil, **kapsam** yanlış: 114 eski günlüğün
hiçbiri eşleşemez ve özellik ancak bundan sonraki sohbetlerde çalışır.

İkinci ihtimal: FreeCAD yeniden başlatılmadıysa eski modül yüklüydü
(§46.4'teki tuzak, daha önce bir kez yanlış negatife sebep oldu).

**Bakılacak sıra (ölçmeden düzeltme yok):**

1. `LOG/` içinde lamba günlüğünün başlığına bak — `belge :` satırı var mı?
   Tek komut: dosyanın ilk 10 satırı. Cevap "yok" ise sebep budur.
2. Bugün YENİ bir sohbet aç, bir şey çizdir, belgeyi kaydet, sohbeti
   kapat; sonra o sohbeti sürdür. Başlıkta satır oluşuyor mu, soru
   geliyor mu — özelliğin gerçek sınavı bu.
3. Eski günlükler için ne yapılacağına ondan sonra karar verilir.
   Muhtemel çare: yedek dosyası adından (`.caddy-backups/<Ad>_<damga>`)
   geriye doğru eşleştirme; ama bu **tahmin** üretir, ve yanlış belgeyi
   "senin modelin bu" diye açmak hiç açmamaktan kötüdür.

**Kalan iki şey:**

1. **Elle doğrulama (kullanıcı).** Sekme gerçekten açılıp odaklanıyor mu —
   `Gui.ActiveDocument` ataması başsız ölçülemez.
2. **Modele söylemek** (S14'ün 3. adımıydı, henüz yapılmadı). Kullanıcı
   "Açma" derse ya da dosya kayıpsa model hâlâ eski adlara güveniyor.
   Sürdürülen ilk turun isteminde bir emir gerekiyor: *"bu sohbet X
   belgesinde geçti, şu an Y açık — eski adlara güvenme, önce `kesif()`
   ile ölç."* §35.2'nin dersi: genel öğüt tetiklenmiyor, adı konmuş emir
   tetikleniyor. Bu satırın günlükte **gerçekten tetiklendiği** görülmeden
   madde tam kapanmaz.
