import re


def normalize_text(text: str) -> str:
    """Normalize text by standardizing line breaks and whitespace.
    
    Converts different line break formats to standard newlines,
    collapses multiple spaces/tabs into single spaces, and reduces
    excessive blank lines.
    
    Args:
        text: Raw text to normalize.
    
    Returns:
        str: Normalized and trimmed text.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
