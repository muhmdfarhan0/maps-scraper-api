from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse

app = Flask(__name__)

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

def scrape_duckduckgo(query: str, country: str, max_results: int = 10):
    """Scrape DuckDuckGo search results - much less likely to block than Google"""
    results = []
    search_term = f"{query} {country} phone email website"
    encoded = urllib.parse.quote(search_term)

    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    try:
        resp = requests.get(url, headers=get_headers(), timeout=15)
        print(f"DDG status: {resp.status_code}, size: {len(resp.text)}")
        soup = BeautifulSoup(resp.text, "lxml")

        items = soup.select("div.result, div.results_links, div[class*='result']")
        print(f"DDG items found: {len(items)}")

        for item in items[:max_results]:
            try:
                # Title / company name
                title_el = item.select_one("a.result__a, h2 a, a[class*='result']")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)
                if not name or len(name) < 3:
                    continue

                # Website
                website = title_el.get("href", "")
                if "duckduckgo.com" in website or not website.startswith("http"):
                    redirect_el = item.select_one("a.result__url")
                    website = redirect_el.get_text(strip=True) if redirect_el else ""
                    if website and not website.startswith("http"):
                        website = "https://" + website

                # Snippet
                snippet_el = item.select_one("a.result__snippet, div.result__snippet, span[class*='snippet']")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                # Extract phone from snippet
                phone_match = re.search(r'(\+?\d[\d\s\-\(\)]{8,15})', snippet)
                phone = phone_match.group(1).strip() if phone_match else ""

                # Extract email from snippet
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', snippet)
                email = email_match.group(0) if email_match else ""

                results.append({
                    "name": name,
                    "website": website,
                    "phone": phone,
                    "email": email,
                    "address": country,
                    "rating": 0,
                    "reviews": 0,
                    "source": "duckduckgo",
                })
            except Exception as e:
                print(f"Item parse error: {e}")
                continue

    except Exception as e:
        print(f"DDG error: {e}")

    return results


def scrape_bing(query: str, country: str, max_results: int = 10):
    """Fallback: Bing search"""
    results = []
    search_term = f"{query} {country} contact"
    encoded = urllib.parse.quote(search_term)
    url = f"https://www.bing.com/search?q={encoded}&count=20"

    try:
        resp = requests.get(url, headers=get_headers(), timeout=15)
        print(f"Bing status: {resp.status_code}")
        soup = BeautifulSoup(resp.text, "lxml")

        items = soup.select("li.b_algo")
        print(f"Bing items: {len(items)}")

        for item in items[:max_results]:
            try:
                title_el = item.select_one("h2 a")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)
                website = title_el.get("href", "")

                snippet_el = item.select_one("div.b_caption p, p.b_lineclamp2")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                phone_match = re.search(r'(\+?\d[\d\s\-\(\)]{8,15})', snippet)
                phone = phone_match.group(1).strip() if phone_match else ""

                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', snippet)
                email = email_match.group(0) if email_match else ""

                if name and len(name) > 3:
                    results.append({
                        "name": name,
                        "website": website,
                        "phone": phone,
                        "email": email,
                        "address": country,
                        "rating": 0,
                        "reviews": 0,
                        "source": "bing",
                    })
            except:
                continue

    except Exception as e:
        print(f"Bing error: {e}")

    return results


def extract_contact_from_website(url: str) -> dict:
    if not url or not url.startswith("http"):
        return {"phone": "", "email": ""}
    try:
        resp = requests.get(url, headers=get_headers(), timeout=8)
        text = resp.text

        # Extract email
        email_match = re.findall(r'[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}', text)
        email = next((e for e in email_match if not e.endswith('.png')
                     and not e.endswith('.jpg') and 'example' not in e), "")

        # Extract phone
        phone_match = re.findall(r'(\+?\d[\d\s\-\.\(\)]{7,15}\d)', text)
        phone = phone_match[0].strip() if phone_match else ""

        return {"phone": phone, "email": email}
    except:
        return {"phone": "", "email": ""}


def scrape_businesses(query: str, country: str, max_results: int = 10):
    # Try DuckDuckGo first
    results = scrape_duckduckgo(query, country, max_results)

    # Fallback to Bing if DDG returned nothing
    if not results:
        print("DDG returned 0, trying Bing...")
        results = scrape_bing(query, country, max_results)

    # Deduplicate and enrich with contact info from each website
    enriched = []
    seen_names = set()
    for lead in results:
        name_key = lead["name"].lower().strip()[:30]
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        if lead.get("website"):
            contact = extract_contact_from_website(lead["website"])
            lead["phone"] = lead["phone"] or contact["phone"]
            lead["email"] = lead.get("email", "") or contact["email"]

        enriched.append(lead)

    return enriched[:max_results]


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
        print(f"Returning {len(leads)} leads")
        return jsonify({
            "success": True,
            "count": len(leads),
            "leads": leads,
        })
    except Exception as e:
        print(f"Failed: {e}")
        return jsonify({"error": str(e), "success": False}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
