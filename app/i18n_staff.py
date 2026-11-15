"""Staff-facing text localisation (Finnish first, Swedish, English). Server-built strings are English underneath (the canonical
text the rules and reports use); loc() translates them at the API boundary using exact matches and patterns.
Finnish and Swedish are first drafts and need review by a Finnish- and Swedish-speaking clinician."""
import contextvars
import re

LANG = contextvars.ContextVar("lang", default="en")

EXACT = {
    # cancers
    "Lung": ("Keuhkosyöpä", "Lungcancer"), "Breast": ("Rintasyöpä", "Bröstcancer"), "Colorectal": ("Suolistosyöpä", "Tarmcancer"),
    "Prostate": ("Eturauhassyöpä", "Prostatacancer"), "Haematological": ("Hematologinen syöpä", "Hematologisk cancer"),
    "lung": ("keuhkosyöpä", "lungcancer"), "breast": ("rintasyöpä", "bröstcancer"), "colorectal": ("suolistosyöpä", "tarmcancer"),
    "prostate": ("eturauhassyöpä", "prostatacancer"), "haematological": ("hematologinen syöpä", "hematologisk cancer"),
    # languages
    "Finnish": ("suomi", "finska"), "Swedish": ("ruotsi", "svenska"), "Arabic": ("arabia", "arabiska"), "Somali": ("somali", "somaliska"),
    "Russian": ("venäjä", "ryska"), "English": ("englanti", "engelska"),
    # steps
    "Suspicion": ("Epäily", "Misstanke"), "Referral sent": ("Lähete lähetetty", "Remiss skickad"), "Referral received": ("Lähete vastaanotettu", "Remiss mottagen"),
    "First test": ("Ensimmäinen tutkimus", "Första undersökning"), "Diagnosis": ("Diagnoosi", "Diagnos"), "MDT": ("Moniammatillinen kokous", "Multidisciplinär konferens"),
    "Treatment": ("Hoito", "Behandling"), "CT scan": ("TT-kuvaus", "Datortomografi"), "Recall imaging": ("Uusintakuvaus", "Ny bildtagning"),
    "Colonoscopy": ("Kolonoskopia", "Koloskopi"), "MRI": ("MRI-kuvaus", "MR-undersökning"), "SPEP + FLC blood test": ("SPEP- ja FLC-verikoe", "SPEP- och FLC-blodprov"),
    # red flags
    "Cough over 3 weeks": ("Yli 3 viikkoa kestänyt yskä", "Hosta i över 3 veckor"), "Coughing blood": ("Veriyskä", "Blodhosta"), "Weight loss": ("Painonlasku", "Viktnedgång"),
    "Nodule on X-ray or CT": ("Kyhmy keuhkokuvassa tai TT:ssä", "Knöl på röntgen eller DT"), "Breast lump": ("Kyhmy rinnassa", "Knöl i bröstet"),
    "Abnormal mammogram": ("Poikkeava mammografia", "Avvikande mammografi"), "Positive FIT": ("Positiivinen FIT", "Positivt FIT"),
    "Rectal bleeding": ("Verenvuoto peräsuolesta", "Blödning från ändtarmen"), "Change in bowel habit": ("Muutos suolen toiminnassa", "Förändrade tarmvanor"),
    "Raised PSA": ("Kohonnut PSA", "Förhöjt PSA"), "Urinary symptoms": ("Virtsaamisoireet", "Urinvägsbesvär"),
    "Back or bone pain, 3rd visit": ("Selkä- tai luukipu, 3. käynti", "Rygg- eller skelettsmärta, 3:e besöket"),
    "Fatigue and infections": ("Väsymys ja toistuvat infektiot", "Trötthet och infektioner"), "Abnormal blood count": ("Poikkeava verenkuva", "Avvikande blodstatus"),
    # loop reasons
    "Nodule or red flag, no CT booked": ("Kyhmy tai varoitusmerkki, TT-aikaa ei varattu", "Knöl eller varningstecken, ingen DT bokad"),
    "Abnormal screen, no assessment booked": ("Poikkeava seulonta, jatkotutkimusta ei varattu", "Avvikande screening, ingen utredning bokad"),
    "Positive FIT, no colonoscopy booked": ("Positiivinen FIT, kolonoskopiaa ei varattu", "Positivt FIT, ingen koloskopi bokad"),
    "Raised PSA, no MRI booked": ("Kohonnut PSA, MRI:tä ei varattu", "Förhöjt PSA, ingen MR bokad"),
    "3rd contact, no SPEP + FLC booked": ("3. yhteydenotto, SPEP- ja FLC-koetta ei varattu", "3:e kontakten, ingen SPEP + FLC bokad"),
    "CT done, no biopsy booked": ("TT tehty, koepalaa ei varattu", "DT gjord, ingen biopsi bokad"),
    "Imaging done, no biopsy booked": ("Kuvaus tehty, koepalaa ei varattu", "Bildtagning gjord, ingen biopsi bokad"),
    "Colonoscopy done, no biopsy result booked": ("Kolonoskopia tehty, tulosten käyntiä ei varattu", "Koloskopi gjord, inget besök för resultat bokat"),
    "MRI done, no biopsy booked": ("MRI tehty, koepalaa ei varattu", "MR gjord, ingen biopsi bokad"),
    "Blood test done, no haematology visit booked": ("Verikoe tehty, hematologin käyntiä ei varattu", "Blodprov taget, inget hematologbesök bokat"),
    "Diagnosis made, no MDT booked": ("Diagnoosi tehty, moniammatillista kokousta ei varattu", "Diagnos ställd, ingen konferens bokad"),
    "MDT done, no treatment booked": ("Kokous pidetty, hoitoa ei varattu", "Konferens hållen, ingen behandling bokad"),
    "Nodule, no CT booked": ("Kyhmy, TT-aikaa ei varattu", "Knöl, ingen DT bokad"),
    "3rd contact with back pain, no SPEP + FLC booked": ("3. yhteydenotto selkäkivun vuoksi, SPEP- ja FLC-koetta ei varattu", "3:e kontakten med ryggsmärta, ingen SPEP + FLC bokad"),
    "Date slipped": ("Aika siirtyi", "Tiden flyttades"),
    "Suspicious finding in a report, no next step stated": ("Epäilyttävä löydös lausunnossa, jatkotoimia ei mainittu", "Misstänkt fynd i svaret, inget nästa steg angivet"),
    "On track": ("Aikataulussa", "I tid"),
    # alerts
    "Could not reach the nurse within 1 working day: call": ("Ei tavoittanut hoitajaa yhdessä arkipäivässä: soita", "Nådde inte sjuksköterskan inom 1 vardag: ring"),
    "Does not know what happens next: call": ("Ei tiedä mitä seuraavaksi tapahtuu: soita", "Vet inte vad som händer härnäst: ring"),
    "Frail (G8 14 or lower)": ("Hauras (G8 enintään 14)", "Skör (G8 14 eller lägre)"), "Interpreter needed": ("Tulkki tarvitaan", "Tolk behövs"),
    # board
    "Add colonoscopy slots for positive FITs": ("Lisää kolonoskopia-aikoja positiivisille FIT-tuloksille", "Fler koloskopitider för positiva FIT"),
    "Add CT slots for suspected lung cancer": ("Lisää TT-aikoja keuhkosyöpäepäilyihin", "Fler DT-tider vid misstänkt lungcancer"),
    "Open a vague-symptoms lane for blood cancers (3rd-contact rule)": ("Avaa epämääräisten oireiden väylä verisyöville (3. yhteydenoton sääntö)", "Öppna ett spår för vaga symtom vid blodcancer (3:e kontakten)"),
    "Book MRI and biopsy as one sequence": ("Varaa MRI ja koepala yhtenä ketjuna", "Boka MR och biopsi som en kedja"),
    "Book biopsy with the test result, not after it": ("Varaa koepala tutkimustuloksen yhteydessä, ei sen jälkeen", "Boka biopsi tillsammans med provsvaret, inte efteråt"),
    "Book the assessment visit when a screen is abnormal": ("Varaa jatkotutkimus heti kun seulonta on poikkeava", "Boka utredningen direkt när screeningen avviker"),
    "Give patients a named person to call when a date moves": ("Anna potilaalle nimetty henkilö, jolle soittaa kun aika siirtyy", "Ge patienten en namngiven person att ringa när en tid flyttas"),
    "Name an owner for every handover between steps": ("Nimeä vastuuhenkilö jokaiselle vaiheiden väliselle siirrolle", "Namnge en ansvarig för varje överlämning mellan stegen"),
    "Keep the safety-net rule on": ("Pidä turvaverkkosääntö käytössä", "Behåll skyddsnätsregeln"), "No open loops right now.": ("Ei avoimia silmukoita juuri nyt.", "Inga öppna luckor just nu."),
    "Keep watching the language gap": ("Seuraa kielieroa edelleen", "Fortsätt följa språkskillnaden"),
    "Danish fast-track pathways shortened the diagnostic interval (see source).": ("Tanskan pikapolut lyhensivät diagnostista väliä (ks. lähde).", "Danmarks snabbspår förkortade det diagnostiska intervallet (se källa)."),
    "Collect more pathways before deciding on referral criteria": ("Kerää lisää hoitopolkuja ennen lähetekriteerien päättämistä", "Samla fler vårdförlopp innan remisskriterier beslutas"),
    "Not enough completed pathways in this view.": ("Tässä näkymässä ei ole riittävästi valmistuneita hoitopolkuja.", "Inte tillräckligt många avslutade vårdförlopp i denna vy."),
    "Projected with this county's median step times; open loops add a chase delay.": ("Ennuste perustuu tämän alueen vaiheiden mediaaniaikoihin; avoimet silmukat lisäävät viivettä.", "Prognos med områdets mediantider per steg; öppna luckor ger en extra fördröjning."),
    # reports
    "Flagged as an open loop: the coordinator sees it in Today": ("Merkitty avoimeksi silmukaksi: koordinaattori näkee sen Tänään-näkymässä", "Markerad som öppen lucka: koordinatorn ser den i Idag"),
    "Diagnosis recorded (confirmed by a person)": ("Diagnoosi kirjattu (ihminen vahvisti)", "Diagnos registrerad (bekräftad av en person)"),
    "home test came back positive": ("kotitesti oli positiivinen", "hemtestet var positivt"),
    "blood when going to the toilet": ("verta WC:ssä käydessä", "blod vid toalettbesök"),
    "bowel habit changed for weeks": ("suolen toiminta muuttunut viikkojen ajan", "tarmvanorna har förändrats i flera veckor"),
    "cough that will not go away": ("yskä, joka ei mene ohi", "hosta som inte går över"),
    "coughed up blood": ("yskinyt verta", "har hostat blod"),
    "losing weight without trying": ("laihtunut tarkoituksettomasti", "går ner i vikt utan att försöka"),
    "spot seen on a chest X-ray": ("keuhkokuvassa nähty varjostuma", "skugga sedd på lungröntgen"),
    "found a lump": ("löytänyt kyhmyn", "har hittat en knöl"),
    "recalled after mammogram": ("kutsuttu jatkotutkimuksiin mammografian jälkeen", "kallad efter mammografi"),
    "PSA test was high": ("PSA-koe oli koholla", "PSA-provet var förhöjt"),
    "trouble passing urine": ("vaikeuksia virtsaamisessa", "svårt att kissa"),
    "back pain, has called before": ("selkäkipua, on soittanut aiemmin", "ryggsmärta, har ringt tidigare"),
    "tired and keeps getting infections": ("väsynyt ja saa jatkuvasti infektioita", "trött och får ständigt infektioner"),
    "blood test looked abnormal": ("verikoe oli poikkeava", "blodprovet var avvikande"),
    "same symptom": ("sama oire", "samma symtom"), "back pain": ("selkäkipu", "ryggsmärta"),
    "phone": ("puhelu", "telefon"), "eVisit": ("e-asiointi", "e-besök"),
    "Patient question: call": ("Potilaan kysymys: soita", "Patientens fråga: ring"),
    "Report logged on the pathway.": ("Lausunto kirjattu hoitopolkuun.", "Svaret registrerat i vårdförloppet."),
}

# (regex, finnish template, swedish template). {0},{1}.. are the captured groups; groups marked with ~ are localised first.
PATTERNS = [
    (r"^Patient question: (.+)$", "Potilaan kysymys: {0}", "Patientens fråga: {0}"),
    (r"^Open loop: (.+)$", "Avoin silmukka: {~0}", "Öppen lucka: {~0}"),
    (r"^New fast-track: first call within (\d+) days?$", "Uusi pikapolku: ensimmäinen soitto {0} päivän sisällä", "Ny snabbväg: första samtalet inom {0} dagar"),
    (r"^Worry (\d+) of 10: call today or the next working day$", "Huoli {0}/10: soita tänään tai seuraavana arkipäivänä", "Oro {0} av 10: ring i dag eller nästa vardag"),
    (r"^(\d+) of (\d+) days of the 6-week clock used, (\d+) steps left$", "{0}/{1} päivää 6 viikon kellosta käytetty, {2} vaihetta jäljellä", "{0} av {1} dagar av 6-veckorsklockan använda, {2} steg kvar"),
    (r"^(.+) done (\d+) days ago, next step due within (\d+)$", "{~0} tehty {1} pv sitten, seuraava vaihe {2} pv sisällä", "{~0} klar för {1} dagar sedan, nästa steg inom {2}"),
    (r"^(.+): many steps still ahead$", "{~0}: monta vaihetta vielä jäljellä", "{~0}: många steg återstår"),
    (r"^Needs (.+): language barrier$", "Tarvitsee kielen {~0}: kieliesteen vuoksi", "Behöver {~0}: språkbarriär"),
    (r"^(.+): slower pathway on average$", "{~0}: keskimäärin hitaampi hoitopolku", "{~0}: i genomsnitt långsammare vårdförlopp"),
    (r"^First test marked done: (.+)$", "Ensimmäinen tutkimus merkitty tehdyksi: {0}", "Första undersökningen markerad som gjord: {0}"),
    (r"^Closed the open loop: (.+)$", "Avoin silmukka suljettu: {~0}", "Öppen lucka stängd: {~0}"),
    (r"^Stage (.+) recorded$", "Levinneisyys {0} kirjattu", "Stadium {0} registrerat"),
    (r"^(\d+) people have an open loop; the most common is “(.+)” \((\d+)\)\.$", "{0} henkilöllä on avoin silmukka; yleisin on “{~1}” ({2}).", "{0} personer har en öppen lucka; vanligast är “{~1}” ({2})."),
    (r"^Interpreter by default for (.+) speakers$", "Tulkki oletuksena kielelle: {~0}", "Tolk som standard för {~0}talande"),
    (r"^(.+) speakers wait (.+) days longer to diagnosis than others with the same cancer(, (.+) of it before the referral)?\.$",
     "Kieli {~0}: diagnoosia odotetaan {1} päivää pidempään kuin muilla samassa syövässä{p}.", "{~0}talande väntar {1} dagar längre på diagnos än andra med samma cancer{p}."),
    (r"^Gaps above (\d+) days are flagged\.$", "Yli {0} päivän erot merkitään.", "Skillnader över {0} dagar markeras."),
    (r"^No language group is more than (\d+) days above the county median\.( Largest: (.+), (.+) days\.)?$",
     "Mikään kieliryhmä ei ylitä alueen mediaania yli {0} päivällä.{L}", "Ingen språkgrupp ligger mer än {0} dagar över områdets median.{L}"),
    (r"^Standard referral criteria and a coordinator at first contact: (.+)$", "Yhtenäiset lähetekriteerit ja koordinaattori ensikontaktissa: {~0}", "Enhetliga remisskriterier och koordinator vid första kontakten: {~0}"),
    (r"^(.+) waits (.+) days from first contact to referral arrival, the longest of the cancers shown\.$", "{~0}: {1} päivää ensikontaktista lähetteen saapumiseen, pisin esitetyistä syövistä.", "{~0}: {1} dagar från första kontakt till remissankomst, längst av de visade cancerformerna."),
]
_COMPILED = [(re.compile(p), fi, sv) for p, fi, sv in PATTERNS]


WEEKDAYS = {"Monday": ("maanantaina", "måndag"), "Tuesday": ("tiistaina", "tisdag"), "Wednesday": ("keskiviikkona", "onsdag"), "Thursday": ("torstaina", "torsdag"),
            "Friday": ("perjantaina", "fredag"), "Saturday": ("lauantaina", "lördag"), "Sunday": ("sunnuntaina", "söndag")}
_WD = re.compile(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) (\d\d:\d\d)$")


def loc(text, lang=None):
    out = _loc(text, lang)
    return out[0].upper() + out[1:] if isinstance(out, str) and out and out is not text else out


def _loc(text, lang=None):
    """Translate a canonical English staff string. Unknown text is returned unchanged."""
    lang = lang or LANG.get()
    if lang == "en" or not isinstance(text, str) or not text:
        return text
    idx = 0 if lang == "fi" else 1
    m = _WD.match(text)
    if m:
        return f"{WEEKDAYS[m.group(1)][idx]} klo {m.group(2)}" if lang == "fi" else f"{WEEKDAYS[m.group(1)][idx]} kl. {m.group(2)}"
    if text in EXACT:
        return EXACT[text][idx]
    for rx, fi, sv in _COMPILED:
        m = rx.match(text)
        if not m:
            continue
        g = list(m.groups())
        tpl = fi if lang == "fi" else sv

        def sub(mm):
            key = mm.group(1)
            if key in ("p", "L"):
                return mm.group(0)   # filled in below
            if key.startswith("~"):
                return loc(g[int(key[1:])], lang)
            return g[int(key)]
        out = re.sub(r"\{(~?\w+)\}", sub, tpl)
        if "{p}" in tpl:   # optional "of it before the referral" clause
            extra = ""
            if len(g) > 3 and g[3]:
                extra = f", josta {g[3]} ennen lähetettä" if lang == "fi" else f", varav {g[3]} före remissen"
            out = out.replace("{p}", extra)
        if "{L}" in tpl:
            extra = ""
            if len(g) > 2 and g[2]:
                nm = loc(g[2], lang)
                extra = f" Suurin: {nm}, {g[3]} päivää." if lang == "fi" else f" Störst: {nm}, {g[3]} dagar."
            out = out.replace("{L}", extra)
        return out
    return text


def loc_deep(obj, keys=None, lang=None):
    """Localise string values (optionally only some keys) in nested dicts/lists. Returns a new structure."""
    lang = lang or LANG.get()
    if lang == "en":
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            hit = keys is None or k in keys
            if hit and isinstance(v, str):
                out[k] = loc(v, lang)
            elif hit and isinstance(v, list) and all(isinstance(x, str) for x in v):
                out[k] = [loc(x, lang) for x in v]
            else:
                out[k] = loc_deep(v, keys, lang)
        return out
    if isinstance(obj, list):
        return [loc(v, lang) if isinstance(v, str) and keys is None else loc_deep(v, keys, lang) for v in obj]
    return obj
