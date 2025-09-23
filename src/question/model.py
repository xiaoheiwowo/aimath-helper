from typing import List, Optional, Union
from dataclasses import dataclass
from enum import Enum


# class QuestionType(Enum):
#     """题目类型枚举"""

#     CHOICE = "choice"
#     CALCULATION = "calculation"


# class Difficulty(Enum):
#     """难度等级枚举"""

#     EASY = "easy"
#     MEDIUM = "medium"
#     HARD = "hard"


# class AnswerType(Enum):
#     """答案类型枚举"""

#     SINGLE_CHOICE = "single_choice"
#     MULTIPLE_CHOICE = "multiple_choice"
#     EXACT_VALUE = "exact_value"
#     RANGE_VALUE = "range_value"
#     EXPRESSION = "expression"


# @dataclass
# class QuestionInfo:
#     """题目基本信息"""


@dataclass
class Choice:
    """选择题选项"""

    id: str
    content: str
    is_correct: bool
    explanation: str


@dataclass
class SolutionStep:
    """解题步骤"""

    step: str

    # description: str
    # formula: str


@dataclass
class KnowledgePoint:
    """知识点"""

    outline: str
    detail: str


# @dataclass
# class QuestionSettings:
#     """题目设置"""

#     randomize_choices: bool = True
#     multiple_select: bool = False
#     has_none_of_above: bool = False
#     show_hint: bool = True
#     allow_calculator: bool = False
#     require_work_shown: bool = False


# @dataclass
# class ChoiceAnswer:
#     """选择题答案"""

#     type: str
#     value: str
#     explanation: str


# @dataclass
# class CalculationAnswer:
#     """计算题答案"""

#     type: str
#     value: str
#     # unit: Optional[str] = None
#     # tolerance: float = 0.0
#     explanation: str = ""


@dataclass
class Question:
    """题目模型"""

    id: str
    type: str

    question: str

    # metadata
    # subject: str
    # grade: str
    # chapter: str
    # difficulty: str

    knowledge_points: List[KnowledgePoint]

    # answer: Union[ChoiceAnswer, CalculationAnswer]
    choices: Optional[List[Choice]] = None
    solution_steps: Optional[List[SolutionStep]] = None
    # question_settings: Optional[QuestionSettings] = None
