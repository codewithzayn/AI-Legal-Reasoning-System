"""
© 2026 Crest Advisory Group LLC. All rights reserved.

PROPRIETARY AND CONFIDENTIAL

This file is part of the Crest Pet System and contains proprietary
and confidential information of Crest Advisory Group LLC.
Unauthorized copying, distribution, or use is strictly prohibited.
"""

"""
Input language detection for multilingual routing.

Maps langdetect ISO 639-1 codes to our supported response languages (en, fi, sv).
Falls back to Finnish when detection fails or returns an unsupported language.
"""

from langdetect import LangDetectException, detect

# Map langdetect codes to our response_lang codes
_DETECT_TO_LANG = {
    "en": "en",
    "fi": "fi",
    "sv": "sv",
    # Common variants
    "et": "fi",  # Estonian -> Finnish (closest Nordic)
    "no": "sv",  # Norwegian -> Swedish (closest)
    "da": "sv",  # Danish -> Swedish
}


def detect_query_language(query: str) -> str:
    """Detect the language of the user's query.

    Returns one of: "en", "fi", "sv".
    Falls back to "fi" when detection fails or language is unsupported.
    """
    if not query or len(query.strip()) < 3:
        return "fi"
    try:
        code = detect(query.strip())
        return _DETECT_TO_LANG.get(code, "fi")
    except LangDetectException:
        return "fi"
