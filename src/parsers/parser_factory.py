"""
Parser Factory - auto-detects file type and selects appropriate parser.
"""
from pathlib import Path
from typing import List, Optional, Type
import os

from src.models import ProcessingResult
from src.parsers.base_parser import BaseParser
from src.parsers.generic_csv_parser import GenericCSVParser
from src.parsers.generic_pdf_parser import GenericPDFParser
from src.parsers.robinhood_parser import RobinhoodParser
from src.parsers.chase_parser import ChaseParser
from src.parsers.citi_parser import CitiParser
from src.parsers.pnc_parser import PNCParser


class ParserFactory:
    """Factory for creating appropriate parsers based on file type."""
    
    # Register all available parsers - bank-specific first, generic last
    _parsers: List[Type[BaseParser]] = [
        RobinhoodParser,
        ChaseParser,
        CitiParser,
        PNCParser,
        GenericCSVParser,
        GenericPDFParser,
    ]
    
    @classmethod
    def get_parser(cls, file_path: str, account_id: Optional[str] = None) -> Optional[BaseParser]:
        """
        Get the appropriate parser for a file.
        Returns None if no parser can handle the file.
        """
        path = Path(file_path)
        
        if not path.exists():
            return None
        
        # Collect all parsers that can handle this file with their confidence
        candidates = []
        for parser_class in cls._parsers:
            can_handle, confidence = parser_class.can_handle(file_path)
            if can_handle:
                candidates.append((parser_class, confidence))
        
        if not candidates:
            return None
        
        # Sort by confidence and pick the best
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_parser_class = candidates[0][0]
        
        return best_parser_class(file_path, account_id)
    
    @classmethod
    def parse_file(cls, file_path: str, account_id: Optional[str] = None) -> ProcessingResult:
        """
        Parse a file and return results.
        Auto-detects file type and uses appropriate parser.
        """
        path = Path(file_path)
        
        if not path.exists():
            return ProcessingResult(
                file_path=file_path,
                file_type="unknown",
                institution="unknown",
                account_type="unknown",
                success=False,
                errors=[f"File not found: {file_path}"]
            )
        
        parser = cls.get_parser(file_path, account_id)
        
        if parser is None:
            suffix = path.suffix.lower()
            return ProcessingResult(
                file_path=file_path,
                file_type=suffix,
                institution="unknown",
                account_type="unknown",
                success=False,
                errors=[f"No parser available for file type: {suffix}"]
            )
        
        return parser.parse()
    
    @classmethod
    def parse_files(cls, file_paths: List[str]) -> List[ProcessingResult]:
        """Parse multiple files."""
        results = []
        for file_path in file_paths:
            result = cls.parse_file(file_path)
            results.append(result)
        return results
    
    @classmethod
    def supported_extensions(cls) -> List[str]:
        """Get list of all supported file extensions."""
        return ['.csv', '.pdf', '.xlsx', '.xls']
    
    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """Check if a file type is supported."""
        path = Path(file_path)
        return path.suffix.lower() in cls.supported_extensions()
    
    @classmethod
    def list_parsers(cls) -> List[str]:
        """List all registered parsers."""
        return [p.__name__ for p in cls._parsers]


def process_upload(file_path: str, account_id: Optional[str] = None) -> ProcessingResult:
    """
    Convenience function to process an uploaded file.
    """
    return ParserFactory.parse_file(file_path, account_id)
