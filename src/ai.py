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

标准解答步骤：
{json.dumps(correct_steps, ensure_ascii=False, indent=2)}

标准答案：{correct_answer}

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
    ) -> List[Dict[str, Any]]:
        """分析错误知识点"""
        try:
            # 收集所有错误信息
            error_info = []
            for result in grading_results:
                if not result.get("is_correct", True):
                    error_info.append(
                        {
                            "question_id": result.get("question_id", ""),
                            "question_type": result.get("question_type", ""),
                            "error_explanation": result.get("explanation", ""),
                            "knowledge_points": result.get("knowledge_points", []),
                        }
                    )

            if not error_info:
                return []

            prompt = f"""请分析以下学生的答题错误，找出涉及的知识点。

错误信息：
{json.dumps(error_info, ensure_ascii=False, indent=2)}

可用的知识点列表：
{json.dumps([{"outline": kp.outline, "detail": kp.detail} for kp in knowledge_base.get_all_knowledge_points()], ensure_ascii=False, indent=2)}

要求：
1. 分析每个错误涉及的知识点
2. 统计每个知识点的错误次数
3. 找出错误最多的前两个知识点

返回JSON格式：
{{
  "error_knowledge_points": [
    {{
      "outline": "知识点名称",
      "detail": "知识点详情", 
      "error_count": 错误次数,
      "error_examples": ["错误示例1", "错误示例2"]
    }}
  ],
  "top_error_points": [
    {{
      "outline": "错误最多的知识点1",
      "detail": "知识点详情",
      "error_count": 错误次数
    }},
    {{
      "outline": "错误最多的知识点2", 
      "detail": "知识点详情",
      "error_count": 错误次数
    }}
  ]
}}"""

            response = self.ai_client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的数学老师，擅长分析学生的学习错误和薄弱知识点。请仔细分析错误模式，找出学生需要重点练习的知识点。",
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

            return json.loads(clean_text)

        except Exception as e:
            self.logger.error(f"分析错误知识点失败: {e}")
            return {"error_knowledge_points": [], "top_error_points": []}

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
2. 使用 latex 语法。
4. 识别中文题目描述和解答过程
5. 对于手写内容，请尽可能准确识别
6. 按照原图的顺序输出内容
7. 注意等号的位置，等号决定了计算步骤的开始。

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
