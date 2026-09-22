# MANTIK — CADdy nasıl çalışıyor, neden böyle kuruldu

Bu dosya **projeyi devralacak kişi ya da yapay zekâ** için yazıldı. Amacı
"hangi dosya ne yapar" listesi vermek değil — kodun kendisi zaten onu söylüyor.
Amacı, koda bakınca **görünmeyen** şeyi anlatmak: hangi kararlar alındı, hangi
alternatifler denendi ve **neden elendi**, hangi tuzaklara fiilen çarpıldı.

Kural ve komutlar `README.md`'de, yol haritası ve ölçümler `PLAN.md`'de.

---

## 1. Bu proje neyi çözüyor

Öncesinde iş `C:\Users\USER-1\Desktop\3D_Models` projesinde, Claude Code
terminalinden yürüyordu: kullanıcı yazar, model `.step.py` üretir, FreeCAD
yalnızca görüntüler. İki sınırı vardı:

- kullanıcı FreeCAD'in kendi araçlarını kullanamıyor
- FreeCAD'de **elle** yaptığı her şey bir sonraki üretimde siliniyor

İstenen şey sıra-sıra çalışma:

> insan elle bir şeyler yapar → AI'a sorar → AI devam eder → insan yine devam eder

### Bu, önceki projenin en temel kuralıyla çelişir

`3D_Models/MANTIK.md` §2: *"kaynak koddur, çıktı üretilir."*
`3D_Models/CLAUDE.md`: *"FreeCAD'de elle bir değişiklik yapıldıysa bir sonraki
`gen` çalıştırmasında kaybolur."*

Sıra-sıra çalışma istiyorsan **script doğruluk kaynağı olamaz** — çünkü
script'ten yeniden üretmek insanın el emeğini siler.

**Alınan karar: doğruluk kaynağı canlı FreeCAD belgesidir.**
CADdy, `3D_Models`'in yerine geçmez; yanında durur. `.step.py` hattı olduğu
gibi kalır.

---

## 2. Neden C++ değil, saf Python eklentisi

FreeCAD'in tam kaynak ağacı elde (`Desktop\cadtotext\FreeCAD-1.1.1`). İki yol
vardı:

| Yol | Maliyet | Karar |
|---|---|---|
| C++ kaynağı değiştir, yeniden derle | LibPack (GB'larca) + MSVC + **2.236 `.cpp` / 1.852 `.h`** soğuk derleme, saatler; sonra sonsuza dek fork bakımı | **Elendi** |
| Saf Python eklentisi | `%APPDATA%\FreeCAD\v1-1\Mod\` altına düşer, derleme yok, sürüm yükseltmesinden sağ çıkar | **Seçildi** |

İhtiyacımız olan her mekanizma zaten Python'a açık: workbench kaydı, komut
kaydı, gerçek `Gui::MainWindow` üzerinde `QDockWidget`, PySide6, `QProcess`.
FreeCAD'in kendi `src/Mod/Help/` modülü bunun birebir örneği.

**C++'a dokunmayı gerektirecek tek meşru aday** ileride `MacroManager::MacroRedirector`
olabilir (bkz. §7) — o da şart değil.

---

## 3. Sert kısıt: iki ayrı Python sürümü

| | Sürüm | İçindekiler |
|---|---|---|
| FreeCAD'in gömülü Python'ı | **3.11.14** | PySide6 6.8.3, Part, Sketcher, requests |
| `3D_Models\.venv` | **3.12.10** | build123d, OCP, trimesh, manifold3d, numpy, shapely |

`numpy`, `shapely`, `manifold3d`, `lxml`, OCP — hepsi **cp312** derlenmiş ikili
paketler. Venv'i FreeCAD'in `sys.path`'ine eklemek **çalışmaz.**

Sonuç: `3D_Models`'in ağır araçları CADdy içinden doğrudan çağrılamaz;
`subprocess` ile venv'e gitmek gerekir. Desen zaten mevcut ve ters yönde
çalışıyor: `3D_Models/tools/mesh-to-step.py` venv'den FreeCAD'i çağırıyor —
parametreleri üretilen betiğe gömüp `FC:` önekli stdout'u ayrıştırarak.

**İstisna:** `3D_Models/tools/kaynak_lib.py` yalnızca `requests` + stdlib
kullanıyor → FreeCAD'in 3.11'inde **olduğu gibi** çalışır. Model arama/indirme
paneli bu yüzden en ucuz sonraki adım.

> **Düzeltme (ölçüldü, §14.5):** bu istisna yalnızca **yarısı** için doğru.
> Printables ve indirme yardımcısı gerçekten olduğu gibi çalışıyor; ama
> `step_parts_ara/indir` alt süreci `sys.executable` ile açıyor ve FreeCAD
> içinde o **FreeCAD'in kendisidir** — argümanları FreeCAD'in ayrıştırıcısı
> yiyor. "Saf stdlib" olmak yetmiyor; `sys.executable`'a dokunan her satır
> gömülü yorumlayıcıda ayrı bir tuzak.

---

## 4. LLM arka ucu: neden Claude Code CLI

Değerlendirilen seçenekler:

| Seçenek | Neden elendi / seçildi |
|---|---|
| **Claude Code CLI** (`claude.exe`) | **Seçildi.** Kullanıcının mevcut Pro aboneliğini kullanıyor: API anahtarı yok, ek ücret yok. Oturum sürekliliğini (`--resume`) kendisi yönetiyor, biz yazmıyoruz. |
| Anthropic API + `anthropic` paketi | API anahtarı ve token başına ücret ister. Kullanıcının açık kararı: para harcanmayacak. |
| Yerel model (Ollama) | Bedava ama iyi GPU ister ve CAD kodu üretmede belirgin şekilde zayıf. |
| Zoo / KittyCAD Text-to-CAD | Ücretli, hesap ister, çıktısı **parametresiz ölü STEP**. (Ayrıntılı gerekçe: `3D_Models/LOG.md` §3.7.) |

### Doğrulanan kimlik durumu

`ANTHROPIC_API_KEY` tanımsız · `~/.claude/.credentials.json` → `claudeAiOauth`,
`subscriptionType: pro`. Yani **abonelik kullanılıyor, faturalama yok.**

### `--bare` KULLANILMAZ

Cazip görünüyor (hook'ları, CLAUDE.md keşfini, eklentileri atlar) ama
dokümantasyonu açıkça diyor ki: *"Anthropic auth is strictly ANTHROPIC_API_KEY
or apiKeyHelper; OAuth and keychain are never read."* Yani **aboneliği kırar.**

### Kullanılan bayraklar ve gerekçeleri

```
-p                          etkilesimsiz
--output-format stream-json yanit AKARKEN gosterilebilsin
--verbose                   -p + stream-json ile ZORUNLU, yoksa CLI reddediyor
--include-partial-messages  metin parcalari gelsin
--model opus
--tools ""                  AI'in KENDI dosya erisimi yok  (bkz. §6)
--permission-mode dontAsk   etkilesimsiz modda izin sorusunda takilmasin
--append-system-prompt ...  cikti sozlesmesi
--session-id / --resume     sohbet surekliligi CLI'da, bizde degil
```

### Ölçümler

| Ne | Değer |
|---|---|
| Tek atışlık çağrı | **8.7 sn** (4.2 API + ~4.5 süreç açılışı) |
| Kalıcı süreç, tur 1 | 8.5 sn |
| **Kalıcı süreç, tur 2** | **2.4 sn** |
| Gerçek tam tur (soru→kod→çalıştır) | 5–9 sn |

Kalıcı süreç ölçümü M6'nın (tek uzun ömürlü süreç) gerekçesi: açılış maliyeti
amortize oluyor.

---

## 5. Mimari kararlar ve elenen alternatifler

### `QProcess`, `subprocess` + `QThread` değil

Bu, ilk bakışta ters gelen ama doğru olan karar.

`QProcess` Qt'nin olay döngüsünde çalışır: `readyReadStandardOutput`
**doğrudan GUI thread'inde** tetiklenir. Sonuç: worker thread yok,
`moveToThread` yok, kuyruklu bağlantı disiplini yok, widget'a yanlış
thread'den dokunma riski yok. İptal `kill()`, süreç ölümü bir sinyal.

*"JSON'u GUI thread'inde ayrıştırmak dondurur"* itirazı burada geçersiz: bir
mesaj birkaç KB, `json.loads` mikro saniyeler. Bu eklentide GUI'yi gerçekten
donduran şey `doc.recompute()` ve o **zaten** GUI thread'inde olmak zorunda —
OpenCascade tek thread'li.

Yine de `ClaudeTransport` soyut arayüzünün arkasında duruyor: `QProcess`
sorun çıkarırsa takas edilir, yeniden yazılmaz.

### İstem stdin'den gider, komut satırından değil

Belge bağlamı kilobaytlara çıkıyor. Windows'ta `CreateProcess` argüman sınırı
~32k ve tırnak kaçışı ayrı bir dert. stdin'in böyle bir sınırı yok.

### Panelde diff/ön-izleme YOK — bilinçli

CAD'de "çalıştırmadan önce ne olacağını" gösteren anlamlı bir diff **yoktur**;
sonuç geometridir, metin değil. Dürüst ilkel şudur:

> çalıştır → 3D görünümde bak → beğenmezsen tek Ctrl+Z

Bu yüzden `Copilot_UndoLastAIChange` (CADdy'de `CADdy_UndoLastAIChange`)
birinci sınıf bir araç çubuğu komutu.

### Panel `QDockWidget`, Task panel değil

Task paneli (`Gui.Control.showDialog`) tek bir yuvayı işgal eder, Sketcher ve
PartDesign ile çakışır, **seçim değişince kendini kapatır**. Sohbet paneli
kalıcı olmak zorunda.

---

## 6. Güvenlik modeli — dürüst hâli

**İki katman var, bir tanesi yazılmadı.** Bu ayrımın altını çizmek gerekiyor,
çünkü bu bölüm uzun süre *"üç katman var"* diye yazılıydı ve ikisi mevcut
değildi — belge, olmayan bir emniyeti varmış gibi anlatıyordu (bkz.
`report.txt` madde 3).

1. **`--tools ""` — asıl sınır budur. MEVCUT.** AI'ın kendi dosya/kabuk/ağ
   erişimi yok. Diske dokunan tek şey, kullanıcının panelde **Çalıştır**'a
   bastığı koddur.
2. **İlk düzenlemeden önce `doc.saveCopy()` yedeği. MEVCUT.**
   `executor._yedek_al` — belge başına bir kez, `.caddy-backups/` altına.
   Gerekçesi ölçüldü: uzun bir seansta model kendi hasarını üstüne üstüne
   biriktirebiliyor (2026-08-19, bozuk BRep üzerine kurulan boolean zinciri)
   ve Ctrl+Z yığını o kadar geriye yetmeyebiliyor. **Asla işi engellemez:**
   yedek alınamazsa uyarılır ve devam edilir.
3. **AST guard'ı — YOK, yazılmadı.** Yazılırsa da bir lint olur, sandbox
   **değil**: `getattr(__import__('o'+'s'), 'system')` onu üç saniyede atlar.
   Amacı **kazayı** yakalamak olurdu, kötü niyeti değil.

   Bu yüzden `config.py`'deki `AutoRun` ayarı **çıkarıldı**. Açıklaması
   *"guard temizse onay beklemeden çalıştır"* idi ve dayandığı guard hiç
   yazılmamıştı; açılsaydı hiçbir şey denetlemeden kod çalışırdı. Guard
   yazılırsa ayar da geri gelir.

---

## 7. FreeCAD tarafında öğrenilenler (fiilen çarpıldı)

### 7.1 `InitGui.py` bir modül değil, `exec` edilen bir metin — kapsam tuzağı

**En pahalı hata buydu: workbench listede hiç görünmedi.**

FreeCAD `InitGui.py`'yi `FreeCADGuiInit.py` içindeki bir **fonksiyonun**
içinden argümansız `exec()` ile çalıştırır. Bir fonksiyon içinde argümansız
`exec`, `globals()` ve `locals()` olarak **ayrı sözlükler** kullanır:

- "modül seviyesi" atamalar `locals`'a düşer
- modül seviyesindeki **kod** onları görür
- ama **sınıf gövdesi** ve **fonksiyon gövdesi** ad aramasını `globals`'a yapar
  → buradaki adları **göremez**

```python
IKON = os.path.join(...)          # locals'a duser
class CADdyWorkbench(Workbench):
    Icon = IKON                   # NameError: name 'IKON' is not defined
```

FreeCAD bunu **sessizce** yutar: workbench hiç kaydedilmez, hata Report
view'da bile görünmez — yalnızca `stderr`'de. Kullanıcı "CADdy nerede" diye
sorana kadar fark edilmedi.

**Kural:** sınıf/metot gövdelerinde bu dosyanın kendi adlarını kullanma.
Sabitleri sınıf tanımından **sonra** ata (`CADdyWorkbench.Icon = IKON`).
FreeCAD'in kendi `OpenSCAD/InitGui.py`'si de bu yüzden ikonu `__init__` içinde
`self.__class__.Icon = ...` diye atıyor.

**İkinci katman:** `__file__` burada tanımsız değil **yanlıştır** — exec eden
modülün globals'ından miras kalır ve `FreeCADGuiInit.py`'yi gösterir. Doğrusu
`sys._getframe().f_code.co_filename`.

Regresyon testi: `tests/test_initgui_kapsam.py` — InitGui'yi bir fonksiyon
içinden argümansız `exec` ile çalıştırır. **İlk elle denemem `exec(kod, g)`
diye tek sözlükle yaptığı için yanlış "geçti" demişti.**

### 7.2 `package.xml` varsa `InitGui.py` kökten çalıştırılmaz

Her `<content><workbench><subdirectory>` altından çalıştırılır. Düz yerleşimde
`<subdirectory>./</subdirectory>` **şart**.

### 7.3 Kullanıcı dizini 1.1'de sürümlendi

`%APPDATA%\FreeCAD\`**`v1-1`**`\Mod\` — eski `%APPDATA%\FreeCAD\Mod`
**yanlış yoldur**, 1.1 oraya bakmaz.

### 7.4 `App.Document`'ta `Modified` yok

FreeCAD 1.1'de `AttributeError`. Kaydedilmemiş değişiklik için `isTouched()`.

### 7.5 Boş belgede `TopologicalSortedObjects` konsolu kirletir

*"cyclic dependency detected (no root object)"* uyarısı basar. Zararsız ama her
turda Report view'a düşer; 2'den az nesnede kullanılmıyor.

### 7.6 `freecadcmd` içinde Qt import edilince `print()` kaybolur

`sys.stdout` yönlendiriliyor. Testler bu yüzden raporu **dosyaya da** yazar
(`tests/_son_rapor.txt`, `tests/_son_tur.txt`). Bir testin "çıktı vermemesi"
başarısız olduğu anlamına gelmez — dosyaya bak.

### 7.7 Makro **kaydı** Python'dan başlatılamaz

`MacroManager::MacroRedirector` C++'a kapalı. "İnsan az önce ne yaptı"
sorusunun desteklenen cevabı `App.addDocumentObserver` (M5).

### 7.8 `setActiveTransaction(..., persist=True)`

Kod bir sinyal geri çağrımında, yani bir `Gui::Command` yığınının **dışında**
çalışıyor. `persist` olmadan işlem komut yığını boşalınca erken kapanıyor ve
"tek temiz geri alma" garantisi bozuluyor.

### 7.9 `linecache` kaydı olmadan traceback işe yaramaz

`compile(src, "<caddy:...>", "exec")` sonrası kaynağı `linecache.cache`'e elle
koymazsan traceback `line 12` der ama **satırı göstermez**. Model neyi
düzelteceğini tahmin etmek zorunda kalır. Tek satır, otomatik onarım başarısını
doğrudan yükseltiyor.

---

## 8. CLI akış şeması — ölçülerek çıkarıldı, tahmin edilmedi

`--output-format stream-json` satır tipleri:

```
system / subtype=init     oturum kimligi
stream_event              ic ice sarilmis Anthropic olayi:
   message_start            -> message.model   (ASIL cevaplayan model)
   content_block_start      -> content_block.type: "thinking" | "text"
   content_block_delta      -> delta.type: text_delta (alan: text)
                                           thinking_delta (alan: thinking)
                                           signature_delta (yok sayilir)
   content_block_stop / message_delta / message_stop
assistant                 tamamlanmis mesaj (parcalar kapaliysa yedek)
rate_limit_event          {status, resetsAt, rateLimitType: "five_hour", ...}
result                    TEK sonlandirici
```

**Kural: bilinmeyen `type` değerinde asla patlama.** `rate_limit_event` tam da
böyle, sonradan görüldü.

Şema yukarıda **eksikti**; "panel 6 dakika donuyor" şikâyeti kovalanırken iki
satır tipi daha ölçüldü ve ikisi de kritik çıktı:

```
system / subtype=status            {"status": "requesting"}
system / subtype=thinking_tokens   {"estimated_tokens": 250,
                                    "estimated_tokens_delta": 150}
```

`thinking_tokens` **model düşündüğü sürece ~1.5 sn'de bir gelir** ve elimizdeki
tek gerçek ilerleme sinyalidir. Çünkü:

> **`thinking_delta.thinking` alanı boş string geliyor.** CLI düşünme metnini
> redakte ediyor. Yani "ne düşündüğünü de görelim" isteği bu yoldan
> karşılanamıyor — panel düşünmenin **metnini** değil **ölçüsünü** gösteriyor.

İki incelik:

- `modelUsage` **birden fazla model** içerir; CLI kendi iç işleri için haiku
  kullanıyor. Panelde asıl cevaplayanı göstermek için `message_start`'taki
  model kullanılır.
- `rate_limit_info` **yüzde vermiyor** — yalnızca durum ve `resetsAt`. Bu
  yüzden "ne kadar kullandım" sorusu token sayısıyla cevaplanıyor.

---

## 8b. Bekleme süresi — donma sanılan şey ve gerçekte ne olduğu

Kullanıcı: *"önce 20 saniyede cevap veriyordu, şimdi 6 dakika bekledim cevap
gelmedi."* Regresyon avına çıkıldı; **regresyon yoktu.**

`LOG/2026-08-18_1ddcb553.txt` olayı yazıyor: istek 14:30:20, sonuç 14:33:02,
`HATA: iptal edildi`. Zaman aşımı 180 sn'di, yani onu **kullanıcı iptal etti** —
panel 162 saniye boyunca hiç kıpırdamadığı için haklı olarak donmuş sandı.

CADdy'nin argv'si birebir kopyalanıp ölçüldüğünde:

| | |
|---|---:|
| Toplam | 166.8 sn |
| İlk metin görünene kadar | 137.9 sn |
| **En uzun sessizlik** | **4.3 sn** |

Süreç hiç takılmadı. Üç ayrı kusur vardı:

1. **Nabız çöpe atılıyordu.** 89 tane `thinking_tokens` geldi, transport hepsini
   yok saydı. Panelin dakikalarca ölü görünmesinin sebebi buydu.
2. **Zaman aşımı toplam süreye bakıyordu** (180 sn). Bu tur 14 saniye farkla
   kurtulmuş; biraz daha zoru kesilip *"iptal edildi"* diye raporlanacaktı,
   üstelik sebebi görünmeden.
3. **Zaman aşımı ile iptal ayırt edilemiyordu** — `oldur()` her ikisinde de
   aynı bayrağı kuruyordu.

Düzeltmeler: sessizlik tabanlı saat (90 sn, **her stdout satırında sıfırlanır**),
nabzın panele bağlanması, zaman aşımı için ayrı bayrak ve açıklayıcı mesaj.

### Süreyi ne kısaltıyor — ölçülen, tahmin edilen değil

Aynı belge, aynı model (opus), sadece isteğin ifadesi değişiyor:

| istek | süre |
|---|---:|
| "kulbun karşısına kedi kafası logosu ekle" | 77 / 95 / 157 / 167 / 183 sn |
| "kulbun karşısına 20 mm çapında 3 mm disk ekle" | **54.4 / 55.7 sn** |

İsteği bölmek hem ~3 kat hızlandırıyor hem de süreyi **öngörülebilir** kılıyor.
Denenip **elenen** kaldıraçlar:

- **`MAX_THINKING_TOKENS`** — CLI dinlemiyor. 2000 verildi, model 12.000 token
  düşündü. Çalışmayan bir ayarı arayüze koymak yalan olurdu, konmadı.
- **Sözleşmeye "adım adım" kuralı** — yanıtın *biçimini* düzeltti (plan +
  yalnızca 1. adım geliyor, doğrulandı) ama **süreyi kısaltmadı**: kurallı
  ölçümler 95 ve 157 sn, kuralsızlar 77–183 sn, aynı gürültü bandı. Kural yine
  de duruyor, çünkü kullanıcıya bölmeyi *öğretiyor* — asıl kazanç orada.
- **Sonnet** — zor işte ~2 kat hızlı (22 / 108 sn) ama bir ölçümde kod bloğunu
  hiç vermedi; basit işte opus'tan **hızlı değil** (11.8'e karşı 8.1 sn).
  Seçenek olarak sunuluyor, varsayılan yapılmıyor, ipucu balonunda bu takas
  açıkça yazıyor.

Panel bu yüzden bekleyiş uzadıkça öğüt yükseltiyor (`dock._OGUT`): 30 sn'de
"takılmadı, büyük istek", 75 sn'de "isteği ikiye bölmeyi dene", 150 sn'de
"iptal edip tek bir parçasını iste". Eşikler yukarıdaki ölçümlerden geliyor.
İsteğin **metnine** bakıp zorluk tahmin etmek denenmedi: Türkçe metinden
"bu zor mu" çıkarmak kırılgan olurdu, geçen süre ise doğrudan ölçülen gerçek.

---

## 8c. Çalışma ritmi: önce kısa soru, sonra tek adım

Kullanıcının isteği: *"kısa kısa adımlarla yapsın, kullanıcı bir şey
istediğinde önce sorsun kaç cm istiyorsun gibi hızlıca sorsun, sonra '3 adıma
bölüyorum şimdi 1. adımı yapıyorum' desin"* — ve devamı: *"iletişim güçlü ve
sürekli olsun ki aynı düzlemde olsunlar"*, *"bir anda büyük şeyler yapmasın,
bölebileceği parçalara bölsün."*

**Bu, §8b'deki kararımı tersine çeviriyor.** Orada "soru sormasın, doğrudan
1. adımı yapsın" demiştim; gerekçem *"her istekte soru sormak sıra-sıra
çalışmayı yavaşlatır"* idi. Ölçüm bunu çürüttü: süreyi yiyen şey soru değil,
**belirsizlik**. Belirsiz istekte model varsayımları kendi kafasında tartıp
12 bin token düşünüyor; aynı iş ölçülü istendiğinde 54 sn. Ucuz bir soru turu,
pahalı bir tahmin turundan iyi.

Sözleşmenin dört maddesi (`transport.SISTEM_SOZLESMESI`):

1. **Tek kısa soru.** Ölçü/konum/adet/tip açıksa ilk yanıt tek sorudur —
   2-3 somut şık, biri "önerim" diye işaretli, **kod bloğu yok**, uzun
   düşünmeden. Aynı anda birden fazla soru yok; cevaplanmış bir şey tekrar
   sorulmaz; "farketmez" denince makul varsayımla devam.
2. **Kaç adım, hangisi.** *"Bunu 3 adıma bölüyorum; şimdi 1. adımı
   yapıyorum."* + kısa numaralı liste + **yalnızca 1. adımın** kod bloğu +
   sırada ne olduğu.
3. **Varsayımlar açıkta.** Hangi ölçüyü seçti, neyi referans aldı, hangi
   birim — her biri bir satır; tahminse "tahmin" desin. Pahalı bir tahminse
   sormasın, sorsun. Adım sonunda "3B'de şunu görmelisin" desin ki yanlış
   yön üç adım sonra değil oracıkta yakalansın.
4. **Adımın büyüklüğüne tavan.** "Adım adım" demek yetmiyor; model "adım 1"
   diye 200 satır verebiliyor. Kural: bakıp yargılanabilecek **tek görünür
   geometrik değişiklik**, ~50 satırın belirgin altında. "Bir de şunu"
   diye devam ediyorsa o ikinci adımdır.

**Ölçüldü** (aynı belge, opus, iki turlu gerçek oturum):

| tur | süre | çıktı |
|---|---:|---|
| 1 — "kulbun karşısına kedi kafası logosu ekle" | **28.0 sn** | kod yok; 3 şıklı tek soru + önerisi + ölçü varsayımı |
| 2 — "kafa çapı 25 mm olsun, devam et" | **55.0 sn** | "3 adıma bölüyorum, şimdi 1. adımı yapıyorum" + plan + varsayımlar + tek blok |

Toplam 83 sn; tek hamlede aynı iş 77–183 sn sürüyordu. Asıl kazanç sürede
değil: kullanıcı **28. saniyede** ekranda bir şey görüyor ve yön yanlışsa
oracıkta düzeltiyor. 1. adımın ürettiği şey de bir "yer işareti diski" oldu —
model konumu önce doğrulatmayı seçti, tam istenen davranış.

Yan gözlem: 2. turda tip sorusu cevapsız bırakıldı; model tekrar sormadı,
varsayılanı alıp devam etti. "Aynı şeyi iki kez sorma" maddesi tuttu.

---

## 8d. Kalıcı süreç, bağlam sayacı ve çift çalıştırma

Üçü de aynı gerçek seanstan çıktı: `LOG/2026-08-19_dcd21af7.txt`, 22 dakika,
25 tur, kupaya kedi yüzü. Proje boyunca en verimli oturum bu oldu.

### Kalıcı süreç (M6)

Kullanıcı: *"her mesajda bağlanıyor yazıyor, bir kere bağlansa sonra direkt
devam etse olmaz mı?"* Olur. Ölçüm: tur 1 = 8.5 sn, tur 2 = **2.4 sn** —
tek atışlık çağrının ~4.5 saniyesi saf süreç açılışıydı.

Bunun için girdi biçimi de `--input-format stream-json` oldu: stdin **açık
kalır**, her tur bir satır JSON kullanıcı mesajı yazılır. Sonuçlar:

- **Turu bitiren şey artık `result` satırı**, sürecin ölümü değil. Tek
  atışlıkta tur `_bitti`'de kapanıyordu; süreç ayakta kaldığı için o sinyal
  hiç gelmiyor. `_turu_bitir()` bu yüzden ayrıldı.
- **Süreç ölümü artık iki anlama geliyor.** Tur ortasındaysa hata (iptal /
  zaman aşımı / çökme); boştaysa zararsız — sonraki tur `--resume` ile
  yenisini açar, kullanıcı bağlam kaybetmez.
- **Panel kapanınca süreç öldürülür** (`closeEvent` → `transport.kapat()`).
  Yoksa FreeCAD'den sonra yaşayan bir `claude.exe` kalırdı.

### Bağlam sayacı — limiti CLI bildirmiyor

Kullanıcı `235k/1M` biçiminde bir gösterge istedi. `init` ve `result`
satırlarının **bütün alanları tarandı: limit hiçbirinde yok.** Kullanılan
taraf hesaplanabiliyor —

    bağlam = girdi + önbellekten okuma + önbelleğe yazma

(çıktı hariç: çıktı bağlama değil cevaba gider). Aynı seansta bu 7.3k'dan
**57.9k**'ya çıktı, yani ölçüm anlamlı. Sınır ise `config.BAGLAM_SINIRI`'ye
sabit yazıldı (Opus 5 / Sonnet 5 = 1M) ve ipucu balonunda *"sınır katalog
değeri, CLI bildirmiyor"* diye işaretlendi — uydurma bir kesinlik vermemek için.

### Çift çalıştırma — üretilmiş kanıt

Log iki kez yakalıyor: 13:30:58 ve 13:31:03'te aynı kart çalıştı ve **22 kopya
nesne** üretti (`KulakBodySol` + `KulakBodySol001`, sketch'ler, origin'ler…);
13:34:06–13:34:32 arasında başka bir kart **dört kez** koştu.

Sebep basit: kart bittikten sonra düğme "Tekrar çalıştır" olarak geri
etkinleşiyor ve kod çalıştırmak **birikimli** — ikinci çalıştırma
tekrarlamaz, üstüne ekler. **İkinci basışta onay soruluyor**, ilkinde değil:
her çalıştırmada onay istemek asıl akışı yavaşlatır, tehlikeli olan tekrar.

### Yan gözlem: model seçici işe yaradı

Kullanıcı 13:33'te opus'tan sonnet'e geçti; turlar 34–78 sn'den **4.5–12
sn**'ye indi. Hız/kalite takasının gerçek olduğunu ve seçicinin kullanışlı
olduğunu gösteren ilk saha verisi.

---

## 8e. Görsel doğrulama — mümkün, ölçüldü, ertelendi

`--tools ""` yüzünden modelin dosya erişimi yok, yani ekran görüntüsünü
**okuyamaz**. Ama `--input-format stream-json` girdisinde `image` içerik
bloğu gönderilebiliyor.

**Ölçüldü:** base64 PNG bloğuyla gönderilen test resmini (sol yarı kırmızı,
sağ mavi, üstte 3 siyah kare) model doğru tarif etti — *"3 tane siyah kare
var ve sol yarı kırmızı"*. Yani güvenlik sınırını gevşetmeden 3B görüntüsü
gösterilebiliyor; `--tools "Read"` açmaya gerek yok.

Tasarım kararı da alındı — **AI kendisi istesin**: yanıtında `GÖRSEL-KONTROL`
satırı yazınca panel mevcut 3B görünümü çekip bir sonraki tura ekler. Her
turda otomatik göndermek ~2-3k token boşa harcardı; AI'ın kendi kararı,
kullanıcının *"gerekiyorsa yapsın kendisi"* isteğinin birebir karşılığı.

**Uygulandı.** Akış:

1. Model yanıtının sonuna kendi satırında `GÖRSEL-KONTROL` yazar.
   İşaret **kullanıcıya gösterilmez** — o bir protokol sözcüğü, mesaj değil.
   Regex kendi satırını arıyor (`^…$`), yoksa *"görsel-kontrol gerekmiyor"*
   gibi bir cümle yanlışlıkla tetiklerdi.
2. **Aynı yanıtta kod bloğu varsa yakalama ertelenir.** Kod çalışmadan önce
   3B'de eski hal duruyor; o resmi göndermek modeli yanıltırdı. Panel
   `Çalıştır`'dan ve `Gui.updateGui()`'den sonra çekiyor. Kod patlarsa
   hiç çekilmiyor — işlem geri alındı, gösterilecek yeni bir şey yok.
3. Kod yoksa hemen çekilir.

**Döngü emniyeti:** model resme bakıp yine resim isteyebilir. Arka arkaya
en fazla **2** görsel tur; üçüncüde durup kullanıcıya söylüyor. Sayaç
gerçek kullanıcı mesajında sıfırlanır, otomatik görsel turunda sıfırlanmaz —
yoksa sınır hiç dolmazdı.

**Sessiz başarısızlık yok.** GUI yoksa, 3B pencere kapalıysa veya yakalama
boş dönerse kullanıcıya sebebiyle söyleniyor; sohbet yürümeye devam ediyor.
`saveImage` bazı sürücü/uzak masaüstü bileşimlerinde boş PNG üretebildiği
için `QWidget.grab()` yedeği var.

`caddy/gorunum.py` bilerek `ui/` altında **değil**: `conversation.py` onu
çağırmak zorunda ve katman kuralı (§12) conversation'ın `ui/` import
etmesini yasaklıyor. Modül widget üretmez, yalnızca PNG baytı döndürür.

**Başsız test edilemez** — `freecadcmd`'de `Gui.getMainWindow` bile yok
(ölçüldü). Testler bu yüzden işaret ayrıştırmayı, döngü sınırını ve
"GUI yokken patlamadan `None` dönme"yi sınıyor; gerçek yakalama panelde.

---

## 8f. FreeCAD'in turuncu satırları — üç yol denendi, ikisi elendi

Kullanıcı: *"uyarı ve haber kodlarını da AI görsün, yani turuncu kısımları."*
Haklı bir istek: bu satırların çoğu **istisna fırlatmıyor** — recompute
sessizce başarısız olur, konsola bir şey yazar, kod "başarılı" görünür ve
model neyin ters gittiğini göremez.

| yol | sonuç |
|---|---|
| `App.Console.AddObserver(...)` | **FreeCAD 1.1'de YOK.** Console modülünde yalnızca `GetObservers` / `GetStatus` / `SetStatus` ve `Print*` var; `AddObserver` kaldırılmış (`AttributeError`) |
| `redirect_stdout` / `redirect_stderr` | **Hiçbir şey yakalamıyor.** Console C++ tarafında yazıyor, Python akışlarına hiç uğramıyor |
| **Report view widget'ını okumak** | **Çalışıyor** — ve asıl istenen bu: kullanıcının ekranda gördüğü satırların ta kendisi |

Monkey-patch (`Print*` fonksiyonlarını sarmak) da çalışıyor ama **yetmiyor**:
yalnızca Python'dan yapılan çağrıları yakalıyor. Ölçüldü — boş bir
`Part::Cut` recompute edildiğinde C++ uyarısı patch'e **hiç uğramadı**.

**Karar: ikisi birlikte.** Report view asıl kaynak; monkey-patch GUI yokken
(testlerde) çalışan yedek. Aynı satır iki yoldan gelirse tekrarlanmıyor.

**Renk sınıflandırması.** Report view'da uyarı turuncu, hata kırmızı, normal
mesaj siyah. Metinde bunu ayırt edecek bir önek **yok**, o yüzden karakter
biçimindeki ön plan rengine bakılıyor: kırmızı baskın + yeşil/mavi düşük =
hata; kırmızı yüksek + yeşil **orta** + mavi düşük = turuncu = uyarı. Siyah
ve gri (mesaj/log) alınmıyor — gürültü. Renk okunamazsa satır **uyarı**
sayılıyor: kaybetmektense fazladan göstermek yeğ.

Kart üzerinde ayrı bir düğme çıkıyor — *"Uyarıları AI'a gönder (3)"* — çünkü
kod başarılı görünürken de gösterilecek bir şey olabiliyor.

---

## 8g. Baskıya hazır çıktı — venv gerekmiyormuş

§3 "mesh işleri cp312 duvarı yüzünden venv'e subprocess ister" diyordu.
**Bu, `trimesh`/`manifold3d` için doğru ama baskı hattı için yanlış.**
Ölçüldü, FreeCAD'in kendi 3.11'i hepsini yerli yapıyor:

| iş | süre |
|---|---:|
| STL / 3MF / OBJ / PLY dışa aktarım | 0.02–0.15 sn |
| STEP | 0.06 sn |
| `MeshPart.meshFromShape` (sapma/açı ayarlı) | 0.03 sn |
| `isSolid()` · `hasNonManifolds()` · `hasSelfIntersections()` | anlık |

Yani **manifold kontrolü bile var**. 20 mm delikli küp testinde `isSolid=True`,
`hasNonManifolds=False`, hacim 6431.8 mm³ — B-rep hacmiyle %0.04 farkla uyumlu.

**Sonuç: bu bir "özellik" değil, zaten yazılabilen kod.** AI kod yazıyor,
dışa aktarım da sadece kod. Eksik olan tek şey modelin bunu *önermesiydi*.
O yüzden çözüm bir modül değil, bir **sözleşme maddesi**: iş bitmiş
görününce tek soruyla format (.3mf/.stl/.step) ve kalite (taslak/normal/ince
→ `LinearDeflection` 0.5/0.1/0.05) sorulur, yazmadan önce mesh kontrol
edilir ve sonuç **söylenir**.

Bilerek dar tutuldu: her adımdan sonra değil, iş bitince. Model arama/indirme,
dilimleme ve yazıcıya gönderme **ayrı eklenti** — farklı iş, farklı arayüz.

---

## 8h. Üst şeritte kalıcı yer

CADdy bir *workbench* olduğu için üstteki açılır listeden seçilmedikçe ortada
yoktu. Workbench'in kendi `appendToolbar`/`appendMenu`'su bu sorunu **çözmez**:
onlar yalnızca o workbench aktifken görünür.

`caddy/ui/ust_menu.py` üste kalıcı bir **araç çubuğu** ekliyor — hangi
workbench'te olursan ol duruyor.

> **Sonradan daraltıldı (2026-08-20).** İlk sürümde menü çubuğuna ayrıca bir
> **CADdy menüsü** giriyordu ve araç çubuğunda iki komut vardı. Kullanıcı:
> *"FreeCAD'de CADdy kötü gözüküyor, sadece logosu gözüksün"* ve *"AI ile
> geri al falan gözükmesin."*
>
> Üst şeritte artık **tek bir logo düğmesi** var (paneli açar):
> menü çubuğu girdisi kaldırıldı — metin oradan geliyordu —
> ve `CADdy_UndoLastAIChange` üst şeritten çıkarıldı.
>
> **Hiçbiri kaybolmadı:** ikisi de workbench'in kendi menüsünde ve araç
> çubuğunda duruyor (`Initialize`). Üst şerit "her yerden erişilen kısayol";
> oraya her komutu koymak kullanıcının şikâyet ettiği kalabalığı yapıyordu.
>
> İki incelik: `setToolButtonStyle(ToolButtonIconOnly)` metni gizleyince
> düğmenin **tek anlatımı ikon** oluyor, o yüzden `_eylemler()` ikonsuz bir
> eylem asla döndürmüyor (komutun QAction'ı ikonsuz gelirse logo elle
> atanıyor); ve `_eski_menuyu_kaldir()` aynı oturumda eski sürüm çalıştıysa
> ekranda kalan menüyü siliyor.
>
> Test de değişti: `test_yukleme_fc.py` önce üst şerit komutlarının kayıtlı
> komutlarla **eşit** olmasını bekliyordu; artık **alt küme** olmasını ve
> geri al komutunun kayıtlı kalmasını ayrıca doğruluyor.

İki tuzak:

- **Zamanlama.** `InitGui.py` açılışta, ana pencere *henüz yokken*
  çalışabiliyor. Önce denenir, olmazsa `QTimer` ile 1.5 sn arayla 8 kez
  tekrar denenir; sonunda vazgeçilir — workbench yolu zaten duruyor,
  eklenti çalışmaya devam etmeli.
- **Komut kaydı.** `Initialize()` yalnızca workbench'e ilk geçildiğinde
  çalışıyor, ama üst menünün açılıştan itibaren dolu olması lazım — bu
  yüzden `commands.kaydet()` `InitGui.py`'nin sonunda da çağrılıyor.

Komutların `QAction`'ına ulaşmanın taşınabilir bir API'si yok (FreeCAD onları
ancak bir menüye eklenince üretiyor), o yüzden ana penceredeki `QAction`'lar
`objectName` ile taranıyor; bulunamazsa paneli açan yedek bir eylem kuruluyor
ki menü boş kalmasın.

---

## 9. Panelde dolar neden gösterilmiyor

CLI her yanıtta `total_cost_usd` döndürür. İlk sürümde bunu bilgi satırına
bastım; kullanıcı haklı olarak *"0.1 dolar harcadın diyor, API ile mi
harcıyor?"* diye sordu.

Gerçek: abonelikle (OAuth) çalışırken **böyle bir tahsilat yok**. O rakam
"aynı iş API fiyatlarıyla yapılsaydı ne tutardı" karşılığı.

**Karar:** bilgi satırında **token** gösteriliyor (gerçekten tüketilen
kaynak), dolar karşılığı açıklamasıyla birlikte ipucu balonuna taşındı.
Token dörde ayrılıyor çünkü aynı şey değiller: önbellekten **okunan** ucuz,
önbelleğe **yazılan** pahalı.

---

## 10. Sohbet günlüğü

`LOG/<tarih>_<oturum8>.txt` — **bir oturum = bir dosya**, her mesajdan sonra
anında yazılır.

- **Neden her mesajda:** ölçüldü, mesaj başına **1.05 ms**. 8 saniyelik bir AI
  çağrısının yanında %0.01. Biriktirmenin kazancı yok, FreeCAD çökerse kayıp
  riski var.
- **Neden oturum başına dosya:** "Yeni sohbet"e basınca yeni dosya açılır, bir
  işi sonradan bulmak kolay olur.
- **Tuzak:** dosya adı bugünün tarihinden üretiliyor. Aynı oturum için
  `oturum_ac()` tekrar çağrıldığında yolu yeniden hesaplarsa, gece yarısını
  geçen bir sohbet ikiye bölünür. Bu yüzden aynı oturum kimliğinde erken dönüş
  var.
- **Kural:** günlükteki hiçbir hata paneli etkilemez. Disk dolu, dosya kilitli,
  yol yazılamaz — sessizce yutulur, bir kez uyarılır ve kayıt kapatılır.
  Sohbet kaydı, sohbetin kendisinden önemli değildir.

---

## 11. Model çıktısının kalitesi nereden geliyor

**`workspace/CLAUDE.md`** — çıktı kalitesini eklentideki hiçbir koddan daha
çok bu dosya belirliyor. CLI onu çalışma dizininden kendisi yükler ve önbelleğe
girer.

İçindeki en önemli kural: **parametrik bırak.**

```
Tercih edilen : PartDesign::Body + Sketch + Pad      (gercek duzenlenebilir gecmis)
Kabul edilir  : Part::Box vb. parametrik ilkeller
KACINILAN     : Part.show(...) / Part::Feature       (olu sekil, gecmis yok)
```

Bunun sebebi eklentinin bütün varlık nedeni: insan AI'dan sonra çalışmaya devam
edecek. Ölü şekil bırakırsan devam edemez.

`executor.py` bu politikayı çalıştırma sonrası da denetler ve ihlali "yumuşak
hata" olarak bildirir (kod patlamamıştır ama sonuç kullanışsızdır).

Kademeli yaptırım merdiveni (ihtiyaç oldukça çıkılır):
`CLAUDE.md` örnekleri → sistem promptu kuralı → guard `warn` → guard `block`.

**İkinci kaynak: `transport.SISTEM_SOZLESMESI`.** `workspace/CLAUDE.md` *nasıl
kod yazılacağını* söyler; sözleşme *nasıl konuşulacağını* — kısa soru, adım
bildirimi, varsayımların açık edilmesi, adım büyüklüğü tavanı (§8c). İkisi
farklı yerlerde çünkü ömürleri farklı: `CLAUDE.md` kullanıcı tarafından
düzenlenebilir bir kılavuz, sözleşme ise koda gömülü ve testle korunan bir
biçim şartı. Sözleşmenin dört maddesi ölçülerek seçildi; değiştirmeden önce
§8c'deki rakamlara bak.

---

## 12. Neyin test edildiği, neyin edilmediği

| Test | Nasıl çalışır | Kapsam |
|---|---|---|
| `test_initgui_kapsam.py` | saf Python | §7.1 kapsam tuzağı — FreeCAD gerekmez |
| `test_yukleme_fc.py` | `freecadcmd` | `package.xml` FreeCAD'in *kendi* ayrıştırıcısından geçiyor mu, modüller 3.11'de import ediliyor mu |
| `test_executor_fc.py` | `freecadcmd` | İşlem bütünlüğü, iptalde artık bırakmama, ölü şekil politikası |
| `test_tam_tur_fc.py` | `freecadcmd` + gerçek claude çağrısı | Uçtan uca: akış, token, günlük, kod, tek Ctrl+Z, **nabız kablosu, model seçimi, sözleşmenin dört maddesi** (46 kontrol) |

`test_tam_tur_fc.py` içindeki iki blok ağa **çıkmaz**, bilerek:

- **Nabız kablosu** sentetik satırla sürülüyor. Gerçek çağrıda model kısa
  düşünürse `thinking_tokens` hiç gelmez; test yeşil yanar ama kablo kopuk
  olabilir. Panelin dakikalarca ölü görünmesinin sebebi tam da o kabloydu (§8b),
  o yüzden şansa bırakılmıyor.
- **Sözleşme maddeleri** metin olarak aranıyor. Ölçülerek seçildiler (§8c);
  biri kazara silinirse davranış sessizce eski hâline döner.

**Test edilmeyen:** ~~widget'ların kendisi~~ — **bu satır artık doğru değil,
bkz. §18.3.** `QT_QPA_PLATFORM=offscreen` ile `freecadcmd` içinde
`QApplication` kurulabiliyor ve widget'lar gerçekten oluşturulup
ölçülebiliyor; `test_panel_fc.py` yerleşimi gerçek piksellerle sınıyor.
Hâlâ test edilmeyen şey **boyama ve tıklama akışı**: "düğme gerçekten
görünüyor mu, rengi doğru mu" insan gözü gerektiriyor.

Güncel test tablosu §18.4'te (249 kontrol); yukarıdaki tablo ilk dört testi
gösteriyor.

**Katman kuralı bunu mümkün kılıyor:** `context/` ve `execution/` QtWidgets
görmez, `transport/` yalnızca QtCore kullanır. Yalnızca `ui/` widget'a dokunur.
Bu kural bozulursa başsız test imkânı kaybolur.

---

## 13. Bir sonraki kişiye/yapay zekâya notlar

- **Ölçmeden şema varsayma.** CLI'ın akış biçimi de, Printables GraphQL'i de
  (önceki projede) hata mesajları ve gerçek çıktı okunarak çıkarıldı. Bu
  projede `tests/` altındaki probe yaklaşımı bilinçli bir alışkanlık.
- **"Testim geçti" yetmez, testin doğru koşulu kurduğunu doğrula.** §7.1 tam
  olarak bu yüzden gözden kaçtı.
- **FreeCAD sessizce başarısız olur.** Bir şey görünmüyorsa önce `stderr`'e bak
  (`Start-Process ... -RedirectStandardError`), Report view yetmez.
- **"Yavaş" ile "donmuş"u karıştırma, önce ölç.** §8b'de altı dakikalık bir
  "hata" aslında sağlıklı bir 166 saniyeydi; asıl kusur, panelin ilerlemeyi
  göstermemesiydi. Şikâyet nereye işaret ediyorsa oraya değil, ölçüme bak.
- **Gerekçen çürüdüyse kararını ters çevir.** §8b'de "soru sormasın" demiştim,
  §8c'de tam tersini yaptım — çünkü ölçüm, gerekçemin (soru yavaşlatır) yanlış
  olduğunu gösterdi: yavaşlatan şey belirsizlikti. Eski kararın gerekçesini
  yorumda saklamak bunu mümkün kılıyor; yalnızca kuralı yazsaydın neyin
  çürüdüğünü göremezdin.
- **Kullanıcıya çalışmayan bir ayar sunma.** `MAX_THINKING_TOKENS` denendi,
  CLI dinlemiyor (2000 verildi, 12.000 düşünüldü). Arayüze konmadı; işe
  yaramayan bir düğme, olmayan bir düğmeden kötüdür.
- **`3D_Models` hattına dokunma.** O proje çalışıyor; CADdy onun yerine geçmiyor.

---

## 14. AYRI EKLENTİ — tartışıldı, kararlar alındı, **yazıldı** (adı: Monkey)

Bu bölüm bir *devir notuydu*: kullanıcı açıkça *"eklentiyi yapma daha onu
tartışalım"* demişti. **Tartışma 2026-08-20 oturumunda yapıldı**, kararlar
§14.4'te, ölçümler §14.5'te.

**Aynı oturumda ilk sürüm de yazıldı.** Kullanıcı: *"şu an CADdy'den
memnunum, diğer eklentiye geçelim, onun adı da Monkey olsun."* Uygulama
ve karşılaşılan tuzaklar **§15**'te.

### 14.1 İstek nereden çıktı

Kullanıcının cümlesi: *"benim yaptığım CAD modelini istediğim 3D yazıcı
modeline dönüştürse olmaz mı"* — ve devamı: *"eskiden direkt chatte
yapıyorduk, onu bu işe de entegre edebilir miyiz, maliyeti ne olur; onu da
ayrı yapabiliriz CADdy tarzı."*

İstek **iki parçaya bölündü**, bu ayrım kasıtlı:

| | nereye | durum |
|---|---|---|
| **Birinci satır** — CAD → baskıya hazır dosya (.3mf/.stl/.step), kalite seçimi, manifold kontrolü | **CADdy'ye girdi** | **bitti**, bkz. §8g |
| **Gerisi** — model arama/indirme, dilimleme, yazıcıya gönderme | **ayrı eklenti** | **yapılmadı** |

Bölmenin gerekçesi: birinci satır zaten *modelin yazabildiği koddu*, eksik
olan tek şey onu önermesiydi — yani bir sözleşme maddesi yetti. Geri kalan
üçü ise başka bir şey: ağ erişimi, üçüncü taraf lisansı, harici ikili
(slicer), ve fiziksel bir cihaza komut. Aynı panele sıkıştırılırsa CADdy'nin
şu anki dar ve doğrulanabilir yüzeyi bozulur.

### 14.2 Kapsam — ayrı eklentiye giren üç iş

1. **Model arama ve indirme** — Printables · Thingiverse · step.parts.
   Lisans görünür olmalı, **ND türev üretmeyi kapatır**.
2. **Dilimleme** — gerçek slicer CLI'ı (PrusaSlicer/OrcaSlicer) çağırıp
   `.gcode` üretmek, üretilen G-code'u yazdırmadan önce statik doğrulamak.
3. **Yazıcıya gönderme** — Bambu Lab LAN üzerinden FTPS/MQTT.

### 14.3 Sıfırdan başlanmıyor — hazır olan ne var

`C:\Users\USER-1\Desktop\3D_Models` altında bu işlerin **çalışan** hâli var;
yeni eklenti onların yerine geçmemeli, onları sarmalı:

| var olan | ne yapıyor |
|---|---|
| `tools\model-ara.py` | arar, **indirmez**, lisans sütunu basar |
| `tools\model-indir.py` | indirir, `kaynak\` altına koyar, `KAYNAK.md` yazar, manifold raporu verir |
| `tools\mesh-uret.py` · `mesh-kontrol.py` · `mesh-to-step.py` | mesh hattı |
| `bambu-labs` skill'i | LAN FTPS/MQTT ile baskı işi |
| `gcode` skill'i | slicer CLI keşfi, dilimleme, statik G-code doğrulaması |
| `step-parts` skill'i | satın alınabilir standart parça kataloğu |

Yani asıl iş **yeni yetenek yazmak değil, var olan hattı FreeCAD içinden
erişilebilir kılmak.** Bu, tartışmanın çıkış noktası olmalı.

### 14.4 Verilen kararlar (2026-08-20 oturumu)

§14.4 önceden bir **soru listesiydi**; sorular kullanıcıya soruldu ve
cevaplandı. Öneriler zaten yazılıydı, hepsi kabul edildi — ama gerekçeleri
burada duruyor, çünkü biri çürürse kararın da düşmesi gerekir (§13).

| # | Karar | Gerekçe |
|---|---|---|
| 1 | **Ayrı eklenti**, ortak kod **kopyalanır** | Ayrı `Mod\` klasörü, ayrı workbench, ayrı günlük. Paylaşılan pakete taşımak CADdy'nin çalışan dosyalarına dokunmayı gerektirirdi — regresyon riski. Kopyanın bedeli iki yerde bakım; kabul edildi. |
| 2 | **İlk iş: model arama/indirme** | Üçünün en ucuzu ve en az riskli olanı; ölçüldü, uçtan uca **~1.4 sn** (§14.5). Dilimleme ve yazıcıya gönderme sonraki turlara. |
| 3 | **Düz arayüz; AI yalnızca öneri verir** | `--tools ""` kararı (§6) **aynen kalır**. AI sürseydi indirme ve dilimleme dosya yazacaktı, güvenlik sınırı gevşerdi. Düğmeler işi yapar, AI "şunu ara" der. |
| 4 | **İndirilen model belgede *mesh* kalır, açıkça işaretli** | Aşağıda, en önemli karar. |
| 5 | Yazıcıya gönderme **çift kapı + dry-run varsayılan** | Fiziksel ve geri alınamaz. En az CADdy'deki çift basış onayı (§8d) kadar sert. |
| 6 | Lisans disiplini **taşınır**: `KAYNAK.md` olmadan indirme bitmiş sayılmaz | Belgeye gömülen bir modelin nereden geldiği kaybolmamalı. |
| 7 | **Maliyet: ek para yok** | Arama/indirme/dilimleme/gönderme tamamen yerel. AI tarafı yine abonelikten. Ek maliyet yalnızca bağlam kullanımı. |

#### Karar 4 — ölü mesh çelişkisi ve neden "öyleymiş gibi yapmıyoruz"

Burada gerçek bir çelişki var ve gizlenmemeli: §11 diyor ki *"KAÇINILAN:
`Part.show(...)` / `Part::Feature` — ölü şekil, geçmiş yok."* Ama **indirilen
bir STL doğası gereği geçmişsizdir.** Kural, AI'ın *ürettiği* koda konmuştu;
başkasının ürettiği bir mesh'e uygulanamaz.

Ölçüldü: `makeShapeFromMesh` 0.11 sn'de katı üretiyor. Yani "STEP'e çevirelim"
teknik olarak mümkün. **Elendi** — çünkü çıkan şey parametrik *değil*, sadece
parametrik *görünüyor*: tesselasyondan gelen binlerce düz yüzey, düzenlenebilir
geçmiş yok. Kullanıcı onu Pad'miş gibi düzenlemeye kalkar ve duvara çarpar.

> **Karar: mesh, mesh olarak durur ve öyle işaretlenir.** AI onu düzenlemeye
> çalışmaz; **etrafına** parametrik geometri kurar. Yalan söyleyen bir dönüşüm,
> dürüst bir sınırdan kötüdür — §13'ün "çalışmayan bir ayar sunma" maddesinin
> geometri hâli.

Not: bu çelişki **step.parts için yok**. O kaynak zaten STEP döndürüyor
(ölçüldü, §14.5) ve STEP CAD hattına doğrudan girer. İki kaynak iki farklı
kalitede — arayüz bunu göstermeli, "hepsi aynı" gibi davranmamalı.

### 14.5 Ölçüldü — hat FreeCAD içinde çalışıyor, üç tuzakla

§14.3 *"asıl iş yeni yetenek yazmak değil, var olan hattı FreeCAD içinden
erişilebilir kılmak"* diyordu. **Doğrulandı**, ama varsayımla değil ölçümle
(FreeCAD 1.1.1 / Python 3.11.14, 2026-08-20):

| ne | sonuç |
|---|---:|
| `requests` gömülü Python'da | **var** (2.32.5) |
| `kaynak_lib.py` import | **0.07 sn**, tek satır değişiklik gerekmeden |
| Printables GraphQL ucu **hâlâ canlı** | arama 0.43–0.86 sn |
| İndirme bağlantısı (süreli) | 0.41 sn |
| Gerçek indirme | 0.39 sn |
| `Mesh.insert` → belgede nesne | **0.02 sn** |
| `isSolid` · `hasNonManifolds` · `hasSelfIntersections` | anlık |
| **uçtan uca** (ara → link → indir → belgede) | **~1.4 sn** |
| `step_parts_ara` (venv python'ıyla) | 1.91 sn, **STEP** döndürüyor |

#### Tuzak 1 — `sys.executable` gömülü yorumlayıcıda yalan söyler

```
cagrilacak : C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe
hata       : unrecognised option '--limit'
```

`step_parts_ara/indir` ve `model-indir.py`'nin `_calistir()`'i alt süreci
`sys.executable` ile açıyor. FreeCAD içinde bu FreeCAD'in kendisi; argümanı
FreeCAD'in kendi ayrıştırıcısı yiyor, betik hiç çalışmıyor.

**Çözüm ölçüldü ve tuttu:** çağrı sırasında `sys.executable` geçici olarak
`3D_Models\.venv\Scripts\python.exe`'ye çevriliyor → 5 sonuç, 1.91 sn.
`3D_Models`'e **dokunulmuyor** (§14.6). Bedeli: venv'in varlığına bağımlılık —
yoksa step-parts uyku moduna düşmeli, Thingiverse'in token yokken yaptığı gibi
(hata vermeden, sebebini söyleyerek).

#### Tuzak 2 — 95 MB kapısı buraya ait değil

İlk denenen vazo modelinin **altı STL'i de 126 MB**; kapı hepsini reddetti.
O sınırın gerekçesi `3D_Models`'e özgü: *"dosyalar git'e commit edildiği için"*.
FreeCAD belgesine gömülen mesh git'e girmiyor, yani gerekçe burada geçersiz.

Ama **sınırsız bırakmak da yanlış**: 126 MB'lık bir STL'i belgeye gömmek
FreeCAD'i dizlerinin üstüne çöktürür. Sınır kalır, gerekçesi değişir —
git değil, **üçgen sayısı ve belge boyutu**. Değeri ölçülerek seçilecek.

#### Tuzak 3 — boş arama hata değil

`"m3 screw holder bracket"` → **0 sonuç**, istisna yok. `"keychain"` → 15.
Arayüz boş sonucu hata gibi göstermemeli; "bulunamadı, sorguyu genelleştir"
demeli. Kaynak başına da ayrı: §14.3'teki `ara()` bir kaynak patlarsa
diğerleriyle devam ediyor — panelde hangisinin sustuğu görünmeli.

#### Probe'un kendi dersi

İlk probe **sessizce öldü**: `Mesh` import edilince `print()` kayboldu (§7.6)
ve rapor yalnızca sonda yazıldığı için erken çıkışta hiç yazılmadı. §7.6'nın
kuralı yetmiyormuş — **rapor her satırda diske yazılmalı**, sonda değil.

### 14.6 Değişmeyen kısıtlar

Yeni eklenti de bunlara uyar — bunlar tartışmaya açık değil:

- **Para harcanmaz.** API anahtarı yok, mevcut Claude Code aboneliği kullanılır.
- **Oturum başına tek günlük dosyası.**
- **İş bitince dur ve raporla**, kendiliğinden bir sonraki işe geçme.
- **`3D_Models` deposuna dokunulmaz** — oradaki hat çalışıyor, sarılır,
  değiştirilmez.

---

## 15. MONKEY — ikinci eklenti, ilk sürüm

CADdy'nin kardeşi. CADdy AI ile **parametrik geometri üretir**; Monkey
**başkasının ürettiği hazır modeli** bulur, indirir ve belgeye lisansıyla
birlikte koyar. Kararlar §14.4'te, onları destekleyen ölçümler §14.5'te.

### 15.1 Nerede duruyor — CADdy'nin İÇİNDE

Kullanıcı: *"Monkey klasörünü CADdy klasörünün içine at, tamamen Desktop'ta
ayrı olmasın."*

```
Desktop\CADdy\            <- Mod\CADdy junction'i buraya
  caddy\ ...
  Monkey\                 <- Mod\Monkey junction'i buraya
    package.xml  InitGui.py  Init.py
    monkey\  resources\  tests\
```

**Neden çalışıyor:** FreeCAD `Mod\*` seviyesindeki her klasörü ayrı eklenti
sayar, `Mod\*\*`'a bakmaz. `Mod\CADdy\Monkey` iki seviye derin olduğu için
CADdy'nin bir parçası gibi taranmaz; `Mod\Monkey` ayrı junction'la doğrudan
görünür. İki `InitGui.py` birbirinden habersiz çalışır.

Yerleşim değişikliği **hiçbir kod düzeltmesi gerektirmedi** — bütün yollar
zaten göreliydi (`co_filename`, `Path(__file__).parent.parent`). Test bunu
doğruladı: taşımadan sonra ikon yolu `...\CADdy\Monkey\resources\...` olarak
doğru çözüldü.

Yan etki: Monkey, CADdy'nin **git deposuna** girdi. Tek repo, iki eklenti.

### 15.2 Katman ve thread — burada CADdy'den AYRILIYORUZ

CADdy'nin en zarif kararı `QProcess`'ti: Qt'nin olay döngüsü sayesinde hiç
worker thread yok (§5). **Monkey'de o numara işe yaramıyor** — `requests`
senkron bir kütüphane, `QProcess` değil.

Ölçüldü: arama 0.4–1.9 sn (sınırda tolere edilebilir), ama indirme 50 MB'a
kadar çıkabiliyor — dakikalar. GUI thread'inde yapılırsa FreeCAD tamamen
donar. Bu yüzden ağ işi `QThreadPool`'da.

> **Kural pazarlıksız: worker thread ağ ve disk yapar, FreeCAD BELGESİNE
> ASLA DOKUNMAZ.** OpenCascade tek thread'li; belgeye başka thread'den
> dokunmak sert çökme.

İş bölümü zaten modül sınırlarıyla örtüşüyor: `kaynak.py` (ağ/disk) thread'de,
`belge.py` (FreeCAD) GUI thread'inde. Qt'nin otomatik bağlantısı sinyalleri
GUI thread'ine taşıdığı için `_indirme_bitti` yuvası GUI thread'inde çalışır —
belgeye orada dokunuluyor. `QRunnable` seçildi, `QThread`+`moveToThread`
değil: iş kısa ömürlü, durum tutmuyor, sonucu tek sinyalle dönüyor.

Havuz **tek thread'e** sabitlendi: kullanıcı tek arama bekliyor, eşzamanlı
istekler hem karışıklık hem kaynak sitesine gereksiz yük.

### 15.3 Yakalanan hata: `setActiveTransaction("")` işlemi KAPATMAZ

İlk yazımda işlemi şöyle kapatıyordum:

```python
App.setActiveTransaction("")     # YANLIS - islemi kapatmaz
```

Test `UndoNames` boş döndü. Doğrusu:

```python
App.closeActiveTransaction(False)   # islensin
App.closeActiveTransaction(True)    # iptal -> tek temiz geri alma
```

`setActiveTransaction("")` yalnızca *"sıradaki işlemin adı"* ayarını
temizliyor. §7.8 `persist=True`'yu anlatıyordu ama **kapatma çağrısını**
yazmıyordu; CADdy'nin `executor.py`'sinde doğrusu zaten vardı.

**Ders:** MANTIK'ta bir mekanizmanın yarısı yazılıysa diğer yarısı sessizce
kaybolabiliyor. Açılış ve kapanış birlikte yazılmalı.

### 15.4 "Testim kaldı" da hemen kod hatası demek değil

§13 *"testim geçti yetmez, testin doğru koşulu kurduğunu doğrula"* diyor.
Bu oturumda **tersi** iki kez oldu — üç kırmızıdan ikisi testin kendi hatasıydı:

| kırmızı | gerçek sebep |
|---|---|
| *"kaynak.py QtWidgets görmüyor"* KALDI | Test dosyada kelimeyi arıyordu; kelime iki modülün de **docstring'inde** geçiyor (*"bu modül QtWidgets GÖRMEZ"*). Kod doğruydu. Doğru koşul: **import satırlarına** bakmak. |
| *"geri alma girdisi oluştu"* KALDI | Konsol modunda `doc.UndoMode` varsayılan **kapalı**, GUI'de açık. Test onu kurmadan "tek Ctrl+Z"yi ölçemez. |
| *"UndoNames boş"* | **Gerçek hataydı** — §15.3. |

Yani kırmızı bir test üç şeyden birini söyler: kod bozuk, koşul yanlış
kurulmuş, ya da iddia yanlış. Üçünü ayırmadan düzeltmeye kalkmak, çalışan
kodu bozmanın en kısa yolu.

Üçüncü örnek CADdy tarafında çıktı: `test_yukleme_fc.py` üst şerit
komutlarının kayıtlı komutlarla **eşit** olmasını istiyordu. Kullanıcı üst
şeridi daraltınca test kırmızı yandı — ama kod doğruydu, **iddia** eskimişti
(§8h). Eşitlik yerine **alt küme** kontrolüne çevrildi.

### 15.5 Uygulanan kararlar — nerede yaşıyorlar

| karar (§14.4) | kod |
|---|---|
| Ortak kod **kopyalanır** | `monkey/log.py`, `monkey/config.py`, `monkey/ui/ust_menu.py` — CADdy'den kopya, başlıklarında kopya olduğu yazıyor |
| Mesh **mesh kalır, işaretli** | `belge.py`: `indirilen_` Label öneki **+** nesne üzerinde salt-okunur `Monkey*` özellikleri |
| step-parts **venv python'ıyla** | `kaynak._venv_executable()` — dar yama, `finally` ile geri alınıyor |
| Provenans **pazarlıksız** | `belge.kaynak_md_yaz()` + nesne özellikleri; belge başkasına gönderilse bile kaynak kaybolmuyor |
| Boş arama **hata değil** | `AramaSonucu.durumlar` — kaynak başına durum panelde yazılı |
| Uyku modları **sebebiyle** | venv yoksa step-parts, token yoksa Thingiverse: patlamıyor, ne yapılacağını söylüyor |

**İki katmanlı işaret** bilinçli: Label öneki insanın ağaç görünümünde
**anında** gördüğü şey; nesne özellikleri belge kaydedilince **kalıcı** olan
şey. Biri UI, diğeri kayıt — birbirinin yerine geçmiyorlar.

ND lisansı **indirmeyi engellemiyor**, ayrı bir onay kutusu istiyor: ND
"indirme" değil "değiştirme" yasağı, kullanıcı modeli olduğu gibi basmak için
indirebilir. Boyut sınırı ise gerçekten engelliyor (§14.5 tuzak 2).

### 15.6 Test durumu

Üç test, hepsi `freecadcmd` ile, toplam **123 kontrol**:

| test | kontrol | kapsam |
|---|---:|---|
| `test_monkey_fc.py` | 62 | Katman kuralı, `package.xml` FreeCAD'in kendi ayrıştırıcısından, InitGui kapsam tuzağı (§7.1 — fonksiyon içinden **argümansız** exec ile), venv yaması ve geri alınması, boyut kapısı, mesh işaretleme, provenans, tek Ctrl+Z, gerçek Printables araması, uyku modları, **işlem günlüğü** |
| `test_sorgu_fc.py` | 42 | Türkçe normalizasyon (`GEMİ`→`gemi` büyük-I tuzağı), çeviri, İngilizce sorguya dokunmama, alaka filtresi (**ölçülen gerçek vakayla**: `Gem rock`/`Semi-automatic` elenir, `Gemide`/`Gemisi` tutulur), sıralama, gerçek `"gemi"` araması |
| `test_panel_fc.py` | 19 | Panel **import edilebiliyor mu**, Qt sabitleri gerçekten var mı, `_Is` hem başarıyı hem hatayı sinyalle dönüyor mu |

`test_panel_fc.py` §12'nin *"widget'lar test edilmiyor"* dürüstlüğünü
değiştirmiyor — GUI yokken widget üretilemez. Yaptığı şey **"panel hiç
açılmıyor" sınıfındaki** hataları (import hatası, olmayan Qt sabiti, yanlış
sinyal adı) kullanıcıdan önce yakalamak. En kritik kontrolü: `_Is` içinde
kaçan istisna Qt tarafından **yutulursa** panel sonsuza kadar "aranıyor"
derdi; test her iki yolun da sinyal döndüğünü doğruluyor.

Rapor **her satırda** diske yazılıyor (`tests/_son_rapor.txt`,
`_son_panel.txt`) — §14.5'teki probe dersi doğrudan uygulandı: sonda yazan
bir rapor erken çıkışta hiç yazılmıyor.

**Test edilmeyen:** widget'ların görünümü ve thread modelinin gerçek
davranışı. Ağ işi sırasında GUI'nin donup donmadığı ancak panelde görülür.

### 15.7 Arama kalitesi — üç şikâyet, üçü de ölçüldü

Kullanıcı ilk gerçek kullanımda üç şey söyledi. Hepsi haklıydı, ama
**çözümlerinden biri ilk tahminimin tam tersi çıktı.**

#### Şikâyet 1: *"gemi yazdıysam sadece gemiye bak, gem'e değil"*

Ölçüldü — `printables_ara("gemi")` gerçek yanıtı:

```
1100802  gemi                                    ind=35     dogru
1328313  Yelkenli Gemi Lithophane                ind=17     dogru
1285424  Gemide Korsan Kadin Lithophane          ind=14     dogru
 399607  Complete Cherry MX stem keycap set...   ind=9709   ALAKASIZ
 115590  'Gem rock' mount for ... dragon         ind=4199   ALAKASIZ
 947003  Semi-automatic cable wrapper            ind=1579   ALAKASIZ
```

Printables'ın kendi araması bulanık: `gem` ve `semi` eşleşmelerini de
getiriyor ve bunlar **popüler oldukları için** listeyi ele geçiriyor.

Süzme kuralı **önek eşleşmesi**, tam kelime değil — çünkü *"Gemide"*,
*"Gemisi"*, *"Gemiler"* elenmemeli (Türkçe ekli hâller). *"Semi-automatic"*
`gemi` ile başlamadığı için elenir. İçeren mantığı seçilseydi `emi` yüzünden
geçerdi; onek mantığı elemektedir.

Emniyet: **filtre her şeyi elerse ham sonuç gösterilir.** Boş ekran alakasız
sonuçtan kötüdür ve kullanıcı göremediği şey için filtreyi suçlayamaz.

#### Şikâyet 2: *"ship olarak da İngilizce'de ara"*

Katalogun tamamı İngilizce; Türkçe sorgu yalnızca Türk kullanıcıların
yüklediği birkaç modeli buluyor. `"ship"` araması karşılaştırmalı olarak çok
daha iyi (Container Ship 5675 indirme vs `"gemi"` en iyisi 35).

Çeviri **sözlükle**, ağ ile değil: ücretsiz çeviri uçları anahtar ister ya da
güvenilmez, ve §14.6 *"para harcanmaz"* diyor. Sözlük **bilerek eksik** —
amaç bütün Türkçeyi çevirmek değil, 3B baskıda sık aranan nesneleri
yakalamak. Bulunamayan kelime olduğu gibi aranır, hata verilmez.

Kullanıcının eklemesi: *"İngilizce olanları Türkçeye çevirme, gerek yok."*
Çeviri zaten tek yönlü, ama birkaç kelime **hem sözlük anahtarı hem geçerli
İngilizce**: `tank`, `test`, `fan`, `stand`, `robot`. Bu yüzden sorgu
sözlüğün İngilizce tarafından bir kelime içeriyorsa hiç dokunulmuyor
(`"model ship"` → çevrilmez, `"gemi modeli"` → çevrilir).

**Çeviri yapıldığında panelde yazıyor** (*"İngilizce de arandı: ship"*).
Sessizce sorgu değiştirmek güven kırar.

#### Şikâyet 3: *"en çok indirilenden itibaren listele"* — ve TUZAK

İlk aklıma gelen çözüm yanlıştı. Printables'ın `ordering=popular`
parametresi var, ama **sorguyu neredeyse görmezden geliyor.** Ölçüldü,
`"ship"` için:

```
ordering=best_match          ordering=popular
  COS - the Container Ship     Dino-Clip Mechanical CAM Chip-Clip
  EMMA - a Container Ship      Rocinante from the Expanse
  Cargo Ship                   Shipping Container
```

`rating` ve `makes_count` da aynı şekilde bozuluyor — `chip`/`ship`
karışıyor ve popüler olan öne geçiyor.

> **Karar: kaynaktan her zaman `best_match` istenir** (alaka orada iyi),
> **sıralama bizde** indirme sayısına göre yapılır. Yani "en çok indirilen"
> = *"alakalılar arasında en çok indirilen"* — kullanıcının kastettiği de bu.

Bu §13'ün *"ölçmeden şema varsayma"* maddesinin taze bir örneği: parametrenin
adı (`popular`) ne yaptığını söylüyor sanmak yanlıştı.

#### Yan bulgu: Thingiverse lisans vermiyor

Token tanımlandı ve çalışıyor. Ama ölçüldü: **arama yanıtında `license` ve
`download_count` alanları boş geliyor** (`lisans='?'`, `indirme=0`).

Bu sessiz geçilemez — ND kontrolü lisans bilinmiyorsa **hiç tetiklenmez**,
yani kullanıcı ND bir modeli uyarısız indirir. Panel artık *"Lisans
bilinmiyor — bu kaynak arama yanıtında lisans vermiyor, indirmeden önce
model sayfasına bak"* diyor. Bilmediğimizi söylemek, bilmiyormuş gibi
davranmaktan iyidir.

### 15.8 İşlem günlüğü — sohbet değil, iş kaydı

Kullanıcı: *"Monkey log tutsun, şu an geliştirme aşamasındayız, her test
değerli."*

CADdy'nin `sohbet_log.py`'si bir **konuşmayı** kaydeder; Monkey'de konuşma
yok (karar 3). Kaydedilen şey başka: hangi sorgu, hangi varyantlar, kaç
sonuç, **hangi kaynak sustu ve neden**, ne indirildi, belgeye girdi mi.

CADdy'de olmayan iki alan bilinçli olarak eklendi:

- **sorgu genişletmesi** kayıtlı — sonuç alakasız gelirse suçlu çeviri mi
  kaynak mı ayırt edilebilsin
- **elenen sonuç sayısı** kayıtlı — alaka filtresi fazla mı kesiyor?

Printables resmî olmayan bir uç ve şeması haber vermeden değişebilir; bir
arama bozulduğunda elde *"ne soruldu, ne döndü"* kaydı olmalı.

CADdy'nin kuralı aynen devralındı: **günlük hatası işi durdurmaz.** Test
bunu `Z:\olmayan\surucu` yoluyla doğruluyor — sessizce kapanıyor, bir kez
uyarıyor, panel çalışmaya devam ediyor.

### 15.9 Henüz yapılmayan

- **Dilimleme** (PrusaSlicer/OrcaSlicer CLI) — §14.2'nin 2. işi
- **Yazıcıya gönderme** (Bambu LAN) — §14.2'nin 3. işi, çift kapı + dry-run
  kararı verildi ama kod yok
- **AI'ın öneri vermesi** — karar 3 "düz arayüz + AI yalnızca öneri" idi;
  ilk sürümde AI **hiç yok**, sadece düz arayüz. Bu bilinçli: arama/indirme
  tek başına çalışır durumda olsun, AI sonra eklensin.
- **Tercihler sayfası** — ayarlar `config.py`'de var ama arayüzü yok;
  `DepoDizini` şu an ancak `MODELS_3D_DIR` ortam değişkeniyle değiştirilebiliyor.
  `Ceviri` ve `AlakaFiltresi` de aynı durumda — kapatılabilir tasarlandılar
  ama kapatma düğmeleri yok.
- **Thingiverse lisans/indirme** — arama yanıtı bu alanları vermiyor (§15.7).
  Her sonuç için ayrı bir detay çağrısı gerekir; N sonuç = N istek, pahalı.
  Şimdilik "bilinmiyor" diye işaretleniyor. Çözülürse ND kapısı o kaynakta
  da çalışır.
- **Çeviri sözlüğü küçük** — `sorgu.SOZLUK` yaklaşık 150 kelime. Genişletmek
  tek satırlık iş; yanlış çeviri eklemek ise **alakasız sonuç üretir ve
  filtre onu doğru sanıp geçirir**, o yüzden emin olunmayan kelime eklenmiyor.

---

## 16. CADdy kalite turu — günlükten ölçülüp uygulananlar

Kaynak: `caddy_gelisim.txt`, 21 oturum günlüğünün betikle ayrıştırılması.
O dosyanın en önemli bulgusu bir *olumsuzlama*: **hız artık darboğaz değil**
(medyan tur 22.4 sn, 120 sn üstü tur yok). Yani optimize edilecek şey süre
değil, **turların boşa gitmesi**. Aşağıdakiler o boşa giden turlara göre
seçildi.

Kullanıcının tek şartı vardı: *"öneri fena değil ama kalite düşmesin."*
Bu yüzden aşağıda **yapılmayanlar da yazılı** — bazıları benim kendi
önerimdi ve incelenince kaliteyi düşürdüğü görüldü.

### 16.1 Yapılanlar

| İş | Nerede | Kapattığı kayıp |
|---|---|---|
| Boolean sonrası kaynakları gizleme reçetesi | `workspace/CLAUDE.md` | 3 |
| Mesh dışa aktarımın iki adımı | `workspace/CLAUDE.md` | 7 |
| İthal katıda `isValid()` kontrolü | `workspace/CLAUDE.md` | 4, 8 (kısmen) |
| Kapsam belirsizliği maddesi | `transport.SISTEM_SOZLESMESI` | 2 |
| Görsel onay turunun kısaltılması | `transport.SISTEM_SOZLESMESI` | 5 |
| **Seçim bağlamının zenginleştirilmesi** | `context/serializer.py` | 1 |

### 16.2 En büyük iş: seçim bağlamı

Ölçülen kayıp şuydu: kullanıcı 3B'de bir yüz seçip *"bunu"* diyor, modele
giden tek bilgi `alt=Face7`. Face7'nin düzlem mi silindir mi olduğu, nereye
baktığı, yarıçapı — hiçbiri yok. Model tahmin ediyor, yanlış tahmin bir tur
daha yiyor.

Artık giden satır şu:

```
Pad (PartDesign::Pad) label='Boss'  bbox=20x20x10 mm @(0,0,0) pos=(0,0,5)
  alt=Face7 cylinder r=4 axis=(0,0,1) area=75.4 tiklanan=(12,0,5)  <- Pocket
```

`cylinder r=4` bir 8 mm delik demek; `normal=(0,0,1)` "daha derin"in hangi
yön olduğunu söyler. Bunlar tahmin edilecek değil, **okunacak** şeyler.

**Bütçe davranışı da değişti** ve asıl düzeltme burada. Eski sürüm metni
sondan kesiyordu — yani sınıra dayanıldığında önce nesne listesinin kuyruğu,
sonra gerekirse **seçimin kendisi** kırpılıyordu. En değerli bayt, ilk atılan
bayttı. Yeni davranış: başlık ve seçim asla kırpılmaz, kırpma yalnızca nesne
listesinden ve alaka sırasına göre yapılır (seçili > seçimin komşuları >
gerisi), ve **kırpıldığı söylenir**. Aynı öncelik içinde en eski nesne
atılır: belgenin sonu genelde üzerinde çalışılan yerdir.

### 16.3 Testin bulduğu gerçek hata

Bütçe 1200 istendi, **1232 karakter üretildi.** Sebep: "*N nesne kırpıldı*"
notunun kendisi hesaba katılmamıştı — bütçeyi aşmamak için eklenen satır
bütçeyi aşıyordu. Aynı sınıftan ikinci bir hata da vardı: bütçe tamamen
dolduğunda devreye giren kaba kesme, kestiği yere `… (baglam kirpildi)`
kuyruğunu **ekliyordu**, yani emniyet ağı da sınırı aşıyordu.

Ders, §15.3'ün aynısı: *bir mekanizmanın maliyeti hesaplanırken mekanizmanın
kendi maliyeti unutuluyor.* Şimdi not payı `_NOT_PAYI` olarak ölçülüyor ve
kaba kesme kuyruk uzunluğunu düşerek kesiyor.

### 16.4 Yapılmayanlar — ve neden

- **E1, görüntüyü küçük çözünürlükte gönder.** *Kendi önerimdi, reddedildi.*
  Görsel kontrolün ölçülen değeri gerçek: model kendi hatasını yakalıyor. Ama
  yakaladığı şey **ince kusur**; resmi küçültmek maliyeti düşürürken kontrolü
  işe yaramaz hâle getirir. Ucuzlatılan şey bu yüzden görüntü değil, **onay
  turunun sözü**: resim doğruysa tek satır, planı tekrar etme, kodu tekrar
  yazma.
- **B2, "ara nesne disiplini" maddesi.** Somut tarif değil, üslup öğüdü.
  `CLAUDE.md` her turda bağlama giriyor; içine konan her satır geri kalanı
  seyreltir. **Tarif konur, öğüt konmaz.** Tek cümlelik hâli, ait olduğu
  boolean reçetesinin altına iliştirildi.
- **C'nin genel hâli.** Öneri *"istek iki türlü okunuyorsa kod yazma"* idi.
  Ama sözleşmede bunun eşdeğeri **zaten vardı** ve günlüklerde %12
  tetikleniyordu. Ölçüm şunu gösteriyor: **genel öğüt tetiklenmiyor, adı
  konmuş desen tetikleniyor.** Kayıp tek bir kalıptı — kapsam belirsizliği
  (*"sadece en üstteki baş kalsın"*), 5 turluk zincire mal oldu. Madde o
  desenin adıyla yazıldı.
- **D, panelde "dosya veremezsin" uyarısı.** Ertelendi. Yapılırsa **oturumda
  bir kez** uyarmalı; her yol yapıştırmada çıkarsa kullanıcı okumayı bırakır
  ve uyarı değerini kaybeder.
- **F, bozuk BRep erken uyarı.** Sorun gerçek ama çözümü belirsiz ve her
  recompute'ta `check()` çalıştırmak yavaş olabilir — ölçülmeden yapılmaz.
  Şimdilik yalnızca kılavuz tarafı yapıldı (ithal katıda `isValid()`), kod
  tarafı yok.

### 16.5 Test

Yeni dosya: `tests/test_baglam_fc.py` — 34 kontrol. Serileştiricinin GUI'siz
sınanabilen parçalarını doğruluyor: yüz/kenar/köşe özeti, yerleşim,
komşuluk, bütçe kırpması, aşırı küçük bütçe, boş belge, bozuk alt-eleman adı.

Konsolda `FreeCADGui` yok, yani `Gui.Selection` erişilemiyor: `_secim()`
uçtan uca sınanamıyor. Onun yerine **beslediği parçalar** doğrudan sınanıyor
— asıl iş onlarda. Bu, "test yeşil ama kablo kopuk" riskinin bilinen bir
örneği (§12'deki nabız notunun aynısı).

Sözleşmeye eklenen üç madde de `test_tam_tur_fc.py`'ye kontrol olarak
girdi. Gerekçe §15.3 ile aynı: **yazılmamış olan sessizce kaybolur.**

| Test | Kontrol |
|---|---|
| `test_yukleme_fc.py` | 34 |
| `test_executor_fc.py` | 18 |
| `test_initgui_kapsam.py` | 9 |
| `test_baglam_fc.py` (yeni) | 34 |
| `test_tam_tur_fc.py` (gerçek tur) | 79 |
| **toplam** | **174** |

Yan bulgu: `test_initgui_kapsam.py`'nin başlığı *"FreeCAD gerekmez,
`python` ile çalıştır"* diyordu. **Yanlış** — betik `InitGui.py`'yi gerçekten
çalıştırdığı için `FreeCAD` modülüne ihtiyacı var; sistem python'unda
`ModuleNotFoundError` veriyor, `freecadcmd`'de de olmuyor. Doğru yorumlayıcı
FreeCAD'in kendi `bin\python.exe`'si. Başlık düzeltildi.

---

## 17. Deterministik doğrulama — eksik olan ikinci katman

Kaynak fikir: **`earthtojake/text-to-cad`** (`skills/cad/references/
inspection-and-validation.md`). Kullanıcı o depoyu işaret etti, *"özellikle
operasyonel açıdan"* dedi. Deponun mimarisi CADdy'ye uymuyor — orada model
CLI araçları çağırıyor, CADdy'de modelin **hiç aracı yok** (§6, `--tools ""`).
Aktarılan şey mimari değil, **disiplin**.

### 17.1 Eksik olan neydi

O dosyanın ana cümlesi şu ayrımı kuruyor:

> *deterministic geometry checks decide pass/fail; mandatory snapshot review
> catches semantic errors the deterministic checks did not encode.*

CADdy'de **ikinci katman vardı, birincisi yoktu.** Görsel kontrol (§8e)
anlamsal hatayı yakalıyor — "kulak yanlış yere kondu", "parçalar birbirine
değmiyor". Yakalayamadığı şey **göze normal görünen bozuk topoloji**.

Eldeki kontrol `executor._yumusak_hatalar` idi: `isNull`, `isValid`,
`MustExecute`. İki yönden yetersizdi ve ikisi de ölçüldü.

### 17.2 Ölçüm: `isValid()` yalan söylüyor

text-to-cad iki uyarı veriyordu. **İkisini de FreeCAD 1.1.1'de denedim, ikisi
de doğru çıktı:**

```
Part.makeBox(10,10,10).reversed()
    isValid() -> True          <- topolojik olarak "geçerli"
    Volume    -> -999.9999     <- ama ters
```

Ters katı 3B'de **dünyada delik** gibi görünür ve üstüne kurulan her
boolean'ı bozar. `isValid()` onu geçirir; **yalnızca hacmin işareti**
yakalar.

```
Part.Compound([+1000 kati, -1000 kati]).Volume  ->  0.0
```

Yani **hacim asla toplanmaz**, katı katı bakılır. Toplama bakan bir kontrol
hiçbir şey görmez.

Üçüncüsü kendi ölçümüm — beş yüzlü kutu:

```
acik kabuk   isValid() -> True    isClosed() -> False    Solids -> 0
```

"Geçerli" ama katı değil: kesilemez, kaynaştırılamaz, basılamaz.

**Maliyet** (36 yüzlü katıda): `isValid` 0.043 sn, `isClosed` ~0,
`Solids`/`Volume` 0.001 sn, `BoundBox` ~0. `isValid` yüz sayısıyla büyüyor,
o yüzden hem süre hem nesne sayısı bütçeli (1.5 sn / 25 nesne).

### 17.3 İkinci boşluk: "değişen" nesne hiç kontrol edilmiyordu

Eski kod yalnızca **eklenen** nesnelere bakıyordu (`onceki`/`sonraki` küme
farkı). Ama çok yaygın bir tür — *"şu pad'i 3 mm uzat"* — **hiçbir nesne
eklemez**. O turlarda **hiçbir kontrol koşmuyordu.**

Çözüm `App.addDocumentObserver`. `Touched` bayrağına bakmak yetmezdi: kodun
kendi içinde `doc.recompute()` çağırması **serbest ve yaygın** (eskiz
oluşturup pad'lemek için gerekli) ve o recompute bayrakları temizliyor.
Gözlemci araya girmeden yakalıyor — ölçüldü, test bunu ayrıca doğruluyor.

Sızan bir gözlemci kullanıcının **her hareketinde** ateşler, o yüzden çözme
`finally` içinde. Geri çağrımlar istisna fırlatmıyor: FreeCAD'in sinyal
zincirinde çalışıyorlar.

Yan kazanç: bu, PLAN'daki **M5'in (DocumentObserver) ilk gerçek parçası**.

### 17.4 Dürüstlük kuralı — asıl aktarılan şey

Kaynak dosyanın en değerli cümlesi teknik değil:

> *Report only checks that were actually run or directly supported by tool
> output.*

Rapor bu yüzden **koşan** kontrolleri **koşmayanlardan** ayırıyor. Koşmamış
bir kontrol sessizce "temiz" sayılmıyor; adı sebebiyle birlikte modele
gidiyor:

```
dogrulama: 1 nesne, 0.00 sn
  kosan kontroller: bos sekil, topoloji gecerliligi, kati hacim isareti
                    (kati kati), kapali kabuk
  KOSMAYAN: kendiyle kesisme (BRep'te pahali; mesh disa aktarimda kosuyor)
  Ters: kati=1 hacim=-1000 mm3 bbox=10x10x10 mm
  BULGU Ters: ters kati — kati 1 hacmi negatif (-1000). isValid() bunu
              YAKALAMAZ; 3B'de dunyada delik gibi gorunur
```

Sözleşmeye eşlik eden madde de bunun içindir: model yalnızca raporun
desteklediğini iddia edebilir, ve *"doğrulandı / su geçirmez / basılabilir /
tolerans içinde / üretilebilir"* demek koşmuş bir kontrole dayanmak zorunda.
Bu, kaynak dosyadaki **"do not claim"** listesinin CADdy'ye uyarlanmış hâli.

### 17.5 Kurt masalı yapmama

Bir kontrol katmanının en kolay ölme biçimi yanlış alarm: model gerçek
bulguları da ciddiye almaz. İki önlem var.

- Katı üretmesi **beklenmeyen** tipler ayrı tutuluyor (`Sketcher::`,
  `App::Origin`, `Part::Part2DObject`, `PartDesign::Plane`…). Bir eskizin
  katısı olmaması kusur değil.
- Katı da kabuk da yoksa bu bir **ölçüm** satırı olarak yazılıyor, **bulgu**
  değil. Test bunu ayrıca sınıyor: boş eskiz ve parametrik kutu temiz
  dönmeli.

### 17.6 Kılavuza giren şeyler

`workspace/CLAUDE.md`'ye iki tablo eklendi. İkisi de tur kazandırmak için:

- **Varsayılanlar** — mm, XY/+Z, plastik kutu duvarı 2–3 mm, M3/M4/M5 boşluk
  deliği 3.4/4.5/5.5 mm, ısıl geçme 4.0/5.6/6.4 mm, kayan parça toleransı
  0.2–0.4 mm. Bunları sormak boşa tur; kaynak deponun *"default modeling
  assumptions"* bölümünün karşılığı.
- **Hata → ilk bakılacak yer** — fillet yarıçapı fazla büyük, boolean'ın
  girdisi zaten geçersiz, loft kesitlerinin nokta sayısı farklı, pad için
  eskiz kapalı değil. Kaynak deponun `repair-loop.md`'sinden.

### 17.7 Test

Yeni dosya: `tests/test_dogrulama_fc.py` — **40 kontrol**. Testin yapısı
biraz sıra dışı: önce **ön kabulleri** doğruluyor (*"isValid() gerçekten ters
katıya True diyor mu?"*), sonra bizim kontrolün onu yakaladığını. Sebep: bu
katmanın bütün varlık nedeni o ön kabul. FreeCAD bir gün `isValid()`'i
düzeltirse test bunu **ön kabul satırında** söyler, bulgu satırında değil.

| Test | Kontrol |
|---|---|
| `test_yukleme_fc.py` | 34 |
| `test_executor_fc.py` | 18 |
| `test_initgui_kapsam.py` | 9 |
| `test_baglam_fc.py` | 34 |
| `test_dogrulama_fc.py` (yeni) | 40 |
| `test_tam_tur_fc.py` (gerçek tur) | 82 |
| **toplam** | **217** |

### 17.8 Alınmayanlar

Depoda çok şey var; alınmayanların sebebi var:

- **`cad-viewer`, `snapshot`, `inspect` CLI'ları** — CADdy'nin modelinde
  araç yok ve olmayacak (§6). Karşılığı zaten var: 3B görünüm kullanıcının
  önünde duruyor, görsel kontrol resmi gönderiyor.
- **`build123d`** — CADdy'nin bütün amacı FreeCAD'in **kendi** parametrik
  ağacını bırakmak (§11). Ayrı bir modelleme kütüphanesi o ağacı üretmez.
- **`gcode` / `bambu-labs`** — dilimleme ve yazıcıya gönderme **Monkey'in**
  işi (§14.2), CADdy'nin değil. Oradaki *"dry-run, sonra execute"* deseni ve
  *"gerçek yazıcı profilini uydurma"* kuralı Monkey'e yazıldığında
  alınacak — §15.9'daki çift kapı kararıyla aynı yöne bakıyor.
- **Kendiyle kesişme kontrolü** — BRep'te ucuz değil, OCC'de boolean testi
  gerektiriyor. Mesh tarafında zaten koşuyor (§8g). Atlandığı **rapora
  yazılıyor**, sessizce geçilmiyor.

---

## 18. Panel yerleşimi: sağa kaçan metin ve çift ilerleme

Kullanıcının iki şikâyeti: *"sağ tarafa çok fazla scroll yapabiliyoruz,
runtime error'larda çok sağa gidiyor"* ve *"2 yerde düşünüyor yazısı var."*
İkisi de küçük görünüyor; birincisinin altından üç ayrı sebep çıktı.

### 18.1 Sağa kaçan metin — üç sebep, tek şikâyet

**Sebep 1: QLabel genişlik dayatıyor.** Sarma açık olsa bile QLabel
`minimumSizeHint().width()` değerini en uzun **bölünemez** parçaya göre
verir. Ölçüldü:

```
QLabel(r"C:\Users\USER-1\Desktop\CADdy\caddy\execution\executor.py")
    setWordWrap(True)
    minimumSizeHint().width()  ->  660 px
```

Dar bir yan panelde tek bir traceback yolu, bütün akışın asgari genişliğini
660 piksele çıkarıyordu; `QScrollArea` de buna uyup yatay çubuk açıyordu.

**Sebep 2: kod kartı `NoWrap`.** Kart uzun bir satırda kendi içinde sağa
kayıyordu — kullanıcı kodu okumak yerine kaydırıyordu.

**Sebep 3 — asıl olan:** asgari genişliği sıfırlamak yetmiyor. QLabel o uzun
yolu **bölemez**; satıra sığmayan parça sağdan taşar ve *görünmez olur*.
Kullanıcının ikinci cümlesi tam buydu: *"biraz sağa kayan metinleri
göremiyorum, sert limit ekle."*

Qt'de bunun tek doğru çözümü **`QTextOption.WrapAtWordBoundaryOrAnywhere`**:
önce boşluktan böl, olmuyorsa **karakterden** böl. Bu ayar **QLabel'da yok** —
`QTextDocument`'ı olan bir widget gerekiyor. `SaranEtiket` bu yüzden artık
etikete benzetilmiş bir `QTextEdit`: çerçevesiz, saydam, salt okunur, iki
kaydırma çubuğu da kapalı, yüksekliği içeriğe göre sabitlenmiş.

Ölçülen sonuç:

| Panel genişliği | Satır | En geniş satır |
|---|---|---|
| 600 px | 3 | 600 px |
| 400 px | 3 | 396 px |
| 220 px | 5 | 216 px |
| 140 px | 6 | 132 px |

Boşluksuz bir yol 140 pikselde altı satıra bölünüyor ve **hiçbir satır
taşmıyor**. Sert limit budur.

İki yan karar:

- **Tekerlek olayı yutulmuyor** (`wheelEvent` → `ignore()`). Yutulsaydı
  sohbeti kaydırırken imleç bir mesajın üstüne geldiğinde kaydırma dururdu —
  çözdüğümüz sorundan sinir bozucu.
- **Yükseklik içerikten hesaplanıyor**, `blockCount`'tan değil. Sarma açıkken
  bir mantıksal satır ekranda birkaç satır kaplıyor; blok saymak kartı kısa
  bırakır ve kodun altı kırpılır. Yani yatay taşmayı çözüp yerine **dikey**
  taşma koymuş olurduk. Kod kartında ölçüldü: 600 px'te 6 satır, 200 px'te
  **14** satır.

### 18.2 Çift ilerleme

*"düşünüyor · 27 sn · ~500 token"* hem sağ üstteki durum etiketinde hem
akıştaki satırda duruyordu. Akıştaki hâli kaldı: öğüt satırı (30/75/150 sn
eşikleri, §8b) da orada ve ikisi birbirini tamamlıyor. Üst etikette yalnızca
sayılar vardı.

**İkinci adımda etiket tamamen kaldırıldı.** Sayan saat gidince geriye
`çalışıyor…` kalmıştı; kullanıcı onu da istemedi ve haklıydı — durumu zaten
iki yer söylüyor: akıştaki ilerleme satırı ve Gönder/İptal düğmelerinin
etkin/pasif hâli. Üçüncüsü gürültü.

Kaybolmaması gereken tek şey **iptal geri bildirimiydi**: iptal kalıcı süreci
de öldürüyor, bu bir saniyeden uzun sürebiliyor ve o sırada ekranda hiçbir şey
değişmezse "tıklamadı mı" sanılıyor. O yüzden `iptal ediliyor…` akışa taşındı,
silinmedi. Test bunu ayrıca kontrol ediyor.

### 18.3 Ekransız GUI testi — yeni imkân

**`QT_QPA_PLATFORM=offscreen` ile `freecadcmd` içinde `QApplication`
kurulabiliyor ve widget'lar gerçekten oluşuyor.** Bu ölçüldü ve §12'nin
*"widget'ların kendisi test edilmiyor"* satırını **geçersiz kılıyor**: artık
ediliyor.

`tests/test_panel_fc.py` (31 kontrol) yerleşimi gerçek piksellerle sınıyor —
QLabel'ın 660 pikseli, sarma sonrası en geniş satır, kod kartının yüksekliği,
ilerleme yazısının tek yerde olduğu.

**İki tuzağa çarptım, ikisi de teste yazıldı:**

- **`show()` şart.** Gösterilmemiş bir `QAbstractScrollArea`'da `resize()`
  viewport genişliğini güncellemiyor. İlk yazımda genişlik ne olursa olsun
  aynı sayı çıktı ve **kodu bozuk sandım** — bozuk olan testti.
- **`print` testi öldürüyor.** Konsol kod sayfası (cp1254) `⏳` karakterini
  kodlayamıyor, `print` `UnicodeEncodeError` fırlatıyor ve betik tam orada
  sessizce ölüyor. §14.5'teki dersin aynısının yeni bir yüzü: rapor dosyaya
  UTF-8 yazıldığı için hayatta kaldı, ama `print` artık `try` içinde.

### 18.4 Test

| Test | Kontrol |
|---|---|
| `test_yukleme_fc.py` | 34 |
| `test_executor_fc.py` | 18 |
| `test_initgui_kapsam.py` | 9 |
| `test_baglam_fc.py` | 34 |
| `test_dogrulama_fc.py` | 40 |
| `test_panel_fc.py` (yeni) | 31 |
| `test_tam_tur_fc.py` (gerçek tur) | 82 |
| **toplam** | **248** |

---

## 19. Geri almayı AI yapıyor — ve kimin işini geri aldığı denetleniyor

Kullanıcının sorusu: *"geri almayı da AI yapamaz mı, niye kullanıcıya zorla
yaptırıyor?"* Yapabilir. Günlüğe bakınca bunun bir kolaylık değil, **ölçülmüş
bir kayıp** olduğu çıktı.

### 19.1 Ölçüm — `LOG/2026-08-20_baa70fa4.txt`

**Birinci kayıp: 13 dakika 21 saniye.**

```
15:32:51  AI : "Bu noktadan sonra script ile daha fazla düzeltme denemek
                riski büyütür. İlk adım kod değil: Ctrl+Z ile ... geri dön."
15:46:12  KUL: "geri aldım"
```

Oturum, hostun milisaniyede yapabileceği bir işlem için on üç dakika durdu.
Üstelik model o turda **kod üretmedi** — "adım adım çalış" sözleşmesinin bir
turu, insana talimat vermeye harcandı.

**İkinci kayıp: aynısı tekrar.** `16:04:52` — *"Ctrl+Z ile bu son adımı geri
al."*

**Üçüncü ve asıl olan — bu bir hız sorunu değil, doğruluk sorunu:**

```
16:05:02  KUL: "tamam"
16:05:20  AI : "Geri alındığını VARSAYIP devam ediyorum:"
                ...ve o varsayımın üstüne kod üretti.
```

Kullanıcının *"tamam"*ı "geri aldım" mı, "devam et" mi? Belli değil. Model
**doğrulayamadığı bir duruma kod yazdı.** Yanlışsa hasar, düzeltmeye
çalıştığı hasarın üstüne biner.

### 19.2 Tehlike ve sınır

Geri alma yıkıcı bir işlem, ama asıl tehlike sanılan yerde değil. Yığının
tepesinde **kimin işi** olduğu belirsiz: kullanıcı AI'ın kodundan sonra elle
bir şey yaptıysa, `doc.undo()` **onun işini** siler.

Kural: **model yalnızca kendi işlemini geri alabilir.** Executor bütün
işlemleri `AI: ` önekiyle açıyor (§7'deki tek-temiz-geri-alma kararının yan
ürünü); tepedeki kayıt bu öneki taşımıyorsa host reddediyor.

Model isteği `GERI-AL` işaretiyle veriyor — `GORSEL-KONTROL` ile aynı desen,
kendi satırında olmalı ki *"geri-al demeye gerek yok"* gibi bir cümle
tetiklemesin.

### 19.3 Reddedilince ne oluyor — ölçülen 3. kaybın panzehiri

Başarılı geri almada **tur harcanmıyor**: modelin varsayımı zaten doğru,
belge de bir sonraki turda bağlamla gidiyor.

Reddedilirse **bir otomatik tur harcanıyor** ve modele neyin olmadığı
söyleniyor. Pahalı ama pazarlık dışı: sessiz kalmak, ölçülen üçüncü kaybı
sisteme kural olarak yazmak olurdu — model isteğinin yerine getirildiğini
sanıp yanlış duruma kod yazardı.

Ayrıca bağlama tek satır eklendi, böylece model körlemesine istemiyor:

```
undo_stack=AI: kalsin | AI: dongu 0
```

Döngü emniyeti: arka arkaya en fazla iki otomatik geri alma, gerçek kullanıcı
mesajı sayacı sıfırlıyor.

### 19.4 Yol boyunca bulunan gerçek hata

Paneldeki düğmenin etiketi **"Son AI değişikliğini geri al"** idi ama kodu
koşulsuz `doc.undo()` çağırıyordu. Yani kullanıcı AI'ın kodundan sonra elle
bir şey yaptıysa, düğme onun işini siliyordu. **Etiket yalan söylüyordu.**

`commands.py`'deki aynı komut daha da kötüydü: öneki kontrol ediyor, sonra

```python
log.uyari(f"son islem AI'a ait degil ({ad}) — yine de geri aliniyor")
doc.undo()
```

diyordu. Yani sorunu **biliyor** ve yine de yapıyordu; üstelik uyarı Report
view'da kalıyor, kullanıcı görmüyordu. İkisi de artık aynı denetimli yoldan
geçiyor (`ConversationController.geri_al`), ve o yol `namespace_temizle()`
de çağırıyor — bayat bağlama §7'de belgelenmiş **sert çökme** sebebi.

### 19.5 Test

`tests/test_geri_al_fc.py` — 36 kontrol, ağa çıkmadan. En önemlisi şu senaryo:
AI bir kutu ekliyor, **kullanıcı elle** başka bir şey yapıyor, sonra geri alma
isteniyor. Beklenen: reddedilsin, kullanıcının nesnesi de AI'ınki de dursun,
ve modele *"varsayma"* denilsin. Dördü de doğrulanıyor.

| Test | Kontrol |
|---|---|
| `test_yukleme_fc.py` | 34 |
| `test_executor_fc.py` | 18 |
| `test_initgui_kapsam.py` | 9 |
| `test_baglam_fc.py` | 34 |
| `test_dogrulama_fc.py` | 40 |
| `test_geri_al_fc.py` (yeni) | 36 |
| `test_panel_fc.py` | 31 |
| `test_tam_tur_fc.py` (gerçek tur) | 85 |
| **toplam** | **287** |

---

## 20. İncelemeden çıkan üç ciddi bulgu — düzeltildi

Kaynak: `report.txt` (48 dosya, ~6.100 satır okundu). Üç bulgunun ortak yanı
şu: hiçbiri patlamıyordu. Testler yeşildi, panel çalışıyordu. **Sessiz
hatalar, gürültülü olanlardan tehlikeli.**

### 20.1 Hata geri beslemesi elle yapılıyordu

Kod patladığında kullanıcı *"Hatayı AI'a gönder"* düğmesine **basmak
zorundaydı**; basmazsa model kodunun patladığını hiç bilmiyordu.

Bu, §19'daki geri alma sorununun **birebir aynı kalıbı**: host'un
kendiliğinden yapabileceği bir iş insana yaptırılıyordu. Günlükte kullanıcı o
düğmeye üç kez basmış — akış her seferinde aynı, tek fark bir tıklama ve
kullanıcının o an başka yere bakıyor olma ihtimali.

Artık otomatik. PLAN M4'ün bütçesi uygulandı, ama **iki sınırla**:

1. En fazla **2** otomatik tur, sonra dur — düğme yerinde, elle devam
   edilebilir.
2. **Aynı hata iki kez gelirse bütçe dolmadan dur.** Model aynı duvara
   tosluyor demektir; üçüncü deneme de aynı yere çarpar. Hatanın kimliği
   traceback'in son satırı — satır numaraları ve yollar değişse de hatanın
   *türü ve mesajı* değişmiyorsa ilerleme yok.

Ayrıca istem sertleşti: *"Aynı yaklaşımla ikinci kez denemek yerine, hata
bunu gerektiriyorsa **başka** bir yol seç."*

### 20.2 Kullanıcının kendi Ctrl+Z'sinde namespace korumasızdı

Executor kalıcı bir namespace tutuyor (bilinçli: model 2. turda `body.Tip`
demeye eğilimli). Riski belgeli: silinmiş bir C++ nesnesini gösteren ad,
istisna değil **sert çökme** üretir (§7).

Önlem `namespace_temizle()` vardı — ama yalnızca panelden/AI'dan gelen geri
almada çağrılıyordu. **Kullanıcı FreeCAD'in kendi Ctrl+Z'sine bastığında, ki
normal yol budur, hiçbir şey temizlenmiyordu.** En olağan senaryoda
korumasızdık.

Çözüm kalıcı bir `DocumentObserver` (§17'nin altyapısı zaten hazırdı).
Nesne silindiğinde namespace toptan boşalıyor.

**Neden nesne nesne değil, toptan:** hangi adın silinen nesneye baktığını
anlamak için değerlerin `.Name`'ine bakmak gerekir — ve o değerlerden bazıları
zaten bayat olabilir. Tam da kaçındığımız şeye dokunmuş olurduk.

**Asıl tuzak, kendi çalıştırmamız.** Namespace, `exec`'in globals'ı olarak
duruyor; ortasında boşaltmak her adı birden `NameError` yapardı. O yüzden
çalışma sırasında bayrak konuyor, `exec` bittikten sonra temizleniyor. Test
bunu ayrıca sınıyor: *bir nesne silen ve sonra devam eden* kod.

### 20.3 Belge var olmayan bir emniyeti "var" diye anlatıyordu

§6 *"Üç katman var"* diyordu; ikisi yazılmamıştı. `(M7)` işareti dipnot gibi
duruyordu ama cümle **var** diyordu. Somut izi: `config.py`'de `AutoRun`
ayarı, açıklaması *"guard temizse onay beklemeden çalıştır"* — **guard yok**.
Açılsaydı hiçbir şey denetlemeden kod çalışırdı.

Bu bir "temizlik" meselesi değil: MANTIK, bir sonraki oturumun tek bilgi
kaynağı. Yanlış belge yanlış karar üretir.

İki seçenek vardı, ikisi de yapıldı:

- **Katman 2 yazıldı.** `executor._yedek_al` — belge başına bir kez, ilk AI
  değişikliğinden **önce**, `.caddy-backups/` altına `saveCopy`. Gerekçesi
  ölçülmüş: uzun bir seansta model kendi hasarını üstüne üstüne
  biriktirebiliyor ve Ctrl+Z yığını o kadar geriye yetmeyebiliyor. Belgenin
  kaydedilmiş olması gerekmiyor — ölçüldü, `saveCopy` kaydedilmemiş belgede
  de çalışıyor.
- **Katman 3 "YOK" diye işaretlendi** ve `AutoRun` koddan çıkarıldı.

**Test bir hata buldu:** `_yedek_al`'ın docstring'i *"asla işi engellemez"*
diyordu ama **çağrı yerinde koruma yoktu** — içerideki `try` yalnızca
`saveCopy`'yi kapsıyordu. Emniyet mekanizmasının asıl işi engellemesi,
engellemeye çalıştığı şeyden kötü olurdu. Çağrı yeri de sarıldı: söz artık
**yapısal**, gözle doğrulanan bir şey değil.

### 20.4 Silinen ölü kod

| Ne | Neden yanıltıcıydı |
|---|---|
| `config.otomatik_calistir` / `AutoRun` | Dayandığı guard yok (20.3) |
| `process.girdiyi_kapat` | Tek atışlık sürümden kalma; kalıcı süreçte stdin **açık** kalmalı, çağrılsa turu bozardı |
| `process.stderr_metin` sinyali | Yayınlanıyor, hiçbir yere bağlı değil |
| `gorunum.py` iskele artığı | Üç satır değer hesaplayıp `del` ediyordu |

`config.yedek_dizini()` ölü listesindeydi; artık **kullanılıyor**.

### 20.5 Günlük artık ölçülebilir

`sohbet_log.calisma()` doğrulama raporunu, `dokunulan` listesini ve yedek
yolunu kaydetmiyordu. Bu projede kalite analizinin tek kaynağı günlükler
(`caddy_gelisim.txt` tamamen onlardan çıktı); **kaydetmediğimizi sonradan
ölçemiyoruz.**

Ayrıca panelin kendiliğinden gönderdiği turlar (görsel kontrol, hata onarımı)
günlükte `KULLANICI` diye yazılıyordu. Artık `OTOMATIK`. Günlüğe sonradan
bakan biri insanın yazdığıyla otomatik turu ayırt edebilmeli — özellikle
artık otomatik tur sayısı arttığı için.

### 20.6 Test

`tests/test_koruma_fc.py` — 45 kontrol, ağa çıkmadan.

| Test | Kontrol |
|---|---|
| `test_yukleme_fc.py` | 34 |
| `test_executor_fc.py` | 18 |
| `test_initgui_kapsam.py` | 9 |
| `test_baglam_fc.py` | 34 |
| `test_dogrulama_fc.py` | 40 |
| `test_geri_al_fc.py` | 36 |
| `test_koruma_fc.py` (yeni) | 45 |
| `test_panel_fc.py` | 31 |
| `test_tam_tur_fc.py` (gerçek tur) | 85 |
| **toplam** | **332** |

`report.txt`'te kalanlar: PLAN.md güncellemesi (madde 4), tek komutla test
koşucusu (madde 7), tercihler sayfası (madde 6) ve küçükler.

## 21. Günlük incelemesi — ölçülen dört kanal eksiği

Kullanıcının sorusu: *"tam istediğim olgunluğa gelmiş değil, logları çok
ayrıntılı incele, limit bu mudur?"*

47 günlük dosyası, 35 gerçek oturum, 190 AI turu, 136 çalıştırma okundu ve
sayıldı (`log_incelemesi.txt`). Cevap: **limit model değildi.** Ölçülen
kayıpların dördü de host'ta eksik olan bir KANALDAN geliyordu.

### 21.1 Ölçümler

| | |
|---|---|
| tur süresi | medyan 21.2 sn · p90 62.2 sn · en kötü 149.6 sn |
| hata ile biten çalıştırma | 37 / 136 (%27) |
| `print()` içeren blok | 8 |
| **çıktısı modele ulaşan** | **0** |
| kasıtlı `raise` ile veri taşıma | ~31 blok |
| aynı kodun arka arkaya koşması | 8 kez |

### 21.2 print() çıktısı modele hiç gitmiyordu

Executor çıktıyı yakalıyordu (`redirect_stdout`), `cikti`'ya koyuyordu,
günlüğe yazıyordu, panelde gösteriyordu — modele göndermiyordu. Sebep tek
satırdı (`code_card.py`): "Sonucu AI'a gönder" düğmesi yalnızca UYARI varken
görünüyordu, `cikti` o koşulda yoktu. Yani kod başarılı olup tek ürünü bir
sayı olduğunda o sayıyı modele iletmenin **hiçbir yolu yoktu**.

Modelin telafisi günlükte duruyor:

* **Nesne üreterek ölçme.** `baa70fa4` 15:22 — "ağız çapı ne kadar": model
  yarıçapı doğru hesapladı, sonra sayıyı kendine geri getirebilmek için
  belgeye Draft çemberi ekleyip **bir sonraki turda** yarıçapını okudu.
  Nesne bir ölçüm aracı değil, bir POSTA KUTUSUYDU. Çemberi silen kod da
  `Placement.Position` ile patladı: bir sayı için 4 tur, 1 çöp nesne, 1 hata.
* **İstisnayı postacı yapma.** `6d5ad55c` 13:26 — modelin kendi cümlesi:
  *"sonucu kasıtlı bir hataya gömüp size otomatik olarak geri gelmesini
  sağlayacağım."* Çalışıyordu, çünkü **hata yolu otomatik besleniyordu,
  başarı yolu beslenmiyordu.** Model host'un açık bıraktığı tek deliği
  bulmuştu.

Artık başarı yolu da besleniyor (`_ciktiyi_yolla`). Görsel kontrol
bekliyorsa çıktı **aynı tura bindiriliyor**, ikinci tur harcanmıyor.

### 21.3 Doğrulama ve bağlam mesh'i görmüyordu

`Mesh::Feature`'ın `Shape`'i yoktur. `dogrulama._bir_nesne` ilk satırda
`Shape is None` diye dönüyordu; `serializer._kutu` bbox'ı `Shape`'ten
alıyordu. Son dört gerçek oturumun ana nesnesi mesh'ti — Monkey indirdiğini
mesh olarak getiriyor, yani asıl iş akışı bu. §17'de yazdığım deterministik
katman o oturumların **hiçbirinde tek bir kontrol koşmadı**, ve modelin
kendi cümlesi: *"Mesh nesnesinde çap bilgisi context'te yok."*

**Ölçüldü — `mesh.isSolid()` de yalan söylüyor:** birbirinin içine giren iki
kutu için `isSolid() → True`, ama `hasSelfIntersections() → True` ve
`countComponents() → 2`. §17'deki `isValid()` bulgusunun mesh'teki tıpatıp
aynısı. O yüzden kontrol tek soruya değil beşine birden bakıyor.

**Maliyet ölçüldü** (12.850 facet): isSolid 0.008, hasSelfIntersections
0.024, hasNonManifolds 0.005, countComponents 0.001 sn — süre bütçesinin
ellide biri. Ödenecek bedel yoktu, sadece yazılmamıştı.

### 21.4 "Baskıya hazır mı" — kanaat yerine ölçüm

Kullanıcı bunu neredeyse her oturumda soruyor ("hazır mı", "hazır dedi mi
nereden bakcıam"). Cevabı model kanaatle veriyordu. `baski_kontrol(nesne)`
namespace'e bağlandı: kapalılık, kesişme, non-manifold, parça sayısı, hacim
— yazdırıyor, çıktı modele dönüyor, tek tur.

### 21.5 Ölçme — asıl mesele geri okuma DEĞİLMİŞ

Kullanıcının itirazı doğruydu: *"neden ölçmek için ekstra parça eklemesin
ki, eğer ölçemiyorsa eklemeli — ölçmesi çok kritik, kullanıcı sürekli
ölçemez."* İki sorun birbirine karışmıştı:

1. **Geri okuma** — model ölçüyü zaten hesaplamıştı, geri getiremiyordu.
   21.2 ile kapandı.
2. **Gerçek ölçme** — mesh'te yüz/kenar YOKTUR. Seçim bağlamı bir katı için
   "cylinder r=4" diyebilirken mesh için söyleyecek hiçbir şeyi yok; orada
   yalnızca üçgen yığını var. "Ağız çapı ne kadar" mesh'te hesaplanmak
   ZORUNDA ve model bunu her seferinde elle, altı satırlık döngülerle yazdı.

İkincisi için `caddy/execution/olcum.py`: `olc()` ve `kesit_capi()`.
`kesit_capi` **kısa ve uzun çapı ayrı ayrı** veriyor — ovalin tek bir çapı
yoktur ve ortalamaya bakan bir ölçüm ovali daire sanar.

FreeCAD 1.1'in kendi Measure sistemi denendi ve ELENDI: `App.MeasureManager`
var ama `getMeasureTypes()` konsolda boş dönüyor (tipleri GUI kaydediyor).
Mesh-mesh en kısa mesafe de kaba kuvvette 1562×1562 nokta için 3.9 sn —
o yüzden mesafe yardımcısı yazılmadı, katı tarafında `distToShape` zaten var.

**Kural nesne üretmeyi yasaklamıyor**, ölçümü İKİ TURA yaymayı yasaklıyor:
kur, oku, yazdır, aynı blokta sil. Nesne belgede yalnızca *kullanıcı*
görsün diye bırakılır.

**Test gerçek bir hata buldu:** `kesit_capi` nesnenin Z ekseninde durduğunu
VARSAYIYORDU. Yatık bir silindirde yatay dilim halka değil dikdörtgen olur
ve fonksiyon "kısa çap = 7.25e-11" gibi **inandırıcı ama yanlış** bir sayı
üretti. Sessizce yanlış sayı vermek, ölçemediğini söylemekten kötüdür
(§17'deki KOSMAYAN kuralının aynısı). Artık halka değilse `OLCULEMEDI`
diyor ve `guvenilir=False` işaretliyor.

### 21.6 Tekrar koruması karttan çalıştırıcıya indi

8 kez ölçüldü; kullanıcının kendi ifadesi: *"yanlışılkla çok çalıştırdım
tekrar çalıştıra bastım."* Bunun için 08-19'da karta onay penceresi
eklenmişti — ama 08-20'de, **onay penceresi varken** yine oldu:
`baa70fa4` 16:05:24 / :26 / :28, üçü de BAŞARILI, mesh her seferinde
yeniden yamandı, oturum orada bitti.

Kartın koruması kendi `_sonuc` alanına bakıyor; yeni bir kart nesnesi
oluşursa ya da sonuç yanlış karta yazılırsa (`dock`: `k.blok is blok`
kimlik eşleşmesi) koruma boşa düşüyor. Koruma tıklamanın olduğu yerde
değil, **hasarın olduğu yerde** olmalı — `CodeExecutor._tekrar_engeli`.
Aynı kod 60 sn içinde ikinci kez gelirse BİR KEZ durur; kullanıcı tekrar
basarsa koşar (onay mekanizması tekrarın kendisi — burada Qt yok, soru
soramayız). Yalnızca BAŞARILI koşular sayılıyor: patlayan kod belgeye bir
şey yazmadı, tekrarı zararsız ve otomatik onarım yolunu tıkamamalı.

`engellendi` alanı hatadan AYRI: modele "kodun patladı" diye gitmiyor,
günlükte hata oranına karışmıyor.

### 21.7 Görsel kanal — yapılmadı, hesabı çıkarıldı

Tek açı yetersiz: `baa70fa4`'te tek kareden iki yanlış teşhis üst üste ve
`b2938bd0`'da kullanıcı kamerayı kendisi çevirip *"ben çevirdim sen direkt
al görüntü bak"* demek zorunda kaldı. Yapılışı ucuz — transport zaten içerik
listesi kuruyor, üç `image` bloğu eklemek iki satır; birleştirme/PIL
gerekmiyor. Yakalama ~0.5 sn (üç offscreen render), token ~+1.7k.
Asıl bedel modelin üç resmi okuması: görsel turlar zaten 48–118 sn.
Kullanıcının kararına bırakıldı.

### 21.8 Test

`tests/test_mesh_cikti_fc.py` — 73 kontrol, ağa çıkmadan.

| Test | Kontrol |
|---|---|
| `test_yukleme_fc.py` | 34 |
| `test_executor_fc.py` | 18 |
| `test_initgui_kapsam.py` | 9 |
| `test_baglam_fc.py` | 34 |
| `test_dogrulama_fc.py` | 40 |
| `test_geri_al_fc.py` | 36 |
| `test_koruma_fc.py` | 45 |
| `test_panel_fc.py` | 31 |
| `test_mesh_cikti_fc.py` (yeni) | 73 |
| `test_tam_tur_fc.py` (gerçek tur) | 85 |
| **toplam** | **405** |

## 22. İlk sohbet, ölçüm ve iki kademeli görsel

Kullanıcının isteği üçe ayrılıyordu: (a) var olan bir şeyin üzerine
çalışılacaksa önce onu tam anlamak, (b) ölçümü ciddiye almak, (c) görseli
iki kademeye ayırmak.

### 22.1 Keşif — ama ÖLÇEN MODEL, host değil

İlk sürümü host'a yazdım: belge boş değilse `conversation` ölçer, `<kesif>`
bloğu olarak bağlama koyar, model ilk yanıtında rakamla konuşur. Gerekçem
"bir tur kazandırır" idi.

**Kullanıcı reddetti ve haklıydı:** *"host falan vermiyor ölçümü, AI
ölçmeli, host niye ölçsün — var olan bir şey varsa AI hızlıca ölçüyor sonra
yapıyor isteneni."*

Neden onunki doğru:

* **Ne ölçüleceğine işe bakarak karar verilir.** Host kör kör her nesnenin
  üç kesitini alır; çoğu turda gereksiz, her turda token. Model "kulp
  eklenecek" bilgisiyle neyin önemli olduğunu bilir.
* **Model ölçünce ölçüm sohbette görünür.** Kullanıcı hangi sayının nereden
  geldiğini görür, gerekirse kodu düzeltip yeniden çalıştırır. Host'un
  yaptığı ölçüm görünmez bir sihirdir.
* Benim "tur kazandırır" gerekçem zaten zayıftı: `print` çıktısı artık
  kendiliğinden döndüğü için ölçüm **tek blok, tek tur**.

Sonuç: `caddy/execution/kesif.py`, namespace'te `kesif()`. Host tarafındaki
tetikleyici tamamen kaldırıldı.

### 22.2 Ölçüm — hazır kod, elle geometri değil

Kullanıcının ikinci uyarısı: *"ölçüm çok zor bir şey, internette araştırma
yap, var olan kodlar varsa ekle."* Araştırıldı ve **hepsi zaten elimizdeydi**
— ölçüldü, tahmin edilmedi:

| Ne | Nereden | Ölçüm |
|---|---|---|
| yüz/kenar yarıçapı, alanı, uzunluğu | `Measure.Measurement` (FreeCAD'in kendi motoru) | arayüzsüz çalışıyor, delik yüzünde `radius() → 1.7` tam |
| iki katı arası en kısa mesafe | `Shape.distToShape` | temas noktalarıyla |
| duvar kalınlığı | `Mesh.foraminate` ışın atma | 24 açıda tarama 0.010 sn |
| gerçek kesit | `Mesh.crossSections` / `Shape.slice` | 1558 facet'te 0.033 sn |
| nesnenin kendi eksenleri | `Mesh.getEigenSystem` | kupada 55.35×95×55.38 |
| mesh-mesh mesafe | scipy `cKDTree` | 3542×3542 nokta **0.032 sn** (kaba kuvvet 3.9 sn — 120 kat) |
| noktadan çap | Taubin çember uydurma (numpy) | kulplu kesitte merkez: gerçek (5,−3), ortalama (6.30,−3), Taubin (5.80,−3) |

**numpy 1.26, scipy 1.16 ve shapely 2.1 FreeCAD'in içinde var** — ölçüldü.
Bunu bilmemek, çözülmüş problemleri elle yeniden yazmak demekti.

`App.MeasureManager` **elendi**: `getMeasureTypes()` konsolda boş dönüyor,
tipleri GUI kaydediyor.

`Shape.optimalBoundingBox()` de **elendi**: 30° döndürülmüş kutu için
28.48×10×19.33 döndü, yani hâlâ eksene hizalı. Yerine `PrincipalProperties`
atalet eksenlerine köşeler izdüşürülüyor — döndürülmüş kutuda
`FirstAxisOfInertia = (0.5, 0, 0.866)`, yani parçanın kendi ekseni.

### 22.3 Testin bulduğu üç hata

Üçü de aynı aileden: **sessizce inandırıcı ama yanlış sayı üretmek.**

1. **Nokta bandıyla kesit almak mesh'in üçgenlemesine bağlıydı.** Koni gibi
   bir gövdede mesh tabandan tepeye uzanan uzun üçgenlerden oluşuyor, ara
   yüksekliklerde hiç köşe yok — ölçüm sessizce boş dönüyordu. Gerçek
   kesitle (`crossSections`) değiştirildi.
2. **Işın atmada işaretsiz uzaklık.** `hypot` ile mutlak uzaklık almak
   ışının arka tarafındaki vuruşları öne karıştırıyordu: duvar 2.1 mm iken
   ortanca 0.045 mm çıktı. Işın yönüne izdüşüm alınıyor artık.
3. **Dejenere çember uydurma.** Yatık silindirin yatay kesiti iki paralel
   çizgidir; Taubin oraya yarıçapı 7.8e8 olan bir çember uydurdu ve kesit
   "dairesel" göründü. Uydurulan yarıçap nokta bulutunun kendi
   büyüklüğünden çok büyükse uydurma atılıyor.

Bunun sonucunda ölçüm katmanının kuralı şu oldu: **ölçemediğinde ölçemediğini
söyler.** `YUVARLAK DEGIL`, `duvar bulunamadi`, `kesit bulunamadi` — üçü de
sayı yerine geçen cevaplar. §17'deki KOSMAYAN kuralının aynısı.

### 22.4 Görsel: iki kademe

Kullanıcının kuralı: *"hızlıca bakması gerekiyorsa tek fotoğraf, ama çok
büyük değişiklik yaptı ve bir türlü çözemedi ise 3 açıdan alsın."*

* **Birinci kademe** — düz `GORSEL-KONTROL`: tek kare, kullanıcının baktığı
  açı. Hızlı, ucuz, çoğu kontrole yetiyor.
* **İkinci kademe** — üç kare (kullanıcının açısı + ön + üst). İki yoldan
  girilir: model `GORSEL-KONTROL 3` yazar (büyük değişiklik), **ya da** bu
  arka arkaya ikinci görsel kontroldür — yani ilk kare sorunu çözmedi.
  İkincisini host kendiliğinden yapıyor.

Resim birleştirmeye gerek yok: transport zaten içerik listesi kuruyor, üç
`image` bloğu ekleniyor. Kamera `getCamera()` ile kaydedilip geri
yükleniyor — kullanıcının baktığı yer bizim yüzümüzden değişmemeli.

İlk kare gönderilirken modele şu da söyleniyor: tek açıdan emin olamadıysan
tahmin etme, `GORSEL-KONTROL 3` ile bitir.

### 22.5 Test

`tests/test_mesh_cikti_fc.py` 73 → **108 kontrol**. Toplam **440**.

## 23. FreeCAD'in hazır yetenekleri — ÖLÇÜLMÜŞ envanter

Kullanıcının yönü: *"FreeCAD'in son potansiyeline kadar kullanalım, AI'ın
işi azalsın."* Gerekçe günlüklerde: model, FreeCAD'de tek çağrı olan şeyleri
elle yazıyor ve bunu yaparken model bozuyor — `baa70fa4`'te flood-fill ve
sınır-döngüsü örme denemeleri gövdede **gerçek delik açtı**, üç tur üst üste.

Aşağıdakilerin hepsi FreeCAD 1.1.1'de **koşturuldu**, tahmin değil.

### 23.1 Çalışanlar

| Yetenek | Çağrı | Ölçüm |
|---|---|---|
| mesh → katı | `Part.Shape().makeShapeFromMesh(m.Topology, 0.1)` + `Part.makeSolid` | 870 facet → 0.705 sn, `isValid()` True, hacim %0.2 sapma |
| mesh onarımı | `removeDuplicatedPoints` → `fixIndices` → `fixDegenerations` → `fixSelfIntersections` → `removeNonManifolds` → `fillupHoles` → `harmonizeNormals` | **0.024 sn**, delikli mesh `isSolid` False → **True** |
| baskı için parçaya bölme | `BOPTools.SplitAPI.slice(sekil, [duzlem], "Split")` | 0.391 sn, 2 katı |
| içini boşaltma (kupa/kutu) | `Shape.makeThickness([yuz], -kalinlik, 1e-3)` | 0.010 sn, silindir → kupa, valid |
| dışa doğru büyütme | `Shape.makeOffsetShape(mesafe, 1e-3)` | 0.038 sn |
| facet azaltma | `Mesh.decimate(tol, oran)` | 0.065 sn |
| dikdörtgen dizi | `Draft.make_ortho_array` | 1.93 sn (ilk çağrı modül yüklemesi) |
| polar dizi | `Draft.make_polar_array` | 0.030 sn |
| tüm kenarları yuvarlatma | `Part::Fillet` + `f.Edges = [(i, r, r), ...]` | 0.159 sn, valid |
| **tabloya bağlı ölçü** | `Spreadsheet::Sheet` + `setAlias` + `obj.setExpression("Radius", "Olculer.cap / 2")` | 0.143 sn, `Radius = 27.75 mm` |
| dışa/içe aktarma | `Mesh.export`, `Mesh.insert`, `Part.export` | 0.055–0.089 sn |
| gereksiz yüz temizleme | `Shape.removeSplitter()` | 0.001 sn |
| nokta içeride mi | `Shape.isInside(v, tol, True)` | 0.001 sn |

**Spreadsheet en çok atlanan yetenek.** MANTIK'ın "bırak düzenlenebilir
olsun" kuralının en güçlü hali bu: ölçüler bir tabloda, özellikler ifadeyle
tabloya bağlı. Kullanıcı tek bir hücreyi değiştirip modeli güncelliyor.

### 23.2 Tuzaklar (ölçülerek bulundu)

* **`makeThickness` yüzü AYNI shape örneğinden almalı.** İlk denemede kutuyu
  iki kez kurup yüzü öbüründen verdim: *"face does not belong to the shape"*.
  Aynı hata modelde de kolayca olur; yüz mutlaka `sekil.Faces[...]` ile
  o shape'ten seçilmeli.
* **mesh → katı, PARAMETRİK bir katı vermez.** 8000 facet'lik küre 4.64 sn'de
  8000 YÜZLÜ bir katıya dönüyor. Boolean'lar çalışır ama ağırdır ve kimse
  onu "düzenleyemez". Yani bu dönüşüm bir araçtır, bir çözüm değil: önce
  `decimate` ile facet düşür, ya da parçayı sıfırdan parametrik kur.

### 23.3 PartDesign desenleri — çözüldü, iki tuzakla

`PartDesign::PolarPattern` **çalışıyor**; ölçüldü: 6 delikli plaka, hacim
tam 13760.2 (beklenen değer), 7 silindirik yüz. İki tuzak vardı:

* **Özelliğin adı `Originals`.** `Transformed` FreeCAD 1.1'de YOK — eski
  belgelerdeki her örnek onu kullanıyor ve `AttributeError` veriyor.
* **Desen yalnızca ESKİZ TABANLI özellikte çalışıyor** (Pad/Pocket).
  Primitifte (`AdditiveCylinder`, `SubtractiveCylinder`) sessizce TEK kopya
  bırakıyor: hata yok, `State` "Up-to-date", hacim değişmiyor. Bu, sessiz
  yanlışların en kötü türü — kod başarılı görünüyor, model "6 delik açtım"
  diyor, belgede bir delik var.

Ayrıca `body.addObject(pattern)` Tip'i taşımıyor; `body.Tip = pattern`
elle kurulmalı. CLAUDE.md'de "addObject appends and moves Tip" yazıyordu,
desenler için doğru değil.

### 23.4 Sıradaki iş

Bu envanterin amacı, her satırı modelin tek çağrıda kullanabileceği bir
yardımcıya çevirmek — ölçüm tarafında `olc`/`kesit_capi`/`mesafe` için
yapıldığı gibi. Kural aynı: **yardımcı, yapamadığında yapamadığını söyler.**

## 24. FreeCAD'in yetenekleri yardımcıya çevrildi

`freecad_yetenekleri.txt`'deki envanterin ilk dört turu uygulandı:
`caddy/execution/islem.py`, 13 yeni yardımcı, namespace'te 20 çağrı.

### 24.1 Hız kısıtı — ölçüme dayanan gerekçe

Kullanıcının şartı: *"AI zaten yavaş veriyor, daha yavaş cevap vermesin."*

Bu iş turları **hızlandırıyor**. Gecikmeyi belirleyen şey üretilen token ve
günlüğün en yavaş turları tam olarak modelin uzun kod yazdığı turlar:
`baa70fa4`'te **149.6 sn** = BFS ile normal düzeltme (~45 satır), **118.5
sn** = delik kapatma (~50 satır). Kısa yanıtlar 3–5 sn. `mesh_onar()`
yazmak 50 satır yazmaktan bir büyüklük mertebesi hızlı.

Sabit istem büyümesi ölçüldü ve **hedefin biraz üstünde kaldı**: sözleşme
2901 → 3029 token, CLAUDE.md 4545 → 4860 token (437 → 449 satır).
Toplam +443 token, yani %6. Hedef "net ≈ 0" idi; elle mesh-cerrahisi
tarifini silmek 13 yardımcının tablosunu tam karşılamadı. Bu istem
önbelleğe alındığı için gecikmeye katkısı ihmal edilebilir, ama rakamı
olduğu gibi yazıyorum.

### 24.2 Ortak kural: yardımcı kendi etkisini doğrular

Her yardımcı işini yaptıktan sonra sonucu ölçüyor. Örnekler testten:

* `mesh_onar` → `ACIK facet=870 -> kapali facet=898 KESISME` ve altına
  **`KALAN SORUN: hala kendiyle kesisiyor`**. Yani mesh'i kapattı ama
  kesişmeyi çözemedi ve bunu söylüyor.
* `kati_yap` açık mesh'i **reddediyor**: "önce mesh_onar çalıştır".
* `icini_bosalt` hacim neredeyse değişmediyse "kabuk oluşmamış olabilir".
* `birlestir` sonuçta iki ayrı katı kalırsa "parçalar DEĞMİYOR olabilir".
* `tabana_otur` düz yüzü olmayan parçada uydurmuyor.
* `bagla` ifadeyi kurmadan **önce deniyor**.

### 24.3 Doğrulamaya yeni kontrol: sessiz desen hatası

MANTIK 23.3'te ölçülen sessiz hata artık deterministik olarak yakalanıyor:
bir `PartDesign::*Pattern` nesnesinin hacmi `BaseFeature`'ınkiyle aynıysa
desen **görünmez kalmıştır**. Test iki yönlü: primitife bağlı desende bulgu
çıkıyor, eskiz tabanlı doğru desende **yanlış alarm yok**.

### 24.4 Ölçerek bulunan üç tuzak

1. **`setExpression` çözülmeyen ifadeyi de kabul ediyor.** İstisna atmıyor,
   `ExpressionEngine`'e giriyor, ama değer değişmiyor. Yani "kuruldu mu"
   diye ExpressionEngine'e bakmak YANLIŞ cevap veriyor. Tek güvenilir yol
   `evalExpression` ile önce denemek — `bagla` bunu yapıyor.
2. **Vida dişi profili silindir yüzeyine TEĞET olmamalı.** Profil tabanı tam
   yarıçapta iken `fuse` geçersiz katı üretti: `isValid()` False ve hacim
   963, düz silindirin 1005'inden KÜÇÜK. Tabanı `derinlik/3` kadar içeri
   alınca `isValid()` True ve hacim 1156 — diş gerçekten dışarı çıkıyor.
3. **Liste kavrayışının içinde `dir()` modül genelini vermiyor**, kavrayışın
   kendi yerelini veriyor. Testte 20 yardımcının hepsi "eksik" göründü;
   `globals()` doğrusu. (Kodun kendisinde değil, testte olan bir hataydı —
   ama sessizce yanlış rapor veren cinsten.)

### 24.5 Test

`tests/test_islem_fc.py` — 73 kontrol. Her yardımcı için üç şey:
çalıştığı durum, **reddettiği** durum, ve kendi doğrulamasının yakaladığı
durum.

| Test | Kontrol |
|---|---|
| `test_yukleme_fc.py` | 34 |
| `test_executor_fc.py` | 18 |
| `test_initgui_kapsam.py` | 9 |
| `test_baglam_fc.py` | 34 |
| `test_dogrulama_fc.py` | 40 |
| `test_geri_al_fc.py` | 36 |
| `test_koruma_fc.py` | 45 |
| `test_panel_fc.py` | 31 |
| `test_mesh_cikti_fc.py` | 108 |
| `test_islem_fc.py` (yeni) | 73 |
| `test_tam_tur_fc.py` (gerçek tur) | 85 |
| **toplam** | **513** |

### 24.6 Sırada ne var

Envanterde kalanlar: arayüz tarafı (AI'ın kastettiği yüzü 3B'de seçmesi,
değiştirdiği yeri boyaması, kesit görünümü), tam kısıtlanmış eskiz, mesh
kesiti → eskiz köprüsü. Önce kullanıcı gerçek oturumda deneyecek; günlükten
yardımcıların kullanılıp kullanılmadığına ve tur sürelerine bakılacak.

## 25. Yapılabilecek işler — açık liste

Bu bölüm, oturum sonundaki tüm açık işleri tek yerde toplar. Kaynaklar:
`freecad_yetenekleri.txt` (envanterden kalanlar), `log_incelemesi.txt`,
`report.txt` ve bu turda kendi açtığımız borçlar. Sıralama değere göre,
her maddede maliyet ve **neyin ölçülmüş neyin tahmin olduğu** yazıyor.

### 25.1 Envanterden kalan üç tur

**A. Arayüz kanalı — şu an tek yönlü** (orta boy, başsız test EDİLEMEZ)

Kullanıcı seçiyor, AI okuyor; tersi yok. Üç parça:

* `Gui.Selection.addSelection(belge, nesne, "Face7")` — AI'ın *"şu yüzü
  kastediyorum"* demek yerine ekranda **seçmesi**.
* `ViewObject.DiffuseColor` — değiştirdiği yeri **boyaması**. Görsel
  kontrolde "şurayı değiştirdim" kanıtlanabilir olurdu.
* Kesit görünümü (clipping plane) — görsel kontrolün en büyük kör noktası:
  içi boş bir parçanın duvarı, iç boşluğu, gömülü parçası dışarıdan
  görünmüyor. Üç açılı görüntü bunu çözmedi.

Üçü de `FreeCADGui` istiyor, yani `freecadcmd` ile sınanamaz. Panel testi
(`test_panel_fc.py`) offscreen Qt ile çalışıyor ama `Gui.Selection` ve
`ViewObject` orada da yok. **Bu yüzden elle sınanacak ve MANTIK'a ölçüm
değil gözlem olarak yazılacak** — bu projede ilk kez.

**B. Tam kısıtlanmış eskiz** (büyük, en kalıcı)

Şu an model kısıtsız eskiz üretiyor: görüntü doğru ama kullanıcı bir noktayı
sürükleyince şekil dağılıyor. Ölçüldü: `sk.solve()` → 0 DoF ve
`FullyConstrained` çalışıyor. Zor olan kısıt üretmek değil, modelin
kısıtları **doğru** kurması. Bir `eskiz_kur(noktalar, kisitlar)` yardımcısı
ve sonunda `FullyConstrained` kontrolü ("kısıtlanmadı, N serbestlik kaldı")
gerçekçi bir ilk adım.

**C. Mesh kesiti → eskiz köprüsü** (orta, Monkey ile CADdy'yi birleştiren şey)

Ölçüldü: `crossSections` → `Part.makePolygon` 0.008 sn, 128 noktalı kesit.
Eksik olan, o telden **düzenlenebilir bir eskiz** üretmek: nokta sayısını
düşürmek (128 nokta kimseye eskiz değildir), yay/doğru parçalarına ayırmak.
İndirilen bir mesh'ten ölçü alıp üzerine parametrik parça kurmanın yolu bu.

### 25.2 Bu turda açtığımız borçlar

* **`mesh_onar` kendiyle kesişmeyi çözemiyor.** Testte ölçüldü: mesh
  kapandı ama `KESISME` kaldı. Şu an dürüstçe söylüyor, çözmüyor.
  Denenebilecek: `fixSelfIntersections`'ı yinelemeli çağırmak, ya da
  `kati_yap` → `removeSplitter` → yeniden mesh'lemek.
* **Dışa aktarma yardımcısı yok.** `disa_aktar(nesne, yol, kalite)` —
  CLAUDE.md'de iki adımlı tarif hâlâ duruyor ve günlükte iki kez hata
  vermişti (`.3mf`). Küçük iş, doğrudan karşılığı var.
* **`mesafe` mesh tarafında yaklaşık.** Nokta bazlı; üçgen yüzeyinin
  ortasına denk gelen teması biraz büyük gösteriyor. Şu an bunu söylüyor.
  Düzeltmek isterse: noktaları üçgen üzerinde örneklemek.
* **Sabit istem %6 büyüdü** (bkz. 24.1). Hedef net sıfırdı. Kısaltılabilecek
  yer: CLAUDE.md'deki dışa aktarma tarifi (yukarıdaki yardımcı yazılırsa
  kendiliğinden gider).

### 25.3 Eski borçlar (`report.txt`)

| # | İş | Durum |
|---|---|---|
| 4 | `PLAN.md` bayat — M2/M6 bitti ama ⬜, doğrulama bölümü 9 testin 3'ünü sayıyor | duruyor |
| 6 | İki eklentide de tercihler sayfası yok | duruyor |
| 7 | Tek komutla test koşucusu yok; **hiçbir test sıfırdan farklı çıkış kodu vermiyordu** | `test_mesh_cikti` ve `test_islem` artık veriyor, diğerleri hayır |
| 9 | CADdy/Monkey kopya kayması | duruyor |
| 10 | `serializer`'da 17 geniş `except Exception` — sessizce boş bağlam üretebilir | duruyor |
| 11 | `self.bilgi` hâlâ `wordWrap`'siz QLabel; `blocks.py` çit regex'i sütun 0 istiyor; `LOG/` sınırsız büyüyor | duruyor |

`log_incelemesi.txt` maddesi 8: 35 oturumun 10'u boş (panel açılıp
kapanmış) ve 264 baytlık günlük bırakıyor. İlk mesaja kadar dosyayı
açmamak yeterli.

### 25.4 Ölçüm bekleyenler

Bunlara **kullanıcının gerçek oturumundan sonra** karar verilecek:

* Yardımcılar gerçekten kullanılıyor mu, yoksa model yine elle mi yazıyor?
  (Günlükte `mesh_onar`/`kati_yap` çağrılarını saymak yeterli.)
* Tur süreleri düştü mü? Beklenti: uzun geometri turları kayboluyor.
* Üç açılı görsel gerçekten pahalı mı? (24.1'deki tahmin +%10–30.)
* Keşif (`kesif()`) ilk turda çağrılıyor mu, yoksa model yine tahminle mi
  başlıyor?

### 25.5 Reddedilenler

* **Assembly / TechDraw / FEM / OpenSCAD** — tek parça baskı işinde
  karşılıkları yok; üçü harici bağımlılık istiyor.
* **`App.MeasureManager`** — `getMeasureTypes()` konsolda boş, tipleri GUI
  kaydediyor. (`Measure.Measurement` kullanılıyor.)
* **`Shape.optimalBoundingBox()`** — döndürülmüş kutuda hâlâ eksene hizalı
  sonuç verdi; yerine atalet eksenleri.
* **Host'un keşfi yapması** — kullanıcı reddetti, gerekçesi 22.1'de.
* **Ekran görüntüsü çözünürlüğünü düşürmek** — modelin yakaladığı şey zaten
  ince kusur; küçültmek kontrolü işe yaramaz hale getirir.

### 25.6 Depo

GitHub uzak deposu **hâlâ tanımlı değil**. Kullanıcının sözü: "en son
gh'a çekicez". Tüm iş yerel `master` dalında.

---

## 26. Panel genişliği — "ayar" sanılan şey aslında bir taban

Kullanıcının isteği: *"caddy ekranın yüzde 60'ını kapsıyor, onu yüzde 40 yap,
yüzde 60 normal model gözüksün."*

İlk refleks bir genişlik ayarı yazmaktı. Ölçüm başka bir şey söyledi
(`freecadcmd` + `QT_QPA_PLATFORM=offscreen`, gerçek widget'lar):

    panel minimumSizeHint = 888 px
      üst satır            876 px
        'Son AI değişikliğini geri al'   344
        model kutusu ('Opus (iyi kalite)') 270
        'Yeni sohbet'                    140
        'Kayıtlar'                       104
    panel 400 px'e zorlandı  ->  yine 888 px

Yani panel Qt'nin verdiği kadar geniş değildi; **daha dar olamıyordu**.
`resizeDocks` dahil hiçbir genişlik ayarı bu tabanı aşamazdı — ayar yazılsaydı
çalışmayacak, "ayarladım" denecekti. 888 px kullanıcının ekranının ~%60'ı
olduğuna göre ana pencere ~1480 px; %40 hedefi 592 px, tabandan 296 px küçük.

Ölçümün kaynağı tamamen **etiket metinleriydi**. Kısaltıldı, bilgi
ipuçlarına taşındı (hiçbir cümle silinmedi):

| önce | sonra | ipucunda |
|---|---|---|
| `Son AI değişikliğini geri al` (344) | `Geri al` (92) | tam cümle + "senin işine dokunmaz" |
| `Yeni sohbet` (140) | `Yeni` (80) | tam cümle |
| `Opus (iyi kalite)` (270) | `Opus · iyi` (186) | tam etiket + ölçülmüş hız notu |

Sonuç: **888 → 492 px**. Taban hedefin 100 px altına indi, ancak ondan sonra
`resizeDocks` anlam kazandı: ölçüldü, 592 px = tam %40, merkezdeki 3B görünüme
%60 kaldı.

`config.PanelYuzde` (varsayılan 40) ile değiştirilebilir; 10–90 dışındaki
değerler varsayılana düşer. Yalnızca panel **ilk oluşturulurken** uygulanır —
kullanıcı kenarı sürüklerse seçimi oturum boyunca korunur. Sonuç günlüğe
yazılır (`panel genisligi: hedef … asgari … gercek …`); taban hedefi yine
aşarsa satır bunu **uyarı** olarak söyler, çünkü bu turun asıl dersi tam da
"ayarladım deyip geçmek" idi.

Testler: `test_panel_fc.py` 31 → 49 kontrol. Tabanın hedefin altında kaldığı,
panelin gerçekten daralabildiği, kısaltılan her etiketin ipucunda durduğu ve
`genisligi_ayarla`'nın gerçek bir `QMainWindow` + `QDockWidget` üzerinde %40
verdiği sınanıyor. Toplam 513 → 532 yeşil.

---

## 27. İkinci günlük incelemesinin beş bulgusu

`log_incelemesi_2.txt` 45 dakikalık gerçek bir oturumu çıkardı. Eklenen dört
kanal çalıştı (hata %27→%3.7, print çıktısı %0→%89, `raise` hilesi 0, ilk
turda ölçüm). Bu bölüm, aynı incelemenin bulduğu beş kusurun kapatılması.

### 27.1 `Mesh.unite()` — envanterde ilk "var ama KULLANILAMAZ"

En pahalı bulgu, `birlestir()`'in KATI istediğinin CLAUDE.md'de yazmamasıydı:
model onu mesh birleştirici sandı ve **13 çalıştırma / 16 dakika** çıkmazda
döndü. Çözüm "mesh birleştirme ekle" gibi göründü. Ölçüm başka şey söyledi.

FreeCAD 1.1.1, `Mesh.Mesh.unite()` — var, hızlı (0.003–0.05 sn), hacmi bile
doğru hesaplıyor (iki kutu: tam 15000 mm³). Ama:

| durum | unite sonrası | onarım zincirinden sonra |
|---|---|---|
| iki kutu | kapalı=False, kesişme=False, parça=1 | kapalı=**False** (değişmedi) |
| iki küre | kapalı=False, kesişme=True, parça=1 | parça **1→3** (kötüleşti) |
| silindir+torus | kapalı=False, kesişme=True, parça=1 | parça **1→7** |

**Hiçbir yapılandırmada kapalı mesh üretmedi** ve onarım zinciri düzeltmedi,
kötüleştirdi. Üzerine kurulacak bir yardımcı "birleştirdim" derken açık mesh
bırakırdı — MANTIK 24'ün "yardımcı kendi etkisini doğrular" kuralının tam
ihlali. Reddedildi.

Katı yolu (`makeShapeFromMesh` → `makeSolid` → `fuse` → `meshFromShape`)
çalışıyor ve facet sayısına aşırı duyarlı:

| toplam facet | süre | sonuç |
|---|---|---|
| 2 172 | 2.9 sn | geçerli, kapalı, kesişmesiz, 1 parça |
| **3 784** | **7.4 sn** | geçerli, kapalı, kesişmesiz, 1 parça |
| 32 756 | 59.2 sn | geçerli katı AMA mesh'te **kesişme** |

Yani `AZAMI_FACET = 4000` yalnızca hız için değil, **sonucun temizliği** için
de doğru çalışma noktası. Dönüşüm artık tek yerde: `islem._mesh_kati`.

### 27.2 `birlestir()` artık mesh de alıyor — ve olmuyorsa doğrusunu söylüyor

Yeni isim EKLENMEDİ. Günlükteki başarısız çağrı `birlestir(govde, kulp)`
idi; doğru olan o çağrının çalışması. Katı+katı yolu aynen duruyor
(`JoinAPI.connect`), mesh+mesh yolu eklendi: ikisi de kapalı mı → bbox'lar
gerçekten değiyor mu (7 saniyelik işi boşuna başlatma) → katıya çevir, fuse,
mesh'e dön → **ölç** (kapalı mı, tek parça mı, hacim toplamdan küçük mü).

Tutmazsa yarım nesne bırakmaz ve baskı için doğru olanı söyler: *iki kapalı
parça iç içeyse dilimleyici zaten tek parça basar.* Bu teselli değil —
modelin 16 dakika sonra kendi bulduğu ve kullanıcının kabul ettiği çözüm.
Fark, ilk çağrıda söylenmesi. Ölçüldü: testte 0.4 sn, kapalı, tek parça,
hacim 5.04e4 < ayrı toplam 5.21e4.

### 27.3 Yardımcı tablosunda GİRDİ/DÖNÜŞ sütunu

İki ölçülmüş boşluk: `birlestir` ne istediğini söylemiyordu (16 dakika) ve
hiçbir satır dönüş değeri söylemiyordu — model bütün bir turu *"`kati_yap`'in
ne döndürdüğünü bilmediğim için önce yazdırıp öğreniyorum"* demeye harcadı.
Tabloya "Needs → gives back" sütunu eklendi. Bütçe tutuldu: sabit istem
4860 → 4991 kaba token, **+131** (hedef +150). Karşılığında tabloda tekrar
eden mesh onarım anlatısı kısaltıldı.

### 27.4 Düşen görsel isteği artık sessiz değil

Model `"...baskıya hazır — GORSEL-KONTROL"` yazdı; işaret kendi satırında
olmadığı için host **sessizce** hiçbir şey göndermedi ve model bunu
öğrenemedi. 5 istekten 1'i böyle kayboldu, 41 saniye sonra kullanıcı yazdı.
MANTIK 21'deki "kapalı kanal" kalıbının aynısı.

Sözleşme zaten "yanıtını bu işaretle **bitir**" diyor; regex artık kendi
satırını **ya da satır sonunu** kabul ediyor. Metnin ortasında geçerse hâlâ
tetiklemiyor (yoksa "görsel-kontrol gerekmiyor" cümlesi resim çektirirdi) ama
artık sessiz de kalmıyor: günlüğe yazılıyor ve **zaten gidecek olan** bir
sonraki otomatik isteme tek cümle biniyor. Ek tur harcamıyor.

### 27.5 `HATA — No error`

Oturumdaki tek hatanın özeti kelimenin tam anlamıyla "No error" diyordu (OCC
istisnaları mesajsız gelebiliyor); model doğru teşhisi ancak kendi
`print`'lerinden çıkarabildi. `executor._hata_ozeti`: son satırın mesajı boş
ya da "No error" ise istisna **tipi** + traceback'te suçu işaret eden son
satır veriliyor. Artık `Part.OCCError (mesajsiz) — son satir: kati =
s1.fuse(s2)`.

### 27.6 Harcama ile bağlam aynı sayı değil

Günlükte bağlam `86953 → 179116 → 92600` diye sıçradı ve panelde kullanıcıya
bu yazıyordu. `result.usage` **turun tamamını** topluyor; tur iki API çağrısı
yaptıysa aynı bağlam iki kez sayılıyor. Bağlam penceresi ise **tek bir
isteğin** boyudur.

Artık `stream_event` içindeki `message_start` olayları sayılıyor
(`api_cagrisi`) ve **son** çağrının istem boyu bağlam olarak kullanılıyor;
alan yoksa eski toplama düşüyor. Harcama (`tk_toplam`) olduğu gibi kalıyor —
iki çağrı olduysa iki katı olması doğru. Günlüğe ikisi de ayrı yazılıyor,
`api=2` görünüyor. **Hipotez gerçek oturumda doğrulanacak; ölçmeden
"düzeldi" denmeyecek.**

### 27.7 Bir test kırılganlığı

`mesh_onar` süre kontrolü çalıştırmanın **duvar saatine** bakıyordu ve ilk
çalıştırma süreçteki tek seferlik import bedelini de ödüyor: aynı test arka
arkaya **16.5 sn ve 1.56 sn** verdi. Artık onarımın kendi süresi ölçülüyor
(< 1 sn). Ölçmek istediğimiz şeyi ölçmeyen bir eşik, eşik değildir.

Testler: 532 → **567** yeşil (islem 73→87, tam_tur 86→100, executor 18→25).

---

## 28. İki model, aynı iş: 2026-08-24 ölçümleri

Aynı gün, aynı tavşan, aynı hedef ("içini doldur"), iki oturum. Bu projede
ilk kez **kontrollü bir karşılaştırma** elimizde.

| | Sonnet `67cd3efb` | Opus `3ad4cef1` |
|---|---|---|
| süre | 21.6 dk | 25.1 dk |
| kullanıcı mesajı | 5 | **4** |
| AI turu | 13 | 10 |
| tur başına ortalama | 49.1 sn | **87.5 sn** |
| harcama | ~938 k token | **~609 k token** |
| kendi kendine GERİ-AL | 1 | 2 |
| sonuç | kullanıcı hiç onaylamadı | **"evet güzel oldu istediğim gibi"** |

Opus tur başına 1.8 kat yavaş, toplamda %35 daha ucuz, ve işi bitirdi.
Fark tur sayısında değil turların isabetinde.

### 28.1 Ölçüm ve görsel AYNI turda

Opus ilk mesajında `kesif()` ile `GORSEL-KONTROL 3`ü birlikte istedi; ikisi
tek istemde döndü. Sonnet ikisini ayrı turlarda, 14 dakika arayla kullandı.
Host bunu zaten destekliyordu (çıktı görsele biniyor) — kullanan olmamıştı.

### 28.2 Görseli kendini ÇÜRÜTMEK için kullanmak

Sonnet 3 kareye bakıp yanlış sonucu **onayladı**, sonra kullanıcı itiraz
edince yeni kanıt olmadan fikir değiştirdi. Opus aynı durumda iki kez
kendi işine baktı, bozuk olduğunu gördü, **kendi GERİ-AL'ini verdi** ve
kendi hatasının mekanizmasını söyledi ("boğaz aramasına koyduğum 20 mm
sınır karnın gerçek açıklığından dar kalmış").

Görsel istemimiz *"doğru görünüyorsa tek cümleyle onayla"* diyor — yani
onaya doğru itiyor. Opus buna rağmen çürüttü; Sonnet itilen yöne gitti.
Kanal iyi, varsayılanı tartışmalı.

### 28.3 `_GORSEL_SINIR` yanlış şeyi sayıyordu

12:03:26'daki başarılı çalıştırmadan sonra günlüğe **hiçbir şey** düşmedi.
Sebep zinciri:

1. `_gorsel_tur` yalnızca **kullanıcı yazınca** sıfırlanıyordu. Opus üç kez
   baktı, aralarda GERİ-AL verip yeni kod yazdı — yani tam da istediğimiz
   döngü — ve dördüncüde bütçe doldu.
2. Bütçe dolunca `_gorseli_gonder` erken dönüyordu; **çıktı ona
   bindirilmişti**, o da gitti. Model başarılı bir çalıştırma hakkında
   sıfır geri bildirim aldı (`dolgu alani: 3080 mm2 | cakisma: 0.00 mm2`).
3. Bastırma yalnızca panele yazılıyordu, `gunluk.sistem`'e değil. Diğer
   bütün bastırma yolları günlüğe yazıyor; bu yüzden logda o boşluğun
   sebebi yoktu.

Üçü de düzeltildi. Sayaç artık **kod çalışınca sıfırlanıyor**: koruma
"bakıp yine bakmak"a karşıydı, "bak → değiştir → yine bak"a değil.

### 28.4 Geçerli katı ≠ basılabilir katı

`birlestir` "hacim=5.551e+04 mm3, 1 katı" dedi, `isValid()` True idi,
doğrulama "katı=1" dedi. **Aynı şekil** 0.05 mm'de mesh'lenince kapalı
değil + kendini kesen + non-manifold çıktı. 108 saniyelik işlem yanlış
güven verdi; hata dışa aktarma anında, 25 dakika sonra ortaya çıktı.

Sebep bilinen borç (25.2) ama asıl kusur şuydu: `dogrulama` kendiyle
kesişme kontrolünü KATI nesnelerde hiç koşmuyor (OCC'de pahalı, her
çalıştırmada her nesne için ödenirdi). `birlestir` ise zaten saniyeler
süren tek bir işlem — kontrolün oraya konması ölçüldü:

| iş | işlem | kontrol |
|---|---|---|
| iki kutu | connect 0.285 sn | 0.047 sn |
| silindir + küre | connect 0.059 sn | 0.064 sn |
| mesh kökenli katı | fuse 1.802 sn | 0.929 sn |

En kötü ~1 sn, riskin en yüksek olduğu yerde işlemin küçük bir yüzdesi.
Koşulsuz koşuyor. `yaz=False` iken hesaplanmıyor — çıktıyı istemeyen
maliyeti de ödemesin.

### 28.5 `JoinAPI.connect` mesh kökenli katıda patlıyor

Ölçüldü: 1740 yüzlü küre katısı + kutu → *"There is more than one largest
piece!"*. Düz `fuse` aynı işi yaptı (7452 mm³, tek katı, baskıya hazır).
Eskiden bu durumda `None` dönüyorduk — çalışan bir yol dururken model
çıkmaza giriyordu. Artık iki kademe var ve hangisinin kullanıldığı
yazılıyor (`(connect)` / `(fuse)`).

### 28.6 İki model de aynı on satırı elle yazdı

Sonnet `slice` döngüsüyle genişlik profili çıkardı: **68.9 sn**. Ayrıca
49.0 sn'lik bir `isInside` nokta taraması yaptı ve — bir çıkarma işlemi
eksik kaldığı için — sonucu "çözemedi" diye çöpe attı (348 boş nokta,
beklenen 353; yani iç boşluk yok, ölçüm soruyu kesin cevaplamıştı).
Opus `makeShapeFromMesh → slice → sort → discretize` kalıbını **beş ayrı
blokta** baştan yazdı.

`kesit_konturu(nesne, z)` eklendi: mesh de katı da alır, belgeye nesne
eklemez, konturları en uzundan kısaya döndürür ([0] her zaman dış hat).

### 28.7 İleri al

Kullanıcı "evet güzel oldu istediğim gibi" dediği sonucu yanlışlıkla geri
aldı — 6 saniyede üç kez — sonra eski bloğu iki kez çalıştırıp aynı hatayı
aldı ve oturum bitti. **O anda ileri yığında üç kayıt duruyordu.**

Ölçüldü — ileri yığını tam olarak ne zaman siliniyor (FreeCAD 1.1.1):

| durum | ileri yığını |
|---|---|
| boş transaction (commit ya da abort) | KORUNUR |
| salt-okunur kod (sadece print) | KORUNUR |
| SyntaxError (transaction hiç açılmadı) | KORUNUR |
| **değişiklik yapıp iptal edilen işlem** | **SİLİNİR** |
| yeni ve başarılı işlem | SİLİNİR (normal) |

Yani o günkü iki başarısız çalıştırma yığına **dokunmamıştı**; düğme o gün
var olsaydı 25 dakikalık iş geri gelirdi. `blogu_calistir` artık yığının
silindiğini fark edip söylüyor.

GERİ-AL'in aksine ileri alma kullanıcının kaydını da geri getiriyor.
Asimetri kasıtlı: geri alma iş **siler** (denetim gerekir), ileri alma iş
**getirir** (reddetmenin koruyacağı bir şey yok).

Düğme panelin asgari genişliğini 492 → 602 px'e çıkardı, yani %40
hedefinin (592) üstüne. 80 px Qt'nin düğme tabanı — "Geri"/"İleri"/"Kayıt"
hepsi 80 px, o eşiğin altında kısaltmak faydasız. Yer `"Kayıtlar" → "Kayıt"`
ile açıldı: **578 px**, panel tam %40'a oturuyor.

### 28.8 Günlük başlığı

Her log dosyasının tepesinde `model : (bilinmiyor)` yazıyordu; başlık
oturum açılırken yazılıyor, model ilk yanıtta belli oluyor. İki modeli
karşılaştırmaya başlayınca bu gerçek bir engel oldu. Artık ilk yanıtta bir
kez düzeltiliyor.

Testler: 567 → **627** yeşil (geri_al 36→64, islem 87→105, tam_tur
100→114). Sabit istem 4991 → **5250** kaba token.

---

## 29. Gecikme nereden geliyor — ölçüldü

Kullanıcının sorusu: "API süreçleri yavaş, hızlandırılabilir mi?" İki
gerçek oturumun 22 turu çözümlendi.

### 29.1 Çıktı hızı sabit; fark modelin ne kadar yazdığında

| | ortanca çıktı hızı | ortalama çıktı | ortalama süre |
|---|---|---|---|
| Sonnet | 78.5 token/sn | 3 214 | 40.6 sn |
| Opus | 72.5 token/sn | 6 230 | 87.5 sn |

**Opus tur başına yavaş değil — iki kat uzun yazıyor.** Aynı hızda.

### 29.2 Bağlam gecikmeyi belirlemiyor

| bağlam | çıktı | süre |
|---|---|---|
| 92 973 | 92 | 3.9 sn |
| 15 502 | 2 486 | 36.8 sn |

Bağlamı 6 kat büyük olan tur 9 kat hızlıydı. Prompt cache çalışıyor.
**Gecikme ≈ çıktı / 75.** "Bağlam büyüdü, yavaşladık" diye bir şey yok —
sohbeti bu yüzden sıfırlamaya gerek yok.

### 29.3 Çıktının %91-94'ü düşünme

Görünür metin (mesaj + kod bloğu) günlükten sayıldı, çıktıdan çıkarıldı:

| | toplam çıktı | görünür | düşünme | pay |
|---|---|---|---|---|
| Sonnet | 38 567 | 2 414 | 36 153 | %94 |
| Opus | 62 295 | 5 570 | 56 725 | %91 |

Sonnet: 482 sn düşünme / 32 sn yazma. Opus: 756 / 74.

### 29.4 `--effort` — kullanmadığımız kol

Aynı istem, 3 tekrar, sonnet:

| effort | süreler | ortanca | çıktı token |
|---|---|---|---|
| low | 37 · 43 · 37 | **37.0 sn** | 2 774 |
| (varsayılan) | 109 · 126 · 116 | 116.1 sn | 9 820 |
| high | 123 · 130 · 149 | **129.6 sn** | 11 408 |

`low` **3.1 kat** hızlı; üçünde de çalışan kod çıktı. Opus'ta 87.0 → 44.4
(2.0 kat).

**`high` varsayılandan DAHA YAVAŞ.** İlk tek örnekte 48 sn çıkmış ve
"dengeli orta seçenek" diye yazılmıştı; tekrarlı ölçüm çürüttü ve seçenek
listeden çıkarıldı. Tek örnekle seçenek yazmanın bedeli buydu — tablo iki
uçlu, ortası yok.

**KALİTE ÖLÇÜLMEDİ.** Test sistem sözleşmesi ve CLAUDE.md olmadan koştu.
"low daha iyi" denmiyor; "düşünme miktarı ayarlanabilir" deniyor.
Varsayılan DEĞİŞTİRİLMEDİ, seçim panele konuldu.

### 29.5 Bizim yükümüz sıfıra yakın

Duvar saati (kullanıcı mesajı → AI satırı) eksi CLI'ın kendi `duration_ms`'i:

| | ilk tur | sonraki turların ortancası |
|---|---|---|
| Sonnet oturumu | 5.4 sn | **-0.1 sn** |
| Opus oturumu | 7.2 sn | **0.5 sn** |

İlk tur süreç açılışı (`KaliciTransport` bunu zaten bir kereye indirmişti).
Sonrası ölçüm gürültüsü içinde. **Süreç başlatma, stdin yazma, akış
ayrıştırma, panel — hiçbiri gecikmeye katkı vermiyor.**

### 29.6 Ama seansın yarısı API değil

Sonnet oturumu, 1296 sn:

| | süre | pay |
|---|---|---|
| AI (düşünme + yazma) | 637.7 sn | %49 |
| **kullanıcının Çalıştır'a basmasını bekleme** | **341.0 sn** | **%26** |
| kullanıcının okuması/yazması | 167.0 sn | %13 |
| kod çalışması | 150.4 sn | %12 |

### 29.7 İkinci kol: isteğin belirginliği

Daha önce ölçülmüştü (config.MODELLER yorumu), burada da geçerli. Aynı
belge, aynı model:

    "kulbun karsisina kedi kafasi logosu ekle"    77 / 95 / 157 / 167 / 183 sn
    "kulbun karsisina 20 mm capinda 3 mm disk ekle"          54.4 / 55.7 sn

Belirsiz istek hem ~3 kat yavaş hem ÖNGÖRÜLEMEZ (77-183 arası zıplıyor).
Efor kolu düşünmenin miktarını kısıyor; bu kol düşünülecek şeyi azaltıyor.

### 29.8 Bulunan yan hata: model değişimi hiç uygulanmıyormuş

`--model` ve `--effort` süreç **başlarken** veriliyor, süreç ise turlar
boyunca ayakta kalıyor (sınıfın varlık sebebi: tur 1 = 8.5 sn, tur 2 =
2.4 sn). Yani oturum ortasında model değiştirmek **hiçbir şey
yapmıyordu** — kutunun ipucu "sonraki mesajdan itibaren geçerli" diyordu
ve bu doğru değildi.

`ayarlar_degisti()` eklendi: boştaki süreci öldürür, sonraki tur
`--resume <oturum>` ile yeni argümanlarla başlar, **bağlam kaybolmaz**.
Tur ortasındaysa dokunmaz — akan yanıtı kesmek ayarın bir tur geç
uygulanmasından pahalı — ama unutmaz, tur bitince uygular.

### 29.9 Panel yeri

Efor kutusu için 86 px lazımdı. "Kayıt" düğmesini silmek TEK BAŞINA
yetmedi:

    Kayıt yok + model(186) + efor(102)  -> panel 600  TAŞAR
    Kayıt yok + model(102) + efor( 90)  -> panel 504  sığar

Model kutusu da kısaldı ("Opus · iyi" → "Opus"); kalite notu zaten öğe
ipucundaydı. "Kayıt" düğmesinin işlevi **sağ tık menüsüne** taşındı —
günlükler bu projede kalite analizinin tek kaynağı, erişim silinemezdi.
Panel asgari **504 px**, %40 hedefinin 88 px altında.

Testler: 627 → **649** yeşil (panel 49→60, tam_tur 114→126).

---

## 30. `kesit_konturu` yalan söylüyordu — ve hız onu kurtarmıyor

`LOG/2026-08-24_5f9d2adc.txt` bu projenin en iyi oturumu: **12.6 dakika**
(önceki karşılaştırılabilir oturumlar 21.6 ve 25.1 dk), toplam çıktı
17.1 k token (62.3 k idi), tur başına 18.2 sn (87.5 idi), Çalıştır'ı
bekleme 40 sn (341 idi) ve ilk kez baskıya hazır bir dosya çıktı:
`tavsan_govdeli.3mf`, kapalı, kesişmesiz, non-manifold yok.

Ama ilk çalıştırma **124.6 saniye** sürdü ve modeli yanlış yere götürdü.
İkisinin de sebebi `kesit_konturu`'ydu.

### 30.1 Düz yüzeye denk gelen kesit sessizce bozuk

Ölçüldü — hiçbiri hata vermiyor:

| parça | z | verdiği alan | doğrusu |
|---|---|---|---|
| silindir r=15 h=40 | 0 | **7.2** | 706.9 |
| silindir r=15 h=40 | 40 | **7.2** | 706.9 |
| kutu 20×30×10 | 0 | **300** | 600 |
| kademeli parça | 10 (omuz) | **600** | 1600 ya da 400 |

Sonuncusu en sinsisi: değer ne alttakine ne üsttekine eşit, ikisinin
arasında uydurma bir sayı. Bu, gönderdiğim yardımcıda açık bir hataydı.

Düzeltme iki parçalı, çünkü iki durum aynı değil:
* **uçta** (bbox sınırı) — istenen kesit odur, sadece tam sınırda OCC
  bozuluyor: içeri kaydırılıyor ve söyleniyor.
* **iç yatay yüzeyde** — hangi tarafın istendiği çağırana ait bir karar:
  uyarı veriliyor ve iki güvenli komşu z yazılıyor.
* **parçanın dışında** — kaydırılmıyor. Kaydırmak sorulmayan soruyu
  cevaplamak olurdu; ilk yazışta bunu yapmıştım, test yakaladı.

Yatay yüzeyler mesh'ten tek geçişte çıkarılıyor (facet normali ±Z),
kabukla birlikte önbelleğe giriyor.

### 30.2 `Mesh.crossSections` REDDEDİLDİ

673 kat hızlı (0.03 sn / 20.0 sn, altı kesit) ve cazipti. Ölçüldü:

| durum | crossSections | OCC | doğru |
|---|---|---|---|
| küre ekvatoru | alan **0.0**, çevre 2× | 7848 ✓ | 7854 |
| kutu z=0 | **300** | 300 | 600 |
| kutu z=10 | 600 ✓ | 599.8 ✓ | 600 |
| boru z=5 | 1248.6 ✓ | ✓ | 1256.6 |

Küre ekvatorunda yolu iki kez dolaşıyor (düzlem tam bir köşe halkasından
geçiyor); alan sıfırlanıyor. İzoperimetrik oranla bu yakalanıyor **ama**
kutu z=0 durumu yakalanmıyor (oran 0.1548, makul bir değer). Yani hızlı
yol sessizce yanlış cevap verebiliyor ve bunu güvenilir biçimde tespit
edemiyorum.

Kullanıcının kuralı: *"yanlış ölçüm yapmasın, daha hızlı olsa bile
kalite kaybetmeyi göze alamayız."* Reddedildi. Envanterdeki ikinci "var
ama kullanılamaz" bulgusu (birincisi `Mesh.unite()`, 27.1).

### 30.3 Kabuk önbelleği — ölçülen kazanç 1.5 kat, iddia ettiğim 6 değil

İlk hipotezim "dönüşüm tekrar tekrar ödeniyor, 124 sn → 20 sn olur"du.
Ölçüm çürüttü:

    makeShapeFromMesh (4512 facet)  1.84 sn   — bir kez
    slice                           2.76 sn   — ÇAĞRI BAŞINA
    discretize                      0.04 sn

Asıl maliyet OCC'nin `slice`'ı ve o bizim elimizde değil. Önbellek
27.8 → 18.6 sn (1.5 kat) kazandırıyor; bedava ve doğru ama küçük.
`z` artık liste de alabiliyor (`{z: konturlar}` döner), böylece altı
yükseklik bir dönüşüm ödüyor.

### 30.4 Sayılar şeklin ne OLDUĞUNU söylemiyor

Model 124.6 saniyelik ölçümden sonra *"karın boşluğu x=−85.7…−62.1,
23.6 × 27.7 mm"* dedi ve kubbeyi oraya koydu. **Orası kulak arasıydı.**
İkinci sayısal geçişte de aynı hatayı yaptı.

Kullanıcı kuralı kendisi söyledi: *"fotoğraf çek sonra ölç sonra yap."*
Model 4.9 saniyelik bir turda sadece `GORSEL-KONTROL 3` yazdı, baktı ve
doğru teşhisi koydu: *"tavşanın gövdesi yok, kulak arasındaki boşluğu
karın sanmışım."* Bir önceki oturumda aynı teşhise üç başarısız
denemeden ve ~19 dakikadan sonra ulaşılmıştı.

Sözleşme buna göre değişti — ilk ölçüm artık **üç kanıt türü**:
`kesif()` + işe özel en az iki ölçüm (`kesit_konturu(o, [z1, z2, z3])`
gibi) + `GORSEL-KONTROL 3`, hepsi **aynı turda**. Ve: parçanın ne
olduğunu tek cümleyle söyleyemiyorsan inşaya başlama, bir okuma bloğu
daha iste.

### 30.5 Diğerleri

* **Efor günlük başlığına girdi.** Modeli eklerken unutmuştuk ve hemen
  ardından "hangi eforla çalıştı" sorusunu logdan cevaplayamadık. Oturum
  ortasında değişirse `AYAR DEGISTI` satırı düşüyor.
* **`baski_kontrol` katıya da cevap veriyor.** Model 14:20:44'te onu
  birleştirmenin sonucuna çağırdı ve tek aldığı cevap *"mesh degil,
  kontrol edilmedi"* oldu — oysa dilimleyiciye giden şey zaten mesh.
  Artık 0.1 mm sapmayla mesh üretip ona bakıyor ve bunu söylüyor.
* **`Part::Fusion` diye bir tip yok** → `Part::MultiFuse`, `.Shapes`
  listesiyle. Oturumun tek hatası buydu, model 11 saniyede kendi
  düzeltti ama bir tur yedi. CLAUDE.md'ye girdi.

Testler: 658 → **678** yeşil (islem 105→117, executor 25→30, tam_tur
126→128). Sabit istem 5250 → **5457** kaba token.

---

## 31. "Sağ taraf gözükmüyor" — suçlu mesaj balonu değil, kod kartıydı

Şikayet: *"mesajlarda bazen göremiyorum, özellikle AI cevabı sağ tarafta
kalıyor ve gözükmüyor bazı kelimeler"*. İlk şüpheli mesaj balonuydu
(§26'da `SaranEtiket`'i tam da bunun için yazmıştık) ama ölçüm başka
yeri gösterdi.

### 31.1 Ölçüm

`tests/test_panel_fc.py`, offscreen ama **gerçek widget'larla**: panele
üç mesaj + bir kod kartı (iki ek düğme görünür, durum yazısı dolu)
konur, dört genişlikte her görünür alt widget'ın sağ/alt köşesi panelin
içinde mi diye bakılır.

| | kart asgari | 368 px | 420 px | 520 px | 900 px |
|---|---|---|---|---|---|
| eski | **911 px** | kırpık | kırpık | kırpık | kırpık |
| yeni | **278 px** | temiz | temiz | temiz | temiz |

Yani sorun "dar panelde" değildi: **her genişlikte** vardı. Tek bir kod
kartı bütün sohbet akışını 911 px'e geniyordu, panel 900 px olsa bile
sığmıyordu — ve panelde yatay kaydırma bilinçli olarak kapalı (§26),
dolayısıyla fazlası kaydırılamıyor, doğrudan kırpılıyordu.

Kaynak: kartın düğme satırı düz bir `QHBoxLayout`'tu. `Çalıştır` +
`Kopyala` + `Hatayı AI'a gönder` + `Uyarıları AI'a gönder` + durum
yazısı yan yana 766 px istiyor ve bunu **asgari** olarak dayatıyordu.

### 31.2 Karar: sarma, kısaltma değil

Reddedilen iki yol:

* **Etiketleri kısaltmak.** Dar panelde yine yetmez, üstelik "Hatayı
  AI'a gönder" düğmesinin ne yaptığı düğmenin üstünde yazıyor olmalı.
* **Yatay kaydırmayı açmak.** Dar bir yan sütunda sağa kaydırılan metin
  okunmuyor — bu zaten §26'da ölçülüp reddedilmişti.

Seçilen: `code_card.SaranSatir`, Qt'nin FlowLayout deseni. Sığmayan öge
**alt satıra** düşer; genişlik ne olursa olsun her düğmenin **tam
etiketi** görünür, yalnızca satır sayısı artar (düğme satırı 900 px'te
20 px, 360 px'te 90 px). Layout'un `minimumSize`'ı satırın toplamı değil
**en geniş tek öge** — kartın genişlik dayatması tam orada kırılıyor.

Bir tuzak: kartın yüksekliği artık genişliğine bağlı ve Qt'nin varsayılan
boyut politikası bunu kapalı tutuyor. Açılmasaydı yatay taşmayı çözüp
yerine **dikey** taşma koymuş olurduk — düğmeler alttan kırpılırdı.
`sizePolicy().setHeightForWidth(True)` bu yüzden var.

### 31.3 Yanında: geri/ileri düğmeleri ikona döndü

Aynı şikayetin ikinci yarısı "yanlış genişlikte olabiliriz"di. Panelin
asgari genişliğini hâlâ üst satır belirliyordu ve metin düğmeleri Qt'nin
**80 px'lik taban**ına oturuyordu. İkona çevrilince o taban kalktı:

| | üst satır | panel asgari |
|---|---|---|
| metin düğmeleri | 492 px | **504 px** |
| ikon düğmeleri | 356 px | **368 px** |

İkonlar araç çubuğundakinin aynısı (`caddy-undo.svg` ve yatay aynası
`caddy-redo.svg`) — kullanıcı aynı şekli iki yerde aynı iş için görüyor.
Etiket kaybı telafi edildi: **ipucunun ilk satırı artık düğmenin adı**,
altında da eski tam cümle duruyor. İkon yüklenemezse düğme metne döner
(`_ikon_dugmesi`), yani hiçbir halde boş bir kare kalmıyor.

### 31.4 Üç açılı görüntüden sonra kamera geri gelmiyordu

Şikayet: *"3B görüntüler aldıktan sonra saçma bir yere gidiyor,
kullanıcının ilk baktığı açıda kalmıyor"*. `yakala_cok` zaten
`setCamera` ile geri yüklüyordu — ama `viewFront`/`viewTop` FreeCAD'de
**canlandırmalı** geçiş yapıyor. Geri yükleme animasyonun ortasına
düşüyor, süren animasyon kamerayı hedefe (üst görünüme) taşıyıp geri
yüklemeyi sessizce eziyordu. Aynı sebep kareleri de bozuyordu: animasyon
ortasında alınan kare yamuk bir açı gösteriyor.

Düzeltme üç satır: açı değiştirmeden önce `setAnimationEnabled(False)`,
geri yükleme `finally` içinde (araya bir istisna girse bile kullanıcının
görünümü geri gelsin), `saveImage`'dan önce `Gui.updateGui()`.

`gorunum.py`'nin başındaki *"başsız test edilemez"* notu artık yarı
doğru: görüntünün kendisi ölçülemiyor ama modül `FreeCADGui`'yi
**fonksiyon içinde** import ettiği için `sys.modules`'a sahte bir GUI
konabiliyor. `tests/test_gorunum_fc.py` (13 kontrol) çağrı sırasını
sınıyor: animasyon `viewFront`'tan önce kapanıyor mu, `setCamera`
animasyon kapalıyken mi çağrılıyor, ve **açı değiştirme patlasa bile**
kamera geri geliyor mu (üç ayrı çağrı tek tek patlatılarak).

Testler (bu makinede sayıldı, `freecadcmd` ile 11 dosya): 688 → **714**
yeşil — panel 69→82, `test_gorunum_fc.py` yeni dosya olarak +13.
(`test_initgui_kapsam.py` özet satırı basmıyor, sayıya dahil değil.)

### 31.5 İkon düğmelerinin boyu satırdaki diğer düğmelerden uzundu

İkona çevirirken düğmeye `setFixedSize(30, 30)` verilmişti — genişliği
kazanmak içindi ama **yükseklik de** sabitlenmiş oldu. Kullanıcı gördü:
*"geri al ve ileri alın boyları diğer butonlarla aynı olsun, daha yüksek
gibi"*. Ölçüldü (offscreen, gerçek widget'lar, yerleşim koştuktan sonra):

| | yükseklik |
|---|---|
| `Yeni` düğmesi | 20 px |
| model / efor kutuları | 22 px |
| geri/ileri (eski, sabit) | **30 px** |
| geri/ileri (yeni) | 20 px |

Artık yalnızca **genişlik** sabit; yükseklik `_yuksekligi_esitle` ile
komşu **metin düğmesinden ölçülüp** veriliyor. Sabit sayı yazmak yerine
ölçmenin sebebi: düğmenin doğal boyu üsluba/temaya/yazı tipine göre
değişir, başka makinede yine tırtıklı satır olurdu.

Ölçüt neden kutular değil de `Yeni` düğmesi: bu satırda Qt'nin kendi
doğal boyları zaten eşit değil (20'ye 22) ve bu **önceden de** böyleydi.
İkon düğmesini kutuya denklersek metin düğmesinden ayrışır — göze çarpan
tam olarak *düğmeler* arasındaki fark. İkon boyutu da yüksekliğe
bağlandı (çerçeve payı için −6 px), yoksa Qt ikonu kırpıp bulanıklaştırıyordu.

İlk ölçüm yalan söyledi: panel `show()` edilmeden çocuklar yerleşime hiç
girmiyor, hepsi varsayılan 640x480'de kalıyor ve test *"480 != 22"*
diyordu. Aynı tuzak 31.1'de de yaşandı; teste yorum olarak yazıldı.

Panel testi 82 → **88** kontrol (dört yeni kontrol: her iki düğme için
"boyu `Yeni` ile aynı" ve "satırın en uzunu değil"; genişliğin hâlâ dar
kaldığı da sınanıyor ki boy düzeltmesi 31.3'ün kazancını geri almasın).

## 32. Yelkenli oturumu (2026-08-26 a0bb49dd) — en büyük günlüğün söyledikleri

31 dakika, 13 kullanıcı turu, 17 kod çalıştırma, 100 KB günlük. Efor
**"Hızlı (az düşünür)"**; yanıtlar 6–47 sn. Bu, deponun en büyük
günlüğü ve ilk kez *estetik* bir iş: basılmayacak bir yelkenli gemiye
yelken, bant dikişi, etek kavisi ve küpeşte eklendi.

### 32.1 Ne işe yaradığı ölçüldü

| | sayı |
|---|---|
| kod çalıştırma | 17 (16 başarılı, **1 hata**) |
| görsel kontrol (3 kare) | 13 · toplam ~1.86 MB PNG |
| geri al — AI'ın kendi kararı | 2 |
| geri al — kullanıcı | 1 |
| bağlam | 16.8k → 145k token |

**Üç kare kendini bir kez daha ödedi.** AI iki kez kendi çıktısını
görüntüden reddetti — kod hatasız çalışmış, doğrulama temiz geçmişti:

- *"her bant üstte ve altta birer sert kenar bıraktığı için … yan
  görünüşte yelken bez değil, fıçı çemberi sarılmış gibi duruyor"*
- *"küpeşte zigzag çıktı — üstten bakışta testere dişi"*, sebebi de
  doğru teşhis edildi: borda hattında iki ayrı kenar zinciri var,
  x'e göre sıralama ikisi arasında gidip gelmiş.

İkisi de **tek açıdan görünmeyecek** hatalar (biri yan, biri üst
görünüşte). §31.4'te kamerayı düzeltmemizin sebebi de bu turlar.

**"Beğenmedim → geri al → yeni öneri" döngüsü çalıştı.** Kullanıcı
*"direk direk yapalım beğenmezsem sileriz"* ve *"önerilerini deneyelim
beğenmezsen geri alırız"* diyerek geri alma yığınına doğrudan güvendi.
`ILERI YIGINI SILINDI (1 adim)` uyarısı üç kez tam doğru anda çıktı.

### 32.2 Sivrilen sorun: 31 kez "açık kabuk"

43 doğrulama bulgusunun **31'i** aynı satır: *"açık kabuk — 1 kabuk
kapalı değil — isValid() bunu geçirir ama basılamaz"*. Bu oturumda
yelkenler ve küpeşte bilerek `Solid=False` yüzey; kullanıcı zaten ilk
turda *"bunu basmayacağız o yüzden boşver oraları, estetik olarak güzel
olmasını istiyorum"* demişti. Yani uyarı teknik olarak doğru, **bu iş
için yanlış alarm** — ve 31 tekrarla hem çıktının hem bağlamın içini
doldurdu.

Not olarak bırakılıyor (henüz yapılmadı): bağlamda "basılmayacak"
bilgisi varken veya nesne bilerek yüzeyken açık kabuk bulgusu
BULGU'dan bilgi satırına inmeli, hiç değilse **aynı bulgu tekrar
ederse tek satırda toplanmalı** ("11 nesnede açık kabuk").

### 32.3 Bağlamın büyümesi görüntüden

16.8k → 145k token artışın büyük kısmı 39 karelik görüntü (13 × 3).
`gorunum.py`'de yazılı olan "büyütmek token maliyetini doğrudan
artırır" notu burada gerçek ölçekte görüldü. Karar değişmiyor —
görüntü iki hatayı yakaladı, bedeline değdi — ama sık görsel kontrol
yapılan uzun oturumlarda bağlamın ne kadar hızlı dolduğu artık kayıtlı.

### 32.4 Tek kod hatası

`ArcOfCircle constructor expects a circle curve and a parameter range
or three points` — AI bir sonraki turda kendi düzeltti. 17 çalıştırmada
1 hata, ve hata metni doğrudan sebebi söylediği için tek turda kapandı:
hata izinin panele tam basılması (§ executor) burada da işini gördü.

## 33. Sözleşme baskıya gömülmüştü — "bu tasarım ne için?" sorusu eklendi

§32'de ölçülen şey buydu: kullanıcı ilk turda *"bunu basmayacağız,
estetik olarak güzel olsun"* dedi, doğrulama yine de 43 bulgunun
**31'inde** "açık kabuk — **basılamaz**" diye bağırdı. Sözleşmede
`IS IT PRINT-READY` ve `PRINT-READY OUTPUT` başlıkları vardı; CNC, sac,
kalıp, analiz ya da "sadece görsel" diye bir dünya yoktu. Kullanıcının
sözü: *"belki 3D yazıcıda basmayacağım, bunu en başta sorsun — tasarımı
ne için yapmak istiyorsunuz gibi… seçenekler a b c d gibi olsun, son şık
da diğer olur"*.

### 33.1 Soru nereye kondu

**İlk ölçümden sonraki cevaba.** Parçanın ne olduğunu bilmeden sorulan
amaç sorusu boş bir anket olur; ölçüm + üç kare zaten ilk turda geliyor,
soru onun üstüne biniyor ve **ek tur harcamıyor**. Boş belgede (sıfırdan
parça) ilk cevapta soruluyor.

Şıklar: (a) 3B baskı, (b) CNC talaşlı, (c) sac/lazer, (d) enjeksiyon
kalıbı, (e) analiz/STEP devri, (f) sadece görsel, **(g) diğer**. Oturumda
**bir kez**; kullanıcı geçerken söylediyse ("CNC'de kesecek") o cevap
sayılıyor, "farketmez" denirse (f) varsayılıp devam ediliyor.

### 33.2 Amaca göre kurallar (internetten derlendi)

Sayılar sözleşmeye tek tek yazıldı, çünkü "CNC için uygun tasarla" gibi
genel öğütler günlüklerde tetiklenmiyor; tetiklenen şey **adı konmuş
sayı**.

| amaç | sözleşmeye giren kritik kurallar |
|---|---|
| **FDM baskı** | duvar ≥ 0.8–1.2 mm (yük varsa 1.5), çıkma 45°, köprü ~10 mm, geçme boşluğu 0.2 sıkı / 0.3–0.4 kayar, tolerans ±0.3 mm |
| **CNC** | iç dik köşe **yarıçapsız olamaz** (R ≥ derinlik/10 + 0.5, asla < 1 mm), cep derinliği ≤ 3–4× genişlik, min duvar 0.5 alu / 0.8 çelik / 1.0–1.5 plastik, alttan kesme = ikinci bağlama |
| **Sac/lazer** | her yerde **sabit kalınlık**, büküm yarıçapı ≥ t, delik büküme ≥ 2.5t + R (kanal 4t + R), delik çapı ≥ t, kenar payı 1.5t, iç köşeye ≥ 0.5 mm radyus |
| **Kalıp** | **tek tip duvar** 1.5–4 mm (geçiş ≥ 3× fark boyunca), kaburga duvarın %50–65'i ve ≤ 3× yükseklik, çıkma açısı ≥ 1° (kaburgada min 0.5°) |
| **FEA / devir** | tek temiz katı; yük taşımayan ince radyus, yazı, delik **sadeleştirilir** — ama yük yolundaki radyus kalır (gerilme orada) |
| **Sadece görsel** | imalat uyarısı **yok**: açık kabuk, sıfır kalınlık, değmeyen parça sorun değil; dikkat orana ve siluete harcanır |

### 33.3 Çıktı biçimi amaca bağlandı + ölçülmüş bir STEP tuzağı

Baskı → `.3mf`/`.stl`; CNC/kalıp/FEA/devir → **`.step`** ("CNC'ye mesh
göndermek yanlış cevap, faceti geri alınamaz"); sac → düz `.dxf`;
görsel → `.obj`/`.stl`.

Bu makinede ölçüldü (freecadcmd 1.1.3):

- `Mesh.export`: `.stl .3mf .obj .ply .amf .off` çalışıyor; `.gltf/.glb`
  **yok**. `Part.export`: `.step .iges .brep` çalışıyor, **`.dxf`
  desteklenmiyor** — DXF için `importDXF.export([obj], yol)` (denendi,
  5839 baytlık geçerli dosya yazdı).
- **STEP şeması tuzağı:** FreeCAD'in kendi
  `Preferences/Mod/Import/hSTEP → Scheme` parametresini `AP242DIS`
  yapmak çıktıyı **değiştirmedi** — `Part.export` da `Import.export` de
  yine AP214 yazdı (`FILE_SCHEMA AUTOMOTIVE_DESIGN … 214`). Çalışan tek
  yol pythonocc: `Interface_Static.SetCVal("write.step.schema",
  "AP242DIS")` → dosya gerçekten
  `AP242_MANAGED_MODEL_BASED_3D_ENGINEERING` çıktı. Sözleşme bu yolu ve
  "yazdıktan sonra FILE_SCHEMA satırını bas" kuralını taşıyor.

### 33.4 Bulgular artık amaca göre okunuyor

Doğrulama maddesine (c) fıkrası eklendi: bilerek yüzey olan bir nesnede
"açık kabuk" **kusur değildir** ve kusur diye raporlanamaz; katı olması,
boolean'a girmesi ya da basılması gerekiyorsa kusurdur. Ayrıca aynı bulgu
nesne nesne tekrarlanmayacak — *"11 nesnede açık kabuk, hepsi bilerek
yüzey"* tek satır. (§32'de bu satır 31 kez basılmıştı.)

### 33.5 Bedeli

Sözleşme 12 009 → 17 393 karakter (~3.0k → ~4.3k token; §34'teki
derinleştirmeyle **20 404** karaktere, ~5.1k token'a çıktı). Bu, oturum
başına bir kez ödenen ve önbelleğe giren bir maliyet; §32'de tek bir
oturumun 145k token'a çıktığı düşünülürse ~2.1k'lık artış ucuz.
`test_tam_tur_fc.py` 127 → 142 (§34 ile **156**) kontrol: amaç sorusu, harfli şıklar,
"son şık diğer", her amacın kritik kuralı, "CNC'ye mesh gönderme",
AP242 yolu ve bulgu okuma maddesi tek tek sınanıyor ki bir daha kazayla
baskı-merkezli hale dönmesin.

**Kaynaklar (33.2):** [Protolabs — wall thickness](https://www.protolabs.com/resources/design-tips/improving-part-design-with-uniform-wall-thickness/),
[Protolabs — draft](https://www.protolabs.com/resources/design-tips/improving-part-moldability-with-draft/),
[Protolabs — bend radii](https://www.protolabs.com/resources/design-tips/the-basics-of-bend-radii-in-sheet-metal/),
[UltiMaker — design for FFF](https://ultimaker.com/learn/design-for-fff-3d-printing-maximize-your-success/),
[Xometry — FDM design tips](https://xometry.pro/en/articles/fdm-design-tips/),
[SendCutSend — CNC guidelines](https://sendcutsend.com/guidelines/cnc-machining/),
[JLC — CNC design guideline](https://jlccnc.com/help/article/cnc-machining-design-guideline),
[Komaspec — laser DFM](https://www.komaspec.com/about-us/blog/5-key-design-tips-for-laser-cutting-dfm/),
[Fabcon — laser tolerances](https://fabcon.com/articles/sheet-metal-fabrication/sheet-metal-laser-cutting-tolerances/),
[Capvidia — AP203/214/242](https://www.capvidia.com/blog/best-step-file-to-use-ap203-vs-ap214-vs-ap242),
[Spatial — FEA ön işleme](https://blog.spatial.com/fem-preprocessing-is-the-bottleneck).

## 34. Amaca göre kuralları derinleştirme — ve iki ölçülmüş tuzak

§33 iskeleti kurdu; bu bölüm araştırmayı derinleştirip sözleşmeye
**tetiklenecek kadar somut** kuralları koydu. Ölçüt hep aynı: genel öğüt
günlüklerde tetiklenmiyor, adı konmuş sayı tetikleniyor.

### 34.1 Eklenen kurallar

**Baskı.** En sık atlanan şey **katman yönü**: XY dayanımı Z'nin 4–5
katı, yani yükü katmanları ayıracak yönde vermek parçayı kırar. Sözleşme
artık "hangi yönde basılacağını varsaydığını söyle" diyor. Reçine
(SLA) ve toz (SLS/MJF) ayrı ele alındı, çünkü kuralları FDM'e
benzemiyor: reçinede her kapalı boşluğa **iki** delik (≥ 3.5–4 mm; biri
tahliye biri hava, yoksa vakum parçayı çökertiyor), tozda her boşluğa
≥ 2 kaçış deliği ve iç kanallarda düzde ≥ 4 mm, dönüşlüde ≥ 6 mm.

**CNC.** Varsayılan tolerans **ISO 2768-m** olarak yazıldı ve asıl kural
şu: sıkı toleransı yalnızca işlevi gerektiren 2–3 yüzeye (yatak yuvası,
sızdırmazlık yüzeyi, sıkı geçme deliği) ver. Tüm parçayı sıkmak,
maliyeti boş yere katlamanın klasik yolu.

**Sac.** Büküm boşaltması (genişlik ≥ t, derinlik ≥ büküm yarıçapı —
yoksa köşe yırtılıyor), flanş ≥ 4t veya 3 mm (kısası abkanta
tutunamıyor), kıvrım payları ve "düz açınım verirken hangi K-faktörünü
varsaydığını söyle" (hava bükümde 0.33).

**Kalıp.** Göbek (boss) kuralları: dış çap ≈ 2× delik, cidar nominalin
%50–60'ı, yükseklik ≤ 3× dış çap, dip radyusu 0.25–0.5× cidar ve **asla
yan duvara tam boy yapıştırma** — ince kaburgayla bağla, yoksa görünen
yüzeyde çökme izi.

**Vida.** Amaçtan bağımsız her işte soruluyor: CNC'de diş tutunması
çelikte ≥ 1×D, alüminyumda 1.5×D, plastikte 2×D ve 3×D'den fazlası
faydasız; kör delik dişten 1–1.5 hatve daha derin delinir. Baskıda
**M4 altı basılı diş güvenilmez** — ısıyla gömülen insert ya da somun
yuvası, çevresinde ≥ 2 mm et.

### 34.2 Ölçülen tuzak 1: FEM burada gerçekten koşuyor, ama kuvvet birimi yalan söylüyor

(e) şıkkını yazarken "STEP'e devret" demekle yetinmedim, denedim.
`ObjectsFem` + gmsh + **CalculiX** (`ccx.exe` FreeCAD 1.1 ile birlikte
geliyor) `freecadcmd` altında **başsız çalıştı**:

| ankastre 100×20×10 çelik çubuk, 1000 N eksenel | çözücü | elle hesap |
|---|---|---|
| gerilme | 5.05 MPa | 5.00 MPa (F/A) |
| yer değiştirme | 0.0024 mm | 0.00238 mm (FL/AE) |

Yani boru hattı doğru. **Tuzak** aynı ölçümde çıktı:
`App::PropertyForce`'un iç birimi `mm·kg/s²` = **milinewton**.
`kuvvet.Force = 1000.0` yazmak **1 N** demek — sessizce 1000 kat hata,
ve sonuç makul göründüğü için fark edilmez.
`App.Units.Quantity("1000 N")` iç değeri 1 000 000 yapıyor, doğrusu bu.
Sözleşmeye hem birim tuzağı hem de "çözücü sonucunu elle formülle
karşılaştırmadan sunma" kuralı girdi. (İlk denemede kendi elle hesabımı
eğilme sanıp yanlış beklemiştim; `ConstraintForce` yüzey normali
boyunca, yani eksenel bastırıyor — sayı değil beklenti yanlıştı.)

### 34.3 Ölçülen tuzak 2: SheetMetal iş tezgahı bu kurulumda yok

`SheetMetalCmd` import edilemiyor. Model onu var sanıp çağırırsa tur
hataya gider; sözleşme artık "bükümü sıradan katılarla modelle,
SheetMetal komutlarını çağırma" diyor. (`ObjectsFem`, `Fem`, `BOPTools`
var; `Mesh.export` glTF **yapmıyor** — §33.3.)

### 34.4 Bedeli

Sözleşme 17 393 → **20 404** karakter (~4.3k → ~5.1k token), oturum
başına bir kez ve önbellekli. `test_tam_tur_fc.py` 142 → **156**
kontrol; eklenen 14 kontrol katman yönü, reçine tahliyesi, toz kaçış
deliği, ISO 2768-m, büküm boşaltması, K-faktörü, göbek kuralları, FEM
birimi, elle doğrulama, M4 eşiği ve SheetMetal yokluğunu tek tek
tutuyor.

**Kaynaklar (34.1):** [Fictiv — ISO 2768](https://www.fictiv.com/articles/iso-2768-an-international-standard),
[Xometry — standart toleranslar](https://xometry.pro/en/articles/standard-tolerances-manufacturing/),
[JLC — dişli delik kılavuzu](https://jlccnc.com/help/article/threaded-hole-guideline),
[Protolabs — baskıda diş ve insert](https://www.protolabs.com/resources/blog/threading-and-inserts-for-3d-printing/),
[Protolabs Network — SLA tasarımı](https://www.hubs.com/knowledge-base/how-design-parts-sla-3d-printing/),
[Materialise — PA12 (MJF)](https://www.materialise.com/en/academy/industrial/design-am/pa12-mjf),
[Protolabs — naylon (SLS/MJF)](https://www.protolabs.com/resources/design-tips/how-to-design-for-nylon-3d-printing/),
[Protolabs Network — parça yönü](https://www.hubs.com/knowledge-base/how-does-part-orientation-affect-3d-print/),
[Protolabs — sac tasarım kılavuzu](https://www.protolabs.com/services/sheet-metal-fabrication/design-guidelines/),
[HLH — göbek tasarımı](https://hlhrapid.com/knowledge/bosses-design-guide-injection-moulding/),
[FreeCAD News — FEM 1.1](https://blog.freecad.org/2025/09/09/what-is-new-in-fem-for-freecad-1-1/).

## 35. Sistem sözleşmesi ne kadar yavaşlatıyor, ne kadar büyüyebilir

Soru: *"bizim system promptumuz ne kadar büyük, her mesajda ne kadar
yavaşlık getiriyor, çok daha fazla büyütebilir miyiz?"*. Ölçüldü —
gerçek CLI (`claude.exe`), sonnet + `--effort low`, aynı önemsiz istem
("sadece 3 yaz"), her durum 3 tekrar, süre duvar saatiyle.

| durum | istem token | ortanca süre |
|---|---|---|
| A — sözleşmesiz, boş dizin | 8 887 | **3.65 sn** |
| B — + sözleşme (20 404 karakter) | 16 324 | **4.23 sn** |
| C — + `workspace/CLAUDE.md` (gerçek kurulum) | 25 512 | **4.03 sn** |
| D — 32 000 karakterlik şişirilmiş sözleşme | 20 563 | **3.85 sn** |

**Cevap: pratikte yavaşlatmıyor.** A'dan C'ye istem 16 625 token
büyüyor, süre ~0.4 sn artıyor — ve C, kendisinden 9 bin token küçük
olan B'den *daha hızlı* çıktı. Yani tekrarlar arası gürültü (±0.5 sn)
etkinin kendisi kadar büyük. Bu, §config'deki ölçümle aynı yöne
bakıyor: gecikmeyi bağlam değil **düşünme** belirliyor (çıktının
%91-94'ü düşünme, gecikme ≈ çıktı/75 token/sn).

Ölçülen tek gerçek bedel **oturumun ilk turunda**: sözleşme önbelleğe
yazılıyor (A'da 5 598, B'de 13 026 `cache_creation` token). Sonraki
turlarda hepsi `cache_read` — ucuz ve hızlı.

### 35.1 Asıl tavan gecikme değil, Windows'un argüman sınırı

Sözleşme `--append-system-prompt` ile **komut satırı argümanı** olarak
gidiyor. Ölçüldü, aynı çağrı farklı boylarla:

| sözleşme boyu | sonuç |
|---|---|
| 25 000 karakter | çalıştı (6.1 sn, önbellek yazımı) |
| 30 000 karakter | çalıştı (7.1 sn) |
| 32 000 karakter | çalıştı (steady-state 3.8–4.6 sn) |
| **40 000 karakter** | **63 ms'de öldü — "Argument list too long"** |

Yani duvar, Windows'un ~32 767 karakterlik komut satırı sınırı. Bunu
aşarsak CADdy hiç cevap veremez ve hata da GÖRÜNMEZ (CLI hiç başlamaz).
Şu anki sözleşme 20 404 karakter — sınırın **%62'si**, elimizde ~12 000
karakter yer var. `test_tam_tur_fc.py` artık bunu bekliyor: sözleşme
28 000 karakteri geçerse test kırmızıya döner (157 kontrol).

Daha fazlası gerekirse yer belli: `workspace/CLAUDE.md` bir **dosya**,
argüman sınırı yok, CLI onu kendisi okuyup önbelleğe alıyor (şu an
22 306 karakter ≈ 9.2k token, C ile B'nin farkı). Kısa ve asla
kaçırılmaması gereken kurallar argümanda, uzun kılavuz dosyada —
zaten kurulu ayrım bu.

### 35.2 Peki büyütmeli miyiz?

Gecikme "hayır" demiyor, ama ölçülmüş başka bir sınır var: *genel öğüt
tetiklenmiyor, adı konmuş desen tetikleniyor* (caddy_gelisim kayıp 2:
genel "belirsizse sor" maddesi günlüklerde yalnızca %12 tetiklendi).
Yani sözleşmeye yazı eklemek ile modelin ona uyması aynı şey değil;
uzun istem uyumu **seyreltiyor**. Kural: yeni madde, ancak bir günlükte
ölçülmüş bir kaybı kapatıyorsa ve içinde bir SAYI ya da adı konmuş bir
desen varsa giriyor. Bu yüzden §33-34'teki maddelerin hepsi rakamlı.

## 36. Açılıştaki piksel satırı sustu

Kullanıcı: *"en başta CADdy panel piksel uyarısı geliyor, gelmesin"*.
Kaynak `genisligi_ayarla`'nın her açılışta Rapor penceresine bastığı
satırdı: `panel genisligi: hedef 592px (%40), asgari 368px, gercek
592px (%40)`. §-panel'de bu satırı bilerek koymuştuk ("ayarladım deyip
geçmek, ayarlamadığını gizlerdi") — ama gizlenmesi gereken şey
*başarı* değil, başarısızlık.

Ayrım şöyle çekildi: rutin rapor `log.ayik`'e indi (ayıklama tercihi
açıkken hâlâ yazılıyor, ölçüm kaybolmadı); **hedefe ulaşılamadığı hal**
(`asgari > hedef`, yani panel istenen kadar daralamıyor) hâlâ `uyari`.
İşler yolundayken konuşmak, bozulduğunda konuşmayı değersizleştirir.

Panel testi 88 → **91** kontrol: açılışta `bilgi`/`uyari` kanalına
piksel içeren tek satır düşmediği, ölçümün `ayik`'te durduğu ve dar
pencerede (600 px, %40'ı 240 px < panel asgarisi 368 px) uyarının
gerçekten geldiği ölçülüyor.

## 37. Boş günlükler: iki sebep, ikisi de ölçüldü

Kullanıcı: *"çok fazla log var, gereksiz boş loglar oluşuyor"*. Ölçüm
(2026-08-26, `LOG/`): **106 dosya**, sınıflandırılınca:

| tür | adet |
|---|---|
| yalnızca başlık (298 bayt, tek satır içerik yok) | **42** |
| test artığı (`SilenKutu`, `patlayan`, `birinci hata`…) | **40** |
| gerçek oturum | 24 |

Yani klasörün **%77'si** çöptü ve gerçek günlükleri aramayı zorlaştırıyordu.

### 37.1 Sebep 1 — başlık hemen yazılıyordu

`oturum_ac` çağrılır çağrılmaz dosyayı açıp başlığı basıyordu. FreeCAD
açılıp panel oluşan ama tek mesaj yazılmayan her oturum geriye 298
baytlık bir hayalet bırakıyordu. Artık başlık **hazırlanıyor ama
yazılmıyor**; ilk gerçek kayıt gelince `_ekle` onu içeriğin önüne
koyuyor. Konuşulmayan oturum artık dosya üretmiyor.

Bir yan tuzak vardı: `_basliga_model_yaz` başlıktaki `(bilinmiyor)`
satırını **dosyayı okuyup değiştirerek** düzeltiyordu — dosya henüz
doğmamışken bu sessizce kaybolurdu. O yol artık önce bekleyen başlık
satırlarına bakıyor. Test bunu ayrıca ölçüyor.

### 37.2 Sebep 2 — testler gerçek `LOG/`'a yazıyordu

Küçük dosyaların içeriği testlerin kendisiydi; suite her koşuşta ~10
dosya bırakıyordu. `SohbetGunlugu` zaten `kok` parametresi alıyordu ama
`ConversationController` varsayılanı kullanıyor, dolayısıyla denetleyici
kuran her test gerçek klasöre yazıyordu. Çözüm tek noktadan:
`CADDY_LOG_DIR` ortam değişkeni. 11 test dosyasının başına eklendi
(`tests/_gunlukler/`, `.gitignore`'da).

**Ölçüldü:** tam suite koşusu öncesi/sonrası `LOG/` **106 → 106** dosya.
Eskiden her koşuşta artıyordu.

`test_koruma_fc.py` 45 → **55** kontrol: oturum açmanın diske
dokunmadığı, ilk kayıtla dosyanın doğduğu, başlığın kaybolmadığı ve
**bir kez** yazıldığı, modelin dosya sonradan doğsa da başlığa
işlendiği, `CADDY_LOG_DIR`'in kökü belirlediği.

Depoda duran eski çöp (42 + 40 dosya) **silinmedi** — kullanıcının
klasörü, silmesi onun kararı.

## 38. Üst satır tamamen ikona döndü — 5 öğeden 6'ya çıkarken daraldı

Kullanıcının kararı: *"yeni yerine artı (+) sembolü, kayıt yerine dolap
gibi kütüphane gibi bir sembol, tüm butonların boyu aynı olacak,
5 butondan 6 butona çıkacağız, ona göre butonları küçülteceğiz"*.

Ölçüldü (offscreen, gerçek widget'lar, yerleşim koştuktan sonra):

| | üst satır asgari | panel asgari |
|---|---|---|
| metin "Yeni" + 2 ikon (5 öğe) | 356 px | 368 px |
| **4 ikon düğme (6 öğe)** | **334 px** | **346 px** |

**Öğe sayısı arttı ama satır daraldı** — çünkü metin düğmesi Qt'nin
80 px'lik tabanına oturuyordu, ikon düğmesi 28 px. Boy da artık tek:
dört düğme 22 px, model ve efor kutuları 22 px — satırın tamamı aynı
yükseklikte. Ölçüt değişti: metin düğmesi kalmadığı için `_yuksekligi_esitle`
artık **kutuları** ölçüyor (§31.5'te ölçüt metin düğmesiydi, çünkü o
zaman satırda iki tür vardı ve göze çarpan düğmeler arası farktı).

### 38.1 "Kayıtlar" geri geldi, sağ tık menüsü gitti

Düğme §31.3'te üst satırdan **kaldırılmıştı** (metin hâlinde 80 px
yiyordu) ve işlevi sağ tık menüsüne taşınmıştı. Kullanıcı onu
**bulamadı** — yani taşıma başarısızdı. Görünmeyen bir menü öğesi,
olmayan bir özelliktir.

İkon olarak geri gelince aynı işlev 28 px'e sığdı. Menü ise tamamen
kaldırıldı (kullanıcının isteği): içinde tek öğe vardı ve o öğenin
varlık sebebi üst satırda yer olmamasıydı. Aynı işlevin ikinci ve gizli
kapısını tutmanın anlamı kalmadı.

İkonlar aynı kalemle çizildi (#2b6cb0, `stroke-width` 7, yuvarlak uç):
`caddy-yeni.svg` artı, `caddy-kayitlar.svg` çekmeceli dolap. İkon
yüklenemezse düğme metne dönüyor (`_ikon_dugmesi`) — işlev hiçbir hâlde
kaybolmuyor. Panel testi 91 → **97** kontrol: dördünün de ikonunun
gerçekten yüklendiği, ipuçlarının ilk satırının düğme adı olduğu, dört
düğmenin aynı boy **ve** aynı genişlikte olduğu, boyun kutularla da
eşit olduğu, ve sağ tık menüsünün artık bağlı olmadığı.

## 39. "Çakışmaları anlamıyor" — görüntü değil, SORU yanlış yere soruluyor

Kullanıcının şüphesi: *"bazen çakışmaları falan anlamıyor, acaba
görselleri yeterince analiz etmiyor mu?"*. Bugünkü oturum
(`LOG/2026-08-26_34ac9988.txt`, 18:26–18:49, 14 tur, bağlam 24k → 195k)
bunu tam olarak gösteriyor.

### 39.1 Ölçüm: görsel kontrol eksik değil, YETERSİZ

Oturumda **8 görsel kontrol, hepsi 3 kare** (138–197 KB). Yani model
bakmayı ihmal etmedi. İki kez baktı, "temiz" dedi ve **yanıldı**:

| an | modelin görüntüye bakıp dediği | kullanıcının cevabı | sonradan ölçülen |
|---|---|---|---|
| 18:33 | *"üç üçgen de … birbirinin içine girmiyor"* | *"floklardaki yelkenler uçtaki yelkenle çakışıyor içinden geçiyor"* (46 sn sonra) | `common()` → **2.7 mm³ gerçek çakışma** + iki temas |
| 18:43 | *"26 halat eklendi … hiçbir çakışma yok"* | *"kıç tarafta direkler taşmış"* | çarmık alt uçları x=−55…−67, bordanın dışında |

İki durumda da kullanıcı söyler söylemez model **doğru aracı** kullandı
ve sorunu saniyeler içinde buldu: `Shape.common().Volume`,
`distToShape()`, `slice()` ile y=0 silueti. Yani bilgi eksikliği değil,
**sıralama hatası**: görüntüye bakıp karar verdi, ölçmedi.

### 39.2 Neden görüntü bunu gösteremez — piksel hesabı

Gemi 201 × 62 × 146 mm (keşiften). Yakalama 900 × 640 (`gorunum.py`),
`fitAll` sonrası yaklaşık **4 piksel/mm**. Buna göre:

| şey | gerçek | görüntüde |
|---|---|---|
| yelken kalınlığı | 0.6 mm | ~2 piksel |
| çarmık çapı | ~1 mm | ~4 piksel |
| yakalanamayan çakışma | 2.7 mm³, ~1 mm genişliğinde | ~4 piksel, üstelik yelkenin ARKASINDA |

Yani o çakışma bizim karelerimizde **fiziksel olarak görünmüyordu**.
Model "görüyorum" diye değil, "göremediğim şeyi yok saydım" diye
yanıldı. Bu, çözünürlüğü global olarak artırmanın da tam çözüm
olmadığını söylüyor: 4 px/mm'yi 8'e çıkarmak 3 kareyi ~4 kat pahalı
yapar ve hâlâ *arkada kalan* çakışmayı göstermez.

### 39.3 Sözleşmenin payı

İki madde bu hatayı kolaylaştırıyor:

1. Görsel kontrol maddesi "parçaların gerçekten değip değmediği" gibi
   soruları **görüntüye havale ediyor** — oysa temas/çakışma sorusunun
   deterministik cevabı `distToShape` ve `common()`.
2. Onay maddesi *"doğru görünüyorsa TEK CÜMLEYLE onayla"* diyor. Bu
   kural token tasarrufu için ölçülerek konuldu (kayıp 5) ama **hızlı
   onaya doğru itiyor**: modelin iki yanlış cümlesi de tam olarak o
   biçimde, tek cümlelik onay olarak geldi.

### 39.4 Yan bulgu: keşif bütçesi yanlış yere harcanıyor

Aynı oturumun ilk ölçümünde: **52 nesne, yalnızca 8'i ölçüldü**, 44'ü
"sınır aşıldı" diye atlandı. Üstelik ölçüm süresi 0.48 sn — süre bütçesi
(3.0 sn) dolmadı, **sayı** sınırı (`AZAMI_NESNE = 8`) bitirdi. Daha
kötüsü, sıralama `doc.Objects` sırası olduğu için o 8 slotun 3'ü
hacimsiz **eskizlere** gitti (`YelkenAltKesit1`, `YelkenAltKesit2`,
`YelkenOrtaKesit1`). Yani model, çakışmasını sorduğumuz yelkenlerin
çoğunu hiç ölçmemiş oldu.

## 40. Çakışma körlüğü kapatıldı — ölçüm, otomatik tarama, yakın çekim

§39'da ölçülen kusurun beş parçası da yapıldı. Sıra bilinçliydi: önce
ölçümü mümkün kılan yardımcı, sonra onu zorunlu kılan sözleşme maddesi.

### 40.1 `cakisma_kontrol()` — ve şekil türüne göre DOĞRU test

Modelin logda iki kez elle yazdığı desen artık hazır. Ama elle yazdığı
hâli **eksikti**; gerçek OCC geometrisiyle ölçtüm ve üç ayrı testin
gerektiği çıktı:

| çift | doğru test | yanlış testin verdiği |
|---|---|---|
| katı × katı | `common().Volume` | `section()` **yan yana değen** iki kutuda 40 mm veriyor → değme "geçiş" sanılırdı |
| katı × yüzey | `common().Area` + ortak parçanın merkezi `isInside` mi | alan tek başına, katının **yüzüne yatan** yüzeyde de 100 mm² veriyor |
| yüzey × yüzey | `section()` eğrisi **ikisinin de sınırında değilse** | eğri tek başına, uç uca değen iki yüzeyde de 10 mm veriyor |

On bir hâlin hepsi ölçüldü ve doğru hüküm veriliyor (testte duruyor):
iç içe / değen / uzak katı, katının içinden geçen ve yüzüne yatan yüzey,
X gibi kesişen yüzeyler, **kenarı ötekinin içinden geçen** yüzey (logdaki
flok vakası), uç uca ve kenardan dik değen yüzeyler.

Çiftler önce **bbox** ile eleniyor: 52 nesnelik belgede 1326 çiftin
1300'ü mikrosaniyede düşüyor, tam tarama **0.33 sn**.

**Değme kusur değildir** ve öyle raporlanmıyor — bu projede yelken
direğe, küpeşte gövdeye bilerek değiyor (§32'deki 31 kez tekrarlanan
yanlış alarma dönmemek için kullanıcının verdiği karar).

### 40.2 Otomatik tarama: host söylüyor, model unutamıyor

`dogrula()` artık her çalıştırmadan sonra **dokunulan nesneleri** bbox'ı
kesişen komşularla karşılaştırıyor. Ölçülen maliyet (52 nesnelik belge):

| durum | süre |
|---|---|
| 1 nesne dokunuldu | **0.018 sn** |
| 8 nesne dokunuldu | **0.062 sn** |
| doğrulamanın tamamı (tarama dahil) | 0.031 sn |

Kullanıcının şartı "yavaşlatmıyorsa" karşılandı; hedef 0.3 sn'ydi.

İki yanlış alarm kaynağı önceden kapatıldı: (a) **boolean girdileri** —
`Part::Cut`in Base/Tool nesneleri belgede durur ve sonuçla tamamen üst
üste biner (ölçüldü: `Kesilmis.OutList = [A, B]`), bağımlılık zincirinde
akraba olan çiftler atlanıyor; (b) tekrar eden bulgu 5 satırdan sonra
tek satırda toplanıyor.

### 40.3 Yakın çekim — `GÖRSEL-KONTROL YAKIN <ad>`

Kamera nesnenin üstüne gidiyor (`Gui.Selection` + FreeCAD'in kendi
`ViewSelection` komutu), tek kare alınıyor, **kamera ve seçim `finally`
içinde geri veriliyor** — §31.4'te kurulan desenin aynısı, animasyon da
kapalı. Çağrı sırası testte birebir sınanıyor:

```
getCamera > animasyon=kapali > secim=temizle > secim+Kutu1 >
msg:ViewSelection > saveImage(YAKIN) > secim=temizle > setCamera >
animasyon=acik
```

Kullanıcının kararı gereği aynı mesajda **ölçüm de gidiyor**: host o
nesneler için `cakisma_kontrol` çalıştırıp sonucu isteme ekliyor. Yani
model yakından bakmak istediği anda sayıyı da eline alıyor, ek tur
harcamadan. `GÖRSEL-KONTROL 3 YAKIN <ad>` üç açıdan yakın çekim veriyor.

### 40.4 Keşif önceliği

`ilgili_nesneler` artık sıralı: hacimli katı → yüzeyli şekil → mesh →
eskiz/2B iskele, eşitlikte görünür olan önce, aynı sınıfta belge sırası
korunuyor. `AZAMI_NESNE` 8 → **24**; freni artık süre bütçesi koyuyor
(§39.4'te ölçülmüştü: 8'de duruyordu ama 3.0 sn'nin yalnızca 0.48 sn'i
kullanılmıştı). Ölçüldü: 24 nesnelik keşif **0.02–0.04 sn**, ilk 8 slotta
artık **hiç eskiz yok**.

### 40.5 Bedeli ve testler

Sözleşme 20 404 → **22 328** karakter (~5.6k token), Windows argüman
tavanının (28 000) altında — test bunu tutuyor.

Testler: `test_dogrulama_fc` 40 → **67**, `test_gorunum_fc` 13 → **28**,
`test_tam_tur_fc` 157 → **171**, `test_executor_fc` 50 → **53**,
`test_koruma_fc` 55 → **62**. Toplam **703** kontrol, sıfır hata.

Bu iş sırasında iki eski test de düzeldi: `test_tam_tur_fc` hâlâ
"oturum açılınca dosya oluşur" varsayıyordu (§37 ile tembel yazıma
geçmiştik) ve günlüğün `LOG/` altında olmasını bekliyordu (§37 ile
`CADDY_LOG_DIR`'e taşınmıştı). İkisi de yeni davranışa göre yazıldı —
yani S3'ün sessiz bir regresyonu bu turda yakalandı.

---

## 41. Panel 651 px'te takılıyordu — sütunu biz değil KOMŞU tutuyor

Kullanıcının bildirdiği hâl: "CADdy 651 px, 514 px olması gerekirken".
Eski kod bunu **sessizce** geçiyordu, çünkü yalnızca kendi asgarimize
bakıyordu (346 px < 514 px → "sorun yok").

### 41.1 Sebep

Qt'de bir kenardaki dock'lar **tek bir sütunu** paylaşır. Sütun, içindeki
dock'ların **en büyük asgarisinden** dar olamaz. Ölçüldü (offscreen, gerçek
widget'lar, `panel_genislik2.py`; ana pencere 1285 px, hedef 514):

| komşunun asgarisi | hedef | gerçek |
|---|---|---|
| 100 px | 514 | **514** ✔ |
| 300 px | 514 | **514** ✔ |
| 650 px | 514 | **650** ✘ |

Yani `resizeDocks` yok sayılmıyor; sütun daha fazla daralamıyor.

### 41.2 Ne yaptık, neyi yapmadık

İki tür asgari var ve ikisi ayrı davranıyor — ölçüldü:

- **Elle konmuş** `minimumWidth`: 0'a çekince hedefe ulaşılıyor (650 → 514).
  Geri koyunca sütun anında 650'ye sıçrıyor, o yüzden **geri koymuyoruz**;
  kalıcı tek etkisi o panelin daha dar çekilebilmesi.
- **İçerikten gelen** asgari (`minimumSizeHint`): tek numara komşuya kalıcı
  `maximumWidth` koymak olurdu — ölçüldü, uygulanınca 1080 → 514 oluyor ama
  kaldırınca geri sıçrıyor. Kalıcı bırakmak, kullanıcının FreeCAD panelini
  bir daha genişletememesi demek. **Yapmıyoruz**; onun yerine UYARI yazıyor
  ve engelleyen dock'u **adıyla** söylüyoruz.

Bunun kuralı §32'nin aynısı: ölçemediğimizi/yapamadığımızı gizlemek yerine
söylüyoruz. Susmak, kusuru kullanıcının gözüne bırakırdı — nitekim bu hata
bize koddan değil kullanıcıdan geldi.

Testler: `test_panel_fc` 97 → **106** (ön kabul dahil: komşunun sütunu
gerçekten genişlettiği önce sınanıyor).

---

## 42. Kütüphane artık arşiv değil, GİRİŞ — `--resume` ile eski sohbete dönüş

Kullanıcının sözü: "logdan başlatma yok galiba, sadece logu görüyorum, o
bağlamda FreeCAD'de başlatamıyorum". Düğme yalnızca klasörü açıyordu.

### 42.1 Bağlamı biz taşımıyoruz

Transport zaten `--resume <oturum>` kullanıyordu (süreç ölünce sonraki tur
böyle devam ediyor). Eksik olan tek şey kimliği **eski bir günlükten**
alabilmekti. Günlük başlığında zaten yazıyor:

    oturum : 9564dc71-071d-4ca3-9c21-483cf5766739

Yeni `caddy/kayitlar.py` (Qt'siz, §12) başlıkları okuyor; `transport.
oturumu_surdur` kimliği koyup `_ilk_tur = False` yapıyor — bu bayrak
kritik, True kalsaydı argümana `--session-id` girer ve CLI "bu kimlik
zaten var" diye reddederdi. Geçmişi CLI kendi oturum dosyasından
yüklüyor, yani bağlam kaybı yok.

### 42.2 Günlük ikiye bölünmüyor

`oturum_ac` dosya adını **bugünün** tarihinden üretiyor; dün başlamış bir
sohbeti sürdürürken ikinci bir dosya açardı. `dosyaya_devam` yolu dışarıdan
alıyor, başlığı tekrarlamıyor, araya görünür bir `DEVAM —` ayracı koyuyor.

İsim alanı **temizlenmiyor**: kullanıcı aynı FreeCAD belgesinde çalışmaya
devam ediyor, değişkenlerini silmek işine yaramaz. Sayaçlar sıfırlanıyor —
devralınan geçmişi bizim sayacımız bilmiyor, bilir gibi yapmak yanlış bir
rakam üretirdi.

Testler: yeni `test_kayitlar_fc` **24** kontrol + `test_panel_fc` içinde
düğme→denetleyici bağlantısı.

---

## 43. Tur başına kod bloğu sayısı — karar ölçümle verildi

Sorulan: "tek istekte 4-5 kod çalıştırsak kaliteyi artırır mıyız, yoksa çok
veri gelince Claude yavaşlar mı?"

### 43.1 Ölçüm — kamyonet oturumu (`2026-08-27_9564dc71.txt`)

16 kullanıcı isteği, 40 AI turu, 24 kod bloğu, 20 görsel gönderimi, 22 dakika.

| bağlam | tur | ortalama süre |
|---|---|---|
| < 50k | 9 | 14.8 sn |
| 50–100k | 13 | 16.7 sn |
| 100–150k | 8 | 18.2 sn |
| > 150k | 10 | 15.0 sn |

**Bağlam ile süre arasında korelasyon r = 0.04** (n = 40). Yani bağlam 22k'dan
200k'ya çıkarken gecikme değişmedi — "çok veri gelince yavaşlar" bu ölçekte
**desteklenmiyor**.

20 görsel gönderimi 433 KB (ortalama 21.7 KB, çoğu 3 kare) — bağlamın
kabaca üçte biri. Yani pahalı olan **kod değil, kare**.

> **DÜZELTME (2026-08-27, §44).** Burada önce şu yazıyordu: *"son tur
> 200 022 token ile pencerenin tavanına dayandı"*. **Yanlıştı.** Aynı
> oturum sürdürüldü ve sorunsuzca **345 893** bağlama çıktı; hiçbir tavana
> çarpmadı. 200 022, ölçüm yaptığım anda oturumun geldiği yerdi — tavan
> değil, sadece son satır. Yuvarlak bir sayıyı sınır sanmak, tam da bu
> projenin yasakladığı şey: *ölçülmemiş bir şeyi ölçülmüş gibi yazmak*.
>
> Kararın kendisi (kareyi kıs, kodu kısma) ayakta kalıyor ama **gerekçesi
> değişti**: mesele "pencereye sığmamak" değil, karenin pahalı ve
> **karşılığında hiçbir şey vermiyor** olması (§44.2). Sınır nerede
> gerçekten, hâlâ ölçülmedi.

İstek başına ortalama 2.5 AI turu, ~40 sn; turların 10'u kullanıcı araya
girmeden zincirlenmiş kod bloklarıydı. Her zincir halkası tam bir gidiş-dönüş
(~16 sn) demek.

### 43.2 Karar

Kullanıcının kararı: "özellikle ölçüm alınacağı zaman bir sürü kod
koşulabilir… ilk ölçümde 5-10 kod ve fonksiyon çalıştırırız… ama kaliteyi
bozmamalı ve çok yavaşlamamalı."

Sözleşmeye giren kural:

1. **Okuyan blok ucuz.** Bir blokta 5-10 ölçüm çağrısı (`kesif`, `olc`,
   `cakisma_kontrol`, `duvar_kalinligi`, `kesit_konturu`…) beş tura
   bölmekten iyidir: bloğun içindeki fazladan satır bedavayken fazladan
   tur 16 sn. Var olan bir modele bakarken ilk blokta **iyice ölç**.
2. **Yazan blok farklı.** Sonraki adım bu bloğun çıktısına ya da görünüşüne
   bağlıysa turda **bir** tane. Yalnızca gerçekten bağımsız adımlar (ilan
   edilmiş planın ayrı parçaları) **en fazla üç** blok olabilir ve neden
   güvenli olduğu bir satırda söylenir.
3. **Gereksiz blok = kullanıcının basacağı fazladan düğme.** Kalabalık
   görünmek için blok eklenmez.
4. **Üç kare varsayılan değil.** Rutin doğrulama tek kare; üç kare yalnızca
   soru gerçekten başka açı istiyorsa. Kısıntı koddan değil **kareden**
   yapılıyor, çünkü ölçüm pencereyi yiyen taraf o.

Sözleşme 22 328 → **23 882** karakter (tavan 28 000). `test_tam_tur_fc`
171 → **176**.

---

## 44. Kamyonet günlüğünün söyledikleri — çakışma gürültüsü, kare kararı, bağlam

Kaynak: `LOG/2026-08-27_9564dc71.txt` (229 KB, 4620 satır, 13:39 → 15:40,
26 kullanıcı isteği, 63 AI turu, 37 kod bloğu). §43'ün ölçümü bu günlüğün
**ilk yarısındandı**; burada tamamı okundu ve üç şey çıktı.

Önce iyi haber, çünkü kıyas noktası o: **37 kod bloğunun 35'i başarılı
(%94.6)**, iki hata da bir sonraki turda kapandı. Sürdürme özelliği
(§42) gerçekten çalıştı — 15:29:03'te `DEVAM` ayracı düştü, model sonraki
turda `KabinKesiciler` / `KabinDetay`'ı adıyla kullandı, yani `--resume`
bağlamı taşıdı. Yeni yardımcılar da kullanıldı: `cakisma_kontrol` 52 kez,
`YAKIN` çekim 20 kez, otomatik tarama 33 turda.

### 44.1 Çakışma raporunun %77'si kusur değildi

813 `ICINDEN GECIYOR` satırı = günlüğün **%17.6'sı**. İçlerinden **627'si
(%77)** şunlardı:

```
KabinDetay x Kabin:  3.78e+04 mm3      Kabin, KabinDetay'in kesilmemis hali
Teker1 x CamIc1:     904.8 mm3         CamIc1 bir kesme silindiri, parca degil
Kasa x KasaDis:      2.31e+04 mm3      KasaDis, Kasa'nin tabani
```

Hiçbiri kusur değil: bunlar boolean işleminin **tükettiği kaynak
nesneler**. `Part::Cut` tabanını sonucuyla çakışıyor diye raporlamak,
"su ıslak" demek. Kaynak kodda: `kesif._oncelik` görünürlüğü yalnızca
**sıralama** anahtarı olarak kullanıyordu, eleme olarak değil.

Bedeli somut ve §32'nin aynısı: model her turda bir feragat cümlesi
yazmak zorunda kaldı — *"ya gizli kaynak nesneler ya da tekerleklerin
kasıtlı gömülmesi — yeni bir sorun yok"*. §32'de bu 31 kez tekrarlanan
yanlış alarmdı; burada 22 kez tekrarlanan `Sasi x Teker1` oldu.

**Düzeltme:** `kesif.tuketilmis_mi(o)` — **iki şart birden**:

1. nesne başkasının hammaddesi (`InList`'teki bir üst nesnenin `Base`,
   `Tool`, `Shapes`, `Source`, `Objects`, `Profile`, `Sections`, `Spine`,
   `Sketch`, `Group` alanlarından birinde duruyor), **ve**
2. FreeCAD onu gizlemiş.

İkisi de ölçümle geldi. Yalnızca **görünürlük** yetmiyor: kullanıcı gerçek
bir parçayı geçici olarak gizlemiş olabilir. Yalnızca **referans** de
yetmiyor — ilk uygulama böyleydi ve aynı belgede `KapiKolu`yu eledi: o bir
`Part::Mirroring` kaynağı, ama FreeCAD ayna kaynağını **gizlemez**, kol
ekranda duran gerçek bir parça. `Cut`/`MultiFuse` tabanlarını ise gizler.

### 44.2 Aynı tarama hem gürültülü hem EKSİKTİ

`conversation._cakisma_metni` yakın çekimde tek nesne için çakışma
soruyordu ama kod onu belgedeki **tüm** nesnelerle çarpıyordu.
Docstring'inde *"burada ise yalnızca ilgili çiftler"* yazıyordu; kod bunu
yapmıyordu. Yani yalan söyleyen bir docstring — `kesit_konturu`'nunkiyle
(§30) aynı tür hata.

Sonuç: 2 sn bütçesi **20 kez doldu**, toplam **15 323 çift hiç ölçülmedi**.
Sorulan çift bile bakılmadan kalabiliyordu. Gürültü bütçeyi yiyor, bütçe
cevabı yiyordu.

**Düzeltme:** `cakisma_kontrol(odak=nesne)` — çiftler `odak × diğerleri`,
yani n(n−1)/2 yerine n−1.

**Ölçüm.** Tezgâh gerçek: `.caddy-backups/Araba_2026-08-27_153002.FCStd`,
günlükteki "49 nesne, 1176 çift, 539 bakılmadı" turunun tam belgesi.

| | önce | sonra |
|---|---:|---:|
| taranan nesne | 44 | **17** |
| çift | 946 | **136** |
| bulgu satırı | 38 | **8** |
| hiç ölçülmeyen çift | **431** | **0** |
| süre | 2.04 sn | **0.63 sn** |

`odak=KabinDetay` ile: 16 çift, 0.38 sn, **2 satır**. Kalan 8 bulgu
gerçek ve kasıtlı gömmeler (teker ↔ şasi) — onları susturmuyoruz, çünkü
kasıtlı olduklarına **model karar vermeli**, biz değil.

Eleme **söyleniyor**: başlık `; 27 nesne listeye alinmadi (baskasinin
kesme tabani/ayna kaynagi)` yazıyor. Ölçmediğimiz şeyi saklamak, yanlış
güven üretir (§17 dürüstlük kuralı).

**Nesneler AÇIKÇA verilirse eleme yok.** `cakisma_kontrol(a, b)` tam
olarak o ikisini ölçer. Model bir şeyi bilerek sorduysa cevabını alır;
sansür, yardım değil.

Otomatik tarama (`dogrulama._cakisma_taramasi`) da aynı elemeyi yapıyor:
`Part::Cut` yapan bir tur **üç** nesneye birden dokunur — sonuç, taban,
takım — ve taban sonucun içinden "geçiyor" görünür.

### 44.3 Kare sayısı kararı MODELDEN HOST'A alındı

§43.2'nin 4. kuralı sözleşmeye "üç kare varsayılan değil" diye yazılmıştı.
**Tutmadı:**

| | gönderim | 3 kare | ortalama boyut |
|---|---:|---:|---:|
| kural yazılmadan önce | 20 | 18 (%90) | 22 KB |
| yazıldıktan sonra | 10 | 9 (%90) | **47 KB** |

Oran zerre değişmedi, boyut ikiye katlandı. İki sebep var ve ikincisi bu
projede yeni bir olgu:

* Sözleşme 15:26'da diske yazıldı, FreeCAD ≥15:19'da açıldı — yeni metnin
  yüklendiği **kesin değil**.
* Yüklendiyse bile sohbet `--resume` ile sürdürülmüştü ve bağlamın içinde
  **40 turluk "GORSEL-KONTROL 3" emsali** duruyordu. Sistem istemindeki
  bir satır, modelin kendi geçmişindeki 40 örneği yenmiyor.

> **Kural: sözleşme değişiklikleri sürdürülen sohbetlere geriye dönük
> işlemez.** Kütüphaneden sürdürme (§42) bunun bedelini getirdi. Bir
> davranışı gerçekten değiştirmek gerekiyorsa yeri sözleşme değil, host.

**Kazanç tarafında görünen bir şey yok.** Görsel dönüşü olan 30 turun
7'sinde model gerçek bir kusur buldu — ve **yedisinde de** kararı veren
delil yazdırılan bir sayıydı:

```
"tekerlekler govdeye hic degmiyor"   -> Teker1 y=-10..-2, govde y=0     (bbox)
"sag kesiciler hicbir sey kesmiyor"  -> Kabin x KabinKesiciler 66.6 mm3 (olcum)
"izgara nisi govdenin disinda"       -> kabin hacmi 37844.5, DEGISMEDI  (hacim)
"arka baglanti 0.2 mm tasiyor"       -> x=48.6 vs 48.4                  (bbox)
```

0.2 mm, 4 piksel/mm'lik karede **beşte bir piksel**. Görüntünün tek başına
yakaladığı **tek bir bulgu yok**. Buna karşılık kullanıcının gözle
yakaladıkları ("simetrik değil", "aynalar çok kötü", "kapı kolu kalın")
zaten estetik yargılardı ve onları da görüntü modele söyletmedi.

> **BU KANITIN KUSURU VAR — okurken bilinsin.** Görüntü ile sayılar
> **aynı mesajda** gidiyor. Yani "kararı sayı verdi" gözlemi, görüntünün
> işe yaramadığını KANITLAMAZ; görüntü modele nereye bakacağını söyleyip
> sonra sayıyı okutmuş da olabilir. Elimizdeki şey gözlem, deney değil.
> Ayırmanın tek yolu birini kısıp diğerini vermek — tasarımı PLAN S9'da.
> Buradaki karar (üç kare varsayılan olmasın) bu belirsizlikte bile
> savunulabilir, çünkü kesinti tek kareye iniyor, sıfıra değil.
>
> **SONRADAN — deney yapıldı (§47).** Ayırma turu koşuldu: aynı istem
> fotoğraflı bir kez, fotoğrafsız iki kez. En iyi ve en kötü koşu aynı
> (fotoğrafsız) koldan çıktı; ayıran değişken görüntü değil **adım
> sayısı**ydı. Bu bölümün gözlemi böylece çürütülmedi ama açıklaması
> değişti — ve görsel sistemi tamamen kapatıldı, yani aşağıdaki
> `_kac_kare` kuralı artık **çalışmıyor** (kod duruyor, etkisiz).

**Yeni kural — `conversation._kac_kare()`:** üç kare hakkı yalnızca

* son blok **YENİ NESNE** ekledi (uzayda yeri hiç kanıtlanmamış bir şey
  var, tek açı "havada mı duruyor"u kapatmaz), ya da
* bu **arka arkaya ikinci bakış** (ilk kare soruyu kapatmamış)

durumunda veriliyor. `GORSEL-KONTROL 3` artık bir **istek**, emir değil.
İndirim yapılırsa modele **sebebi söyleniyor** — sessizce indirmek onu
aynı isteği tekrarlamaya iter — ve yerine ne yapacağı da: *bir sonraki
blokta ölç, `cakisma_kontrol(odak=…)`*.

### 44.4 Kesinti koddan değil, kareden: blok artık kendi kanıtını basıyor

Kullanıcının kararı: *"görüntüyü azaltalım, onun yerine çalıştırdığı kod
sayısını artıralım… tek çalıştır butonu olsun tabi ama içinde çok farklı
işler yapan bir sürü kod olabilir, analizler fonksiyonlar da dahil."*

Sözleşmeye giren madde: **her yazan blok kendi kanıtıyla biter.** Bir şey
oluşturduktan ya da taşıdıktan sonra, işe yaradığını gösterecek şey aynı
blokta yazdırılır — yeni bbox'ın oturması gereken yüzeye göre konumu,
kesmeden önceki/sonraki hacim (*hiçbir şey kesmemiş bir kesme, değişmemiş
hacim yazdırır — bu hata bu oturumda iki kez oldu*), katı sayısı,
`cakisma_kontrol(odak=…)`. Bu satırlar **zaten ödenen** gidiş-dönüşün
içinde; ek tur yok. Blok içinde fonksiyon tanımlayıp dört kez çağırmak,
dört blok yazmaktan iyidir: **bir blok çok iş yapabilir, yine tek
düğmedir.**

### 44.5 Kayıt

Sözleşme 23 882 → **25 678** karakter (tavan 28 000, §35).
`test_dogrulama_fc` 67 → **84**, `test_tam_tur_fc` 176 → **192**.
Takım toplamı 873 → **906 kontrol, 0 başarısız**.

Yan bulgu — **test yazarken düşülecek çukur:** `freecadcmd`, betikte
yakalanmamış bir istisna olunca **izi basmadan ve çıkış kodunu 0
bırakarak** sessizce ölüyor. Yeni testi yazarken `" ".join(rapor.bulgular)`
(bunlar `Bulgu` kaydı, metin değil) tam bunu yaptı: dosya yarıda kesildi,
"0 başarısız" göründü. Bir test dosyasının bittiğinin kanıtı, çıkış kodu
değil **özet satırının varlığıdır**.

---

## 45. Panel hâlâ 651 px — §41'in düzeltmesi yanlış şeyi düzeltmişti

Kullanıcı ikinci kez bildirdi: panel **651 px**, olması gereken **512**.
§41'de "çözüldü" denmişti; çözülmemiş.

### 45.1 Önce aritmetik: hedef gerçekten 512

Ekran **1280×800**, `PanelYuzde = 40` → hedef `1280 × 0.40 = 512`. Panel
651 px, yani **%51**. Kullanıcının verdiği iki sayı da tutarlı; sorun
ayarda değil, uygulamada.

### 45.2 Suçlu düğmeler değil — ölçüldü

Kullanıcının tahmini "butonları küçült"tü. Gerçek panel offscreen kurulup
her alt widget'ın asgarisi tek tek okundu:

```
panel minimumSizeHint : 346 px      (elle konmus minimumWidth: 0)
  QComboBox            102
  QComboBox             90
  QPushButton "Gönder"  80
  QPushButton "İptal"   80
  4 ikon dugme        4×28   (elle 28)
```

**346 < 512.** Yani panel hedefin çok altına inebiliyor; düğmeleri
küçültmek bu sorunda **tek piksel kazandırmaz**. §38'de üst satır zaten
ikonlaştırılmış ve asgari 504 → 346'ya indirilmişti; o iş bitmiş.

### 45.3 §41'in düzeltmesi neden işe yaramadı

§41 şunu varsaymıştı: sütunu bir **komşu dock** geniş tutuyor, öyleyse
komşunun elle konmuş asgarisini gevşet. Ölçüm o varsayımı doğrulamıştı —
ama sentetik bir kardeşle. Kullanıcının gerçek yerleşiminde hedefi aşan
bir komşu **bulunamıyor** (bulunsaydı §41'in eklediği uyarı adını
yazardı). Yani doğru bir düzeltme, yanlış bir sebep için yazılmıştı.

Geriye tek açıklama kalıyor ve kodda görünüyor: `resizeDocks` **bir kez**
çağrılıyor, hemen `addDockWidget`ten sonra. Yerleşim ise o anda oturmuş
değil. FreeCAD kapanırken dock düzenini kaydediyor; panel yeniden
eklendiğinde Qt kayıtlı genişliği geri yüklüyor ve **tek seferlik
çağrımızın üstüne yazıyor**. Bizim `_rapor`'umuz bunu görüyor, komşu
suçlu bulamıyor ve teşhissiz susuyordu.

### 45.4 Yapılan

* **İki ek deneme.** Komşu engellemiyorsa ama panel yine genişse
  `resizeDocks` tekrar çağrılıyor (en fazla iki kez). Birincisi
  yerleşimin ilk turundan, ikincisi geri yüklemeden sonra düşüyor.
  Sınırsız denemiyoruz: kullanıcı paneli elle genişletirse onunla kavga
  ederdi.
* **Başarısızlıkta tam döküm.** Eskiden yalnızca "engelleyen" komşular
  yazılıyordu; hiçbiri hedefi aşmayınca satır `bilinmiyor` diyordu ve
  teşhis elde kalmıyordu — bu sorunun iki gün sürmesinin sebebi tam da o.
  Artık aynı kenardaki **her** dock genişliği ve asgarisiyle, ana pencere
  genişliğiyle ve kaç ek deneme yapıldığıyla birlikte yazılıyor.

Test (`test_panel_fc`, 106 → **112**): sahte bir "üstüne yazan yerleşim"
kuruluyor — ilk `resizeDocks`ten hemen sonra genişlik 651'e geri
konuyor — ve panelin yine hedefe döndüğü, bunu yaparken gerçekten ikinci
bir çağrı yaptığı ölçülüyor.

### 45.4b Cevap geldi: sebep komşu değil, BİZ — ve offscreen ölçüm yalan söylüyordu

Kullanıcı Rapor penceresini yapıştırdı:

```
[CADdy] panel hedefe ulasamadi: hedef 512px, gercek 651px,
        kendi asgarimiz 651px, ana pencere 1280px, 2 ek deneme yapildi
```

**`kendi asgarimiz 651px`.** Oysa §45.2'deki offscreen ölçüm aynı panel
için **346 px** demişti. İki sayı arasındaki 305 px'lik fark tek bir
şeyden geliyor: **yazı tipi.** `QT_QPA_PLATFORM=offscreen` altındaki yedek
font, FreeCAD'in gerçek arayüz fontundan çok daha dar; metne bağlı her
asgari (kutular, düğmeler) orada olduğundan küçük çıkıyor.

Yani §45.2'nin "düğmeler suçlu değil, 346 < 512" sonucu **geçersiz** —
ölçüm aleti bozukmuş. Ve bu, aynı hatanın üçüncü tekrarıydı: §41'deki
"komşu dock sütunu tutuyor" teşhisi de sentetik bir kardeşle offscreen
doğrulanmıştı.

> **Kural: yazı tipine/stile/DPI'a bağlı bir arayüz ölçüsü offscreen
> ÖLÇÜLEMEZ.** Simüle edilebilir olan geometri ve mantık; piksel değil.
> Böyle bir sayı gerekiyorsa kod onu Rapor penceresine yazar, ölçüm
> çalışan FreeCAD'den gelir. Kullanıcının sözü: *"sen kendi ui testi
> yapma, bana sor, ben sana Report view'dan atayım."*

`_asgari_dokumu()` bunun için eklendi: hedefe ulaşılamadığında ve taban
bizdeyse, panelin en geniş asgariye sahip 10 alt widget'ı yol/metin/hint/
elle-asgari dörtlüsüyle Rapor penceresine yazılıyor. Bir sonraki açılış
suçluyu adıyla söyleyecek.

### 45.4c Suçlu: FreeCAD'in tema stil sayfası, bizim `setFixedWidth`i eziyordu

Döküm geldi:

```
106px (hint 106, elle 106) /QPushButton
106px (hint 106, elle 106) /QPushButton
106px (hint 106, elle 106) /QPushButton
106px (hint 106, elle 106) /QPushButton
106px (hint 106, elle 106) /QPushButton  metin='Gönder'
106px (hint 106, elle 106) /QPushButton  metin='İptal'
 97px (hint  97, elle 0)   /QComboBox    metin='Opus'
 88px (hint  88, elle 0)   /QComboBox    metin='Hızlı'
```

Dört ikon düğmesinin **elle konmuş** asgarisi 106 px — oysa
`_ikon_dugmesi` açıkça `setFixedWidth(28)` diyor. Üst satır böylece
`4×106 + 97 + 88 + aralıklar ≈ 651`, yani gördüğümüz sayının tamamı.

Sebep: FreeCAD'in tema stil sayfasında `QPushButton { min-width: … }`
var ve Qt bunu polish sırasında **widget üzerinde `setMinimumWidth()`
çağırarak** uyguluyor — bizim satırımızın üstüne yazıyor. `setFixedWidth`
bir öneri değil, ama stil sayfası ondan sonra geliyor.

Bir kural stil sayfasıyla konduysa ancak stil sayfasıyla kalkar: kaskadda
daha **özel** olan kazanır ve widget'ın kendi sayfası uygulamanınkinden
özeldir. `_ikon_dugmesi` artık düğmeye kendi sayfasını takıyor
(`min-width` + `max-width` + dar dolgu). Diğer tema kuralları — renk,
kenarlık, hover — kaskadda duruyor; yalnızca genişlik eziliyor.

**Test piksel ölçmüyor** (o sayılar offscreen yalan söylüyor); ölçtüğü şey
**kaskad**, ve o her makinede aynı. Ön kabul de içinde: aynı tema kuralı
altında çıplak bir `setFixedWidth(28)` düğmesi **108 px**'e çıkıyor —
kullanıcının gerçek 106'sıyla birebir — bizimkiler 30'da kalıyor.
Tuzağın var olduğu kanıtlanmadan tuzağın kapatıldığı iddia edilmiyor.

`test_panel_fc` 112 → **116**.

**DOĞRULANDI (2026-08-28).** Kullanıcı FreeCAD'i yeniden başlattı, panel
hedefe indi ve `panel hedefe ulasamadi` uyarısı hiç düşmedi. Üç turdur
açık olan sorun kapandı.

### 45.6 Bu işi asıl çözen şey

Üç tur boyunca yanlış yeri kazdım: komşu dock'lar (§41), düğme metinleri
(§45.2). Üçünde de ölçüm aletim `QT_QPA_PLATFORM=offscreen` idi ve üçünde
de yanlış sayı verdi. Sorunu çözen tek değişiklik **ölçümü kullanıcının
makinesine taşımak** oldu: koda kalıcı teşhis dökümü (`_asgari_dokumu`)
konuldu, kullanıcı Rapor penceresini yapıştırdı, suçlu ilk bakışta
görüldü.

> **Kural:** yazı tipine, stile ya da DPI'a bağlı bir arayüz sayısı
> simüle edilemez. Böyle bir sayı gerekiyorsa tahmin etme, ölçme aleti
> yazıp gerçek ortamdan iste. `freecadcmd` geometri ve mantık için
> geçerli; piksel için değil.

Bu, MANTIK'ın "ölçmeden düzeltme yok" kuralının eksik yarısıydı: ölçmek
yetmiyor, **doğru yerden** ölçmek gerekiyor. Yanlış aletle alınan ölçüm,
hiç ölçmemekten daha pahalı — çünkü kendine güven veriyor.

### 45.5 Karşılama kısaldı

Kullanıcı: *"ilk açılış kısa bir cümle olsun, o kadar açıklamaya gerek
yok."* Yedi satırdı (abonelik, belge koruma, adım adım çalışma, varsayım
bildirme) — hepsi doğru ama hiçbiri **ilk anda** gerekli değil; dar
panelde sohbetin ilk ekranının yarısını yiyordu. Şimdi iki satır,
112 karakter: sürüm/model bilgisi + ne yazacağını gösteren tek örnek.
Test uzunluğu tutuyor (≤2 satır, <160 karakter), ki yarın yine büyümesin.

---

## 46. `saglik` ve `simetri` — aday listesini tahmin değil GÜNLÜK seçti

Kullanıcı analiz eklemek istedi (*"kullanıcı analiz yapmak isterse ne
yapabiliriz... modal analiz"*) ve sıralamayı kendisi koydu: önce ucuz
geometrik ölçümler (B grubu), FEM ve çıktı tezgâhları plana.

### 46.1 Seçim yöntemi — S8'in kendi kuralı uygulandı

PLAN S8 bir kabul ölçütü koymuştu: *"günlükte iki kez elle yazılmış
olmalı — uydurma ihtiyaç değil."* Bu kez o kural **gerçekten
uygulandı**: aday listesi düşünülerek değil, `LOG/` taranarak çıkarıldı.

| desen | kaç kez | kaç günlükte | karar |
|---|---:|---:|---|
| `isValid` | 156 | 9 | ✅ |
| `isSolid` | 125 | 4 | ✅ |
| `hasSelfIntersections` | 96 | 4 | ✅ |
| `len(Shape.Solids)` | 86 | 7 | ✅ |
| `hasNonManifolds` | 48 | 3 | ✅ |
| "simetri" | 38 | 5 | ✅ |
| `MatrixOfInertia` / atalet | **0** | 0 | ❌ |
| sapma haritası (Inspection) | **0** | 0 | ❌ |

**Elenenler bu kaydın asıl değeri.** Atalet tensörü ve sapma haritası
liste yapılırken makul görünüyordu; günlük ikisini de sıfır kez
istemişti. Kütle merkezi de elendi: 6 `CenterOfMass` çağrısının hepsi
**yüz merkezi** bulmak içindi, denge sorusu için değil. Yani sayım
yalnızca ne ekleneceğini değil, **ne eklenmeyeceğini** de söyledi — ve
bu üçü eklenseydi §44'ün uyardığı gürültüyü büyütecekti.

### 46.2 `saglik` — `isValid()` tek başına neden yetmiyor

Model iki AYRI deyim yazıyordu, nesnenin türüne göre:

    kati  ->  sh.isValid() and len(sh.Solids) == 1 and sh.isClosed()
    mesh  ->  m.isSolid() and not m.hasNonManifolds()
              and not m.hasSelfIntersections()

Yani hangi testin uygulanacağını da her seferinde kendisi seçiyordu.
`saglik()` o seçimi üstlenir.

Ön kabul zaten `test_dogrulama_fc.py` başlığında ölçülüydü ve teste
yeniden kondu: **açık kabuk `isValid()`'i geçiyor**, ters katı da
geçiyor. Bu yüzden `saglik` yalnızca `isValid`'e dayanmıyor; katıda
`Solids`, `isClosed` ve hacim işaretine de bakıyor.

**Kusur ile bilgi ayrıldı.** Modelin elle yazdığı `len(Solids) != 1`
olduğu gibi alınsaydı bileşik şekiller yanlış alarm üretirdi — §32'deki
31 kez tekrarlanan hatanın aynısı. "2 ayrı katı" **bilgi** satırı,
"katı yok" **kusur**.

Hammadde (kesme tabanı, ayna kaynağı) çakışmada elenirken burada
**elenmiyor**, yalnızca etiketleniyor: bozuk bir kesme tabanı, bozuk
sonucun ta kendisidir. İki soru farklı, eleme kuralı da farklı olmalı.

### 46.3 `simetri` — elle yazılanın ölçülebilir kusuru

Model simetriyi bbox'ı bantlara bölüp nokta sayarak arıyordu ve bir kez
**gerçek bir kusuru böyle buldu**: *"Y≈111–143 bandında sadece pozitif X
var, negatif tarafta hiçbir nokta yok — eksik olan kuyruk yatay
kanadının sol yarısı."* 4 piksel/mm'lik bir karede kaçabilecek bir kusur.

Ama bant sayımının bir körlüğü var: yalnızca *"bu tarafta hiç nokta var
mı"* diye sorar. **Kaymış ama var olan** bir yarıyı temiz gösterir — ve
aranan kusur çoğu zaman tam odur. `simetri` bunun yerine aynalayıp
gerçek sapmayı ölçüyor.

İki karar:

* **Fark iki yönlü alınıyor.** `A - A'` tek başına yalnızca fazlalığı
  görür, **eksiği görmez**. Simetrik fark iki taraflıdır.
* **Eşikler göreli.** 200 mm'lik bir parçada 0.1 mm simetriktir, 2
  mm'lik parçada değildir.

Katıda hacim farkı + fark bölgesinin bbox'ı, mesh'te en büyük nokta
sapması + yeri raporlanıyor. Boolean patlarsa (bozuk şekilde olağan)
nokta bulutuna düşer ve **bunu satırda söyler**; ikisi de olmazsa
"simetrik" DEMEZ.

### 46.4 Doğrulama — bilinen cevaplı sayı

40×20×10 kutudan tek tarafta 6×6×6 cep kesildi. Elle hesap:

| | |
|---|---:|
| cep hacmi | 216 mm³ |
| gövde | 7 784 mm³ |
| simetrik fark (216 fazlalık + 216 eksiklik) | **432 mm³** |
| oran | **%5.5** |

Yardımcı birebir bunu yazdı ve bozuk bölgeyi `x 30..36` diye gösterdi.
Maliyet: `saglik` 4 nesnede 0.05 sn, `simetri` üç eksende 0.11 sn.

`test_dogrulama_fc.py` 84 → **99 kontrol**. Tüm takım **931 kontrol, 0
başarısız**.

> **TEST TUZAĞI, yine.** İlk süpürmede dört dosya "özet satırı yok" diye
> göründü ve §44.5'teki sessiz ölüm sanıldı. Sebep testler değildi:
> FreeCAD'in `Recompute...(100 %)` ilerleme çıktısı stdout'u boğuyor ve
> grep'i besleyen borunun sonunu yiyor. Doğru kaynak `tests/_son_*.txt`
> rapor dosyaları — zaten §14.5 bu yüzden var. Ekrandan test okumak
> güvenilmez.

### 46.5 Sözleşme tavanı — kullanıcı doğrulamamı istedi, doğrulandı

İkisi de sisteme eklendi (kullanıcının isteği: *"bu eklediklerimizi de
aktif olarak sistem prompta ekle, çok fazla kod koşulmasını seviyorum,
daha kaliteli oluyor"*). Sözleşme 25 678 → **26 903** karakter.

Kullanıcı *"sözleşmenin tavanını da hızlıca doğrula, gerçekten o mu"*
dedi. Ölçüldü:

| | |
|---|---:|
| sözleşme | 26 903 |
| sabit bayraklar (`-p`, `--model`, `--session-id`…) | 300 |
| toplam komut satırı | 27 203 |
| **Windows sert duvarına pay** (32 767) | **5 564** |
| test tavanına pay (28 000) | 1 097 |

**Kullanıcının istemi argv'ye girmiyor** — `--input-format stream-json`
ile stdin'den gidiyor (transport `_argv`'de doğrulandı). Yani sözleşme
argv'nin neredeyse tamamı ve tek büyüyen parçası.

Sonuç: **28 000 gerçek duvar değil**, projenin kendi emniyet payı. Sert
duvar §35.1'de ölçülmüştü (32 000 çalıştı, 40 000 "Argument list too
long" ile 63 ms'de öldü). Elimizde hâlâ ~5 500 karakter var; bittiğinde
uzun anlatım `workspace/CLAUDE.md`'ye taşınacak — dosyanın argüman
sınırı yok.

### 46.6 FEM için ölçülen tek şey: parçalar kurulu

Modal analizin üç gereği de bu makinede var (kurulum dizini okundu):
`Mod/Fem`, `bin/gmsh.exe` + `NETGENPlugin.dll`, ve çözücü `bin/ccx.exe`
(CalculiX). **Çalıştığı ölçülmedi** — kullanıcı koşturmayı durdurdu,
sıra B grubundaydı. Ayrıntı ve kalibrasyon planı PLAN S10'da; oradaki
kritik nokta modal analizin **yük istememesi**, yani modelin uyduracağı
sayı olmaması, ve ankastre kirişin elle hesaplanabilen ~833 Hz'i
sayesinde bilinen cevaplı bir testinin bulunması.

---

## 47. Fotoğraf deneyi yapıldı — ve kaliteyi belirleyen şeyin fotoğraf olmadığı çıktı

PLAN S9'da tasarlanan deney koşuldu. Sonuç, deneyin sorduğu soruyu
cevapladı **ve sormadığı bir soruyu da cevapladı** — asıl değerli olan
ikincisi oldu.

### 47.1 Düzenek — kod deneyler ARASINDA değişmedi

Metodolojik nokta, sonradan düzeltilemeyeceği için önce halledildi:
görüntüyü kapatmak bir kod değişikliği gerektiriyordu ve bunu A ile B
arasında yapmak iki koşuyu farklı kodla çalıştırırdı. Bu yüzden anahtar
(`config.GorselKapali`) **her iki koşudan önce** kondu, `_gorseli_gonder`
fonksiyonunun en başına — hiçbir sayacı kirletmesin, tek fark karenin
gönderilip gönderilmemesi olsun diye.

Aynı istem (masa lambası: yuvarlak taban, iki parçalı eklemli kol, konik
abajur, içinde ampul, ~400 mm, devrilmesin, parçalar iç içe geçmesin),
aynı model (opus-5), aynı efor (Hızlı), her koşuda **boş yeni belge** ve
aynı tek yan cevap (`f` = yalnızca görsel amaç).

### 47.2 Sonuçlar

| | A — fotoğraflı | B1 — fotoğrafsız | B2 — fotoğrafsız |
|---|---:|---:|---:|
| yazma bloğu | 6 | **4** | **8** |
| süre | 3:04 | 2:08 | 4:01 |
| token | 48.7k | 37.2k | 50.6k |
| görsel | 2 gönderim, 129 KB | 0 | 0 |
| iç içe geçme kaldı mı | evet | evet | **hayır** |
| kullanıcı hükmü | iyi | kötü | **en iyi** |

**En iyi ve en kötü koşu AYNI koldaydı.** Fotoğraf kolu ortada kaldı.
Yani görüntünün etkisi, varsa bile, koşular arası saçılmanın altında.

Fotoğrafın **bedeli** ise bu çiftte kesin ölçüldü: %31 daha fazla token,
%44 daha fazla süre.

Kullanıcının hükmü: *"görselle alakası yok, tamamen randomluktanmış."*

### 47.3 Deneyin sormadığı soruyu cevaplaması

Tabloda fotoğrafla korelasyon yok; **blok sayısıyla tam korelasyon var**:

    4 blok -> kötü      6 blok -> iyi      8 blok -> en iyi

Mekanizma tahmin değil, logda görünüyor: **her yazma bloğu kendi
doğrulama raporunu doğuruyor.** Daha çok adım = daha çok bulgu = kusurun
hâlâ ucuzken yakalanma şansı. B2, doğrulama üç iç içe geçme bulunca
adımı `GERİ-AL` edip teğet temasla yeniden kurdu:

> *"Haklı olarak 'içine geçmesin' dediniz — doğrulama üç iç içe geçme
> buldu (kol × mafsal 2872 mm³, mafsal × boyun 4601 mm³). Bunlar mafsal
> için tipik ama sizin kuralınıza aykırı, o yüzden 2. adımı geri alıp
> yeniden kuruyorum."*

A ve B1 ise **aynı türden bulguları** tek cümleyle akladı: *"kalan tüm
kesişmeler kasıtlı bağlantı geçmeleri."*

Kullanıcının kararı: *"insanlar 1-2 dakika geç bitirebilir ama tasarım
güzel olmazsa hiçbir işe yaramaz. önceliğimiz kalite."*

### 47.4 Görsel sistemi kapatıldı — silinmedi

`conversation.GORSEL_ACIK = False`. Yakalama kodu, işaret regex'i,
`gorunum.py`, `_kac_kare` — hepsi yerinde duruyor, yalnızca etkisiz.
Açmak **iki** şey gerektiriyor ve bu koda yazıldı: bayrağı `True` yapmak
**ve** sözleşmeye `GORSEL-KONTROL` maddesini geri koymak. İkisi birden
gerekli: sözleşme anlatmazsa model işareti hiç yazmaz.

Sözleşmeden görselle ilgili **tek madde bırakılmadı** (ölçüldü:
`GORSEL-KONTROL` geçiş sayısı 0). Gerekçe: madde kalsaydı model olmayan
bir şey ister, her turda reddedilir ve bir tur boşa giderdi. Yerine
konan madde modele durumu açıkça söylüyor — *"YOU CANNOT SEE THE 3D
VIEW. There is no picture, ever."* — ve ölçmediği bölgeyi adlandırmaması
gerektiğini, siluete en yakın şeyin `kesit_konturu` olduğunu ekliyor.

Model yine de isteyebilir (eski alışkanlık). O yüzden host **sessiz
kalmıyor**: kod çıktısı gönderiliyor ve "görüntüye bakmış gibi konuşma"
deniyor — §14'teki "başarılı çalıştırma hakkında sıfır geri bildirim"
kaybına dönmemek için.

> **KAPATMA KESİN HÜKÜM DEĞİL.** Üç koşu, fotoğrafın *işe yaramadığını*
> kanıtlamaz; yalnızca etkisinin gürültünün altında kaldığını, bedelinin
> ise ölçülebilir olduğunu gösterir. Kanıtlanan şey masraf, aklanan şey
> değil. Kod bu yüzden duruyor.

### 47.5 Deney kodu söküldü

`config.VARSAYILAN["GorselKapali"]`, `config.gorsel_kapali()` ve
`conversation`'daki geçici blok kaldırıldı; `user.cfg`'deki ayar da
silindi. Ölçüm düzeneği depoda kalmaz — kalırsa bir gün birinin
"özellik" sanacağı bir anahtar olur.

---

## 48. Bulgu satırı kusuru buluyordu ama BÜYÜKLÜĞÜNÜ söylemiyordu

§47'nin B1 koşusu bir kusuru teslim etti ve nedeni tek bir eksik sayıydı.
Bu bölüm o dersi kaydediyor.

### 48.1 Olay

Host bunu yazdı:

    BULGU Abajur: icinden geciyor — ortak hacim 5.791e+04 mm3 (Ampul ile)

Model şöyle cevapladı:

> *"ampul abajurun tam içinde (57906/57906 mm³), kalan tüm kesişmeler
> kasıtlı bağlantı geçmeleri."*

**Aynı sayıyı gördü ve onay diye okudu.** Oysa o hacim ampulün
tamamıydı: abajur içi boş bir kabuk olması gerekirken dolu koniydi.
Ampul görünmez bir cismin içine gömülmüştü.

Daha kötüsü: model kendi geçme ölçütünü şöyle yazmıştı —

    print("ampul abajur icinde mi (ortak hacim ampul hacmine esitse evet):", ...)

Bu testi **dolu bir koni de geçer.** Model kendi sınavını, kusuru başarı
gösterecek biçimde kurdu.

Aynı oturumda 2872 mm³'lük bir mafsal geçmesi **gerçekten kasıtlıydı**.
İki durumu ayıran şey hacmin büyüklüğü değil — **küçük parçanın ne
kadarının yutulduğu**. O oran raporda yoktu.

### 48.2 Üç düzeltme

**(a) Oran eklendi** (`olcum._cift_olc`). Katı–katı geçişlerde ortak
hacim, iki parçanın **küçüğüne** oranlanıyor:

| durum | eski satır | yeni satır |
|---|---|---|
| ampul gömülü | `ortak hacim 5.791e+04 mm3` | `ortak hacim 57906 mm3, Ampul TAMAMEN GOMULU (hacminin %100'u iceride)` |
| gerçek mafsal | `ortak hacim 4145 mm3` | `ortak hacim 4145 mm3, Eklem hacminin %45'i` |

%98 ve üstü "TAMAMEN GOMULU" diye adlandırılıyor, çünkü o eşiğin
üstünde küçük parça pratikte görünmez hâle geliyor ve bu neredeyse hiç
istenen bir şey değil.

**(b) Bilimsel gösterim kaldırıldı** (`olcum._sayi`). `%.4g` biçimi
10 000'den sonra `5.791e+04` üretiyordu ve CAD'de mm³ değerleri rutin
olarak orada. 10 000 üstü artık düz yazılıyor: `57906`. Küçük değerler
`%.4g` kalmaya devam ediyor — ondalık hassasiyet orada gerekli.

**(c) Kesme artık keyfi değil** (`dogrulama._cakisma_taramasi`). Rapor
en fazla 5 çakışma satırı yazıyor (§32'deki 31 kez tekrarlanan yanlış
alarma dönmemek için) ama liste **belge sırasındaydı** — yani en ağır
geçiş tavanın dışında kalabiliyordu. B1'de tam bu oldu: 7 geçişten 5'i
yazıldı, "kalanları `cakisma_kontrol()` ile gör" dendi ve model o
çağrıyı yapmadı.

Artık liste **yutulma oranına, sonra hacme** göre sıralanıyor. Ölçülen
yeni sıra: %100 → %77 → %45 → %7 → %1. Bir şey kesilecekse en hafifi
kesiliyor. Kesilen kısım da artık sessiz değil — kalanların en büyüğünü
adıyla ve hacmiyle yazıyor.

### 48.3 Sözleşme: toplu aklama yasaklandı

Sayıyı düzeltmek yetmez; modelin onu **karşılamak zorunda** olması
gerekiyor. Eklenen madde: bulgular tek tek cevaplanacak, *"kalanlar
kasıtlı"* bir cevap değil, bakmama biçimi. Ve kullanıcı "içine
geçmesin" dediyse **kasıtlı bir bağlantı bile ihlaldir** — açıklanmaz,
teğet temas olarak yeniden kurulur. (B2'nin doğru davranışı buydu;
sözleşme artık onu kural yapıyor.)

---

## 49. Adım sayısı arttırıldı — ölçüme dayanarak

§47.3'ün bulgusu sözleşmeye taşındı.

### 49.1 Ne değişti

**Yazma bloğu artık kesin olarak bir tane.** Eski madde *"bağımsızsalar
en fazla üç yazma bloğu verebilirsin"* diyordu ve tam ters yöne
çekiyordu. Kaldırıldı.

Yerine 4/6/8 tablosu, mekanizmasıyla birlikte sözleşmeye yazıldı; ve
karar kuralı: **"bir şeyin tek adım mı iki adım mı olduğundan emin
değilsen, iki yap."** Ayrı şekilli bir parça, bir eklem, bir delik
deseni, bir pah geçişi — her biri kendi adımı.

Planlama maddesine de ekleme yapıldı: *"işi gerektiğinden daha ince
kes. İkiden üç parçadan fazlası olan her iş altı veya daha çok adım
ister. Altı parçalı bir nesne için planın üç adımsa, ilk bloğu yazmadan
önce böl."*

### 49.2 Gerekçe kullanıcının, ölçüm bizim

> *"insanlar 1-2 dakika geç bitirebilir ama tasarım güzel olmazsa
> hiçbir işe yaramaz. önceliğimiz kalite."*

Ölçülen ek maliyet gerçekten o mertebede: 4 blok 2:08, 8 blok 4:01 —
yaklaşık iki dakika. Bunun karşılığında B2, üç koşunun **hiçbir çifti
iç içe geçmeyen tek koşusu** oldu.

### 49.3 Yan kazanç — sözleşme küçüldü

Görsel maddeleri çıkınca 2 804 karakter yer açıldı. Dört yeni madde
(görüntü yok, adım sayısı, bulgu disiplini, ince bölme) eklenmesine
rağmen sözleşme **26 903 → 25 196** karaktere indi. Sert duvara
(§35.1, Windows ~32 767) pay: ~7 270 karakter.

### 49.4 Testler

`test_tam_tur_fc.py` 195 → **200 kontrol**. Silinen görsel iddiaları
yerine yeni değişmezler kondu: sözleşmede `GORSEL-KONTROL` geçmemeli,
`GORSEL_ACIK` kapalı olmalı, görsel kapalıyken kare gitmemeli ama **kod
çıktısı gitmeli**, ve döngü emniyeti sabiti (açılırsa gerekli) yerinde
durmalı.

Tüm takım: **886 kontrol, 0 başarısız.**

---

## 50. Sürdürülen sohbet doğru belgeye bağlandı — kimlik AD değil YOL

Kullanıcının bildirdiği kusur (2026-08-28): *"kaldığı yerden yanlış
başlıyor. çünkü kaldığı yerden başladığında ve o modelin içinde değilsem
bile o modelde başlıyor. tamam doğru chati düzeltiyor ama kaldığı model o
değil."*

S2 sohbeti `--resume` ile getiriyordu; getirmediği şey **belge**. Kod her
zaman o an aktif olan belgede koşuyor.

### Neden sadece kafa karışıklığı değil

`doc.getObject("Sasi")` `None` dönerse kod patlar ve zararsızdır. Asıl
tehlike adların **çakıştığı** durum: iki ayrı projede de `Kutu`, `Govde`,
`Taban` bulunması hiç uzak bir ihtimal değil. O zaman kod sessizce yanlış
modeli değiştirir; tek `GERİ-AL` girdisi bunu geri alır ama kullanıcı ne
olduğunu ancak 3B'de görürse anlar.

### Ölçüm 1 — kimlik ne olmalı

Tasarıma başlamadan önce `freecadcmd` 1.1.3 ile üç şey ölçüldü:

| soru | ölçüm |
|---|---|
| Zaten açık dosyayı `openDocument` ile açmak | **İkinci kopya üretmiyor**, aynı nesneyi döndürüyor (`d2 is d`) |
| Kapatılıp yeniden açılan belgenin `Name`'i | **`ProbeAc` → `caddy_probe_ac`** — ad DOSYA ADINDAN yeniden türetiliyor |
| Olmayan dosya | `OSError: File ... does not exist!` — yakalanabilir |

İkincisi planı değiştirdi. PLAN S14'ün ilk taslağı *"günlüğe belge adını
yaz, karşılaştır"* diyordu; **`doc.Name` oturumlar arası sabit değil.**
Karşılaştırma **dosya yolu** ile yapılır, ad yalnızca insana gösterilir.
Ölçmeden yazsaydık, uyarı belgeler eşleştiğinde bile tetiklenirdi.

Bu ön kabul teste de girdi ve girerken bir tuzak çıktı: adın dosya
adından türediğini göstermek için ikisinin **ayrıldığı** bir örnek
gerekiyor. İlk yazdığım testte belge adı da dosya adı da `S14Model`'di ve
eşitlik hiçbir şey kanıtlamıyordu — test geçmiyordu, iyi ki geçmedi.

### Ölçüm 2 — dosya yolu elimizde olacak mı

Diskte tarandı: modeller gerçekten kaydediliyor
(`Desktop\3D_Models\models\araba\Araba.FCStd`, `.../lamba/Adsız4.FCStd`,
`.../yelkenli/Adsız.FCStd`). Ayrıca hiç kaydedilmemiş belgede bile
`.caddy-backups/<Ad>_<damga>.FCStd` duruyor (28 dosya) — `_yedek_al` ilk
AI değişikliğinden önce kopya bırakıyor.

**Yedek bir AÇMA hedefi değil.** İçeriği işin *başındaki* hâl. Onu
"modelin geldi" diye açmak, AI'ın yaptığı her şeyi silinmiş göstermek
olurdu — bu projenin en sevmediği şey olan sessiz yanlış cevabın ta
kendisi. Yedek yalnızca bilgi satırında adı geçiyor.

### Yapılan

Günlük başlığına iki satır eklendi:

    belge  : Adsız4 (Unnamed)
    dosya  : C:\Users\...\lamba\Adsız4.FCStd

Başlık **tembel** yazıldığı için (§37) ve dosya yolu oturumun
**ortasında** doğabildiği için (kullanıcı çoğunlukla sonda kaydediyor),
satırlar yol bulunana kadar her kayıtta tazeleniyor; bulununca donuyor.
`_basliga_model_yaz`'ın iki durumlu mantığı (`bekleyen başlık` vs `diskte`)
tek bir `_baslik_satirini_degistir`'e çıkarıldı — aynı hatayı iki yerde
yapma daveti kalmasın.

Etiket **ve** iç ad birlikte yazılıyor: etiket kullanıcıya gösterilen ad,
iç ad ise yedek dosyasının adı (`_yedek_al` `doc.Name` kullanıyor).
Ayrıldıklarında birini seçmek diğerini arayan tarafı kör bırakırdı.

Sürdürülen günlükte başlık **hiç güncellenmiyor** (`_belge_yazildi = True`).
Üzerine şimdi açık olanı yazsaydık, sohbetin hangi modelde geçtiği
bilgisini kendi elimizle silmiş olurduk — maddenin tek dayanağı o satır.

### Dört dal

Karar `kayitlar.belge_durumu()`'nda, Qt'siz ve test edilebilir; açma işi
ui'nin:

| durum | davranış |
|---|---|
| **açık** | sessizce o sekmeye geç |
| **kapalı** | **sor**, kendiliğinden açma |
| **kayıp** (taşınmış/silinmiş) | yolu yaz, uyar |
| **kaydedilmemiş** | uyar + yedek kopyanın yolunu bilgi olarak ver |
| **bilinmiyor** (eski günlükler) | **hiçbir şey yazma** |

Son satır bilerek böyle: başlığında belge satırı olmayan 114 eski günlük
var ve bilmediğimizi uyarı diye yazmak, gerçek uyarıları da
değersizleştirir (§32'deki 31 kez tekrarlanan yanlış alarmın dersi).

**Neden otomatik açmıyoruz.** Belge açmak kullanıcının ekranını
değiştiren, geri alınması olmayan bir hareket. Yanlış tahmin edersek iş
bozulmaz ama can sıkar; sormanın maliyeti tek tık. GUI'de her belge kendi
sekmesi olduğu için açmak, açık belgeyi **kapatmıyor** — yanına sekme
geliyor.

### Ölçülemeyen tek şey

Sekmenin gerçekten açılıp **odaklandığı** (`Gui.ActiveDocument` ataması)
başsız ölçülemez; `freecadcmd`'de 3B görünüm yok. Kullanıcı FreeCAD'de
elle bakacak. Bu, hafızadaki kuralın aynısı: UI ölçümü gerçek FreeCAD'den
gelir, kendi başsız testimden değil.

### Testler

`test_kayitlar_fc.py` 24 → **50 kontrol**. İki ön kabul (ikinci kopya
üretilmiyor, ad dosyadan türüyor), dört dalın hepsi, büyük/küçük harfli
yol aynı dosya sayılıyor, olmayan dosyada `belgeyi_ac` patlamıyor metin
döndürüyor, kullanıcı mesajındaki sahte `dosya :` satırı başlığın yerine
geçmiyor, ve sürdürülen günlüğün eski belge satırı korunuyor.

Tüm takım: **965 kontrol, 0 başarısız** (12 paket; rapor dosyası
bırakan 11'i 912, `test_executor_fc.py` ayrıca 53).

---

## 51. Uzay asansörü oturumu — 21 blok, 0 hata, ve üç küçük kusur

`LOG/2026-08-31_ed2bc86b.txt`. Öncekilerden farkı: iş mühendislik parçası
değil **sahne**; kullanıcı ortada *"sadece görsel güzellik önemli,
kesişebilir"* dedi. Yine de ölçüm katmanı işini yaptı.

| | |
|---|---:|
| süre | 17 dk 12 sn |
| kod bloğu | 21 |
| **başarısız blok** | **0** |
| blok yoğunluğu | ort. 40 satır, 3.6 `print`, 2.0 ölçüm çağrısı |
| bağlam (son tur) | 143 959 token |
| efor | Hızlı (az düşünür) |

21 bloğun 21'i çalıştı; elimizdeki günlüklerde bu ilk, üstelik en düşük
efor ayarında.

### Dün yapılanlar üretimde doğrulandı

**§48 (bulgu satırı).** Halka–Kol bulgusu tam dünkü daldan çıktı:
`ortak hacim 0.01031 mm3, Kol1 hacminin %1'inden azi`. O dal olmasaydı
**`%0'i`** yazacak, gerçek bir çakışmayı yok gösterecekti. Model dört
bulgunun dördünü de tek tek karşıladı ve *"doğru çözüm bunu açıklamak
değil"* deyip göbek+kol+halkayı `MultiFuse` ile tek katıya kaynattı —
sözleşmedeki "kasıtlı bağlantı da olsa yeniden kur" maddesinin birebir
karşılığı.

**§46 (`saglik`).** Afrika kıtası `isSolid()`'i geçti, `saglik` "kendini
kesen yüzey" dedi. Model sebebi buldu (merkezden yelpaze üçgenleme,
Afrika yıldız-şekilli değil), **`GERİ-AL`** çekip ear clipping ile
yeniden yazdı. Mesh yolu tek başına bir adımı kurtardı.

`cakisma_kontrol` 12 kez `odak=` ile çağrıldı; yardımcılar kullanılıyor.

### Kusur 1 — `KUSUR Origin001: KATI YOK` ✅ **düzeltildi**

Ölçüldü, tahmin edilmedi: `Origin001` bir datum **noktası**
(`App::Point`, `Shape=Vertex`). Katısı olmaması normal. İki katman birden
yanlıştı:

* `kesif._ATLANAN` listesinde `App::Plane` ve `App::Line` vardı,
  **`App::Point` unutulmuştu** — üçü aynı iskele takımının parçası.
* `_saglik_kati` yüzü olmayan şekle katı testi uyguluyordu. Bu kategori
  hatası: noktanın/kenarın/telin katı olmaması kusur değil.

Düzeltme iki kata da yapıldı (nesne **elle** verilse de yanlış kusur
yazılmasın) ve bakılmadığı **söyleniyor**: `not X: yuzu yok (nokta/kenar/
tel) — kati testleri uygulanmadi`. Sessizce atlamak "0 kusurlu"yu temiz
gösterirdi; §44'ün "ölçemediğini uydurma" kuralı burada da geçerli.
Gerçek belgede doğrulandı: `Origin001` artık keşfe girmiyor, geriye
yalnızca kullanıcının umursamadığı kıta/yıldız kesişmeleri kalıyor.
Testler: `test_dogrulama_fc.py` 99 → **108**; takım **974, 0 hata**.

### Kusur 2 — "bu klasöre kaydet" ⬜ açık

Kullanıcı belgenin klasörünü kastetti; model `r"...\Desktop\CADdy"` yazdı
ve resimleri kullanıcı elle taşıdı. Savunması var — belge o an
kaydedilmemişti (`Adsız.FCStd` 12:02'de, resimler 12:01'de), yani
`doc.FileName` boştu. **Ama sessizce tahmin etti.** Doğrusu: `FileName`
doluysa onun klasörü, boşsa sormak. S14 ile aynı damar: kimlik dosya
yoludur, ve artık `<document>` bloğunda duruyor.

### Kusur 3 — tutamayacağı söz ⬜ açık

*"kesişebilir"* denince model *"artık bunları bulgu olarak
raporlamıyorum"* dedi. Raporlayan o değil, **host**; bulgular aynen geldi
(`Kita_KuzeyAmerika`, `Yildizlar`). Zararsız ama yanlış. Modelin kendi
yetkisiyle host'un yetkisini ayırt etmesi gerekiyor.

### S12'nin izleme maddesi için veri

Adım sayısına tavan koymamıştık, *"ölçülmüş bir zarar yok"* diye. 21 blok
gitti, zarar hâlâ yok. Ama asıl tavanın ne olduğu görüldü: kullanıcının
sabrı değil, **bağlam**. Son tur 143 959 token; bu hızla 30-35 blok
sınıra dayanır. Tavan koymak yerine izlenecek sayı budur.

### Görseller

`uzay_asansoru_onden.png` istenen kareyi veriyor: perde arkada, Dünya
önde. `uzay_asansoru_perspektif.png` ise hileyi ele veriyor — yıldız
perdesi yandan bakınca boşlukta duran eğik bir dikdörtgen ve Satürn
perdenin dışında kalıyor. Kusur değil (sahne "tek açıdan bakılsın" diye
kuruldu) ama ikinci kare sahneyi güçlendirmiyor, zayıflatıyor. Model bunu
göremez; görsel kapalı.
## 52. Araba oturumu — aynı çakışma tek isteme iki kez yazılıyordu

`LOG/2026-08-31_f5a6a5ac.txt`, 341 KB / 6204 satır. Bugüne kadarki en uzun
oturum: 51 dakika, 28 kullanıcı mesajı, **52 kod bloğu — 51 başarılı, 1
hata (%98)**, belge 104 → **231 nesne**. Bağlam 28.6k'dan **788 387**'e
çıktı: 1M sınırın **%79'u** ve önceki en yüksek ölçümün (143 959, §51)
**5.5 katı**.

Oturumda **hiç otomatik görsel yakalanmadı** (§49'da kapatılmıştı) ve
kalite düşmedi; sondaki 8 render'ı kullanıcı ayrıca istedi ve `saveImage`
sorunsuz çalıştı. S1 için kanıt: yakalama mekanizması sağlam, sorun onu
her turda **otomatik** çalıştırmaktı.

### 52.1 Ölçülen kusur: aynı geçiş, iki cümle, tek istem

Model her yeni parçadan sonra `cakisma_kontrol(odak=...)` çağırıyor.
Ardından host'un doğrulama taraması aynı çiftleri bir daha bulup `BULGU`
satırı yazıyor. Tek `<execution_result>` içinde, yan yana:

```
BULGU RollbarKiris: icinden geciyor — ortak hacim 10.42 mm3,
      RollbarDikme1 hacminin %16'i (RollbarDikme1 ile)
...
RollbarKiris x RollbarDikme1: ICINDEN GECIYOR — ortak hacim 10.42 mm3,
      RollbarDikme1 hacminin %16'i
```

Aynı sayı, aynı çift, farklı cümle. O tek blokta ~950 karakter; günlükte
**76 geçiş** var ve bunların çoğu iki kez gitti. Bağlamı 788k'ya çıkan bir
oturumda bu ödenmesi gereksiz bir bedel — ama asıl zarar bu değil: aynı
bulguyu iki ayrı ifadeyle okuyan model onu **iki ayrı sorun** sanabilir.

### 52.2 Hangi taraf kazanır — ve neden tarama değil

Bastırılan taraf **doğrulama taraması** oldu, `cakisma_kontrol` çıktısı
değil. Üç gerekçe:

1. Modelin **kendi sorduğu** şey `cakisma_kontrol` çıktısıdır.
2. O çıktı daha zengin: kaç nesne, kaç çift, kaçı bbox ile elendi, kaç
   nesne listeye alınmadı, ne kadar sürdü. `BULGU` satırında bunlar yok.
3. Taramanın işi zaten §39'da konmuştu: modelin **sormadığını** yakalamak.
   Sorulmuş olanı bir daha söylemesi gerekmiyor.

### 52.3 Bastırma SESSİZ değil

`olcum._bildirilen_gecisler` yalnızca `yaz=True` çağrılarını kaydeder —
`yaz=False` (görsel yolu) hiçbir şey yazdırmaz, onun bulgusu bastırılırsa
gerçekten kaybolurdu. Kayıt her blok başında sıfırlanır
(`executor.calistir`): bir önceki turda yazılmış bir geçiş, bu turun
taramasında bastırılmaz.

Bastırılan sayı rapora yazılır:

```
cakisma: 3 gecis blogun kendi cakisma_kontrol ciktisinda zaten yazili
         — burada tekrarlanmadi
```

Ve `cakisma: N cift olculdu, icinden gecen yok` hükmü artık yalnızca
**gerçekten** geçiş yokken veriliyor — bastırma varken o cümle yanlış
güven verirdi. Bu, projedeki "ölçemediğini söyle" kuralının aynısı.

### 52.4 Oturumdaki tek hata: yardımcıların dönüş tipi

52 bloğun tek hatası şuydu:

```
round(mesafe(a, b), 3)
TypeError: type dict doesn't define __round__ method
```

Sözleşme yardımcıların sonucu **yazdırdığını** söylüyordu ama ne
**döndürdüğünü** hiç söylemiyordu; sayı döndürdüklerini varsaymak doğal
bir yanlıştı. `olc`, `mesafe`, `olcu`, `kesit_capi`, `duvar_kalinligi`,
`simetri`, `saglik`, `cakisma_kontrol` — hepsi `dict` döndürüyor, o yüzden
tek cümle bütün sınıfı kapatıyor:

> Every one of those measuring helpers RETURNS A DICT, never a number …
> take it out by key — `mesafe(a, b)["mesafe"]`, `olc(o)["hacim"]`.

Sözleşme 25 105 → **25 525** karakter (tavan 28 000).

### 52.5 Kapatılmayan iki kusur

**bbox doğrulaması yön kördür.** Model plakalara FRKN yazdı, bbox'ı ölçtü,
temiz raporladı; kullanıcı baktı: *"soldan sağa yazmalı ama sağdan sola
yazmışsın, sen iki tarafı da düzelt."* **Aynalanmış bir yazının bbox'ı
birebir aynıdır** — hiçbir mevcut ölçüm bunu yakalayamazdı. Bu §39'un
tersi: orada görüntü yetmiyordu, burada ölçüm yetmiyor. Ucuz ve
deterministik bir vekil var ve yazılmadı:
`Placement.Rotation.multVec(Vector(1,0,0))` ile yerel +X'in nereye
gittiğine bakıp bakış yönüne göre soldan sağa mı diye karar vermek.

**Bağlam %79'a çıktı ve hiçbir eşik uyarısı yok.** `config.BAGLAM_SINIRI`
yalnızca paneldeki durum satırında (`788k/1M`) kullanılıyor; sohbete
düşen bir sistem satırı yok. Bu hızda 60-70 bloklu bir oturum sınıra
dayanır ve o noktada ne olacağı **ölçülmedi**.

### 52.6 İyi giden şeyler (ölçüldü)

* **S14 üretimde:** günlük başlığında `belge : Araba` ve tam dosya yolu
  var — §50'nin ilk gerçek çıktısı.
* **Adım freni kalktı:** *"devam sormadan devam et"* dedikten sonra
  13:48:36 → 13:55:49 arası **7 dakika, 9 blok kesintisiz**. §49 tuttu.
* **Model kullanıcının GERİ-AL'ini kendi fark etti:** *"belgede artık
  `AynaCamSol/Sag` yok (231 nesne…)"*. `<document>` bağlamı işini yapıyor.
* **Tarama karar değiştirdi:** 76 bulgunun ~55'i tek satırda "kasıtlı
  montaj" diye geçildi ama **6'sı gerçek düzeltmeye yol açtı** — en netı
  susturucunun şasiye 1 mm girmesi (76.76 mm³), model *"görsel iş olsa da
  burası gerçekten yanlış görünür"* deyip düzeltti.

### 52.7 Testler

`tests/test_dogrulama_fc.py` 108 → **117** (kayıt boşken bulgu yazılıyor;
`yaz=True` kaydediyor; anahtar sıradan bağımsız; tekrar bastırılıyor;
bastırma dürüstçe yazılıyor; yanlış "geçen yok" hükmü verilmiyor;
`yaz=False` kaydetmiyor; kaydedilmemiş çift hâlâ bulgu).
`tests/test_executor_fc.py`'deki *"doğrulama raporu da çakışmayı gördü"*
kontrolü **tersine çevrildi** — artık tekrarlamaması bekleniyor — ve
kaydın **tek bloklu** olduğu ayrıca sınanıyor. Rapor yazan 11 suite
921 → **930**; hepsi 0 başarısız.

## 53. Uçak oturumu — 22.66 saniye altı satır "kontur yok" için ödendi

`LOG/2026-09-01_361c792d.txt`, 302 KB / 6016 satır, ~46 dakika. İndirilmiş
bir uçak mesh'i (`Flugzeug__2_`, 34 350 facet) **oran referansı** alınarak
yanına 3B baskıya uygun, parça parça, geçmeli yeni bir uçak kuruldu.
**38 kod bloğu — 36 başarılı, 2 hata (%95)**, bağlam 259 054, 1 GERİ-AL
(AI'ın kendi kararı). Çıktı: `Desktop\ucak_baski`, 7 parça ayrı `.stl` +
`.3mf` artı birleşik 237 KB `.3mf` — yedisi de `kapali=True,
kesisme=False, nonmanifold=False`.

Bu oturumun farkı: ölçüm kaynağı bir **dosya**, hedef ayrı **katılar**,
tüketici de FreeCAD değil **dilimleyici**.

### 53.1 Ölçülen kusur

İlk blok 60.2 saniye sürdü. Nereye gittiği yedek dosya üzerinde ölçüldü
(`.caddy-backups/Unnamed_2026-09-01_135650.FCStd`):

```
kesit_konturu(ucak, [3,8,15,25,35,43])  TOPLAM  22.66 sn
  _kabuk_ve_duzler (makeShapeFromMesh)          23.56 sn  ← maliyetin tamamı
  slice z=3..43, altı kesit                      0.01 sn her biri
```

Karşılığında altı özdeş satır:

```
kesit_konturu: z=3 kesitinde kontur yok
... (altı kez)
```

Cevabın boş çıkacağı **önceden, 0.05 saniyede** biliniyordu:

```
isSolid              False   0.016 sn
hasNonManifolds      True    0.001 sn
hasSelfIntersections True    0.016 sn
countComponents      494     0.000 sn
```

**700 kat ucuz bir bakış, 22.66 saniyenin boşa gideceğini söylüyordu.**
Üstelik teşhis aynı blokta zaten yazılmıştı: `kesif()` çıktısında
`baskiya hazir = HAYIR (kapali degil, kendiyle kesisme, non-manifold, cok
parca)`. Bilgi vardı, `kesit_konturu` ona bakmıyordu.

### 53.2 Neden REDDETMİYORUZ — ölçüm kuralı belirledi

İlk refleks "bozuk mesh'te dönüşümü hiç yapma" idi. Dört mesh ölçüldü ve
bu **çürüdü**:

| mesh | kapalı | non-manifold | kesişen | parça | dönüşüm | kontur |
|---|---|---|---|---|---|---|
| temiz kutu | ✔ | — | — | 1 | 0.00 sn | 1 |
| **açık** kutu | ✘ | — | — | 1 | 0.01 sn | **1** |
| 3 ayrık küre | ✔ | — | — | **3** | 0.13 sn | **3** |
| indirilen uçak | ✘ | ✔ | ✔ | 494 | 24.87 sn | **0** |

Yani **"kapalı değil" tek başına ret sebebi değil** (açık kutu doğru
kontur verdi) ve **"çok parça" da değil** (üç küre üç kontur verdi).
Başarısız olan tek örnek non-manifold + kendiyle kesişen olandı — ama tek
örnekten kural yazmak bu projede yasak (§41'in dersi: tek örnekle seçenek
yazmanın bedeli).

O yüzden hüküm vermiyoruz. Yapılan üç şey:

1. **Ödemeden önce söyle.** Dönüşüme girmeden 0.05 saniyelik kontrol
   koşuyor ve ne alınacağı yazılıyor:
   `kesit_konturu: mesh saglam degil (kapali degil, non-manifold,
   kendiyle kesisen, 494 ayrik parca); 34350 facet kabuga cevrilecek —
   bu uzun surebilir ve kesit hic cikmayabilir`
2. **Boş çıkarsa SEBEBİNİ söyle.** Altı özdeş "kontur yok" hiçbir şey
   anlatmıyordu; model doğru sonuca kendi akıl yürütmesiyle vardı. Artık
   sonda tek satır:
   `6 yukseklikte de kontur cikmadi — sebep YUKSEKLIK SECIMI DEGIL, mesh
   (...); kabuk saglam cikmadi. Bu nesnede kesit yolu kapali, baska bir
   olcum kullan (bbox tarama, olc(), mesafe()).`
   §35.2'nin dersi burada da geçerli: genel öğüt tetiklenmez, **adı konmuş
   emir** tetiklenir. "Dikkatli ol" değil, "bu yolu bırak, şunu kullan".
3. **Sağlam mesh'te tek satır bile gürültü yok**, katı nesnede ön kontrol
   hiç koşmuyor (mesh dalı değil).

Ölçüm ve gerekçe `islem._mesh_on_kontrol` docstring'inde duruyor.

### 53.3 Kapatılmayan kusur — görünürlük yetimi

Kullanıcının sözü: *"şaka mı yapıyorsun uçağın gövdesi yok sildin."*

Model haklıydı, kullanıcı da haklıydı. Olan şu:

1. 14:36'da gövdeye fileto denendi → `GovdeYuvaliF` oluştu,
   `GovdeYuvali.Visibility = False` yapıldı.
2. Sonraki blokta gövde baştan kurulmaya karar verildi → `GovdeYuvaliF`
   **silindi**.
3. `GovdeYuvali` **gizli kaldı**. Üç dakika boyunca 3B'de gövde yok.
4. Model son raporunda "Gövde (yuvalı) 25787.3 mm³, kapalı tek katı" diye
   hacmini yazdı — ölçüm nesneyi görüyor, **ekranı görmüyor**.

Host'un elinde bunu yakalayacak her şey vardı ve hiçbir şey söylemedi.
`GovdeYuvaliF` silindiği an `GovdeYuvali` şu hale geldi: **gizli + hiçbir
şeyin `Base`/`Tool`'u değil** = kullanıcının göremediği yetim parça.
`kesif.tuketilmis_mi` zaten tam bu soruyu cevaplıyor. Doğrulamaya tek
satır yeter:

```
gorunurluk: GovdeYuvali gizli ama hicbir seyin girdisi degil — 3B'de gorunmuyor
```

Bu, projenin en pahalı hata sınıfı: **sessiz yanlış cevap**. Model "bitti"
dedi, sayılar doğruydu, ekran yanlıştı, fark eden kullanıcı oldu.
Kullanıcının kararı: *"ilk hata host yüzünden onu boşver"* — yani bu madde
**bilinçli olarak açık bırakıldı**, unutulduğu için değil.

### 53.4 İyi giden şeyler

* **Ölçemediğini söyledi ve yolunu değiştirdi.** İlk turda: *"Mesh çok
  bozuk: 494 ayrı parça, açık, kendiyle kesişen. Bu yüzden
  `kesit_konturu` hiçbir yükseklikte kontur bulamadı. Orijinali kesitle
  kopyalamak mümkün değil, onu ancak oran referansı olarak
  kullanabiliriz."* Sonra kendi yazdığı X-kovası histogramıyla siluetin
  gerçek sayılarını çıkardı. Uydurmadı, vazgeçmedi, üçüncü yolu buldu.
* **Tasarım amacı sorusu (§32) tam yerinde çalıştı.** "(a) 3B baskı ←
  önerim bu" dedi; kullanıcı (c)'ye basıp hemen iptal edip (a) yazdı —
  modelin önerisi doğruydu. Sonrasında bütün oturum duvar ≥1.2 mm,
  0.2 mm sıkı geçme kurallarıyla yürüdü.
* **Dışa aktarma bloğu sözleşmeye harfiyen uydu:** geçici mesh üretti →
  her birini `isSolid/hasSelfIntersections/hasNonManifolds` ile doğruladı
  → yazdı → **aynı blokta sildi** → dosya boyutlarını listeledi. "Nesneyi
  bir turda üretip diğerinde okuma" kuralının ders kitabı örneği.

### 53.5 Küçük notlar

* İki hata da öğretici: `f.Shape.isValid()` boş şekilde patlıyor
  (`isNull()` önce sorulmalı) — model bunu kendi düzeltip "kontrol sırası
  yanlıştı" dedi; ve `Part.Ellipse` üç nokta bekliyor, iki yarıçap değil.
* **`kesif()` uçağı vazo sandı:** `taban kesit dis cap=194.5 ic cap=175.1
  duvar=9.707`, `duvar z=23.33: en ince 0.002626 mm`. Kap/vazo için
  tasarlanmış "taban/orta/ağız" şablonu bir uçak mesh'ine uygulanınca
  anlamsız sayı üretiyor. Model bunlara güvenmedi ama bağlamda gürültü
  olarak durdular.
* **Belge hiç kaydedilmedi** (`dosya : (kaydedilmemis)`). Bu sohbet
  kütüphaneden sürdürülürse §50'nin dördüncü dalı çalışır: model gelir,
  belge gelmez, yedeğin yolu bilgi olarak yazılır.

### 53.6 Testler

`tests/test_islem_fc.py` 117 → **127**: dönüşümden önce uyarı veriliyor;
uyarı kusurları adıyla sayıyor; facet sayısı yazılıyor; hepsi boş çıkınca
sebep söyleniyor; sebep mesh kusurunu tekrar ediyor; başka bir ölçüm
adıyla öneriliyor; sağlam mesh'te uyarı yok; sağlam mesh'te kontur var;
katıda ön kontrol koşmuyor; sağlam mesh'te boş sonuca mesh suçu
atılmıyor. Hepsi 0 başarısız.

## 54. Rack oturumu — grup, çocuğunun çakışmasını ikinci kez bildiriyordu

`LOG/2026-09-04_92416f9e.txt`. 19" rack çekmecesi (bir laboratuvar cihazı için). 53 dakika,
25 kod bloğu, **hepsi BAŞARILI** — tek bir çalıştırma hatası yok. Sonuç:
3 basılan parça, üçü de tek katı + kapalı + geçerli, aralarında geçiş yok,
AP242 STEP olarak yazıldı ve şema dosyadan okunarak doğrulandı. Bağlam
283 269. Hiç görsel kontrol istenmedi; ölçüm tamamen `olc` / `mesafe` /
`cakisma_kontrol` üzerinden gitti — §39'un istediği tam olarak buydu.

§52 sahada çalıştı: satır 2911'de `cakisma: 1 gecis blogun kendi
cakisma_kontrol ciktisinda zaten yazili — burada tekrarlanmadi`.

### 54.1 Ölçülen kusur: grup bir parça sanılıyordu

`REF_Cihaz` bir `App::DocumentObjectGroup`tu (satır 528). FreeCAD gruba
**`.Shape` VERİYOR** — çocukların bileşiği. Başsız doğrulandı:

```
hasShape: True   shape: Compound   solids 2   vol 1125.0
```

Sonuç, satır 2912-2914'teki üç BULGU satırının **ikisinin yankı** olması:

| satır | ne diyor | gerçek |
|---|---|---|
| `D_sag ... 2520 mm3 (REF_OnPanel ile)` | gerçek bulgu | ✔ |
| `REF_Cihaz ... 2520 mm3 (D_sol_k4 ile)` | `D_sol_k4 x REF_OnPanel`in aynısı | yankı |
| `REF_Cihaz ... 2520 mm3 (D_sag ile)` | 1. satırın aynısı | yankı |

Aritmetik kapatıyor: `REF_Cihaz` hacmi 2.06369e7 = `REF_Govde` 2.03345e7 +
`REF_OnPanel` 302 400. Grup, çocuklarının toplamı.

Aynı şey ölçüm tablosunda da vardı. Sentetik belgede birebir üretildi:

```
GRUP: kati=1 hacim=1000 mm3 bbox=10x10x10 mm
A:    kati=1 hacim=1000 mm3 bbox=10x10x10 mm
```

Grup ayrıca 25 nesnelik doğrulama kotasından bir slot yiyordu.

### 54.2 Neden `_akraba_mi` yetmedi

`_akraba_mi` grubu **kendi çocuğuna** karşı koruyor (`OutList` = çocuklar),
ama gruba karşı **üçüncü** bir nesneyi korumuyor. Yankı oradan geliyordu.

`kesif._ATLANAN` grupları zaten eliyordu — ama yalnız **aday** havuzunda
(`kesif.py:52`). Eksik olan iki yer vardı, ikisi de `dogrulama.py`de:
`_cakisma_taramasi`ın **dokunulan** listesi ve `dogrula`nın nesne döngüsü.
Yani kural zaten vardı; iki çağrı yerinde uygulanmıyordu.

### 54.3 Düzeltme ve ölçüm

Her iki yere `kesif._atlanir_mi` eklendi. Nesne döngüsünde eleme **sayı
sınırından ÖNCE** yapılıyor — yoksa grup, kotadan slot yemeye devam ederdi.

Logun iskeleti sentetik olarak kurulup önce/sonra ölçüldü:

| | bulgu | ölçüm satırı | bakılan nesne |
|---|---:|---:|---:|
| önce | 2 | 4 | 4 |
| sonra | **1** | **3** | **3** |

Kapsam daralmadı: çocuklar (`REF_Govde`, `REF_OnPanel`, `Duvar`) ölçüm
tablosunda duruyor ve gerçek geçiş bulgusu aynen bildiriliyor. Grubu
elemek bir şey **gizlemiyor**, çünkü grubun ölçtüğü her şey zaten
çocuğunun satırında yazılı.

### 54.4 Kusur sayılmayanlar

- **6 kez "iptal edildi"** — hepsi `kasitli_olduruldu_mu`, yani kullanıcı
  İptal'e bastı. Host tarafında sorun yok. Bir tanesinde (15:00:52 →
  15:01:14) kullanıcı aynı mesajı iki kez yazdı: iptal ettiği turla
  birlikte mesaj da gitmişti.
- **Host maliyeti temiz**: en yavaş blok 3.3 sn, en yavaş doğrulama
  1.71 sn. Ölçülecek bir yavaşlık yok, `AZAMI_NESNE` hiç aşılmadı.
- `N ayri kati — birlestirilmemis olabilir` notları yalnız kesici
  yardımcılara ait ve tek blokta çıktı (5 satır). Model de bunu
  kullanıcıya doğru açıkladı. Gürültü sayılacak kadar tekrarlamıyor.
- Bağlam yine 283k'ya çıktı, eşik uyarısı yok — "tokenim bitti" diyen
  kullanıcı oldu, host değil. §52.5'te açık duruyor.

### 54.5 İyi giden

- Model her bloğa `raise RuntimeError("on kosul saglanmiyor")` ön kabulü
  koydu; 25 blokta hiç çift-çalıştırma kazası olmadı.
- Kullanıcı "sanayide yaptırıcaz" deyince model 250 mm baskı tablası
  kısıtını kendiliğinden sorguladı, **soru sordu** ve tasarımı 6 parçadan
  3'e indirdi (satır 2469).
- STEP yazıldıktan sonra `FILE_SCHEMA` satırı kesikti; model "şemayı
  doğrulayamadım" deyip dosyayı okuyan ikinci bir blok yazdı. Uydurmadı.

### 54.6 Testler

`tests/test_dogrulama_fc.py` 117 → **127**. Yeni bölüm: *grup PARCA
DEGILDIR — cocugunun cakismasini tekrarlamaz*. İki ön kabul (grubun
`.Shape`i var, hacmi çocuğunun hacmine eşit) + bulgu tekliği + grup adının
ne bulguda ne ölçüm satırında geçmemesi + kotadan slot yememesi + çocuk
ölçümlerinin duruyor olması + `App::Part`in aynı sınıfta olması.

Tam takım: 950 kontrol, 11 rapor yazan takım, **0 başarısız**
(`test_executor_fc.py` rapor yazmaz, çıkış kodu 0).
