import os, re, json, time, random
from curl_cffi import requests as cr
import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

print("--- DÉMARRAGE DU BOT VINTED CARTES GRAPHIQUES ---")
if not TOKEN or not CHAT:
    print("❌ Secrets manquants : vérifie TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID.")
    raise SystemExit(1)

WWW = "https://www.vinted.fr"
API = "https://api.vinted.fr/svc-catalogue/items"
SEEN_FILE = "seen_vinted_cg.json"
MAX_FAV = 40
PRICE_CEILING = 500

# Pays acceptés : France + Europe de l'Ouest proche
ALLOWED_COUNTRIES = {"FR", "BE", "NL", "LU", "ES", "IT", "PT", "IE", "DE"}

SEARCHES = [
    "rtx 3070", "rtx 3070 ti", "rtx 3080", "rtx 3080 ti",
    "rx 9060 xt", "rx 6800", "rx 6800 xt", "rx 7700 xt", "rx 7800 xt",
    "rtx 5060 ti", "rtx 4070",
    "rtx 4070 ti", "rtx 4070 super", "rtx 4080", "rtx 4090",
    "rtx 5070", "rtx 5070 ti", "rtx 5080", "rtx 5090",
    "rx 6900 xt", "rx 6950 xt", "rx 7900 xt", "rx 7900 xtx", "rx 7900 gre",
    "rx 9070", "rx 9070 xt",
]

MODELS = [
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
        print("Telegram :", r.status_code, r.text[:150])
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
    for w in BAD_WORDS:
        if w == "hs":
            if " hs " in padded:
                return False
        elif w in text:
            return False

    if any(b in text for b in ["boite seule", "boite uniquement", "boite vide", "boite de", "boite du", "boite d'"]) \
            and not any(k in text for k in ["avec boite", "avec la boite", "dans sa boite", "avec sa boite"]):
        return False

    p = price_of(item)
    if p is None or p <= 0 or p > max_price:
        return False

    if favs_of(item) > MAX_FAV:
        return False

    return True


def seller_country(session, item_url):
    """Va lire la vraie fiche de l'annonce pour trouver le pays du vendeur.
    Renvoie None si l'info n'a pas pu être confirmée (l'annonce sera alors écartée)."""
    try:
        r = session.get(item_url, timeout=20)
        if r.status_code != 200:
            return None
        html = r.text
    except Exception:
        return None

    m = re.search(r'"country_code"\s*:\s*"([A-Z]{2})"', html)
    if m:
        return m.group(1)
    m = re.search(r'"country_iso_code"\s*:\s*"([A-Z]{2})"', html)
    if m:
        return m.group(1)
    return None


s = cr.Session(impersonate="chrome")
s.headers.update({"Accept-Language": "fr-FR,fr;q=0.9"})
home = s.get(WWW, timeout=25)
print("Accueil Vinted :", home.status_code)

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
    print(f"📁 {len(seen)} annonces déjà en mémoire")
except Exception:
    seen = set()
    print("📁 Aucun historique trouvé, on part de zéro.")

first_run = len(seen) == 0
candidates = []

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
                "time": str(int(time.time())),
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
            candidates.append((ad, label, max_price))
        else:
            seen.add(ad_id)

    time.sleep(random.uniform(1, 2))

print(f"🕵️ {len(candidates)} annonce(s) candidate(s), vérification du pays du vendeur...")

to_send = []
for ad, label, max_price in candidates:
    ad_id = str(ad.get("id"))
    country = seller_country(s, url_of(ad))
    print(f"   → annonce {ad_id} ({label}) : pays détecté = {country}")

    if country is None or country not in ALLOWED_COUNTRIES:
        seen.add(ad_id)
        continue

    to_send.append((ad, label, max_price, country))
    time.sleep(random.uniform(0.6, 1.2))

print(f"📲 {len(to_send)} annonce(s) à envoyer.")

if first_run and to_send:
    tg(f"✅ Bot Cartes Graphiques Vinted actif. {len(to_send)} annonces trouvées, envoi en cours.")

sent = 0
for ad, label, max_price, country in to_send:
    ad_id = str(ad.get("id"))
    title = ad.get("title", "Sans titre")
    p = price_of(ad)
    favs = favs_of(ad)

    msg = (
        f"🎮 [{label}]\n{title}\n"
        f"💶 {p if p is not None else '?'} € (max {max_price} €)\n"
        f"❤️ {favs} favoris  🌍 {country}\n"
        f"{url_of(ad)}"
    )

    if tg(msg):
        seen.add(ad_id)
        sent += 1
        time.sleep(random.uniform(0.8, 1.3))

with open(SEEN_FILE, "w") as f:
    json.dump(sorted(seen), f)

print(f"--- FIN : {sent} notification(s) envoyée(s) sur {len(to_send)} ---")
