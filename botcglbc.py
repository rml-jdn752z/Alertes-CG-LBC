import os, re, json, time, random, requests
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

TOKEN = os.environ.get("LBC_CG_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

print("--- DÉMARRAGE DU BOT LBC CARTES GRAPHIQUES ---")
if not TOKEN or not CHAT:
    print("❌ Secrets manquants : vérifie LBC_CG_BOT_TOKEN et TELEGRAM_CHAT_ID.")
    raise SystemExit(1)

SEEN_FILE = "seen_lbc_cg.json"
MAX_FAV = 40
PRICE_CEILING = 500

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


def is_ok(ad, max_price):
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
    price = price_list[0] if price_list else ad.get("price_cents", 0) / 100 if ad.get("price_cents") else 0
    if not price or price <= 0 or price > max_price:
        return False

    fav_count = ad.get("like_count") or ad.get("nb_likes") or 0
    if fav_count > MAX_FAV:
        return False

    return True


def find_ads(node, results):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "list_id" in v[0] and "subject" in v[0]:
                results.extend(v)
            else:
                find_ads(v, results)
    elif isinstance(node, list):
        for item in node:
            find_ads(item, results)


def extract_ads_from_page(page):
    try:
        html = page.content()
    except Exception:
        return []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    results = []
    find_ads(data, results)
    uniq = {}
    for ad in results:
        uniq[ad.get("list_id")] = ad
    return list(uniq.values())


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
window.chrome = { runtime: {} };
"""

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        locale="fr-FR",
        viewport={"width": 1366, "height": 850},
        extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"},
    )
    context.add_init_script(STEALTH_JS)
    page = context.new_page()

    try:
        page.goto("https://www.leboncoin.fr", timeout=30000, wait_until="domcontentloaded")
        time.sleep(random.uniform(2, 3.5))
        for label in ["Accepter", "Accepter tout", "J'accepte"]:
            try:
                btn = page.get_by_text(label, exact=False).first
                if btn.is_visible(timeout=1500):
                    btn.click(timeout=1500)
                    time.sleep(1)
                    break
            except Exception:
                pass
    except Exception as e:
        print("⚠️ Erreur au chargement initial :", e)

    for query in SEARCHES:
        url = f"https://www.leboncoin.fr/recherche?text={quote_plus(query)}&price=0-{PRICE_CEILING}&sort=time&order=desc"
        try:
            resp = page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(random.uniform(2, 3.5))
            status = resp.status if resp else None
            ads = extract_ads_from_page(page)
            print(f"🔍 '{query}' : statut {status}, {len(ads)} annonces trouvées sur la page")
        except Exception as e:
            print(f"❌ Erreur sur '{query}' :", e)
            ads = []

        for ad in ads:
            ad_id = str(ad.get("list_id"))
            if ad_id in seen:
                continue

            match = classify(ad.get("subject") or "", ad.get("body") or "")
            if not match:
                seen.add(ad_id)
                continue

            label, max_price = match
            if is_ok(ad, max_price):
                to_send.append((ad, label, max_price))
            else:
                seen.add(ad_id)

        time.sleep(random.uniform(1.5, 3))

    browser.close()

print(f"📲 {len(to_send)} annonce(s) à envoyer.")

if first_run and to_send:
    tg(f"✅ Bot Cartes Graphiques LBC actif. {len(to_send)} annonces trouvées, envoi en cours.")

sent = 0
for ad, label, max_price in to_send:
    ad_id = str(ad.get("list_id"))
    title = ad.get("subject", "Sans titre")
    price_list = ad.get("price") or []
    price = price_list[0] if price_list else (ad.get("price_cents", 0) / 100 if ad.get("price_cents") else "?")
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
