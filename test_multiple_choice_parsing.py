"""
Unit tests for multiple choice question parsing.

Tests the parse_multiple_choice_questions function to ensure it correctly
parses structured text and JSON formats of multiple choice questions.
"""

import pytest
from my_revision_helper.api import parse_multiple_choice_questions


@pytest.mark.unit
class TestMultipleChoiceParsing:
    """Test suite for multiple choice question parsing."""
    
    def test_parse_single_question_structured_format(self):
        """Test parsing a single question in structured text format."""
        content = """QUESTION: What is 2 + 2?
A) 3
B) 4
C) 5
D) 6
CORRECT: B
RATIONALE: Two plus two equals four."""
        
        questions = parse_multiple_choice_questions(content, "test-run-1", 10)
        
        assert len(questions) == 1
        assert questions[0]["id"] == "test-run-1-q1"
        assert questions[0]["text"] == "What is 2 + 2?"
        assert questions[0]["questionStyle"] == "multiple-choice"
        assert questions[0]["options"] == ["3", "4", "5", "6"]
        assert questions[0]["correctAnswerIndex"] == 1  # B is index 1
        assert questions[0]["rationale"] == "Two plus two equals four."
    
    def test_parse_multiple_questions_structured_format(self):
        """Test parsing multiple questions in structured text format."""
        content = """QUESTION: What is 2 + 2?
A) 3
B) 4
C) 5
D) 6
CORRECT: B
RATIONALE: Two plus two equals four.

QUESTION: What is 3 × 5?
A) 12
B) 15
C) 18
D) 20
CORRECT: B
RATIONALE: Three times five equals fifteen."""
        
        questions = parse_multiple_choice_questions(content, "test-run-2", 10)
        
        assert len(questions) == 2
        assert questions[0]["text"] == "What is 2 + 2?"
        assert questions[0]["correctAnswerIndex"] == 1
        assert questions[1]["text"] == "What is 3 × 5?"
        assert questions[1]["correctAnswerIndex"] == 1
        assert questions[0]["id"] == "test-run-2-q1"
        assert questions[1]["id"] == "test-run-2-q2"
    
    def test_parse_question_with_multiline_rationale(self):
        """Test parsing question with multi-line rationale."""
        content = """QUESTION: What is the capital of France?
A) London
B) Berlin
C) Paris
D) Madrid
CORRECT: C
RATIONALE: The capital of France is Paris.
This is a well-known fact.
Paris is located in northern France."""
        
        questions = parse_multiple_choice_questions(content, "test-run-3", 10)
        
        assert len(questions) == 1
        assert questions[0]["correctAnswerIndex"] == 2  # C is index 2
        assert "The capital of France is Paris." in questions[0]["rationale"]
        assert "This is a well-known fact." in questions[0]["rationale"]
        assert "Paris is located in northern France." in questions[0]["rationale"]
    
    def test_parse_question_with_explanation_keyword(self):
        """Test parsing question using EXPLANATION instead of RATIONALE."""
        content = """QUESTION: What is 5 × 5?
A) 20
B) 25
C) 30
D) 35
CORRECT: B
EXPLANATION: Five times five equals twenty-five."""
        
        questions = parse_multiple_choice_questions(content, "test-run-4", 10)
        
        assert len(questions) == 1
        assert questions[0]["rationale"] == "Five times five equals twenty-five."
    
    def test_parse_question_without_rationale(self):
        """Test parsing question without rationale (should use default)."""
        content = """QUESTION: What is 1 + 1?
A) 1
B) 2
C) 3
D) 4
CORRECT: B"""
        
        questions = parse_multiple_choice_questions(content, "test-run-5", 10)
        
        assert len(questions) == 1
        assert questions[0]["rationale"] == "Correct answer selected."
    
    def test_parse_question_with_lowercase_correct(self):
        """Test parsing question with lowercase correct answer letter."""
        content = """QUESTION: What is 2 × 3?
A) 4
B) 5
C) 6
D) 7
CORRECT: c
RATIONALE: Two times three equals six."""
        
        questions = parse_multiple_choice_questions(content, "test-run-6", 10)
        
        assert len(questions) == 1
        assert questions[0]["correctAnswerIndex"] == 2  # C is index 2
    
    def test_parse_all_answer_options(self):
        """Test parsing questions with all possible correct answers (A, B, C, D)."""
        content = """QUESTION: Option A is correct?
A) Yes
B) No
C) Maybe
D) Unknown
CORRECT: A
RATIONALE: A is correct.

QUESTION: Option B is correct?
A) No
B) Yes
C) Maybe
D) Unknown
CORRECT: B
RATIONALE: B is correct.

QUESTION: Option C is correct?
A) No
B) No
C) Yes
D) No
CORRECT: C
RATIONALE: C is correct.

QUESTION: Option D is correct?
A) No
B) No
C) No
D) Yes
CORRECT: D
RATIONALE: D is correct."""
        
        questions = parse_multiple_choice_questions(content, "test-run-7", 10)
        
        assert len(questions) == 4
        assert questions[0]["correctAnswerIndex"] == 0  # A
        assert questions[1]["correctAnswerIndex"] == 1  # B
        assert questions[2]["correctAnswerIndex"] == 2  # C
        assert questions[3]["correctAnswerIndex"] == 3  # D
    
    def test_parse_json_format_single_question(self):
        """Test parsing single question in JSON format (fallback)."""
        content = """[{"question": "What is 2 + 2?", "options": ["3", "4", "5", "6"], "correct": "B", "rationale": "Two plus two equals four."}]"""
        
        questions = parse_multiple_choice_questions(content, "test-run-8", 10)
        
        assert len(questions) == 1
        assert questions[0]["text"] == "What is 2 + 2?"
        assert questions[0]["options"] == ["3", "4", "5", "6"]
        assert questions[0]["correctAnswerIndex"] == 1  # B is index 1
        assert questions[0]["rationale"] == "Two plus two equals four."
    
    def test_parse_json_format_multiple_questions(self):
        """Test parsing multiple questions in JSON format."""
        content = """[
            {"question": "What is 2 + 2?", "options": ["3", "4", "5", "6"], "correct": "B", "rationale": "Four"},
            {"question": "What is 3 × 5?", "options": ["12", "15", "18", "20"], "correct": "B", "explanation": "Fifteen"}
        ]"""
        
        questions = parse_multiple_choice_questions(content, "test-run-9", 10)
        
        assert len(questions) == 2
        assert questions[0]["text"] == "What is 2 + 2?"
        assert questions[0]["rationale"] == "Four"
        assert questions[1]["text"] == "What is 3 × 5?"
        assert questions[1]["rationale"] == "Fifteen"  # Uses "explanation" field
    
    def test_parse_json_format_without_rationale(self):
        """Test parsing JSON format question without rationale."""
        content = """[{"question": "What is 1 + 1?", "options": ["1", "2", "3", "4"], "correct": "B"}]"""
        
        questions = parse_multiple_choice_questions(content, "test-run-10", 10)
        
        assert len(questions) == 1
        assert questions[0]["rationale"] == "Correct answer selected."
    
    def test_parse_empty_content(self):
        """Test parsing empty content returns empty list."""
        questions = parse_multiple_choice_questions("", "test-run-11", 10)
        
        assert questions == []
    
    def test_parse_invalid_format_returns_empty(self):
        """Test parsing invalid format returns empty list."""
        content = "This is not a valid question format."
        
        questions = parse_multiple_choice_questions(content, "test-run-12", 10)
        
        assert questions == []
    
    def test_parse_incomplete_question_ignored(self):
        """Test that incomplete questions (missing parts) are ignored."""
        content = """QUESTION: What is 2 + 2?
A) 3
B) 4
CORRECT: B
RATIONALE: Four

QUESTION: Incomplete question
A) Option 1"""
        
        questions = parse_multiple_choice_questions(content, "test-run-13", 10)
        
        # Only the first complete question should be parsed
        assert len(questions) == 1
        assert questions[0]["text"] == "What is 2 + 2?"
    
    def test_parse_question_with_extra_whitespace(self):
        """Test parsing question with extra whitespace and blank lines."""
        content = """QUESTION: What is 2 + 2?

A) 3
B) 4
C) 5
D) 6

CORRECT: B

RATIONALE: Two plus two equals four.

"""
        
        questions = parse_multiple_choice_questions(content, "test-run-14", 10)
        
        assert len(questions) == 1
        assert questions[0]["text"] == "What is 2 + 2?"
        assert questions[0]["options"] == ["3", "4", "5", "6"]
    
    def test_parse_respects_desired_count(self):
        """Test that parsing respects the desired_count limit for JSON format."""
        content = """[
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct": "A"},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct": "B"},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct": "C"},
            {"question": "Q4", "options": ["A", "B", "C", "D"], "correct": "D"}
        ]"""
        
        questions = parse_multiple_choice_questions(content, "test-run-15", 2)
        
        assert len(questions) == 2
        assert questions[0]["text"] == "Q1"
        assert questions[1]["text"] == "Q2"
    
    def test_parse_question_with_special_characters(self):
        """Test parsing question with special characters in text."""
        content = """QUESTION: What is 2 + 2? (Choose one)
A) 3
B) 4
C) 5
D) 6
CORRECT: B
RATIONALE: The answer is 4 (four)."""
        
        questions = parse_multiple_choice_questions(content, "test-run-16", 10)
        
        assert len(questions) == 1
        assert questions[0]["text"] == "What is 2 + 2? (Choose one)"
        assert "(four)" in questions[0]["rationale"]
    
    def test_parse_question_with_option_text_containing_parentheses(self):
        """Test parsing question where option text contains parentheses."""
        content = """QUESTION: What is the result?
A) Option A (first)
B) Option B (second)
C) Option C (third)
D) Option D (fourth)
CORRECT: B
RATIONALE: Option B is correct."""
        
        questions = parse_multiple_choice_questions(content, "test-run-17", 10)
        
        assert len(questions) == 1
        assert questions[0]["options"][0] == "Option A (first)"
        assert questions[0]["options"][1] == "Option B (second)"
    
    def test_parse_invalid_correct_answer_ignored(self):
        """Test that questions with invalid correct answer (e.g., E, F) are ignored."""
        content = """QUESTION: What is 2 + 2?
A) 3
B) 4
C) 5
D) 6
CORRECT: E
RATIONALE: Invalid answer."""
        
        questions = parse_multiple_choice_questions(content, "test-run-18", 10)
        
        # Question should be ignored because E is not a valid option
        assert len(questions) == 0
    
    def test_parse_question_with_fewer_than_four_options(self):
        """Test parsing question with fewer than 4 options (should still work)."""
        content = """QUESTION: True or False?
A) True
B) False
CORRECT: A
RATIONALE: True is correct."""
        
        questions = parse_multiple_choice_questions(content, "test-run-19", 10)
        
        assert len(questions) == 1
        assert len(questions[0]["options"]) == 2
        assert questions[0]["correctAnswerIndex"] == 0
    
    def test_parse_question_with_more_than_four_options(self):
        """Test parsing question with more than 4 options (should still work)."""
        content = """QUESTION: Pick a number?
A) 1
B) 2
C) 3
D) 4
E) 5
CORRECT: C
RATIONALE: Three is correct."""
        
        questions = parse_multiple_choice_questions(content, "test-run-20", 10)
        
        # Only A-D should be parsed (E) is not recognized
        assert len(questions) == 1
        assert len(questions[0]["options"]) == 4  # Only A-D are parsed
        assert questions[0]["correctAnswerIndex"] == 2  # C is index 2

