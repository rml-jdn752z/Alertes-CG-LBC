import os, re, json, time, random
from curl_cffi import requests as cr
import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

print("--- DÉMARRAGE DU BOT VINTED MATÉRIEL PC ---")
if not TOKEN or not CHAT:
    print("❌ Secrets manquants : vérifie TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID.")
    raise SystemExit(1)

WWW = "https://www.vinted.fr"
API = "https://api.vinted.fr/svc-catalogue/items"
SEEN_FILE = "seen_vinted_cg.json"
MAX_FAV = 40
PRICE_CEILING = 500

# Pays autorisés (Europe de l'Ouest / FR)
ALLOWED_COUNTRY_IDS = {16, 14, 7, 13, 22, 20, 15, 21, 2}
COUNTRY_ID_MAP = {
    16: "FR", 14: "BE", 7: "ES", 13: "IT", 22: "NL",
    20: "PT", 15: "LU", 21: "DE", 2: "AT"
}

# Termes de recherche envoyés à l'API
SEARCHES = [
    # GPU
    "rtx 3070", "rtx 3070 ti", "rtx 3080", "rtx 3080 ti",
    "rx 6800", "rx 6800 xt", "rx 7700 xt", "rx 7800 xt",
    "rx 9060 xt", "rtx 5060 ti", "rtx 4070",
    "rtx 4070 ti", "rtx 4070 super", "rtx 4080", "rtx 4090",
    "rtx 5070", "rtx 5070 ti", "rtx 5080", "rtx 5090",
    "rx 6900 xt", "rx 6950 xt", "rx 7900 xt", "rx 7900 xtx", "rx 7900 gre",
    "rx 9070", "rx 9070 xt",
    # CPU
    "ryzen 9600x", "ryzen 7500f", "ryzen 7600x", "ryzen 7600",
    "ryzen 7500x3d", "ryzen 7800x3d",
    # RAM & SSD
    "ram ddr5 16go", "ram ddr5 16gb", "ssd nvme 500go", "ssd nvme 500gb",
    "ssd nvme 1to", "ssd nvme 1tb", "ssd nvme 2to", "ssd nvme 2tb",
    # CM & WC
    "a620m", "b650m", "watercooling 360", "watercooling 360mm"
]

# Modèles, patterns de détection et plafonds de prix spécifiques
MODELS = [
    # --- GPU ---
    (r"rtx\s*3070\s*ti", "RTX 3070 Ti", 270),
    (r"rtx\s*3070", "RTX 3070", 270),
    (r"rtx\s*3080\s*ti", "RTX 3080 Ti", 380),
    (r"rtx\s*3080", "RTX 3080", 360),
    (r"rx\s*9060\s*xt.{0,15}(16\s*go|16\s*gb)", "RX 9060 XT 16 Go", 380),
    (r"rx\s*9060\s*xt", "RX 9060 XT 8 Go", 300),
    (r"rx\s*6800\s*xt", "RX 6800 XT", 360),
    (r"rx\s*6800", "RX 6800", 270),
    (r"rx\s*7700\s*xt", "RX 7700 XT", 280),
    (r"rx\s*7800\s*xt", "RX 7800 XT", 380),
    (r"rtx\s*5060\s*ti.{0,15}(16\s*go|16\s*gb)", "RTX 5060 Ti 16 Go", 400),
    (r"rtx\s*5060\s*ti", "RTX 5060 Ti 8 Go", 350),
    (r"rtx\s*4070\s*ti\s*super", "RTX 4070 Ti Super", 500),
    (r"rtx\s*4070\s*ti", "RTX 4070 Ti", 500),
    (r"rtx\s*4070\s*super", "RTX 4070 Super", 500),
    (r"rtx\s*4070", "RTX 4070", 400),
    (r"rtx\s*4080\s*super", "RTX 4080 Super", 500),
    (r"rtx\s*4080", "RTX 4080", 500),
    (r"rtx\s*4090", "RTX 4090", 500),
    (r"rtx\s*5070\s*ti", "RTX 5070 Ti", 500),
    (r"rtx\s*5070", "RTX 5070", 500),
    (r"rtx\s*5080", "RTX 5080", 500),
    (r"rtx\s*5090", "RTX 5090", 500),
    (r"rx\s*6900\s*xt", "RX 6900 XT", 500),
    (r"rx\s*6950\s*xt", "RX 6950 XT", 500),
    (r"rx\s*7900\s*xtx", "RX 7900 XTX", 500),
    (r"rx\s*7900\s*xt", "RX 7900 XT", 500),
    (r"rx\s*7900\s*gre", "RX 7900 GRE", 500),
    (r"rx\s*9070\s*xt", "RX 9070 XT", 500),
    (r"rx\s*9070", "RX 9070", 500),

    # --- CPU ---
    (r"ryzen\s*5\s*9600x|r5\s*9600x", "Ryzen 5 9600X", 130),
    (r"ryzen\s*5\s*7500f|r5\s*7500f", "Ryzen 5 7500F", 80),
    (r"ryzen\s*5\s*7600x|r5\s*7600x", "Ryzen 5 7600X", 90),
    (r"ryzen\s*5\s*7600|r5\s*7600", "Ryzen 5 7600", 90),
    (r"ryzen\s*5\s*7500x3d|r5\s*7500x3d", "Ryzen 5 7500X3D", 200),
    (r"ryzen\s*7\s*7800x3d|r7\s*7800x3d", "Ryzen 7 7800X3D", 240),

    # --- RAM ---
    (r"16\s*(go|gb).{0,15}ddr5|ddr5.{0,15}16\s*(go|gb)", "RAM 16 Go DDR5", 130),

    # --- SSD NVMe ---
    (r"ssd.{0,10}nvme.{0,15}2\s*(to|tb)|2\s*(to|tb).{0,10}nvme", "SSD NVMe 2 To", 150),
    (r"ssd.{0,10}nvme.{0,15}(1\s*(to|tb)|1000\s*(go|gb))|(1\s*(to|tb)|1000\s*(go|gb)).{0,10}nvme", "SSD NVMe 1 To", 80),
    (r"ssd.{0,10}nvme.{0,15}500\s*(go|gb)|500\s*(go|gb).{0,10}nvme", "SSD NVMe 500 Go", 45),

    # --- Cartes mères ---
    (r"a620m|a620", "Carte mère A620M", 60),
    (r"b650m|b650", "Carte mère B650M", 90),

    # --- Watercooling ---
    (r"360\s*mm.{0,15}blanc|360.{0,15}blanc|watercooling.{0,15}360.{0,15}white", "Watercooling 360mm Blanc", 30),
]

BAD_WORDS = [
    "hs", "h.s", "hors service", "hors-service", "pour pièces",
    "pour pieces", "pour piece", "en panne", "panne", "défectueu",
    "defectueu", "ne fonctionne", "ne marche", "cassé", "casse",
    "artefact", "ne s'allume", "morte", "mort ", "à réparer",
    "a reparer", "brûlé", "brule", "backplate", "waterblock",
    "vendu", "réservé", "reserve", "achat en cours",
]

def tg(text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT, "text": text},
            timeout=20,
        )
        return r.status_code == 200
    except Exception as e:
        print("Telegram erreur :", e)
        return False

def price_of(item):
    p = item.get("price")
    if p is None:
        p = item.get("price_numeric")
    if isinstance(p, dict):
        p = p.get("amount")
    try:
        return float(str(p).replace(",", "."))
    except Exception:
        return None

def url_of(item):
    u = item.get("url") or item.get("path") or ""
    if u.startswith("/"):
        u = WWW + u
    if not u:
        u = f"{WWW}/items/{item.get('id')}"
    return u

def favs_of(item):
    try:
        return int(item.get("favourite_count") or 0)
    except Exception:
        return 0

def classify(title, body):
    text = f"{title} {body}".lower()
    for pattern, label, max_price in MODELS:
        if re.search(pattern, text):
            return label, max_price
    return None

def passes_basic_filters(item, max_price):
    text = (item.get("title", "") + " " + (item.get("description") or "")).lower()
    padded = " " + text.replace(",", " ").replace(".", " ") + " "
    
    # Exclude HS / Mots interdits
    for w in BAD_WORDS:
        if w == "hs":
            if " hs " in padded:
                return False
        elif w in text:
            return False

    # Exclusion systématique des boîtes seules / boîtes vides
    if any(b in text for b in ["boite seule", "boite uniquement", "boite vide", "boite de", "boite du", "boite d'", "boîte seule", "boîte uniquement", "boîte vide"]) \
            and not any(k in text for k in ["avec boite", "avec la boite", "dans sa boite", "avec sa boite", "avec boîte", "dans sa boîte"]):
        return False

    # Filtre sur le prix
    p = price_of(item)
    if p is None or p <= 0 or p > max_price:
        return False

    # Ignore si > 40 favoris
    if favs_of(item) > MAX_FAV:
        return False

    return True

def extract_country_id(item):
    user = item.get("user") or {}
    cid = user.get("country_id") or item.get("country_id")
    if cid is not None:
        try:
            return int(cid)
        except Exception:
            pass
    return None

s = cr.Session(impersonate="chrome")
s.headers.update({"Accept-Language": "fr-FR,fr;q=0.9"})

home = s.get(WWW, timeout=25)
print(f"Connexion Vinted : statut {home.status_code}")

token = s.cookies.get("access_token_web")
anon = home.headers.get("x-anon-id") or home.headers.get("X-Anon-Id")

headers = {"Accept": "application/json, text/plain, */*"}
if token:
    headers["Authorization"] = f"Bearer {token}"
if anon:
    headers["X-Anon-Id"] = anon

try:
    with open(SEEN_FILE, "r") as f:
        seen = set(json.load(f))
    print(f"📁 {len(seen)} annonces en mémoire")
except Exception:
    seen = set()

first_run = len(seen) == 0
to_send = []

for query in SEARCHES:
    try:
        r = s.get(
            API,
            params={
                "search_text": query,
                "price_to": str(PRICE_CEILING),
                "currency": "EUR",
                "order": "newest_first",
                "per_page": "50",
                "page": "1",
            },
            headers=headers,
            timeout=25,
        )
        status = r.status_code
        ads = r.json().get("items") or [] if status == 200 else []
    except Exception as e:
        print(f"❌ Erreur sur '{query}' :", e)
        status, ads = None, []

    print(f"🔍 '{query}' : statut {status}, {len(ads)} annonces reçues")

    for ad in ads:
        ad_id = str(ad.get("id"))
        if ad_id in seen:
            continue

        match = classify(ad.get("title") or "", ad.get("description") or "")
        if not match:
            seen.add(ad_id)
            continue

        label, max_price = match
        if passes_basic_filters(ad, max_price):
            cid = extract_country_id(ad)
            
            # Rejet si hors Europe / FR
            if cid not in ALLOWED_COUNTRY_IDS:
                seen.add(ad_id)
                continue

            country_code = COUNTRY_ID_MAP.get(cid, "EU")
            to_send.append((ad, label, max_price, country_code))
        else:
            seen.add(ad_id)

    time.sleep(random.uniform(1, 1.5))

print(f"📲 {len(to_send)} annonce(s) valide(s) Europe/FR à envoyer.")

if first_run and to_send:
    tg(f"✅ Bot Vinted Hardware actif. {len(to_send)} offres détectées.")

sent = 0
for ad, label, max_price, country in to_send:
    ad_id = str(ad.get("id"))
    title = ad.get("title", "Sans titre")
    p = price_of(ad)
    favs = favs_of(ad)

    msg = (
        f"🖥️ [{label}]\n{title}\n"
        f"💶 {p if p is not None else '?'} € (max {max_price} €)\n"
        f"❤️ {favs} favoris  🌍 {country}\n"
        f"{url_of(ad)}"
    )

    if tg(msg):
        seen.add(ad_id)
        sent += 1
        time.sleep(random.uniform(0.8, 1.2))

with open(SEEN_FILE, "w") as f:
    json.dump(sorted(seen), f)

print(f"--- FIN : {sent} notification(s) envoyée(s) ---")
