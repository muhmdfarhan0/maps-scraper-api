from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import re

app = Flask(__name__)

def scrape_google_maps(query: str, country: str, max_results: int = 10):
    search_term = f"{query} {country}"
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()

        url = f"https://www.google.com/maps/search/{search_term.replace(' ', '+')}"
        print(f"Searching: {url}")
        page.goto(url, timeout=30000)
        page.wait_for_timeout(3000)

        try:
            results_panel = page.locator('[role="feed"]')
            for _ in range(5):
                results_panel.evaluate("el => el.scrollTop += 800")
                page.wait_for_timeout(1000)
        except Exception as e:
            print(f"Scroll error (non-fatal): {e}")

        listings = page.locator('[role="feed"] > div > div > a').all()
        print(f"Found {len(listings)} listings")

        for i, listing in enumerate(listings[:max_results]):
            try:
                listing.click()
                page.wait_for_timeout(2500)
                lead = {}

                try:
                    lead["name"] = page.locator('h1.DUwDvf, h1[class*="fontHeadlineLarge"]').first.inner_text(timeout=3000)
                except:
                    try:
                        lead["name"] = listing.get_attribute("aria-label") or ""
                    except:
                        lead["name"] = ""

                if not lead["name"]:
                    continue

                try:
                    rating_text = page.locator('[class*="fontDisplayLarge"]').first.inner_text(timeout=2000)
                    lead["rating"] = float(rating_text.strip())
                except:
                    lead["rating"] = 0

                try:
                    reviews_text = page.locator('span[aria-label*="reviews"]').first.get_attribute("aria-label", timeout=2000)
                    numbers = re.findall(r'[\d,]+', reviews_text or "")
                    lead["reviews"] = int(numbers[0].replace(",", "")) if numbers else 0
                except:
                    lead["reviews"] = 0

                try:
                    lead["address"] = page.locator('button[data-item-id="address"] [class*="fontBodyMedium"]').first.inner_text(timeout=2000)
                except:
                    lead["address"] = ""

                try:
                    lead["phone"] = page.locator('button[data-item-id*="phone"] [class*="fontBodyMedium"]').first.inner_text(timeout=2000)
                except:
                    lead["phone"] = ""

                try:
                    lead["website"] = page.locator('a[data-item-id="authority"]').first.get_attribute("href", timeout=2000) or ""
                except:
                    lead["website"] = ""

                lead["source"] = "google_maps"
                print(f"Scraped: {lead['name']} | {lead.get('phone','no phone')} | {lead.get('website','no site')}")
                results.append(lead)

            except Exception as e:
                print(f"Error on listing {i}: {e}")
                continue

        browser.close()
    return results


@app.route("/scrape", methods=["GET", "POST"])
def scrape():
    if request.method == "POST":
        data = request.get_json() or {}
    else:
        data = request.args

    query = data.get("query", "").strip()
    country = data.get("country", "").strip()
    max_results = int(data.get("max_results", 10))

    if not query:
        return jsonify({"error": "query is required"}), 400
    if not country:
        return jsonify({"error": "country is required"}), 400

    print(f"Request: query={query}, country={country}, max={max_results}")

    try:
        leads = scrape_google_maps(query, country, max_results)
        return jsonify({
            "success": True,
            "query": query,
            "country": country,
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
