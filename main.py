from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def scrape_businesses(query: str, country: str, max_results: int = 10):
    results = []
    search_term = f"{query} {country}"
    encoded = requests.utils.quote(search_term)

    # Primary: Google local search
    url = f"https://www.google.com/search?q={encoded}&tbm=lcl&num=20"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.VkpGBb") or soup.select("div.rllt__details") or soup.select("div[class*='uMdZh']")
        print(f"Google local cards found: {len(cards)}")

        for card in cards[:max_results]:
            try:
                lead = {}
                name_el = card.select_one("div.dbg0pd span, span.OSrXXb, div[class*='rllt__'] span")
                lead["name"] = name_el.get_text(strip=True) if name_el else ""
                if not lead["name"]:
                    continue
                rating_el = card.select_one("span.BTtC6e, span[class*='yi40Hd']")
                try:
                    lead["rating"] = float(rating_el.get_text(strip=True)) if rating_el else 0
                except:
                    lead["rating"] = 0
                details = [d.get_text(strip=True) for d in card.select("div.rllt__wrapped div, span.LrzXr") if d.get_text(strip=True)]
                lead["address"] = details[0] if details else ""
                lead["phone"] = next((t for t in details if re.search(r'[\+\d][\d\s\-\(\)]{7,}', t)), "")
                lead["website"] = ""
                lead["reviews"] = 0
                lead["source"] = "google_local"
                results.append(lead)
            except:
                continue
    except Exception as e:
        print(f"Google local error: {e}")

    # Fallback: Google organic search
    if not results:
        url2 = f"https://www.google.com/search?q={encoded}+contact+phone&num=20"
        try:
            resp2 = requests.get(url2, headers=HEADERS, timeout=15)
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            for item in soup2.select("div.g")[:max_results]:
                try:
                    title_el = item.select_one("h3")
                    if not title_el:
                        continue
                    name = title_el.get_text(strip=True)
                    link_el = item.select_one("a")
                    website = link_el.get("href", "") if link_el else ""
                    if website.startswith("/url?q="):
                        website = website.split("/url?q=")[1].split("&")[0]
                    snippet_el = item.select_one("div.VwiC3b")
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    phone_match = re.search(r'[\+\d][\d\s\-\(\)]{8,}', snippet)
                    results.append({
                        "name": name,
                        "website": website,
                        "phone": phone_match.group(0).strip() if phone_match else "",
                        "address": "",
                        "rating": 0,
                        "reviews": 0,
                        "source": "google_search",
                    })
                except:
                    continue
        except Exception as e:
            print(f"Fallback error: {e}")

    return results


@app.route("/scrape", methods=["GET", "POST"])
def scrape():
    data = request.get_json() if request.method == "POST" else request.args
    query = (data.get("query") or "").strip()
    country = (data.get("country") or "").strip()
    max_results = int(data.get("max_results", 10))

    if not query or not country:
        return jsonify({"error": "query and country are required"}), 400

    print(f"Request: query={query}, country={country}, max={max_results}")
    try:
        leads = scrape_businesses(query, country, max_results)
        return jsonify({"success": True, "count": len(leads), "leads": leads})
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
