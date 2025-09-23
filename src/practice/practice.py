import os
import json
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# 添加父目录到路径，支持直接运行
# import sys
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.question.model import Question
from src.question.bank import QuestionBank


@dataclass
class PracticeSection:
    """练习章节"""

    name: str
    type: str
    question_ids: List[str]


@dataclass
class Practice:
    """练习试卷"""

    title: str
    practice_id: str
    sections: List[PracticeSection]


class PracticeManager:
    """练习管理器"""

    def __init__(self):
        self.question_bank = QuestionBank()

    def create_practice(
        self, title: str, choice_count: int = 2, calculation_count: int = 2
    ) -> Practice:
        """创建练习试卷"""
        practice_id = str(uuid.uuid4())[:8]  # 生成8位随机ID

        # 从题库中获取题目
        choice_questions = self.question_bank.get_questions_by_type("choice")
        calculation_questions = self.question_bank.get_questions_by_type("calculation")

        # 随机选择指定数量的题目
        import random

        selected_choices = random.sample(
            choice_questions, min(choice_count, len(choice_questions))
        )
        selected_calculations = random.sample(
            calculation_questions, min(calculation_count, len(calculation_questions))
        )

    def create_practice_by_knowledge_points(
        self,
        title: str,
        knowledge_points: List[str],
        choice_count: int = 2,
        calculation_count: int = 2,
    ) -> Practice:
        """根据知识点创建练习试卷"""
        practice_id = str(uuid.uuid4())[:8]  # 生成8位随机ID

        # 根据知识点获取题目
        selected_questions = (
            self.question_bank.get_random_questions_by_knowledge_points(
                knowledge_points, choice_count, calculation_count
            )
        )

        # 按类型分组
        choice_questions = [q for q in selected_questions if q.type == "choice"]
        calculation_questions = [
            q for q in selected_questions if q.type == "calculation"
        ]

        # 创建章节
        sections = []

        if choice_questions:
            choice_section = PracticeSection(
                name="一、选择题",
                type="choice",
                question_ids=[q.id for q in choice_questions],
            )
            sections.append(choice_section)

        if calculation_questions:
            calculation_section = PracticeSection(
                name="二、计算题",
                type="calculation",
                question_ids=[q.id for q in calculation_questions],
            )
            sections.append(calculation_section)

        return Practice(title=title, practice_id=practice_id, sections=sections)

    def practice_to_dict(self, practice: Practice) -> Dict[str, Any]:
        """将Practice对象转换为字典格式"""
        sections_data = []

        for section in practice.sections:
            questions_data = []

            for question_id in section.question_ids:
                question = self.question_bank.get_question(question_id)
                if question:
                    question_dict = {
                        "id": question.id,
                        "type": question.type,
                        "metadata": {"category": section.type},
                        "question": question.question,
                        "knowledge_points": [
                            {"outline": kp.outline, "detail": kp.detail}
                            for kp in question.knowledge_points
                        ],
                    }

                    if question.choices:
                        question_dict["choices"] = [
                            {
                                "id": choice.id,
                                "content": choice.content,
                                "is_correct": choice.is_correct,
                                "explanation": choice.explanation,
                            }
                            for choice in question.choices
                        ]
                        # 找到正确答案
                        correct_choice = next(
                            (c for c in question.choices if c.is_correct), None
                        )
                        question_dict["answer"] = (
                            correct_choice.id if correct_choice else ""
                        )

                    if question.solution_steps:
                        question_dict["solution_steps"] = [
                            {"step": step.step} for step in question.solution_steps
                        ]
                        # 对于计算题，需要从solution_steps中提取答案
                        if question.type == "calculation" and question.solution_steps:
                            last_step = question.solution_steps[-1].step
                            # 尝试从最后一步提取答案
                            import re

                            answer_match = re.search(
                                r"=?\s*([+-]?\d+(?:\.\d+)?)", last_step
                            )
                            question_dict["answer"] = (
                                answer_match.group(1) if answer_match else ""
                            )

                    questions_data.append(question_dict)

            section_dict = {
                "name": section.name,
                "type": section.type,
                "question_ids": section.question_ids,
                "questions": questions_data,
            }
            sections_data.append(section_dict)

        return {
            "title": practice.title,
            "practice_id": practice.practice_id,
            "sections": sections_data,
        }

    def save_practice(self, practice: Practice, filename: Optional[str] = None) -> str:
        """保存练习到文件"""
        if filename is None:
            filename = f"practice_{practice.practice_id}.json"

        filepath = os.path.join(os.path.dirname(__file__), filename)

        # 转换为字典格式
        practice_dict = {
            "title": practice.title,
            "practice_id": practice.practice_id,
            "sections": [
                {
                    "name": section.name,
                    "type": section.type,
                    "question_ids": section.question_ids,
                }
                for section in practice.sections
            ],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(practice_dict, f, ensure_ascii=False, indent=2)

        return filepath

    def load_practice(self, filename: str) -> Practice:
        """从文件加载练习"""
        filepath = os.path.join(os.path.dirname(__file__), filename)

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        sections = []
        for section_data in data.get("sections", []):
            section = PracticeSection(
                name=section_data["name"],
                type=section_data["type"],
                question_ids=section_data["question_ids"],
            )
            sections.append(section)

        return Practice(
            title=data["title"], practice_id=data["practice_id"], sections=sections
        )

    def get_practice_questions(self, practice: Practice) -> List[Question]:
        """获取练习中的所有题目"""
        questions = []
        for section in practice.sections:
            for question_id in section.question_ids:
                question = self.question_bank.get_question(question_id)
                if question:
                    questions.append(question)
        return questions

    def get_section_questions(
        self, practice: Practice, section_name: str
    ) -> List[Question]:
        """获取指定章节的题目"""
        questions = []
        for section in practice.sections:
            if section.name == section_name:
                for question_id in section.question_ids:
                    question = self.question_bank.get_question(question_id)
                    if question:
                        questions.append(question)
                break
        return questions

    def generate_pdf(
        self, practice: Practice, output_path: Optional[str] = None
    ) -> str:
        """生成PDF试卷"""
        # PDF生成功能暂未实现
        return "PDF生成功能暂未实现"


if __name__ == "__main__":
    # 测试功能
    manager = PracticeManager()

    # 创建练习
    practice = manager.create_practice(
        "有理数加法练习", choice_count=2, calculation_count=2
    )
    print(f"创建练习: {practice.title}")
    print(f"练习ID: {practice.practice_id}")
    print(f"章节数: {len(practice.sections)}")

    for section in practice.sections:
        print(f"  {section.name}: {len(section.question_ids)} 题")
        questions = manager.get_section_questions(practice, section.name)
        for q in questions:
            print(f"    - {q.question}")

    # 保存练习
    filepath = manager.save_practice(practice)
    print(f"练习已保存到: {filepath}")

    # 生成PDF
    pdf_path = manager.generate_pdf(practice)
    print(f"PDF试卷已生成: {pdf_path}")
