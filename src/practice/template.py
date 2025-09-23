import os
import json
from jinja2 import Environment, FileSystemLoader

def get_template_dir():
    """获取模板文件所在目录"""
    return os.path.dirname(os.path.abspath(__file__))

def render_markdown(practice: dict):
    """
    使用Jinja2模板渲染练习试卷
    
    Args:
        practice: 包含试卷数据的字典，格式与practice_example.json一致
    
    Returns:
        渲染后的markdown字符串
    """
    template_dir = get_template_dir()
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('practice_template.j2')
    
    return template.render(
        title=practice["title"],
        sections=practice["sections"]
    )

def load_practice_from_json(json_file_path: str):
    """
    从JSON文件加载练习数据
    
    Args:
        json_file_path: JSON文件路径
    
    Returns:
        包含练习数据的字典
    """
    with open(json_file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def render_practice_from_json(json_file_path: str):
    """
    从JSON文件渲染练习试卷
    
    Args:
        json_file_path: JSON文件路径
    
    Returns:
        渲染后的markdown字符串
    """
    practice_data = load_practice_from_json(json_file_path)
    return render_markdown(practice_data)

# 示例：使用practice_example.json渲染试卷
if __name__ == "__main__":
    # 渲染示例试卷
    example_json_path = os.path.join(os.path.dirname(__file__), "practice_example.json")
    markdown_content = render_practice_from_json(example_json_path)
    
    # 输出结果
    print("渲染结果：")
    print("=" * 50)
    print(markdown_content)
    print("=" * 50)
    
    # 保存到文件
    output_path = os.path.join(os.path.dirname(__file__), "generated_practice.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"结果已保存到 {output_path}")
