"""生成测试数据脚本 - 用于Phase 2教材解析测试"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def register_chinese_font():
    """注册中文字体"""
    # 尝试使用系统字体
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
        "C:/Windows/Fonts/simsun.ttc",  # 宋体
        "C:/Windows/Fonts/simhei.ttf",  # 黑体
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont('Chinese', font_path))
                return 'Chinese'
            except:
                continue
    
    # 如果没有中文字体，使用默认字体
    return 'Helvetica'


def generate_test_pdf(output_path: Path):
    """生成测试PDF文件"""
    font_name = register_chinese_font()
    
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    styles = getSampleStyleSheet()
    
    # 创建自定义样式
    title_style = ParagraphStyle(
        'ChapterTitle',
        parent=styles['Heading1'],
        fontSize=18,
        fontName=font_name,
        alignment=TA_CENTER,
        spaceAfter=30,
        spaceBefore=20
    )
    
    subtitle_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        fontName=font_name,
        alignment=TA_LEFT,
        spaceAfter=20,
        spaceBefore=15
    )
    
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=11,
        fontName=font_name,
        alignment=TA_LEFT,
        spaceAfter=12,
        leading=16
    )
    
    # 教材内容
    chapters = [
        {
            "title": "第一章 绪论",
            "sections": [
                {
                    "title": "1.1 什么是生理学",
                    "content": """生理学是研究生物体正常生命活动规律的科学。它主要研究生物体及其各组成部分的功能活动规律，以及这些功能活动在整体生命活动中的意义。生理学是医学科学的重要基础学科之一，为临床医学提供了理论基础。"""
                },
                {
                    "title": "1.2 生理学的研究方法",
                    "content": """生理学的研究方法主要包括实验方法和观察方法。实验方法是在控制条件下，通过改变某些因素来观察其对生物体功能的影响。观察方法是在自然条件下，对生物体的功能活动进行系统的观察和记录。"""
                },
                {
                    "title": "1.3 生理学的发展简史",
                    "content": """生理学的发展经历了漫长的历史过程。从古代的朴素唯物主义观点，到近代的实验生理学，再到现代的分子生理学，生理学不断发展和完善。"""
                }
            ]
        },
        {
            "title": "第二章 细胞的基本功能",
            "sections": [
                {
                    "title": "2.1 细胞膜的结构和功能",
                    "content": """细胞膜是细胞的重要组成部分，它将细胞内容物与细胞周围环境分隔开来。细胞膜主要由脂质、蛋白质和糖类组成，具有选择性通透性，能够控制物质的进出。"""
                },
                {
                    "title": "2.2 细胞的物质转运",
                    "content": """细胞的物质转运包括被动转运和主动转运两种方式。被动转运不需要消耗能量，包括简单扩散和易化扩散。主动转运需要消耗能量，包括原发性主动转运和继发性主动转运。"""
                },
                {
                    "title": "2.3 细胞的信号转导",
                    "content": """细胞的信号转导是指细胞外信号通过特定的机制转化为细胞内信号的过程。这个过程涉及多种信号分子和信号通路，是细胞适应环境变化的重要方式。"""
                }
            ]
        },
        {
            "title": "第三章 血液",
            "sections": [
                {
                    "title": "3.1 血液的组成和功能",
                    "content": """血液是流动在心脏和血管腔内的不透明红色液体，由血浆和血细胞组成。血液具有运输功能、防御功能和调节功能，是维持生命活动的重要物质。"""
                },
                {
                    "title": "3.2 血细胞的生理",
                    "content": """血细胞包括红细胞、白细胞和血小板。红细胞的主要功能是运输氧气和二氧化碳。白细胞的主要功能是防御和免疫。血小板的主要功能是止血和凝血。"""
                },
                {
                    "title": "3.3 血液凝固",
                    "content": """血液凝固是一个复杂的生理过程，涉及多种凝血因子的参与。当血管受损时，血液凝固能够防止出血过多，保护机体。"""
                }
            ]
        },
        {
            "title": "第四章 血液循环",
            "sections": [
                {
                    "title": "4.1 心脏的泵血功能",
                    "content": """心脏是循环系统的动力器官，通过节律性的收缩和舒张，将血液泵入动脉，维持血液循环。心脏的泵血功能包括收缩期和舒张期两个时相。"""
                },
                {
                    "title": "4.2 心肌的电生理",
                    "content": """心肌细胞具有自律性、传导性、兴奋性和收缩性四种生理特性。心肌的电生理特性是心脏节律性活动的基础。"""
                },
                {
                    "title": "4.3 血管生理",
                    "content": """血管是血液流动的管道，包括动脉、毛细血管和静脉。不同类型的血管具有不同的结构和功能特点，共同完成血液循环。"""
                }
            ]
        }
    ]
    
    # 构建PDF内容
    story = []
    
    # 添加封面
    story.append(Spacer(1, 5*cm))
    story.append(Paragraph("生理学", title_style))
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("（测试教材）", ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=14,
        fontName=font_name,
        alignment=TA_CENTER
    )))
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("用于学科知识整合智能体测试", ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        fontName=font_name,
        alignment=TA_CENTER
    )))
    story.append(PageBreak())
    
    # 添加目录
    story.append(Paragraph("目 录", title_style))
    story.append(Spacer(1, 1*cm))
    for i, chapter in enumerate(chapters, 1):
        story.append(Paragraph(chapter["title"], body_style))
    story.append(PageBreak())
    
    # 添加各章节内容
    for chapter in chapters:
        story.append(Paragraph(chapter["title"], title_style))
        story.append(Spacer(1, 0.5*cm))
        
        for section in chapter["sections"]:
            story.append(Paragraph(section["title"], subtitle_style))
            story.append(Paragraph(section["content"], body_style))
            story.append(Spacer(1, 0.3*cm))
        
        story.append(PageBreak())
    
    # 生成PDF
    doc.build(story)
    print(f"Generated PDF: {output_path}")


def generate_test_markdown(output_path: Path):
    """生成测试Markdown文件"""
    content = """# 生理学

## 目录

- [第一章 绪论](#第一章-绪论)
- [第二章 细胞的基本功能](#第二章-细胞的基本功能)
- [第三章 血液](#第三章-血液)
- [第四章 血液循环](#第四章-血液循环)

---

## 第一章 绪论

### 1.1 什么是生理学

生理学是研究生物体正常生命活动规律的科学。它主要研究生物体及其各组成部分的功能活动规律，以及这些功能活动在整体生命活动中的意义。生理学是医学科学的重要基础学科之一，为临床医学提供了理论基础。

### 1.2 生理学的研究方法

生理学的研究方法主要包括实验方法和观察方法。实验方法是在控制条件下，通过改变某些因素来观察其对生物体功能的影响。观察方法是在自然条件下，对生物体的功能活动进行系统的观察和记录。

### 1.3 生理学的发展简史

生理学的发展经历了漫长的历史过程。从古代的朴素唯物主义观点，到近代的实验生理学，再到现代的分子生理学，生理学不断发展和完善。

---

## 第二章 细胞的基本功能

### 2.1 细胞膜的结构和功能

细胞膜是细胞的重要组成部分，它将细胞内容物与细胞周围环境分隔开来。细胞膜主要由脂质、蛋白质和糖类组成，具有选择性通透性，能够控制物质的进出。

### 2.2 细胞的物质转运

细胞的物质转运包括被动转运和主动转运两种方式。被动转运不需要消耗能量，包括简单扩散和易化扩散。主动转运需要消耗能量，包括原发性主动转运和继发性主动转运。

### 2.3 细胞的信号转导

细胞的信号转导是指细胞外信号通过特定的机制转化为细胞内信号的过程。这个过程涉及多种信号分子和信号通路，是细胞适应环境变化的重要方式。

---

## 第三章 血液

### 3.1 血液的组成和功能

血液是流动在心脏和血管腔内的不透明红色液体，由血浆和血细胞组成。血液具有运输功能、防御功能和调节功能，是维持生命活动的重要物质。

### 3.2 血细胞的生理

血细胞包括红细胞、白细胞和血小板。红细胞的主要功能是运输氧气和二氧化碳。白细胞的主要功能是防御和免疫。血小板的主要功能是止血和凝血。

### 3.3 血液凝固

血液凝固是一个复杂的生理过程，涉及多种凝血因子的参与。当血管受损时，血液凝固能够防止出血过多，保护机体。

---

## 第四章 血液循环

### 4.1 心脏的泵血功能

心脏是循环系统的动力器官，通过节律性的收缩和舒张，将血液泵入动脉，维持血液循环。心脏的泵血功能包括收缩期和舒张期两个时相。

### 4.2 心肌的电生理

心肌细胞具有自律性、传导性、兴奋性和收缩性四种生理特性。心肌的电生理特性是心脏节律性活动的基础。

### 4.3 血管生理

血管是血液流动的管道，包括动脉、毛细血管和静脉。不同类型的血管具有不同的结构和功能特点，共同完成血液循环。

---

*本教材用于学科知识整合智能体测试*
"""
    
    output_path.write_text(content, encoding='utf-8')
    print(f"Generated Markdown: {output_path}")


def generate_test_txt(output_path: Path):
    """生成测试TXT文件"""
    content = """生理学

第一章 绪论

1.1 什么是生理学

生理学是研究生物体正常生命活动规律的科学。它主要研究生物体及其各组成部分的功能活动规律，以及这些功能活动在整体生命活动中的意义。生理学是医学科学的重要基础学科之一，为临床医学提供了理论基础。

1.2 生理学的研究方法

生理学的研究方法主要包括实验方法和观察方法。实验方法是在控制条件下，通过改变某些因素来观察其对生物体功能的影响。观察方法是在自然条件下，对生物体的功能活动进行系统的观察和记录。

1.3 生理学的发展简史

生理学的发展经历了漫长的历史过程。从古代的朴素唯物主义观点，到近代的实验生理学，再到现代的分子生理学，生理学不断发展和完善。

第二章 细胞的基本功能

2.1 细胞膜的结构和功能

细胞膜是细胞的重要组成部分，它将细胞内容物与细胞周围环境分隔开来。细胞膜主要由脂质、蛋白质和糖类组成，具有选择性通透性，能够控制物质的进出。

2.2 细胞的物质转运

细胞的物质转运包括被动转运和主动转运两种方式。被动转运不需要消耗能量，包括简单扩散和易化扩散。主动转运需要消耗能量，包括原发性主动转运和继发性主动转运。

2.3 细胞的信号转导

细胞的信号转导是指细胞外信号通过特定的机制转化为细胞内信号的过程。这个过程涉及多种信号分子和信号通路，是细胞适应环境变化的重要方式。

第三章 血液

3.1 血液的组成和功能

血液是流动在心脏和血管腔内的不透明红色液体，由血浆和血细胞组成。血液具有运输功能、防御功能和调节功能，是维持生命活动的重要物质。

3.2 血细胞的生理

血细胞包括红细胞、白细胞和血小板。红细胞的主要功能是运输氧气和二氧化碳。白细胞的主要功能是防御和免疫。血小板的主要功能是止血和凝血。

3.3 血液凝固

血液凝固是一个复杂的生理过程，涉及多种凝血因子的参与。当血管受损时，血液凝固能够防止出血过多，保护机体。

第四章 血液循环

4.1 心脏的泵血功能

心脏是循环系统的动力器官，通过节律性的收缩和舒张，将血液泵入动脉，维持血液循环。心脏的泵血功能包括收缩期和舒张期两个时相。

4.2 心肌的电生理

心肌细胞具有自律性、传导性、兴奋性和收缩性四种生理特性。心肌的电生理特性是心脏节律性活动的基础。

4.3 血管生理

血管是血液流动的管道，包括动脉、毛细血管和静脉。不同类型的血管具有不同的结构和功能特点，共同完成血液循环。

本教材用于学科知识整合智能体测试
"""
    
    output_path.write_text(content, encoding='utf-8')
    print(f"Generated TXT: {output_path}")


def main():
    """主函数"""
    # 创建输出目录
    fixtures_dir = project_root / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成测试文件
    generate_test_pdf(fixtures_dir / "test_textbook.pdf")
    generate_test_markdown(fixtures_dir / "test_textbook.md")
    generate_test_txt(fixtures_dir / "test_textbook.txt")
    
    print("\nTest data generation completed!")
    print(f"Output directory: {fixtures_dir}")


if __name__ == "__main__":
    main()
