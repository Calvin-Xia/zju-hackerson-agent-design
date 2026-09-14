"""针对本轮检查与优化所修复行为的回归测试。

覆盖范围：
* 分块偏移量与长度上限（``TextChunker``）；
* 文本工具（定义合并、抽取式摘要）的边界行为；
* RAG 引用补齐、无答案判定、上下文预算；
* 语义对齐一对一匹配、决策应用语义、压缩比达标；
* 整合流水线端到端（不依赖 LLM，走的规则判定路径）；
* 存储层（状态、图谱）的原子写入与损坏处理；
* 抽取器的关系类型归一化与节点合并不改写入参。
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import numpy as np
import pytest

from src.integration.compression import CompressionController
from src.integration.decision import (
    DecisionAction,
    DecisionMaker,
    IntegrationDecision,
    apply_decisions,
)
from src.integration.pipeline import run_integration
from src.integration.alignment import AlignedPair, SemanticAligner
from src.kg.extractor import _normalize_relation_type, merge_nodes
from src.kg.graph_store import KnowledgeGraphStore
from src.kg.models import KnowledgeGraph, KnowledgeNode, KnowledgeRelation
from src.llm.client import extract_json
from src.models.textbook import Chapter, Textbook
from src.rag.chunking import TextChunker
from src.rag.qa import Citation, RAGQuestionAnswerer
from src.shared.state_store import StateStore
from src.shared.text import extractive_condense, merge_definitions


# ----------------------------------------------------------------------
# 分块
# ----------------------------------------------------------------------
class TestChunking:
    def test_chunk_length_bound(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = "".join(f"这是第{i}个句子，用于测试分块逻辑。" for i in range(60))
        chunks = chunker.chunk_text(text)
        assert chunks
        for chunk in chunks:
            assert len(chunk) <= chunker.chunk_size + chunker.chunk_overlap

    def test_offsets_are_monotonic_and_accurate(self):
        chunker = TextChunker(chunk_size=40, chunk_overlap=10)
        sentences = [f"句子编号{i}用于验证偏移。" for i in range(12)]
        text = "".join(sentences)
        pairs = chunker.chunk_text_with_offsets(text)

        assert pairs
        offsets = [start for _, start in pairs]
        assert offsets == sorted(offsets), "偏移量应单调不减"

        # 每个块的「自身内容」应当能在原文对应位置找到
        for content, start in pairs:
            assert text[start:start + len(content)] == content or content in text[start:]

    def test_repeated_sentence_offsets_do_not_collapse(self):
        """重复句子曾导致 char_start 全部指向第一次出现的位置。"""
        chunker = TextChunker(chunk_size=20, chunk_overlap=0)
        text = "重复的句子。" * 8
        pairs = chunker.chunk_text_with_offsets(text)
        offsets = [start for _, start in pairs]
        assert len(set(offsets)) == len(offsets), f"偏移量出现重复: {offsets}"

    def test_chapter_chunks_have_distinct_ids(self):
        textbook = Textbook(
            textbook_id="bk1",
            filename="t.md",
            title="测试教材",
            chapters=[
                Chapter(chapter_id="c1", title="第一章", content="内容甲。" * 30, page_start=1),
                Chapter(chapter_id="c2", title="第二章", content="内容乙。" * 30, page_start=5),
            ],
        )
        chunker = TextChunker(chunk_size=60, chunk_overlap=10)
        chunks = chunker.chunk_textbook(textbook)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))
        assert all(c.char_count == len(c.content) for c in chunks)


# ----------------------------------------------------------------------
# 文本工具
# ----------------------------------------------------------------------
class TestTextUtils:
    def test_merge_definitions_separates_unpunctuated_fragments(self):
        merged = merge_definitions("定义一是这样的", "定义二是那样的")
        assert "定义一是这样的" in merged
        assert "定义二是那样的" in merged
        # 缺少句末标点时应补分隔符，而不是直接黏成一句
        assert merged != "定义一是这样的定义二是那样的"

    def test_merge_definitions_dedupes(self):
        merged = merge_definitions("炎症是防御性反应。", "炎症是防御性反应。")
        assert merged.count("炎症是防御性反应。") == 1

    def test_extractive_condense_within_budget(self):
        text = "第一句定义。第二句补充说明。第三句举例说明。第四句注意事项。"
        result = extractive_condense(text, 20)
        assert 0 < len(result) <= 20

    def test_extractive_condense_keeps_first_sentence(self):
        text = "这是最重要的定义句。补充说明一。补充说明二。"
        result = extractive_condense(text, 12)
        assert result.startswith("这是最重要的定义句") or "这是最重要" in result


# ----------------------------------------------------------------------
# RAG 问答
# ----------------------------------------------------------------------
class TestQABehaviour:
    def _answerer(self) -> RAGQuestionAnswerer:
        return RAGQuestionAnswerer(top_k=3)

    def test_ensure_citations_appends_when_model_omits_all(self):
        citations = [
            Citation("c1", "教材A", "第一章", 1, "内容A", 0.9),
            Citation("c2", "教材B", "第二章", 2, "内容B", 0.8),
        ]
        # 模型完全没写编号 -> 补齐来源列表
        answer = RAGQuestionAnswerer._ensure_citations("这是一段没有标注来源的回答。", citations)
        assert "[1]" in answer
        assert "[2]" in answer
        assert "参考来源" in answer

    def test_ensure_citations_respects_partial_citations(self):
        """模型只引用其中一条时，不应把未使用的来源硬塞进答案。"""
        citations = [
            Citation("c1", "教材A", "第一章", 1, "内容A", 0.9),
            Citation("c2", "教材B", "第二章", 2, "内容B", 0.8),
            Citation("c3", "教材C", "第三章", 3, "内容C", 0.7),
        ]
        answer = RAGQuestionAnswerer._ensure_citations("答案来自教材 A [1]。", citations)
        assert "[1]" in answer
        # 未被模型使用的来源不应出现在答案里
        assert "教材B" not in answer
        assert "教材C" not in answer

    def test_ensure_citations_noop_when_complete(self):
        citations = [Citation("c1", "教材A", "第一章", 1, "内容A", 0.9)]
        answer = RAGQuestionAnswerer._ensure_citations("答案 [1]。", citations)
        assert answer == "答案 [1]。"

    def test_long_answer_with_hedging_word_is_not_no_answer(self):
        long_answer = "根据教材内容，" + "该结论在特定条件下成立，" * 10 + "某些情形下无法确定。"
        assert not RAGQuestionAnswerer._looks_like_no_answer(long_answer)

    def test_short_refusal_is_no_answer(self):
        assert RAGQuestionAnswerer._looks_like_no_answer("当前知识库中未找到相关信息")
        assert RAGQuestionAnswerer._looks_like_no_answer("未找到")

    def test_build_context_respects_budget(self, monkeypatch):
        from src.shared.config import settings

        monkeypatch.setattr(settings, "RAG_MAX_CONTEXT_CHARS", 600, raising=False)
        answerer = self._answerer()
        chunks = [
            {
                "metadata": {
                    "content": "内容" * 500,
                    "textbook_title": f"教材{i}",
                    "chapter_title": "章节",
                    "page_start": i,
                },
                "similarity": 0.9,
            }
            for i in range(5)
        ]
        context, used = answerer._build_context(chunks)
        assert len(context) <= 600
        assert used

    def test_diversify_without_textbook_identifier(self, monkeypatch):
        from src.shared.config import settings

        monkeypatch.setattr(settings, "RAG_MAX_CHUNKS_PER_TEXTBOOK", 3, raising=False)
        answerer = RAGQuestionAnswerer(top_k=6)
        candidates = [
            {"metadata": {"content": f"互不相同的片段内容{i}" * 3}, "similarity": 0.9 - i * 0.01}
            for i in range(6)
        ]
        selected = answerer._dedupe_and_diversify(candidates)
        # 没有教材标识时不应被「单教材上限」误伤
        assert len(selected) == 6


# ----------------------------------------------------------------------
# 语义对齐 / 决策 / 压缩
# ----------------------------------------------------------------------
class TestAlignmentMatching:
    def test_select_one_to_one(self):
        candidates = [(0, 0, 0.99), (0, 1, 0.95), (1, 1, 0.90)]
        selected = SemanticAligner.select_one_to_one(candidates)
        left = [i for i, _, _ in selected]
        right = [j for _, j, _ in selected]
        assert len(left) == len(set(left))
        assert len(right) == len(set(right))
        assert (0, 0, 0.99) in selected

    def test_select_respects_accepted_set(self):
        candidates = [(0, 0, 0.99), (1, 1, 0.90)]
        selected = SemanticAligner.select_one_to_one(candidates, accepted={(1, 1)})
        assert selected == [(1, 1, 0.90)]


class TestDecisionSemantics:
    def _node(self, node_id: str, name: str, definition: str, frequency: int = 1) -> KnowledgeNode:
        return KnowledgeNode(
            id=node_id, name=name, definition=definition, frequency=frequency
        )

    def test_apply_remove_deletes_only_target(self):
        nodes = [
            self._node("a", "炎症", "炎症是防御反应。"),
            self._node("b", "炎症", "炎症是防御反应。"),
        ]
        relations = [KnowledgeRelation(source="a", target="b", relation_type="parallel")]
        decisions = [
            IntegrationDecision(
                decision_id="d1",
                action=DecisionAction.REMOVE,
                affected_nodes=["b"],
                result_node="a",
                reason="重复",
                confidence=0.9,
            )
        ]
        kept, kept_relations, stats = apply_decisions(nodes, relations, decisions)
        assert [n.id for n in kept] == ["a"]
        assert kept_relations == []  # 悬空边被清理
        assert stats.removed_nodes == 1

    def test_apply_merge_unions_definitions_and_frequency(self):
        nodes = [
            self._node("a", "炎症", "炎症是防御性反应。", frequency=1),
            self._node("b", "炎症反应", "炎症由损伤因子引起。", frequency=2),
        ]
        decisions = [
            IntegrationDecision(
                decision_id="d1",
                action=DecisionAction.MERGE,
                affected_nodes=["b", "a"],
                result_node="b",
                reason="同概念",
                confidence=0.95,
            )
        ]
        kept, _, stats = apply_decisions(nodes, [], decisions)
        assert [n.id for n in kept] == ["b"]
        merged = kept[0]
        assert "防御性反应" in merged.definition
        assert "损伤因子" in merged.definition
        assert merged.frequency == 3
        assert stats.merged_nodes == 1

    def test_make_decisions_rule_based_without_llm(self):
        maker = DecisionMaker(use_llm_reason=False)
        nodes = {
            "a": self._node("a", "炎症", "炎症是防御性反应，由损伤因子引起。"),
            "b": self._node("b", "炎症反应", "炎症是防御性反应。"),
        }
        pairs = [
            AlignedPair(
                node1_id="a",
                node2_id="b",
                node1_name="炎症",
                node2_name="炎症反应",
                similarity_score=0.9,
                is_equivalent=True,
                confidence=0.9,
                reason="",
            )
        ]
        result = asyncio.run(maker.make_decisions_for_aligned_pairs(pairs, nodes))
        assert result.total_decisions == 1
        assert result.merge_count + result.keep_count + result.remove_count == 1

    def test_reason_wording_for_same_name_nodes(self):
        """跨教材同名是最常见情况，理由不应是「「静脉」与「静脉」」。"""
        from src.integration.decision import make_rule_based_reason

        a = self._node("a", "静脉", "静脉是导血回心的血管。")
        b = self._node("b", "静脉", "静脉是把血液送回心脏的血管。")

        for action in (DecisionAction.MERGE, DecisionAction.KEEP, DecisionAction.REMOVE):
            reason = make_rule_based_reason(action, a, b, 0.97)
            assert "「静脉」与「静脉」" not in reason
            assert "静脉" in reason


class TestCompressionRatio:
    def _corpus(self):
        nodes = []
        for i in range(30):
            nodes.append(
                KnowledgeNode(
                    id=f"n{i}",
                    name=f"知识点{i}",
                    definition=(
                        f"知识点{i}是指在学习过程中需要掌握的第{i}个核心内容，"
                        "它包含多个方面的含义，既有理论层面的解释，也有实践中的应用场景，"
                        "通常需要结合具体例子加以理解，并在后续章节中反复出现。"
                    ),
                    frequency=1,
                )
            )
        original_chars = sum(len(n.name) + len(n.definition) for n in nodes)
        return nodes, original_chars

    def test_enforce_ratio_reaches_target(self):
        nodes, original_chars = self._corpus()
        controller = CompressionController(max_compression_ratio=0.30)
        result_nodes, _, stats = controller.enforce_ratio(
            nodes, [], original_total_chars=original_chars
        )
        assert stats.compression_ratio <= 0.30 + 1e-9
        assert stats.is_within_limit
        assert result_nodes

    def test_enforce_ratio_keeps_at_least_one_node(self):
        """语料极小时压缩比不可达，但也不应把知识图谱清空。"""
        nodes = [KnowledgeNode(id="n1", name="短", definition="很短的定义")]
        controller = CompressionController(max_compression_ratio=0.30)
        result_nodes, _, stats = controller.enforce_ratio(nodes, [])
        assert [n.id for n in result_nodes] == ["n1"]


# ----------------------------------------------------------------------
# 整合流水线端到端
# ----------------------------------------------------------------------
class TestIntegrationPipeline:
    def _graph(self, textbook_id: str, shared_names, unique_prefix: str) -> KnowledgeGraph:
        nodes = []
        for name in shared_names:
            nodes.append(
                KnowledgeNode(
                    id=f"{textbook_id}_{name}",
                    name=name,
                    definition=f"{name}是{textbook_id}教材中给出的定义，" + "补充说明。" * 12,
                    category="核心概念",
                    textbook_id=textbook_id,
                )
            )
        for i in range(12):
            nodes.append(
                KnowledgeNode(
                    id=f"{textbook_id}_u{i}",
                    name=f"{unique_prefix}知识点{i}",
                    definition=f"{unique_prefix}知识点{i}的详细解释。" + "更多细节。" * 12,
                    category="核心概念",
                    textbook_id=textbook_id,
                )
            )
        relations = [
            KnowledgeRelation(
                source=nodes[0].id, target=nodes[-1].id, relation_type="prerequisite"
            )
        ] if len(nodes) >= 2 else []
        return KnowledgeGraph(
            textbook_id=textbook_id,
            textbook_title=textbook_id,
            nodes=nodes,
            relations=relations,
            total_nodes=len(nodes),
            total_relations=len(relations),
        )

    def test_pipeline_produces_within_limit_result(self):
        shared = ["炎症", "免疫", "细胞"]
        graphs = {
            "bookA": self._graph("bookA", shared, "甲"),
            "bookB": self._graph("bookB", shared, "乙"),
        }
        outcome = asyncio.run(run_integration(graphs))

        stats = outcome.statistics()
        assert stats["original_textbook_count"] == 2
        assert stats["compressed_node_count"] <= stats["original_node_count"]
        assert stats["compression_ratio"] <= 0.30 + 1e-9
        assert stats["is_within_limit"] is True
        assert stats["total_decisions"] >= 1

        # 整合结果中不应出现悬空关系
        node_ids = {n.id for n in outcome.nodes}
        for relation in outcome.relations:
            assert relation.source in node_ids
            assert relation.target in node_ids

        # 同名知识点应被合并（每个共享概念只保留一个节点）
        shared_names = [n.name for n in outcome.nodes if n.name in shared]
        assert len(shared_names) == len(set(shared_names))

    def test_pipeline_rejects_empty_input(self):
        with pytest.raises(ValueError):
            asyncio.run(run_integration({}))


# ----------------------------------------------------------------------
# 存储层
# ----------------------------------------------------------------------
class TestStores:
    def test_state_store_roundtrip_and_update(self, tmp_path):
        store = StateStore(str(tmp_path / "tasks"))
        store.set("t1", {"status": "pending", "progress": 0})
        store.update("t1", {"progress": 50})
        loaded = store.get("t1")
        assert loaded == {"status": "pending", "progress": 50}
        # 返回副本，外部修改不应污染内部状态
        loaded["progress"] = 999
        assert store.get("t1")["progress"] == 50

    def test_state_store_concurrent_updates_do_not_corrupt(self, tmp_path):
        """并发更新不同字段时不应丢字段，落盘文件也必须始终是合法 JSON。"""
        store = StateStore(str(tmp_path / "tasks"))
        store.set("t2", {"base": 0})

        def worker(worker_id: int):
            for i in range(20):
                store.update("t2", {f"w{worker_id}_{i}": i})

        threads = [threading.Thread(target=worker, args=(wid,)) for wid in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        data = store.get("t2")
        assert data is not None
        assert data["base"] == 0
        for wid in range(4):
            for i in range(20):
                assert data[f"w{wid}_{i}"] == i

        # 磁盘文件没有出现半截写入
        raw = (tmp_path / "tasks" / "t2.json").read_text(encoding="utf-8")
        assert json.loads(raw) == data

    def test_graph_store_detects_corruption(self, tmp_path):
        store = KnowledgeGraphStore(str(tmp_path / "kg"))
        graph = KnowledgeGraph(
            textbook_id="b1",
            textbook_title="教材",
            nodes=[KnowledgeNode(id="n1", name="概念", definition="定义")],
            total_nodes=1,
        )
        store.save("b1", graph)
        assert store.load("b1") is not None

        # 破坏文件后：load 抛错，load_safe 返回 None
        (tmp_path / "kg" / "b1_kg.json").write_text("{ not json", encoding="utf-8")
        with pytest.raises(ValueError):
            store.load("b1")
        assert store.load_safe("b1") is None
        # 遍历列表不应因单个坏文件中断
        assert store.list_graphs() == ["b1"]

    def test_graph_store_list_graphs_suffix(self, tmp_path):
        store = KnowledgeGraphStore(str(tmp_path / "kg"))
        graph = KnowledgeGraph(textbook_id="x", nodes=[], total_nodes=0)
        store.save("abc", graph)
        assert store.list_graphs() == ["abc"]


# ----------------------------------------------------------------------
# 抽取器
# ----------------------------------------------------------------------
class TestExtractorHelpers:
    def test_normalize_relation_type(self):
        assert _normalize_relation_type("prerequisite") == "prerequisite"
        assert _normalize_relation_type("Part-Of") == "contains"
        assert _normalize_relation_type(None) == "parallel"
        assert _normalize_relation_type("未知类型") == "parallel"

    def test_merge_nodes_does_not_mutate_input(self):
        original = KnowledgeNode(id="n1", name="细胞", definition="短定义", frequency=1)
        duplicate = KnowledgeNode(id="n1", name="细胞", definition="更长的定义内容", frequency=2)
        batch = [[original], [duplicate]]

        merged = merge_nodes(batch)

        assert len(merged) == 1
        assert merged[0].definition == "更长的定义内容"
        assert merged[0].frequency == 3
        # 入参保持原样
        assert original.definition == "短定义"
        assert original.frequency == 1
        assert duplicate.frequency == 2


# ----------------------------------------------------------------------
# 解析器身份（textbook_id / 标题）
# ----------------------------------------------------------------------
class TestParserIdentity:
    def test_split_stored_name(self):
        from src.parsers.base import split_stored_name

        fid, original = split_stored_name(
            "05970468-ae53-4581-b539-dcc489a79d8f_生理学.md"
        )
        assert fid == "05970468-ae53-4581-b539-dcc489a79d8f"
        assert original == "生理学.md"
        # 不匹配命名约定时保持原样
        assert split_stored_name("test_textbook.txt") == ("test_textbook", "test_textbook.txt")

    def test_parser_strips_storage_prefix(self, tmp_path):
        import src.parsers.txt_parser  # noqa: F401 - 触发解析器注册
        from src.parsers.factory import get_parser

        stored = tmp_path / "05970468-ae53-4581-b539-dcc489a79d8f_生理学.txt"
        stored.write_text("第一章 绪论\n生理学是研究生命活动规律的科学。\n", encoding="utf-8")

        textbook = get_parser("txt").parse(stored)
        assert textbook.textbook_id == "05970468-ae53-4581-b539-dcc489a79d8f"
        assert textbook.title == "生理学"

    def test_resolve_display_title(self):
        from src.shared.utils import resolve_display_title

        fid = "05970468-ae53-4581-b539-dcc489a79d8f"
        stored = f"{fid}_生理学.txt"
        # 历史数据：标题就是存储名 -> 修正
        assert resolve_display_title(stored, stored, fid) == "生理学"
        # 解析器从正文提取的真实标题 -> 保留
        assert resolve_display_title("人体生理学", stored, fid) == "人体生理学"
        # 空标题 -> 用文件名派生
        assert resolve_display_title("", stored, fid) == "生理学"


# ----------------------------------------------------------------------
# 配置解析
# ----------------------------------------------------------------------
class TestSettings:
    def test_env_example_is_loadable(self):
        """`cp .env.example .env` 必须能直接启动服务。"""
        from src.shared.config import Settings

        env_example = Path(__file__).resolve().parents[1] / ".env.example"
        assert env_example.exists()
        cfg = Settings(_env_file=str(env_example))

        assert "http://localhost:5174" in cfg.cors_origins
        assert "xlsx" in cfg.allowed_extensions
        assert cfg.RAG_MIN_SCORE is None
        assert cfg.MAX_COMPRESSION_RATIO == 0.30

    def test_list_settings_accept_comma_and_json(self):
        from src.shared.config import Settings

        comma = Settings(CORS_ORIGINS="a,b , c", ALLOWED_EXTENSIONS="PDF, .Md")
        assert comma.cors_origins == ["a", "b", "c"]
        assert comma.allowed_extensions == ["md", "pdf"]

        json_form = Settings(CORS_ORIGINS='["x", "y"]')
        assert json_form.cors_origins == ["x", "y"]

    def test_empty_list_value(self):
        from src.shared.config import Settings

        assert Settings(CORS_ORIGINS="").cors_origins == []


# ----------------------------------------------------------------------
# LLM JSON 解析
# ----------------------------------------------------------------------
class TestLLMJsonParsing:
    def test_extract_json_from_fence(self):
        raw = '```json\n{"nodes": [], "relations": []}\n```'
        assert extract_json(raw) == {"nodes": [], "relations": []}

    def test_extract_json_from_noisy_text(self):
        raw = '好的，结果如下：{"a": 1} 希望有帮助'
        assert extract_json(raw) == {"a": 1}

    def test_extract_json_raises_on_garbage(self):
        with pytest.raises(ValueError):
            extract_json("完全不是 JSON")
