import unittest

from tutor.assessment.concepts import find_concepts
from tutor.assessment.retrieval import Passage
from tutor.planning import StudyAssignment, StudyUnit


SLIDE = """Two memories, one agent
SHORT-TERM · THE CONTEXT
Limited, rots as it grows, paid for on every call.
clear · compact · take notes
LONG-TERM · THE STORE
Facts, events and lessons in a file or database
Survives sessions; only what is retrieved enters the context.
write policy · read policy"""


class ConceptTests(unittest.TestCase):
    def concepts(self, text):
        unit = StudyUnit("u1", "Long-term memory store", "Explain how memory is stored and retrieved.",
                         ("p1",), "Compare the two memories.")
        return [c.text for c in find_concepts(StudyAssignment(unit, "read", ("p1",)), [Passage("p1-c1", "p1", text)])]

    def test_slide_labels_and_keyword_lists_are_not_facts(self):
        found = self.concepts(SLIDE)
        self.assertIn("Survives sessions; only what is retrieved enters the context.", found)
        for label in ("LONG-TERM · THE STORE", "SHORT-TERM · THE CONTEXT", "write policy · read policy"):
            self.assertFalse(any(text.startswith(label) for text in found), label)

    def test_capitalized_sentence_and_formula_remain_facts(self):
        found = self.concepts("Memory\nTHE STORE KEEPS FACTS ACROSS SESSIONS.\nscore = hits / total")
        self.assertIn("THE STORE KEEPS FACTS ACROSS SESSIONS.", found)
        self.assertIn("score = hits / total", found)
