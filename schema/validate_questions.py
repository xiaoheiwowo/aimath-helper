#!/usr/bin/env python3
"""
验证 questions.json 是否符合 schema 规范
"""

import json
import sys
import os
from typing import List, Dict, Any

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schema.question_models import Question, QuestionBank, QuestionType, QuestionMetadata, KnowledgePoint, Choice, SolutionStep, validate_question, validate_question_bank


def load_questions_from_json(file_path: str) -> List[Dict[str, Any]]:
    """从JSON文件加载题目数据"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('questions', [])


def convert_to_question_objects(questions_data: List[Dict[str, Any]]) -> List[Question]:
    """将JSON数据转换为Question对象"""
    questions = []
    
    for q_data in questions_data:
        # 转换知识点
        knowledge_points = []
        for kp_data in q_data.get('knowledge_points', []):
            knowledge_points.append(KnowledgePoint(
                outline=kp_data['outline'],
                detail=kp_data['detail']
            ))
        
        # 转换元数据
        metadata = QuestionMetadata(
            category=q_data['metadata']['category']
        )
        
        # 转换选择题选项
        choices = None
        if q_data['type'] == 'choice' and 'choices' in q_data:
            choices = []
            for choice_data in q_data['choices']:
                choices.append(Choice(
                    id=choice_data['id'],
                    content=choice_data['content'],
                    is_correct=choice_data['is_correct'],
                    explanation=choice_data['explanation']
                ))
        
        # 转换解题步骤
        solution_steps = None
        if q_data['type'] == 'calculation' and 'solution_steps' in q_data:
            solution_steps = []
            for step_data in q_data['solution_steps']:
                solution_steps.append(SolutionStep(
                    step=step_data['step']
                ))
        
        # 创建题目对象
        question = Question(
            id=q_data['id'],
            type=QuestionType(q_data['type']),
            metadata=metadata,
            question=q_data['question'],
            knowledge_points=knowledge_points,
            answer=q_data['answer'],
            choices=choices,
            solution_steps=solution_steps
        )
        
        questions.append(question)
    
    return questions


def validate_questions_file(file_path: str) -> bool:
    """验证题目文件"""
    print(f"正在验证文件: {file_path}")
    
    try:
        # 加载JSON数据
        questions_data = load_questions_from_json(file_path)
        print(f"✅ 成功加载 {len(questions_data)} 个题目")
        
        # 转换为对象
        questions = convert_to_question_objects(questions_data)
        print(f"✅ 成功转换为 {len(questions)} 个Question对象")
        
        # 创建题目库
        bank = QuestionBank(questions=questions)
        
        # 验证题目库
        errors = validate_question_bank(bank)
        
        if errors:
            print(f"❌ 发现 {len(errors)} 个错误:")
            for error in errors:
                print(f"  - {error}")
            return False
        else:
            print("✅ 所有题目验证通过!")
            
            # 显示统计信息
            choice_count = len(bank.get_choice_questions())
            calc_count = len(bank.get_calculation_questions())
            print("📊 统计信息:")
            print(f"  - 选择题: {choice_count} 个")
            print(f"  - 计算题: {calc_count} 个")
            print(f"  - 总计: {len(questions)} 个")
            
            return True
            
    except Exception as e:
        print(f"❌ 验证过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("=== 题目数据验证工具 ===")
    
    # 验证 questions.json
    questions_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src', 'question', 'questions.json')
    
    if not os.path.exists(questions_file):
        print(f"❌ 文件不存在: {questions_file}")
        return False
    
    success = validate_questions_file(questions_file)
    
    if success:
        print("\n🎉 验证完成，所有数据符合规范!")
    else:
        print("\n💥 验证失败，请检查数据格式!")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
