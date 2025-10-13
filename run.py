#!/usr/bin/env python3
"""
数学题目生成器启动脚本
"""

from dotenv import load_dotenv

load_dotenv()


def main():
    """主函数"""
    print("🧮 AI数学助手 - 整合版")
    print("=" * 50)

    print("启动AI数学助手整合界面...")
    print("访问地址: http://localhost:7860")
    print("按 Ctrl+C 停止程序")
    print("=" * 50)

    from src.main_layout import create_web_app_layout

    # 创建整合界面
    demo = create_web_app_layout()
    
    # 启动界面
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
