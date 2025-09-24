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

            for i, image in enumerate(images):
                # 保存图片到会话
                image_path = f"temp_image_{i}.jpg"
                image.save(image_path, "JPEG")
                self.current_session.add_image(image_path)
                os.remove(image_path)  # 删除临时文件

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
            top_error_points = error_analysis.get("top_error_points", [])
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

            # 生成分析报告
            analysis_report = "错误分析报告\n\n"
            analysis_report += "错误最多的知识点:\n"
            for point in top_error_points:
                analysis_report += (
                    f"- {point['outline']}: {point['error_count']} 次错误\n"
                )

            analysis_report += "\n已根据错误知识点重新生成针对性练习。"

            return analysis_report, practice_markdown

        except Exception as e:
            return f"分析错误时出错: {str(e)}", None

    def _generate_grading_report(
        self, grading_results: List[Dict], student_answers: List[Dict]
    ) -> str:
        """生成批改报告"""
        if not grading_results:
            return "没有批改结果"

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

        report = "📊 批改报告\n"
        report += "=" * 50 + "\n\n"
        report += f"批改时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"学生数量: {len(student_answers)}\n"
        report += f"总题数: {total_questions}\n"
        report += f"正确题数: {correct_answers}\n"
        report += f"正确率: {accuracy}%\n\n"

        # 详细结果
        report += "📝 详细结果:\n"
        report += "=" * 50 + "\n"

        for i, result in enumerate(grading_results, 1):
            report += f"题目 {i}: {result.get('question_text', '')[:50]}\n"
            report += f"类型: {result.get('question_type', '')}\n"
            report += (
                f"结果: {'✅ 正确' if result.get('is_correct', False) else '❌ 错误'}\n"
            )

            if not result.get("is_correct", False) and result.get("explanation"):
                report += f"错误原因: {result['explanation']}\n"

            report += "\n"

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
        grading_report = gr.Textbox(label="批改报告", lines=20, interactive=False)

        analyze_btn = gr.Button("分析错误知识点", variant="primary")
        error_analysis = gr.Textbox(label="错误分析", lines=10, interactive=False)

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
            return app.analyze_errors_and_regenerate()

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
            outputs=[error_analysis, new_practice_markdown],
        )

        # 重新出题
        regenerate_btn.click(
            fn=analyze_errors,
            inputs=[],
            outputs=[error_analysis, new_practice_markdown],
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
