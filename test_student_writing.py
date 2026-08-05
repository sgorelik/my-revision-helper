"""
Tests for separating a printed paper from the child's handwriting.

The tags under test are the ones OCR_SYSTEM_PROMPT in file_processing.py tells
the model to produce, so these fixtures mirror real transcriptions of a
worksheet a child filled in by hand.
"""

import pytest

from my_revision_helper.services.student_writing import (
    has_student_writing,
    looks_self_contained,
    strip_student_writing,
)

# A worksheet done on paper: printed questions, the child's answers written in.
COMPLETED_SCAN = """Mathematics — Fractions and percentages
1. Work out 3/4 of 60.
Answer: [written] 45  ......................... (2)
2. Increase £80 by 15%.
Answer: [written] 92  ......................... (2)
3. Write 0.375 as a fraction in its simplest form.
[written] 375/1000 = 3/8
Answer: ......................... (3)
4. Draw a pie chart showing 6 red, 6 blue, 6 green and 6 yellow counters.
[FIGURE: drawn by student — a circle in four equal sectors, labelled]
Answer: ......................... (3)
5. What is 12% of 250?
[no answer]
Answer: ......................... (2)
"""


@pytest.mark.unit
class TestSpottingHandwriting:
    def test_a_completed_scan_is_recognised(self):
        assert has_student_writing(COMPLETED_SCAN)

    def test_a_blank_paper_is_not(self):
        assert not has_student_writing("1. Work out 3/4 of 60.\nAnswer: ......... (2)")

    def test_nothing_at_all(self):
        assert not has_student_writing(None)
        assert not has_student_writing("")


@pytest.mark.unit
class TestRemovingTheChildsAnswers:
    def test_the_answers_are_gone(self):
        printed = strip_student_writing(COMPLETED_SCAN)

        assert "45" not in printed
        assert "92" not in printed
        assert "375/1000" not in printed

    def test_the_questions_survive(self):
        printed = strip_student_writing(COMPLETED_SCAN)

        assert "Work out 3/4 of 60." in printed
        assert "Increase £80 by 15%." in printed
        assert "What is 12% of 250?" in printed

    def test_the_answer_space_and_marks_survive(self):
        """These are what make the stripped page usable as a worksheet again."""
        printed = strip_student_writing(COMPLETED_SCAN)

        assert "(2)" in printed
        assert "(3)" in printed
        assert "........." in printed

    def test_what_the_child_drew_is_dropped_but_the_question_is_kept(self):
        printed = strip_student_writing(COMPLETED_SCAN)

        assert "drawn by student" not in printed
        assert "four equal sectors" not in printed
        assert "Draw a pie chart" in printed

    def test_an_unanswered_question_leaves_no_trace_of_the_tag(self):
        printed = strip_student_writing(COMPLETED_SCAN)

        assert "[no answer]" not in printed
        assert "12% of 250" in printed

    def test_no_tags_are_left_behind(self):
        printed = strip_student_writing(COMPLETED_SCAN)

        assert "[written]" not in printed
        assert "[FIGURE: drawn" not in printed

    def test_a_figure_printed_on_the_paper_is_kept(self):
        text = (
            "7. The diagram shows a triangle.\n"
            "[FIGURE: printed — a right-angled triangle, base 8 cm, height 6 cm]\n"
            "Answer: [written] 24 cm² ......... (2)\n"
        )
        printed = strip_student_writing(text)

        assert "printed — a right-angled triangle" in printed
        assert "24 cm²" not in printed

    def test_a_paper_with_no_handwriting_comes_back_unchanged(self):
        blank = "1. Work out 3/4 of 60.\nAnswer: ......................... (2)"

        assert strip_student_writing(blank) == blank

    def test_crossed_out_working_goes_with_the_rest(self):
        text = "2. Increase £80 by 15%.\nAnswer: [written] [crossed out] 88 92 ......... (2)"
        printed = strip_student_writing(text)

        assert "88" not in printed
        assert "crossed out" not in printed
        assert "Increase £80 by 15%." in printed

    def test_nothing_at_all(self):
        assert strip_student_writing(None) == ""


@pytest.mark.unit
class TestWhetherTheScanCarriesItsOwnQuestions:
    def test_a_full_worksheet_does(self):
        assert looks_self_contained(COMPLETED_SCAN)

    def test_a_page_of_only_answers_does_not(self):
        """Nothing here says what was asked, so it cannot become a paper."""
        answers_only = (
            "[written] 1. 45\n"
            "[written] 2. 92\n"
            "[written] 3. 3/8\n"
            "[written] 4. 30 red\n"
        )

        assert not looks_self_contained(answers_only)

    def test_answer_scaffolding_alone_does_not(self):
        scaffold = "\n".join(["Answer: ......................... (2)"] * 8)

        assert not looks_self_contained(scaffold)
