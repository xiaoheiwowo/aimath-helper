"""
数学知识点数据库
基于七年级第二章《有理数计算》教学大纲
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
import re


@dataclass
class KnowledgePoint:
    """知识点"""
    outline: str
    detail: str
    keywords: List[str]  # 关键词列表，用于匹配


class KnowledgeBase:
    """知识点数据库"""
    
    def __init__(self):
        self.knowledge_points = self._init_knowledge_points()
    
    def _init_knowledge_points(self) -> List[KnowledgePoint]:
        """初始化知识点数据库"""
        return [
            # 知识点1：加法法则
            KnowledgePoint(
                outline="有理数加法法则",
                detail="⑴同号两数相加，取相同的符号，并把绝对值相加。⑵绝对值不相等的异号两数相加，取绝对值较大的加数的符号，并用较大的绝对值减去较小的绝对值。互为相反数的两个数相加得0。⑶一个数同0相加，仍得这个数。",
                keywords=["加法", "同号相加", "异号相加", "相反数", "绝对值", "加法法则", "有理数加法"]
            ),
            
            # 知识点2：加法运算定律
            KnowledgePoint(
                outline="加法运算定律",
                detail="（1）加法交换律：两数相加，交换加数的位置，和不变。即a＋b=b＋a（2）加法结合律：在有理数加法中，三个数相加，先把前两个数相加或者先把后两个数相加，和不变。即a＋b＋c=（a＋b）＋c=a＋（b＋c）",
                keywords=["加法交换律", "加法结合律", "交换律", "结合律", "运算定律"]
            ),
            
            # 知识点3：减法法则
            KnowledgePoint(
                outline="有理数减法法则",
                detail="减法法则：减去一个数，等于加上这个数的相反数。即a－b=a＋（﹣）b",
                keywords=["减法", "减法法则", "相反数", "有理数减法"]
            ),
            
            # 知识点4：乘法法则
            KnowledgePoint(
                outline="有理数乘法法则",
                detail="（1）两数相乘，同号得正，异号得负，并把绝对值相乘。（2）任何数同0相乘，都得0。（3）多个不为0的数相乘，负因数的个数是偶数时，积为正数；负因数的个数是奇数时，积为负数，即先确定符号，再把绝对值相乘，绝对值的积就是积的绝对值。（4）多个数相乘，若其中有因数0，则积等于0；反之，若积为0，则至少有一个因数是0。",
                keywords=["乘法", "乘法法则", "同号得正", "异号得负", "负因数", "有理数乘法"]
            ),
            
            # 知识点5：乘法运算定律
            KnowledgePoint(
                outline="乘法运算定律",
                detail="（1）乘法交换律：两数相乘，交换因数的位置，积相等。即a×b＝ba（2）乘法结合律：三个数相乘，先把前两个数相乘，或者先把后两个数相乘，积相等。即a×b×c＝﹙a×b﹚×c＝a×﹙b×c﹚。（3）乘法分配律：一个数同两个数的和相乘，等于把这个数分别同这两个数相乘，在把积相加即a×﹙b＋c﹚＝a×b＋a×c。",
                keywords=["乘法交换律", "乘法结合律", "乘法分配律", "交换律", "结合律", "分配律", "运算定律"]
            ),
            
            # 知识点6：倒数
            KnowledgePoint(
                outline="倒数",
                detail="（1）定义：乘积为1的两个数互为倒数。（2）性质：负数的倒数还是负数，正数的倒数是正数。注意：① 0 没有倒数；②倒数等于它本身的数为±1。",
                keywords=["倒数", "互为倒数", "乘积为1", "倒数性质"]
            ),
            
            # 知识点7：除法法则
            KnowledgePoint(
                outline="有理数除法法则",
                detail="（1）除以一个（不等于0）的数，等于乘这个数的倒数。（2）两个数相除，同号得正，异号得负，并把绝对值相除。（3）0除以任何一个不等于0的数，都得0。",
                keywords=["除法", "除法法则", "倒数", "同号得正", "异号得负", "有理数除法"]
            ),
            
            # 知识点8：乘方法则运算
            KnowledgePoint(
                outline="乘方法则运算",
                detail="（1）正数的任何次幂都是正数（2）负数的奇次幂是负数，负数的偶次幂是正数（3）0的任何正整数次幂都是0",
                keywords=["乘方", "幂", "奇次幂", "偶次幂", "乘方法则", "幂运算"]
            ),
            
            # 知识点9：混合运算
            KnowledgePoint(
                outline="有理数混合运算",
                detail="（1）先乘方，再乘除，最后加减。（2）同级运算，从左到右的顺序进行。（3）如有括号，先算括号内的运算，按小括号，中括号，大括号依次进行。在进行有理数的运算时，要分两步走：先确定符号，再求值。",
                keywords=["混合运算", "运算顺序", "乘方", "乘除", "加减", "括号", "运算规则"]
            ),
            
            # 知识点10：科学计数法
            KnowledgePoint(
                outline="科学计数法",
                detail="1.科学记数法概念：把一个大于10的数表示成a×10n的形式（其中a 是整数数位只有一位的数，n为正整数）。这种记数的方法叫做科学记数法。﹙1≤|a|＜10﹚注：一个n为数用科学记数法表示为a×10n－1。2.近似数的精确度：两种形式（1）精确到某位或精确到小数点后某位。（2）保留几个有效数字注：对于较大的数取近似数时，结果一般用科学记数法来表示例如：256000（精确到万位）的结果是2.6×105。3.有效数字：从一个数的左边第一个非0数字起，到末尾数字止，所有的数字都是这个数的有效数。",
                keywords=["科学计数法", "科学记数法", "有效数字", "近似数", "精确度", "a×10n"]
            )
        ]
    
    def find_matching_knowledge_points(self, text: str) -> List[KnowledgePoint]:
        """根据文本内容匹配知识点"""
        matched_points = []
        text_lower = text.lower()
        
        for point in self.knowledge_points:
            # 检查关键词匹配
            for keyword in point.keywords:
                if keyword.lower() in text_lower:
                    matched_points.append(point)
                    break  # 找到一个匹配就足够了
        
        return matched_points
    
    def get_all_knowledge_points(self) -> List[KnowledgePoint]:
        """获取所有知识点"""
        return self.knowledge_points
    
    def get_knowledge_point_by_outline(self, outline: str) -> KnowledgePoint:
        """根据大纲获取知识点"""
        for point in self.knowledge_points:
            if point.outline == outline:
                return point
        return None


# 全局知识点数据库实例
knowledge_base = KnowledgeBase()
