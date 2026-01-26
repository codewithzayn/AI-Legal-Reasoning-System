"""
Complete KKO Case Extraction using Playwright
Extracts ALL sections from the case page
"""

import asyncio
from playwright.async_api import async_playwright
import re
import json

async def extract_complete_case(url: str):
    """Extract complete case data with all sections"""
    
    print(f"🔍 Fetching: {url}\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(3000)  # Wait for dynamic content
        
        # Get FULL text content
        full_text = await page.evaluate('''() => {
            const main = document.querySelector('main') || document.querySelector('article') || document.body;
            return main.innerText;
        }''')
        
        await browser.close()
    
    # Parse the full text into sections
    result = parse_case_text(full_text)
    
    return result

def parse_case_text(text: str) -> dict:
    """Parse the case text into structured sections"""
    
    # Finnish section markers
    section_markers = {
        "lower_court": "Asian käsittely alemmissa oikeuksissa",
        "appeal": "Muutoksenhaku Korkeimmassa oikeudessa",
        "supreme_court_decision": "Korkeimman oikeuden ratkaisu",
        "reasoning": "Perustelut",
        "judgment": "Tuomiolauselma",
    }
    
    result = {
        "metadata": {},
        "sections": {},
        "full_text": text,
        "full_text_length": len(text)
    }
    
    # Extract metadata
    case_id = re.search(r"KKO[:\s]*\d{4}[:\s]*\d+", text)
    ecli = re.search(r"ECLI:FI:KKO:\d{4}:\d+", text)
    date = re.search(r"Antopäivä\s*\n?(\d{1,2}\.\d{1,2}\.\d{4})", text)
    diary = re.search(r"Diaarinumero\s*\n?(R?\d+/\d+)", text)
    year = re.search(r"Tapausvuosi\s*\n?(\d{4})", text)
    
    # Keywords - everything between "Asiasanat" and "Tapausvuosi"
    keywords_match = re.search(r"Asiasanat\s*\n(.*?)Tapausvuosi", text, re.DOTALL)
    keywords = []
    if keywords_match:
        keywords_text = keywords_match.group(1).strip()
        keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
    
    result["metadata"] = {
        "case_id": case_id.group(0).replace(" ", ":") if case_id else None,
        "ecli": ecli.group(0) if ecli else None,
        "date": date.group(1) if date else None,
        "diary_number": diary.group(1) if diary else None,
        "year": int(year.group(1)) if year else None,
        "keywords": keywords
    }
    
    # Extract abstract (text before first section marker)
    first_section_pos = len(text)
    for marker in section_markers.values():
        pos = text.find(marker)
        if pos > 0 and pos < first_section_pos:
            first_section_pos = pos
    
    # Find abstract after ECLI link (skip metadata table)
    ecli_pos = text.find("ECLI-tunnus")
    if ecli_pos > 0:
        abstract_start = text.find("\n", ecli_pos + 50)  # Skip ECLI line
        if abstract_start > 0 and abstract_start < first_section_pos:
            abstract = text[abstract_start:first_section_pos].strip()
            # Clean up: remove "Kopioi ECLI-linkki" if present
            abstract = re.sub(r"Kopioi ECLI-linkki\s*", "", abstract)
            result["sections"]["abstract"] = abstract.strip()
    
    # Extract each named section
    for section_key, marker in section_markers.items():
        section_text = extract_section(text, marker, list(section_markers.values()))
        if section_text:
            result["sections"][section_key] = section_text
    
    return result

def extract_section(text: str, start_marker: str, all_markers: list) -> str:
    """Extract text between start_marker and the next section marker"""
    
    start_pos = text.find(start_marker)
    if start_pos == -1:
        return ""
    
    # Move past the marker itself
    start_pos += len(start_marker)
    
    # Find the next section marker
    end_pos = len(text)
    for marker in all_markers:
        if marker == start_marker:
            continue
        pos = text.find(marker, start_pos)
        if pos > start_pos and pos < end_pos:
            end_pos = pos
    
    section_text = text[start_pos:end_pos].strip()
    return section_text

async def main():
    url = "https://www.finlex.fi/fi/oikeuskaytanto/korkein-oikeus/ennakkopaatokset/2026/1"
    
    print("🚀 Complete KKO Case Extraction")
    print("=" * 70)
    
    result = await extract_complete_case(url)
    
    # Print summary
    print("\n" + "=" * 70)
    print("📋 EXTRACTION SUMMARY")
    print("=" * 70)
    
    print("\n🔖 METADATA:")
    for key, value in result["metadata"].items():
        if key == "keywords":
            print(f"  {key}:")
            for kw in value[:5]:  # First 5 keywords
                print(f"    - {kw}")
        else:
            print(f"  {key}: {value}")
    
    print(f"\n📊 FULL TEXT LENGTH: {result['full_text_length']} characters")
    
    print("\n📄 SECTIONS EXTRACTED:")
    for section_key, section_text in result["sections"].items():
        status = "✅" if len(section_text) > 50 else "⚠️" if section_text else "❌"
        print(f"  {status} {section_key}: {len(section_text)} chars")
    
    print("\n📖 SECTION PREVIEWS (first 500 chars each):")
    print("-" * 70)
    for section_key, section_text in result["sections"].items():
        if section_text:
            print(f"\n### {section_key.upper()} ###")
            print(section_text[:500] + ("..." if len(section_text) > 500 else ""))
    
    # Save to JSON file
    with open("kko_case_complete.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Complete data saved to: kko_case_complete.json")

if __name__ == "__main__":
    asyncio.run(main())
