#!/usr/bin/env python3
"""
数学题目生成器启动脚本
"""

from dotenv import load_dotenv

load_dotenv()


def main():
    """主函数"""
    print("🧮 数学题目生成器")
    print("=" * 50)

    print("启动数学题目生成器...")
    print("访问地址: http://localhost:7860")
    print("按 Ctrl+C 停止程序")
    print("=" * 50)

    from src.complete_ui import demo
    from src.question.bank import QuestionBank

    qb = QuestionBank()
    qb.load_questions()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        debug=True,
        share=False,
        show_error=True,
        inbrowser=True,
    )


if __name__ == "__main__":
    main()
