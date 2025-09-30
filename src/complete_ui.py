import gradio as gr
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

# 初始化组件
qb = QuestionBank()
practice_manager = PracticeManager()
ai_processor = AIProcessor()


class MathHelperApp:
    """数学练习助手应用"""

    def __init__(self):
        self.current_session = CompleteSession()

    def generate_questions_from_prompt(self, prompt: str):
        """根据提示词生成题目"""
        if not prompt.strip():
            return "请输入出题要求", None, None, [], ""

        try:
            # 初始化会话
            session_path = self.current_session.initialize()

            # 使用AI提取知识点
            knowledge_points = ai_processor.extract_knowledge_points(prompt)
            knowledge_point_names = [kp.outline for kp in knowledge_points]

            # 根据知识点生成练习
            practice = practice_manager.create_practice_by_knowledge_points(
                title="练习试题",
                knowledge_points=knowledge_point_names,
                choice_count=2,
                calculation_count=2,
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
                f"会话: {os.path.basename(session_path)}",
                self.current_session.get_images(),
                practice_markdown,
            )

        except Exception as e:
            return f"生成题目时出错: {str(e)}", None, [], ""

    def process_student_images(self, images):
        """处理学生答题图片"""
        if not images:
            return "请上传学生答题图片", None, ""

        try:
            if not self.current_session.session_path:
                return "请先生成题目", None, ""

            # 处理每张图片
            student_answers = []
            grading_results = []

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

            # 更新会话数据
            self.current_session.data.update(
                {"student_answers": student_answers, "grading_results": grading_results}
            )
            self.current_session.save()

            # 打印调试信息，确保学生信息正确保存
            print(f"保存的grading_results数量: {len(grading_results)}")
            if grading_results:
                print(
                    f"第一个结果的学生信息: {grading_results[0].get('student_name', '未找到')}"
                )
                print(
                    f"第一个结果的学生ID: {grading_results[0].get('student_id', '未找到')}"
                )

            # 生成批改报告
            report = self._generate_grading_report(grading_results, student_answers)

            return report, f"已处理 {len(images)} 张图片", ""

        except Exception as e:
            return f"处理图片时出错: {str(e)}", None, ""

    def analyze_errors_only(self):
        """只分析错误知识点，不生成新练习"""
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
        try:
            # 检查是否有批改结果
            grading_results = self.current_session.data.get("grading_results", [])
            if not grading_results:
                return "请先批改学生答案", None, None, [], ""

            # 分析错误知识点
            error_analysis = ai_processor.analyze_error_knowledge_points(
                grading_results
            )

            # 获取错误最多的知识点
            top_error_points = error_analysis.get("top_error_points", [])
            if not top_error_points:
                return "未发现明显的错误模式", None, None, [], ""

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
                f"会话: {os.path.basename(session_path)}",
                self.current_session.get_images(),
                practice_markdown,
                session_path,  # 返回新会话路径
            )

        except Exception as e:
            return f"创建新会话时出错: {str(e)}", None, [], "", None

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
            return "", "", "", [], "", ""

        try:
            if not self.current_session.load_from_path(session_path):
                return "会话数据不存在", "", "", [], "", ""

            # 格式化显示
            data = self.current_session.data
            result_text = "已加载会话数据\n\n"
            result_text += f"出题要求: {data.get('prompt', '')}\n"
            result_text += f"知识点: {', '.join(data.get('knowledge_points', []))}\n"
            result_text += f"学生答案数量: {len(data.get('student_answers', []))}\n"
            result_text += f"批改结果数量: {len(data.get('grading_results', []))}\n"

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
            if grading_results:
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

            return (
                data.get("prompt", ""),
                result_text,
                grading_report,
                self.current_session.get_images(),
                f"会话: {os.path.basename(session_path)}",
                practice_markdown,
                analysis_report,
            )

        except Exception as e:
            return (
                f"加载会话数据时出错: {str(e)}",
                "",
                "",
                [],
                "",
                "",
                "## 📊 错误分析\n\n点击上方按钮开始分析学生答题错误...",
            )

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


def create_interface():
    """创建完整的Gradio界面"""
    app = MathHelperApp()

    with gr.Blocks(
        title="AIMath Helper - 完整版",
        theme=gr.themes.Soft(),
        css=".practice_md {width: 750px !important;}",
    ) as demo:
        gr.Markdown("# 🧮 AIMath Helper - 数学练习助手")

        with gr.Row():
            session_dropdown = gr.Dropdown(
                choices=[], value=None, label="选择历史会话", scale=4
            )
            refresh_sessions_btn = gr.Button(
                "刷新会话列表", variant="secondary", scale=1
            )

        current_session_info = gr.Textbox(
            label="当前会话信息", interactive=False, lines=2
        )

        # 分隔线
        gr.Markdown("---")

        # 第一步：出题
        gr.Markdown("## 第一步：生成练习题目")
        prompt_input = gr.Textbox(
            label="出题要求",
            placeholder="例如：生成关于有理数加法的练习题目",
            lines=3,
        )
        generate_btn = gr.Button("生成题目", variant="primary")

        result_output = gr.Textbox(label="生成结果", lines=10, interactive=False)
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
        )

        gr.Markdown("---")

        # 第二步：学生答题
        gr.Markdown("## 第二步：学生答题（上传图片）")
        image_input = gr.Image(
            label="上传学生答题图片",
            sources=["upload", "clipboard"],
            type="pil",
            height=400,
        )

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

        # 第三步：批改和分析
        gr.Markdown("## 第三步：批改和分析")
        grading_report = gr.Markdown(
            label="批改报告",
            value='## 📊 批改报告\n\n上传学生答题图片后，点击"处理学生答题"按钮开始批改...',
            visible=True,
            elem_id="grading_report",
            latex_delimiters=[
                {"left": "$$", "right": "$$", "display": True},  # 块级数学
                {"left": "$", "right": "$", "display": False},  # 行内数学
            ],
        )

        analyze_btn = gr.Button("分析错误知识点", variant="primary")
        error_analysis = gr.Markdown(
            label="错误分析",
            value="## 📊 错误分析\n\n点击上方按钮开始分析学生答题错误...",
            visible=True,
            elem_id="error_analysis",
            latex_delimiters=[
                {"left": "$$", "right": "$$", "display": True},  # 块级数学
                {"left": "$", "right": "$", "display": False},  # 行内数学
            ],
        )

        # 第四步：重新出题
        gr.Markdown("## 第四步：针对性练习")
        regenerate_btn = gr.Button("根据错误重新出题", variant="primary")

        # 事件绑定
        def generate_questions(prompt):
            return app.generate_questions_from_prompt(prompt)

        def process_images(images):
            return app.process_student_images(images)

        def analyze_errors():
            return app.analyze_errors_only()

        def regenerate_with_new_session():
            result = app.regenerate_with_new_session()
            # 获取新会话路径（第5个返回值）
            new_session_path = result[4] if len(result) > 4 else None
            # 获取更新后的会话列表，设置新会话为默认值
            updated_sessions = app.get_sessions_for_dropdown(
                default_value=new_session_path
            )
            # 返回前4个结果加上更新后的会话列表（总共5个值）
            return result[:4] + (updated_sessions,)

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

        # 生成题目
        generate_btn.click(
            fn=generate_questions,
            inputs=[prompt_input],
            outputs=[
                result_output,
                current_session_info,
                images_gallery,
                practice_markdown,
            ],
        )

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
            outputs=[grading_report, current_session_info, error_analysis],
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
                current_session_info,
                images_gallery,
                practice_markdown,
                session_dropdown,  # 刷新会话列表并选择新会话
            ],
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
                current_session_info,
                practice_markdown,
                error_analysis,
            ],
        )

        # 刷新会话列表
        refresh_sessions_btn.click(fn=get_sessions, outputs=[session_dropdown])

        # 页面加载时初始化会话列表
        demo.load(fn=get_sessions, outputs=[session_dropdown])

    return demo


# 创建界面
demo = create_interface()
