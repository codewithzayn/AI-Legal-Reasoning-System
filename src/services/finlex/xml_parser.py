"""
XML Parser for Finlex Documents
"""

import defusedxml.ElementTree as ET


class XMLParser:
    """Parse Finlex Akoma Ntoso XML"""

    def __init__(self):
        self.ns = {
            "akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0",
            "finlex": "http://data.finlex.fi/schema/finlex",
        }

    def _get_element_text(self, element) -> str:
        """Helper to extract all text from element and preserve order"""
        texts = []

        # Get text from current element
        if element.text and element.text.strip():
            texts.append(element.text.strip())

        # Recursively get text from all children
        for child in element:
            texts.extend(self._get_element_text_recursive(child))

        return " ".join(texts)

    def _get_element_text_recursive(self, element) -> list:
        """Recursively extract text preserving document order"""
        result = []

        # Text inside this element
        if element.text and element.text.strip():
            result.append(element.text.strip())

        # Text from children
        for child in element:
            result.extend(self._get_element_text_recursive(child))

        # Text after this element (tail)
        if element.tail and element.tail.strip():
            result.append(element.tail.strip())

        return result

    def extract_text(self, xml_content: str) -> str:
        """Extract clean Finnish text from XML - ALL sections"""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}") from e

        all_text = []

        # 1. Preface (document number and title)
        preface = root.find(".//akn:preface", self.ns)
        if preface is None:
            preface = root.find(".//{*}preface")
        if preface is not None:
            all_text.append(self._get_element_text(preface))

        # 2. Preamble (enacting clause)
        preamble = root.find(".//akn:preamble", self.ns)
        if preamble is None:
            preamble = root.find(".//{*}preamble")
        if preamble is not None:
            all_text.append(self._get_element_text(preamble))

        # 3. Body (main content)
        body = root.find(".//akn:body", self.ns)
        if body is None:
            body = root.find(".//{*}body")
        if body is not None:
            all_text.append(self._get_element_text(body))

        # 4. Conclusions/Signatures
        conclusions = root.find(".//akn:conclusions", self.ns)
        if conclusions is None:
            conclusions = root.find(".//{*}conclusions")
        if conclusions is not None:
            all_text.append(self._get_element_text(conclusions))

        # 5. Judgment Body (for decisions)
        judgment_body = root.find(".//akn:judgmentBody", self.ns)
        if judgment_body is None:
            judgment_body = root.find(".//{*}judgmentBody")
        if judgment_body is not None:
            all_text.append(self._get_element_text(judgment_body))

        return " ".join(all_text)

    def extract_title(self, xml_content: str, language: str = "fin") -> str:
        """Extract document title from XML

        Args:
            xml_content: XML string
            language: Language code (fin, swe, eng, sme)
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return "Untitled Document"

        # 1. Try finlex:title with specific language (Best for translations)
        # e.g. <finlex:title language="eng">...</finlex:title>
        finlex_title = root.find(f'.//finlex:title[@language="{language}"]', self.ns)
        if finlex_title is None:
            # Try 'lang' attribute as fallback (some files typically use 'language', others 'lang')
            finlex_title = root.find(f'.//finlex:title[@lang="{language}"]', self.ns)

        if finlex_title is not None and finlex_title.text:
            return finlex_title.text.strip()

        # 2. Key Fallback: If requesting English/Sami but not found, try finding ANY English title
        if language == "eng":
            # Try any english title
            finlex_title = root.find('.//finlex:title[@language="en"]', self.ns) or root.find(
                './/finlex:title[@lang="en"]', self.ns
            )
            if finlex_title is not None and finlex_title.text:
                return finlex_title.text.strip()

        # 3. Fallback to Finnish metadata title (often present even in translations)
        if language != "fin":
            finlex_title = root.find('.//finlex:title[@language="fin"]', self.ns) or root.find(
                './/finlex:title[@lang="fin"]', self.ns
            )
            if finlex_title is not None and finlex_title.text:
                return finlex_title.text.strip()

        # 4. Try standard docTitle (used in regular statutes)
        title_elem = root.find(".//akn:preface//akn:docTitle", self.ns)
        if title_elem is None:
            title_elem = root.find(".//{*}preface//{*}docTitle")

        # 5. Try header docTitle (used in judgments)
        if title_elem is None:
            title_elem = root.find(".//akn:header//akn:docTitle", self.ns)
        if title_elem is None:
            title_elem = root.find(".//{*}header//{*}docTitle")

        if title_elem is not None:
            title_text = self._get_element_text(title_elem)
            if title_text:
                return title_text.strip()

        return "Untitled Document"

    def extract_sections(self, xml_content: str) -> list[dict]:
        """Extract structured sections from XML"""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return []

        sections = []

        # Find all <section> elements in body
        section_elements = root.findall(".//akn:body//akn:section", self.ns)
        if not section_elements:
            section_elements = root.findall(".//{*}body//{*}section")

        for section_elem in section_elements:
            # Extract section number from <num> tag
            num_elem = section_elem.find(".//akn:num", self.ns)
            if num_elem is None:
                num_elem = section_elem.find(".//{*}num")

            section_number = None
            if num_elem is not None and num_elem.text:
                section_number = num_elem.text.strip()

            # Extract section heading
            heading_elem = section_elem.find(".//akn:heading", self.ns)
            if heading_elem is None:
                heading_elem = section_elem.find(".//{*}heading")

            heading = None
            if heading_elem is not None:
                heading = self._get_element_text(heading_elem)

            # Extract section content (all text except num and heading)
            content_parts = []
            for child in section_elem:
                tag_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag_name not in ["num", "heading"]:
                    content_parts.append(self._get_element_text(child))

            content = " ".join(content_parts).strip()

            if section_number:  # Only add if we found a section number
                sections.append({"number": section_number, "heading": heading, "content": content})

        return sections

    def _extract_table_text(self, table_elem) -> str:
        """Convert table to readable text format"""
        rows = []

        # Find all table rows
        tr_elements = table_elem.findall(".//{*}tr")

        for tr in tr_elements:
            cells = []
            # Find all cells in row
            td_elements = tr.findall(".//{*}td")

            for td in td_elements:
                cell_text = self._get_element_text(td).strip()
                if cell_text:
                    cells.append(cell_text)

            if cells:
                rows.append(" | ".join(cells))

        return "\n".join(rows)

    def extract_attachments(self, xml_content: str) -> list[dict]:
        """Extract attachments including tables"""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return []

        attachments = []

        # Find attachment containers
        attachment_containers = root.findall('.//{*}hcontainer[@name="attachments"]')

        for container in attachment_containers:
            # Find individual attachments
            attachment_elems = container.findall('.//{*}hcontainer[@name="attachment"]')

            for attach_elem in attachment_elems:
                # Extract heading
                heading_elem = attach_elem.find(".//{*}heading")
                heading = self._get_element_text(heading_elem) if heading_elem is not None else "Liite"

                # Extract content
                content_parts = []
                content_elem = attach_elem.find(".//{*}content")

                if content_elem is not None:
                    # Process all children in content
                    for child in content_elem:
                        tag_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag

                        if tag_name == "table":
                            # Convert table to text
                            table_text = self._extract_table_text(child)
                            if table_text:
                                content_parts.append(table_text)
                        elif tag_name == "p":
                            # Regular paragraph
                            p_text = self._get_element_text(child)
                            if p_text:
                                content_parts.append(p_text)

                if content_parts:
                    attachments.append({"heading": heading, "content": "\n\n".join(content_parts)})

        return attachments

    def extract_pdf_links(self, xml_content: str) -> list[str]:
        """Extract PDF links from document body"""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return []

        links = []
        # Find all PDF links
        a_elems = root.findall(".//akn:body//akn:a", self.ns)
        if not a_elems:
            # Fallback for judgment body
            a_elems = root.findall(".//akn:judgmentBody//akn:a", self.ns)

        # Generic fallback
        if not a_elems:
            a_elems = root.findall(".//{*}a")

        for a in a_elems:
            href = a.get("href", "")
            if href.lower().endswith(".pdf"):
                links.append(href)

        return list(set(links))  # Deduplicate

    def parse(self, xml_content: str, language: str = "fin", document_uri: str = None) -> dict:
        """Parse XML and return structured data

        Args:
            xml_content: XML string
            language: Language code (fin, swe, eng, sme)
            document_uri: Optional URI for fallback extraction
        """
        # Check if this is a PDF-only document
        try:
            root = ET.fromstring(xml_content)
            component_ref = root.find(".//akn:body//akn:componentRef", self.ns)
            if component_ref is not None:
                # PDF-only document
                title = self.extract_title(xml_content, language)
                return {
                    "text": "",
                    "title": title,
                    "sections": [],
                    "attachments": [],
                    "length": 0,
                    "is_pdf_only": True,
                    "pdf_ref": component_ref.get("src", ""),
                }
        except ET.ParseError:
            pass

        # Regular document with text content
        text = self.extract_text(xml_content)
        title = self.extract_title(xml_content, language)
        sections = self.extract_sections(xml_content)
        attachments = self.extract_attachments(xml_content)
        pdf_links = self.extract_pdf_links(xml_content)

        # Combine text with attachment content for full text search
        full_text = text
        if attachments:
            attachment_texts = [f"{att['heading']}\n{att['content']}" for att in attachments]
            full_text = text + "\n\n" + "\n\n".join(attachment_texts)

        return {
            "text": full_text,
            "title": title,
            "sections": sections,
            "attachments": attachments,
            "pdf_links": pdf_links,
            "length": len(full_text),
            "is_pdf_only": False,
        }
