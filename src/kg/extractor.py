"""知识点抽取。

相对旧实现的改进：

* ``split_content`` 对超长段落做硬切，保证每段都在 ``EXTRACTION_MAX_CHARS`` 内
  （旧实现遇到没有换行的长段落会直接把超长 Prompt 发出去）；
* 分片并发抽取（受 ``LLM_CONCURRENCY`` 约束），多章节教材抽取显著加速；
* JSON 解析失败会自动重试一次，并跳过结构不完整的知识点；
* 节点合并按「归一化名称」判定，兼顾频次累计与更优描述的保留；
* 关系去重、去自环，并剔除指向不存在节点的悬空边；
* 抽取结果为空时抛出异常，避免把"抽取失败"写成"抽取成功但 0 个知识点"。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.kg.models import KnowledgeGraph, KnowledgeNode, KnowledgeRelation
from src.llm.client import LLMError, call_llm_json
from src.llm.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT
from src.models.textbook import Chapter, Textbook
from src.shared.config import settings

logger = logging.getLogger(__name__)

# 允许的关系类型（与抽取 Prompt 中的约定一致）
RELATION_TYPES = frozenset({"prerequisite", "parallel", "contains", "applies_to"})

_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[\s。．.、，,；;：:!！?？\"'“”‘’（）()\[\]【】]+$")


def normalize_name(name: str) -> str:
    """知识点名称归一化，用于合并与去重。"""
    return _TRAILING_PUNCT_RE.sub("", _WHITESPACE_RE.sub("", name or "")).strip().lower()


def generate_node_id(textbook_id: str, name: str) -> str:
    """生成节点唯一 ID（同一教材内同名知识点共享 ID）。"""
    digest = hashlib.md5(f"{textbook_id}:{normalize_name(name)}".encode("utf-8")).hexdigest()[:8]
    return f"node_{digest}"


def split_content(content: str, max_length: Optional[int] = None) -> List[str]:
    """按段落切分超长内容，段落本身超长时硬切。"""
    if max_length is None:
        max_length = int(settings.EXTRACTION_MAX_CHARS)
    max_length = max(1, int(max_length))
    if not content:
        return []
    if len(content) <= max_length:
        return [content]

    segments: List[str] = []
    current = ""

    for paragraph in content.split("\n"):
        if len(paragraph) > max_length:
            if current:
                segments.append(current.strip())
                current = ""
            segments.extend(
                paragraph[i:i + max_length] for i in range(0, len(paragraph), max_length)
            )
            continue

        if len(current) + len(paragraph) + 1 <= max_length:
            current += paragraph + "\n"
        else:
            if current:
                segments.append(current.strip())
            current = paragraph + "\n"

    if current.strip():
        segments.append(current.strip())

    return [segment for segment in segments if segment]


def parse_llm_response(response: str) -> dict:
    """解析 LLM 返回的 JSON（兼容 markdown 围栏与前后噪声）。"""
    from src.llm.client import extract_json

    data = extract_json(response)
    if not isinstance(data, dict):
        raise ValueError("抽取结果不是 JSON 对象")
    return data


def _normalize_relation_type(value: Any) -> str:
    """把关系类型收敛到已知集合，未知类型退化为 ``parallel``。"""
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in RELATION_TYPES:
        return normalized
    # 常见同义写法容错
    aliases = {
        "前置": "prerequisite",
        "prerequisite_of": "prerequisite",
        "depends_on": "prerequisite",
        "并列": "parallel",
        "parallel_relation": "parallel",
        "包含": "contains",
        "part_of": "contains",
        "include": "contains",
        "应用": "applies_to",
        "applied_to": "applies_to",
        "uses": "applies_to",
    }
    if normalized in aliases:
        return aliases[normalized]
    return "parallel"


def _build_node(
    textbook: Textbook, chapter: Chapter, node_data: Dict[str, Any]
) -> Optional[KnowledgeNode]:
    name = str(node_data.get("name", "") or "").strip()
    if not name:
        return None

    definition = str(node_data.get("definition", "") or "").strip()
    raw_page = node_data.get("page", chapter.page_start)
    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = chapter.page_start

    category = str(node_data.get("category") or "核心概念").strip() or "核心概念"

    return KnowledgeNode(
        id=generate_node_id(textbook.textbook_id, name),
        name=name,
        definition=definition,
        category=category,
        chapter=chapter.title,
        chapter_id=chapter.chapter_id,
        page=page,
        textbook_id=textbook.textbook_id,
    )


async def extract_from_segment(
    textbook: Textbook, chapter: Chapter, segment: str, index: int, total: int
) -> Tuple[List[KnowledgeNode], List[KnowledgeRelation]]:
    """从单个文本片段抽取知识点与关系。"""
    logger.info("抽取 %s 片段 %d/%d", chapter.title, index + 1, total)

    prompt = EXTRACTION_USER_PROMPT.format(
        chapter_title=chapter.title,
        textbook_title=textbook.title or textbook.filename,
        content=segment,
    )

    data = await call_llm_json(
        prompt=prompt,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.1,
    )
    if not isinstance(data, dict):
        return [], []

    nodes: List[KnowledgeNode] = []
    relations: List[KnowledgeRelation] = []

    for node_data in data.get("nodes", []) or []:
        if not isinstance(node_data, dict):
            continue
        node = _build_node(textbook, chapter, node_data)
        if node:
            nodes.append(node)

    # 只有两端都能对上（本片段内出现的知识点）的关系才保留
    name_to_node = {normalize_name(n.name): n for n in nodes}
    for rel_data in data.get("relations", []) or []:
        if not isinstance(rel_data, dict):
            continue
        source_name = normalize_name(str(rel_data.get("source", "")))
        target_name = normalize_name(str(rel_data.get("target", "")))
        if not source_name or not target_name or source_name == target_name:
            continue
        source_node = name_to_node.get(source_name)
        target_node = name_to_node.get(target_name)
        if source_node is None or target_node is None:
            continue

        raw_confidence = rel_data.get("confidence")
        try:
            confidence = float(raw_confidence) if raw_confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None:
            confidence = min(1.0, max(0.0, confidence))

        relation = KnowledgeRelation(
            # 用归一化后的名称生成 ID，避免 LLM 返回非字符串时崩溃
            source=source_node.id,
            target=target_node.id,
            relation_type=_normalize_relation_type(rel_data.get("relation_type")),
            description=str(rel_data.get("description", "") or ""),
        )
        if confidence is not None:
            relation.confidence = confidence
        relations.append(relation)

    return nodes, relations


async def extract_from_chapter(
    textbook: Textbook, chapter: Chapter
) -> Tuple[List[KnowledgeNode], List[KnowledgeRelation]]:
    """从单个章节抽取知识点与关系（片段间并发）。"""
    logger.info("开始抽取章节: %s", chapter.title)

    segments = split_content(chapter.content or "")
    if not segments:
        return [], []

    results = await asyncio.gather(
        *(
            extract_from_segment(textbook, chapter, segment, index, len(segments))
            for index, segment in enumerate(segments)
        ),
        return_exceptions=True,
    )

    nodes: List[KnowledgeNode] = []
    relations: List[KnowledgeRelation] = []
    for index, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.error("抽取 %s 片段 %d 失败: %s", chapter.title, index + 1, result)
            continue
        chapter_nodes, chapter_relations = result
        nodes.extend(chapter_nodes)
        relations.extend(chapter_relations)

    return nodes, relations


def merge_nodes(nodes_list: List[List[KnowledgeNode]]) -> List[KnowledgeNode]:
    """合并节点：同一教材内同名知识点合并，累计频次并保留信息量更大的描述。

    返回**新建**的节点对象，不修改传入的原始节点，
    避免调用方（按章节保留的结果）在合并后被意外改写。
    """
    node_map: Dict[str, KnowledgeNode] = {}

    for nodes in nodes_list:
        for node in nodes:
            key = node.id
            existing = node_map.get(key)
            if existing is None:
                node_map[key] = node.model_copy(deep=True)
                continue

            existing.frequency += max(1, int(node.frequency or 1))
            if len(node.definition or "") > len(existing.definition or ""):
                existing.definition = node.definition
            # 保留更具体的分类与页码信息
            if node.category and existing.category == "核心概念":
                existing.category = node.category
            if not existing.page and node.page:
                existing.page = node.page

    return list(node_map.values())


def merge_relations(relations_list: List[List[KnowledgeRelation]]) -> List[KnowledgeRelation]:
    """合并关系：去重、去自环。"""
    seen: set = set()
    merged: List[KnowledgeRelation] = []

    for relations in relations_list:
        for relation in relations:
            if relation.source == relation.target:
                continue
            key = f"{relation.source}:{relation.target}:{relation.relation_type}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(relation)

    return merged


async def extract_from_textbook(
    textbook: Textbook,
    progress_cb: Optional[Any] = None,
) -> KnowledgeGraph:
    """从整本教材抽取知识图谱（章节间并发）。"""
    logger.info("开始抽取知识图谱: %s", textbook.title or textbook.filename)

    chapters = list(textbook.chapters)
    if not chapters:
        raise ValueError("教材没有可抽取的章节（解析结果为空）")

    results: List[Any] = []
    semaphore = asyncio.Semaphore(max(1, int(settings.LLM_CONCURRENCY)))

    async def run(chapter: Chapter):
        async with semaphore:
            return await extract_from_chapter(textbook, chapter)

    tasks = [asyncio.create_task(run(chapter)) for chapter in chapters]
    chapter_by_task = {task: chapter for task, chapter in zip(tasks, chapters)}
    completed = 0
    for task in asyncio.as_completed(tasks):
        chapter = chapter_by_task.get(task)
        try:
            results.append(await task)
        except Exception as exc:  # 单章失败不影响整本
            logger.error("抽取章节失败: %s", exc)
        completed += 1
        if progress_cb:
            try:
                # 第二个参数用于上报「最近完成的章节」，供前端展示进度详情
                progress_cb(
                    completed / len(chapters) * 100.0,
                    chapter.title if chapter else "",
                )
            except TypeError:
                # 兼容只接受一个参数的旧回调
                progress_cb(completed / len(chapters) * 100.0)
            except Exception:
                pass

    merged_nodes = merge_nodes([nodes for nodes, _ in results])
    merged_relations = merge_relations([relations for _, relations in results])

    node_ids = {node.id for node in merged_nodes}
    valid_relations = [
        relation for relation in merged_relations
        if relation.source in node_ids and relation.target in node_ids
    ]

    if len(merged_nodes) < max(1, int(settings.EXTRACTION_MIN_NODES)):
        raise ValueError(
            f"未能从《{textbook.title or textbook.filename}》中抽取到知识点，"
            "请检查教材内容或 LLM 配置"
        )

    graph = KnowledgeGraph(
        textbook_id=textbook.textbook_id,
        textbook_title=textbook.title or textbook.filename,
        nodes=merged_nodes,
        relations=valid_relations,
        total_nodes=len(merged_nodes),
        total_relations=len(valid_relations),
    )

    logger.info("抽取完成：%d 个知识点，%d 条关系", graph.total_nodes, graph.total_relations)
    return graph
