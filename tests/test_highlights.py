import unittest

from tests.test_pdf_preview import make_pdf
from tutor.materials.highlights import PageLines, TextLine, page_lines, quote_boxes


class QuoteBoxTests(unittest.TestCase):
    def setUp(self):
        # Courier 10 pt: 6 pt per character, lines 14 pt apart from y = 360, on a 300 x 400 page.
        self.page = page_lines(make_pdf("Intro line here.\nThe base case stops\nthe recursion early.\nOther."), 1)

    def test_a_quote_over_two_lines_gets_a_box_on_each(self):
        boxes = quote_boxes(self.page, "The base case stops the recursion")
        self.assertEqual(len(boxes), 2)
        first, second = boxes
        self.assertAlmostEqual(first.x, 30, delta=1)
        self.assertAlmostEqual(first.width, 19 * 6, delta=2)
        # Only the words of the quote: "the recursion", not " early."
        self.assertAlmostEqual(second.width, 13 * 6, delta=2)
        # From the top of the page; the second line is 14 pt lower.
        self.assertAlmostEqual(second.y - first.y, 14, delta=0.5)
        self.assertTrue(0 < first.y < 400 - 346)

    def test_symbols_case_and_escapes_do_not_matter(self):
        self.assertTrue(quote_boxes(self.page, "the BASE case — stops"))
        self.assertTrue(quote_boxes(self.page, "Intro line here\\u002e"))

    def test_a_quote_not_on_the_page_gets_no_box(self):
        self.assertEqual(quote_boxes(self.page, "The base case returns"), [])
        self.assertEqual(quote_boxes(self.page, ""), [])

    def test_words_of_the_other_column_may_sit_in_between(self):
        page = PageLines((
            TextLine("Each call adds   Costs grow", 0, 270, 300, 10),
            TextLine("a frame to   with every turn", 0, 270, 286, 10),
            TextLine("the stack.", 0, 100, 272, 10),
        ), 0, 400)
        self.assertEqual(len(quote_boxes(page, "Each call adds a frame to the stack.")), 3)

    def test_chinese_quotes_match_inside_a_run_of_characters(self):
        page = PageLines((TextLine("递归函数需要一个基本情况才能停止。", 0, 170, 300, 10),), 0, 400)
        self.assertEqual(len(quote_boxes(page, "需要一个基本情况")), 1)

    def test_a_page_that_cannot_be_read_has_no_lines(self):
        self.assertEqual(page_lines(b"not a pdf", 1).lines, ())
        self.assertEqual(page_lines(make_pdf(""), 1).lines, ())


if __name__ == "__main__":
    unittest.main()
