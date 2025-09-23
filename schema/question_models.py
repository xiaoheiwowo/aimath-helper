"""
数学题目数据模型
基于 questions.json 的结构定义
"""

from typing import List, Optional, Union
from dataclasses import dataclass
from enum import Enum


class QuestionType(Enum):
    """题目类型枚举"""
    CHOICE = "choice"
    CALCULATION = "calculation"


@dataclass
class KnowledgePoint:
    """知识点"""
    outline: str
    detail: str


@dataclass
class Choice:
    """选择题选项"""
    id: str  # A, B, C, D, E, F
    content: str
    is_correct: bool
    explanation: str


@dataclass
class SolutionStep:
    """解题步骤"""
    step: str


@dataclass
class QuestionMetadata:
    """题目元数据"""
    category: str  # 格式: "数字.choice" 或 "数字.cal"


@dataclass
class Question:
    """题目模型"""
    id: str  # 格式: "qu_" + UUID
    type: QuestionType
    metadata: QuestionMetadata
    question: str
    knowledge_points: List[KnowledgePoint]
    answer: str
    
    # 选择题特有字段
    choices: Optional[List[Choice]] = None
    
    # 计算题特有字段
    solution_steps: Optional[List[SolutionStep]] = None
    
    def __post_init__(self):
        """验证数据完整性"""
        if self.type == QuestionType.CHOICE and not self.choices:
            raise ValueError("选择题必须包含选项")
        if self.type == QuestionType.CALCULATION and not self.solution_steps:
            raise ValueError("计算题必须包含解题步骤")
        if self.type == QuestionType.CHOICE and self.solution_steps:
            raise ValueError("选择题不应包含解题步骤")
        if self.type == QuestionType.CALCULATION and self.choices:
            raise ValueError("计算题不应包含选项")


@dataclass
class QuestionBank:
    """题目库"""
    questions: List[Question]
    
    def get_questions_by_type(self, question_type: QuestionType) -> List[Question]:
        """根据类型获取题目"""
        return [q for q in self.questions if q.type == question_type]
    
    def get_questions_by_category(self, category: str) -> List[Question]:
        """根据分类获取题目"""
        return [q for q in self.questions if q.metadata.category == category]
    
    def get_question_by_id(self, question_id: str) -> Optional[Question]:
        """根据ID获取题目"""
        return next((q for q in self.questions if q.id == question_id), None)
    
    def get_choice_questions(self) -> List[Question]:
        """获取所有选择题"""
        return self.get_questions_by_type(QuestionType.CHOICE)
    
    def get_calculation_questions(self) -> List[Question]:
        """获取所有计算题"""
        return self.get_questions_by_type(QuestionType.CALCULATION)


# 验证函数
def validate_question(question: Question) -> List[str]:
    """验证题目数据"""
    errors = []
    
    # 验证ID格式
    if not question.id.startswith("qu_") or len(question.id) != 40:
        errors.append(f"题目ID格式错误: {question.id}")
    
    # 验证分类格式
    if not question.metadata.category or "." not in question.metadata.category:
        errors.append(f"分类格式错误: {question.metadata.category}")
    
    # 验证选择题
    if question.type == QuestionType.CHOICE:
        if not question.choices or len(question.choices) < 2:
            errors.append("选择题至少需要2个选项")
        
        # 验证选项ID唯一性
        choice_ids = [c.id for c in question.choices]
        if len(choice_ids) != len(set(choice_ids)):
            errors.append("选项ID重复")
        
        # 验证正确答案存在
        correct_choices = [c for c in question.choices if c.is_correct]
        if len(correct_choices) != 1:
            errors.append("选择题必须有且仅有一个正确答案")
        
        # 验证答案字段与正确选项匹配
        if question.answer not in choice_ids:
            errors.append("答案字段与选项ID不匹配")
    
    # 验证计算题
    if question.type == QuestionType.CALCULATION:
        if not question.solution_steps or len(question.solution_steps) == 0:
            errors.append("计算题必须包含解题步骤")
    
    return errors


def validate_question_bank(bank: QuestionBank) -> List[str]:
    """验证题目库数据"""
    errors = []
    
    # 验证题目ID唯一性
    question_ids = [q.id for q in bank.questions]
    if len(question_ids) != len(set(question_ids)):
        errors.append("题目ID重复")
    
    # 验证每个题目
    for i, question in enumerate(bank.questions):
        question_errors = validate_question(question)
        for error in question_errors:
            errors.append(f"题目 {i+1} ({question.id}): {error}")
    
    return errors
