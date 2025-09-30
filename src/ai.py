import numpy as np
import base64
import os
import json
import re
from typing import Dict, List, Optional, Any
import logging
from openai import OpenAI
from src.knowledge_base import knowledge_base, KnowledgePoint


class AIProcessor:
    def __init__(self) -> None:
        self.ai_client = OpenAI(
            # api_key=os.getenv("OPENAI_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.logger = logging.getLogger(__name__)

    def extract_knowledge_points(self, text: str) -> List[KnowledgePoint]:
        """Extract knowledge points from text based on math curriculum."""
        # 获取所有可用的知识点
        all_knowledge_points = knowledge_base.get_all_knowledge_points()

        # 构建知识点列表供AI参考
        knowledge_points_info = []
        for i, point in enumerate(all_knowledge_points, 1):
            knowledge_points_info.append(f"{i}. {point.outline}: {point.detail}")

        knowledge_points_text = "\n".join(knowledge_points_info)

        # 构建AI提示词
        prompt = f"""你是一个数学教学专家，需要根据用户的要求精准匹配七年级第二章《有理数计算》的知识点。

可用的知识点列表：
{knowledge_points_text}

用户要求："{text}"

请根据用户的要求，从上述知识点中选择所有符合要求的知识点。要求：
1. 精准匹配，不要选择不相关的知识点
2. 如果用户要求涉及多个知识点，请选择所有相关的知识点
3. 只返回知识点的序号，用逗号分隔，例如：1,3,5
4. 如果没有匹配的知识点，返回空字符串

请直接返回匹配的知识点序号："""

        messages = [
            {
                "role": "user",
                "content": prompt,
            }
        ]

        try:
            response = self.ai_client.chat.completions.create(
                model="qwen-plus", messages=messages, max_tokens=100, temperature=0.1
            )

            result = response.choices[0].message.content.strip()

            # 解析AI返回的序号
            if not result:
                return []

            # 提取序号
            numbers = re.findall(r"\d+", result)

            matched_points = []
            for num_str in numbers:
                try:
                    index = int(num_str) - 1  # 转换为0基索引
                    if 0 <= index < len(all_knowledge_points):
                        matched_points.append(all_knowledge_points[index])
                except (ValueError, IndexError):
                    continue

            return matched_points

        except Exception as e:
            logging.error(f"AI knowledge point extraction failed: {e}")
            # 如果AI调用失败，使用关键词匹配作为备选
            return knowledge_base.find_matching_knowledge_points(text)

    def parse_practice_markdown(self, practice_markdown: str) -> dict:
        """Parse practice markdown and return practice data."""
        pass

    def parse_student_answer_from_ocr(self, ocr_text: str, practice_data: dict) -> dict:
        """Parse OCR text to student answer format"""
        try:
            prompt = f"""请将以下OCR识别的学生答题内容解析为结构化的JSON格式。

OCR文本：
{ocr_text}

参考练习试卷结构：
{json.dumps(practice_data, ensure_ascii=False, indent=2)}

要求：
1. 识别所有题目编号和对应的学生答案
2. 对于选择题，提取学生选择的选项（A、B、C、D等）
3. 对于计算题，提取学生的解题步骤和最终答案
4. 按照student_answer.json的格式输出

返回JSON格式：
{{
  "name": "学生姓名（如果识别到）",
  "practice_id": "",
  "sections": [
    {{
      "name": "一、选择题",
      "type": "choice",
      "questions": [
        {{
          "id": "题目ID",
          "answer": {{
            "choice": "A"
          }}
        }}
      ]
    }},
    {{
      "name": "二、计算题", 
      "type": "calculation",
      "questions": [
        {{
          "id": "题目ID",
          "answer": {{
            "solution_steps": ["步骤1", "步骤2"],
            "result": "最终答案"
          }}
        }}
      ]
    }}
  ]
}}

请严格按照JSON格式返回，不要添加其他内容。"""

            response = self.ai_client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的数学老师，擅长解析学生的答题内容。请仔细识别题目编号和答案，并按照要求的JSON格式输出。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
            )

            response_text = response.choices[0].message.content

            # 清理响应文本
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            return json.loads(clean_text)

        except Exception as e:
            self.logger.error(f"解析学生答案失败: {e}")
            return {"name": "未知学生", "practice_id": "", "sections": []}

    def grade_choice_question(
        self, student_answer: str, correct_answer: str, choices: List[Dict]
    ) -> Dict[str, Any]:
        """批改选择题"""
        is_correct = student_answer == correct_answer
        result = {
            "is_correct": is_correct,
            "student_answer": student_answer,
            "correct_answer": correct_answer,
            "explanation": "",
        }

        if not is_correct:
            # 找到错误选项的解释
            for choice in choices:
                if choice["id"] == student_answer:
                    result["explanation"] = choice.get("explanation", "答案错误")
                    break

        return result

    def grade_calculation_question(
        self,
        student_steps: List[str],
        student_result: str,
        correct_steps: List[Dict],
        correct_answer: str,
    ) -> Dict[str, Any]:
        """批改计算题"""
        try:
            # 使用AI判断每个步骤的正确性
            prompt = f"""请分析学生的计算题解答过程，判断每个步骤是否正确。

学生解答步骤：
{json.dumps(student_steps, ensure_ascii=False, indent=2)}

学生最终答案：{student_result}

要求：
1. 逐个分析学生解答的每个步骤
2. 判断步骤是否正确，如果不正确请说明错误原因
3. 判断最终答案是否正确
4. 特别注意符号运算、运算顺序等数学规则

返回JSON格式：
{{
  "overall_correct": true/false,
  "final_answer_correct": true/false,
  "steps_analysis": [
    {{
      "step_index": 0,
      "student_step": "学生步骤",
      "is_correct": true/false,
      "explanation": "错误原因或正确说明"
    }}
  ],
  "final_answer_explanation": "最终答案分析"
}}"""

            response = self.ai_client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的数学老师，擅长分析学生的解题过程。请仔细分析每个步骤的正确性，特别注意数学运算规则。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1500,
            )

            response_text = response.choices[0].message.content

            # 清理响应文本
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()
            print("### grade_calculation_question\n", prompt, clean_text)
            return json.loads(clean_text)

        except Exception as e:
            self.logger.error(f"批改计算题失败: {e}")
            return {
                "overall_correct": False,
                "final_answer_correct": False,
                "steps_analysis": [],
                "final_answer_explanation": "批改过程中出现错误",
            }

    def analyze_error_knowledge_points(
        self, grading_results: List[Dict]
    ) -> Dict[str, Any]:
        """分析错误知识点 - 直接从grading_results统计"""
        try:
            # 统计每个知识点的错误次数
            knowledge_point_errors = {}

            for result in grading_results:
                # 判断题目是否错误，兼容选择题和计算题的不同字段
                question_type = result.get("question_type", "")
                is_incorrect = False

                if question_type == "choice":
                    is_incorrect = not result.get("is_correct", True)
                elif question_type == "calculation":
                    is_incorrect = not result.get("overall_correct", True)
                else:
                    is_incorrect = not result.get("is_correct", True)

                if is_incorrect:
                    # 获取题目涉及的知识点
                    knowledge_points = result.get("knowledge_points", [])
                    for kp in knowledge_points:
                        if isinstance(kp, dict):
                            outline = kp.get("outline", "")
                            if outline:
                                if outline not in knowledge_point_errors:
                                    knowledge_point_errors[outline] = {
                                        "outline": outline,
                                        "error_count": 0,
                                        "error_examples": [],
                                    }

                                knowledge_point_errors[outline]["error_count"] += 1

                                # 收集错误示例（从explanation中提取）
                                explanation = result.get("explanation", "")
                                if (
                                    explanation
                                    and explanation
                                    not in knowledge_point_errors[outline][
                                        "error_examples"
                                    ]
                                ):
                                    knowledge_point_errors[outline][
                                        "error_examples"
                                    ].append(explanation)

            if not knowledge_point_errors:
                return {"error_knowledge_points": [], "top_error_points": []}

            # 转换为列表并添加标准detail描述
            error_knowledge_points = []
            for outline, data in knowledge_point_errors.items():
                # 查找知识库中的标准detail描述
                standard_detail = ""
                for kp in knowledge_base.get_all_knowledge_points():
                    if kp.outline == outline:
                        standard_detail = kp.detail
                        break

                error_knowledge_points.append(
                    {
                        "outline": outline,
                        "detail": standard_detail,
                        "error_count": data["error_count"],
                        "error_examples": data["error_examples"][:3],  # 最多保留3个示例
                    }
                )

            # 按错误次数排序
            error_knowledge_points.sort(key=lambda x: x["error_count"], reverse=True)

            # 获取错误最多的前两个知识点
            top_error_points = error_knowledge_points[:2]

            return {
                "error_knowledge_points": error_knowledge_points,
                "top_error_points": top_error_points,
            }

        except Exception as e:
            self.logger.error(f"分析错误知识点失败: {e}")
            return {"error_knowledge_points": [], "top_error_points": []}

    def generate_teaching_suggestions(self, grading_results: List[Dict]) -> str:
        """根据学生答题错误类型生成课堂讲解建议"""
        try:
            # 分析错误类型和模式
            error_analysis = self._analyze_error_patterns(grading_results)

            # 生成针对性的教学建议
            suggestions = self._generate_targeted_suggestions(error_analysis)

            return suggestions

        except Exception as e:
            self.logger.error(f"生成教学建议失败: {e}")
            return "根据以上错误分析，建议重点关注错误较多的知识点，加强相关练习。"

    def _analyze_error_patterns(self, grading_results: List[Dict]) -> Dict[str, Any]:
        """分析错误模式和类型"""
        error_patterns = {
            "choice_errors": [],
            "calculation_errors": [],
            "common_mistakes": [],
            "knowledge_gaps": [],
        }

        for result in grading_results:
            question_type = result.get("question_type", "")
            is_incorrect = False

            if question_type == "choice":
                is_incorrect = not result.get("is_correct", True)
                if is_incorrect:
                    error_patterns["choice_errors"].append(
                        {
                            "question": result.get("question_text", ""),
                            "student_answer": result.get("student_answer", ""),
                            "correct_answer": result.get("correct_answer", ""),
                            "explanation": result.get("explanation", ""),
                            "knowledge_points": result.get("knowledge_points", []),
                        }
                    )
            elif question_type == "calculation":
                is_incorrect = not result.get("overall_correct", True)
                if is_incorrect:
                    steps_analysis = result.get("steps_analysis", [])
                    error_steps = [
                        step
                        for step in steps_analysis
                        if not step.get("is_correct", True)
                    ]

                    error_patterns["calculation_errors"].append(
                        {
                            "question": result.get("question_text", ""),
                            "student_steps": result.get("student_steps", []),
                            "error_steps": error_steps,
                            "final_answer_correct": result.get(
                                "final_answer_correct", False
                            ),
                            "knowledge_points": result.get("knowledge_points", []),
                        }
                    )

        # 分析常见错误模式
        error_patterns["common_mistakes"] = self._identify_common_mistakes(
            error_patterns
        )
        error_patterns["knowledge_gaps"] = self._identify_knowledge_gaps(
            grading_results
        )

        return error_patterns

    def _identify_common_mistakes(self, error_patterns: Dict[str, Any]) -> List[str]:
        """识别常见错误模式"""
        common_mistakes = []

        # 分析选择题常见错误
        choice_errors = error_patterns["choice_errors"]
        if choice_errors:
            # 统计错误选项分布
            wrong_choices = {}
            for error in choice_errors:
                choice = error.get("student_answer", "")
                if choice in wrong_choices:
                    wrong_choices[choice] += 1
                else:
                    wrong_choices[choice] = 1

            # 找出最常见的错误选项
            if wrong_choices:
                most_common_wrong = max(wrong_choices.items(), key=lambda x: x[1])
                if most_common_wrong[1] > 1:  # 如果错误次数大于1
                    common_mistakes.append(
                        f"选择题中选项{most_common_wrong[0]}被错误选择{most_common_wrong[1]}次"
                    )

        # 分析计算题常见错误
        calculation_errors = error_patterns["calculation_errors"]
        if calculation_errors:
            # 统计错误步骤类型
            step_error_types = {}
            for error in calculation_errors:
                error_steps = error.get("error_steps", [])
                for step in error_steps:
                    explanation = step.get("explanation", "")
                    if "符号" in explanation:
                        step_error_types["符号错误"] = (
                            step_error_types.get("符号错误", 0) + 1
                        )
                    elif "运算顺序" in explanation or "优先级" in explanation:
                        step_error_types["运算顺序错误"] = (
                            step_error_types.get("运算顺序错误", 0) + 1
                        )
                    elif "计算" in explanation:
                        step_error_types["计算错误"] = (
                            step_error_types.get("计算错误", 0) + 1
                        )

            # 添加最常见的错误类型
            for error_type, count in step_error_types.items():
                if count > 1:
                    common_mistakes.append(f"计算题中{error_type}出现{count}次")

        return common_mistakes

    def _identify_knowledge_gaps(self, grading_results: List[Dict]) -> List[str]:
        """识别知识盲点"""
        knowledge_gaps = []

        # 统计错误知识点
        error_knowledge_points = {}
        for result in grading_results:
            question_type = result.get("question_type", "")
            is_incorrect = False

            if question_type == "choice":
                is_incorrect = not result.get("is_correct", True)
            elif question_type == "calculation":
                is_incorrect = not result.get("overall_correct", True)

            if is_incorrect:
                knowledge_points = result.get("knowledge_points", [])
                for kp in knowledge_points:
                    if isinstance(kp, dict):
                        outline = kp.get("outline", "")
                        if outline:
                            error_knowledge_points[outline] = (
                                error_knowledge_points.get(outline, 0) + 1
                            )

        # 找出错误最多的知识点
        if error_knowledge_points:
            sorted_errors = sorted(
                error_knowledge_points.items(), key=lambda x: x[1], reverse=True
            )
            for outline, count in sorted_errors[:3]:  # 取前3个
                if count > 1:  # 错误次数大于1
                    knowledge_gaps.append(f"{outline}相关题目错误{count}次")

        return knowledge_gaps

    def _generate_targeted_suggestions(self, error_patterns: Dict[str, Any]) -> str:
        """生成针对性的教学建议"""
        suggestions = []
        suggestion_count = 1

        # 基于知识盲点生成建议（最重要的）
        knowledge_gaps = error_patterns["knowledge_gaps"]
        if knowledge_gaps:
            gap_topic = knowledge_gaps[0].split("相关")[0]
            suggestions.append(
                f"{suggestion_count}. 重点突破：针对{gap_topic}进行专项训练，通过典型例题反复练习。"
            )
            suggestion_count += 1

        # 基于常见错误模式生成建议
        common_mistakes = error_patterns["common_mistakes"]
        if common_mistakes:
            if any("符号错误" in mistake for mistake in common_mistakes):
                suggestions.append(
                    f"{suggestion_count}. 符号强化：专门练习符号运算，要求学生先确定符号再计算，避免符号错误。"
                )
                suggestion_count += 1
            if any("运算顺序错误" in mistake for mistake in common_mistakes):
                suggestions.append(
                    f"{suggestion_count}. 口诀记忆：总结运算顺序口诀（如'先括号，再乘方，乘除加减不乱忙'），帮助学生记忆。"
                )
                suggestion_count += 1
            if any("计算错误" in mistake for mistake in common_mistakes):
                suggestions.append(
                    f"{suggestion_count}. 步骤化教学：带着学生一步一步演算，要求写清每一步，避免心算跳步。"
                )
                suggestion_count += 1

        # 基于具体错误类型生成建议
        choice_errors = error_patterns["choice_errors"]
        calculation_errors = error_patterns["calculation_errors"]

        if choice_errors and calculation_errors:
            suggestions.append(
                f"{suggestion_count}. 错因讲解：用学生的典型错题做反例分析，让他们自己找错误并改正。"
            )
            suggestion_count += 1
        elif choice_errors:
            suggestions.append(
                f"{suggestion_count}. 概念辨析：通过对比分析易混淆概念，设计变式练习加深理解。"
            )
            suggestion_count += 1
        elif calculation_errors:
            suggestions.append(
                f"{suggestion_count}. 验算习惯：培养学生逐步验算的习惯，提高计算准确性。"
            )
            suggestion_count += 1

        # 如果没有具体错误模式，提供通用建议
        if not suggestions:
            suggestions.append(
                f"{suggestion_count}. 基础巩固：加强基础概念教学，通过反复练习巩固知识点。"
            )

        return "\n".join(suggestions)

    def ocr_practice(self, image_path: str) -> Dict[str, str]:
        """Extract text using Qwen-VL-OCR model.

        Args:
            image_path: Path to the input image

        Returns:
            Dictionary containing OCR results from AI model
        """
        try:
            # Encode image to base64
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")

            # Log image processing without exposing image data
            self.logger.debug(
                f"Processing image: {image_path}, size: {len(base64_image)} characters"
            )

            # Create prompt for mathematical OCR
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """请仔细识别这张数学作业图片中的所有文字和数学表达式。要求：
1. 准确识别题目编号和数字、运算符号、分数、等号等数学符号
2. 数学表达式使用 latex 语法。
3. 识别中文题目描述和解答过程
4. 对于手写内容，请尽可能准确识别
5. 按照原图的顺序输出内容

请直接输出识别的文字内容，不要添加额外的解释。""",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ]

            # Call Qwen-VL-OCR model
            response = self.ai_client.chat.completions.create(
                model="qwen-vl-ocr", messages=messages, max_tokens=2000, temperature=0.1
            )

            raw_text = response.choices[0].message.content

            # AI OCR typically has high confidence when it works
            confidence = 85.0 if raw_text and len(raw_text.strip()) > 10 else 30.0

            return {
                "raw_text": raw_text.strip(),
                "confidence": confidence,
                "method": "ai_ocr",
                "model": "qwen-vl-ocr",
            }

        except Exception as e:
            return {
                "raw_text": "",
                "confidence": 0,
                "error": str(e),
                "method": "ai_ocr_failed",
            }

    def _parse_with_rules(self, ocr_text: str) -> List[Dict]:
        """Use rule-based parsing as fallback"""
        # 简单的规则解析，返回空列表
        return []
