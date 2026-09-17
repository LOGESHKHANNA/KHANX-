"""
Centralized text extraction service for multiple document formats.
Supports: PDF, DOCX, PPTX, TXT, CSV, XLSX.

Each format handler is isolated — one format failing does not affect others.
Returns (extracted_text, file_type) tuple.
"""
import os
import csv
import io
from typing import Tuple, Optional

# ── Supported extensions → canonical file type mapping ────────────────────────
EXTENSION_MAP = {
    ".pdf":  "pdf",
    ".docx": "docx",
    ".doc":  "docx",
    ".pptx": "pptx",
    ".ppt":  "pptx",
    ".txt":  "txt",
    ".text": "txt",
    ".md":   "txt",
    ".csv":  "csv",
    ".tsv":  "csv",
    ".xlsx": "xlsx",
    ".xls":  "xlsx",
    ".png":  "image",
    ".jpg":  "image",
    ".jpeg": "image",
    ".webp": "image",
    ".bmp":  "image",
    ".gif":  "image",
}


SUPPORTED_EXTENSIONS = set(EXTENSION_MAP.keys())


def detect_file_type(filename: str) -> Optional[str]:
    """Detect canonical file type from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    return EXTENSION_MAP.get(ext)


def is_supported(filename: str) -> bool:
    """Check if file extension is supported for text extraction."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


def get_supported_extensions_str() -> str:
    """Return a human-readable string of supported extensions."""
    return ", ".join(sorted(SUPPORTED_EXTENSIONS))


async def extract_text(file_path: str, filename: str) -> Tuple[str, str]:
    """Extract text from a document file.

    Args:
        file_path: Absolute or relative path to the saved file on disk.
        filename:  Original filename (used for extension detection).

    Returns:
        Tuple of (extracted_text, file_type).

    Raises:
        ValueError: If the file format is unsupported.
    """
    file_type = detect_file_type(filename)
    if not file_type:
        ext = os.path.splitext(filename)[1]
        raise ValueError(
            f"Unsupported file format '{ext}'. "
            f"Supported: {get_supported_extensions_str()}"
        )

    # Dispatch to format-specific handler
    handler = _HANDLERS.get(file_type)
    if not handler:
        raise ValueError(f"No extraction handler for file type '{file_type}'.")

    text = handler(file_path)
    return text, file_type


# ── Format-specific extraction handlers ──────────────────────────────────────

def _extract_pdf(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF (fitz). Already installed."""
    import fitz  # PyMuPDF
    text_parts = []
    doc = fitz.open(file_path)
    for page_num, page in enumerate(doc, start=1):
        page_text = page.get_text()
        if page_text.strip():
            text_parts.append(f"[Page {page_num}]\n{page_text}")
    doc.close()
    return "\n\n".join(text_parts) if text_parts else ""


def _extract_docx(file_path: str) -> str:
    """Extract text from DOCX using python-docx."""
    from docx import Document
    doc = Document(file_path)
    paragraphs = []

    # Extract paragraphs
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)

    # Extract text from tables
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                paragraphs.append(row_text)

    return "\n\n".join(paragraphs)


def _extract_pptx(file_path: str) -> str:
    """Extract text from PPTX using python-pptx."""
    from pptx import Presentation
    prs = Presentation(file_path)
    slides_text = []

    for slide_num, slide in enumerate(prs.slides, start=1):
        slide_parts = [f"[Slide {slide_num}]"]
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = paragraph.text.strip()
                    if text:
                        slide_parts.append(text)
            # Extract text from tables in slides
            if shape.has_table:
                for row in shape.table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        slide_parts.append(row_text)
        if len(slide_parts) > 1:  # More than just the header
            slides_text.append("\n".join(slide_parts))

    return "\n\n".join(slides_text)


def _extract_txt(file_path: str) -> str:
    """Extract text from plain text / markdown files."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _extract_csv(file_path: str) -> str:
    """Extract text from CSV/TSV files, preserving structure."""
    with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
        # Sniff delimiter (handles both CSV and TSV)
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel  # fallback to standard CSV

        reader = csv.reader(f, dialect)
        rows = []
        for i, row in enumerate(reader):
            if i == 0:
                # Format header row distinctly
                rows.append("Headers: " + " | ".join(row))
            else:
                rows.append(" | ".join(row))
            if i > 500:  # Cap at 500 rows to prevent massive files
                rows.append(f"... (truncated after {i} rows)")
                break

    return "\n".join(rows)


def _extract_xlsx(file_path: str) -> str:
    """Extract text from XLSX/XLS using openpyxl."""
    from openpyxl import load_workbook
    wb = load_workbook(file_path, read_only=True, data_only=True)
    sheets_text = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet_parts = [f"[Sheet: {sheet_name}]"]
        row_count = 0

        for row in ws.iter_rows(values_only=True):
            # Convert each cell to string, skip None
            cells = [str(cell) if cell is not None else "" for cell in row]
            row_text = " | ".join(cells)
            if row_text.strip() and row_text.strip(" |"):
                if row_count == 0:
                    sheet_parts.append("Headers: " + row_text)
                else:
                    sheet_parts.append(row_text)
                row_count += 1
            if row_count > 500:
                sheet_parts.append(f"... (truncated after {row_count} rows)")
                break

        if row_count > 0:
            sheets_text.append("\n".join(sheet_parts))

    wb.close()
    return "\n\n".join(sheets_text)


def _extract_image(file_path: str) -> str:
    """Extract information and visual text from image using PIL."""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            w, h = img.size
            fmt = img.format or "Image"
            mode = img.mode
        fname = os.path.basename(file_path)
        return f"[Uploaded Image File: {fname} | Dimensions: {w}x{h} px | Format: {fmt} | Color Mode: {mode}]\nVisual document image uploaded for analysis."
    except Exception as e:
        return f"[Uploaded Image File: {os.path.basename(file_path)}]\nError opening image: {e}"


# ── Handler dispatch map ─────────────────────────────────────────────────────
_HANDLERS = {
    "pdf":   _extract_pdf,
    "docx":  _extract_docx,
    "pptx":  _extract_pptx,
    "txt":   _extract_txt,
    "csv":   _extract_csv,
    "xlsx":  _extract_xlsx,
    "image": _extract_image,
}

