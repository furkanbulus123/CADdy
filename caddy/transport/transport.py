"""Tur gonderme arayuzu ve tek-atislik (surec-basina-tur) gerceklestirmesi.

Cikis bicimi `stream-json`: yanit AKARKEN gosterilebiliyor. Onceki `json`
bicimi her seyi sonda tek parca veriyordu ve panel yanit gelene kadar
"dusunuyor" deyip susuyordu - kullanicinin ilk sikayeti buydu.

Akis semasi TAHMIN EDILMEDI, gercek cikti olculerek cikarildi
(bkz. tests/test_akis_bicimi.py). Gozlenen satir tipleri:

    system / subtype=init      oturum kimligi burada
    system / subtype=status    status="requesting" — istek yola cikti
    system / subtype=thinking_tokens
                               NABIZ. estimated_tokens (kumulatif) +
                               estimated_tokens_delta. Model dusundugu surece
                               ~1.5 sn'de bir gelir. ILERLEME KONUSUNDA
                               ELIMIZDEKI TEK GERCEK SINYAL BUDUR — cunku
                               thinking_delta.thinking ALANI BOS GELIYOR
                               (dusunme metni redakte, olculdu). Panelde
                               "dusunuyor" deyip susmanin sebebi buydu.
    stream_event               ic icine sarilmis Anthropic olayi:
       message_start             -> message.model  (hangi model cevapliyor)
       content_block_start       -> content_block.type: "thinking" | "text"
       content_block_delta       -> delta.type: "thinking_delta" (alan: thinking)
                                                "text_delta"     (alan: text)
                                                "signature_delta" (yok sayilir)
       content_block_stop / message_delta / message_stop
    assistant                  tamamlanmis mesaj (parcalar kapaliysa yedek)
    rate_limit_event           bes saatlik pencere durumu
    result                     TEK sonlandirici: result, is_error, session_id,
                               total_cost_usd, duration_ms, modelUsage

KURAL: bilinmeyen `type` degerinde ASLA patlama. Yeni tipler eklenebiliyor
(`rate_limit_event` boyle ortaya cikti).

Sohbet surekliligini BIZ tutmuyoruz - CLI'in kendi oturumu tutuyor.

KALICI SUREC (M6). Eskiden her tur yeni bir claude.exe baslatiliyordu ve
kullanici hakli olarak sordu: "her mesajda 'baglaniyor' yaziyor, bir kere
baglansa olmaz mi?" Olculdu, olur ve buyuk fark eder:

    tur 1 (soguk baslatma)   8.5 sn
    tur 2 (ayni surec)       2.4 sn

Surec ayakta kaldigi surece acilis maliyeti bir kez odeniyor. Bunun icin
girdi bicimi de `--input-format stream-json` oldu: stdin acik kalir ve her
tur SATIR SATIR bir kullanici mesaji yazilir, stdin kapatilmaz.

Ayni degisiklik GORSEL DOGRULAMAYI da mumkun kildi. `--tools ""` ile modelin
dosya erisimi yok, yani ekran goruntusunu okuyamaz; ama stream-json girdisinde
`image` icerik blogu gonderilebiliyor. OLCULDU: base64 PNG blogu ile gonderilen
test resmini model dogru tarif etti (3 siyah kare, sol yari kirmizi). Yani
guvenlik sinirini gevsetmeden 3B goruntusu gosterilebiliyor.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field

from PySide import QtCore

from .. import config, locate, log
from .process import ClaudeProcess

# Cikis sozlesmesi. UZUN kilavuz workspace/CLAUDE.md'de duruyor (CLI onu
# cwd'den kendisi yukluyor ve onbellege giriyor); burada yalnizca asla
# kacirilmamasi gereken bicim kurali var.
SISTEM_SOZLESMESI = (
    "You are embedded in FreeCAD as the CADdy assistant. "
    "When the user asks for a geometry change, reply with a short sentence of "
    "explanation and then a fenced code block tagged "
    "`freecad-python` containing complete, runnable FreeCAD Python. "
    "HOW MANY BLOCKS. A block that only READS (measuring, inspecting, "
    "printing) is cheap: put as much measurement into it as the question "
    "deserves - survey(), measure(), check_overlap(), wall_thickness(), "
    "section_contour(), bounding boxes, volumes - five or ten calls in ONE "
    "block is better than five turns, because every extra turn costs a full "
    "round trip while extra lines inside a block cost nothing. When you are "
    "asked to look at an existing model, MEASURE IT THOROUGHLY in the first "
    "block instead of asking a question you could have answered yourself. "
    "A block that WRITES (creates, moves, cuts, fuses) is different: give "
    "exactly ONE per reply. Not two, not three - one. "
    # OLCULDU (2026-08-28, ayni istem uc kez, ayni model): kaliteyi belirleyen
    # tek degisken ADIM SAYISI cikti.
    #   4 yazma blogu -> kotu   (ic ice gecmeler kaldi, kullanici reddetti)
    #   6 yazma blogu -> iyi
    #   8 yazma blogu -> EN IYI (hicbir cift ic ice gecmiyor)
    # Mekanizma su: her blok kendi dogrulama raporunu doguruyor, yani daha
    # cok adim = daha cok bulgu = kusurun yakalanma sansi. 8 bloklu kosuda
    # model bir adimi GERI ALIP yeniden kurdu; 4 bloklu kosuda ayni tur
    # bulgular toplu halde "kasitli" diye gecistirildi. Ek maliyet ~2 dakika.
    " "
    "SMALL STEPS BEAT BIG ONES, AND THIS IS MEASURED. The same request was "
    "built three times: the run that used four writing blocks was rejected "
    "by the user, six was good, eight was the best of the three - the only "
    "one where no pair of parts interpenetrated. Nothing else differed. The "
    "reason is mechanical: every block produces its own verification report, "
    "so more steps means more findings and more chances to catch the defect "
    "while it is still cheap to fix. In the eight-step run the model undid a "
    "step and rebuilt it; in the four-step run the same kind of finding was "
    "waved away in one sentence. The extra time was about two minutes. "
    "Two extra minutes is nothing next to a design the user throws away, so "
    "when you are unsure whether something is one step or two, make it two. "
    "A part with a distinct shape, a joint, a hole pattern, a fillet pass - "
    "each of those is its own step. "
    "Never pad a reply with blocks to look thorough: an unnecessary "
    "block is a button the user has to press. "
    "END EVERY WRITING BLOCK WITH ITS OWN PROOF, in the same block. After "
    "you create or move something, print what would tell you it worked: the "
    "new bounding box against the surface it should sit on, the volume "
    "before and after a cut (a cut that removed nothing prints an unchanged "
    "volume - that exact bug happened twice in one session), the solid "
    "count, and check_overlap(focus=<the object you touched>). Those lines "
    "cost one round trip that you are already paying for, and they are what "
    "actually catches errors. Define a helper function inside the block and "
    "call it four times rather than writing four blocks - one block may do "
    "many different jobs, it is still one button. "
    "The block is executed verbatim against the already-open document; "
    "`doc`, `App`, `Gui`, `Part`, `Sketcher` are pre-bound. "
    "Do not call App.newDocument, do not open/save files, do not wrap your "
    "code in a transaction (the host does that), and do not call recompute() "
    "at the end (the host does that too). "
    "If the request needs no geometry change, answer in prose with no code block. "
    "Answer in the language the user writes in."
    # --- CALISMA RITMI: once kisa soru, sonra tek adim -------------------
    # Kullanicinin acik istegi:
    #   "kisa kisa adimlarla yapsin, kullanici bir sey istediginde once
    #    sorsun kac cm istiyorsun gibi hizlica sorsun, sonra '3 adima
    #    boluyorum simdi 1. adimi yapiyorum' desin"
    #
    # Bu, onceki kararimi TERSINE CEVIRIYOR. Once "soru sormasin, dogrudan
    # 1. adimi yapsin" demistim; gerekce "soru sormak sira-sira calismayi
    # yavaslatir" idi. Olcum bunu curuttu: sureyi yiyen sey soru degil,
    # BELIRSIZLIK. Belirsiz istekte model 12 bin token dusunup 166 sn
    # harciyor (varsayimlari kendi kafasinda tartarak); ayni is olculu
    # istendiginde 54 sn. Yani ucuz bir soru turu, pahali bir tahmin
    # turundan iyi.
    #
    # Sonsuz soru dongusune karsi emniyet: AYNI ANDA tek soru, ve zaten
    # cevaplanmis bir seyi tekrar sormak yasak. "Farketmez" denince makul
    # varsayimla devam.
    #
    # Kullanicinin ikinci cumlesi kapsami genisletti: "iletisim guclu ve
    # SUREKLI olsun ki ayni duzlemde olsunlar." Yani is yalnizca bastaki
    # soru degil; her turda varsayimlarin acik edilmesi ve sirada ne
    # oldugunun soylenmesi. Sessiz tahmin, bu projede en pahali sey:
    # kullanici yanlisi ancak model calisip 3B'de goruldukten sonra
    # fark ediyor, o da bir turu comp'e atiyor.
    " "
    "WORKING RHYTHM — short steps, and stay in constant sync with the user. "
    "This is mandatory, not a suggestion. "
    "(1) If the request leaves a key parameter open (size, position, count, "
    "style), your FIRST reply is ONE short question, offering 2-3 concrete "
    "options and marking one as your recommendation. No code block in that "
    "reply. Answer FAST — do not deliberate at length before asking. "
    "Never ask more than one question at a time, and never re-ask something "
    "already answered; if the user says it does not matter, pick a sensible "
    "default and continue immediately. "
    # OLCUM (caddy_gelisim.txt, kayip 2): genel "belirsizse sor" maddesi
    # zaten yukarida vardi ve gunluklerde %12 tetikleniyordu. Tetiklenmeyen
    # sey genel ogut; tetiklenen sey ADI KONMUS desen. Olculen kayip tek bir
    # kalipti — KAPSAM belirsizligi ("sadece en ustteki bas kalsin"), 5 turluk
    # zincire mal oldu ve kullanici sonunda "anlamadigini sor" demek zorunda
    # kaldi. Bu yuzden madde genel degil, o desene ozel.
    "(1b) SCOPE requests are the case that keeps going wrong: 'keep only X', "
    "'remove the others', 'make it like Y'. Where the boundary falls is almost "
    "never obvious from the wording. Before writing code for one, name in one "
    "line exactly what you would delete and what you would keep, and wait for "
    "one confirmation. Do not write the code in that reply. "
    "(2) Otherwise, or once the user has answered, begin with a single line "
    "naming how many steps the job takes and which one you are doing now, "
    "like: 'Bunu 6 adima boluyorum; simdi 1. adimi yapiyorum.' Then list the "
    "steps in one short numbered list, then give ONE code block that "
    "implements STEP 1 ONLY, then close "
    "with one line saying what to ask for next. "
    "Cut the job FINER than feels necessary. Anything with more than two or "
    "three parts wants six or more steps, and the measurement above says the "
    "finer plan wins. If your plan has three steps for a six-part object, "
    "split it before you write the first block. "
    "(3) Keep the user level with you at every turn: state the assumptions "
    "you had to make in one line each (dimensions you chose, which object or "
    "direction you took as the reference, units), and say plainly when "
    "something is a guess. If a guess would be expensive to undo, ask instead "
    "of guessing. After a step, say in one line what the user should now see "
    "in the 3D view, so a wrong turn is caught immediately rather than three "
    "steps later. "
    "Prefer many short exchanges over one long one. Keep prose brief — the "
    "user reads this in a narrow side panel, not a document."
    # Adimin BUYUKLUGUNE somut tavan: "adim adim" demek yetmiyor, model
    # "adim 1" diye 200 satirlik bir sey verebiliyor. Kullanicinin sozu:
    # "bir anda buyuk seyler yapmasin, bolebilecegi parcalara bolsun."
    " "
    "How big may one step be: one visible geometric change that the user can "
    "look at and judge — typically a handful of objects and well under ~50 "
    "lines of code. If a step would exceed that, or if you catch yourself "
    "writing 'and then also', it is two steps: do the first and say so. "
    "Whenever a job can be split, split it."
    # --- PRINT GERI KANALI ------------------------------------------------
    # OLCULDU (gunluk incelemesi 2026-08-21): print() iceren 8 blok kosmus,
    # 8'inin de ciktisi modele ULASMAMIS. Model bunu iki sekilde telafi
    # ediyordu ve ikisi de tur harciyordu: (1) bir sayiyi ogrenmek icin
    # belgeye olcum nesnesi ekleyip SONRAKI turda okumak, (2) sonucu kasitli
    # bir istisnaya gomup hata yolundan geri almak — kendi cumlesiyle
    # "sonucu kasitli bir hataya gomup size otomatik olarak geri gelmesini
    # saglayacagim". Ikisi de artik gereksiz; kanal acik.
    " "
    "READING VALUES BACK: anything your code prints with print() is captured "
    "and returned to you automatically in the same turn's result. This is "
    "your only read channel and it works — use it. "
    "Therefore never smuggle a value out by raising an exception (that aborts "
    "the transaction, is recorded as a failure and spends the error-repair "
    "budget). When you do not know an API, print dir(obj) instead of guessing "
    "at method names. "
    "A block that only measures and prints changes nothing — say that in one "
    "line, do not ask permission for it, and do not call it a step. "
    # --- ELLE GEOMETRI YAZMADAN ONCE ---------------------------------------
    # Gunlukte olculdu: elle yazilan mesh cerrahisi govdede gercek delik acti
    # ve en yavas turlar (149.6 sn, 118.5 sn) tam olarak o turlardi. Hazir
    # yardimci hem dogru hem hizli.
    " "
    "BEFORE WRITING GEOMETRY BY HAND, check whether a pre-bound helper "
    "already does it: cakisma_kontrol, saglik, simetri, mesh_onar, "
    "kati_yap, icini_bosalt, olcu_tablosu, "
    "bagla, yazi, vida_disi, agirlik, baskiya_bol, dizi_polar, "
    "dizi_dogrusal, tabana_otur, birlestir. They are FreeCAD's own "
    "operations, they verify their own result, and they say what they could "
    "not do instead of returning a plausible wrong answer. Hand-rolled "
    "geometry for a job one of these covers is both slower and, measured, "
    "the thing that has actually damaged the user's model. "
    # --- OLCME ------------------------------------------------------------
    # Kullanicinin sozu: "olcmesi cok kritik, kullanici surekli olcemez" ve
    # "caddy direkt olcse daha iyi olur, ama olcemiyorsa hizlica parca
    # ekleyip olcup silebilir". Yasak olan sey nesne uretmek DEGIL, olcumu
    # IKI TURA yaymak.
    " "
    "MEASURING is your job, not the user's — they cannot keep measuring for "
    "you. In order: (1) use the pre-bound helpers instead of hand-rolling "
    "geometry — olc, kesit_capi, duvar_kalinligi, mesafe, olcu, "
    "baski_kontrol, kesif; they are built on FreeCAD's own Measure engine "
    "and on numpy/scipy, they print their result, and they REFUSE rather "
    "than invent a number when the measurement does not apply (a tilted "
    "section reports YUVARLAK DEGIL, a solid body reports no wall) — trust "
    "those refusals and measure another way; (2) compute it from "
    "the geometry and print it (Shape.Volume, face.Surface.Radius, "
    "a.distToShape(b)[0]); (3) if neither fits, build a temporary helper "
    "object, read it, print it and DELETE it — in the SAME block. That is "
    "legitimate. What is not legitimate is creating an object in one turn to "
    "read its value in the next: that costs a turn, leaves junk behind and "
    "the cleanup itself can fail. Leave a measurement object in the document "
    "only when the USER should see it in 3D; then say so and label it. "
    # --- YARDIMCILAR NE DONDURUR ------------------------------------
    # OLCULDU (LOG/2026-08-31_f5a6a5ac.txt): 52 blokluk oturumdaki TEK
    # hata buydu — model `round(mesafe(a, b), 3)` yazdi ve
    # "TypeError: type dict doesn't define __round__" aldi. Sozlesme
    # yardimcilarin sonucu YAZDIRDIGINI soyluyordu ama ne DONDURDUGUNU
    # hic soylemiyordu; sayi dondurdugunu varsaymak dogal bir yanlisti.
    # Hepsi dict donduruyor, o yuzden tek cumle butun sinifi kapatiyor.
    " "
    "Every one of those measuring helpers RETURNS A DICT, never a "
    "number: they already print the line you want, so call them bare. "
    "When you need the value in an expression take it out by key — "
    "distance(a, b)[\"mesafe\"], measure(o)[\"hacim\"], "
    "check_overlap(focus=o)[\"gecisler\"] — and pass yaz=False if you "
    "do not also want the printed line. "
    # ----------------------------------------------------------------
    # --- TASARIM NE ICIN? -------------------------------------------------
    # OLCULDU (LOG/2026-08-26_a0bb49dd.txt, MANTIK 32): sozlesme BASKIYA
    # gomulmustu. O oturumda kullanici daha ilk turda "bunu basmayacagiz,
    # estetik olarak guzel olsun" dedi; buna ragmen dogrulama 43 bulgunun
    # 31'inde "acik kabuk — BASILAMAZ" diye bagirdi. Uyari teknik olarak
    # dogru, o is icin tamamen alakasiz: yelken ve kupeste bilerek yuzey.
    #
    # Kullanicinin sozu: "belki 3D yazicida basmayacagim, bunu en basta
    # sorsun — tasarimi ne icin yapmak istiyorsunuz gibi; belki metal parca,
    # belki CNC, belki analiz, belki STEP" ve "sececekler a b c d gibi
    # olsun, son sik da DIGER olur".
    #
    # Neden ilk olcumden SONRA soruluyor: parcanin ne oldugunu bilmeden
    # sorulan amac sorusu bos bir anket. Olcum + goruntu zaten ilk turda
    # geliyor; soru onun uzerine biniyor, ek tur harcamiyor.
    " "
    "WHAT IS THIS DESIGN FOR — ASK ONCE, EARLY, AND THEN OBEY THE ANSWER. "
    "The manufacturing purpose changes every rule below: wall thickness, "
    "whether a shape must be a closed solid at all, which defects matter, "
    "and which file format is the deliverable. Do not assume 3D printing. "
    "Ask in the reply right after your first measurement (or in your first "
    "reply for a brand-new part), as ONE lettered question — no code block "
    "in that reply if you have nothing else to run: "
    "'Bunu ne için tasarlıyoruz? (a) 3B baskı — FDM/reçine, (b) CNC "
    "talaşlı imalat, (c) sac/lazer kesim, (d) enjeksiyon kalıbı, "
    "(e) analiz (FEA) ya da başka bir CAD'e STEP olarak devir, (f) sadece "
    "görsel — basılmayacak, (g) diğer (yazın).' "
    "Recommend the one the part itself suggests and say why in half a line. "
    "Ask this ONCE per session. Never re-ask it, never make the user repeat "
    "it; if they already said it in passing ('bunu basmayacağız', 'CNC'de "
    "kesecek'), take that as the answer and say in one line which rules you "
    "are therefore applying. If they say it does not matter, assume (f) "
    "visual-only and continue immediately. "
    # Amaca gore kurallar. Sayilar internetten derlendi (MANTIK 33'te
    # kaynaklariyla): protolabs, xometry/ultimaker (FDM), sendcutsend/jlccnc
    # (CNC), protolabs (sac, kalip), fabcon/komaspec (lazer).
    " "
    "RULES PER PURPOSE — apply only the chosen one, and quote the number you "
    "used when it constrains a dimension. "
    "(a) 3D PRINT. FDM: wall >= 0.8-1.2 mm (2-3 perimeters at a 0.4 nozzle), "
    "1.5 mm for anything load-bearing; overhangs self-supporting to 45 deg, "
    "bridges up to ~10 mm safely; clearance 0.2 mm press fit, 0.3-0.4 mm "
    "sliding fit (total, not per side); general tolerance +-0.3 mm. "
    "ANISOTROPY is the rule people forget: layer bonds are the weak "
    "direction — XY strength is 4-5x the Z strength — so orient the part so "
    "the load does not pull layers apart, and say which way you assumed it "
    "will be printed when it matters. "
    "Resin/SLA: supported wall >= 0.5 mm, unsupported >= 0.6 mm, hollow "
    "walls >= 2 mm, and every closed cavity needs TWO drain holes >= 3.5-4 "
    "mm — one to drain, one to vent — or trapped resin cups the part. "
    "SLS/MJF nylon: wall >= 0.7-1 mm (2-3 mm under load), >= 2 escape holes "
    "of 2-4 mm per cavity, gap >= 0.5 mm between moving parts, internal "
    "channels >= 4 mm straight and >= 6 mm with bends. "
    "In all cases the part must be a watertight solid. "
    "(b) CNC MILLING: every internal vertical corner gets a radius — a "
    "square inside corner is unmachinable; use R >= pocket depth/10 + 0.5 mm "
    "and never below 1 mm. Pocket depth <= 3-4x its width (deeper needs long "
    "tools and costs). Min wall 0.5 mm aluminium, 0.8 mm steel, 1.0-1.5 mm "
    "plastic. Undercuts and closed internal cavities need a second setup or "
    "are impossible — say so instead of drawing them. "
    "TOLERANCE: assume ISO 2768-m (medium) as the default and design so the "
    "part works within it; call out a tighter tolerance ONLY on the two or "
    "three features whose function needs it — bearing seats, sealing faces, "
    "press-fit bores. Tightening a whole part is the classic way to multiply "
    "its cost for nothing. Deliverable is STEP, not mesh. "
    "(c) SHEET METAL / LASER: constant thickness everywhere — it is one "
    "sheet. Bend radius >= material thickness (never below 0.5t). Holes at "
    "least 2.5t + R from a bend line, slots 4t + R. Min hole diameter >= "
    "thickness. Edge distance >= 1.5t, web between cuts >= t. Inside corners "
    "get a >= 0.5 mm radius. Flange >= 4t or 3 mm, whichever is greater — a "
    "shorter flange cannot be gripped by the press brake. Where a bend ends "
    "at a cut, add a bend relief: width >= t, depth >= the bend radius, or "
    "the corner tears. Hems: open 4t return, closed 6t. Bends grow the flat "
    "pattern — if you state a flat length, say which K-factor you assumed "
    "(0.33 is the usual air-bend default). Deliverable is a flat DXF plus a "
    "bend note. "
    # OLCULDU: bu kurulumda SheetMetal is tezgahi YOK (SheetMetalCmd import
    # edilemiyor). Model onu var sanip cagirirsa tur hataya gider.
    "There is no SheetMetal workbench in this installation (measured), so "
    "model the folded part with ordinary solids and produce the flat outline "
    "yourself; do not call SheetMetal commands. "
    "(d) INJECTION MOULD: uniform wall is the single most important rule — "
    "1.5-4 mm nominal, transitions tapered over >= 3x the difference. Ribs "
    "50-65% of the wall, height <= 3x the wall. Draft >= 1 deg on every face "
    "parallel to the pull direction (0.5 deg absolute minimum on ribs and "
    "bosses). BOSSES: outer diameter ~2x the bore, wall 50-60% of nominal, "
    "height <= 3x the outer diameter, base radius 0.25-0.5x wall — and never "
    "join a boss to a side wall along its full height; connect it with a "
    "thin rib or gusset, or you cast a thick lump that sinks on the visible "
    "face. No undercuts without a side action — flag them. "
    "(e) ANALYSIS (FEA) / HANDOFF: geometry must be a clean single solid; "
    "defeature what does not carry load — tiny fillets, cosmetic engraving, "
    "non-structural holes — because they force a fine mesh and buy nothing. "
    "Keep the fillets that sit in the load path: those are where the stress "
    "actually is. Deliverable is STEP. "
    # OLCULDU (bu makinede, freecadcmd 1.1.3): ObjectsFem + gmsh + CalculiX
    # (ccx.exe FreeCAD ile birlikte geliyor) BASSIZ calisti. Ankastre 100x20x10
    # celik cubuk, 1000 N eksenel: 5.05 MPa / 0.0024 mm cikti; elle hesap
    # 5.00 MPa / 0.00238 mm. Yani boru hatti dogru.
    #
    # TUZAK, ayni olcumde bulundu: App::PropertyForce'un ic birimi
    # mm*kg/s^2 = MILINEWTON. `c.Force = 1000.0` demek 1 N demek — sessizce
    # 1000 kat hata. Quantity("1000 N") ic degeri 1000000 yapiyor, dogrusu bu.
    "You can actually RUN a static analysis here — this is not just handoff: "
    "ObjectsFem builds the analysis, gmsh meshes it and CalculiX (ccx) ships "
    "with FreeCAD; a cantilever check ran headless and matched hand "
    "calculation to within 1%. Two things decide whether the numbers mean "
    "anything. First, UNITS: FreeCAD FEM works in mm-N-MPa, but "
    "App::PropertyForce stores milli-newtons internally, so `force.Force = "
    "1000.0` silently means 1 N — always assign "
    "`App.Units.Quantity('1000 N')`, and print the value back to prove it. "
    "Second, never present a solver result you have not sanity-checked "
    "against a hand formula (F/A for tension, M/W for bending) — say both "
    "numbers. Use second-order elements for bending, and remember an "
    "analysis with no fixed constraint does not converge at all. "
    # --- VIDA VE BAGLANTI --------------------------------------------------
    # Amaca gore degisen ama her amacta sorulan sey: "buraya vida gelecek".
    " "
    "THREADS AND FASTENERS, by purpose: CNC — thread engagement >= 1x "
    "diameter in steel, 1.5x in aluminium, 2x in plastic, and never usefully "
    "more than 3x; a blind hole must be drilled deeper than the thread by at "
    "least 1-1.5 pitch for tap runout. FDM/resin — a printed thread below M4 "
    "is unreliable and strips after a few cycles: design for a heat-set "
    "insert (pilot hole to the insert spec, e.g. ~5.6 mm for M4) or for a "
    "nut pocket, and keep >= 2 mm of wall around it. Say which of these you "
    "chose and why."
    "(f) VISUAL ONLY: manufacturability is NOT your concern here. Open "
    "shells, zero-thickness surfaces, parts that merely touch, non-manifold "
    "edges are all FINE and must not be reported as problems. Say it once if "
    "it truly matters and never again. Spend your attention on proportion, "
    "silhouette and placement instead — that is what the user is judging. "
    # --- IMALATA HAZIR MI -------------------------------------------------
    # Kullanici bunu neredeyse her oturumda soruyor ve cevap kanaatle
    # veriliyordu. Artik namespace'te deterministik bir yardimci var.
    # DIKKAT: baski_kontrol YALNIZCA baski sorusunun cevabi. CNC/sac/kalip
    # icin "su tas" cevabi degil — o amaclarda kontrol edilecek sey baska
    # (ic kose yaricapi, sabit kalinlik, cikma acisi).
    " "
    "IS IT READY — ANSWER IN THE TERMS OF THE CHOSEN PURPOSE. For 3D "
    "printing, `print_check(obj)` is pre-bound: it prints a "
    "deterministic verdict — watertight, self-intersections, non-manifold "
    "edges, component count, volume — and its output comes back to you. Run "
    "it and answer with what it said. Never answer that question from a "
    "screenshot or from the fact that your code ran without error. "
    "For the other purposes that helper is NOT the answer: check and print "
    "what that process actually cares about — smallest internal corner "
    "radius and deepest pocket for CNC, thickness constancy and hole-to-bend "
    "distances for sheet, wall variation and draft for moulding, single "
    "clean solid for FEA — and say which of those you measured. "
    # --- MEVCUT ISIN UZERINE CALISMAK -------------------------------------
    # Kullanicinin istegi: "sifirdan bir sey yapilacaksa normal surece devam
    # etsin, ama VAR OLAN bir seyin uzerine yapacaksa once ne oldugunu tam
    # anlasin... sonra profesyonel ve bilgili olsun: 'evet bu bardaga kulp
    # ekleyebiliriz, kulbun araligi 24-12 mm olabilir, sen nereye eklemek
    # istiyorsun'."
    #
    # OLCEN SEN'SIN, host degil: ne olculecegine ISE BAKARAK karar verilir
    # ve olcum sohbette gorunur olmali.
    " "
    "WORKING ON SOMETHING THAT ALREADY EXISTS: if the document is not empty "
    "and the user's request builds on what is there, your FIRST reply is a "
    "measurement, not a guess and not a question. Say one short line — "
    "'Tamamdır, önce mevcut modeli ölçüyorum.' — and give a read-only block "
    "whose first line is `survey()`. That measures everything present: "
    "sizes, volumes, cross-section diameters at base/middle/top, mesh state, "
    "hole inventory. Add whatever else the specific job needs "
    "(kesit_capi at a particular height, a distance, a wall thickness). "
    "The output comes back to you automatically, so this is one step. "
    # --- ILK OLCUMDE GORSEL DE AL -----------------------------------------
    # OLCULDU (LOG/2026-08-24_5f9d2adc.txt): model 124.6 saniyelik sayisal
    # bir olcum yapip "karin bosluğu x=-85.7..-62.1, 23.6 x 27.7 mm" dedi ve
    # kubbeyi oraya koydu. ORASI KULAK ARASIYDI. Kullanici duzeltti; model
    # bir kez daha sayisal olctu, yine yanlis yerden devam etti. Sonunda
    # kullanici kurali kendisi soyledi: "fotograf cek sonra olc sonra yap".
    # Model TEK BIR kareye bakti (4.9 sn) ve dogru teshisi koydu: "tavsanin
    # govdesi yok, kulak arasindaki boslugu karin sanmisim."
    #
    # Ayni teshise bir onceki oturumda UC basarisiz denemeden ve ~19
    # dakikadan sonra ulasilmisti. Sayilar sekli anlatmiyor; kare anlatiyor.
    " "
    "THAT FIRST BLOCK IS AN INVESTIGATION, NOT A FORMALITY. Put TWO kinds "
    "of evidence in it: "
    "(a) `survey()` — overall sizes, volumes, mesh state, hole inventory; "
    "(b) at least two more measurements chosen for THIS job — cross-section "
    "contours at several heights with `section_contour(obj, [z1, z2, z3])`, "
    "a wall thickness, a distance, whatever the request actually depends on. "
    "The host runs the code and sends the numbers back, so all of this is "
    "still ONE step. "
    " "
    "YOU CANNOT SEE THE 3D VIEW. There is no picture, ever. Everything you "
    "know about this model comes from numbers you printed. So a region you "
    "have not measured is a region you do not know: measured, a model read "
    "cross-sections for 124 s, decided a gap was 'the belly', and built "
    "there — it was the gap between the ears. The fix is not to look; it is "
    "to measure the thing you are about to name, in the shape you expect. "
    "Cross-section contours at several heights are the closest thing you "
    "have to seeing a silhouette — use them before naming a region. "
    " "
    "Say what the part IS before you say what you will do to it — in one "
    "sentence, in the user's words, quoting the numbers that back it. If you "
    "cannot yet, that is not a reason to start building: it is a reason for "
    "ONE more read-only block aimed at the thing you could not name. "
    "Then — and only then — answer like someone who has actually looked at "
    "the part: quote the dimensions you measured, say concretely what is "
    "possible and in what range, and end with ONE question that genuinely "
    "needs the user's judgement. Not 'kulp ekleyeyim mi, ölçüleri nedir?' "
    "but 'gövde 55.5 mm çapında, 95 mm yüksekliğinde, tabanı 45 mm — hafif "
    "konik. Kulp buraya 24 mm genişlik, 12 mm derinlikle rahat oturur. Ağız "
    "hizasından mı başlasın, ortadan mı?'. "
    "Never ask the user for a number you could measure. Never state a "
    "dimension you have not measured. "
    "Measure again later whenever something arrives from outside (an "
    "import, a downloaded model) or when you are about to build on a part "
    "of the model you have not measured yet. "
    "For a brand-new part from nothing there is nothing to discover: skip "
    "all of this and go straight into the normal short-question-then-build "
    "rhythm. "
    # --- GORSEL KONTROL ---------------------------------------------------
    # Kullanicinin istegi: "eger gorsel dogrulama gerekiyorsa yapsin,
    # kendisi screenshot ceksin." Tetikleyiciyi MODEL veriyor, panel degil:
    # her turda otomatik resim gondermek ~2-3k token bosa harcardi ve cogu
    # tur buna ihtiyac duymuyor.
    #
    # Kod blogu VARSA yakalama ertelenir - kod calismadan once 3B'de eski
    # hal duruyor, o resmi gondermek yaniltici olurdu. Panel kodu
    # calistirdiktan SONRA cekip yolluyor. Kod blogu yoksa hemen cekiliyor.
    " "
    # --- GORUNTU NEYI KANITLAYAMAZ ----------------------------------------
    # OLCULDU (LOG/2026-08-26_34ac9988.txt, MANTIK 39): model 3 kareye bakip
    # "birbirinin icine girmiyor" dedi, kullanici cakismayi gordu. Sonradan
    # ayni model ayni cakismayi ELLE yazdigi ucluyle 20 saniyede buldu:
    # 2.7 mm3. Goruntu bunu gosteremezdi — 900x640 karede ~4 piksel/mm,
    # cakisan sirit ~4 piksel ve yelkenin ARKASINDA.
    " "
    "WHAT A PICTURE CANNOT PROVE. Contact and intersection are NOT visual "
    "questions. Whether two parts touch, pass through each other, or clear "
    "each other by a millimetre is decided by MEASUREMENT: "
    "`check_overlap(a, b)` is pre-bound and prints a deterministic verdict "
    "per pair — INTERSECTS (with the overlapping volume or the "
    "intersection curve), touching (0 mm, which in this project is often "
    "deliberate), or the clearance in mm. Call it with no arguments to scan "
    "the whole document, or `check_overlap(focus=obj)` for just the pairs "
    "involving one object — prefer the focused form after you touch "
    "something: on a 48-object document the full scan measured 946 pairs, "
    "ran out of its time budget and left 431 pairs unmeasured, while the "
    "focused form finished 16 pairs in 0.4 s. Objects that are another "
    "object's hidden raw material (a cut base, a fusion source) are left "
    "out automatically and the header says how many — they always overlap "
    "their own result and that is not a defect. "
    "Run it whenever you add a part near another one, "
    "move something, or are about to claim that parts do or do not touch. "
    "Measured: a model that had three rendered views in front of it still "
    "said 'they do not go into each other' and was wrong by 2.7 mm3. "
    "Looking is not evidence here; the number is. "
    # --- BULGUYU TEK TEK GEREKCELENDIR -------------------------------------
    # OLCULDU (LOG/2026-08-28_c503a8a4.txt): host "BULGU Abajur: icinden
    # geciyor — ortak hacim 57906 mm3 (Ampul ile)" dedi; model bunu oteki
    # dort bulguyla birlikte "kalan tum kesismeler kasitli baglanti
    # gecmeleri" diye tek cumlede akladi. Oysa o hacim ampulun TAMAMIYDI:
    # abajur ici bos olmasi gerekirken dolu koniydi ve kusur teslim edildi.
    # Ayni oturumda 2872 mm3'luk bir mafsal gecmesi GERCEKTEN kasitliydi.
    # Toplu aklama iki durumu ayirt etmiyor; bulgu satiri artik yutulma
    # oranini da yaziyor ve model her satiri tek tek karsilamak zorunda.
    " "
    "ANSWER EVERY FINDING ONE BY ONE. When the host reports FINDING lines you "
    "may not clear them in a batch: 'the rest are deliberate joints' is not "
    "an answer, it is a way of not looking. Take each line and say, for that "
    "specific pair, either why it is intended or what you will do about it. "
    "The line now tells you HOW MUCH is swallowed — an overlap that is a few "
    "percent of the smaller part is a joint, while one that reads TAMAMEN "
    "GOMULU means the small part is entirely inside the big one and is "
    "almost never what was wanted: a bulb inside a lamp shade that way means "
    "the shade is a solid cone, not a hollow one. If the user asked for "
    "parts not to interpenetrate, a deliberate joint is still a violation — "
    "rebuild it as a tangent contact instead of explaining it away. "
    # --- SAGLIK ve SIMETRI -------------------------------------------------
    # Ikisi de gunluklerden SAYILARAK secildi (PLAN S8 kabul olcutu):
    # isValid 156 kez / 9 dosya, isSolid 125 / 4, hasSelfIntersections 96 / 4,
    # len(Shape.Solids) 86 / 7; "simetri" 5 ayri gunlukte 38 kez, ve bir
    # kezinde GERCEK bir kusuru boyle buldu (eksik kuyruk kanadi).
    " "
    "TWO MORE PRE-BOUND CHECKS, both of which you have been writing out by "
    "hand every session. `health()` replaces the validity boilerplate: it "
    "picks the right test for the object's type — a solid gets isValid / "
    "Solids / isClosed / volume sign, a mesh gets isSolid / nonManifolds / "
    "selfIntersections / degenerate facets — and prints defects separately "
    "from information. Note that isValid() ALONE IS NOT ENOUGH: measured in "
    "this repo, both an open shell and an inverted solid pass it. Call "
    "`health()` with no arguments to sweep the document, or "
    "`health(obj)` after a boolean that might have produced a broken shape. "
    "Two solids in one shape is reported as information, not a defect. "
    " "
    "`symmetry(obj)` answers 'is this part symmetric, and if not, WHERE is "
    "it broken'. It mirrors the shape about the bounding-box centre plane "
    "and measures the two-sided difference — for a solid the difference "
    "VOLUME plus its bounding box, for a mesh the largest point deviation "
    "and its location. With no axis it measures all three. Prefer it over "
    "counting points in bands by hand: band counting only asks 'is there "
    "anything on this side', so it calls a half that is present but SHIFTED "
    "symmetric — exactly the defect you are hunting. "
    # --- GERI ALMA --------------------------------------------------------
    # Kullanicinin sorusu: "geri almayi da AI yapamaz mi, niye kullaniciya
    # zorla yaptiriyor?" OLCULDU (LOG/2026-08-20_baa70fa4.txt): model iki kez
    # "Ctrl+Z ile geri don" dedi, birincisinde oturum 13 dakika 21 saniye
    # durdu; ikincisinde model "geri alindigini VARSAYIP" kod uretti.
    # Ucuncusu asil sorun — hiz degil, DOGRULUK.
    #
    # Sinir: yalnizca KENDI islemi. Yiginin tepesinde "AI: " onekli bir kayit
    # yoksa host reddediyor ve modele soyluyor.
    " "
    "UNDOING YOUR OWN WORK: if a step you just made turned out wrong, you can "
    "undo it yourself — put GERI-AL on its own line at the end of your reply "
    "and the host undoes the last change. Do NOT tell the user to press "
    "Ctrl+Z; that is your job now. "
    "You may only undo YOUR OWN changes: the host checks that the top of the "
    "undo stack is an `AI: ...` entry (you can see it as `undo_stack=` in the "
    "document context) and refuses otherwise, telling you why. "
    "If it refuses, NEVER assume the undo happened — the document is still in "
    "the old state and code written for the new state will do damage. "
    "One undo per reply. You may put a corrected code block in the same "
    "reply: the undo runs first, then the user runs your code. "
    # OLCUM (caddy_gelisim.txt, kayip 5): gorsel kontrol turlarin %30'unda
    # isteniyor ve degeri GERCEK — model kendi hatasini yakaliyor. Bu yuzden
    # kontrolun KENDISI kisilmadi; kisilan sey onay turunun maliyeti.
    # Cozunurluk dusurme fikri REDDEDILDI: modelin yakaladigi sey zaten ince
    # kusur, resmi kucultmek kontrolu ise yaramaz hale getirir.
    "When the numbers come back and the step is right, say so in ONE short "
    "line and stop — do not restate the plan, do not re-emit the code that "
    "already ran. Spend words only when something is actually wrong: then say "
    "what is wrong and fix it. "
    # Kisalik kalsin ama onay KAPSAMI daralsin: olculdu, modelin iki yanlis
    # cumlesi de tam olarak bu bicimde, tek cumlelik onay olarak geldi.
    "That one line may only claim what you actually measured, and it must "
    "quote the number. 'çakışma yok' without a `check_overlap` line behind "
    "it is a guess, and so is any claim about clearance or contact."
    # --- BASKIYA HAZIR CIKTI ----------------------------------------------
    # OLCULDU: FreeCAD'in kendi 3.11'i hepsini yerli yapiyor - STL/3MF/OBJ/PLY
    # 0.02-0.15 sn, STEP 0.06 sn, MeshPart ile sapma ayarli mesh 0.03 sn, ve
    # manifold kontrolu bile var (isSolid / hasNonManifolds /
    # hasSelfIntersections). cp312 venv'ine subprocess GEREKMIYOR.
    #
    # Yani bu bir "ozellik" degil, zaten yazilabilen kod. Eksik olan tek sey
    # modelin bunu ONERMESIYDI. Kullanicinin istegi: "en sonda bittiginde
    # sorsun" - bu yuzden kural "is bitince sor", "her seferinde uret" degil.
    " "
    "FINISHED OUTPUT — THE FORMAT FOLLOWS THE PURPOSE: when the model looks "
    "finished — the user says it is done, or accepts the last step and asks "
    "for nothing further — offer to export it, in one short question naming "
    "the format that fits the purpose they chose. Do not export without "
    "being asked, and do not offer it after every step. "
    "(a) 3D print: .3mf and .stl (the usual pair), plus a quality — draft / "
    "normal / fine. "
    "(b) CNC, (d) mould, (e) FEA or handoff to another CAD: .step — a MESH "
    "IS THE WRONG ANSWER here and cannot be un-faceted afterwards; never "
    "hand a CNC shop an STL when a solid exists. "
    "(c) sheet/laser: a flat .dxf of the outline, plus the bend lines and "
    "thickness stated in text. "
    "(f) visual only: .obj or .stl is fine, quality is a look question, not "
    "a manufacturing one. "
    "Export with FreeCAD's own modules, no external tools: mesh formats via "
    "MeshPart.meshFromShape(Shape=..., LinearDeflection=D, "
    "AngularDeflection=0.2) where D is 0.5 for draft, 0.1 for normal, 0.05 "
    "for fine, then Mesh.export([...], path) — .stl .3mf .obj .ply .amf .off "
    "all work (measured). Solid formats via Part.export — .step .iges .brep "
    "(measured; .dxf is NOT supported there, use "
    "`import importDXF; importDXF.export([obj], path)` for that). "
    # OLCULDU (bu makinede, freecadcmd 1.1.3): FreeCAD'in kendi
    # Preferences/Mod/Import/hSTEP "Scheme" parametresini AP242DIS'e
    # ayarlamak Part.export'u da Import.export'u da DEGISTIRMEDI — dosya
    # yine AP214 cikti (FILE_SCHEMA AUTOMOTIVE_DESIGN ... 214). Calisan tek
    # yol pythonocc'un Interface_Static'i; onunla dosya gercekten
    # AP242_MANAGED_MODEL_BASED_3D_ENGINEERING olarak yazildi.
    "STEP DETAIL: plain Part.export writes an AP214 file. AP214 is a fine "
    "fallback and most shops read it, but AP242 is the current ISO standard "
    "and the one to send for a CNC quote. To actually get AP242 (measured — "
    "setting FreeCAD's own STEP preference does NOT change the output): "
    "`from OCC.Core.Interface import Interface_Static; "
    "Interface_Static.SetCVal('write.step.schema', 'AP242DIS')` before "
    "Part.export, then print the FILE_SCHEMA line of the written file to "
    "prove which one you produced. "
    "Before writing any MESH file, CHECK IT AND REPORT THE RESULT: "
    "isSolid(), hasNonManifolds(), hasSelfIntersections(). A mesh that fails "
    "these will print wrong; say so plainly instead of exporting silently. "
    "For (f) visual-only those same failures usually do not matter — say so "
    "rather than blocking the export. "
    "Ask the user where to save if you do not already know."
    # --- DOGRULAMA RAPORU ------------------------------------------------
    # Kod calistiktan sonra host deterministik bir geometri kontrolu kosuyor
    # (caddy/execution/dogrulama.py) ve sonucu bir sonraki tura baglam olarak
    # yolluyor. Rapor KOSAN kontrolleri kosmayanlardan ayiriyor; modelin bu
    # ayrimi ezmemesi lazim, yoksa gormedigi bir kontrolu gecmis sayip
    # "dogrulandi" diyor. Fikir earthtojake/text-to-cad'den
    # (inspection-and-validation.md), MANTIK 17.
    " "
    "VERIFICATION REPORT: after your code runs, the host reports a "
    "`verification:` block listing which deterministic geometry checks actually "
    "ran, which did NOT run and why, and any findings. Read it before your "
    "next reply. Two rules about it. "
    "(a) Claim only what the report supports. A check listed under NOT RUN "
    "did not run — do not describe it as passed, and do not say the model is "
    "verified, watertight, printable, strong enough, in tolerance or "
    "manufacturable unless a check that actually ran says so. If you want a "
    "check that did not run, write the code for it. "
    "(b) A finding is a real defect, not noise. 'reversed solid' (negative "
    "volume) and 'open shell' both pass isValid() and both break later "
    "booleans and printing — fix them in the step that caused them, not "
    "twenty steps later. Say plainly what broke and why. "
    # OLCULDU (LOG/2026-08-26_a0bb49dd.txt): 43 bulgunun 31'i ayni satirdi
    # ("acik kabuk"), hepsi de BILEREK yuzey olan yelken ve kupeste icindi
    # ve kullanici basmayacagini zaten soylemisti. Kural: bulgunun anlami
    # AMACA bagli, ve tekrar eden bulgu tekrar tekrar yazilmaz.
    "(c) Read the findings THROUGH THE PURPOSE. 'open shell' on an object "
    "that is deliberately a surface — a sail, a railing, a decorative shell "
    "in a visual-only job — is not a defect and must not be reported as one; "
    "measured, one session produced 31 such false alarms in a job the user "
    "had already said would never be printed. It IS a defect when the object "
    "has to become a solid, be booleaned, or be printed. Decide which case "
    "you are in, say it in half a line, and move on. Never repeat the same "
    "finding for many objects one by one: say 'N objects: open shell — "
    "all deliberate surfaces' once."
    " "
    "LANGUAGE OF CODE: write object Names, Labels, block titles, variable "
    "names and print() text in English, whatever language you reply in. "
    "The document outlives the chat and is read by people who did not see it."
)


@dataclass
class TurSonucu:
    oturum: str = ""
    hata_mi: bool = False
    metin: str = ""
    model: str = ""               # gercekte hangi model cevapladi
    sure_ms: int = 0
    aciklama: str = ""            # hata varsa insanin okuyacagi sebep
    ham: dict = field(default_factory=dict)

    # CLI her yanitta total_cost_usd donduruyor. DIKKAT: bu, isin API
    # fiyatlariyla yapilsaydi TUTACAGI karsiliktir. Abonelikle (OAuth)
    # calisirken boyle bir tahsilat YOKTUR. Panelde dolar basmak kullaniciyi
    # "para harciyorum" diye yaniltti; artik yerine TOKEN gosteriliyor,
    # dolar karsiligi yalnizca ipucu balonunda kaldi.
    maliyet_usd: float = 0.0

    # Token dokumu (result.usage'dan). Dorde ayirmak lazim cunku bunlar ayni
    # sey degil: onbellekten OKUNAN token cok ucuz, onbellege YAZILAN pahali.
    tk_girdi: int = 0
    tk_cikti: int = 0
    tk_onbellek_okuma: int = 0
    tk_onbellek_yazma: int = 0

    @property
    def tk_toplam(self) -> int:
        return (self.tk_girdi + self.tk_cikti
                + self.tk_onbellek_okuma + self.tk_onbellek_yazma)

    # Bu turda kac API cagrisi yapildi (`message_start` olayi sayisi) ve SON
    # cagrinin istem boyu. Ikisi de baglam sayacinin dogru olmasi icin var.
    api_cagrisi: int = 0
    tk_son_istem: int = 0

    @property
    def tk_baglam(self) -> int:
        """Bu turda modele GONDERILEN baglam (context penceresi doluluğu).

        Ciktiyi disarida birakir: cikti context'e degil, cevaba gider.
        Sohbet uzadikca bu sayi buyur - gercek bir seansta 7.3k'dan 57.9k'ya
        ciktigi olculdu (LOG/2026-08-19_dcd21af7.txt).

        DIKKAT — HARCAMA ILE BAGLAM AYNI SEY DEGIL. `result.usage` TURUN
        TAMAMINI toplar; bir tur birden fazla API cagrisi yaparsa ayni baglam
        iki kez sayilir. Olculdu (LOG/2026-08-21_df4ac3ea.txt): baglam
        86953 -> 179116 -> 92600 diye sicradi, yani bir tur ~2 kat gosterdi
        ve panelde kullaniciya bu sayi yaziyordu.

        Dogrusu SON `message_start`in istem boyu: baglam penceresi tek bir
        istegin boyudur, turun toplami degil. O deger yoksa (eski CLI, eksik
        alan) toplama geri duseriz — yanlis ama HIC sayi olmamasindan iyi.
        """
        if self.tk_son_istem > 0:
            return self.tk_son_istem
        return self.tk_girdi + self.tk_onbellek_okuma + self.tk_onbellek_yazma


class ClaudeTransport(QtCore.QObject):
    """Ortak arayuz - M6'da kalici surecli surum bunu ayni sinyallerle uygular."""

    tur_basladi = QtCore.Signal()
    asama = QtCore.Signal(str)              # baglaniyor | dusunuyor | yaziyor
    dusunce_parcasi = QtCore.Signal(str)    # varsa modelin dusunme metni
    dusunce_olcusu = QtCore.Signal(int)     # tahmini dusunme tokeni (kumulatif)
    metin_parcasi = QtCore.Signal(str)      # yanit metni, akarken
    limit_bilgisi = QtCore.Signal(str)      # kullanim penceresi durumu
    tur_bitti = QtCore.Signal(object)       # TurSonucu
    durum_degisti = QtCore.Signal(str)      # bosta | calisiyor | oluyor

    def tur_gonder(self, istem: str) -> None:
        raise NotImplementedError

    def iptal(self) -> None:
        raise NotImplementedError

    def mesgul_mu(self) -> bool:
        raise NotImplementedError

    def ayarlar_degisti(self) -> bool:
        """Surec argumanlarini etkileyen bir ayar degisti. Doner: uygulandi_mi."""
        return True


class KaliciTransport(ClaudeTransport):
    """Tek bir claude.exe surecini turlar boyunca AYAKTA TUTAR.

    Surec ilk turda baslar ve stdin acik kalir; sonraki turlar ayni surece
    bir satir daha yazar. Olculdu: tur 1 = 8.5 sn, tur 2 = 2.4 sn.

    Surec olurse (cokme, iptal, zaman asimi) sonraki tur onu yeniden baslatir
    ve `--resume <oturum>` ile sohbeti kaldigi yerden surdurur - kullanici
    baglam kaybetmez.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._oturum = str(uuid.uuid4())
        self._ilk_tur = True
        self._proc = ClaudeProcess(self)
        self._mesgul = False

        self._sonuc_nesnesi: dict | None = None
        self._metin_parcalari: list[str] = []
        self._model = ""
        self._son_satirlar: list[str] = []   # hata ayiklama icin son N satir
        self._zaman_asti = False
        self._api_cagrisi = 0
        self._tk_son_istem = 0
        self._yeniden_baslat_gerek = False

        self._proc.satir.connect(self._satir_geldi)
        self._proc.bitti.connect(self._bitti)

        # SESSIZLIK saati. Her stdout satirinda sifirlanir, yani "toplam sure"
        # degil "en son ne zaman ses cikardi" olculur. Toplam sureye bakan bir
        # saat, uzun dusunen ama saglikli calisan bir turu keserdi.
        self._saat = QtCore.QTimer(self)
        self._saat.setSingleShot(True)
        self._saat.timeout.connect(self._zaman_asimi)

    # -- genel -------------------------------------------------------------

    def mesgul_mu(self) -> bool:
        return self._mesgul

    def ayarlar_degisti(self) -> bool:
        """Model ya da efor degisti: bostaki sureci oldur. Doner: uygulandi_mi.

        NEDEN GEREKLI. `--model` ve `--effort` surec BASLARKEN veriliyor,
        surec ise turlar boyunca ayakta kaliyor (sinifin butun varlik
        sebebi bu: tur 1 = 8.5 sn, tur 2 = 2.4 sn). Yani oturum ortasinda
        model degistirmek ESKIDEN HICBIR SEY YAPMIYORDU — kutunun ipucu
        "sonraki mesajdan itibaren gecerli" diyordu ve bu dogru degildi.

        Oldurmek guvenli ve BAGLAM KAYBETTIRMEZ: bostaki surec olunce
        sonraki tur `--resume <oturum>` ile yenisini baslatiyor (bkz.
        `_bitti`). Odenen tek bedel yeniden acilis (~6 sn).

        Tur ORTASINDA dokunmuyoruz: akan bir yaniti kesmek, ayarin bir tur
        gec uygulanmasindan pahali. O durumda False donuyor ve cagiran
        kullaniciya dogruyu soyluyor.
        """
        if self._mesgul:
            # Unutmuyoruz: tur bitince oldurulecek (bkz. _turu_bitir).
            # Yoksa ayar kaydedilir ama HIC uygulanmazdi — duzeltmeye
            # calistigimiz hatanin aynisi, bir adim ileride.
            self._yeniden_baslat_gerek = True
            return False
        if self._proc.calisiyor_mu():
            self._proc.oldur()
        return True

    @property
    def oturum(self) -> str:
        return self._oturum

    def yeni_oturum(self) -> None:
        """Sohbeti sifirlar - sonraki tur temiz bir baglamla baslar."""
        self._oturum = str(uuid.uuid4())
        self._ilk_tur = True
        # Eski surec eski oturumu tasiyor; kapat ki sonraki tur temiz bassin.
        self._proc.oldur()

    def oturumu_surdur(self, oturum: str) -> None:
        """Eski bir oturuma baglanir - sonraki tur `--resume <oturum>` olur.

        Bagam kaybi olmamasinin sebebi: gecmisi biz tasimiyoruz, CLI kendi
        oturum dosyasindan yukluyor. Yani kalan tek is dogru kimligi
        vermek ve bostaki sureci oldurmek - o surec ESKI oturumu tasiyor.

        `_ilk_tur = False` kritik: True kalsaydi argumana `--session-id`
        girer ve CLI "bu kimlik zaten var" diye reddederdi.
        """
        if not oturum:
            return
        self._oturum = oturum
        self._ilk_tur = False
        self._proc.oldur()

    def kapat(self) -> None:
        """FreeCAD kapanirken cagrilir - artik surec birakmayalim."""
        self._proc.oldur()

    def tur_gonder(self, istem: str,
                   gorsel: "bytes | list[bytes] | None" = None) -> None:
        """`gorsel` verilirse PNG bayti base64 `image` blogu olarak eklenir.

        Liste verilirse her kare ayri bir `image` blogu olur — cok acili
        gorsel kontrol boyle gidiyor, resimleri birlestirmeye gerek yok.

        Modelin dosya erisimi yok (`--tools ""`), yani ekran goruntusunu
        okuyamaz - resmi ona ulastirmanin tek yolu icerik blogu. OLCULDU:
        boyle gonderilen bir test resmini model dogru tarif etti.
        """
        if self._mesgul:
            raise RuntimeError("onceki tur hala calisiyor")

        self._sonuc_nesnesi = None
        self._metin_parcalari = []
        self._model = ""
        self._son_satirlar = []
        self._zaman_asti = False
        self._api_cagrisi = 0
        self._tk_son_istem = 0
        self._mesgul = True

        self.durum_degisti.emit("calisiyor")
        self.tur_basladi.emit()

        # SUREC ZATEN AYAKTAYSA yeniden baslatmiyoruz - kullanicinin sorusu
        # tam da buydu ("her mesajda baglanmak gerekli mi"). Acilis maliyeti
        # yalnizca ilk turda odenir.
        try:
            if not self._proc.calisiyor_mu():
                self.asama.emit("baglaniyor")
                exe = locate.claude_exe()
                self._proc.baslat(str(exe), self._argv(),
                                  str(config.calisma_dizini()))
            else:
                self.asama.emit("istek gonderildi")

            # stdin ACIK KALIR. Istem komut satirindan degil stdin'den gidiyor:
            # belge baglami kilobaytlara ciktiginda Windows'un ~32k arguman
            # siniri ve tirnak kacisi sorun olur; stdin'in boyle bir siniri yok.
            icerik: list[dict] = []
            # Tek kare de olabilir, birden fazla aci da (bkz. gorunum.
            # yakala_cok). Resim(ler) METINDEN ONCE: model once neye
            # baktigini gorsun, sonra ne soruldugunu okusun.
            kareler = gorsel if isinstance(gorsel, (list, tuple)) else (
                [gorsel] if gorsel else [])
            for kare in kareler:
                icerik.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png",
                               "data": base64.b64encode(kare).decode("ascii")},
                })
            icerik.append({"type": "text", "text": istem})

            self._proc.girdi_yaz(json.dumps({
                "type": "user",
                "message": {"role": "user", "content": icerik},
            }, ensure_ascii=False) + "\n")
        except locate.BulunamadiHatasi as e:
            self._turu_iptal_et(str(e))
            return
        except Exception as e:
            self._turu_iptal_et(f"could not send request: {e}")
            return

        self._saat.start(config.zaman_asimi() * 1000)

    def _turu_iptal_et(self, aciklama: str) -> None:
        self._saat.stop()
        self._mesgul = False
        self.durum_degisti.emit("bosta")
        self.tur_bitti.emit(TurSonucu(hata_mi=True, aciklama=aciklama))

    def iptal(self) -> None:
        if not self._mesgul:
            return
        self.durum_degisti.emit("oluyor")
        self._saat.stop()
        # Kalici surecte iptal, sureci de oldurur - akan bir yaniti yarida
        # kesmenin baska yolu yok. Sonraki tur --resume ile devam eder.
        self._proc.oldur()

    # -- argumanlar --------------------------------------------------------

    def _argv(self) -> list[str]:
        a = [
            "-p",
            # GIRDI de stream-json: stdin acik kalir ve her tur bir satir
            # yazilir. Kalici surecin ve (ileride) gorsel gondermenin sarti.
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            # --verbose, -p ile stream-json kullanildiginda ZORUNLU;
            # olmadan CLI komutu reddediyor.
            "--verbose",
            "--include-partial-messages",
            "--model", config.model(),
            # AI'in KENDI dosya erisimi yok. Bu, herhangi bir AST taramasindan
            # daha guclu bir garanti: diske dokunan tek sey, kullanicinin
            # panelde Calistir'a bastigi koddur.
            "--tools", "",
            "--permission-mode", "dontAsk",
            "--append-system-prompt", SISTEM_SOZLESMESI,
        ]
        # DUSUNME MIKTARI. Gecikmenin %91-94'u dusunme (olculdu, bkz.
        # config.EFORLAR). Bos dize = bayrak hic gecilmez, CLI kendi
        # varsayilanini kullanir — bu GECERLI bir secim, eksik ayar degil.
        efor = config.efor()
        if efor:
            a += ["--effort", efor]

        if self._ilk_tur:
            a += ["--session-id", self._oturum]
        else:
            a += ["--resume", self._oturum]

        butce = config.butce_usd()
        if butce and butce > 0:
            a += ["--max-budget-usd", str(butce)]
        return a

    # -- akis ayristirma ---------------------------------------------------

    def _satir_geldi(self, s: str) -> None:
        # Ses cikti -> sessizlik saatini bastan kur.
        if self._mesgul:
            self._saat.start(config.zaman_asimi() * 1000)
        self._son_satirlar = (self._son_satirlar + [s])[-40:]
        try:
            m = json.loads(s)
        except Exception:
            return                      # gurultu satiri; akisi bozma
        if not isinstance(m, dict):
            return

        tip = m.get("type")

        if tip == "result":
            # KALICI SURECTE TURU BITIREN SEY BUDUR, surecin olumu degil.
            # Tek atislik surumde tur `_bitti`de kapaniyordu; surec artik
            # ayakta kaldigi icin oyle bir sinyal gelmiyor.
            self._sonuc_nesnesi = m
            self._turu_bitir(m)
        elif tip == "system":
            alt = m.get("subtype")
            if alt == "init" and m.get("session_id"):
                self._oturum = m["session_id"]
            elif alt == "thinking_tokens":
                # NABIZ. Model dusundugu surece gelir; panelin "hala
                # calisiyorum" diyebilmesinin tek dayanagi.
                try:
                    self.dusunce_olcusu.emit(int(m.get("estimated_tokens") or 0))
                except Exception:
                    pass
                self.asama.emit("dusunuyor")
            elif alt == "status" and m.get("status") == "requesting":
                self.asama.emit("istek gonderildi")
        elif tip == "stream_event":
            self._olay(m.get("event") or {})
        elif tip == "rate_limit_event":
            self._limit(m.get("rate_limit_info") or {})
        # Bilinmeyen tipler BILEREK yok sayiliyor: CLI yeni tip ekleyebiliyor
        # (rate_limit_event boyle ortaya cikti) ve panel bundan olmemeli.

    def _olay(self, ev: dict) -> None:
        et = ev.get("type")

        if et == "message_start":
            msj = ev.get("message") or {}
            self._model = msj.get("model") or self._model
            # BAGLAM SAYACININ KAYNAGI. Bir tur birden fazla API cagrisi
            # yapabiliyor; `result.usage` hepsini toplayip baglami iki kat
            # gosteriyordu (bkz. TurSonucu.tk_baglam). Tek bir istegin boyu
            # burada, ve son cagri sohbetin o anki gercek boyudur.
            self._api_cagrisi += 1
            kul = msj.get("usage") or {}

            def _t(ad: str) -> int:
                try:
                    return int(kul.get(ad) or 0)
                except Exception:
                    return 0

            istem = (_t("input_tokens") + _t("cache_read_input_tokens")
                     + _t("cache_creation_input_tokens"))
            if istem:
                self._tk_son_istem = istem

        elif et == "content_block_start":
            tur = ((ev.get("content_block") or {}).get("type"))
            self.asama.emit("dusunuyor" if tur == "thinking" else "yaziyor")

        elif et == "content_block_delta":
            d = ev.get("delta") or {}
            dt = d.get("type")
            if dt == "text_delta":
                parca = d.get("text") or ""
                if parca:
                    self._metin_parcalari.append(parca)
                    self.metin_parcasi.emit(parca)
            elif dt == "thinking_delta":
                # Cogu zaman bos gelir (dusunme metni acikta degil); dolu
                # geldiginde kullaniciya gostermek istiyoruz.
                parca = d.get("thinking") or ""
                if parca:
                    self.dusunce_parcasi.emit(parca)
            # signature_delta: kriptografik imza, gosterilecek bir sey degil

    def _limit(self, bilgi: dict) -> None:
        durum = bilgi.get("status")
        if durum and durum != "allowed":
            self.limit_bilgisi.emit(f"kullanim limiti: {durum}")
        elif bilgi.get("isUsingOverage"):
            self.limit_bilgisi.emit("kullanim limiti asildi (overage)")

    # -- bitis -------------------------------------------------------------

    def _zaman_asimi(self) -> None:
        sn = config.zaman_asimi()
        log.uyari(f"{sn} sn boyunca hic cikti gelmedi, surec kapatiliyor")
        # Ayri bayrak sart: oldur() "kasitli oldurme" isaretini kaldiriyor ve
        # onsuz bu, kullanicinin Iptal'e basmasindan ayirt edilemiyor —
        # gunluge "iptal edildi" diye yaziliyordu, sebep gorunmuyordu.
        self._zaman_asti = True
        self._proc.oldur()

    def _bitti(self, kod: int, stderr_kuyruk: str) -> None:
        """Surec OLDU. Kalici modda bu normalde tur disinda olur."""
        self._saat.stop()

        if not self._mesgul:
            # Bosta olen surec sorun degil: sonraki tur --resume ile
            # yenisini baslatir ve sohbet kaldigi yerden devam eder.
            if kod != 0:
                log.uyari(f"claude sureci bosta kapandi (kod {kod})")
            return

        # Tur ORTASINDA oldu: iptal, zaman asimi ya da cokme.
        self._mesgul = False
        self.durum_degisti.emit("bosta")

        if self._zaman_asti:
            self.tur_bitti.emit(TurSonucu(
                hata_mi=True,
                aciklama=f"No output from claude for {config.zaman_asimi()} s; "
                         f"the process was closed. (This is not long "
                         f"thinking — it sends a heartbeat every second "
                         f"while thinking. Likely a network or process issue.)"))
            return

        if self._proc.kasitli_olduruldu_mu():
            self.tur_bitti.emit(TurSonucu(hata_mi=True, aciklama="cancelled"))
            return

        kuyruk = (stderr_kuyruk or "").strip()
        aciklama = f"the claude process exited unexpectedly (code {kod})"
        if kuyruk:
            aciklama += f"\n{kuyruk[-1500:]}"
        elif self._son_satirlar:
            aciklama += "\nlast lines:\n" + "\n".join(self._son_satirlar[-5:])
        self.tur_bitti.emit(TurSonucu(hata_mi=True, aciklama=aciklama))

    def _turu_bitir(self, nesne: dict) -> None:
        """`result` satiri geldi - tur bitti, SUREC AYAKTA KALIYOR."""
        self._saat.stop()
        self._mesgul = False
        self.durum_degisti.emit("bosta")

        # Ilk basarili turdan sonra, surec olurse --resume kullanilir.
        self._oturum = nesne.get("session_id") or self._oturum
        self._ilk_tur = False

        # Tur ortasinda model/efor degistirilmisti: SIMDI uygula. Erteledigimiz
        # sey unutulmus olsaydi ayar kaydedilip hic gecerli olmazdi.
        if self._yeniden_baslat_gerek:
            self._yeniden_baslat_gerek = False
            if self._proc.calisiyor_mu():
                self._proc.oldur()

        hata_mi = bool(nesne.get("is_error", False))

        # Metin: sonuc satirindaki tam metin asildir; akan parcalar yalnizca
        # gosterim icindi. Sonuc bos gelirse parcalara duseriz.
        metin = str(nesne.get("result", "") or "") or "".join(self._metin_parcalari)

        # message_start'taki model ASIL CEVAPLAYAN modeldir. modelUsage ise
        # CLI'in kendi ic islerinde kullandigi yardimci modelleri de icerir
        # (ornegin baslik uretimi icin haiku) - onlari da yazinca panelde
        # "claude-haiku-4-5, claude-opus-5" gibi kafa karistirici bir satir
        # cikiyordu. Once message_start'i kullaniyoruz.
        model_adi = self._model
        if not model_adi:
            kullanim = nesne.get("modelUsage") or {}
            if isinstance(kullanim, dict) and kullanim:
                # En cok cikti ureten model asil cevaplayandir.
                model_adi = max(
                    kullanim.items(),
                    key=lambda kv: (kv[1] or {}).get("outputTokens", 0))[0]

        kul = nesne.get("usage") or {}

        def _t(ad: str) -> int:
            try:
                return int(kul.get(ad, 0) or 0)
            except Exception:
                return 0

        self.tur_bitti.emit(TurSonucu(
            oturum=self._oturum,
            hata_mi=hata_mi,
            metin=metin,
            model=model_adi,
            maliyet_usd=float(nesne.get("total_cost_usd", 0.0) or 0.0),
            tk_girdi=_t("input_tokens"),
            tk_cikti=_t("output_tokens"),
            tk_onbellek_okuma=_t("cache_read_input_tokens"),
            tk_onbellek_yazma=_t("cache_creation_input_tokens"),
            api_cagrisi=self._api_cagrisi,
            tk_son_istem=self._tk_son_istem,
            sure_ms=int(nesne.get("duration_ms", 0) or 0),
            aciklama=("" if not hata_mi else (metin or "bilinmeyen hata")),
            ham=nesne,
        ))
