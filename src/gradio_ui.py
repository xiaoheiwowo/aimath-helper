import gradio as gr
import os
import datetime
import json
from typing import Optional, List, Dict, Any

# from src.generator import PracticePaperGenerator
# from src.question.model import questions
from src.session import *
from src.session import get_session_images
from src.question.bank import QuestionBank
from src.practice.template import render_markdown

qb = QuestionBank()


class Session:
    """会话管理类，每个实例代表一个独立的会话"""

    def __init__(self, session_id: str = None):
        self.session_id = (
            session_id
            or f"session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}"
        )
        self.session_path: Optional[str] = None
        self.prompt: str = ""
        self.questions_data: List[Dict[str, Any]] = []
        self.practice_markdown: str = ""
        self.grading_report: str = ""
        self.images: List[str] = []
        self.is_initialized = False

    def initialize(self) -> str:
        """初始化会话，创建会话目录"""
        if not self.is_initialized:
            self.session_path = create_session()
            self.is_initialized = True
        return self.session_path

    def load_from_path(self, session_path: str) -> bool:
        """从现有路径加载会话数据"""
        try:
            self.session_path = session_path
            json_path = os.path.join(session_path, "session_data.json")

            if not os.path.exists(json_path):
                return False

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.prompt = data.get("prompt", "")
            self.questions_data = data.get("questions", [])
            self.grading_report = self._generate_grading_report(data)
            self.images = get_session_images(session_path)
            self.practice_markdown = self._generate_practice_markdown()
            self.is_initialized = True

            return True
        except Exception as e:
            print(f"加载会话数据时出错: {str(e)}")
            return False

    def save_data(
        self,
        prompt: str,
        questions_data: List[Dict[str, Any]],
        extra_data: Dict[str, Any] = None,
    ):
        """保存会话数据"""
        if self.session_path:
            save_session_data(self.session_path, prompt, questions_data, extra_data)
            self.prompt = prompt
            self.questions_data = questions_data

    def add_image(self, image) -> tuple:
        """添加图片到当前会话"""
        if image is None:
            return self.images, None, "请先选择或拍摄图片"

        if not self.session_path:
            return self.images, None, "请先创建或选择会话"

        # 创建 images 子目录
        images_dir = os.path.join(self.session_path, "images")
        os.makedirs(images_dir, exist_ok=True)

        # 保存图片到 session 目录
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        image_filename = f"image_{timestamp}.jpg"
        image_path = os.path.join(images_dir, image_filename)

        # 保存图片
        image.save(image_path, "JPEG")

        # 更新图片列表
        self.images = get_session_images(self.session_path)

        return self.images, None, f"已添加图片，当前共有 {len(self.images)} 张图片"

    def clear_images(self) -> tuple:
        """清空图片库"""
        if not self.session_path:
            return self.images, "请先创建或选择会话"

        # 清空 images 目录
        images_dir = os.path.join(self.session_path, "images")
        if os.path.exists(images_dir):
            for file in os.listdir(images_dir):
                file_path = os.path.join(images_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)

        self.images = []
        return self.images, "图片库已清空"

    def _generate_practice_markdown(self) -> str:
        """生成练习试卷的 Markdown 内容"""
        if not self.questions_data:
            return ""

        practice_data = convert_questions_to_practice_from_dict(
            self.questions_data, f"数学练习 - {self.prompt[:20]}"
        )
        return render_markdown(practice_data)

    def _generate_grading_report(self, data: Dict[str, Any]) -> str:
        """生成批改报告"""
        grading_data = data.get("type") == "grading"
        if grading_data:
            grading_report = "恢复的批改数据:\n"
            grading_report += f"批改时间: {data.get('created_at', '未知')}\n"
            grading_report += f"图片数量: {data.get('images_count', 0)}\n"
            grading_report += f"总题数: {data.get('total_questions', 0)}\n"
            grading_report += f"正确数: {data.get('correct_answers', 0)}\n"
            grading_report += f"正确率: {data.get('overall_accuracy', 0)}%\n\n"

            results = data.get("results", [])
            for result in results:
                grading_report += f"👤 {result.get('student', '未知学生')}\n"
                grading_report += f"   得分: {result.get('score', 0)}%\n"
                grading_report += f"   正确: {result.get('correct_answers', 0)}/{result.get('total_questions', 0)}\n\n"
        else:
            grading_report = "该会话不是批改数据"

        return grading_report

    def get_session_info(self) -> str:
        """获取会话信息"""
        if not self.session_path:
            return "未初始化会话"

        return f"会话: {os.path.basename(self.session_path)}\n创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def convert_questions_to_practice(questions_data, title="数学练习"):
    """将题目数据转换为 Practice 格式"""
    practice_data = {
        "title": title,
        "practice_id": f"practice_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "sections": [],
    }

    # 按题目类型分组
    choice_questions = []
    calculation_questions = []

    for q in questions_data:
        if hasattr(q, "type"):
            if q.type == "choice":
                choice_questions.append(q)
            elif q.type == "calculation":
                calculation_questions.append(q)

    # 添加选择题部分
    if choice_questions:
        choice_section = {
            "name": "一、选择题",
            "type": "choice",
            "question_ids": [q.id for q in choice_questions],
            "questions": [],
        }

        for q in choice_questions:
            question_data = {
                "id": q.id,
                "type": q.type,
                "metadata": {"category": "choice"},
                "question": q.question,
                "knowledge_points": [
                    {"outline": kp.outline, "detail": kp.detail}
                    for kp in q.knowledge_points
                ],
                "choices": [
                    {
                        "id": choice.id,
                        "content": choice.content,
                        "is_correct": choice.is_correct,
                        "explanation": choice.explanation,
                    }
                    for choice in (q.choices or [])
                ],
                "answer": next(
                    (choice.id for choice in (q.choices or []) if choice.is_correct), ""
                ),
            }
            choice_section["questions"].append(question_data)

        practice_data["sections"].append(choice_section)

    # 添加计算题部分
    if calculation_questions:
        calc_section = {
            "name": "二、计算题",
            "type": "calculation",
            "question_ids": [q.id for q in calculation_questions],
            "questions": [],
        }

        for q in calculation_questions:
            question_data = {
                "id": q.id,
                "type": q.type,
                "metadata": {"category": "calculation"},
                "question": q.question,
                "knowledge_points": [
                    {"outline": kp.outline, "detail": kp.detail}
                    for kp in q.knowledge_points
                ],
                "solution_steps": [
                    {"step": step.step} for step in (q.solution_steps or [])
                ],
                "answer": "",  # 计算题答案需要从其他地方获取
            }
            calc_section["questions"].append(question_data)

        practice_data["sections"].append(calc_section)

    return practice_data


def convert_questions_to_practice_from_dict(questions_data, title="数学练习"):
    """将字典格式的题目数据转换为 Practice 格式"""
    practice_data = {
        "title": title,
        "practice_id": f"practice_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "sections": [],
    }

    # 按题目类型分组
    choice_questions = []
    calculation_questions = []

    for q in questions_data:
        if q.get("type") == "choice":
            choice_questions.append(q)
        elif q.get("type") == "calculation":
            calculation_questions.append(q)

    # 添加选择题部分
    if choice_questions:
        choice_section = {
            "name": "一、选择题",
            "type": "choice",
            "question_ids": [q["id"] for q in choice_questions],
            "questions": [],
        }

        for q in choice_questions:
            question_data = {
                "id": q["id"],
                "type": q["type"],
                "metadata": {"category": "choice"},
                "question": q["question"],
                "knowledge_points": q.get("knowledge_points", []),
                "choices": q.get("choices", []),
                "answer": next(
                    (
                        choice["id"]
                        for choice in q.get("choices", [])
                        if choice.get("is_correct")
                    ),
                    "",
                ),
            }
            choice_section["questions"].append(question_data)

        practice_data["sections"].append(choice_section)

    # 添加计算题部分
    if calculation_questions:
        calc_section = {
            "name": "二、计算题",
            "type": "calculation",
            "question_ids": [q["id"] for q in calculation_questions],
            "questions": [],
        }

        for q in calculation_questions:
            question_data = {
                "id": q["id"],
                "type": q["type"],
                "metadata": {"category": "calculation"},
                "question": q["question"],
                "knowledge_points": q.get("knowledge_points", []),
                "solution_steps": q.get("solution_steps", []),
                "answer": "",  # 计算题答案需要从其他地方获取
            }
            calc_section["questions"].append(question_data)

        practice_data["sections"].append(calc_section)

    return practice_data


def generate_math_questions_interface(session: Session, prompt: str):
    """生成数学题目接口，使用 Session 实例"""
    if not prompt.strip():
        return "请输入提示词", None, None, [], ""

    try:
        # 初始化会话
        session_path = session.initialize()

        # 获取题目数据
        questions_objects = qb.get_all_questions()

        # 转换为字典格式用于保存和渲染
        questions_data = []
        for q in questions_objects:
            q_dict = {
                "id": q.id,
                "type": q.type,
                "question": q.question,
                "knowledge_points": [
                    {"outline": kp.outline, "detail": kp.detail}
                    for kp in q.knowledge_points
                ],
                "choices": [
                    {
                        "id": choice.id,
                        "content": choice.content,
                        "is_correct": choice.is_correct,
                        "explanation": choice.explanation,
                    }
                    for choice in (q.choices or [])
                ],
                "solution_steps": [
                    {"step": step.step} for step in (q.solution_steps or [])
                ],
            }
            questions_data.append(q_dict)

        # 保存会话数据
        session.save_data(prompt, questions_data)

        # 更新会话状态
        session.practice_markdown = session._generate_practice_markdown()

        # 格式化显示结果
        result_text = f"成功生成 {len(questions_data)} 道数学题目！\n\n"
        result_text += f"提示词: {prompt}\n\n"

        for i, q in enumerate(questions_data, 1):
            result_text += f"题目 {i}:\n{q['question']}\n"
            if q.get("choices"):
                for choice in q["choices"]:
                    result_text += f"  {choice['id']}. {choice['content']}\n"
            if q.get("solution_steps"):
                result_text += "解答步骤:\n"
                for step in q["solution_steps"]:
                    result_text += f"  {step['step']}\n"
            result_text += "\n" + "=" * 50 + "\n\n"

        return (
            result_text,
            session.get_session_info(),
            session.images,
            session.practice_markdown,
        )

    except Exception as e:
        return f"生成题目时出错: {str(e)}", None, [], ""


def get_sessions_list():
    sessions = get_all_sessions()
    if not sessions:
        return "暂无会话记录"

    result = "所有会话记录:\n\n"
    for session in sessions:
        result += f"📁 {session['name']}\n"
        result += f"   创建时间: {session['created_at']}\n"
        if "prompt" in session:
            result += f"   提示词: {session['prompt'][:]}\n"
        result += f"   路径: {session['path']}\n\n"

    return result


def refresh_sessions():
    """刷新会话列表"""
    return get_sessions_list()


def get_sessions_for_dropdown():
    """获取会话列表供下拉选择使用"""
    sessions = get_all_sessions()
    if not sessions:
        return gr.Dropdown(choices=[], value=None, label="历史会话")

    choices = []
    for session in sessions:
        display_name = f"### {session['name']} - {session.get('prompt', '无提示词')}"
        choices.append((display_name, session["path"]))

    return gr.Dropdown(
        choices=choices,
        value=None,
        label="选择历史会话",
    )


def load_session_data(session: Session, session_path: str):
    """加载指定会话的数据到 Session 实例"""
    if not session_path:
        return "", "", "", [], "", ""

    try:
        # 加载会话数据到 Session 实例
        if not session.load_from_path(session_path):
            return "会话数据不存在", "", "", [], "", ""

        # 格式化题目显示
        if session.questions_data:
            result_text = f"恢复的题目数据 ({len(session.questions_data)} 道题):\n\n"
            for i, q in enumerate(session.questions_data, 1):
                result_text += f"题目 {i}:\n{q.get('question', '')}\n"
                if q.get("solution"):
                    result_text += f"解答: {q['solution']}\n"
                if q.get("answer"):
                    result_text += f"答案: {q['answer']}\n"
                result_text += "\n" + "=" * 50 + "\n\n"
        else:
            result_text = "该会话没有题目数据"

        return (
            session.prompt,
            result_text,
            session.grading_report,
            session.images,
            session.get_session_info(),
            session.practice_markdown,
        )

    except Exception as e:
        return f"加载会话数据时出错: {str(e)}", "", "", [], "", ""


def grade_student_answers(images, reference_answers=None):
    """批改学生答题结果"""
    if not images:
        return "请上传学生答题图片", None

    try:
        # 创建批改会话目录
        session_path = create_session()

        # 模拟批改结果（这里需要根据实际需求实现）
        grading_results = []
        total_questions = 0
        correct_answers = 0

        for i, image in enumerate(images, 1):
            # 这里应该调用实际的图片识别和批改逻辑
            # 目前使用模拟数据
            student_name = f"学生{i}"
            questions_count = 5  # 假设每张图片有5道题
            correct_count = 3 + (i % 3)  # 模拟正确题数

            grading_results.append(
                {
                    "student": student_name,
                    "total_questions": questions_count,
                    "correct_answers": correct_count,
                    "score": round(correct_count / questions_count * 100, 1),
                    "image_path": image,
                }
            )

            total_questions += questions_count
            correct_answers += correct_count

        # 生成批改报告
        report = "📊 批改报告\n"
        report += f"{'=' * 50}\n\n"
        report += f"批改时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"批改图片数量: {len(images)}\n"
        report += f"总题数: {total_questions}\n"
        report += f"总正确数: {correct_answers}\n"
        report += (
            f"整体正确率: {round(correct_answers / total_questions * 100, 1)}%\n\n"
        )

        report += "📝 详细结果:\n"
        report += f"{'=' * 50}\n"
        for result in grading_results:
            report += f"👤 {result['student']}\n"
            report += f"   正确题数: {result['correct_answers']}/{result['total_questions']}\n"
            report += f"   得分: {result['score']}%\n"
            report += f"   图片: {os.path.basename(result['image_path'])}\n\n"

        # 保存批改结果
        grading_data = {
            "type": "grading",
            "images_count": len(images),
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "overall_accuracy": round(correct_answers / total_questions * 100, 1),
            "results": grading_results,
            "created_at": datetime.datetime.now().isoformat(),
        }

        save_session_data(session_path, "图片批改", [], grading_data)

        return report, f"批改会话: {os.path.basename(session_path)}"

    except Exception as e:
        return f"批改过程中出错: {str(e)}", None


def add_image_wrapper(session: Session, image):
    """包装函数，使用 Session 实例添加图片"""
    return session.add_image(image)


def clear_image_wrapper(session: Session):
    """包装函数，使用 Session 实例清空图片"""
    return session.clear_images()


def grade_all_images_wrapper(session: Session):
    """包装函数，使用 Session 实例批改图片"""
    if not session.session_path:
        return "请先创建或选择会话", None

    # 获取当前 session 中的所有图片
    image_paths = session.images

    if not image_paths:
        return "图片库为空，请先添加图片", None

    try:
        # 调用批改函数，直接使用保存的图片路径
        report, session_info = grade_student_answers(image_paths)
        return report, session_info
    except Exception as e:
        return f"批改过程中出错: {str(e)}", None


def create_interface():
    """创建 Gradio Interface，实现会话隔离"""

    # 创建新的 Session 实例
    session = Session()

    def generate_questions(prompt):
        return generate_math_questions_interface(session, prompt)

    def load_session(session_path):
        return load_session_data(session, session_path)

    def add_image(image):
        return add_image_wrapper(session, image)

    def clear_images():
        return clear_image_wrapper(session)

    def grade_images():
        return grade_all_images_wrapper(session)

    def get_sessions():
        return get_sessions_for_dropdown()

    # 创建界面
    with gr.Blocks(title="AIMath Helper", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🧮 AIMath Helper")

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

        prompt_input = gr.Textbox(
            label="提示词",
            placeholder="输入提示词，将为您生成数学题目, 例如：生成5道关于二次方程的题目，难度中等",
            lines=3,
        )

        generate_btn = gr.Button("生成题目", variant="primary")

        result_output = gr.Textbox(label="生成的题目", lines=20, interactive=False)

        practice_markdown = gr.Markdown(
            label="练习试卷",
            value="",
            visible=True,
            elem_id="practice_markdown",
            latex_delimiters=[
                {"left": "$$", "right": "$$", "display": True},  # 块级数学
                {"left": "$", "right": "$", "display": False},  # 行内数学
            ],
        )

        gr.Markdown("---")

        image_input = gr.Image(
            label="上传或拍摄图片",
            sources=["webcam", "upload", "clipboard"],
            type="pil",
            height=400,
        )

        images_gallery = gr.Gallery(
            label="已保存的图片",
            show_label=True,
            elem_id="images_gallery",
            columns=4,
            rows=3,
            height=200,
            object_fit="cover",
        )

        clear_images_btn = gr.Button("清空图片", variant="secondary")

        grade_btn = gr.Button("批改", variant="primary")

        grading_report = gr.Textbox(label="批改报告", lines=25, interactive=False)

        regenerate_btn = gr.Button("重新生成题目", variant="primary")

        # 事件绑定
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

        # 图片选择时自动添加到图片库
        image_input.change(
            fn=add_image,
            inputs=[image_input],
            outputs=[images_gallery, image_input, grading_report],
        )

        # 清空图片库
        clear_images_btn.click(
            fn=clear_images,
            inputs=[],
            outputs=[images_gallery, grading_report],
        )

        # 批改所有图片
        grade_btn.click(
            fn=grade_images,
            inputs=[],
            outputs=[grading_report, current_session_info],
        )

        # 会话选择事件
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


# 创建Gradio界面
demo = create_interface()
