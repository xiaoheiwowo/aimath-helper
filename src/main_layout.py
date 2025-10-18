import gradio as gr
import random
import time
import os
import datetime
import json
from typing import Optional, List, Dict, Any

from src.session import CompleteSession, get_all_sessions
from src.question.bank import QuestionBank
from src.practice.template import render_markdown
from src.practice.practice import PracticeManager
from src.ai import AIProcessor
from src.knowledge_base import knowledge_base
from src.image_grading import ImageGradingMarker

# 初始化组件（安全初始化，避免API密钥问题）
try:
    qb = QuestionBank()
    practice_manager = PracticeManager()
    ai_processor = AIProcessor()
    image_marker = ImageGradingMarker()
except Exception as e:
    print(f"警告: AI组件初始化失败: {e}")
    print("界面将以演示模式运行，部分功能可能不可用")
    # 创建模拟的组件
    qb = None
    practice_manager = None
    ai_processor = None
    image_marker = None

class MathHelperApp:
    """数学练习助手应用"""

    def __init__(self):
        self.current_session = CompleteSession()

    def generate_questions_from_prompt(self, prompt: str, choice_count: int = 2, calculation_count: int = 2):
        """根据提示词生成题目"""
        if not prompt.strip():
            return "请输入出题要求", [], ""

        # 检查AI组件是否可用
        if ai_processor is None or practice_manager is None:
            return "⚠️ AI功能不可用，请检查API密钥配置", [], ""

        try:
            # 创建新的会话（不修改历史session）
            self.current_session = CompleteSession()
            session_path = self.current_session.initialize()

            # 使用AI提取知识点
            knowledge_points = ai_processor.extract_knowledge_points(prompt)
            knowledge_point_names = [kp.outline for kp in knowledge_points]

            # 根据知识点生成练习
            practice = practice_manager.create_practice_by_knowledge_points(
                title="练习试题",
                knowledge_points=knowledge_point_names,
                choice_count=int(choice_count),
                calculation_count=int(calculation_count),
            )

            # 转换为字典格式
            practice_data = practice_manager.practice_to_dict(practice)

            # 更新会话数据
            self.current_session.data.update(
                {
                    "prompt": prompt,
                    "knowledge_points": knowledge_point_names,
                    "practice_data": practice_data,
                }
            )
            self.current_session.save()

            # 生成Markdown
            practice_markdown = render_markdown(practice_data)

            # 格式化显示结果
            result_text = "成功生成数学练习！\n\n"
            result_text += f"出题要求: {prompt}\n\n"
            result_text += f"涉及知识点: {', '.join(knowledge_point_names)}\n\n"
            result_text += f"题目数量: {len(practice_data['sections'])} 个部分\n"

            for section in practice_data["sections"]:
                result_text += (
                    f"  - {section['name']}: {len(section['questions'])} 题\n"
                )

            return (
                result_text,
                self.current_session.get_images(),
                practice_markdown,
            )

        except Exception as e:
            return f"生成题目时出错: {str(e)}", [], ""

    def process_student_images(self, images):
        """处理学生答题图片"""
        if not images:
            return "请上传学生答题图片", ""

        # 检查AI组件是否可用
        if ai_processor is None:
            return "⚠️ AI功能不可用，请检查API密钥配置", ""

        try:
            if not self.current_session.session_path:
                return "请先生成题目", ""

            # 处理每张图片
            student_answers = []
            grading_results = []
            question_positions_map = {}

            for i, image_item in enumerate(images):
                # 处理 Gallery 组件返回的数据格式
                # Gallery 可能返回字符串路径或 (path, caption) 元组
                if isinstance(image_item, tuple):
                    image_path = image_item[0]  # 取元组的第一个元素（路径）
                else:
                    image_path = image_item  # 直接是字符串路径

                # 检查图片路径是否存在
                if not os.path.exists(image_path):
                    continue

                # 图片已经保存在会话中，直接使用路径
                # OCR识别
                ocr_result = ai_processor.ocr_practice(image_path)
                if not ocr_result.get("raw_text"):
                    continue

                # 解析学生答案（包含学生姓名识别）
                practice_data = self.current_session.data.get("practice_data", {})
                student_answer = ai_processor.parse_student_answer_from_ocr(
                    ocr_result["raw_text"], practice_data
                )

                # 从解析结果中获取学生姓名，如果没有则使用序号
                extracted_name = student_answer.get("name", "")
                if (
                    extracted_name
                    and extracted_name != "未知学生"
                    and extracted_name != "未识别"
                ):
                    student_name = extracted_name
                else:
                    student_name = f"学生{i + 1}"

                student_id = f"student_{i + 1}"

                # 添加学生信息到答案中
                student_answer["student_name"] = student_name
                student_answer["student_id"] = student_id

                student_answers.append(student_answer)

                # 批改答案
                section_results = []
                for section in practice_data.get("sections", []):
                    for question in section.get("questions", []):
                        # 找到对应的学生答案
                        student_question_answer = None
                        for sa_section in student_answer.get("sections", []):
                            if sa_section["type"] == section["type"]:
                                for sa_question in sa_section.get("questions", []):
                                    if sa_question["id"] == question["id"]:
                                        student_question_answer = sa_question
                                        break
                                break

                        if not student_question_answer:
                            continue

                        # 批改题目
                        if section["type"] == "choice":
                            student_choice = student_question_answer.get(
                                "answer", {}
                            ).get("choice", "")
                            correct_answer = question.get("answer", "")
                            grading_result = ai_processor.grade_choice_question(
                                student_choice,
                                correct_answer,
                                question.get("choices", []),
                            )
                        else:  # calculation
                            student_steps = student_question_answer.get(
                                "answer", {}
                            ).get("solution_steps", [])
                            student_result = student_question_answer.get(
                                "answer", {}
                            ).get("result", "")
                            correct_steps = question.get("solution_steps", [])
                            correct_answer = question.get("answer", "")
                            grading_result = ai_processor.grade_calculation_question(
                                student_steps,
                                student_result,
                                correct_steps,
                                correct_answer,
                            )

                        grading_result.update(
                            {
                                "question_id": question["id"],
                                "question_type": section["type"],
                                "question_text": question["question"],
                                "knowledge_points": question.get(
                                    "knowledge_points", []
                                ),
                                "student_name": student_name,
                                "student_id": student_id,
                            }
                        )
                        section_results.append(grading_result)

                grading_results.extend(section_results)

            # 生成带标记的图片
            marked_images = []
            if image_marker is not None and grading_results:
                try:
                    practice_data = self.current_session.data.get("practice_data", {})
                    # 获取原始图片路径列表
                    original_images = [
                        image_path
                        for image_item in images
                        for image_path in (
                            [image_item]
                            if isinstance(image_item, str)
                            else [image_item[0]]
                        )
                    ]

                    # 使用AI检测题目位置（如果可用）
                    if ai_processor is not None:
                        print("🔍 使用AI检测题目位置...")
                        for image_path in original_images:
                            try:
                                # 直接获取AI检测的原始位置信息
                                question_areas = ai_processor.detect_question_areas(
                                    image_path, practice_data
                                )
                                if question_areas:
                                    question_positions_map[image_path] = question_areas
                                    print(
                                        f"✅ 检测到 {len(question_areas)} 个题目位置: {image_path}"
                                    )
                                else:
                                    print(f"⚠️ 未检测到题目位置: {image_path}")
                            except Exception as e:
                                print(f"❌ 题目位置检测失败 {image_path}: {e}")
                    else:
                        print("⚠️ AI处理器不可用，使用估算位置")

                    # 将题目位置信息添加到对应的学生答案中
                    for i, student_answer in enumerate(student_answers):
                        if i < len(original_images):
                            image_path = original_images[i]
                            if image_path in question_positions_map:
                                # 直接使用AI检测的原始位置信息
                                question_areas = question_positions_map[image_path]

                                # 保存到sections中
                                updated_student_answers = (
                                    ai_processor.save_question_positions_to_sections(
                                        question_areas, [student_answer]
                                    )
                                )
                                # 更新student_answers中的对应项
                                student_answers[i] = updated_student_answers[0]
                                print("📍 已保存题目位置信息到sections中")

                    # 生成标记图片，明确指定session目录
                    if self.current_session.session_path:
                        # 为每张图片指定输出目录
                        marked_images = []
                        for i, image_path in enumerate(original_images):
                            # 创建graded_images目录
                            graded_dir = os.path.join(
                                self.current_session.session_path, "graded_images"
                            )
                            os.makedirs(graded_dir, exist_ok=True)

                            # 生成输出路径
                            base_name = os.path.splitext(os.path.basename(image_path))[
                                0
                            ]
                            output_path = os.path.join(
                                graded_dir, f"{base_name}_graded.jpg"
                            )

                            # 获取该图片的题目位置并转换为批改位置
                            question_areas = question_positions_map.get(image_path)
                            question_positions = None
                            if question_areas:
                                # 读取图片获取尺寸（使用 PIL）
                                from PIL import Image

                                try:
                                    with Image.open(image_path) as img:
                                        image_width, image_height = img.size

                                        # 使用已有的 question_areas 转换归一化坐标为批改位置格式
                                        question_positions = ai_processor.get_question_positions_for_grading(
                                            image_width=image_width,
                                            image_height=image_height,
                                            question_areas=question_areas,
                                        )

                                        print(
                                            f"📍 转换批改位置: {len(question_positions)} 个题目"
                                        )
                                        for pos in question_positions:
                                            print(
                                                f"  题目 {pos['question_number']}: ({pos['x']}, {pos['y']}) - bbox_2d: {pos['bbox_2d']}"
                                            )
                                except Exception as e:
                                    print(f"❌ 读取图片尺寸失败 {image_path}: {e}")

                            # 过滤出当前图片对应学生的批改结果
                            # 假设图片按顺序对应学生答案
                            student_answer = None
                            if i < len(student_answers):
                                student_answer = student_answers[i]
                                student_name = student_answer.get(
                                    "student_name", f"学生{i+1}"
                                )
                                student_id = student_answer.get(
                                    "student_id", f"student_{i+1}"
                                )

                                print(f"\n🔍 调试信息 - 图片 {i+1}:")
                                print(f"  当前学生: {student_name} (ID: {student_id})")
                                print(f"  所有批改结果数量: {len(grading_results)}")

                                # 显示所有批改结果的学生ID
                                all_student_ids = set(
                                    r.get("student_id", "unknown")
                                    for r in grading_results
                                )
                                print(f"  所有批改结果中的学生ID: {all_student_ids}")

                                # 从所有批改结果中过滤出该学生的结果
                                student_grading_results = [
                                    result
                                    for result in grading_results
                                    if result.get("student_id") == student_id
                                ]

                                print(
                                    f"  ✅ 过滤后该学生的批改结果数量: {len(student_grading_results)}"
                                )

                                if student_grading_results:
                                    print(f"  该学生的题目:")
                                    for r in student_grading_results:
                                        print(
                                            f"    - {r.get('question_type')} {r.get('question_id')}: {r.get('is_correct') or r.get('overall_correct')}"
                                        )

                                print(
                                    f"\n🎨 为 {student_name} (ID: {student_id}) 绘制标记（{len(student_grading_results)} 个批改结果）"
                                )
                            else:
                                # 如果没有对应的学生答案，使用所有批改结果（兜底）
                                student_grading_results = grading_results
                                print(
                                    f"\n⚠️ 图片 {i+1} 没有对应的学生答案，使用所有批改结果"
                                )

                            # 标记单张图片（使用该学生的批改结果）
                            marked_path = image_marker.mark_image_with_grading_results(
                                image_path,
                                student_grading_results,  # 使用过滤后的结果
                                practice_data,
                                output_path,
                                question_positions,
                                student_answer,  # 传递student_answer参数
                            )
                            marked_images.append(marked_path)
                    else:
                        # 如果没有session路径，使用默认方法
                        marked_images = image_marker.batch_mark_images(
                            original_images,
                            grading_results,
                            practice_data,
                            question_positions_map if question_positions_map else None,
                            student_answers,  # 传入学生答案列表
                        )

                    # 确保标记图片路径保存到session数据中
                    if marked_images:
                        self.current_session.data["marked_images"] = marked_images
                        self.current_session.save()

                except Exception as e:
                    print(f"生成标记图片时出错: {str(e)}")
                    marked_images = []

            # 更新会话数据
            self.current_session.data.update(
                {
                    "student_answers": student_answers,
                    "grading_results": grading_results,
                    "marked_images": marked_images,
                }
            )
            self.current_session.save()

            # 生成批改报告
            report = self._generate_grading_report(grading_results, student_answers)

            return report, ""

        except Exception as e:
            return f"处理图片时出错: {str(e)}", ""

    def analyze_errors_only(self):
        """只分析错误知识点，不生成新练习"""
        # 检查AI组件是否可用
        if ai_processor is None:
            return "⚠️ AI功能不可用，请检查API密钥配置"

        try:
            grading_results = self.current_session.data.get("grading_results", [])
            if not grading_results:
                return "请先批改学生答案"

            # 分析错误知识点
            error_analysis = ai_processor.analyze_error_knowledge_points(
                grading_results
            )

            # 获取错误最多的知识点
            if isinstance(error_analysis, dict):
                top_error_points = error_analysis.get("top_error_points", [])
            else:
                top_error_points = []

            # 生成详细的分析报告
            analysis_report = "## 📊 错误分析报告\n\n"

            # 总体错误统计
            total_errors = sum(
                1 for result in grading_results if self._is_question_incorrect(result)
            )
            analysis_report += f"**总错误数:** {total_errors}\n\n"

            # 按题目类型统计错误
            choice_errors = sum(
                1
                for result in grading_results
                if self._is_question_incorrect(result)
                and result.get("question_type") == "choice"
            )
            calculation_errors = sum(
                1
                for result in grading_results
                if self._is_question_incorrect(result)
                and result.get("question_type") == "calculation"
            )

            analysis_report += "### 📈 错误类型统计\n\n"
            analysis_report += f"- **选择题错误:** {choice_errors} 题\n"
            analysis_report += f"- **计算题错误:** {calculation_errors} 题\n\n"

            # 错误最多的知识点
            analysis_report += "### 🎯 错误最多的知识点\n\n"
            if top_error_points:
                for i, point in enumerate(top_error_points, 1):
                    if isinstance(point, dict):
                        outline = point.get("outline", "未知知识点")
                        error_count = point.get("error_count", 0)
                        detail = point.get("detail", "")

                        analysis_report += f"**{i}. {outline}**\n"
                        analysis_report += f"- 错误次数: {error_count}\n"
                        if detail:
                            analysis_report += f"- 知识点详情: {detail}\n"
                        analysis_report += "\n"
                    else:
                        analysis_report += f"**{i}. 数据格式错误: {point}**\n\n"
            else:
                analysis_report += "未发现明显的错误模式\n\n"

            # 所有错误知识点统计
            all_error_points = error_analysis.get("error_knowledge_points", [])
            if all_error_points and isinstance(all_error_points, list):
                analysis_report += "### 📚 所有错误知识点统计\n\n"
                analysis_report += "| 知识点 | 错误次数 | 错误示例 |\n"
                analysis_report += "|--------|----------|----------|\n"
                for point in all_error_points:
                    if isinstance(point, dict):
                        outline = point.get("outline", "未知知识点")
                        error_count = point.get("error_count", 0)
                        examples = point.get("error_examples", [])
                        example_text = "; ".join(examples[:2]) if examples else "无"
                        if len(examples) > 2:
                            example_text += "..."
                        analysis_report += (
                            f"| {outline} | {error_count} | {example_text} |\n"
                        )
                    else:
                        analysis_report += "| 数据格式错误 | - | - |\n"
                analysis_report += "\n"
            else:
                analysis_report += "### 📚 所有错误知识点统计\n\n"
                analysis_report += "暂无详细错误知识点数据\n\n"

            analysis_report += "### 💡 分析建议\n\n"
            # 生成针对性的教学建议
            teaching_suggestions = ai_processor.generate_teaching_suggestions(
                grading_results
            )
            analysis_report += teaching_suggestions

            # 保存分析建议到session
            self.current_session.data["teaching_suggestions"] = teaching_suggestions
            self.current_session.save()

            return analysis_report

        except Exception as e:
            return f"分析错误时出错: {str(e)}"

    def regenerate_with_new_session(self):
        """基于错误知识点创建新会话并生成题目"""
        # 检查AI组件是否可用
        if ai_processor is None or practice_manager is None:
            return "⚠️ AI功能不可用，请检查API密钥配置", [], ""

        try:
            # 检查是否有批改结果
            grading_results = self.current_session.data.get("grading_results", [])
            if not grading_results:
                return "请先批改学生答案", [], ""

            # 分析错误知识点
            error_analysis = ai_processor.analyze_error_knowledge_points(
                grading_results
            )

            # 获取错误最多的知识点
            top_error_points = error_analysis.get("top_error_points", [])
            if not top_error_points:
                return "未发现明显的错误模式", [], ""

            # 创建新的会话
            new_session = CompleteSession()
            session_path = new_session.initialize()

            # 根据错误知识点生成练习
            error_knowledge_points = [point["outline"] for point in top_error_points]
            practice = practice_manager.create_practice_by_knowledge_points(
                title=f"针对性练习 - {', '.join(error_knowledge_points)}",
                knowledge_points=error_knowledge_points,
                choice_count=2,
                calculation_count=2,
            )

            # 转换为字典格式
            practice_data = practice_manager.practice_to_dict(practice)

            # 更新新会话数据
            new_session.data.update(
                {
                    "prompt": f"基于错误知识点的针对性练习: {', '.join(error_knowledge_points)}",
                    "knowledge_points": error_knowledge_points,
                    "practice_data": practice_data,
                    "parent_session": self.current_session.session_path,  # 记录父会话
                    "error_analysis": error_analysis,
                }
            )
            new_session.save()

            # 生成Markdown
            practice_markdown = render_markdown(practice_data)

            # 生成结果文本
            result_text = "成功创建新会话并生成针对性练习！\n\n"
            result_text += f"新会话: {os.path.basename(session_path)}\n\n"
            result_text += f"错误知识点: {', '.join(error_knowledge_points)}\n\n"
            result_text += f"题目数量: {len(practice_data['sections'])} 个部分\n"

            for section in practice_data["sections"]:
                result_text += (
                    f"  - {section['name']}: {len(section['questions'])} 题\n"
                )

            # 更新当前会话为新会话
            self.current_session = new_session

            return (
                result_text,
                self.current_session.get_images(),
                practice_markdown,
                session_path,  # 返回新会话路径
            )

        except Exception as e:
            return f"创建新会话时出错: {str(e)}", [], "", None

    def _is_question_incorrect(self, result: Dict) -> bool:
        """判断题目是否错误，兼容选择题和计算题的不同字段"""
        question_type = result.get("question_type", "")

        if question_type == "choice":
            return not result.get("is_correct", True)
        elif question_type == "calculation":
            return not result.get("overall_correct", True)
        else:
            # 默认使用 is_correct 字段
            return not result.get("is_correct", True)

    def _generate_grading_report(
        self, grading_results: List[Dict], student_answers: List[Dict]
    ) -> str:
        """生成批改报告（Markdown格式，支持LaTeX）"""
        if not grading_results:
            return "## 📊 批改报告\n\n没有批改结果"

        # 按学生分组统计
        student_stats = {}
        student_grading_results = {}

        # 从grading_results中提取学生信息并分组
        for result in grading_results:
            student_name = result.get("student_name", "未知学生")
            student_id = result.get("student_id", "unknown")

            if student_id not in student_grading_results:
                student_grading_results[student_id] = {
                    "name": student_name,
                    "results": [],
                }

            student_grading_results[student_id]["results"].append(result)

        # 从student_answers中提取题目位置信息
        student_question_positions = {}
        for student_answer in student_answers:
            student_id = student_answer.get("student_id", "unknown")
            sections = student_answer.get("sections", [])

            # 从sections中提取位置信息
            question_positions = []
            for section in sections:
                questions = section.get("questions", [])
                for i, question in enumerate(questions):
                    positions = question.get("positions", {})
                    if positions:
                        # 获取归一化坐标
                        answer_bbox_2d = positions.get("answer_bbox_2d", [0, 0, 0, 0])

                        # 需要图片尺寸来转换坐标，这里暂时使用归一化坐标显示
                        # 实际使用时需要根据图片尺寸转换
                        question_positions.append(
                            {
                                "question_number": str(i + 1),
                                "question_type": section.get("type", ""),
                                "bbox_2d": positions.get("bbox_2d", [0, 0, 0, 0]),
                                "answer_bbox_2d": answer_bbox_2d,
                                "x": 0,  # 占位符，实际应从转换后的坐标获取
                                "y": 0,  # 占位符，实际应从转换后的坐标获取
                                "width": 100,
                                "height": 100,
                                "confidence": positions.get("confidence", 0.5),
                            }
                        )

            if question_positions:
                student_question_positions[student_id] = question_positions

        # 计算每个学生的统计信息
        for student_id, data in student_grading_results.items():
            results = data["results"]
            student_name = data["name"]

            # 统计该学生的答题情况
            total_questions = len(results)
            correct_answers = sum(
                1 for result in results if self._is_question_correct(result)
            )

            student_accuracy = (
                round(correct_answers / total_questions * 100, 1)
                if total_questions > 0
                else 0
            )

            student_stats[student_name] = {
                "correct": correct_answers,
                "total": total_questions,
                "accuracy": student_accuracy,
                "results": results,
            }

        # 计算总体统计
        total_students = len(student_stats)
        total_questions = len(grading_results)
        total_correct = sum(
            1 for result in grading_results if self._is_question_correct(result)
        )
        overall_accuracy = (
            round(total_correct / total_questions * 100, 1)
            if total_questions > 0
            else 0
        )

        report = "## 📊 批改报告\n\n"
        report += (
            f"**批改时间:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        # 总体统计
        report += "### 📈 总体统计\n\n"
        report += f"- **学生数量:** {total_students}\n"
        report += f"- **总题数:** {total_questions}\n"
        report += f"- **总正确数:** {total_correct}\n"
        report += f"- **总体正确率:** {overall_accuracy}%\n\n"

        # 学生个人统计表格
        report += "### 👥 学生答题情况\n\n"
        report += "| 学生 | 正确题数 | 总题数 | 正确率 |\n"
        report += "|------|----------|--------|--------|\n"

        for student_name, stats in student_stats.items():
            report += f"| {student_name} | {stats['correct']} | {stats['total']} | {stats['accuracy']}% |\n"

        report += "\n"

        # 按题目详细展示答题情况（表格形式）
        report += "### 📝 详细答题情况\n\n"

        # 收集所有题目信息（去重，确保每道题只出现一次）
        all_questions = []
        seen_questions = set()

        # 按题目类型分组并去重
        choice_questions = []
        calculation_questions = []

        for result in grading_results:
            question_id = result.get("question_id", "")
            question_type = result.get("question_type", "")
            question_text = result.get("question_text", "")

            if question_id and question_id not in seen_questions:
                seen_questions.add(question_id)

                if question_type == "choice":
                    choice_questions.append(
                        {
                            "id": question_id,
                            "text": question_text,
                            "knowledge_points": result.get("knowledge_points", []),
                        }
                    )
                elif question_type == "calculation":
                    calculation_questions.append(
                        {
                            "id": question_id,
                            "text": question_text,
                            "knowledge_points": result.get("knowledge_points", []),
                        }
                    )

        # 添加选择题到总题目列表
        for i, question in enumerate(choice_questions, 1):
            all_questions.append(
                {
                    "id": question["id"],
                    "type": "选择题",
                    "number": i,
                    "text": question["text"],
                    "knowledge_points": question["knowledge_points"],
                }
            )

        # 添加计算题到总题目列表
        for i, question in enumerate(calculation_questions, 1):
            all_questions.append(
                {
                    "id": question["id"],
                    "type": "计算题",
                    "number": i,
                    "text": question["text"],
                    "knowledge_points": question["knowledge_points"],
                }
            )

        if all_questions:
            # 创建表格 - 题目作为列，学生作为行
            report += "| 学生 |"
            for i, question in enumerate(all_questions, 1):
                report += f" 题目{i} |"
            report += "\n"

            report += "|------|"
            for _ in all_questions:
                report += "--------|"
            report += "\n"

            # 为每个学生添加一行
            for student_name, stats in student_stats.items():
                report += f"| {student_name} |"

                # 获取该学生的所有答题结果
                student_results = {r.get("question_id"): r for r in stats["results"]}

                for question in all_questions:
                    question_id = question["id"]
                    if question_id in student_results:
                        result = student_results[question_id]
                        is_correct = self._is_question_correct(result)
                        status = "✅" if is_correct else "❌"
                        report += f" {status} |"
                    else:
                        report += " - |"
                report += "\n"

            report += "\n"

        # 添加题目详情
        report += "#### 题目详情\n\n"

        for i, question in enumerate(all_questions, 1):
            report += f"**题目{i}:** {question['text']}\n"
        report += "\n"

        # 添加题目位置信息
        if student_question_positions:
            report += "### 📍 题目位置信息\n\n"
            report += "以下是通过AI检测到的题目在图片中的位置信息：\n\n"

            for student_id, positions in student_question_positions.items():
                student_name = student_grading_results.get(student_id, {}).get(
                    "name", "未知学生"
                )
                report += f"**{student_name}:**\n"
                report += "| 题目 | 归一化坐标 (x1,y1,x2,y2) | 答题区域归一化坐标 | 置信度 |\n"
                report += "|------|----------|----------|--------|\n"

                for pos in positions:
                    question_num = pos.get("question_number", "")
                    bbox_2d = pos.get("bbox_2d", [0, 0, 0, 0])
                    answer_bbox_2d = pos.get("answer_bbox_2d", [0, 0, 0, 0])
                    confidence = pos.get("confidence", 0)

                    # 格式化归一化坐标显示（保留3位小数）
                    bbox_str = f"({bbox_2d[0]:.3f},{bbox_2d[1]:.3f},{bbox_2d[2]:.3f},{bbox_2d[3]:.3f})"
                    answer_bbox_str = f"({answer_bbox_2d[0]:.3f},{answer_bbox_2d[1]:.3f},{answer_bbox_2d[2]:.3f},{answer_bbox_2d[3]:.3f})"

                    report += f"| {question_num} | {bbox_str} | {answer_bbox_str} | {confidence:.2f} |\n"

                report += "\n"

        return report

    def _is_question_correct(self, result: Dict) -> bool:
        """判断题目是否正确，兼容选择题和计算题的不同字段"""
        question_type = result.get("question_type", "")

        if question_type == "choice":
            return result.get("is_correct", False)
        elif question_type == "calculation":
            return result.get("overall_correct", False)
        else:
            # 默认使用 is_correct 字段
            return result.get("is_correct", False)

    def load_session(self, session_path: str):
        """加载历史会话"""
        if not session_path:
            return "", "", "", [], "", "", []

        try:
            if not self.current_session.load_from_path(session_path):
                return "会话数据不存在", "", "", [], "", "", []

            # 格式化显示
            data = self.current_session.data
            result_text = "已加载会话数据\n\n"
            result_text += f"出题要求: {data.get('prompt', '')}\n"
            result_text += f"知识点: {', '.join(data.get('knowledge_points', []))}\n"
            # result_text += f"学生答案数量: {len(data.get('student_answers', []))}\n"
            # result_text += f"批改结果数量: {len(data.get('grading_results', []))}\n"

            # 生成Markdown
            practice_data = data.get("practice_data", {})
            practice_markdown = render_markdown(practice_data) if practice_data else ""

            # 生成批改报告
            grading_results = data.get("grading_results", [])
            student_answers = data.get("student_answers", [])
            grading_report = self._generate_grading_report(
                grading_results, student_answers
            )

            # 生成错误分析报告
            # 实时计算错误分析
            if grading_results and ai_processor is not None:
                error_analysis = ai_processor.analyze_error_knowledge_points(
                    grading_results
                )

                # 生成分析报告
                analysis_report = "## 📊 错误分析报告\n\n"

                # 总体错误统计
                total_errors = sum(
                    1
                    for result in grading_results
                    if self._is_question_incorrect(result)
                )
                analysis_report += f"**总错误数:** {total_errors}\n\n"

                # 按题目类型统计错误
                choice_errors = sum(
                    1
                    for result in grading_results
                    if self._is_question_incorrect(result)
                    and result.get("question_type") == "choice"
                )
                calculation_errors = sum(
                    1
                    for result in grading_results
                    if self._is_question_incorrect(result)
                    and result.get("question_type") == "calculation"
                )

                analysis_report += "### 📈 错误类型统计\n\n"
                analysis_report += f"- **选择题错误:** {choice_errors} 题\n"
                analysis_report += f"- **计算题错误:** {calculation_errors} 题\n\n"

                # 错误最多的知识点
                if isinstance(error_analysis, dict):
                    top_error_points = error_analysis.get("top_error_points", [])
                    if top_error_points:
                        analysis_report += "### 🎯 错误最多的知识点\n\n"
                        for i, point in enumerate(top_error_points, 1):
                            if isinstance(point, dict):
                                outline = point.get("outline", "未知知识点")
                                error_count = point.get("error_count", 0)
                                detail = point.get("detail", "")
                                analysis_report += f"**{i}. {outline}**\n"
                                analysis_report += f"- 错误次数: {error_count}\n"
                                if detail:
                                    analysis_report += f"- 知识点详情: {detail}\n"
                                analysis_report += "\n"
                    else:
                        analysis_report += "### 🎯 错误最多的知识点\n\n"
                        analysis_report += "未发现明显的错误模式\n\n"

                    # 所有错误知识点统计
                    all_error_points = error_analysis.get("error_knowledge_points", [])
                    if all_error_points and isinstance(all_error_points, list):
                        analysis_report += "### 📚 所有错误知识点统计\n\n"
                        analysis_report += "| 知识点 | 错误次数 | 错误示例 |\n"
                        analysis_report += "|--------|----------|----------|\n"
                        for point in all_error_points:
                            if isinstance(point, dict):
                                outline = point.get("outline", "未知知识点")
                                error_count = point.get("error_count", 0)
                                examples = point.get("error_examples", [])
                                example_text = (
                                    "; ".join(examples[:2]) if examples else "无"
                                )
                                if len(examples) > 2:
                                    example_text += "..."
                                analysis_report += (
                                    f"| {outline} | {error_count} | {example_text} |\n"
                                )
                        analysis_report += "\n"

                analysis_report += "### 💡 分析建议\n\n"
                # 优先使用保存的分析建议，如果没有则重新生成
                teaching_suggestions = data.get("teaching_suggestions")
                if not teaching_suggestions:
                    teaching_suggestions = ai_processor.generate_teaching_suggestions(
                        grading_results
                    )
                    # 保存新生成的分析建议
                    self.current_session.data["teaching_suggestions"] = (
                        teaching_suggestions
                    )
                    self.current_session.save()
                analysis_report += teaching_suggestions
            else:
                analysis_report = (
                    "## 📊 错误分析\n\n点击上方按钮开始分析学生答题错误..."
                )

            # 检查是否有题目位置信息，如果有则重新生成标记图片
            marked_images = data.get("marked_images", [])
            has_question_positions = any(
                any(
                    question.get("positions")
                    for section in student.get("sections", [])
                    for question in section.get("questions", [])
                )
                for student in student_answers
            )

            if has_question_positions and grading_results and image_marker is not None:
                print("🔄 检测到题目位置信息，重新生成标记图片...")
                try:
                    # 重新生成标记图片
                    marked_images = self._regenerate_marked_images_with_positions(
                        grading_results, student_answers, practice_data
                    )
                    if marked_images:
                        # 更新session数据
                        self.current_session.data["marked_images"] = marked_images
                        self.current_session.save()
                        print(f"✅ 已重新生成 {len(marked_images)} 张标记图片")
                except Exception as e:
                    print(f"❌ 重新生成标记图片失败: {e}")
                    # 如果重新生成失败，使用原有的图片
                    pass

            # 如果marked_images为空但存在graded_images目录，则从目录中加载
            if not marked_images and self.current_session.session_path:
                graded_dir = os.path.join(
                    self.current_session.session_path, "graded_images"
                )
                if os.path.exists(graded_dir):
                    marked_images = []
                    for file in os.listdir(graded_dir):
                        if file.lower().endswith(
                            (".jpg", ".jpeg", ".png", ".gif", ".bmp")
                        ):
                            marked_images.append(os.path.join(graded_dir, file))
                    # 按文件名排序
                    marked_images.sort()

            return (
                data.get("prompt", ""),
                result_text,
                grading_report,
                self.current_session.get_images(),
                practice_markdown,
                analysis_report,
                marked_images,
            )

        except Exception as e:
            return (
                f"加载会话数据时出错: {str(e)}",
                "",
                "",
                [],
                "",
                "## 📊 错误分析\n\n点击上方按钮开始分析学生答题错误...",
                [],
            )

    def _regenerate_marked_images_with_positions(
        self,
        grading_results: List[Dict],
        student_answers: List[Dict],
        practice_data: Dict[str, Any],
    ) -> List[str]:
        """
        使用保存的题目位置信息重新生成标记图片

        Args:
            grading_results: 批改结果列表
            student_answers: 学生答案列表（包含题目位置信息）
            practice_data: 练习数据

        Returns:
            重新生成的标记图片路径列表
        """
        if not self.current_session.session_path:
            return []

        marked_images = []

        # 获取原始图片路径
        original_images = self.current_session.get_images()
        if not original_images:
            return []

        # 为每张图片重新生成标记
        for i, image_path in enumerate(original_images):
            try:
                # 找到对应的学生答案和题目位置
                student_answer = None
                question_positions = None

                # 找到对应的学生和批改结果
                current_student_id = None
                for student in student_answers:
                    student_id = student.get("student_id", "")
                    # 通过student_id找到对应的图片（简化处理，假设按顺序对应）
                    student_index = (
                        int(student_id.split("_")[1]) - 1 if "_" in student_id else 0
                    )
                    if student_index == i:
                        student_answer = student
                        current_student_id = student_id
                        # 从sections中提取位置信息，传入图片路径以获取尺寸
                        question_positions = self._extract_positions_from_sections(
                            student, image_path
                        )
                        break

                if not question_positions:
                    # 如果没有位置信息，使用估算方法
                    question_positions = None

                # 过滤出当前学生的批改结果
                if current_student_id:
                    student_grading_results = [
                        result
                        for result in grading_results
                        if result.get("student_id") == current_student_id
                    ]
                    print(
                        f"重新标记 - 学生 {current_student_id}: 过滤后 {len(student_grading_results)} 个批改结果"
                    )
                else:
                    student_grading_results = grading_results
                    print(f"⚠️ 未找到学生ID，使用所有批改结果")

                # 创建graded_images目录
                graded_dir = os.path.join(
                    self.current_session.session_path, "graded_images"
                )
                os.makedirs(graded_dir, exist_ok=True)

                # 生成输出路径
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                output_path = os.path.join(graded_dir, f"{base_name}_graded.jpg")

                # 重新生成标记图片（使用过滤后的批改结果）
                marked_path = image_marker.mark_image_with_grading_results(
                    image_path,
                    student_grading_results,  # 使用过滤后的结果
                    practice_data,
                    output_path,
                    question_positions,
                    student_answer,  # 传递student_answer参数
                )
                marked_images.append(marked_path)

            except Exception as e:
                print(f"❌ 重新生成图片 {image_path} 失败: {e}")
                continue

        return marked_images

    def _extract_positions_from_sections(
        self, student_answer: Dict[str, Any], image_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        从sections中提取题目位置信息

        Args:
            student_answer: 学生答案数据
            image_path: 图片路径（用于获取图片尺寸）

        Returns:
            题目位置信息列表
        """
        question_positions = []
        sections = student_answer.get("sections", [])

        # 获取图片尺寸（使用 PIL）
        image_width, image_height = None, None
        if image_path:
            try:
                from PIL import Image

                with Image.open(image_path) as img:
                    image_width, image_height = img.size
            except Exception as e:
                print(f"⚠️ 无法读取图片尺寸 {image_path}: {e}")

        for section in sections:
            questions = section.get("questions", [])
            for i, question in enumerate(questions):
                positions = question.get("positions", {})
                if positions:
                    # 检查是否使用新的归一化坐标格式
                    bbox = positions.get("bbox_2d")

                    if bbox and image_width and image_height:
                        # 新格式：使用归一化坐标
                        x1 = bbox[0] * image_width
                        y1 = bbox[1] * image_height
                        x2 = bbox[2] * image_width
                        y2 = bbox[3] * image_height

                        # answer_width = x2 - x1
                        # answer_height = y2 - y1

                        # grading_x = int(x2 + 20)  # 答题区域右侧20像素
                        # grading_y = int(y1 + answer_height / 2)  # 答题区域垂直居中

                        grading_x = int((x2 + x1) / 2) + random.randint(0, 100)
                        grading_y = int((y2 + y1) / 2)
                    else:
                        # 旧格式：使用像素坐标（向后兼容）
                        answer_area = positions.get("answer_area", {})
                        grading_x = (
                            answer_area.get("x", 0) + answer_area.get("width", 0) + 20
                        )
                        grading_y = (
                            answer_area.get("y", 0) + answer_area.get("height", 0) // 2
                        )

                    question_positions.append(
                        {
                            "question_number": str(i + 1),
                            "question_type": section.get("type", ""),
                            "bbox_2d": positions.get("bbox_2d", [0, 0, 0, 0]),
                            "answer_bbox_2d": positions.get(
                                "answer_bbox_2d", [0, 0, 0, 0]
                            ),
                            "x": grading_x,
                            "y": grading_y,
                            "width": 100,
                            "height": 100,
                            "confidence": positions.get("confidence", 0.5),
                        }
                    )

        return question_positions

    def _get_session_choices(self):
        """获取会话列表的choices数据"""
        sessions = get_all_sessions()
        if not sessions:
            return []

        choices = []
        for session in sessions:
            display_name = (
                f"### {session['name']} - {session.get('prompt', '无提示词')[:30]}"
            )
            choices.append((display_name, session["path"]))

        return choices

    def get_sessions_for_dropdown(self, default_value=None):
        """获取会话列表供下拉选择使用"""
        choices = self._get_session_choices()

        return gr.Dropdown(
            choices=choices,
            value=default_value,
            label="选择历史会话",
        )

    def export_practice_to_file(self, practice_markdown_content):
        """导出练习题目为Markdown文件"""
        if not practice_markdown_content or not practice_markdown_content.strip():
            return "请先生成题目", None

        try:
            # 创建导出目录
            export_dir = "exports"
            os.makedirs(export_dir, exist_ok=True)

            # 生成文件名（包含时间戳）
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"数学练习_{timestamp}.md"
            filepath = os.path.join(export_dir, filename)

            # 保存Markdown内容到文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(practice_markdown_content)

            # 返回成功消息和文件路径
            success_msg = f"✅ 题目已导出成功！\n文件保存位置: {filepath}\n文件名: {filename}"
            return success_msg, filepath

        except Exception as e:
            error_msg = f"❌ 导出失败: {str(e)}"
            return error_msg, None

    def get_session_buttons_data(self):
        """获取session按钮数据，返回按钮的显示状态和文本"""
        sessions = get_all_sessions()
        button_data = []

        # 最多显示10个session
        for i in range(10):
            if i < len(sessions):
                session = sessions[i]
                # 获取session的概要信息
                prompt = session.get("prompt", "练习")
                created_at = session.get("created_at", "")

                # 格式化概要文本，限制长度
                if len(prompt) > 20:
                    summary = prompt[:20] + "..."
                else:
                    summary = prompt

                # 格式化显示文本：概要 + 日期时间（精确到秒）
                if created_at:
                    try:
                        # 解析ISO格式时间字符串
                        from datetime import datetime

                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        # 格式化为 YYYY-MM-DD HH:MM:SS
                        formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                        button_text = f"📄 {summary}   {formatted_time}"
                    except:
                        # 如果解析失败，使用原始时间字符串
                        button_text = f"📄 {summary}   {created_at}"
                else:
                    button_text = f"📄 {summary}"

                button_data.append(
                    {
                        "visible": True,
                        "value": button_text,
                        "session_path": session["path"],
                    }
                )
            else:
                button_data.append(
                    {"visible": False, "value": "", "session_path": None}
                )

        return button_data

    def switch_to_session(self, session_path):
        """切换到指定的session"""
        if not session_path:
            return "请选择有效的会话"

        # 加载session数据
        success = self.current_session.load_from_path(session_path)
        if success:
            return f"已切换到会话: {os.path.basename(session_path)}"
        else:
            return f"加载会话失败: {session_path}"


def create_web_app_layout():
    """创建模拟 web 应用布局的 Gradio 页面"""

    # 自定义 CSS 样式
    custom_css = """
    .header-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 15px 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .logo-text {
        font-size: 24px;
        font-weight: bold;
        color: white;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
    }
    
    .nav-container {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        margin-right: 20px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        min-height: 500px;
    }
    
    .nav-item {
        display: block;
        padding: 12px 16px;
        margin: 8px 0;
        background: white;
        border-radius: 8px;
        text-decoration: none;
        color: #333;
        transition: all 0.3s ease;
        border-left: 4px solid transparent;
    }
    
    .nav-item:hover {
        background: #e3f2fd;
        border-left-color: #2196f3;
        transform: translateX(5px);
    }
    
    .nav-item.active {
        background: #2196f3;
        color: white;
        border-left-color: #1976d2;
    }
    
    .main-content {
        background: white;
        border-radius: 10px;
        padding: 30px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        min-height: 500px;
    }
    
    .user-info {
        background: rgba(255, 255, 255, 0.2);
        padding: 10px 15px;
        border-radius: 20px;
        color: white;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .user-avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        color: white;
        font-weight: bold;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        border: 2px solid rgba(255, 255, 255, 0.3);
    }
    
    .user-details {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
    }
    
    .user-name {
        font-size: 14px;
        font-weight: 600;
        margin: 0;
    }
    
    .user-role {
        font-size: 12px;
        opacity: 0.8;
        margin: 0;
    }
    
    .welcome-avatar {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: linear-gradient(135deg, #4caf50 0%, #2e7d32 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        color: white;
        font-weight: bold;
        box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);
        border: 3px solid rgba(255, 255, 255, 0.8);
        transition: all 0.3s ease;
    }
    
    .welcome-avatar:hover {
        transform: scale(1.05);
        box-shadow: 0 6px 20px rgba(76, 175, 80, 0.4);
    }
    
    .welcome-container {
        background: #e8f5e8;
        padding: 20px;
        border-radius: 15px;
        border-left: 4px solid #4caf50;
        display: flex;
        align-items: center;
        gap: 15px;
        transition: all 0.3s ease;
    }
    
    .welcome-container:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }
    
    .stats-card {
        background: linear-gradient(45deg, #ff6b6b, #ee5a24);
        color: white;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        margin: 10px 0;
    }
    
    .stats-card h3 {
        margin: 0 0 10px 0;
        font-size: 18px;
    }
    
    .stats-card .number {
        font-size: 32px;
        font-weight: bold;
        margin: 0;
    }
    
    .nav-button {
        width: 100%;
        margin: 6px 0;
        padding: 14px 18px;
        background: white;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        text-align: left;
        font-size: 15px;
        font-weight: 500;
        color: #333;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
        border-left: 4px solid transparent;
        cursor: pointer;
        position: relative;
        overflow: hidden;
    }
    
    .nav-button::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
        transition: left 0.5s;
    }
    
    .nav-button:hover {
        background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
        border-left-color: #2196f3;
        transform: translateX(8px) translateY(-2px);
        box-shadow: 0 6px 20px rgba(33, 150, 243, 0.15);
        color: #1976d2;
    }
    
    .nav-button:hover::before {
        left: 100%;
    }
    
    .nav-button.active {
        background: linear-gradient(135deg, #2196f3 0%, #1976d2 100%);
        color: white;
        border-left-color: #0d47a1;
        box-shadow: 0 6px 20px rgba(33, 150, 243, 0.4);
        transform: translateX(5px);
    }
    
    .nav-button.active:hover {
        background: linear-gradient(135deg, #1976d2 0%, #0d47a1 100%);
        transform: translateX(8px) translateY(-2px);
    }
    
    .nav-container {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 15px;
        padding: 25px 20px;
        margin-right: 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        min-height: 500px;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    .nav-title {
        color: #2c3e50;
        border-bottom: 3px solid #2196f3;
        padding-bottom: 12px;
        margin-bottom: 25px;
        font-size: 18px;
        font-weight: 700;
        text-align: center;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
        position: relative;
    }
    
    .nav-title::after {
        content: '';
        position: absolute;
        bottom: -3px;
        left: 50%;
        transform: translateX(-50%);
        width: 30px;
        height: 3px;
        background: linear-gradient(90deg, #2196f3, #1976d2);
        border-radius: 2px;
    }
    
    /* 工作区组件样式统一 */
    .gradio-container {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        min-height: 100vh;
    }
    
    /* 输入框样式 */
    .gradio-textbox, .gradio-textbox textarea {
        background: #f8f9fa !important;
        border: 1px solid #e9ecef !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
    }
    
    .gradio-textbox:focus-within, .gradio-textbox textarea:focus {
        border-color: #2196f3 !important;
        box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.1) !important;
    }
    
    /* 按钮样式 */
    .gradio-button {
        background: #2196f3 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 12px 24px !important;
        font-weight: 500 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 2px 4px rgba(33, 150, 243, 0.2) !important;
    }
    
    .gradio-button:hover {
        background: #1976d2 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(33, 150, 243, 0.3) !important;
    }
    
    .gradio-button.secondary {
        background: #f8f9fa !important;
        color: #333 !important;
        border: 1px solid #e9ecef !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
    }
    
    .gradio-button.secondary:hover {
        background: #e3f2fd !important;
        border-color: #2196f3 !important;
        color: #1976d2 !important;
    }
    
    /* 滑块样式 */
    .gradio-slider {
        background: #e3f2fd !important;
    }
    
    .gradio-slider .slider-track {
        background: linear-gradient(90deg, #2196f3, #1976d2) !important;
        border-radius: 4px !important;
    }
    
    .gradio-slider .slider-handle {
        background: #2196f3 !important;
        border: 2px solid white !important;
        box-shadow: 0 2px 6px rgba(33, 150, 243, 0.3) !important;
    }
    
    /* 下拉框样式 */
    .gradio-dropdown {
        background: #f8f9fa !important;
        border: 1px solid #e9ecef !important;
        border-radius: 8px !important;
    }
    
    .gradio-dropdown:focus-within {
        border-color: #2196f3 !important;
        box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.1) !important;
    }
    
    /* 图片上传区域样式 */
    .gradio-image {
        border: 2px dashed #e9ecef !important;
        border-radius: 8px !important;
        background: #f8f9fa !important;
        transition: all 0.3s ease !important;
    }
    
    .gradio-image:hover {
        border-color: #2196f3 !important;
        background: #e3f2fd !important;
    }
    
    /* 画廊样式 */
    .gradio-gallery {
        background: #f8f9fa !important;
        border: 1px solid #e9ecef !important;
        border-radius: 8px !important;
    }
    
    /* 标签样式 */
    .gradio-label {
        color: #333 !important;
        font-weight: 500 !important;
        margin-bottom: 8px !important;
    }
    
    /* 面板样式 */
    .gradio-panel {
        background: white !important;
        border: 1px solid #e9ecef !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
    }
    
    /* 行和列间距 */
    .gradio-row {
        gap: 16px !important;
    }
    
    .gradio-column {
        gap: 16px !important;
    }
    
    /* Session按钮样式 */
    .session-button {
        width: 90% !important;
        margin: 1px 0 !important;
        margin-left: 10% !important;
        padding: 10px 12px !important;
        background: #f8f9fa !important;
        border: 1px solid #e9ecef !important;
        border-radius: 8px !important;
        text-align: left !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        color: #333 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
        white-space: pre-line !important;
        line-height: 1.4 !important;
        min-height: 60px !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
    }
    
    .session-button:hover {
        background: #e3f2fd !important;
        border-color: #2196f3 !important;
        color: #1976d2 !important;
        transform: translateX(3px) !important;
        box-shadow: 0 3px 8px rgba(33, 150, 243, 0.2) !important;
    }
    
    .session-button:active {
        background: #bbdefb !important;
        transform: translateX(1px) !important;
    }

    """

    # 模拟数据
    def get_dashboard_data():
        return {
            "total_students": random.randint(50, 200),
            "active_students": random.randint(20, 80),
            "completed_exercises": random.randint(500, 2000),
            "average_score": round(random.uniform(75, 95), 1)
        }

    def get_recent_activities():
        activities = [
            "学生 李明 完成了代数练习",
            "学生 王小红 提交了作业",
            "学生 张伟 获得了满分",
            "新学生 陈小明 加入了班级",
            "学生 刘芳 完成了几何练习",
            "班级平均分提升了 5 分"
        ]
        return random.sample(activities, 4)

    # 创建数学练习助手应用实例
    app = MathHelperApp()

    # 主页内容生成函数
    def generate_main_page():
        return """
        <div class="main-content">
            <h2 style="color: #333; margin-bottom: 30px;">🎓 AI 数学助手</h2>
            <p style="color: #666; margin-bottom: 20px; font-size: 18px;">欢迎使用AI数学助手！这是一个智能化的数学练习生成和批改系统，帮助教师高效地创建、批改和分析数学练习。</p>
            
            <div style="background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%); padding: 30px; border-radius: 15px; margin-bottom: 30px; text-align: center;">
                <h3 style="color: #1976d2; margin: 0 0 20px 0; font-size: 24px;">🎓 开始使用</h3>
                <p style="color: #666; margin-bottom: 25px; font-size: 16px;">点击左侧导航栏的"📄 生成练习"开始创建您的第一个数学练习</p>
                <div style="display: inline-block; background: #2196f3; color: white; padding: 12px 24px; border-radius: 25px; font-weight: 500; box-shadow: 0 4px 12px rgba(33, 150, 243, 0.3);">
                    → 立即开始
                </div>
            </div>
            
            <div style="background: #f8f9fa; padding: 25px; border-radius: 15px; margin-bottom: 25px;">
                <h3 style="color: #333; margin: 0 0 20px 0; font-size: 20px;">📋 使用流程</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px;">
                    <div style="background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <div style="background: #4caf50; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 15px; font-weight: bold;">1</div>
                        <h4 style="color: #333; margin: 0 0 10px 0;">生成题目</h4>
                        <p style="margin: 0; color: #666; font-size: 14px;">输入出题要求，AI自动生成数学练习</p>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <div style="background: #2196f3; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 15px; font-weight: bold;">2</div>
                        <h4 style="color: #333; margin: 0 0 10px 0;">学生答题</h4>
                        <p style="margin: 0; color: #666; font-size: 14px;">上传学生答题图片，系统自动识别</p>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <div style="background: #ff9800; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 15px; font-weight: bold;">3</div>
                        <h4 style="color: #333; margin: 0 0 10px 0;">智能批改</h4>
                        <p style="margin: 0; color: #666; font-size: 14px;">AI自动批改并提供详细分析报告</p>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <div style="background: #9c27b0; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 15px; font-weight: bold;">4</div>
                        <h4 style="color: #333; margin: 0 0 10px 0;">针对性练习</h4>
                        <p style="margin: 0; color: #666; font-size: 14px;">基于错误分析生成专项练习</p>
                    </div>
                </div>
            </div>
            
            <div style="background: #f8f9fa; padding: 25px; border-radius: 15px;">
                <h3 style="color: #333; margin: 0 0 20px 0; font-size: 20px;">✨ 功能特色</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                    <div style="background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <h4 style="color: #4caf50; margin: 0 0 10px 0;">🤖 AI智能出题</h4>
                        <p style="margin: 0; color: #666; font-size: 14px;">基于知识点自动生成数学练习</p>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <h4 style="color: #2196f3; margin: 0 0 10px 0;">📸 图片识别</h4>
                        <p style="margin: 0; color: #666; font-size: 14px;">OCR识别学生手写答案</p>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <h4 style="color: #ff9800; margin: 0 0 10px 0;">📊 智能批改</h4>
                        <p style="margin: 0; color: #666; font-size: 14px;">自动批改并提供详细分析</p>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <h4 style="color: #9c27b0; margin: 0 0 10px 0;">🎯 针对性练习</h4>
                        <p style="margin: 0; color: #666; font-size: 14px;">基于错误生成专项练习</p>
                    </div>
                </div>
            </div>
        </div>
        """

    # 练习页面内容生成函数
    def generate_practice_page():
        return """
        <div>
            <h2 style="color: #333; margin-bottom: 30px;">📄 生成练习</h2>
        </div>
        """

    def generate_students_page():
        # 模拟学生答题数据
        students_data = [
            {
                "name": "李明",
                "student_id": "2024001",
                "total_questions": 45,
                "correct_answers": 38,
                "accuracy": 84.4,
                "last_activity": "2024-01-26 14:30",
                "status": "积极学习"
            },
            {
                "name": "王小红",
                "student_id": "2024002", 
                "total_questions": 32,
                "correct_answers": 24,
                "accuracy": 75.0,
                "last_activity": "2024-01-25 16:45",
                "status": "需要关注"
            },
            {
                "name": "张伟",
                "student_id": "2024003",
                "total_questions": 52,
                "correct_answers": 49,
                "accuracy": 94.2,
                "last_activity": "2024-01-26 15:20",
                "status": "优秀学生"
            },
            {
                "name": "陈小明",
                "student_id": "2024004",
                "total_questions": 28,
                "correct_answers": 21,
                "accuracy": 75.0,
                "last_activity": "2024-01-24 10:15",
                "status": "需要关注"
            },
            {
                "name": "刘芳",
                "student_id": "2024005",
                "total_questions": 38,
                "correct_answers": 35,
                "accuracy": 92.1,
                "last_activity": "2024-01-26 09:30",
                "status": "积极学习"
            }
        ]

        students_html = """
        <div class="main-content">
            <h2 style="color: #333; margin-bottom: 30px;">👥 学生答题情况</h2>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h3>班级答题统计</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 15px;">
                    <div style="background: white; padding: 15px; border-radius: 8px; text-align: center; border-left: 4px solid #007bff;">
                        <h4 style="margin: 0; color: #007bff;">总答题数</h4>
                        <p style="font-size: 24px; font-weight: bold; margin: 5px 0;">195</p>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 8px; text-align: center; border-left: 4px solid #28a745;">
                        <h4 style="margin: 0; color: #28a745;">平均正确率</h4>
                        <p style="font-size: 24px; font-weight: bold; margin: 5px 0;">84.1%</p>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 8px; text-align: center; border-left: 4px solid #ffc107;">
                        <h4 style="margin: 0; color: #ffc107;">活跃学生</h4>
                        <p style="font-size: 24px; font-weight: bold; margin: 5px 0;">5</p>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 8px; text-align: center; border-left: 4px solid #dc3545;">
                        <h4 style="margin: 0; color: #dc3545;">需要关注</h4>
                        <p style="font-size: 24px; font-weight: bold; margin: 5px 0;">2</p>
                    </div>
                </div>
            </div>
            
            <div style="background: white; border: 1px solid #ddd; border-radius: 10px; overflow: hidden;">
                <div style="background: #f8f9fa; padding: 15px; border-bottom: 1px solid #ddd;">
                    <h3 style="margin: 0; color: #333;">学生答题详情</h3>
                </div>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead style="background: #e9ecef;">
                        <tr>
                            <th style="padding: 15px; text-align: left; border-bottom: 1px solid #ddd;">学生姓名</th>
                            <th style="padding: 15px; text-align: left; border-bottom: 1px solid #ddd;">学号</th>
                            <th style="padding: 15px; text-align: center; border-bottom: 1px solid #ddd;">总题数</th>
                            <th style="padding: 15px; text-align: center; border-bottom: 1px solid #ddd;">正确数</th>
                            <th style="padding: 15px; text-align: center; border-bottom: 1px solid #ddd;">正确率</th>
                            <th style="padding: 15px; text-align: left; border-bottom: 1px solid #ddd;">最后活动</th>
                            <th style="padding: 15px; text-align: center; border-bottom: 1px solid #ddd;">状态</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for student in students_data:
            # 根据正确率设置颜色
            if student["accuracy"] >= 90:
                accuracy_color = "#28a745"
                status_bg = "#d4edda"
                status_color = "#155724"
                status_text = "优秀"
            elif student["accuracy"] >= 80:
                accuracy_color = "#007bff"
                status_bg = "#d1ecf1"
                status_color = "#0c5460"
                status_text = "良好"
            else:
                accuracy_color = "#ffc107"
                status_bg = "#fff3cd"
                status_color = "#856404"
                status_text = "需提升"

            students_html += f"""
                        <tr>
                            <td style="padding: 15px; border-bottom: 1px solid #eee; font-weight: 500;">{student['name']}</td>
                            <td style="padding: 15px; border-bottom: 1px solid #eee;">{student['student_id']}</td>
                            <td style="padding: 15px; border-bottom: 1px solid #eee; text-align: center;">{student['total_questions']}</td>
                            <td style="padding: 15px; border-bottom: 1px solid #eee; text-align: center; color: #28a745; font-weight: bold;">{student['correct_answers']}</td>
                            <td style="padding: 15px; border-bottom: 1px solid #eee; text-align: center; color: {accuracy_color}; font-weight: bold;">{student['accuracy']}%</td>
                            <td style="padding: 15px; border-bottom: 1px solid #eee; color: #666;">{student['last_activity']}</td>
                            <td style="padding: 15px; border-bottom: 1px solid #eee; text-align: center;">
                                <span style="background: {status_bg}; color: {status_color}; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{status_text}</span>
                            </td>
                        </tr>
            """

        students_html += """
                    </tbody>
                </table>
            </div>
            
            <div style="margin-top: 20px; padding: 15px; background: #e3f2fd; border-radius: 8px;">
                <h4 style="color: #1976d2; margin: 0 0 10px 0;">📊 答题趋势分析</h4>
                <p style="margin: 0; color: #666;">最近一周学生答题积极性较高，平均正确率保持在84%以上。建议重点关注正确率低于80%的学生，提供个性化辅导。</p>
            </div>
        </div>
        """
        return students_html

    def generate_settings_page():
        settings_html = """
        <div class="main-content">
            <h2 style="color: #333; margin-bottom: 30px;">⚙️ 教师设置</h2>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h3>基本设置</h3>
                <div style="margin: 15px 0;">
                    <label style="display: block; margin-bottom: 5px; font-weight: 500;">教师姓名:</label>
                    <input type="text" value="张老师" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                </div>
                <div style="margin: 15px 0;">
                    <label style="display: block; margin-bottom: 5px; font-weight: 500;">班级名称:</label>
                    <input type="text" value="七年级(1)班" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                </div>
                <div style="margin: 15px 0;">
                    <label style="display: block; margin-bottom: 5px; font-weight: 500;">教学科目:</label>
                    <input type="text" value="数学" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                </div>
            </div>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h3>教学设置</h3>
                <div style="margin: 10px 0;">
                    <label style="display: flex; align-items: center;">
                        <input type="checkbox" checked style="margin-right: 10px;">
                        学生作业提醒
                    </label>
                </div>
                <div style="margin: 10px 0;">
                    <label style="display: flex; align-items: center;">
                        <input type="checkbox" checked style="margin-right: 10px;">
                        成绩发布通知
                    </label>
                </div>
                <div style="margin: 10px 0;">
                    <label style="display: flex; align-items: center;">
                        <input type="checkbox" style="margin-right: 10px;">
                        家长通知
                    </label>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <button style="background: #007bff; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px;">保存设置</button>
            </div>
        </div>
        """
        return settings_html

    def generate_analytics_page():
        analytics_html = """
        <div class="main-content">
            <h2 style="color: #333; margin-bottom: 30px;">📈 数据分析</h2>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h3>学习效果分析</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 15px;">
                    <div style="background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h4 style="color: #007bff; margin: 0 0 10px 0;">本周学习时长</h4>
                        <p style="font-size: 28px; font-weight: bold; margin: 0; color: #007bff;">42.5小时</p>
                        <p style="color: #666; margin: 5px 0 0 0;">比上周 +15%</p>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h4 style="color: #28a745; margin: 0 0 10px 0;">知识点掌握度</h4>
                        <p style="font-size: 28px; font-weight: bold; margin: 0; color: #28a745;">87%</p>
                        <p style="color: #666; margin: 5px 0 0 0;">较上月 +8%</p>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h4 style="color: #ffc107; margin: 0 0 10px 0;">错题集中度</h4>
                        <p style="font-size: 28px; font-weight: bold; margin: 0; color: #ffc107;">几何</p>
                        <p style="color: #666; margin: 5px 0 0 0;">需要重点讲解</p>
                    </div>
                </div>
            </div>
            
            <div style="background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h3>学生进步排行榜</h3>
                <div style="margin-top: 15px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px; background: #f8f9fa; border-radius: 8px; margin-bottom: 10px;">
                        <div style="display: flex; align-items: center;">
                            <span style="background: #ffd700; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 15px;">1</span>
                            <div>
                                <strong>张伟</strong> - 正确率提升 12%
                            </div>
                        </div>
                        <span style="color: #28a745; font-weight: bold;">+12%</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px; background: #f8f9fa; border-radius: 8px; margin-bottom: 10px;">
                        <div style="display: flex; align-items: center;">
                            <span style="background: #c0c0c0; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 15px;">2</span>
                            <div>
                                <strong>刘芳</strong> - 正确率提升 8%
                            </div>
                        </div>
                        <span style="color: #28a745; font-weight: bold;">+8%</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px; background: #f8f9fa; border-radius: 8px; margin-bottom: 10px;">
                        <div style="display: flex; align-items: center;">
                            <span style="background: #cd7f32; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 15px;">3</span>
                            <div>
                                <strong>李明</strong> - 正确率提升 5%
                            </div>
                        </div>
                        <span style="color: #28a745; font-weight: bold;">+5%</span>
                    </div>
                </div>
            </div>
        </div>
        """
        return analytics_html

    def generate_help_page():
        help_html = """
        <div class="main-content">
            <h2 style="color: #333; margin-bottom: 30px;">❓ 帮助中心</h2>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h3>常见问题</h3>
                <div style="margin-top: 15px;">
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #007bff;">
                        <h4 style="margin: 0 0 10px 0; color: #007bff;">如何查看学生答题情况？</h4>
                        <p style="margin: 0; color: #666;">点击左侧导航的"学生管理"按钮，可以查看所有学生的答题统计和详细情况。</p>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #28a745;">
                        <h4 style="margin: 0 0 10px 0; color: #28a745;">如何导出学生数据？</h4>
                        <p style="margin: 0; color: #666;">在仪表板页面点击"导出数据"按钮，可以下载学生的答题数据Excel文件。</p>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #ffc107;">
                        <h4 style="margin: 0 0 10px 0; color: #ffc107;">如何设置班级信息？</h4>
                        <p style="margin: 0; color: #666;">点击"教师设置"页面，可以修改班级名称、教学科目等基本信息。</p>
                    </div>
                </div>
            </div>
            
            <div style="background: #e3f2fd; padding: 20px; border-radius: 10px;">
                <h3 style="color: #1976d2; margin: 0 0 15px 0;">📞 联系我们</h3>
                <p style="margin: 0 0 10px 0; color: #666;">如有其他问题，请联系技术支持：</p>
                <p style="margin: 0; color: #666;">📧 邮箱：support@aimath-helper.com</p>
                <p style="margin: 5px 0 0 0; color: #666;">📱 电话：400-123-4567</p>
            </div>
        </div>
        """
        return help_html

    # 页面切换函数
    def switch_to_main():
        return (
            gr.HTML(generate_main_page()),
            gr.Button("🏠 主页", elem_classes="nav-button active", variant="secondary"),
            gr.Button("📄 生成练习", elem_classes="nav-button", variant="secondary"),
            gr.Button("👥 学生管理", elem_classes="nav-button", variant="secondary"),
            gr.Button("⚙️ 系统设置", elem_classes="nav-button", variant="secondary"),
            gr.Button("📈 数据分析", elem_classes="nav-button", variant="secondary"),
            gr.Button("❓ 帮助中心", elem_classes="nav-button", variant="secondary"),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
        )

    def switch_to_practice():
        return (
            gr.HTML(generate_practice_page()),
            gr.Button("🏠 主页", elem_classes="nav-button", variant="secondary"),
            gr.Button(
                "📄 生成练习", elem_classes="nav-button active", variant="secondary"
            ),
            gr.Button("👥 学生管理", elem_classes="nav-button", variant="secondary"),
            gr.Button("⚙️ 系统设置", elem_classes="nav-button", variant="secondary"),
            gr.Button("📈 数据分析", elem_classes="nav-button", variant="secondary"),
            gr.Button("❓ 帮助中心", elem_classes="nav-button", variant="secondary"),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=True),
        )

    def switch_to_students():
        return (
            generate_students_page(),
            gr.Button("🏠 主页", elem_classes="nav-button", variant="secondary"),
            gr.Button("📄 生成练习", elem_classes="nav-button", variant="secondary"),
            gr.Button(
                "👥 学生管理", elem_classes="nav-button active", variant="secondary"
            ),
            gr.Button("⚙️ 系统设置", elem_classes="nav-button", variant="secondary"),
            gr.Button("📈 数据分析", elem_classes="nav-button", variant="secondary"),
            gr.Button("❓ 帮助中心", elem_classes="nav-button", variant="secondary"),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    def switch_to_settings():
        return (
            generate_settings_page(),
            gr.Button("🏠 主页", elem_classes="nav-button", variant="secondary"),
            gr.Button("📄 生成练习", elem_classes="nav-button", variant="secondary"),
            gr.Button("👥 学生管理", elem_classes="nav-button", variant="secondary"),
            gr.Button(
                "⚙️ 系统设置", elem_classes="nav-button active", variant="secondary"
            ),
            gr.Button("📈 数据分析", elem_classes="nav-button", variant="secondary"),
            gr.Button("❓ 帮助中心", elem_classes="nav-button", variant="secondary"),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    def switch_to_analytics():
        return (
            generate_analytics_page(),
            gr.Button("🏠 主页", elem_classes="nav-button", variant="secondary"),
            gr.Button("📄 生成练习", elem_classes="nav-button", variant="secondary"),
            gr.Button("👥 学生管理", elem_classes="nav-button", variant="secondary"),
            gr.Button("⚙️ 系统设置", elem_classes="nav-button", variant="secondary"),
            gr.Button(
                "📈 数据分析", elem_classes="nav-button active", variant="secondary"
            ),
            gr.Button("❓ 帮助中心", elem_classes="nav-button", variant="secondary"),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    def switch_to_help():
        return (
            generate_help_page(),
            gr.Button("🏠 主页", elem_classes="nav-button", variant="secondary"),
            gr.Button("📄 生成练习", elem_classes="nav-button", variant="secondary"),
            gr.Button("👥 学生管理", elem_classes="nav-button", variant="secondary"),
            gr.Button("⚙️ 系统设置", elem_classes="nav-button", variant="secondary"),
            gr.Button("📈 数据分析", elem_classes="nav-button", variant="secondary"),
            gr.Button(
                "❓ 帮助中心", elem_classes="nav-button active", variant="secondary"
            ),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    # 用户登录函数
    def user_login(username, password):
        if username and password:
            return f"欢迎回来，{username}！", "已登录"
        else:
            return "请输入用户名和密码", "未登录"

    # 创建界面
    # 自定义主题，与主布局风格保持一致
    custom_theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="purple",
        neutral_hue="slate",
        font=gr.themes.GoogleFont("Inter"),
    ).set(
        # 主要颜色
        button_primary_background_fill="#2196f3",
        button_primary_background_fill_hover="#1976d2",
        button_primary_text_color="#ffffff",
        
        # 输入框样式
        input_background_fill="#f8f9fa",
        input_border_color="#e9ecef",
        input_border_color_focus="#2196f3",
        
        # 面板样式
        panel_background_fill="#ffffff",
        panel_border_color="#e9ecef",
        
        # 文本颜色
        body_text_color="#333333",
        
        # 阴影效果
        shadow_drop="0 2px 4px rgba(0, 0, 0, 0.1)",
        shadow_drop_lg="0 4px 6px rgba(0, 0, 0, 0.1)",
    )

    with gr.Blocks(theme=custom_theme, css=custom_css, title="AI数学助手 - Web应用演示") as demo:

        # Header 部分
        with gr.Row():
            with gr.Column(scale=1):
                gr.HTML("""
                <div class="header-container">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div class="logo-text">🎓 AI 数学助手</div>
                        <div class="user-info">
                            <div class="user-avatar">张</div>
                            <div class="user-details">
                                <p class="user-name">张老师</p>
                                <p class="user-role">数学</p>
                            </div>
                        </div>
                    </div>
                </div>
                """)

        # 主要内容区域
        with gr.Row():
            # 左侧导航栏
            with gr.Column(scale=1, min_width=200):
                nav_main = gr.Button("🏠 主页", elem_classes="nav-button active", variant="secondary")
                nav_practice = gr.Button("📄 生成练习", elem_classes="nav-button", variant="secondary")

                # 历史session按钮容器 - 仅在练习页面显示
                with gr.Column(visible=False) as session_buttons_container:
                    session_buttons = []
                    for i in range(10):  # 最多显示10个历史session
                        with gr.Row():
                            session_btn = gr.Button(
                                value="",
                                variant="secondary",
                                visible=False,
                                elem_classes="session-button",
                            )
                            session_buttons.append(session_btn)

                nav_students = gr.Button("👥 学生管理", elem_classes="nav-button", variant="secondary")
                nav_analytics = gr.Button("📈 数据分析", elem_classes="nav-button", variant="secondary")
                nav_settings = gr.Button("⚙️ 系统设置", elem_classes="nav-button", variant="secondary")
                nav_help = gr.Button("❓ 帮助中心", elem_classes="nav-button", variant="secondary")

            # 右侧工作区
            with gr.Column(scale=4):
                # 用户信息区域 - 仅在主页显示
                with gr.Column(visible=True) as user_info_section:
                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.HTML("""
                            <div class="welcome-container">
                                <div class="welcome-avatar">张</div>
                                <div>
                                    <h3 style="margin: 0 0 8px 0; color: #2e7d32; font-size: 18px;">欢迎回来，张老师！</h3>
                                    <p style="margin: 0; color: #666; font-size: 14px;">您已成功登录系统，可以开始使用各项功能。</p>
                                </div>
                            </div>
                            """)

                # 主要内容显示区域 - 默认显示主页
                main_content = gr.HTML(generate_main_page())

                # 数学练习助手功能区域 - 仅在练习页面显示
                with gr.Column(visible=False) as math_helper_section:
                    # gr.Markdown("# 🎓 AIMath Helper - 数学练习助手")

                    with gr.Row():
                        session_dropdown = gr.Dropdown(
                            choices=[], value=None, label="选择历史会话", scale=4
                        )
                        refresh_sessions_btn = gr.Button(
                            "刷新会话列表", variant="secondary", scale=1
                        )

                    # 分隔线
                    gr.Markdown("---")

                    # 第一步：出题
                    gr.Markdown("## 生成练习题目")

                    with gr.Row():
                        choice_count_input = gr.Slider(
                            label="选择题数量", 
                            minimum=0, 
                            maximum=10, 
                            value=2, 
                            step=1,
                            info="选择0-10之间的数量"
                        )
                        calculation_count_input = gr.Slider(
                            label="计算题数量", 
                            minimum=0, 
                            maximum=10, 
                            value=2, 
                            step=1,
                            info="选择0-10之间的数量"
                        )

                    prompt_input = gr.Textbox(
                        label="出题要求",
                        placeholder="例如：生成关于有理数加法的练习题目",
                        lines=3,
                    )
                    generate_btn = gr.Button("生成题目", variant="primary")

                    with gr.Row():
                        with gr.Column(scale=3):
                            practice_markdown = gr.Markdown(
                                label="练习试卷",
                                value="",
                                visible=True,
                                elem_id="practice_markdown",
                                elem_classes=["practice_md"],
                                show_copy_button=True,
                                container=True,
                                latex_delimiters=[
                                    {"left": "$$", "right": "$$", "display": True},  # 块级数学
                                    {"left": "$", "right": "$", "display": False},  # 行内数学
                                ],
                                height=1000,
                            )
                        with gr.Column(scale=2):
                            result_output = gr.Textbox(label="生成依据", lines=10, interactive=False)

                            with gr.Row():
                                download_pdf_btn = gr.Button(
                                    "📥 下载试卷（PDF）", 
                                    variant="primary",
                                )
                                download_word_btn = gr.Button(
                                    "📥 下载试卷（Word）", 
                                    variant="primary",
                                )

                            # export_markdown_btn = gr.Button(
                            #     "📥 导出题目",
                            #     variant="primary",
                            # )
                            # export_status = gr.Textbox(
                            #     label="导出状态",
                            #     value="",
                            #     interactive=False,
                            #     lines=2,
                            #     visible=True
                            # )
                            # download_file = gr.File(
                            #     label="下载文件",
                            #     visible=False
                            # )

                    gr.Markdown("---")

                    # 第二步：学生答题
                    gr.Markdown("## 上传学生答题结果")

                    with gr.Row():
                        with gr.Column(scale=3):
                            image_input = gr.Image(
                                label="上传学生答题图片",
                                sources=["upload", "clipboard"],
                                type="pil",
                                height=450,
                            )
                        with gr.Column(scale=2):
                            images_gallery = gr.Gallery(
                                label="已保存的图片",
                                show_label=True,
                                elem_id="images_gallery",
                                columns=4,
                                rows=5,
                                height=400,
                                object_fit="cover",
                            )
                            clear_images_btn = gr.Button("清空图片", variant="secondary")

                    process_images_btn = gr.Button("处理学生答题", variant="primary")

                    gr.Markdown("## 批改和分析")

                    with gr.Row():
                        with gr.Column(scale=3):
                            grading_report = gr.Markdown(
                                label="批改报告",
                                show_label=True,
                                value='## 📊 批改报告\n\n上传学生答题图片后，点击"处理学生答题"按钮开始批改...',
                                # visible=True,
                                # elem_id="grading_report",
                                container=True,
                                height=400,
                                latex_delimiters=[
                                    {
                                        "left": "$$",
                                        "right": "$$",
                                        "display": True,
                                    },  # 块级数学
                                    {
                                        "left": "$",
                                        "right": "$",
                                        "display": False,
                                    },  # 行内数学
                                ],
                            )
                        with gr.Column(scale=2):
                            grading_result_gallery = gr.Gallery(
                                label="批改结果图片",
                                show_label=True,
                                elem_id="grading_result_gallery",
                                columns=2,
                                rows=3,
                                height=400,
                                object_fit="cover",
                            )

                    analyze_btn = gr.Button("分析错误知识点", variant="primary")
                    with gr.Row():
                        with gr.Column(scale=3):
                            error_analysis = gr.Markdown(
                                label="错误分析",
                                value="## 📊 错误分析\n\n点击上方按钮开始分析学生答题错误...",
                                visible=True,
                                elem_id="error_analysis",
                                container=True,
                                height=400,
                                latex_delimiters=[
                                    {
                                        "left": "$$",
                                        "right": "$$",
                                        "display": True,
                                    },  # 块级数学
                                    {
                                        "left": "$",
                                        "right": "$",
                                        "display": False,
                                    },  # 行内数学
                                ],
                            )
                        with gr.Column(scale=2):
                            # 第四步：重新出题
                            regenerate_btn = gr.Button(
                                "根据错误重新出题", variant="secondary"
                            )

        # 事件绑定
        def handle_refresh():
            return generate_main_page()

        # 绑定导航事件
        nav_main.click(
            switch_to_main,
            outputs=[
                main_content,
                nav_main,
                nav_practice,
                nav_students,
                nav_settings,
                nav_analytics,
                nav_help,
                math_helper_section,
                user_info_section,
                session_buttons_container,
            ],
        )

        nav_practice.click(
            switch_to_practice,
            outputs=[
                main_content,
                nav_main,
                nav_practice,
                nav_students,
                nav_settings,
                nav_analytics,
                nav_help,
                math_helper_section,
                user_info_section,
                session_buttons_container,
            ],
        )

        nav_students.click(
            switch_to_students,
            outputs=[
                main_content,
                nav_main,
                nav_practice,
                nav_students,
                nav_settings,
                nav_analytics,
                nav_help,
                math_helper_section,
                user_info_section,
                session_buttons_container,
            ],
        )

        nav_settings.click(
            switch_to_settings,
            outputs=[
                main_content,
                nav_main,
                nav_practice,
                nav_students,
                nav_settings,
                nav_analytics,
                nav_help,
                math_helper_section,
                user_info_section,
                session_buttons_container,
            ],
        )

        nav_analytics.click(
            switch_to_analytics,
            outputs=[
                main_content,
                nav_main,
                nav_practice,
                nav_students,
                nav_settings,
                nav_analytics,
                nav_help,
                math_helper_section,
                user_info_section,
                session_buttons_container,
            ],
        )

        nav_help.click(
            switch_to_help,
            outputs=[
                main_content,
                nav_main,
                nav_practice,
                nav_students,
                nav_settings,
                nav_analytics,
                nav_help,
                math_helper_section,
                user_info_section,
                session_buttons_container,
            ],
        )

        # refresh_btn.click(
        #     handle_refresh,
        #     outputs=[main_content]
        # )

        # 数学练习助手事件绑定
        def generate_questions(prompt, choice_count, calculation_count):
            return app.generate_questions_from_prompt(prompt, choice_count, calculation_count)

        def process_images(images):
            report, _ = app.process_student_images(images)
            # 获取标记后的图片
            marked_images = app.current_session.data.get("marked_images", [])
            return report, marked_images

        def analyze_errors():
            return app.analyze_errors_only()

        def regenerate_with_new_session():
            result = app.regenerate_with_new_session()
            # 获取新会话路径（第4个返回值）
            new_session_path = result[3] if len(result) > 3 else None
            # 获取更新后的会话列表，设置新会话为默认值
            updated_sessions = app.get_sessions_for_dropdown(
                default_value=new_session_path
            )
            # 返回前3个结果加上更新后的会话列表（总共4个值）
            return result[:3] + (updated_sessions,)

        def load_session(session_path):
            return app.load_session(session_path)

        def get_sessions():
            return app.get_sessions_for_dropdown()

        def add_image(image):
            if image is None:
                return app.current_session.get_images(), "请先选择或拍摄图片"
            # 保存临时图片
            temp_path = (
                f"temp_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
            )
            image.save(temp_path, "JPEG")
            result = app.current_session.add_image(temp_path)
            os.remove(temp_path)
            return app.current_session.get_images(), result

        def clear_images():
            result = app.current_session.clear_images()
            return app.current_session.get_images(), result

        def export_practice(practice_markdown_content):
            return app.export_practice_to_file(practice_markdown_content)

        def update_session_buttons():
            """更新session按钮的显示状态和文本"""
            button_data = app.get_session_buttons_data()
            updates = []
            for i, data in enumerate(button_data):
                updates.append(gr.update(visible=data["visible"], value=data["value"]))
            return updates

        def handle_session_button_click(button_index):
            """处理session按钮点击事件"""
            button_data = app.get_session_buttons_data()
            if button_index < len(button_data) and button_data[button_index]["visible"]:
                session_path = button_data[button_index]["session_path"]
                if session_path:
                    # 切换到指定的session
                    result = app.load_session(session_path)
                    return result
            # 返回默认的空值，与load_session的返回格式一致
            return "", "请选择有效的会话", "", [], "", "", []

        # 生成题目
        generate_btn.click(
            fn=generate_questions,
            inputs=[prompt_input, choice_count_input, calculation_count_input],
            outputs=[
                result_output,
                images_gallery,
                practice_markdown,
            ],
        )

        # 生成题目后更新session按钮
        generate_btn.click(
            fn=update_session_buttons,
            inputs=[],
            outputs=session_buttons,
        )

        # 导出题目
        # export_markdown_btn.click(
        #     fn=export_practice,
        #     inputs=[practice_markdown],
        #     outputs=[export_status, download_file],
        # )

        # 添加图片
        image_input.change(
            fn=add_image,
            inputs=[image_input],
            outputs=[images_gallery, grading_report],
        )

        # 清空图片
        clear_images_btn.click(
            fn=clear_images,
            inputs=[],
            outputs=[images_gallery, grading_report],
        )

        # 处理学生答题
        process_images_btn.click(
            fn=process_images,
            inputs=[images_gallery],
            outputs=[grading_report, grading_result_gallery],
        )

        # 分析错误
        analyze_btn.click(
            fn=analyze_errors,
            inputs=[],
            outputs=[error_analysis],
        )

        # 重新出题
        regenerate_btn.click(
            fn=regenerate_with_new_session,
            inputs=[],
            outputs=[
                result_output,
                images_gallery,
                practice_markdown,
                session_dropdown,  # 刷新会话列表并选择新会话
            ],
        )

        # 重新出题后更新session按钮
        regenerate_btn.click(
            fn=update_session_buttons,
            inputs=[],
            outputs=session_buttons,
        )

        # 会话选择
        session_dropdown.change(
            fn=load_session,
            inputs=[session_dropdown],
            outputs=[
                prompt_input,
                result_output,
                grading_report,
                images_gallery,
                practice_markdown,
                error_analysis,
                grading_result_gallery,
            ],
        )

        # 刷新会话列表
        refresh_sessions_btn.click(fn=get_sessions, outputs=[session_dropdown])

        # 页面加载时初始化会话列表
        demo.load(fn=get_sessions, outputs=[session_dropdown])

        # 页面加载时初始化session按钮
        demo.load(fn=update_session_buttons, outputs=session_buttons)

        # 为每个session按钮绑定点击事件
        for i, session_btn in enumerate(session_buttons):
            session_btn.click(
                fn=lambda idx=i: handle_session_button_click(idx),
                inputs=[],
                outputs=[
                    prompt_input,
                    result_output,
                    grading_report,
                    images_gallery,
                    practice_markdown,
                    error_analysis,
                    grading_result_gallery,
                ],
            )

        # 添加一些示例交互
        gr.HTML("""
        <div style="margin-top: 20px; padding: 20px; background: #e3f2fd; border-radius: 10px; text-align: center;">
            <h4 style="color: #1976d2; margin-bottom: 10px;">🎉 欢迎使用 AI数学助手 Web应用演示</h4>
        </div>
        """)

    return demo

if __name__ == "__main__":
    # 创建并启动应用
    demo = create_web_app_layout()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        debug=True
    )
