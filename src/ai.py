import numpy as np
import base64
import os
import json
import re
from typing import Dict, List, Optional, Any
import logging
from openai import OpenAI
from PIL import Image
import random
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

    def detect_question_areas(
        self,
        image_path: str,
        practice_data: Dict[str, Any] = None,
        resize_size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        检测图片中的题目区域（简化版本）

        Args:
            image_path: 图片路径
            practice_data: 练习数据（可选，不使用）
            resize_size: 图片缩放尺寸（默认 1000x1000）

        Returns:
            题目区域信息列表，包含题号、位置坐标等（像素坐标）
            注意：坐标是基于 resize 后的图片，包含 original_size 和 resized_size 信息用于还原
        """
        try:
            # 获取原始图片尺寸
            with Image.open(image_path) as img:
                original_width, original_height = img.size

            # Resize 图片
            resized_path = self._resize_image(image_path, resize_size)

            # 编码图片为 base64
            with open(resized_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")

            # 简化的 prompt
            prompt = """定位试卷图片中所有题目区域，输出为二维线框坐标（像素坐标），按照以下 JSON 结构返回：

{
  "question_areas": [
    {
      "question_number": "题目编号",
      "bbox_2d": [x1, y1, x2, y2]
    }
  ]
}

要求：
- bbox_2d 是题目区域的矩形坐标，[x1, y1, x2, y2] 为像素坐标（整数）
- question_number 为题目编号（如 "1", "2" 等）
- 只返回 JSON，不要其他说明"""

            # 构建消息
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
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

            self.logger.info(
                f"使用简化 prompt 检测题目区域，原始尺寸: {original_width}x{original_height}, resize 尺寸: {resize_size}x{resize_size}"
            )

            # 调用 AI 模型（不使用 JSON Schema）
            response = self.ai_client.chat.completions.create(
                model="qwen-vl-max",
                messages=messages,
                max_tokens=2000,
                temperature=0.1,
            )

            response_text = response.choices[0].message.content
            self.logger.info(f"AI模型返回结果长度: {len(response_text)} 字符")

            # 清理 markdown 代码块标记
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            # 解析 JSON
            result = json.loads(response_text)
            question_areas = result.get("question_areas", [])

            # 为每个区域添加默认字段和尺寸信息
            for area in question_areas:
                # 添加尺寸信息用于坐标转换
                area["original_size"] = [original_width, original_height]
                area["resized_size"] = [resize_size, resize_size]

                if "answer_bbox_2d" not in area:
                    # 默认答案区域为题目区域的下半部分
                    bbox = area.get("bbox_2d", [0, 0, 0, 0])
                    if len(bbox) == 4:
                        x1, y1, x2, y2 = bbox
                        answer_y1 = y1 + int((y2 - y1) * 0.6)
                        area["answer_bbox_2d"] = [x1, answer_y1, x2, y2]
                    else:
                        area["answer_bbox_2d"] = [0, 0, 0, 0]

                if "question_type" not in area:
                    area["question_type"] = "unknown"
                if "confidence" not in area:
                    area["confidence"] = 0.8

            self.logger.info(f"检测到 {len(question_areas)} 个题目区域")
            if question_areas:
                for i, area in enumerate(question_areas):
                    self.logger.info(
                        f"题目 {i + 1}: {area.get('question_number', 'N/A')} - 坐标(resize): {area.get('bbox_2d', 'N/A')}"
                    )
            else:
                self.logger.warning("未检测到任何题目区域")

            return question_areas

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 解析失败: {e}")
            self.logger.error(
                f"响应内容: {response_text[:500] if 'response_text' in locals() else 'N/A'}"
            )
            return []
        except Exception as e:
            self.logger.error(f"题目区域检测失败: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            return []

    def _resize_image(self, image_path: str, target_size: int = 1000) -> str:
        """
        将图片缩放为指定尺寸（正方形）

        Args:
            image_path: 原始图片路径
            target_size: 目标尺寸（默认 1000）

        Returns:
            缩放后的图片路径
        """
        img = Image.open(image_path)
        original_size = img.size

        # 直接缩放到目标尺寸（不保持宽高比）
        resized_img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)

        # 保存缩放后的图片（临时文件）
        import tempfile

        # 获取文件扩展名
        _, ext = os.path.splitext(image_path)
        if not ext:
            ext = ".jpg"

        # 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="resized_")
        os.close(temp_fd)

        # 保存图片
        resized_img.save(temp_path, quality=95)

        self.logger.info(
            f"图片已缩放: {original_size} -> ({target_size}, {target_size})"
        )
        self.logger.debug(f"缩放后图片路径: {temp_path}")

        return temp_path

    @staticmethod
    def convert_coords_to_original(
        bbox: List[int], original_size: List[int], resized_size: List[int]
    ) -> List[int]:
        """
        将 resize 后的坐标转换回原始图片坐标

        Args:
            bbox: resize 后的坐标 [x1, y1, x2, y2]
            original_size: 原始图片尺寸 [width, height]
            resized_size: resize 后的尺寸 [width, height]

        Returns:
            原始图片坐标 [x1, y1, x2, y2]
        """
        if len(bbox) != 4 or len(original_size) != 2 or len(resized_size) != 2:
            print(
                f"⚠️ 坐标转换参数错误: bbox={bbox}, orig={original_size}, resized={resized_size}"
            )
            return bbox

        x1, y1, x2, y2 = bbox
        orig_w, orig_h = original_size
        resized_w, resized_h = resized_size

        # 计算缩放比例
        scale_x = orig_w / resized_w
        scale_y = orig_h / resized_h

        print(f"🔧 坐标转换:")
        print(f"   输入坐标: [{x1}, {y1}, {x2}, {y2}]")
        print(f"   原始尺寸: {orig_w} x {orig_h}")
        print(f"   Resize尺寸: {resized_w} x {resized_h}")
        print(f"   缩放比例: x={scale_x:.2f}, y={scale_y:.2f}")

        # 转换坐标
        orig_x1 = int(x1 * scale_x)
        orig_y1 = int(y1 * scale_y)
        orig_x2 = int(x2 * scale_x)
        orig_y2 = int(y2 * scale_y)

        print(f"   输出坐标: [{orig_x1}, {orig_y1}, {orig_x2}, {orig_y2}]")

        return [orig_x1, orig_y1, orig_x2, orig_y2]

    @staticmethod
    def convert_question_areas_to_original(
        question_areas: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        将检测结果中的所有坐标转换回原始图片坐标

        Args:
            question_areas: 检测结果列表（包含 original_size 和 resized_size）

        Returns:
            转换后的检测结果列表
        """
        converted_areas = []

        for area in question_areas:
            converted_area = area.copy()

            original_size = area.get("original_size")
            resized_size = area.get("resized_size")

            if original_size and resized_size:
                # 转换题目区域坐标
                if "bbox_2d" in area:
                    converted_area["bbox_2d"] = AIProcessor.convert_coords_to_original(
                        area["bbox_2d"], original_size, resized_size
                    )

                # 转换答案区域坐标
                if "answer_bbox_2d" in area:
                    converted_area["answer_bbox_2d"] = (
                        AIProcessor.convert_coords_to_original(
                            area["answer_bbox_2d"], original_size, resized_size
                        )
                    )

            converted_areas.append(converted_area)

        return converted_areas

    def get_question_positions_for_grading(
        self,
        image_width: int,
        image_height: int,
        question_areas: Optional[List[Dict[str, Any]]] = None,
        image_path: Optional[str] = None,
        practice_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取用于批改标记的题目位置信息

        Args:
            image_width: 目标图片宽度（像素）- 通常是原始图片尺寸
            image_height: 目标图片高度（像素）- 通常是原始图片尺寸
            question_areas: 已检测的题目区域列表（优先使用）
            image_path: 图片路径（当question_areas为None时使用）
            practice_data: 练习数据（当question_areas为None时使用）

        Returns:
            用于批改标记的位置信息列表（坐标已转换为目标图片尺寸）
        """
        # 如果没有提供question_areas，则尝试检测
        if question_areas is None:
            if image_path and practice_data:
                question_areas = self.detect_question_areas(image_path, practice_data)
            else:
                self.logger.warning(
                    "未提供question_areas，且缺少image_path或practice_data"
                )
                return []

        if not question_areas:
            self.logger.warning("question_areas为空，无法生成批改位置")
            return []

        # 检查是否需要坐标转换
        # 如果 question_areas 包含 original_size 和 resized_size，说明是 resize 后的坐标
        needs_conversion = False
        if (
            question_areas
            and "original_size" in question_areas[0]
            and "resized_size" in question_areas[0]
        ):
            original_size = question_areas[0]["original_size"]
            resized_size = question_areas[0]["resized_size"]

            self.logger.info(f"原始图片尺寸（从检测结果）: {original_size}")
            self.logger.info(f"Resize 后尺寸（从检测结果）: {resized_size}")
            self.logger.info(f"目标尺寸（参数传入）: ({image_width}, {image_height})")

            # 打印第一个坐标作为示例
            if question_areas:
                sample_bbox = question_areas[0].get("bbox_2d", [])
                self.logger.info(f"示例坐标（转换前）: {sample_bbox}")

            # 检查目标尺寸是否与 resized_size 一致
            if (image_width, image_height) != tuple(resized_size):
                needs_conversion = True
                self.logger.info(
                    f"检测到坐标需要转换: resize({resized_size}) -> target({image_width}x{image_height})"
                )
            else:
                self.logger.info("目标尺寸与 resize 尺寸一致，无需转换")

        # 如果需要转换，先转换坐标
        if needs_conversion:
            # 转换到原始尺寸
            question_areas_converted = self.convert_question_areas_to_original(
                question_areas
            )

            # 打印转换后的坐标
            if question_areas_converted:
                sample_bbox_converted = question_areas_converted[0].get("bbox_2d", [])
                self.logger.info(f"示例坐标（转换后）: {sample_bbox_converted}")
        else:
            question_areas_converted = question_areas

        # 转换为批改标记需要的格式
        grading_positions = []

        for area in question_areas_converted:
            bbox_2d = area.get("bbox_2d", [0, 0, 0, 0])
            answer_bbox_2d = area.get("answer_bbox_2d", [0, 0, 0, 0])

            # bbox_2d 现在是目标尺寸的像素坐标，直接使用
            question_x1 = bbox_2d[0]
            question_y1 = bbox_2d[1]
            question_x2 = bbox_2d[2]
            question_y2 = bbox_2d[3]

            # 标记位置：放在题目区域的左下角
            # x = question_x1
            # y = question_y2

            x = (question_x1 + question_x2) / 2 + random.randint(0, 100)
            y = (question_y1 + question_y2) / 2

            self.logger.debug(f"批改标记位置: ({x}, {y})")

            grading_position = {
                "question_number": area.get("question_number", ""),
                "question_type": area.get("question_type", ""),
                "bbox_2d": bbox_2d,
                "answer_bbox_2d": answer_bbox_2d,
                "x": int(x),
                "y": int(y),
                "width": 100,  # 标记区域宽度
                "height": 100,  # 标记区域高度
                "confidence": area.get("confidence", 0.5),
            }

            grading_positions.append(grading_position)

        return grading_positions

    def save_question_positions_to_sections(
        self,
        question_areas: List[Dict[str, Any]],
        student_answers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        将题目位置信息保存到sections[].questions[].positions中

        新逻辑：按照 student_answers 中题目的整体顺序进行匹配
        只要 question_areas 的数量等于题目总数，就按顺序一一对应

        Args:
            question_areas: AI检测到的题目区域信息（不包含question_id，但按顺序排列）
            student_answers: 学生答案数据

        Returns:
            更新后的学生答案数据
        """
        # 为每个学生答案添加位置信息
        for student_answer in student_answers:
            sections = student_answer.get("sections", [])

            # 计算总题目数
            total_questions = sum(
                len(section.get("questions", [])) for section in sections
            )

            print(
                f"📍 保存位置信息: 题目总数 {total_questions}, 位置信息数量 {len(question_areas)}"
            )

            # 如果位置信息数量与题目数量匹配，按顺序对应
            if len(question_areas) == total_questions:
                print("✅ 数量匹配，按顺序保存位置信息")

                # 按顺序遍历所有题目
                position_index = 0
                for section in sections:
                    questions = section.get("questions", [])
                    for question in questions:
                        if position_index < len(question_areas):
                            area = question_areas[position_index]
                            question["positions"] = {
                                "bbox_2d": area.get("bbox_2d", [0, 0, 0, 0]),
                                "answer_bbox_2d": area.get(
                                    "answer_bbox_2d", [0, 0, 0, 0]
                                ),
                                "confidence": area.get("confidence", 0.5),
                            }
                            print(f"  题目 {position_index + 1}: 保存位置信息")
                            position_index += 1
            else:
                # 如果数量不匹配，回退到旧的匹配逻辑（按题目类型和序号）
                print("⚠️ 数量不匹配，使用旧的匹配逻辑（按题目类型和序号）")

                # 按题目类型和序号组织位置信息
                positions_by_type_and_number = {}
                for area in question_areas:
                    question_type = area.get("question_type", "")
                    question_number = area.get("question_number", "")

                    if question_type not in positions_by_type_and_number:
                        positions_by_type_and_number[question_type] = {}

                    positions_by_type_and_number[question_type][question_number] = {
                        "bbox_2d": area.get("bbox_2d", [0, 0, 0, 0]),
                        "answer_bbox_2d": area.get("answer_bbox_2d", [0, 0, 0, 0]),
                        "confidence": area.get("confidence", 0.5),
                    }

                # 将位置信息添加到对应的题目中
                for section in sections:
                    section_type = section.get("type", "")
                    questions = section.get("questions", [])

                    if section_type in positions_by_type_and_number:
                        type_positions = positions_by_type_and_number[section_type]

                        for i, question in enumerate(questions):
                            question_number = str(i + 1)  # 题目序号从1开始

                            if question_number in type_positions:
                                question["positions"] = type_positions[question_number]

        return student_answers

    def _build_question_info(self, practice_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建题目信息字典供AI参考"""
        sections_info = []
        total_questions = 0

        for section in practice_data.get("sections", []):
            section_name = section.get("name", "")
            section_type = section.get("type", "")
            questions = section.get("questions", [])
            question_count = len(questions)
            total_questions += question_count

            section_data = {
                "name": section_name,
                "type": section_type,
                "count": question_count,
                "questions": [],
            }

            for i, question in enumerate(questions, 1):
                question_id = question.get("id", "")
                question_text = question.get("question", "")

                # 截取题目文本的前100个字符作为参考
                short_question = (
                    question_text[:100] + "..."
                    if len(question_text) > 100
                    else question_text
                )

                section_data["questions"].append(
                    {"number": i, "id": question_id, "preview": short_question}
                )

            sections_info.append(section_data)

        return {"total_questions": total_questions, "sections": sections_info}

    def _build_detection_prompt(
        self, question_info: Dict[str, Any], image_width: int, image_height: int
    ) -> str:
        """构建检测prompt"""
        # 构建题目概述
        total_questions = question_info.get("total_questions", 0)
        sections = question_info.get("sections", [])

        # 构建详细的题目信息
        sections_text = []
        for section in sections:
            section_name = section.get("name", "")
            section_type = section.get("type", "")
            question_count = section.get("count", 0)
            sections_text.append(
                f"- {section_name}：{question_count} 道题（类型：{section_type}）"
            )

        sections_summary = "\n".join(sections_text)

        print("sections_summary", sections_summary, "total_questions", total_questions)

        return f"""获取图片中所有题目区域的位置坐标，共有 {total_questions} 道题   
图片尺寸：{image_width} x {image_height} 像素

试卷结构：
{sections_summary}

内容：
1. 题目内容位置信息：识别每个题目区域的具体位置坐标
2. 学生答题位置信息：识别在每个题目区域中学生填写答案的位置信息。
3. 识别题目类型：选择题（choice）或计算题（calculation）

请按照以下JSON格式返回结果：
{{
  "question_areas": [
    {{
      "question_number": "题目编号（如1、2、一、二等）",
      "question_type": "题目类型（choice/calculation）",
      "bbox_2d": [x1, y1, x2, y2],
      "answer_bbox_2d": [x1, y1, x2, y2],
      "confidence": "识别置信度（0-1）"
    }}
  ]
}}

要求：
1. 坐标使用绝对像素坐标（整数），范围是 0 到 {image_width}（宽度）和 0 到 {image_height}（高度）
2. **必须识别出所有 {total_questions} 道题目，question_areas 数组的长度应该等于 {total_questions}**
   - 为每道题确定一个矩形区域，包含题目和答题内容，边界一定不要过大，可以适当缩小。
   - 题目的区域不可重叠。
3. 确保识别结果按顺序排列
4. 如果某个题目位置不太确定，仍然要尽量给出估计位置，但将confidence设置为较低值（如0.3-0.5）
5. 只返回JSON格式，不要添加其他解释文字

请开始分析图片："""

    def _parse_detection_result(
        self, response_text: str, practice_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """解析AI返回的检测结果"""
        try:
            self.logger.info(f"开始解析AI返回结果，原始长度: {len(response_text)}")

            # 计算期望的题目数量
            expected_count = sum(
                len(section.get("questions", []))
                for section in practice_data.get("sections", [])
            )
            self.logger.info(f"期望识别 {expected_count} 道题目")

            # 清理响应文本
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
                self.logger.info("移除了开头的```json标记")
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
                self.logger.info("移除了结尾的```标记")
            clean_text = clean_text.strip()

            self.logger.info(f"清理后的文本长度: {len(clean_text)}")
            self.logger.debug(f"清理后的文本内容: {clean_text[:200]}...")

            # 解析JSON（如果使用了 JSON Schema，应该已经是严格格式）
            result = json.loads(clean_text)
            image_width = result.get("image_width", 1)
            image_height = result.get("image_height", 1)
            question_areas = result.get("question_areas", [])
            self.logger.info(f"图片尺寸: {image_width}x{image_height}")
            self.logger.info(f"从JSON中提取到 {len(question_areas)} 个题目区域")

            # 验证和清理结果
            validated_areas = []
            for i, area in enumerate(question_areas):
                self.logger.debug(f"验证题目区域 {i + 1}: {area}")
                if self._validate_question_area(area):
                    validated_areas.append(area)
                    self.logger.info(f"题目区域 {i + 1} 验证通过")
                else:
                    self.logger.warning(f"题目区域 {i + 1} 验证失败，跳过")

            self.logger.info(f"最终验证通过 {len(validated_areas)} 个题目区域")

            # 检查识别数量是否正确
            if len(validated_areas) != expected_count:
                self.logger.warning(
                    f"⚠️ 识别到的题目数量({len(validated_areas)})与期望数量({expected_count})不一致！"
                )
                self.logger.warning(
                    f"   期望: {expected_count} 道题，实际识别: {len(validated_areas)} 道题"
                )
            else:
                self.logger.info(
                    f"✅ 题目数量匹配：成功识别所有 {expected_count} 道题！"
                )

            return validated_areas

        except json.JSONDecodeError as e:
            self.logger.error(f"解析检测结果JSON失败: {e}")
            self.logger.error(
                f"清理后的文本: {clean_text if 'clean_text' in locals() else 'N/A'}..."
            )
            self.logger.error(f"原始响应文本: {response_text[:]}...")
            return []
        except Exception as e:
            self.logger.error(f"解析检测结果失败: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            return []

    def _validate_question_area(self, area: Dict[str, Any]) -> bool:
        """验证题目区域数据的有效性"""
        required_fields = ["question_number", "bbox_2d", "answer_bbox_2d"]

        # 检查必需字段
        for field in required_fields:
            if field not in area:
                self.logger.warning(f"缺少必需字段: {field}")
                return False

        bbox_2d = area.get("bbox_2d", [])
        answer_bbox_2d = area.get("answer_bbox_2d", [])

        # 检查bbox是否为长度为4的列表
        if not isinstance(bbox_2d, list) or len(bbox_2d) != 4:
            self.logger.warning(f"bbox_2d格式错误，应为长度为4的列表: {bbox_2d}")
            return False

        if not isinstance(answer_bbox_2d, list) or len(answer_bbox_2d) != 4:
            self.logger.warning(
                f"answer_bbox_2d格式错误，应为长度为4的列表: {answer_bbox_2d}"
            )
            return False

        try:
            if bbox_2d[0] >= bbox_2d[2] or bbox_2d[1] >= bbox_2d[3]:
                self.logger.warning(
                    f"bbox_2d坐标逻辑错误: x1={bbox_2d[0]} >= x2={bbox_2d[2]} 或 y1={bbox_2d[1]} >= y2={bbox_2d[3]}"
                )
                return False

            if (
                answer_bbox_2d[0] >= answer_bbox_2d[2]
                or answer_bbox_2d[1] >= answer_bbox_2d[3]
            ):
                self.logger.warning(
                    f"answer_bbox_2d坐标逻辑错误: x1={answer_bbox_2d[0]} >= x2={answer_bbox_2d[2]} 或 y1={answer_bbox_2d[1]} >= y2={answer_bbox_2d[3]}"
                )
                return False

        except (ValueError, TypeError) as e:
            self.logger.warning(f"坐标值转换失败: {e}")
            return False

        self.logger.debug(f"题目区域验证通过: {area.get('question_number', 'N/A')}")
        return True
