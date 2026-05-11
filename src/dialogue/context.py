"""
对话上下文管理模块

实现对话历史和上下文维护：
- 对话历史存储
- 上下文理解
- 指代关系处理
"""

import logging
import json
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
        """更新主题"""
        keywords = ["整合", "决策", "知识点", "合并", "删除", "保留"]
        for keyword in keywords:
            if keyword in content:
                self.current_topic = keyword
                break
    
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
    
    def get_or_create_context(self, conversation_id: str) -> ConversationContext:
        """获取或创建上下文"""
        if conversation_id not in self.contexts:
            self.contexts[conversation_id] = ConversationContext(
                conversation_id=conversation_id
            )
            self._load_context(conversation_id)
        
        return self.contexts[conversation_id]
    
    def _load_context(self, conversation_id: str):
        """从磁盘加载上下文"""
        context_file = self.storage_path / f"{conversation_id}.json"
        if context_file.exists():
            try:
                with open(context_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                context = self.contexts[conversation_id]
                for msg_data in data.get("messages", []):
                    msg = Message(
                        role=msg_data["role"],
                        content=msg_data["content"],
                        timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                        metadata=msg_data.get("metadata", {})
                    )
                    context.messages.append(msg)
                
                logger.info(f"Loaded context for conversation {conversation_id}")
            except Exception as e:
                logger.error(f"Failed to load context: {e}")
    
    def save_context(self, conversation_id: str):
        """保存上下文到磁盘"""
        if conversation_id not in self.contexts:
            return
        
        context = self.contexts[conversation_id]
        context_file = self.storage_path / f"{conversation_id}.json"
        
        try:
            data = {
                "conversation_id": conversation_id,
                "messages": [msg.to_dict() for msg in context.messages],
                "entities": context.entities,
                "current_topic": context.current_topic
            }
            
            with open(context_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved context for conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Failed to save context: {e}")
    
    def add_message(self, conversation_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """添加消息"""
        context = self.get_or_create_context(conversation_id)
        context.add_message(role, content, metadata)
        self.save_context(conversation_id)
    
    def get_context(self, conversation_id: str) -> ConversationContext:
        """获取上下文"""
        return self.get_or_create_context(conversation_id)
    
    def clear_context(self, conversation_id: str):
        """清空上下文"""
        if conversation_id in self.contexts:
            self.contexts[conversation_id].clear()
            self.save_context(conversation_id)


_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """获取上下文管理器单例"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
