import unittest

from tutor.assessment.printed import recover_printed_stem


class PrintedStemTests(unittest.TestCase):
    def setUp(self):
        self.stem = "What is the new counter value\nafter incrementing 2 by one?"
        self.text = f"Question 1. {self.stem}\nA) 1\nB) 2\nC) 3\nAnswer: C"
        self.options = ("1", "2", "3")

    def test_recovers_exact_printed_stem_without_choices_or_key(self):
        self.assertEqual(recover_printed_stem(self.text, "multiple_choice", self.options), self.stem)

    def test_preserves_code_layout(self):
        stem = "What will this print?\nfor n in [2]:\n    print(n + 1)"
        self.assertEqual(recover_printed_stem(f"{stem}\nA. 2\nB. 3", "multiple_choice", ("2", "3")), stem)

    def test_requires_every_option_in_source_order(self):
        for options in (("1", "2"), ("1", "2", "4"), ("3", "2", "1"), ("1", "2", "3", "4"), ("", "2")):
            with self.subTest(options=options):
                self.assertIsNone(recover_printed_stem(self.text, "multiple_choice", options))

    def test_refuses_ambiguous_excerpts(self):
        for text in (
            "Chapter overview: assignment and counters", "",
            "Question 3. How many loops? " + self.text,
            "1. Find the initial value. 2. What is the final value? A) 1 B) 2 C) 3",
            self.text + "\nQ2. What comes next?",
            "What are the initial and final values? How many updates? A) 1 B) 2 C) 3",
            "A sequence of numbers. A) 1 B) 2 C) 3",
            "Question 1. Pick one. A) 1 C) 2 B) 3",
        ):
            with self.subTest(text=text):
                self.assertIsNone(recover_printed_stem(text, "multiple_choice", self.options))

    def test_true_false_requires_an_explicit_single_directive(self):
        labels = ("True", "False")
        self.assertEqual(
            recover_printed_stem("Question 2. True or false: An increment adds one.\nAnswer: True", "true_false", labels),
            "An increment adds one.",
        )
        self.assertEqual(
            recover_printed_stem("第2题 判断题：计数器加一。\n答案：正确", "true_false", ("正确", "错误")),
            "计数器加一。",
        )
        for text in ("2. An increment adds one.", "True or false: ", "True or false: A. True or false: B.",
                     "True or false: First statement.\nQ2. Second statement."):
            with self.subTest(text=text):
                self.assertIsNone(recover_printed_stem(text, "true_false", labels))


if __name__ == "__main__":
    unittest.main()
