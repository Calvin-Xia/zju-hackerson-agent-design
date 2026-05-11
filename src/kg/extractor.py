import json
import hashlib
import logging
from typing import List, Tuple

from src.models.textbook import Textbook, Chapter
from src.kg.models import KnowledgeNode, KnowledgeRelation, KnowledgeGraph
from src.llm.client import call_llm
from src.llm.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 6000


def generate_node_id(textbook_id: str, name: str) -> str:
    """生成节点唯一ID"""
    hash_str = hashlib.md5(f"{textbook_id}:{name}".encode()).hexdigest()[:8]
    return f"node_{hash_str}"


def split_content(content: str, max_length: int = MAX_CONTENT_LENGTH) -> List[str]:
    """分段过长内容"""
    if len(content) <= max_length:
        return [content]

    segments = []
    paragraphs = content.split('\n')
    current_segment = ""

    for paragraph in paragraphs:
        if len(current_segment) + len(paragraph) + 1 <= max_length:
            current_segment += paragraph + '\n'
        else:
            if current_segment:
                segments.append(current_segment.strip())
            current_segment = paragraph + '\n'

    if current_segment:
        segments.append(current_segment.strip())

    return segments


def parse_llm_response(response: str) -> dict:
    """解析LLM返回的JSON响应"""
    response = response.strip()

    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]

    response = response.strip()

    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.debug(f"Response content: {response[:500]}")

        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as parse_err:
            logger.warning(f"Failed to extract JSON from response fragment: {parse_err}")

        raise ValueError(f"Invalid JSON response from LLM: {e}")


async def extract_from_chapter(
    textbook: Textbook,
    chapter: Chapter,
) -> Tuple[List[KnowledgeNode], List[KnowledgeRelation]]:
    """从单个章节提取知识点和关系"""
    logger.info(f"Extracting from chapter: {chapter.title}")

    segments = split_content(chapter.content)
    all_nodes: List[KnowledgeNode] = []
    all_relations: List[KnowledgeRelation] = []

    for i, segment in enumerate(segments):
        logger.info(f"Processing segment {i + 1}/{len(segments)} of chapter: {chapter.title}")

        prompt = EXTRACTION_USER_PROMPT.format(
            chapter_title=chapter.title,
            textbook_title=textbook.title,
            content=segment,
        )

        try:
            response = await call_llm(
                prompt=prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
            )

            data = parse_llm_response(response)

            for node_data in data.get("nodes", []):
                node = KnowledgeNode(
                    id=generate_node_id(textbook.textbook_id, node_data["name"]),
                    name=node_data["name"],
                    definition=node_data.get("definition", ""),
                    category=node_data.get("category", "核心概念"),
                    chapter=chapter.title,
                    chapter_id=chapter.chapter_id,
                    page=chapter.page_start,
                    textbook_id=textbook.textbook_id,
                )
                all_nodes.append(node)

            for rel_data in data.get("relations", []):
                source_id = generate_node_id(textbook.textbook_id, rel_data["source"])
                target_id = generate_node_id(textbook.textbook_id, rel_data["target"])
                relation = KnowledgeRelation(
                    source=source_id,
                    target=target_id,
                    relation_type=rel_data.get("relation_type", "parallel"),
                    description=rel_data.get("description", ""),
                )
                all_relations.append(relation)

        except Exception as e:
            logger.error(f"Failed to extract from segment {i + 1}: {e}")
            continue

    return all_nodes, all_relations


def merge_nodes(nodes_list: List[List[KnowledgeNode]]) -> List[KnowledgeNode]:
    """合并节点，同名节点使用语义相似度合并"""
    node_map: dict[str, KnowledgeNode] = {}

    for nodes in nodes_list:
        for node in nodes:
            key = f"{node.textbook_id}:{node.name}"
            if key in node_map:
                node_map[key].frequency += 1
                if len(node.definition) > len(node_map[key].definition):
                    node_map[key].definition = node.definition
            else:
                node_map[key] = node

    return list(node_map.values())


def merge_relations(relations_list: List[List[KnowledgeRelation]]) -> List[KnowledgeRelation]:
    """合并关系，去重"""
    relation_set: set[str] = set()
    merged: List[KnowledgeRelation] = []

    for relations in relations_list:
        for rel in relations:
            key = f"{rel.source}:{rel.target}:{rel.relation_type}"
            if key not in relation_set:
                relation_set.add(key)
                merged.append(rel)

    return merged


async def extract_from_textbook(textbook: Textbook) -> KnowledgeGraph:
    """从整本教材提取知识图谱"""
    logger.info(f"Extracting knowledge graph from textbook: {textbook.title}")

    all_nodes: List[List[KnowledgeNode]] = []
    all_relations: List[List[KnowledgeRelation]] = []

    for chapter in textbook.chapters:
        try:
            nodes, relations = await extract_from_chapter(textbook, chapter)
            all_nodes.append(nodes)
            all_relations.append(relations)
        except Exception as e:
            logger.error(f"Failed to extract from chapter {chapter.title}: {e}")
            continue

    merged_nodes = merge_nodes(all_nodes)
    merged_relations = merge_relations(all_relations)

    valid_relations = []
    node_ids = {node.id for node in merged_nodes}
    for rel in merged_relations:
        if rel.source in node_ids and rel.target in node_ids:
            valid_relations.append(rel)

    graph = KnowledgeGraph(
        textbook_id=textbook.textbook_id,
        textbook_title=textbook.title,
        nodes=merged_nodes,
        relations=valid_relations,
        total_nodes=len(merged_nodes),
        total_relations=len(valid_relations),
    )

    logger.info(f"Extraction completed: {graph.total_nodes} nodes, {graph.total_relations} relations")
    return graph
