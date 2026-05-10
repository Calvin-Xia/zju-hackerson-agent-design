EXTRACTION_SYSTEM_PROMPT = """你是一个学科知识分析专家，擅长从教材中提取核心知识点和它们之间的关系。
你需要仔细分析教材内容，提取出结构化的知识点和关系。
请严格按照JSON格式输出，不要添加任何其他文字。"""


EXTRACTION_USER_PROMPT = """请从以下教材章节中提取核心知识点和它们之间的关系。

章节标题: {chapter_title}
教材: {textbook_title}

章节内容:
{content}

请以JSON格式输出，包含以下字段:
{{
  "nodes": [
    {{
      "name": "知识点名称",
      "definition": "简明定义或解释（50-200字）",
      "category": "核心概念|定理|方法|现象"
    }}
  ],
  "relations": [
    {{
      "source": "源知识点名称",
      "target": "目标知识点名称",
      "relation_type": "prerequisite|parallel|contains|applies_to",
      "description": "关系描述（简短说明为什么存在这个关系）"
    }}
  ]
}}

关系类型说明:
- prerequisite: 前置依赖，学习目标知识点前必须先掌握源知识点
- parallel: 并列关系，同一层级的平行概念
- contains: 包含关系，源知识点包含或涵盖目标知识点
- applies_to: 应用关系，源知识点是目标知识点的应用场景

注意:
1. 提取5-15个核心知识点，不要过于细碎
2. 知识点应该是学科中的重要概念、定理、方法或现象
3. 关系要有意义，不要随意创建关系
4. 只输出JSON，不要其他文字

以下是输出示例（以生理学"动作电位"为例）:
{{
  "nodes": [
    {{
      "name": "静息电位",
      "definition": "细胞未受刺激时，存在于细胞膜两侧的电位差，表现为内负外正",
      "category": "核心概念"
    }},
    {{
      "name": "动作电位",
      "definition": "细胞受到刺激后，膜电位发生的一次快速而可逆的倒转",
      "category": "核心概念"
    }},
    {{
      "name": "阈电位",
      "definition": "能够触发动作电位的最小膜电位值",
      "category": "核心概念"
    }}
  ],
  "relations": [
    {{
      "source": "静息电位",
      "target": "动作电位",
      "relation_type": "prerequisite",
      "description": "理解动作电位需要先掌握静息电位的概念"
    }},
    {{
      "source": "阈电位",
      "target": "动作电位",
      "relation_type": "prerequisite",
      "description": "动作电位的产生需要膜电位达到阈电位"
    }}
  ]
}}

现在请分析上面的章节内容，输出JSON:"""
