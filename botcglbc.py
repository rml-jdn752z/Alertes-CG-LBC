import os, re, json, time, random, requests
from playwright.sync_api import sync_playwright

TOKEN = os.environ.get("LBC_CG_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

print("--- DÉMARRAGE DU BOT LBC CARTES GRAPHIQUES ---")
if not TOKEN or not CHAT:
    print("❌ Secrets manquants : vérifie LBC_CG_BOT_TOKEN et TELEGRAM_CHAT_ID.")
    raise SystemExit(1)

SEEN_FILE = "seen_lbc_cg.json"
MAX_FAV = 40
REQUEST_PRICE_CEILING = 500  # plafond large côté recherche ; le vrai plafond est appliqué par modèle

# Recherches Leboncoin (une par modèle ou famille)
SEARCHES = [
    "rtx 3070", "rtx 3070 ti", "rtx 3080", "rtx 3080 ti",
    "rx 9060 xt", "rx 6800", "rx 6800 xt", "rx 7700 xt", "rx 7800 xt",
    "rtx 5060 ti", "rtx 4070",
    "rtx 4070 ti", "rtx 4070 super", "rtx 4080", "rtx 4090",
    "rtx 5070", "rtx 5070 ti", "rtx 5080", "rtx 5090",
    "rx 6900 xt", "rx 6950 xt", "rx 7900 xt", "rx 7900 xtx", "rx 7900 gre",
    "rx 9070", "rx 9070 xt",
]

# Modèle -> (nom affiché, prix max), du plus précis au plus général
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
]

SOLD_STATUSES = {"sold", "reserved", "pending", "purchase_pending", "inactive"}


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


def classify(title, body):
    text = f"{title} {body}".lower()
    for pattern, label, max_price in MODELS:
        if re.search(pattern, text):
            return label, max_price
    return None


def is_ok(ad, label, max_price):
    title = ad.get("subject") or ""
    body = ad.get("body") or ""
    text = f"{title} {body}".lower()

    status = (ad.get("status") or "").lower()
    if status in SOLD_STATUSES or "achat en cours" in text or "réservé" in text or "reserve" in text or "vendu" in text:
        return False

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

    price_list = ad.get("price") or []
    price = price_list[0] if price_list else 0
    if price <= 0 or price > max_price:
        return False

    fav_count = ad.get("like_count") or ad.get("nb_likes") or 0
    if fav_count > MAX_FAV:
        return False

    return True


try:
    with open(SEEN_FILE, "r") as f:
        seen = set(json.load(f))
    print(f"📁 {len(seen)} annonces déjà en mémoire")
except Exception:
    seen = set()
    print("📁 Aucun historique trouvé, on part de zéro.")

first_run = len(seen) == 0
to_send = []

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['fr-FR', 'fr']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
"""

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        locale="fr-FR",
        viewport={"width": 1280, "height": 800},
    )
    context.add_init_script(STEALTH_JS)
    page = context.new_page()

    try:
        page.goto("https://www.leboncoin.fr", timeout=30000, wait_until="networkidle")
        time.sleep(random.uniform(1.5, 3))
    except Exception as e:
        print("⚠️ Erreur au chargement initial :", e)

    for query in SEARCHES:
        payload = {
            "limit": 35,
            "filters": {
                "keywords": {"text": query},
                "price": {"max": REQUEST_PRICE_CEILING},
                "enums": {"ad_type": ["offer"]},
            },
            "sort_by": "time",
            "sort_order": "desc",
        }

        result = None
        for attempt in range(2):
            try:
                result = page.evaluate(
                    """
                    async (payload) => {
                        const res = await fetch('https://api.leboncoin.fr/finder/search', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'api_key': 'ba444675426c5002803ea272e1c7200c'
                            },
                            body: JSON.stringify(payload)
                        });
                        return {status: res.status, body: res.status === 200 ? await res.json() : null};
                    }
                    """,
                    payload,
                )
                break
            except Exception as e:
                print(f"❌ Erreur réseau sur '{query}' (essai {attempt + 1}) :", e)
                time.sleep(2)

        if not result or result.get("status") != 200 or not result.get("body"):
            print(f"⚠️ '{query}' : bloqué ou vide (statut {result.get('status') if result else '?'})")
            time.sleep(random.uniform(0.8, 1.6))
            continue

        ads = result["body"].get("ads") or []
        print(f"🔍 '{query}' : {len(ads)} annonces reçues")

        for ad in ads:
            ad_id = str(ad.get("list_id"))
            if ad_id in seen:
                continue

            match = classify(ad.get("subject") or "", ad.get("body") or "")
            if not match:
                seen.add(ad_id)
                continue

            label, max_price = match
            if is_ok(ad, label, max_price):
                to_send.append((ad, label, max_price))
            else:
                seen.add(ad_id)

        time.sleep(random.uniform(0.8, 1.6))

    browser.close()

print(f"📲 {len(to_send)} annonce(s) à envoyer.")

if first_run and to_send:
    tg(f"✅ Bot Cartes Graphiques LBC actif. {len(to_send)} annonces trouvées, envoi en cours.")

sent = 0
for ad, label, max_price in to_send:
    ad_id = str(ad.get("list_id"))
    title = ad.get("subject", "Sans titre")
    price = (ad.get("price") or [0])[0]
    url = ad.get("url") or f"https://www.leboncoin.fr/ad/informatique/{ad_id}"
    location = (ad.get("location") or {}).get("city", "France")
    favs = ad.get("like_count") or ad.get("nb_likes") or 0

    msg = f"🎮 [{label}]\n{title}\n💶 {price} € (max {max_price} €)\n❤️ {favs} favoris\n📍 {location}\n{url}"

    if tg(msg):
        seen.add(ad_id)
        sent += 1
        time.sleep(random.uniform(0.8, 1.3))

with open(SEEN_FILE, "w") as f:
    json.dump(sorted(seen), f)

print(f"--- FIN : {sent} notification(s) envoyée(s) sur {len(to_send)} ---")
