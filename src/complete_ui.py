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

                # 解析学生答案
                practice_data = self.current_session.data.get("practice_data", {})
                student_answer = ai_processor.parse_student_answer_from_ocr(
                    ocr_result["raw_text"], practice_data
                )
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
                            }
                        )
                        section_results.append(grading_result)

                grading_results.extend(section_results)

            # 更新会话数据
            self.current_session.data.update(
                {"student_answers": student_answers, "grading_results": grading_results}
            )
            self.current_session.save()

            # 生成批改报告
            report = self._generate_grading_report(grading_results, student_answers)

            return report, f"已处理 {len(images)} 张图片", ""

        except Exception as e:
            return f"处理图片时出错: {str(e)}", None, ""

    def analyze_errors_and_regenerate(self):
        """分析错误并重新生成题目"""
        try:
            grading_results = self.current_session.data.get("grading_results", [])
            if not grading_results:
                return "请先批改学生答案", None, ""

            # 分析错误知识点
            error_analysis = ai_processor.analyze_error_knowledge_points(
                grading_results
            )

            # 更新会话数据
            self.current_session.data["error_analysis"] = error_analysis
            self.current_session.save()

            # 获取错误最多的知识点
            if isinstance(error_analysis, dict):
                top_error_points = error_analysis.get("top_error_points", [])
            else:
                top_error_points = []
            if not top_error_points:
                return "未发现明显的错误模式", None, ""

            # 根据错误知识点重新生成题目
            error_knowledge_points = [point["outline"] for point in top_error_points]
            practice = practice_manager.create_practice_by_knowledge_points(
                title=f"针对性练习 - {', '.join(error_knowledge_points)}",
                knowledge_points=error_knowledge_points,
                choice_count=2,
                calculation_count=2,
            )

            # 转换为字典格式
            practice_data = practice_manager.practice_to_dict(practice)

            # 更新会话数据
            self.current_session.data["practice_data"] = practice_data
            self.current_session.save()

            # 生成Markdown
            practice_markdown = render_markdown(practice_data)

            # 生成详细的分析报告
            analysis_report = "## 📊 错误分析报告\n\n"

            # 总体错误统计
            total_errors = sum(
                1 for result in grading_results if not result.get("is_correct", True)
            )
            analysis_report += f"**总错误数:** {total_errors}\n\n"

            # 按题目类型统计错误
            choice_errors = sum(
                1
                for result in grading_results
                if not result.get("is_correct", True)
                and result.get("question_type") == "choice"
            )
            calculation_errors = sum(
                1
                for result in grading_results
                if not result.get("is_correct", True)
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

            analysis_report += "### ✅ 后续建议\n\n"
            analysis_report += (
                "已根据错误知识点重新生成针对性练习，建议重点练习上述薄弱环节。"
            )

            return analysis_report, practice_markdown

        except Exception as e:
            return f"分析错误时出错: {str(e)}", None

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

            # 更新会话数据
            self.current_session.data["error_analysis"] = error_analysis
            self.current_session.save()

            # 获取错误最多的知识点
            if isinstance(error_analysis, dict):
                top_error_points = error_analysis.get("top_error_points", [])
            else:
                top_error_points = []

            # 生成详细的分析报告
            analysis_report = "## 📊 错误分析报告\n\n"

            # 总体错误统计
            total_errors = sum(
                1 for result in grading_results if not result.get("is_correct", True)
            )
            analysis_report += f"**总错误数:** {total_errors}\n\n"

            # 按题目类型统计错误
            choice_errors = sum(
                1
                for result in grading_results
                if not result.get("is_correct", True)
                and result.get("question_type") == "choice"
            )
            calculation_errors = sum(
                1
                for result in grading_results
                if not result.get("is_correct", True)
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
            analysis_report += (
                "根据以上错误分析，建议重点关注错误较多的知识点，加强相关练习。"
            )

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
            )

        except Exception as e:
            return f"创建新会话时出错: {str(e)}", None, [], ""

    def _generate_grading_report(
        self, grading_results: List[Dict], student_answers: List[Dict]
    ) -> str:
        """生成批改报告（Markdown格式，支持LaTeX）"""
        if not grading_results:
            return "## 📊 批改报告\n\n没有批改结果"

        # 统计总体情况
        total_questions = len(grading_results)
        correct_answers = sum(
            1 for result in grading_results if result.get("is_correct", False)
        )
        accuracy = (
            round(correct_answers / total_questions * 100, 1)
            if total_questions > 0
            else 0
        )

        # 按学生分组统计
        student_stats = {}
        if len(student_answers) > 1:
            # 如果有多个学生，需要更精确的统计
            for i, student_answer in enumerate(student_answers):
                student_id = f"学生 {i + 1}"
                student_correct = 0
                student_total = 0

                # 统计该学生的答题情况
                # 简化处理：假设每个学生都回答了所有题目
                student_total = len(grading_results)
                student_correct = sum(
                    1 for result in grading_results if result.get("is_correct", False)
                )

                student_accuracy = (
                    round(student_correct / student_total * 100, 1)
                    if student_total > 0
                    else 0
                )
                student_stats[student_id] = {
                    "correct": student_correct,
                    "total": student_total,
                    "accuracy": student_accuracy,
                }
        else:
            # 单个学生的情况
            student_id = "学生"
            student_total = len(grading_results)
            student_correct = sum(
                1 for result in grading_results if result.get("is_correct", False)
            )
            student_accuracy = (
                round(student_correct / student_total * 100, 1)
                if student_total > 0
                else 0
            )
            student_stats[student_id] = {
                "correct": student_correct,
                "total": student_total,
                "accuracy": student_accuracy,
            }

        report = "## 📊 批改报告\n\n"
        report += (
            f"**批改时间:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        # 总体统计
        report += "### 📈 总体统计\n\n"
        report += f"- **学生数量:** {len(student_answers)}\n"
        report += f"- **总题数:** {total_questions}\n"
        report += f"- **正确题数:** {correct_answers}\n"
        report += f"- **总体正确率:** {accuracy}%\n\n"

        # 学生个人统计
        if len(student_answers) > 1:
            report += "### 👥 学生个人统计\n\n"
            report += "| 学生 | 正确题数 | 总题数 | 正确率 |\n"
            report += "|------|----------|--------|--------|\n"
            for student_id, stats in student_stats.items():
                report += f"| {student_id} | {stats['correct']} | {stats['total']} | {stats['accuracy']}% |\n"
            report += "\n"
        else:
            # 单个学生的情况，显示详细信息
            stats = list(student_stats.values())[0]
            report += "### 👤 学生答题情况\n\n"
            report += f"- **正确题数:** {stats['correct']}\n"
            report += f"- **总题数:** {stats['total']}\n"
            report += f"- **正确率:** {stats['accuracy']}%\n\n"

        # 详细结果
        report += "### 📝 详细批改结果\n\n"

        # 按题目类型分组
        choice_results = [
            r for r in grading_results if r.get("question_type") == "choice"
        ]
        calculation_results = [
            r for r in grading_results if r.get("question_type") == "calculation"
        ]

        if choice_results:
            report += "#### 选择题\n\n"
            for i, result in enumerate(choice_results, 1):
                question_text = result.get("question_text", "")
                report += f"**题目 {i}:** {question_text}\n\n"
                report += "- **类型:** 选择题\n"
                report += f"- **结果:** {'✅ 正确' if result.get('is_correct', False) else '❌ 错误'}\n"

                if not result.get("is_correct", False) and result.get("explanation"):
                    report += f"- **错误原因:** {result['explanation']}\n"

                # 添加知识点信息
                knowledge_points = result.get("knowledge_points", [])
                if knowledge_points:
                    kp_names = [
                        kp.get("outline", "")
                        for kp in knowledge_points
                        if isinstance(kp, dict)
                    ]
                    if kp_names:
                        report += f"- **涉及知识点:** {', '.join(kp_names)}\n"

                report += "\n---\n\n"

        if calculation_results:
            report += "#### 计算题\n\n"
            for i, result in enumerate(calculation_results, 1):
                question_text = result.get("question_text", "")
                report += f"**题目 {i}:** {question_text}\n\n"
                report += "- **类型:** 计算题\n"
                report += f"- **结果:** {'✅ 正确' if result.get('is_correct', False) else '❌ 错误'}\n"

                if not result.get("is_correct", False) and result.get("explanation"):
                    report += f"- **错误原因:** {result['explanation']}\n"

                # 添加知识点信息
                knowledge_points = result.get("knowledge_points", [])
                if knowledge_points:
                    kp_names = [
                        kp.get("outline", "")
                        for kp in knowledge_points
                        if isinstance(kp, dict)
                    ]
                    if kp_names:
                        report += f"- **涉及知识点:** {', '.join(kp_names)}\n"

                report += "\n---\n\n"

        return report

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

            return (
                data.get("prompt", ""),
                result_text,
                grading_report,
                self.current_session.get_images(),
                f"会话: {os.path.basename(session_path)}",
                practice_markdown,
            )

        except Exception as e:
            return f"加载会话数据时出错: {str(e)}", "", "", [], "", ""

    def get_sessions_for_dropdown(self):
        """获取会话列表供下拉选择使用"""
        sessions = get_all_sessions()
        if not sessions:
            return gr.Dropdown(choices=[], value=None, label="历史会话")

        choices = []
        for session in sessions:
            display_name = (
                f"### {session['name']} - {session.get('prompt', '无提示词')[:30]}"
            )
            choices.append((display_name, session["path"]))

        return gr.Dropdown(
            choices=choices,
            value=None,
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
            sources=["webcam", "upload", "clipboard"],
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
            value="",
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
            value="",
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
        new_practice_markdown = gr.Markdown(
            label="新练习试卷",
            value="",
            visible=True,
            elem_id="new_practice_markdown",
            latex_delimiters=[
                {"left": "$$", "right": "$$", "display": True},  # 块级数学
                {"left": "$", "right": "$", "display": False},  # 行内数学
            ],
        )

        # 事件绑定
        def generate_questions(prompt):
            return app.generate_questions_from_prompt(prompt)

        def process_images(images):
            return app.process_student_images(images)

        def analyze_errors():
            return app.analyze_errors_only()

        def regenerate_with_new_session():
            return app.regenerate_with_new_session()

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
                new_practice_markdown,
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
            ],
        )

        # 刷新会话列表
        refresh_sessions_btn.click(fn=get_sessions, outputs=[session_dropdown])

        # 页面加载时初始化会话列表
        demo.load(fn=get_sessions, outputs=[session_dropdown])

    return demo


# 创建界面
demo = create_interface()
