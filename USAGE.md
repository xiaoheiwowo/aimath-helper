# 使用说明

## 快速开始

1. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```

2. **配置API密钥**：
   创建 `.env` 文件并添加您的 OpenAI API Key：
   ```
   OPENAI_API_KEY=your_actual_api_key_here
   ```

3. **运行程序**：
   ```bash
   python run.py
   ```
   或者直接运行：
   ```bash
   python src/gradio_ui.py
   ```

4. **访问界面**：
   打开浏览器访问 `http://localhost:7860`

## 功能说明

### 生成题目
- 在提示词框中输入您想要的数学题目类型
- 例如："生成5道关于二次方程的题目，难度中等"
- 选择题目数量（1-20道）
- 点击"生成题目"按钮

### 查看历史
- 在"查看历史会话"标签页可以查看所有生成的会话
- 每个会话都有独立的目录，包含PDF文件和数据

### 数据存储
- 所有数据保存在 `data/` 目录下
- 每个会话使用 `ID_时间戳` 格式命名
- 包含 `session_data.json` 和 `math_questions.pdf` 文件
