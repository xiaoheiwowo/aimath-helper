import os
import json
import sys
from typing import List, Dict, Any
import random

# 添加当前目录到路径，支持直接运行
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from model import Question, Choice, SolutionStep, KnowledgePoint


class QuestionBank:
    """题目库"""

    def __init__(self):
        self.questions = self.load_questions()

    def load_questions(self) -> List[Question]:
        """从 JSON 文件加载题目数据并解析为 Question 对象"""
        file_name = os.path.join(os.path.dirname(__file__), "questions.json")
        with open(file_name, "r", encoding="utf-8") as f:
            data = json.load(f)

        questions = []
        for q_data in data.get("questions", []):
            question = self._parse_question(q_data)
            questions.append(question)

        return questions

    def _parse_question(self, q_data: Dict[str, Any]) -> Question:
        """解析单个题目数据"""
        # 解析知识点
        knowledge_points = []
        for kp_data in q_data.get("knowledge_points", []):
            if isinstance(kp_data, str):
                # 简单字符串格式
                knowledge_points.append(KnowledgePoint(outline=kp_data, detail=""))
            elif isinstance(kp_data, dict):
                # 对象格式
                knowledge_points.append(KnowledgePoint(
                    outline=kp_data.get("outline", ""),
                    detail=kp_data.get("detail", "")
                ))

        # 解析选择题选项
        choices = None
        if q_data.get("choices"):
            choices = []
            for choice_data in q_data["choices"]:
                choices.append(Choice(
                    id=choice_data["id"],
                    content=choice_data["content"],
                    is_correct=choice_data["is_correct"],
                    explanation=choice_data.get("explanation", "")  # 使用get方法安全获取
                ))

        # 解析解题步骤
        solution_steps = None
        if q_data.get("solution_steps"):
            solution_steps = []
            for step_data in q_data["solution_steps"]:
                solution_steps.append(SolutionStep(
                    step=step_data["step"]
                ))

        return Question(
            id=str(q_data["id"]),
            type=q_data["type"],
            question=q_data["question"],
            knowledge_points=knowledge_points,
            choices=choices,
            solution_steps=solution_steps
        )

    def get_question(self, id: str) -> Question:
        """根据 ID 获取题目"""
        return next((q for q in self.questions if q.id == id), None)

    def get_random_questions(self, count: int) -> List[Question]:
        """获取随机题目"""
        return random.sample(self.questions, count)

    def get_questions_by_type(self, question_type: str) -> List[Question]:
        """根据类型获取题目"""
        return [q for q in self.questions if q.type == question_type]

    def get_questions_by_knowledge_point(self, knowledge_point: str) -> List[Question]:
        """根据知识点获取题目"""
        return [q for q in self.questions 
                if any(kp.outline == knowledge_point for kp in q.knowledge_points)]

    def get_questions_by_knowledge_points(
        self, knowledge_points: List[str]
    ) -> List[Question]:
        """根据多个知识点获取题目"""
        matching_questions = []
        for q in self.questions:
            for kp in q.knowledge_points:
                # 检查精确匹配
                if kp.outline in knowledge_points:
                    matching_questions.append(q)
                    break
                # 检查部分匹配（更灵活的匹配）
                kp_clean = (
                    kp.outline.replace("的", "").replace("律", "").replace("定", "")
                )
                for target_kp in knowledge_points:
                    target_clean = (
                        target_kp.replace("的", "").replace("律", "").replace("定", "")
                    )
                    # 检查是否包含关键词
                    if (
                        ("加法" in kp_clean and "加法" in target_clean)
                        or ("运算" in kp_clean and "运算" in target_clean)
                        or ("法则" in kp_clean and "法则" in target_clean)
                    ):
                        matching_questions.append(q)
                        break
                if q in matching_questions:
                    break
        return matching_questions

    def get_random_questions_by_knowledge_points(
        self,
        knowledge_points: List[str],
        choice_count: int = 2,
        calculation_count: int = 2,
    ) -> List[Question]:
        """根据知识点随机选择指定数量的题目"""
        # 获取所有匹配知识点的题目
        matching_questions = self.get_questions_by_knowledge_points(knowledge_points)

        # 按类型分组
        choice_questions = [q for q in matching_questions if q.type == "choice"]
        calculation_questions = [
            q for q in matching_questions if q.type == "calculation"
        ]

        # 随机选择指定数量的题目
        selected_questions = []

        if choice_questions:
            selected_choices = random.sample(
                choice_questions, min(choice_count, len(choice_questions))
            )
            selected_questions.extend(selected_choices)

        if calculation_questions:
            selected_calculations = random.sample(
                calculation_questions,
                min(calculation_count, len(calculation_questions)),
            )
            selected_questions.extend(selected_calculations)

        return selected_questions

    def get_all_questions(self) -> List[Question]:
        """获取所有题目"""
        return self.questions.copy()

if __name__ == "__main__":
    qb = QuestionBank()
    qb.load_questions()
    print(qb.get_all_questions())
