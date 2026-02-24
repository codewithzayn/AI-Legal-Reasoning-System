"""
Provision Extractor Service
Extracts legal statute, regulation, and provision references from court decisions.
Handles Finnish legal abbreviations, EU references, and international treaties.
"""

import re

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


class ProvisionExtractor:
    """Extracts legal provisions/statutes from court decision text."""

    # Finnish legal statute abbreviations and their full names
    FINNISH_STATUTES = {
        "PL": "Perustuslaki (Constitution)",
        "RL": "Rikoslaki (Criminal Code)",
        "OK": "Oikeudenkäyntikaari (Code of Judicial Procedure)",
        "VK": "Valtion virkamieslaki (State Officials Act)",
        "KuntalL": "Kuntalaki (Local Government Act)",
        "AML": "Ammattiyhdistyslainsäädäntö (Trade Union Act)",
        "StL": "Sähköpostilaki (Electronic Communications Act)",
        "KeL": "Kemikaalilainsäädäntö (Chemicals Act)",
        "YVL": "Ydinenergialaki (Nuclear Energy Act)",
        "LKL": "Lakikokoelma",
        "VTL": "Verotuslainsäädäntö (Tax Laws)",
        "YSL": "Ympäristönsuojelulaki (Environmental Protection Act)",
        "KTL": "Kilpailulainsäädäntö (Competition Act)",
        "KuL": "Kuluttajasuojelulaki (Consumer Protection Act)",
        "TL": "Tahdontekijälaki",
        "AiL": "Aikaansaannoslaki",
        "AL": "Asunto-osakeyhtiölaki (Housing Association Act)",
        "LahL": "Lahjoitusselostelaki",
        "PML": "Pelastuslaki (Rescue Act)",
        "HL": "Hallintolaki (Administrative Act)",
        "SL": "Seuraamustoimilaki",
        "MenL": "Menestyslaki",
        "PNL": "Puolueettomuuslaki",
        "MTL": "Maankäyttö- ja rakennuslaki (Land Use and Building Act)",
        "RKL": "Rekisteröintilaki",
    }

    # Regex patterns for extracting provisions
    PROVISION_PATTERNS = [
        # Finnish statute with section: "RL 46 §", "RL § 46", "RL 46:1", "RL 46/1"
        r"([A-Z][a-zA-Z]*L?)\s*(?:§|[Ss]ec\.?|[Ss]ectio|[Pp]ara\.?)\s*(\d+)(?:[:/](\d+))?",
        # EU Directive: "Directive 2020/123" or "Dir. 2020/123"
        r"(?:Directive|Dir\.?)\s+(\d{4})/(\d+)/EU",
        # EU Regulation: "Regulation (EU) No 833/2014"
        r"(?:Regulation|Reg\.?)\s+\(EU\)\s+(?:No|Nr\.?)\s+(\d+)/(\d{4})",
        # Government proposal: "HE 44/2002"
        r"HE\s+(\d+)/(\d{4})",
        # Court of Justice case: "C-123/45 ECJ" or "C-123/45 CJEU"
        r"C-(\d+)/(\d{2})",
        # Law number: "Laki 123/2020" or "Law No. 123/2020"
        r"(?:Laki|Law)\s+(?:No\.?|Nr\.?)\s+(\d+)/(\d{4})",
        # EU Treaty reference: "TFEU Article 123" or "TEU Article 45"
        r"(?:TFEU|TEU)\s+(?:Article|Art\.?)\s+(\d+)",
        # Generic statute chapter/section: "Chapter 3 Section 5" or "§ 45"
        r"(?:Chapter|Ch\.?)\s+(\d+)\s+(?:Section|Sec\.?|§)\s+(\d+)",
        # International convention: "European Convention on Human Rights"
        r"(?:European Convention|ECHR|International Convention)",
    ]

    def __init__(self) -> None:
        """Initialize provision extractor."""
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile all regex patterns for performance."""
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.PROVISION_PATTERNS]

    def extract_provisions(self, text: str) -> dict:
        """Extract legal provisions from text.

        Args:
            text: Full text of court decision.

        Returns:
            Dict with:
            - provisions: List of extracted provision references
            - applied_provisions: Comma-separated string for database storage
            - unique_statutes: Set of unique statute abbreviations found
            - extraction_confidence: 0.0-1.0 quality score
        """
        if not text or not text.strip():
            return {
                "provisions": [],
                "applied_provisions": "",
                "unique_statutes": [],
                "extraction_confidence": 0.0,
            }

        provisions = set()
        unique_statutes = set()

        # Extract using patterns
        for pattern in self.compiled_patterns:
            matches = pattern.finditer(text)
            for match in matches:
                provision_ref = match.group(0).strip()
                if provision_ref:
                    provisions.add(provision_ref)

        # Extract statute abbreviations with sections (e.g., "RL 46 §")
        statute_section_pattern = r"\b([A-Z][a-zA-Z]*L?)\s+(?:§|[Ss]ec\.?)\s+(\d+(?:[:/]\d+)?)\b"
        for match in re.finditer(statute_section_pattern, text):
            statute = match.group(1)
            section = match.group(2)
            unique_statutes.add(statute)
            provisions.add(f"{statute} § {section}")

        # Extract government proposals (HE references)
        he_pattern = r"HE\s+(\d+)/(\d{4})"
        for match in re.finditer(he_pattern, text):
            provisions.add(match.group(0).strip())

        # Extract EU Directive/Regulation references
        eu_pattern = r"(?:Directive|Dir\.?)\s+(\d{4})/(\d+)/EU"
        for match in re.finditer(eu_pattern, text):
            provisions.add(match.group(0).strip())

        # Extract law number references
        law_pattern = r"(?:Laki|Law)\s+(?:No\.?|Nr\.?)\s+(\d+)/(\d{4})"
        for match in re.finditer(law_pattern, text):
            provisions.add(match.group(0).strip())

        # Extract CJEU case references
        cjeu_pattern = r"C-(\d+)/(\d{2})"
        for match in re.finditer(cjeu_pattern, text):
            provisions.add(match.group(0).strip())

        # Remove duplicates and sort for consistency
        sorted_provisions = sorted(list(provisions))

        # Calculate extraction confidence based on quantity and types found
        confidence = self._calculate_confidence(len(sorted_provisions), unique_statutes)

        logger.info(
            "Extracted %d provisions from document (%d unique statutes, confidence=%.2f)",
            len(sorted_provisions),
            len(unique_statutes),
            confidence,
        )

        return {
            "provisions": sorted_provisions,
            "applied_provisions": "; ".join(sorted_provisions) if sorted_provisions else "",
            "unique_statutes": sorted(list(unique_statutes)),
            "extraction_confidence": confidence,
        }

    @staticmethod
    def _calculate_confidence(provision_count: int, unique_statutes: set) -> float:
        """Calculate extraction confidence score.

        Based on:
        - Number of provisions found (more = higher confidence in extraction working)
        - Diversity of statute types (indicates thorough extraction)
        """
        if provision_count == 0:
            return 0.0

        # Confidence increases with number of provisions found
        provision_confidence = min(provision_count / 10, 1.0)  # 10+ = full confidence

        # Bonus for statute diversity
        statute_bonus = min(len(unique_statutes) / 5, 0.15)  # Up to 15% bonus for 5+ statutes

        return min(provision_confidence + statute_bonus, 1.0)

    def extract_statute_abbreviations(self, text: str) -> dict[str, int]:
        """Extract and count statute abbreviations in text.

        Args:
            text: Full text of court decision.

        Returns:
            Dict mapping statute abbreviation to count of occurrences.
        """
        statute_counts = {}

        for statute, _full_name in self.FINNISH_STATUTES.items():
            # Match statute abbreviation with optional section reference
            pattern = rf"\b{re.escape(statute)}\b"
            matches = re.finditer(pattern, text, re.IGNORECASE)
            count = len(list(matches))
            if count > 0:
                statute_counts[statute] = count

        return statute_counts

    def extract_with_context(self, text: str, context_chars: int = 150) -> list[dict]:
        """Extract provisions with surrounding context (for validation/review).

        Args:
            text: Full text of court decision.
            context_chars: Characters of context before/after provision.

        Returns:
            List of dicts with: provision, context, position
        """
        results = []

        # Find all provision matches with context
        for pattern in self.compiled_patterns:
            for match in pattern.finditer(text):
                provision = match.group(0).strip()
                start = max(0, match.start() - context_chars)
                end = min(len(text), match.end() + context_chars)
                context = text[start:end]

                results.append(
                    {
                        "provision": provision,
                        "context": context,
                        "position": match.start(),
                        "statute": match.group(1) if match.lastindex >= 1 else None,
                    }
                )

        return sorted(results, key=lambda x: x["position"])
