"""Erzeugt Beispiel-Dokumente fuer die CV-Auswertungstests, ohne binaere
Fixtures ins Repo einzuchecken: ein Text-PDF (handgeschriebenes Minimal-PDF),
ein mehrseitiges gescanntes PDF (nur Bilder, kein Text-Layer), ein JPG und
eine .doc-Datei (OLE2-Header des alten Word-Formats)."""

from io import BytesIO

from PIL import Image, ImageDraw

DOC_OLE2_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 512


def make_text_pdf(pages: list[str]) -> bytes:
    """Text-PDF mit einem echten Text-Layer (Helvetica), eine Seite je Eintrag."""
    page_count = len(pages)
    kids = " ".join(f"{4 + 2 * index} 0 R" for index in range(page_count))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, text in enumerate(pages):
        content_id = 5 + 2 * index
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        words = text.split()
        lines = [" ".join(words[i : i + 12]) for i in range(0, len(words), 12)]
        stream = "BT /F1 10 Tf 40 800 Td 12 TL " + " ".join(f"({line}) Tj T*" for line in lines)
        stream += " ET"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream".encode())

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(output)


def _page_image(label: str, size: tuple[int, int] = (600, 800)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).text((40, 40), label, fill="black")
    return image


def make_scanned_pdf(page_count: int) -> bytes:
    """Mehrseitiges PDF, dessen Seiten reine Bilder sind - pypdf findet
    keinen Text, genau wie bei einem eingescannten Lebenslauf."""
    images = [_page_image(f"Seite {number + 1}") for number in range(page_count)]
    buffer = BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:], resolution=100)
    return buffer.getvalue()


def make_jpg(size: tuple[int, int] = (600, 800)) -> bytes:
    buffer = BytesIO()
    _page_image("Lebenslauf", size).save(buffer, format="JPEG")
    return buffer.getvalue()


LONG_CV_TEXT = " ".join(
    "Berufserfahrung Steuerberater Kanzlei Jahresabschluss Umsatzsteuer Mandantenbetreuung"
    for _ in range(12)
)
