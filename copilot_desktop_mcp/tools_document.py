from __future__ import annotations

from pathlib import Path
from typing import Any
from mcp.types import ToolAnnotations
from .tools_workspace import get_workspace_helpers


def register_document_tools(mcp: Any, config: dict[str, Any]) -> None:
    safe_path, _, _, _, _, max_read, _ = get_workspace_helpers(config)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def read_document(path: str, max_chars: int = 20000) -> str:
        """Extract readable text from a PDF (.pdf), Word (.docx), Excel (.xlsx/.xlsm), or PowerPoint (.pptx) file.
        Use this for documents and spreadsheets that cannot be read as plain text."""
        p = safe_path(path, must_exist=True)
        if not p.is_file():
            raise ValueError(f"Path is not a file: {path}")
        if p.stat().st_size > max_read:
            raise ValueError("File exceeds maximum allowed read size")

        suffix = p.suffix.lower()
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(p))
            parts = []
            for i, page in enumerate(reader.pages):
                parts.append(f"--- Page {i + 1} ---\n{page.extract_text() or ''}")
            text_out = "\n\n".join(parts)
        elif suffix == ".docx":
            import docx

            doc = docx.Document(str(p))
            paras = [para.text for para in doc.paragraphs if para.text.strip()]
            for tbl in doc.tables:
                for row in tbl.rows:
                    paras.append(" | ".join(cell.text for cell in row.cells))
            text_out = "\n".join(paras)
        elif suffix in (".xlsx", ".xlsm"):
            import openpyxl

            wb = openpyxl.load_workbook(str(p), data_only=True, read_only=True)
            lines = []
            for ws in wb.worksheets:
                lines.append(f"--- Sheet: {ws.title} ---")
                for row in ws.iter_rows(values_only=True):
                    if any(c is not None for c in row):
                        lines.append(" | ".join("" if c is None else str(c) for c in row))
            text_out = "\n".join(lines)
        elif suffix == ".pptx":
            from pptx import Presentation

            prs = Presentation(str(p))
            lines = []
            for i, slide in enumerate(prs.slides, start=1):
                lines.append(f"--- Slide {i} ---")
                for shape in slide.shapes:
                    if getattr(shape, "has_text_frame", False):
                        for para in shape.text_frame.paragraphs:
                            line = "".join(run.text for run in para.runs) or para.text
                            if line.strip():
                                lines.append(line)
                    if getattr(shape, "has_table", False):
                        for row in shape.table.rows:
                            lines.append(" | ".join(cell.text for cell in row.cells))
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
                    lines.append(f"[Speaker notes] {slide.notes_slide.notes_text_frame.text}")
            text_out = "\n".join(lines)
        else:
            raise ValueError(f"Unsupported document format '{suffix}'. Use read_file for plain text.")

        truncated = len(text_out) > max_chars
        body = text_out[:max_chars]
        result = (
            "=== DOCUMENT CONTENT ===\n"
            f"{body}\n"
            "=== END DOCUMENT CONTENT ==="
        )
        if truncated:
            result += "\n\n[...content truncated by max_chars limit...]"
        return result

    @mcp.tool
    def create_excel(
        path: str,
        sheets: dict[str, list[list[Any]]],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a native Excel workbook (.xlsx).
        `sheets` is a dict mapping sheet names to lists of rows. First row is automatically formatted as a bold header."""
        import openpyxl
        from openpyxl.styles import Font

        if not sheets:
            raise ValueError("At least one sheet definition is required.")

        p = safe_path(path)
        if p.suffix.lower() not in (".xlsx", ".xlsm"):
            raise ValueError("Path must end with .xlsx or .xlsm")
        if p.exists() and not overwrite:
            raise FileExistsError(f"File '{path}' already exists; set overwrite=True to replace.")

        wb = openpyxl.Workbook()
        wb.remove(wb.active)  # remove default sheet
        for name, rows in sheets.items():
            ws = wb.create_sheet(title=str(name)[:31])
            for r_idx, row in enumerate(rows, start=1):
                for c_idx, value in enumerate(row, start=1):
                    cell = ws.cell(row=r_idx, column=c_idx, value=value)
                    if r_idx == 1:
                        cell.font = Font(bold=True)
            for col_cells in ws.columns:
                width = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells) + 2
                ws.column_dimensions[col_cells[0].column_letter].width = min(width, 60)

        p.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(p))
        return {"path": str(p), "sheets": list(sheets.keys()), "status": "success"}

    @mcp.tool
    def create_docx(
        path: str,
        blocks: list[dict[str, Any]],
        title: str = "",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a native Word document (.docx).
        `blocks` is a list of structured content blocks:
        - {"type": "heading", "text": "...", "level": 1-3}
        - {"type": "paragraph", "text": "..."}
        - {"type": "bullets", "items": ["item 1", "item 2"]}
        - {"type": "table", "rows": [["Col 1", "Col 2"], ["Val 1", "Val 2"]]}"""
        import docx

        p = safe_path(path)
        if p.suffix.lower() != ".docx":
            raise ValueError("Path must end with .docx")
        if p.exists() and not overwrite:
            raise FileExistsError(f"File '{path}' already exists; set overwrite=True to replace.")
        if not blocks and not title:
            raise ValueError("Provide at least a title or one content block.")

        doc = docx.Document()
        if title:
            doc.add_heading(title, level=0)

        for b in blocks:
            btype = b.get("type")
            if btype == "heading":
                doc.add_heading(str(b.get("text", "")), level=max(1, min(int(b.get("level", 1)), 3)))
            elif btype == "paragraph":
                doc.add_paragraph(str(b.get("text", "")))
            elif btype == "bullets":
                for item in b.get("items", []):
                    doc.add_paragraph(str(item), style="List Bullet")
            elif btype == "table":
                rows = b.get("rows", [])
                if rows:
                    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
                    table.style = "Light Grid Accent 1"
                    for r_idx, row in enumerate(rows):
                        for c_idx, val in enumerate(row):
                            table.cell(r_idx, c_idx).text = "" if val is None else str(val)
            else:
                raise ValueError(f"Unknown content block type: '{btype}'")

        p.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(p))
        return {"path": str(p), "blocks_written": len(blocks), "status": "success"}

    @mcp.tool
    def create_pptx(
        path: str,
        slides: list[dict[str, Any]],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a native PowerPoint presentation (.pptx).
        `slides` is a list of slide dicts: {"title": str, "bullets": [str, ...], "notes": str (optional)}."""
        from pptx import Presentation

        p = safe_path(path)
        if p.suffix.lower() != ".pptx":
            raise ValueError("Path must end with .pptx")
        if p.exists() and not overwrite:
            raise FileExistsError(f"File '{path}' already exists; set overwrite=True to replace.")
        if not slides:
            raise ValueError("At least one slide is required.")

        prs = Presentation()
        title_slide_layout = prs.slide_layouts[0]
        bullet_slide_layout = prs.slide_layouts[1]

        for i, s in enumerate(slides):
            has_bullets = bool(s.get("bullets"))
            layout = title_slide_layout if (i == 0 and not has_bullets) else bullet_slide_layout
            slide = prs.slides.add_slide(layout)
            if slide.shapes.title:
                slide.shapes.title.text = str(s.get("title", ""))

            if has_bullets and len(slide.shapes.placeholders) > 1:
                tf = slide.shapes.placeholders[1].text_frame
                tf.text = ""
                for b_idx, bullet in enumerate(s.get("bullets", [])):
                    p_elem = tf.add_paragraph() if b_idx > 0 else tf.paragraphs[0]
                    p_elem.text = str(bullet)

            if s.get("notes") and slide.has_notes_slide:
                slide.notes_slide.notes_text_frame.text = str(s["notes"])

        p.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(p))
        return {"path": str(p), "slides_count": len(slides), "status": "success"}

    @mcp.tool
    def create_pdf(
        path: str,
        blocks: list[dict[str, Any]],
        title: str = "",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a clean PDF document using structured blocks (headings, paragraphs, bullet lists, tables)."""
        from fpdf import FPDF

        p = safe_path(path)
        if p.suffix.lower() != ".pdf":
            raise ValueError("Path must end with .pdf")
        if p.exists() and not overwrite:
            raise FileExistsError(f"File '{path}' already exists; set overwrite=True to replace.")
        if not blocks and not title:
            raise ValueError("Provide at least a title or one content block.")

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)

        def write_multicell(h: int, text: str) -> None:
            clean = text.encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(0, h, clean, new_x="LMARGIN", new_y="NEXT")

        if title:
            pdf.set_font("Helvetica", "B", 18)
            write_multicell(10, title)
            pdf.ln(4)
            pdf.set_font("Helvetica", size=12)

        for b in blocks:
            btype = b.get("type")
            if btype == "heading":
                lvl = max(1, min(int(b.get("level", 1)), 3))
                size = {1: 16, 2: 14, 3: 12}.get(lvl, 14)
                pdf.set_font("Helvetica", "B", size)
                write_multicell(8, str(b.get("text", "")))
                pdf.set_font("Helvetica", size=12)
                pdf.ln(1)
            elif btype == "paragraph":
                write_multicell(7, str(b.get("text", "")))
                pdf.ln(1)
            elif btype == "bullets":
                for item in b.get("items", []):
                    write_multicell(7, f"- {item}")
                pdf.ln(1)
            elif btype == "table":
                rows = b.get("rows", [])
                if rows:
                    col_count = len(rows[0])
                    col_w = (pdf.w - pdf.l_margin - pdf.r_margin) / col_count
                    for r_idx, row in enumerate(rows):
                        if r_idx == 0:
                            pdf.set_font("Helvetica", "B", 11)
                        for val in row:
                            txt = ("" if val is None else str(val)).encode("latin-1", "replace").decode("latin-1")
                            pdf.cell(col_w, 8, txt, border=1)
                        pdf.ln()
                        if r_idx == 0:
                            pdf.set_font("Helvetica", size=12)
            else:
                raise ValueError(f"Unknown block type: '{btype}'")

        p.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(p))
        return {"path": str(p), "blocks_written": len(blocks), "status": "success"}

    @mcp.tool
    def pdf_merge(paths: list[str], output_path: str, overwrite: bool = False) -> dict[str, Any]:
        """Merge multiple PDF files into one combined PDF document."""
        from pypdf import PdfWriter

        out = safe_path(output_path)
        if out.exists() and not overwrite:
            raise FileExistsError(f"Target '{output_path}' already exists; set overwrite=True.")
        if len(paths) < 2:
            raise ValueError("At least two source PDF paths are required for merging.")

        writer = PdfWriter()
        for p_str in paths:
            src = safe_path(p_str, must_exist=True)
            writer.append(str(src))

        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return {"path": str(out), "total_pages": len(writer.pages), "files_merged": len(paths), "status": "success"}

    @mcp.tool
    def pdf_split(path: str, output_dir: str) -> dict[str, Any]:
        """Split a multi-page PDF into separate single-page PDF files."""
        from pypdf import PdfReader, PdfWriter

        src = safe_path(path, must_exist=True)
        target_dir = safe_path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        reader = PdfReader(str(src))
        stem = src.stem
        created_files = []

        for i, page in enumerate(reader.pages, start=1):
            writer = PdfWriter()
            writer.add_page(page)
            out_file = target_dir / f"{stem}_page_{i:03d}.pdf"
            with open(out_file, "wb") as f:
                writer.write(f)
            created_files.append(str(out_file))

        return {"output_directory": str(target_dir), "pages_split": len(created_files), "status": "success"}
