import base64
from io import BytesIO
import json
from pathlib import Path
import unittest

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from streamlit.testing.v1 import AppTest

from tutor.materials.ingest import PdfInputError, read_pdf_pages


APP = Path(__file__).resolve().parents[1] / "app.py"


def previewed_pdf(app: AppTest) -> tuple[bytes, list[int]]:
    viewer, = app.get("component_instance")
    payload = json.loads(viewer.proto.json_args)
    return base64.b64decode(payload["binary"]), payload["pages_to_render"]


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def make_pdf(*pages: str, password: str | None = None) -> bytes:
    """Build pages with positioned text, as in a PDF containing code samples."""
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Courier"),
    })
    for text in pages:
        page = writer.add_blank_page(width=300, height=400)
        if not text:
            continue
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        commands = []
        for row, line in enumerate(text.splitlines()):
            content = line.lstrip(" ")
            x = 30 + 6 * (len(line) - len(content))
            y = 360 - row * 14
            commands.append(f"BT /F1 10 Tf 1 0 0 1 {x} {y} Tm <{content.encode('ascii').hex()}> Tj ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(commands).encode("ascii"))
        page.replace_contents(stream)
    if password is not None:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PdfPreviewTests(unittest.TestCase):
    def test_page_positions_and_code_indentation(self):
        pages = read_pdf_pages(make_pdf("for n in values:\n    total += n", "", "Last page"))
        self.assertEqual([p.number for p in pages], [1, 2, 3])
        self.assertRegex(pages[0].text, r"for n in values:\s*\n +total \+= n")
        self.assertEqual(pages[1].text.strip(), "")
        self.assertIsNone(pages[1].error)
        self.assertEqual(pages[2].text.strip(), "Last page")

    def test_corrupt_empty_and_locked_inputs(self):
        for data in (b"not a PDF", b"", make_pdf("Protected", password="secret")):
            with self.subTest(size=len(data)), self.assertRaises(PdfInputError):
                read_pdf_pages(data)

    def test_navigation_and_upload_replacement(self):
        app = AppTest.from_file(str(APP)).run()
        self.assertEqual(app.sidebar.file_uploader[0].label, "Upload a PDF")
        self.assertFalse(app.main.file_uploader)
        first = make_pdf("First page", "", "Third page")
        app.sidebar.file_uploader[0].set_value(("lecture.pdf", first, "application/pdf")).run()
        self.assertEqual(previewed_pdf(app), (first, [1]))
        text_panel = app.main.container("extracted_text_panel")
        self.assertGreater(text_panel.proto.height_config.pixel_height, 0)
        self.assertFalse(any(expander.code for expander in app.main.expander))
        self.assertEqual(text_panel.code[0].value.strip(), "First page")
        self.assertTrue(button(app.main, "Previous page").disabled)
        button(app.main, "Next page").click().run()
        self.assertEqual(previewed_pdf(app), (first, [2]))
        self.assertEqual(app.selectbox(key="pdf_page_number").value, 2)
        self.assertTrue(app.main.container("extracted_text_panel").info)
        self.assertFalse(app.main.container("extracted_text_panel").code)
        app.selectbox(key="pdf_page_number").select(3).run()
        self.assertEqual(previewed_pdf(app), (first, [3]))
        self.assertEqual(app.code[0].value.strip(), "Third page")
        self.assertTrue(button(app.main, "Next page").disabled)
        button(app.main, "Previous page").click().run()
        self.assertEqual(previewed_pdf(app), (first, [2]))

        replacement = make_pdf("Replacement", "Next", "End")
        app.file_uploader[0].set_value(("lecture.pdf", replacement, "application/pdf")).run()
        self.assertEqual(previewed_pdf(app), (replacement, [1]))
        self.assertEqual(app.code[0].value.strip(), "Replacement")
        app.file_uploader[0].set_value(("lecture.pdf", b"damaged", "application/pdf")).run()
        self.assertTrue(app.error)
        self.assertFalse(app.code)
        self.assertFalse(app.get("component_instance"))
        app.file_uploader[0].clear().run()
        self.assertFalse(app.error)
        self.assertFalse(app.selectbox)
        self.assertFalse(app.get("component_instance"))
        self.assertFalse(app.exception)
