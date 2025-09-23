import os
import datetime
import json
import uuid
from typing import List, Dict, Any


def save_session_data(session_path: str, prompt: str, questions: List[Dict[str, Any]], extra_data: Dict[str, Any] = None):
    """保存会话数据"""
    data = {
        "prompt": prompt,
        "questions": questions,
        "created_at": datetime.datetime.now().isoformat(),
        "session_id": os.path.basename(session_path)
    }

    # 添加额外数据
    if extra_data:
        data.update(extra_data)

    json_path = os.path.join(session_path, "session_data.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_complete_session_data(session_path: str, session_data: Dict[str, Any]):
    """保存完整的会话数据"""
    session_data["updated_at"] = datetime.datetime.now().isoformat()
    json_path = os.path.join(session_path, "session_data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)


def load_complete_session_data(session_path: str) -> Dict[str, Any]:
    """加载完整的会话数据"""
    json_path = os.path.join(session_path, "session_data.json")
    if not os.path.exists(json_path):
        return {}

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_session() -> str:
    """创建以ID+时间命名的会话目录"""
    data_dir = os.getenv('DATA_DIR')
    session_id = str(uuid.uuid4())[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"{session_id}_{timestamp}"
    session_path = os.path.join(data_dir, session_name)
    os.makedirs(session_path, exist_ok=True)
    return session_path

def get_all_sessions() -> List[Dict[str, Any]]:
    """获取所有会话目录信息"""
    data_dir = os.getenv('DATA_DIR')
    sessions = []
    if not os.path.exists(data_dir):
        return sessions

    for item in os.listdir(data_dir):
        item_path = os.path.join(data_dir, item)
        if os.path.isdir(item_path):
            session_info = {
                "name": item,
                "path": item_path,
                "created_at": datetime.datetime.fromtimestamp(os.path.getctime(item_path)).strftime("%Y-%m-%d %H:%M:%S")
            }

            # 尝试读取会话数据
            json_path = os.path.join(item_path, "session_data.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        session_info.update(data)
                except:
                    pass

            sessions.append(session_info)

    # 按创建时间倒序排列
    sessions.sort(key=lambda x: x['created_at'], reverse=True)
    return sessions


class CompleteSession:
    """完整的会话管理类"""

    def __init__(self, session_path: str = None):
        self.session_path = session_path
        self.data = {
            "prompt": "",
            "knowledge_points": [],
            "practice_data": None,
            "student_answers": [],
            "grading_results": [],
            "error_analysis": None,
            "images": [],
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
        }

    def initialize(self) -> str:
        """初始化会话，创建会话目录"""
        if not self.session_path:
            self.session_path = create_session()
        return self.session_path

    def load_from_path(self, session_path: str) -> bool:
        """从现有路径加载会话数据"""
        try:
            self.session_path = session_path
            self.data = load_complete_session_data(session_path)
            return bool(self.data)
        except Exception as e:
            print(f"加载会话数据时出错: {str(e)}")
            return False

    def save(self):
        """保存会话数据"""
        if self.session_path:
            save_complete_session_data(self.session_path, self.data)

    def add_image(self, image_path: str) -> str:
        """添加图片到会话"""
        if not self.session_path:
            return "请先初始化会话"

        # 创建 images 子目录
        images_dir = os.path.join(self.session_path, "images")
        os.makedirs(images_dir, exist_ok=True)

        # 复制图片到会话目录
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        image_filename = f"image_{timestamp}.jpg"
        target_path = os.path.join(images_dir, image_filename)

        import shutil

        shutil.copy2(image_path, target_path)

        # 更新图片列表
        if "images" not in self.data:
            self.data["images"] = []
        self.data["images"].append(target_path)
        self.save()

        return f"已添加图片，当前共有 {len(self.data['images'])} 张图片"

    def get_images(self) -> List[str]:
        """获取会话中的所有图片"""
        return self.data.get("images", [])

    def clear_images(self):
        """清空图片"""
        if not self.session_path:
            return "请先初始化会话"

        # 清空 images 目录
        images_dir = os.path.join(self.session_path, "images")
        if os.path.exists(images_dir):
            for file in os.listdir(images_dir):
                file_path = os.path.join(images_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)

        self.data["images"] = []
        self.save()
        return "图片库已清空"


def get_session_images(session_path: str) -> List[str]:
    """获取指定 session 中的所有图片"""
    if not session_path:
        return []

    images_dir = os.path.join(session_path, "images")
    if not os.path.exists(images_dir):
        return []

    image_files = []
    for file in os.listdir(images_dir):
        if file.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
            image_files.append(os.path.join(images_dir, file))

    # 按文件名排序
    image_files.sort()
    return image_files
