"""Tests for the Prompt Registry module"""

import pytest
from src.prompts import PromptRegistry, PROMPTS


class TestPromptRegistry:
    """Test the PromptRegistry class"""
    
    def test_registry_initialization(self):
        """Test that the global PROMPTS instance is initialized"""
        assert isinstance(PROMPTS, PromptRegistry)
        assert PROMPTS._initialized is True
    
    def test_all_steps_registered(self):
        """Test that all expected steps are registered"""
        steps = PROMPTS.get_all_steps()
        
        expected_steps = [
            "classify",
            "lister",
            "annotate_paper",
            "annotate_solution",
            "question_latex",
            "answer_latex",
            "bbox_correction",
        ]
        
        for step in expected_steps:
            assert step in steps, f"Step '{step}' not registered"
    
    def test_build_classify_prompt(self):
        """Test building the classify prompt"""
        prompt = PROMPTS.build("classify")
        
        assert isinstance(prompt, str)
        assert len(prompt) > 500
        assert "Type1" in prompt
        assert "Type2" in prompt
        assert "exam_type" in prompt
    
    def test_build_lister_prompt_type1(self):
        """Test building the lister prompt for type1"""
        prompt = PROMPTS.build_lister_prompt(exam_type="type1", emphasize=False)
        
        assert isinstance(prompt, str)
        assert len(prompt) > 1000
        assert "Type1 Rules" in prompt
        assert "10(a)" in prompt
        assert "file_search" in prompt
    
    def test_build_lister_prompt_type2(self):
        """Test building the lister prompt for type2"""
        prompt = PROMPTS.build_lister_prompt(exam_type="type2", emphasize=False)
        
        assert isinstance(prompt, str)
        assert len(prompt) > 1000
        assert "Type2 Rules" in prompt
        assert "Question" in prompt
    
    def test_build_lister_prompt_with_emphasis(self):
        """Test building the lister prompt with emphasis"""
        prompt_no_emphasis = PROMPTS.build_lister_prompt(exam_type="type1", emphasize=False)
        prompt_with_emphasis = PROMPTS.build_lister_prompt(exam_type="type1", emphasize=True)
        
        assert len(prompt_with_emphasis) > len(prompt_no_emphasis)
        assert "CRITICAL REMINDER" in prompt_with_emphasis
        assert "CRITICAL REMINDER" not in prompt_no_emphasis
    
    def test_build_question_latex_prompt(self):
        """Test building the question latex prompt"""
        prompt = PROMPTS.build(
            "question_latex",
            question_label="10(a)",
            pages_str="5, 6",
            question_index=1
        )
        
        assert isinstance(prompt, str)
        assert "10(a)" in prompt
        assert "5, 6" in prompt
        assert "LaTeX" in prompt
        assert "PLACEHOLDER" in prompt
    
    def test_build_answer_latex_prompt(self):
        """Test building the answer latex prompt"""
        prompt = PROMPTS.build(
            "answer_latex",
            question_label="10(a)",
            pages_str="2, 3",
            question_index=1
        )
        
        assert isinstance(prompt, str)
        assert "10(a)" in prompt
        assert "2, 3" in prompt
        assert "answer" in prompt.lower()
        assert "LaTeX" in prompt
    def test_build_invalid_step(self):
        """Test that building an invalid step raises ValueError"""
        with pytest.raises(ValueError, match="No prompt registered"):
            PROMPTS.build("invalid_step")
    
    def test_register_custom_step(self):
        """Test registering a custom step"""
        registry = PromptRegistry()
        
        registry.register(
            "custom_step",
            "Section 1: Introduction",
            "Section 2: Details with {variable}",
            "Section 3: Conclusion"
        )
        
        prompt = registry.build("custom_step", variable="test_value")
        
        assert "Section 1" in prompt
        assert "test_value" in prompt
        assert "Section 3" in prompt


class TestPromptContent:
    """Test the content and format of prompts"""
    
    def test_classify_prompt_structure(self):
        """Test the structure of classify prompt"""
        prompt = PROMPTS.build("classify")
        
        # Should contain key sections
        assert "Type1" in prompt
        assert "Type2" in prompt
        assert "Analysis Guidelines" in prompt
        assert "Return JSON" in prompt
    
    def test_lister_prompt_structure(self):
        """Test the structure of lister prompt"""
        prompt = PROMPTS.build_lister_prompt(exam_type="type1", emphasize=False)
        
        # Should contain key sections
        assert "Question Splitting Rules" in prompt
        assert "Your Task" in prompt
        assert "Search Strategy" in prompt
        assert "Critical Rules" in prompt
        assert "Output Format" in prompt
        assert "Quality Check" in prompt
    
    def test_question_latex_prompt_structure(self):
        """Test the structure of question latex prompt"""
        prompt = PROMPTS.build(
            "question_latex",
            question_label="Q1",
            pages_str="0",
            question_index=1
        )
        
        # Should contain key sections
        assert "Your Task" in prompt
        assert "Question Location" in prompt
        assert "Conversion Guidelines" in prompt
        assert "Output Format" in prompt
        assert "Examples" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

