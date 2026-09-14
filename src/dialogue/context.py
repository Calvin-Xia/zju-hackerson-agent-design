"""
对话上下文管理模块

实现对话历史和上下文维护：
- 对话历史存储
- 上下文理解
- 指代关系处理
"""

import logging
import json
import os
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """对话消息"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class ConversationContext:
    """对话上下文"""
    conversation_id: str
    messages: List[Message] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)
    current_topic: Optional[str] = None
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """添加消息"""
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.messages.append(message)
        
        self._update_entities(content)
        self._update_topic(content)
    
    def _update_entities(self, content: str):
        """更新实体"""
        pass
    
    def _update_topic(self, content: str):
        """更新主题：取最靠前出现的关键词，而不是固定列表顺序里的第一个。"""
        keywords = ["整合", "决策", "知识点", "合并", "删除", "保留"]
        best_position = None
        best_keyword = None
        for keyword in keywords:
            position = content.find(keyword)
            if position >= 0 and (best_position is None or position < best_position):
                best_position = position
                best_keyword = keyword
        if best_keyword:
            self.current_topic = best_keyword
    
    def get_recent_messages(self, n: int = 10) -> List[Message]:
        """获取最近n条消息"""
        return self.messages[-n:]
    
    def get_context_summary(self) -> str:
        """获取上下文摘要"""
        if not self.messages:
            return "无对话历史"
        
        recent = self.get_recent_messages(5)
        summary = "最近对话：\n"
        for msg in recent:
            role = "用户" if msg.role == "user" else "助手"
            summary += f"{role}: {msg.content[:50]}...\n"
        
        return summary
    
    def clear(self):
        """清空上下文"""
        self.messages.clear()
        self.entities.clear()
        self.current_topic = None


class ContextManager:
    """上下文管理器"""
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化上下文管理器
        
        Args:
            storage_path: 存储路径
        """
        self.storage_path = Path(storage_path) if storage_path else Path("data/dialogue")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.contexts: Dict[str, ConversationContext] = {}
        self._lock = threading.RLock()

    def get_or_create_context(self, conversation_id: str) -> ConversationContext:
        """获取或创建上下文（线程安全）。"""
        with self._lock:
            if conversation_id not in self.contexts:
                context = ConversationContext(conversation_id=conversation_id)
                self.contexts[conversation_id] = context
                self._load_context_into(context)
            return self.contexts[conversation_id]

    def _load_context(self, conversation_id: str) -> None:
        """从磁盘加载上下文（兼容旧调用）。"""
        with self._lock:
            context = self.contexts.get(conversation_id)
            if context is not None:
                self._load_context_into(context)

    def _load_context_into(self, context: ConversationContext) -> None:
        """把磁盘上的历史恢复到给定上下文对象。"""
        conversation_id = context.conversation_id
        context_file = self.storage_path / f"{conversation_id}.json"
        if not context_file.exists():
            return

        try:
            with open(context_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("加载对话上下文失败 %s: %s", conversation_id, exc)
            return

        restored = 0
        for position, msg_data in enumerate(data.get("messages", []) or []):
            try:
                context.messages.append(
                    Message(
                        role=msg_data["role"],
                        content=msg_data["content"],
                        timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                        metadata=msg_data.get("metadata", {}) or {},
                    )
                )
                restored += 1
            except (KeyError, TypeError, ValueError) as exc:
                # 单条消息损坏不应该让整段历史丢失
                logger.warning(
                    "跳过损坏的对话消息 %s[%d]: %s", conversation_id, position, exc
                )

        context.entities = data.get("entities", {}) or {}
        context.current_topic = data.get("current_topic")
        logger.info("已加载对话上下文 %s（%d 条消息）", conversation_id, restored)

    def save_context(self, conversation_id: str) -> None:
        """原子地保存上下文到磁盘。"""
        with self._lock:
            context = self.contexts.get(conversation_id)
            if context is None:
                return

            context_file = self.storage_path / f"{conversation_id}.json"
            tmp_file = context_file.with_suffix(".json.tmp")
            data = {
                "conversation_id": conversation_id,
                "messages": [msg.to_dict() for msg in context.messages],
                "entities": context.entities,
                "current_topic": context.current_topic,
            }
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_file, context_file)
            except OSError as exc:
                tmp_file.unlink(missing_ok=True)
                logger.error("保存对话上下文失败 %s: %s", conversation_id, exc)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加消息"""
        context = self.get_or_create_context(conversation_id)
        context.add_message(role, content, metadata)
        self.save_context(conversation_id)

    def get_context(self, conversation_id: str) -> ConversationContext:
        """获取上下文"""
        return self.get_or_create_context(conversation_id)

    def clear_context(self, conversation_id: str) -> None:
        """清空上下文（内存 + 磁盘）。

        即使会话不在内存中（例如服务重启后直接调用删除），也要删掉磁盘上的
        历史文件，否则下次获取时历史会「复活」。
        """
        with self._lock:
            context = self.contexts.get(conversation_id)
            if context is not None:
                context.clear()
            context_file = self.storage_path / f"{conversation_id}.json"
            if context_file.exists():
                try:
                    context_file.unlink()
                except OSError as exc:
                    logger.error("删除对话历史失败 %s: %s", conversation_id, exc)
            if context is not None:
                self.save_context(conversation_id)


_context_manager: Optional[ContextManager] = None
_context_manager_lock = threading.Lock()


def get_context_manager() -> ContextManager:
    """获取上下文管理器单例"""
    global _context_manager
    if _context_manager is None:
        with _context_manager_lock:
            if _context_manager is None:
                _context_manager = ContextManager()
    return _context_manager
