import pandas as pd
import io
import os

# Monkeypatch pandas to_excel to automatically strip timezones from all datetime columns and index
_original_to_excel = pd.DataFrame.to_excel

def _patched_to_excel(self, *args, **kwargs):
    df_clean = self.copy()
    if isinstance(df_clean.index, pd.DatetimeIndex) and df_clean.index.tz is not None:
        df_clean.index = df_clean.index.tz_localize(None)
        
    for col in df_clean.columns:
        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
            if hasattr(df_clean[col].dt, "tz") and df_clean[col].dt.tz is not None:
                try:
                    df_clean[col] = df_clean[col].dt.tz_localize(None)
                except Exception:
                    try:
                        df_clean[col] = df_clean[col].dt.tz_convert(None).dt.tz_localize(None)
                    except Exception:
                        pass
        else:
            def make_tz_unaware(val):
                if hasattr(val, "tzinfo") and val.tzinfo is not None:
                    try:
                        return val.replace(tzinfo=None)
                    except Exception:
                        return str(val)
                return val
            df_clean[col] = df_clean[col].apply(make_tz_unaware)
            
    return _original_to_excel(df_clean, *args, **kwargs)

pd.DataFrame.to_excel = _patched_to_excel

import urllib.request
import unicodedata
from datetime import datetime
from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# =====================================================================
# UNICODE FONT DOWNLOADER
# =====================================================================

def download_dejavu_font() -> str:
    """
    Downloads the DejaVuSans TrueType font (which supports full Unicode)
    into utils/fonts/ on first use and returns the local path.
    Returns empty string if the download fails (e.g. no internet).
    """
    font_dir = os.path.join(os.path.dirname(__file__), "fonts")
    os.makedirs(font_dir, exist_ok=True)
    font_path = os.path.join(font_dir, "DejaVuSans.ttf")

    # Validate an already-existing file (guard against corrupt previous download)
    if os.path.exists(font_path):
        with open(font_path, "rb") as fh:
            magic = fh.read(4)
        # Valid TrueType: starts with 0x00010000 or 'true' or 'OTTO' (CFF/OTF)
        if magic in (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf"):
            return font_path
        # Corrupt / HTML redirect saved — delete and re-download
        os.remove(font_path)

    # Confirmed direct download URLs (no JavaScript redirect)
    urls = [
        # jsDelivr CDN (reliable, no redirect)
        "https://cdn.jsdelivr.net/npm/@fontsource/source-sans-pro@5.0.12/files/source-sans-pro-all-400-normal.woff",
        # GitHub releases (direct binary asset link)
        "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip",
    ]

    # Best bet: use the fontsource CDN which serves a real TTF via urllib
    dejavu_direct = (
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/refs/heads/master/ttf/DejaVuSans.ttf"
    )

    try:
        req = urllib.request.Request(
            dejavu_direct,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/octet-stream"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        # Validate magic bytes before saving
        if data[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf") and len(data) > 100_000:
            with open(font_path, "wb") as fh:
                fh.write(data)
            return font_path
    except Exception:
        pass

    return ""



# =====================================================================
# TEXT CLEANING HELPER
# =====================================================================

def clean_text(text) -> str:
    """
    Normalises unicode and replaces characters that cause
    FPDFUnicodeEncodingException even with DejaVu, or that look wrong
    on export (smart quotes, em-dash, rupee symbol, etc.).
    """
    if not text:
        return ""
    text = str(text)
    text = unicodedata.normalize("NFKC", text)
    replacements = {
        "\u2014": "-",     # em dash  —
        "\u2013": "-",     # en dash  –
        "\u2018": "'",     # left single quote  '
        "\u2019": "'",     # right single quote  '
        "\u201C": '"',     # left double quote  "
        "\u201D": '"',     # right double quote  "
        "\u2026": "...",   # ellipsis  …
        "\u2022": "-",     # bullet  •
        "\u20B9": "Rs.",   # rupee sign  ₹
        "\u00A0": " ",     # non-breaking space
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
        
    # Strip emojis and symbols that DejaVu does not support
    clean_chars = []
    for c in text:
        cp = ord(c)
        if cp > 0xFFFF:
            continue
        if 0x2600 <= cp <= 0x27BF:
            continue
        clean_chars.append(c)
    return "".join(clean_chars)



# =====================================================================
# BACKWARDS COMPATIBILITY EXPORTS
# =====================================================================

def sanitize_df_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures that all datetime columns are timezone-unaware before exporting to Excel.
    """
    df_clean = df.copy()
    for col in df_clean.columns:
        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
            try:
                df_clean[col] = df_clean[col].dt.tz_localize(None)
            except TypeError:
                try:
                    df_clean[col] = df_clean[col].dt.tz_convert(None).dt.tz_localize(None)
                except Exception:
                    pass
        else:
            def make_tz_unaware(val):
                if hasattr(val, "tzinfo") and val.tzinfo is not None:
                    try:
                        return val.replace(tzinfo=None)
                    except Exception:
                        return str(val)
                return val
            df_clean[col] = df_clean[col].apply(make_tz_unaware)
    return df_clean

def export_to_excel(data: list[dict]) -> bytes:
    """
    Exports a list of dictionaries to an Excel file (bytes).
    """
    if not data:
        data = [{"Message": "No data available to export"}]
    df = pd.DataFrame(data)
    df = sanitize_df_for_excel(df)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return output.getvalue()


def export_to_pdf(title: str, content: list[str]) -> bytes:
    """
    Generates a simple PDF from text paragraphs using DejaVu font.
    Falls back to plain-text bytes if the font is unavailable.
    """
    font_path = download_dejavu_font()
    if not font_path:
        # Fallback to plain text
        txt = f"{title}\n{'='*len(title)}\n\n" + "\n\n".join(content)
        return txt.encode("utf-8")

    pdf = FPDF()
    pdf.add_font("DejaVu", "", font_path)
    pdf.add_font("DejaVu", "B", font_path)
    pdf.add_page()
    pdf.set_font("DejaVu", style="B", size=16)
    pdf.cell(0, 10, clean_text(title), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)
    pdf.set_font("DejaVu", size=12)
    for paragraph in content:
        pdf.multi_cell(0, 10, clean_text(paragraph))
        pdf.ln(5)
    pdf_bytes = pdf.output()
    return bytes(pdf_bytes)


# =====================================================================
# PREMIUM HOD PDF REPORT GENERATOR & HELPERS
# =====================================================================

class DepartmentReportPDF(FPDF):
    """
    Custom FPDF subclass implementing branded headers and footers on every
    page, using the DejaVu Unicode font so all characters render correctly.
    """

    def __init__(self, title: str, generated_by: str, font_path: str):
        super().__init__()
        self.report_title = clean_text(title)
        self.generated_by = clean_text(generated_by)
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Register all three variants (fpdf2 maps "" / "B" / "I" separately)
        self.add_font("DejaVu", "", font_path)
        self.add_font("DejaVu", "B", font_path)
        self.add_font("DejaVu", "I", font_path)

    def header(self):
        self.set_font("DejaVu", "B", 10)
        self.set_text_color(100, 110, 120)
        self.cell(
            0, 5,
            "Department of Artificial Intelligence & Machine Learning",
            new_x="LMARGIN", new_y="NEXT", align="L",
        )
        self.set_font("DejaVu", "B", 14)
        self.set_text_color(15, 23, 42)
        self.cell(0, 7, self.report_title, new_x="LMARGIN", new_y="NEXT", align="L")
        self.set_font("DejaVu", "I", 9)
        self.set_text_color(148, 163, 184)
        self.cell(
            0, 5,
            f"Generated: {self.generated_at} | By: {self.generated_by}",
            new_x="LMARGIN", new_y="NEXT", align="L",
        )
        self.ln(3)
        self.set_draw_color(203, 213, 225)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(
            0, 10,
            f"Confidential - AIML Dept | Page {self.page_no()}/{{nb}}",
            align="C",
        )


def render_pdf_table(pdf: FPDF, table_rows: list[list[str]]):
    """
    Draws a standard bordered table grid from parsed markdown columns.
    """
    if not table_rows:
        return
    cols_count = max(len(row) for row in table_rows)
    page_width = 190.0
    col_width = page_width / cols_count

    for row_idx, row in enumerate(table_rows):
        if row_idx == 0:
            pdf.set_font("DejaVu", style="B", size=9)
            pdf.set_fill_color(241, 245, 249)
        else:
            pdf.set_font("DejaVu", style="", size=9)
            pdf.set_fill_color(255, 255, 255)

        max_h = 7
        for col_idx in range(cols_count):
            val = row[col_idx].strip() if col_idx < len(row) else ""
            val = clean_text(val.replace("**", "").replace("__", ""))
            pdf.cell(col_width, max_h, val, border=1, align="C", fill=True)
        pdf.ln(max_h)
    pdf.ln(4)


def write_markdown_line(pdf: FPDF, line_text: str, default_size: int = 10):
    """
    Parses headings, bold text segments, and list items for PDF rendering.
    """
    text = line_text.strip()
    if not text:
        return

    # Headings
    if text.startswith("#"):
        hashes = len(text) - len(text.lstrip("#"))
        heading_text = clean_text(text.lstrip("#").strip())
        size_boost = 4 if hashes == 1 else (3 if hashes == 2 else 2)
        pdf.set_font("DejaVu", style="B", size=default_size + size_boost)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(0, 8, heading_text)
        pdf.ln(2)
        return

    # Bullet list items
    is_bullet = text.startswith("- ") or text.startswith("* ")
    if is_bullet:
        text = text[2:].strip()

    pdf.set_font("DejaVu", style="", size=default_size)
    pdf.set_text_color(51, 65, 85)

    if is_bullet:
        pdf.set_x(15)
        pdf.write(5, "-  ")

    # Inline bold (**text**)
    parts = text.split("**")
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            pdf.set_font("DejaVu", style="B", size=default_size)
        else:
            pdf.set_font("DejaVu", style="", size=default_size)
        pdf.write(5, clean_text(part))

    pdf.ln(6)


def _plain_text_fallback(title: str, content_markdown: str, generated_by: str) -> bytes:
    """Returns a UTF-8 plain-text version when PDF generation is unavailable."""
    lines = [
        "PDF generation unavailable - plain text version",
        "=" * 60,
        f"Department of Artificial Intelligence & Machine Learning",
        f"Report: {title}",
        f"Generated by: {generated_by}",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        content_markdown,
    ]
    return "\n".join(lines).encode("utf-8")


def generate_pdf_report(title: str, content_markdown: str, metadata: dict) -> bytes:
    """
    Generates a branded PDF report using DejaVu Unicode font.

    Returns:
        bytes — Either PDF bytes (starts with b'%PDF') or UTF-8 plain-text
                bytes if the font could not be downloaded.  Callers can
                detect the type with:
                    is_pdf = data[:4] == b'%PDF'
    """
    generated_by = metadata.get("generated_by", "Head of Department")

    try:
        font_path = download_dejavu_font()
        if not font_path:
            raise RuntimeError("DejaVu font not available (no internet connection).")

        pdf = DepartmentReportPDF(title, generated_by, font_path)
        pdf.alias_nb_pages()
        pdf.set_margins(10, 10, 10)
        pdf.add_page()

        lines = content_markdown.split("\n")
        table_rows: list[list[str]] = []
        in_table = False

        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("|") and line_stripped.endswith("|"):
                # Skip markdown table separator rows (---|---|---)
                if all(c in "-:| " for c in line_stripped.replace("|", "")):
                    continue
                cols = [col.strip() for col in line_stripped.split("|")[1:-1]]
                table_rows.append(cols)
                in_table = True
            else:
                if in_table:
                    render_pdf_table(pdf, table_rows)
                    table_rows = []
                    in_table = False
                if line_stripped:
                    write_markdown_line(pdf, line, default_size=10)
                else:
                    pdf.ln(3)

        # Flush remaining table rows
        if in_table and table_rows:
            render_pdf_table(pdf, table_rows)

        pdf_bytes = pdf.output()
        return bytes(pdf_bytes)

    except Exception:
        # Any failure (font download, FPDF error, encoding issue) → plain text
        return _plain_text_fallback(title, content_markdown, generated_by)


# =====================================================================
# PREMIUM EXCEL REPORT GENERATORS
# =====================================================================

def generate_excel_report(records_dict: dict, sheet_name: str = None) -> bytes:
    """
    Generates a premium styled multi-sheet Excel report with frozen panes,
    merged department header rows, and zebra-striped data rows.
    """
    wb = Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)

    blue_fill   = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    zebra_fill  = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    white_font  = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font   = Font(name="Calibri", size=11, bold=True)
    normal_font = Font(name="Calibri", size=11)

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # --- Summary sheet ---
    summary_ws = wb.create_sheet(title="Summary")
    summary_ws.merge_cells("A1:C1")
    summary_ws["A1"] = "Department of Artificial Intelligence & Machine Learning"
    summary_ws["A1"].font = white_font
    summary_ws["A1"].fill = blue_fill
    summary_ws["A1"].alignment = Alignment(horizontal="center")

    summary_ws["A2"] = "Academic Year Activity Report Summary"
    summary_ws["A2"].font = bold_font
    summary_ws["C2"] = f"Export Date: {datetime.now().strftime('%Y-%m-%d')}"
    summary_ws["C2"].font = bold_font

    for col_letter, header_val in [("A", "Department Category"), ("B", "Total Records")]:
        cell = summary_ws[f"{col_letter}3"]
        cell.value = header_val
        cell.font = bold_font
        cell.fill = header_fill
        cell.border = thin_border

    row_num = 4
    for key, val_list in records_dict.items():
        c1 = summary_ws.cell(row=row_num, column=1, value=str(key))
        c1.font = normal_font
        c1.border = thin_border
        c2 = summary_ws.cell(row=row_num, column=2, value=len(val_list))
        c2.font = normal_font
        c2.border = thin_border
        if row_num % 2 == 1:
            c1.fill = zebra_fill
            c2.fill = zebra_fill
        row_num += 1

    for col in summary_ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        summary_ws.column_dimensions[col_letter].width = max(max_len + 3, 15)
    summary_ws.freeze_panes = "A4"

    # --- Individual collection sheets ---
    for cat_name, recs in records_dict.items():
        ws = wb.create_sheet(title=str(cat_name)[:30])

        if not recs:
            headers   = ["Message"]
            data_rows = [["No submissions recorded"]]
        else:
            all_keys = []
            for r in recs:
                for k in r.keys():
                    if k not in all_keys and k != "doc_id":
                        all_keys.append(k)
            headers   = all_keys
            data_rows = [[r.get(h, "") for h in headers] for r in recs]

        last_col_letter = get_column_letter(max(len(headers), 3))

        ws.merge_cells(f"A1:{last_col_letter}1")
        ws["A1"] = "Department of Artificial Intelligence & Machine Learning"
        ws["A1"].font  = white_font
        ws["A1"].fill  = blue_fill
        ws["A1"].alignment = Alignment(horizontal="center")

        ws["A2"] = f"Collection: {cat_name}"
        ws["A2"].font = bold_font
        ws["B2"] = f"Export Date: {datetime.now().strftime('%Y-%m-%d')}"
        ws["B2"].font = bold_font

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col_idx, value=str(h).replace("_", " ").title())
            cell.font   = bold_font
            cell.fill   = header_fill
            cell.border = thin_border

        for r_idx, row in enumerate(data_rows, 4):
            for c_idx, val in enumerate(row, 1):
                val_str = val.strftime("%Y-%m-%d %H:%M:%S") if isinstance(val, datetime) else str(val)
                cell = ws.cell(row=r_idx, column=c_idx, value=val_str)
                cell.font   = normal_font
                cell.border = thin_border
                if r_idx % 2 == 1:
                    cell.fill = zebra_fill

        ws.freeze_panes = "A4"

        for col in ws.columns:
            max_len = max(
                (len(str(cell.value or "")) for cell in col if cell.row != 1),
                default=0,
            )
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    excel_out = io.BytesIO()
    wb.save(excel_out)
    return excel_out.getvalue()


def export_my_records_excel(records: dict, user_name: str, user_id: str) -> bytes:
    """
    Creates a personal Excel file for a faculty/student with their records.
    """
    wb = Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)

    blue_fill   = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    zebra_fill  = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    white_font  = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font   = Font(name="Calibri", size=11, bold=True)
    normal_font = Font(name="Calibri", size=11)

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    records_dict = {"My Submissions": records} if isinstance(records, list) else records

    for sheet_name, rec_list in records_dict.items():
        ws = wb.create_sheet(title=str(sheet_name)[:30])

        if not rec_list:
            headers   = ["Message"]
            data_rows = [["No personal records found"]]
        else:
            all_keys = []
            for r in rec_list:
                for k in r.keys():
                    if k not in all_keys and k != "doc_id":
                        all_keys.append(k)
            headers   = all_keys
            data_rows = [[r.get(h, "") for h in headers] for r in rec_list]

        last_col_letter = get_column_letter(max(len(headers), 3))

        ws.merge_cells(f"A1:{last_col_letter}1")
        ws["A1"] = "Department of Artificial Intelligence & Machine Learning"
        ws["A1"].font  = white_font
        ws["A1"].fill  = blue_fill
        ws["A1"].alignment = Alignment(horizontal="center")

        ws["A2"] = f"Personal Export: {user_name} ({user_id})"
        ws["A2"].font = bold_font
        ws["B2"] = f"Export Date: {datetime.now().strftime('%Y-%m-%d')}"
        ws["B2"].font = bold_font

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col_idx, value=str(h).replace("_", " ").title())
            cell.font   = bold_font
            cell.fill   = header_fill
            cell.border = thin_border

        for r_idx, row in enumerate(data_rows, 4):
            for c_idx, val in enumerate(row, 1):
                val_str = val.strftime("%Y-%m-%d %H:%M:%S") if isinstance(val, datetime) else str(val)
                cell = ws.cell(row=r_idx, column=c_idx, value=val_str)
                cell.font   = normal_font
                cell.border = thin_border
                if r_idx % 2 == 1:
                    cell.fill = zebra_fill

        ws.freeze_panes = "A4"

        for col in ws.columns:
            max_len = max(
                (len(str(cell.value or "")) for cell in col if cell.row != 1),
                default=0,
            )
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    excel_out = io.BytesIO()
    wb.save(excel_out)
    return excel_out.getvalue()
