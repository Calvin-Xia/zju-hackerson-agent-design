"""
RAG问答模块

实现基于检索的问答功能：
- 文档检索
- 答案生成
- 引用处理
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from src.embedding.service import get_embedding_service
from src.vectorstore.faiss_store import get_vector_store
from src.llm.client import call_llm

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """引用"""
    chunk_id: str
    textbook: str
    chapter: str
    page: int
    content: str
    relevance_score: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "textbook": self.textbook,
            "chapter": self.chapter,
            "page": self.page,
            "content": self.content,
            "relevance_score": self.relevance_score
        }


@dataclass
class QAResponse:
    """问答响应"""
    answer: str
    citations: List[Citation]
    source_chunks: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "source_chunks": self.source_chunks
        }


class RAGQuestionAnswerer:
    """RAG问答器"""
    
    def __init__(self, top_k: int = 5):
        """
        初始化问答器
        
        Args:
            top_k: 检索数量
        """
        self.top_k = top_k
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store()
    
    async def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """
        检索相关文档
        
        Args:
            query: 查询文本
            
        Returns:
            检索结果列表
        """
        query_vector = self.embedding_service.encode(query)
        
        results = self.vector_store.search(query_vector, top_k=self.top_k)
        
        retrieved_chunks = []
        for idx, similarity in results:
            metadata = self.vector_store.get_metadata(idx)
            if metadata:
                retrieved_chunks.append({
                    "metadata": metadata,
                    "similarity": similarity
                })
        
        return retrieved_chunks
    
    async def generate_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> QAResponse:
        """
        生成答案
        
        Args:
            query: 查询文本
            context_chunks: 上下文文档块
            
        Returns:
            问答响应
        """
        context = "\n\n".join([
            f"[来源: {chunk['metadata'].get('textbook_title', '')}, {chunk['metadata'].get('chapter_title', '')}]\n{chunk['metadata'].get('content', '')}"
            for chunk in context_chunks
        ])
        
        prompt = f"""基于以下参考内容回答用户问题。

参考内容：
{context}

用户问题：{query}

要求：
1. 只基于参考内容回答，不要使用自己的知识
2. 每个回答必须附带来源引用，格式为[教材名称, 章节]
3. 如果参考内容中找不到答案，请回复"当前知识库中未找到相关信息"
4. 回答要准确、简洁、完整"""

        try:
            answer = await call_llm(
                prompt=prompt,
                system_prompt="你是一个教育知识问答助手，擅长基于教材内容回答问题。"
            )
            
            citations = []
            source_chunks = []
            
            for chunk in context_chunks:
                metadata = chunk.get("metadata", {})
                citation = Citation(
                    chunk_id=metadata.get("chunk_id", ""),
                    textbook=metadata.get("textbook_title", ""),
                    chapter=metadata.get("chapter_title", ""),
                    page=metadata.get("page_start", 0),
                    content=metadata.get("content", "")[:200],
                    relevance_score=chunk.get("similarity", 0.0)
                )
                citations.append(citation)
                source_chunks.append(metadata.get("content", ""))
            
            return QAResponse(
                answer=answer,
                citations=citations,
                source_chunks=source_chunks
            )
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return QAResponse(
                answer=f"生成答案时出错: {str(e)}",
                citations=[],
                source_chunks=[]
            )
    
    async def answer_question(self, query: str) -> QAResponse:
        """
        回答问题
        
        Args:
            query: 用户问题
            
        Returns:
            问答响应
        """
        logger.info(f"Answering question: {query}")
        
        retrieved_chunks = await self.retrieve(query)
        
        if not retrieved_chunks:
            return QAResponse(
                answer="当前知识库中未找到相关信息",
                citations=[],
                source_chunks=[]
            )
        
        response = await self.generate_answer(query, retrieved_chunks)
        
        logger.info(f"Generated answer with {len(response.citations)} citations")
        
        return response


_qa_instance: Optional[RAGQuestionAnswerer] = None


def get_qa_instance(top_k: int = 5) -> RAGQuestionAnswerer:
    """获取问答器单例"""
    global _qa_instance
    if _qa_instance is None:
        _qa_instance = RAGQuestionAnswerer(top_k=top_k)
    return _qa_instance
