"""
图片批改标记模块
用于在学生答题图片上标记批改结果（对勾或错误符号）
"""

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Tuple, Optional
import json
import io
import xml.etree.ElementTree as ET


class ImageGradingMarker:
    """图片批改标记器"""

    def __init__(self):
        self.checkmark_color = (0, 255, 0)  # 绿色对勾
        self.cross_color = (255, 0, 0)      # 红色错误
        self.mark_size = 240                # 标记大小（4倍大：60 * 4 = 240）
        self.font_size = 24                 # 字体大小

        # PNG文件路径
        self.check_png_path = os.path.join(os.path.dirname(__file__), "images", "check.png")
        self.cross_png_path = os.path.join(os.path.dirname(__file__), "images", "cross.png")

    def load_png_as_image(self, png_path: str, size: int, color: Tuple[int, int, int]) -> np.ndarray:
        """从PNG文件加载图片并调整大小和颜色"""
        try:
            # 检查PNG文件是否存在
            if not os.path.exists(png_path):
                print(f"PNG文件不存在: {png_path}")
                return self._create_fallback_symbol(size, color)

            # 加载PNG图片
            pil_image = Image.open(png_path)

            # 转换为RGBA模式
            if pil_image.mode != 'RGBA':
                pil_image = pil_image.convert('RGBA')

            # 调整大小
            pil_image = pil_image.resize((size, size), Image.Resampling.LANCZOS)

            # 调整颜色
            data = np.array(pil_image)
            if len(data.shape) == 3 and data.shape[2] == 4:
                # 创建颜色掩码（非透明像素）
                alpha = data[:, :, 3]
                mask = alpha > 0

                # 应用新颜色
                data[mask, 0] = color[0]  # R
                data[mask, 1] = color[1]  # G
                data[mask, 2] = color[2]  # B
                # 保持alpha通道不变

            return data

        except Exception as e:
            print(f"加载PNG文件失败: {e}")
            # 如果加载失败，返回一个简单的替代符号
            return self._create_fallback_symbol(size, color)

    def load_svg_as_image(self, svg_path: str, size: int, color: Tuple[int, int, int]) -> np.ndarray:
        """从SVG文件加载图片并调整大小和颜色"""
        try:
            # 检查SVG文件是否存在
            if not os.path.exists(svg_path):
                print(f"SVG文件不存在: {svg_path}")
                return self._create_fallback_symbol(size, color)

            # 读取SVG文件
            with open(svg_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()

            # 解析SVG并提取路径信息
            root = ET.fromstring(svg_content)

            # 创建PIL图像
            img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # 简化的SVG路径绘制（针对简单的对勾和叉号）
            if 'check' in svg_path.lower():
                # 绘制对勾
                self._draw_checkmark_simple(draw, size, color)
            elif 'cross' in svg_path.lower():
                # 绘制叉号
                self._draw_cross_simple(draw, size, color)
            else:
                # 默认绘制圆圈
                self._draw_circle_simple(draw, size, color)

            # 转换为numpy数组
            return np.array(img)

        except Exception as e:
            print(f"加载SVG文件失败: {e}")
            # 如果加载失败，返回一个简单的替代符号
            return self._create_fallback_symbol(size, color)

    def _draw_checkmark_simple(self, draw: ImageDraw.Draw, size: int, color: Tuple[int, int, int]):
        """绘制简单的对勾"""
        # 计算对勾的坐标点
        margin = size // 8
        points = [
            (margin, size // 2),
            (size // 2 - margin // 2, size - margin),
            (size - margin, margin)
        ]

        # 绘制对勾线条
        thickness = max(4, size // 15)
        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=color, width=thickness)

    def _draw_cross_simple(self, draw: ImageDraw.Draw, size: int, color: Tuple[int, int, int]):
        """绘制简单的叉号"""
        margin = size // 4
        thickness = max(4, size // 15)

        # 绘制两条交叉的线
        draw.line([(margin, margin), (size - margin, size - margin)], fill=color, width=thickness)
        draw.line([(size - margin, margin), (margin, size - margin)], fill=color, width=thickness)

    def _draw_circle_simple(self, draw: ImageDraw.Draw, size: int, color: Tuple[int, int, int]):
        """绘制简单的圆圈"""
        margin = size // 8
        draw.ellipse([margin, margin, size - margin, size - margin], fill=color)

    def _create_fallback_symbol(self, size: int, color: Tuple[int, int, int]) -> np.ndarray:
        """创建备用符号（当SVG加载失败时使用）"""
        img = np.zeros((size, size, 4), dtype=np.uint8)
        center = (size // 2, size // 2)
        radius = size // 2 - 2
        cv2.circle(img, center, radius, (*color, 255), -1)
        return img

    def _overlay_symbol(self, pil_image: Image.Image, symbol: np.ndarray, x: int, y: int) -> Image.Image:
        """将符号叠加到PIL图像上"""
        # 计算符号位置（居中）
        symbol_h, symbol_w = symbol.shape[:2]
        x_offset = x - symbol_w // 2
        y_offset = y - symbol_h // 2

        # 确保位置在图像范围内
        x_offset = max(0, min(x_offset, pil_image.width - symbol_w))
        y_offset = max(0, min(y_offset, pil_image.height - symbol_h))

        # 将符号转换为PIL图像
        symbol_pil = Image.fromarray(symbol, 'RGBA')

        # 创建临时图像用于叠加
        temp_image = pil_image.copy()

        # 叠加符号
        temp_image.paste(symbol_pil, (x_offset, y_offset), symbol_pil)

        return temp_image

    def create_checkmark(self, size: int = 40) -> np.ndarray:
        """创建对勾符号（使用PNG文件）"""
        return self.load_png_as_image(self.check_png_path, size, self.checkmark_color)

    def create_cross(self, size: int = 40) -> np.ndarray:
        """创建叉号符号（使用PNG文件）"""
        return self.load_png_as_image(self.cross_png_path, size, self.cross_color)

    def estimate_question_positions(self, image_shape: Tuple[int, int], practice_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        根据题目信息估算题目在图片中的位置
        
        Args:
            image_shape: 图片尺寸 (height, width, channels)
            practice_data: 练习数据
            
        Returns:
            题目位置信息列表
        """
        height, width = image_shape[:2]
        positions = []

        # 估算每道题的位置
        # 假设题目按顺序从上到下排列
        sections = practice_data.get("sections", [])

        # 计算总题目数
        total_questions = sum(len(section.get("questions", [])) for section in sections)

        if total_questions == 0:
            return positions

        # 估算每道题的高度
        question_height = height // max(total_questions, 1)

        current_y = 0
        question_index = 0

        for section in sections:
            questions = section.get("questions", [])
            for question in questions:
                # 估算题目位置（在题目右侧留出标记空间）
                question_rect = {
                    "question_id": question.get("id", ""),
                    "question_type": section.get("type", ""),
                    "question_number": question_index + 1,
                    "x": int(width * 0.8),  # 在图片右侧80%位置（为更大的标记留出空间）
                    "y": current_y + question_height // 2,  # 题目中间位置
                    "width": int(width * 0.15),  # 标记区域宽度
                    "height": question_height
                }
                positions.append(question_rect)

                current_y += question_height
                question_index += 1

        return positions

    def mark_image_with_grading_results(
        self,
        image_path: str,
        grading_results: List[Dict[str, Any]],
        practice_data: Dict[str, Any],
        output_path: Optional[str] = None,
        question_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        在图片上标记批改结果

        Args:
            image_path: 原始图片路径
            grading_results: 批改结果列表
            practice_data: 练习数据
            output_path: 输出图片路径，如果为None则自动生成
            question_positions: 题目位置信息列表，如果提供则使用AI检测的位置

        Returns:
            标记后的图片路径
        """
        # 读取图片
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"无法读取图片: {image_path}")

        # 转换为PIL图像以便更好的文本处理
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(image_rgb)
        draw = ImageDraw.Draw(pil_image)

        # 获取题目位置信息
        if question_positions is None:
            # 如果没有提供AI检测的位置，使用估算方法
            question_positions = self.estimate_question_positions(
                image.shape, practice_data
            )

        # 创建批改结果映射（按题目类型和序号）
        grading_map = {}
        for result in grading_results:
            question_type = result.get("question_type", "")
            question_id = result.get("question_id", "")

            # 从practice_data中找到对应的题目序号
            question_number = self._find_question_number_by_id(
                practice_data, question_id, question_type
            )
            if question_number:
                key = f"{question_type}_{question_number}"
                grading_map[key] = result

        # 为每道题添加标记
        for pos in question_positions:
            question_type = pos.get("question_type", "")
            question_number = pos.get("question_number", "")
            key = f"{question_type}_{question_number}"
            grading_result = grading_map.get(key)

            if grading_result is None:
                continue

            # 判断是否正确
            is_correct = self._is_question_correct(grading_result)

            # 绘制标记
            x = pos["x"]
            y = pos["y"]

            # 使用SVG符号进行标记
            if is_correct:
                # 加载绿色对勾符号
                symbol = self.create_checkmark(self.mark_size)
            else:
                # 加载红色叉号符号
                symbol = self.create_cross(self.mark_size)

            # 将符号叠加到图片上
            pil_image = self._overlay_symbol(pil_image, symbol, x, y)
            draw = ImageDraw.Draw(pil_image)

            # 添加题目编号
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 24)  # 增大字体
            except:
                font = ImageFont.load_default()

            question_num = pos["question_number"]
            draw.text(
                (x + self.mark_size // 2 + 20, y - 12),  # 调整位置
                f"第{question_num}题",
                fill=(0, 0, 0),
                font=font
            )

        # 保存标记后的图片
        if output_path is None:
            # 自动生成输出路径，保存到session目录
            base_name = os.path.splitext(os.path.basename(image_path))[0]

            # 尝试从image_path推断session目录
            # 如果路径包含session目录结构，则使用该目录
            if "data" in image_path and "images" in image_path:
                # 从images子目录回到session目录
                session_dir = os.path.dirname(os.path.dirname(image_path))
            else:
                # 如果无法推断，使用当前工作目录
                session_dir = os.getcwd()

            # 创建graded_images子目录
            graded_dir = os.path.join(session_dir, "graded_images")
            os.makedirs(graded_dir, exist_ok=True)
            output_path = os.path.join(graded_dir, f"{base_name}_graded.jpg")

        # 转换回OpenCV格式并保存
        marked_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        cv2.imwrite(output_path, marked_image)

        return output_path

    def _is_question_correct(self, grading_result: Dict[str, Any]) -> bool:
        """判断题目是否正确"""
        question_type = grading_result.get("question_type", "")

        if question_type == "choice":
            return grading_result.get("is_correct", False)
        elif question_type == "calculation":
            return grading_result.get("overall_correct", False)
        else:
            return grading_result.get("is_correct", False)

    def _find_question_number_by_id(
        self, practice_data: Dict[str, Any], question_id: str, question_type: str
    ) -> Optional[str]:
        """根据题目ID和类型找到题目序号"""
        sections = practice_data.get("sections", [])

        for section in sections:
            if section.get("type") == question_type:
                questions = section.get("questions", [])
                for i, question in enumerate(questions):
                    if question.get("id") == question_id:
                        return str(i + 1)  # 题目序号从1开始

        return None

    def batch_mark_images(
        self,
        image_paths: List[str],
        grading_results: List[Dict[str, Any]],
        practice_data: Dict[str, Any],
        question_positions_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[str]:
        """
        批量标记多张图片

        Args:
            image_paths: 图片路径列表
            grading_results: 批改结果列表
            practice_data: 练习数据
            question_positions_map: 每张图片的题目位置信息映射，键为图片路径

        Returns:
            标记后的图片路径列表
        """
        marked_images = []

        for i, image_path in enumerate(image_paths):
            try:
                # 获取该图片的题目位置信息
                question_positions = None
                if question_positions_map and image_path in question_positions_map:
                    question_positions = question_positions_map[image_path]

                # 为每张图片生成标记
                output_path = self.mark_image_with_grading_results(
                    image_path, grading_results, practice_data, None, question_positions
                )
                marked_images.append(output_path)
            except Exception as e:
                print(f"标记图片 {image_path} 时出错: {str(e)}")
                # 如果标记失败，返回原图片
                marked_images.append(image_path)

        return marked_images


def test_image_grading():
    """测试图片批改标记功能"""
    # 创建测试数据
    practice_data = {
        "sections": [
            {
                "name": "一、选择题",
                "type": "choice",
                "questions": [
                    {"id": "q1", "question": "测试题目1"},
                    {"id": "q2", "question": "测试题目2"}
                ]
            },
            {
                "name": "二、计算题", 
                "type": "calculation",
                "questions": [
                    {"id": "q3", "question": "测试题目3"}
                ]
            }
        ]
    }
    
    grading_results = [
        {"question_id": "q1", "question_type": "choice", "is_correct": True},
        {"question_id": "q2", "question_type": "choice", "is_correct": False},
        {"question_id": "q3", "question_type": "calculation", "overall_correct": True}
    ]
    
    # 创建标记器
    marker = ImageGradingMarker()
    
    # 测试标记功能（需要提供真实的图片路径）
    # marked_path = marker.mark_image_with_grading_results(
    #     "test_image.jpg", grading_results, practice_data
    # )
    # print(f"标记后的图片保存到: {marked_path}")


if __name__ == "__main__":
    test_image_grading()
