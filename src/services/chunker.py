"""
Document Chunker for Finnish Legal Documents
Splits documents by § sections while preserving structure
"""

import re
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class Chunk:
    """Represents a chunk of legal text"""
    text: str
    chunk_index: int
    section_number: str
    metadata: Dict


class LegalDocumentChunker:
    """
    Chunks Finnish legal documents by § sections
    
    Features:
    - Splits by § (section) markers
    - Preserves section numbers for citations
    - Handles edge cases (no sections, very long sections)
    - Maintains document structure
    """
    
    def __init__(
        self, 
        max_chunk_size: int = 1000,
        min_chunk_size: int = 100,
        overlap: int = 50
    ):
        """
        Initialize chunker
        
        Args:
            max_chunk_size: Maximum words per chunk
            min_chunk_size: Minimum words per chunk (merge small sections)
            overlap: Words to overlap between chunks (for context)
        """
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap = overlap
        
        # Regex to find § sections
        # Matches: "§ 1", "§1", "§ 15 a", "1 §", etc.
        self.section_pattern = re.compile(
            r'^\s*§\s*(\d+(?:\s*[a-z])?)',
            re.MULTILINE
        )
    
    def chunk_document(
        self, 
        text: str, 
        document_uri: str,
        document_title: str,
        document_year: int,
        document_type: str = "unknown",
        document_category: str = "unknown",
        language: str = "fin",
        sections: List[Dict] = None,
        attachments: List[Dict] = None
    ) -> List[Chunk]:
        """
        Split document into chunks by § sections and attachments
        
        Args:
            text: Full document text
            document_uri: Finlex URI for citations
            document_title: Document title
            document_year: Year of document
            sections: Structured sections from XML (if available)
            attachments: Structured attachments (if available)
            
        Returns:
            List of Chunk objects
        """
        chunks = []
        chunk_index = 0
        
        # Use structured sections if available
        if sections and len(sections) > 0:
            chunks = self._chunk_by_xml_sections(
                sections,
                document_uri,
                document_title,
                document_year,
                document_type,
                document_category,
                language
            )
            chunk_index = len(chunks)
        else:
            # Fallback: Find all § section markers in text
            text_sections = self._split_by_sections(text)
            
            # If no sections found, split by size
            if len(text_sections) <= 1:
                chunks = self._split_by_size(
                    text, 
                    document_uri, 
                    document_title, 
                    document_year,
                    document_type,
                    document_category,
                    language
                )
                chunk_index = len(chunks)
            else:
                # Process sections into chunks
                for section_num, section_text in text_sections:
                    # Check if section is too large
                    word_count = len(section_text.split())
                    
                    if word_count > self.max_chunk_size:
                        # Split large section into sub-chunks
                        sub_chunks = self._split_large_section(
                            section_text,
                            section_num,
                            chunk_index,
                            document_uri,
                            document_title,
                            document_year,
                            document_type,
                            document_category,
                            language,
                        )
                        chunks.extend(sub_chunks)
                        chunk_index += len(sub_chunks)
                    
                    elif word_count < self.min_chunk_size and chunks:
                        # Merge small section with previous chunk
                        chunks[-1].text += f"\n\n{section_text}"
                        chunks[-1].metadata['merged_sections'].append(section_num)
                    
                    else:
                        # Normal-sized section
                        chunks.append(Chunk(
                            text=section_text.strip(),
                            chunk_index=chunk_index,
                            section_number=section_num,
                            metadata={
                                'document_uri': document_uri,
                                'document_title': document_title,
                                'document_year': document_year,
                                'document_type': document_type,
                                'document_category': document_category,
                                'language': language,
                                'word_count': word_count,
                                'merged_sections': []
                            }
                        ))
                        chunk_index += 1
        
        # Add attachment chunks (tables, appendices)
        if attachments:
            for attachment in attachments:
                attachment_text = f"{attachment['heading']}\n\n{attachment['content']}"
                word_count = len(attachment_text.split())
                
                chunks.append(Chunk(
                    text=attachment_text.strip(),
                    chunk_index=chunk_index,
                    section_number=f"Liite: {attachment['heading']}",
                    metadata={
                        'document_uri': document_uri,
                        'document_title': document_title,
                        'document_year': document_year,
                        'document_type': document_type,
                        'document_category': document_category,
                        'language': language,
                        'word_count': word_count,
                        'merged_sections': [],
                        'is_attachment': True
                    }
                ))
                chunk_index += 1

        return chunks
    
    def _chunk_by_xml_sections(
        self,
        sections: List[Dict],
        document_uri: str,
        document_title: str,
        document_year: int,
        document_type: str,
        document_category: str,
        language: str = "fin"
    ) -> List[Chunk]:
        """
        Chunk document using structured XML sections
        
        Args:
            sections: List of dicts with 'number', 'heading', 'content'
        """
        chunks = []
        chunk_index = 0
        
        # Collect all section numbers for metadata
        all_section_numbers = [s['number'] for s in sections]
        
        for section in sections:
            section_number = section['number']
            section_heading = section.get('heading', '')
            section_content = section['content']
            
            # Combine heading and content
            full_text = f"{section_heading} {section_content}".strip()
            word_count = len(full_text.split())
            
            # Check if section is too large
            if word_count > self.max_chunk_size:
                # Split large section
                sub_chunks = self._split_large_section(
                    full_text,
                    section_number,
                    chunk_index,
                    document_uri,
                    document_title,
                    document_year,
                    document_type,
                    document_category,
                    language,
                )
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)
            else:
                # Section fits in one chunk
                chunks.append(Chunk(
                    text=full_text,
                    chunk_index=chunk_index,
                    section_number=section_number,
                    metadata={
                        'document_uri': document_uri,
                        'document_title': document_title,
                        'document_year': document_year,
                        'document_type': document_type,
                        'document_category': document_category,
                        'language': language,
                        'section_heading': section_heading,
                        'all_sections': all_section_numbers,
                        'word_count': word_count,
                        'merged_sections': []
                    }
                ))
                chunk_index += 1
        
        return chunks
    
    def _split_by_sections(self, text: str) -> List[tuple]:
        """
        Split text by § section markers
        
        Returns:
            List of (section_number, section_text) tuples
        """
        sections = []
        matches = list(self.section_pattern.finditer(text))
        
        if not matches:
            return [("Preamble", text)]
        
        # Extract preamble (text before first section)
        first_match = matches[0]
        preamble = text[:first_match.start()].strip()
        if preamble:
            sections.append(("Preamble", preamble))
        
        # Extract each section
        for i, match in enumerate(matches):
            # Get section number
            section_num = match.group(1).strip()
            section_num = f"§ {section_num}"
            
            # Get section text (from this match to next match or end)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()
            
            sections.append((section_num, section_text))
        
        return sections
    
    def _split_by_size(
        self, 
        text: str, 
        document_uri: str,
        document_title: str,
        document_year: int,
        document_type: str = "unknown",
        document_category: str = "unknown",
        language: str = "fin"
    ) -> List[Chunk]:
        """
        Fallback: Split by size when no § sections found
        """
        words = text.split()
        chunks = []
        chunk_index = 0
        
        for i in range(0, len(words), self.max_chunk_size - self.overlap):
            chunk_words = words[i:i + self.max_chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            chunks.append(Chunk(
                text=chunk_text,
                chunk_index=chunk_index,
                section_number=None,
                metadata={
                    'document_uri': document_uri,
                    'document_title': document_title,
                    'document_year': document_year,
                    'document_type': document_type,
                    'document_category': document_category,
                    'language': language,
                    'word_count': len(chunk_words),
                    'merged_sections': [],
                    'split_method': 'size-based'
                }
            ))
            chunk_index += 1
        
        return chunks
    
    def _split_large_section(
        self,
        section_text: str,
        section_num: str,
        start_index: int,
        document_uri: str,
        document_title: str,
        document_year: int,
        document_type: str = "unknown",
        document_category: str = "unknown",
        language: str = "fin"
    ) -> List[Chunk]:
        """
        Split a large § section into multiple chunks
        """
        words = section_text.split()
        chunks = []
        sub_index = 0
        
        for i in range(0, len(words), self.max_chunk_size - self.overlap):
            chunk_words = words[i:i + self.max_chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            chunks.append(Chunk(
                text=chunk_text,
                chunk_index=start_index + sub_index,
                section_number=f"{section_num} (part {sub_index + 1})",
                metadata={
                    'document_uri': document_uri,
                    'document_title': document_title,
                    'document_year': document_year,
                    'document_type': document_type,
                    'document_category': document_category,
                    'language': language,
                    'word_count': len(chunk_words),
                    'merged_sections': [],
                    'split_method': 'large-section'
                }
            ))
            sub_index += 1
        
        return chunks
