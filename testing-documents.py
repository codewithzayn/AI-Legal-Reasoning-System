import requests
import time

BASE_URL = "https://opendata.finlex.fi/finlex/avoindata/v1"

categories = {
    "act": ["statute", "statute-consolidated", "statute-foreign-language-translation","statute-sami-translation"],
    "judgment": ["chancellor-of-justice-decision", "data-protection-ombudsman-decision"],
    "doc": ["collective-agreement-general-applicability-decision","authority-regulation", 
    "government-proposal", "legal-literature-references", "tax-treaty-consolidated",
    "trade-union-center-agreement", "treaty-metadata", "treaty"]
}
params = {
        "format": "json",
        "langAndVersion": "fin@",
        "startYear": 2025,
        "endYear": 2025,
        "limit": 10,
        "page": 1
    }
headers = {"User-Agent": "AI-Legal-Reasoning-System/1.0"}


total = 0
for category, subtypes in categories.items():
    for subtype in subtypes:
        url = f"{BASE_URL}/akn/fi/{category}/{subtype}/list"
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Handle both list and dict responses
            if isinstance(data, list):
                count = len(data)
            elif isinstance(data, dict):
                count = data.get("totalResults", 0)
            else:
                count = 0
                
            print(f"{category}/{subtype}: {count:,}")
            total += count
            
        except requests.exceptions.JSONDecodeError:
            print(f"{category}/{subtype}: Error - Invalid JSON response")
        except requests.exceptions.RequestException as e:
            print(f"{category}/{subtype}: Error - {str(e)}")
        except Exception as e:
            print(f"{category}/{subtype}: Error - {str(e)}")
            
        time.sleep(0.2)  # Be nice to the API

print(f"\nTOTAL: {total:,} documents")