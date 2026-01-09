"""
XML Parser for Finlex Documents
"""

import xml.etree.ElementTree as ET
from typing import Dict, List


class XMLParser:
    """Parse Finlex Akoma Ntoso XML"""
    
    def __init__(self):
        self.ns = {'akn': 'http://docs.oasis-open.org/legaldocml/ns/akn/3.0'}
    
    def _get_element_text(self, element) -> str:
        """Helper to extract all text from element and preserve order"""
        texts = []
        
        # Get text from current element
        if element.text and element.text.strip():
            texts.append(element.text.strip())
        
        # Recursively get text from all children
        for child in element:
            texts.extend(self._get_element_text_recursive(child))
        
        return ' '.join(texts)

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
            raise ValueError(f"Invalid XML: {e}")
        
        all_text = []
        
        # 1. Preface (document number and title)
        preface = root.find('.//akn:preface', self.ns)
        if preface is None:
            preface = root.find('.//{*}preface')
        if preface is not None:
            all_text.append(self._get_element_text(preface))
        
        # 2. Preamble (enacting clause)
        preamble = root.find('.//akn:preamble', self.ns)
        if preamble is None:
            preamble = root.find('.//{*}preamble')
        if preamble is not None:
            all_text.append(self._get_element_text(preamble))
        
        # 3. Body (main content)
        body = root.find('.//akn:body', self.ns)
        if body is None:
            body = root.find('.//{*}body')
        if body is not None:
            all_text.append(self._get_element_text(body))
        
        # 4. Conclusions/Signatures
        conclusions = root.find('.//akn:conclusions', self.ns)
        if conclusions is None:
            conclusions = root.find('.//{*}conclusions')
        if conclusions is not None:
            all_text.append(self._get_element_text(conclusions))
        
        return ' '.join(all_text)
    
    def parse(self, xml_content: str) -> Dict:
        """Parse XML and return structured data"""
        text = self.extract_text(xml_content)
        
        return {
            "text": text,
            "length": len(text)
        }