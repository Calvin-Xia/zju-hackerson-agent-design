"""
对话模块测试

测试对话上下文管理、API端点
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from src.dialogue.context import ContextManager, ConversationContext, Message


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)


@pytest.fixture
def context_manager(temp_dir):
    return ContextManager(storage_path=str(temp_dir))


class TestMessage:
    """消息测试"""
    
    def test_create_message(self):
        msg = Message(role="user", content="测试消息")
        
        assert msg.role == "user"
        assert msg.content == "测试消息"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}
    
    def test_to_dict(self):
        msg = Message(
            role="assistant",
            content="回复消息",
            metadata={"type": "test"}
        )
        
        data = msg.to_dict()
        
        assert data["role"] == "assistant"
        assert data["content"] == "回复消息"
        assert "timestamp" in data
        assert data["metadata"]["type"] == "test"


class TestConversationContext:
    """对话上下文测试"""
    
    def test_add_message(self):
        context = ConversationContext(conversation_id="test_1")
        
        context.add_message("user", "你好")
        context.add_message("assistant", "你好！有什么可以帮助你的吗？")
        
        assert len(context.messages) == 2
        assert context.messages[0].role == "user"
        assert context.messages[1].role == "assistant"
    
    def test_get_recent_messages(self):
        context = ConversationContext(conversation_id="test_1")
        
        for i in range(15):
            context.add_message("user", f"消息{i}")
        
        recent = context.get_recent_messages(5)
        
        assert len(recent) == 5
        assert recent[0].content == "消息10"
        assert recent[4].content == "消息14"
    
    def test_get_context_summary(self):
        context = ConversationContext(conversation_id="test_1")
        
        context.add_message("user", "什么是炎症？")
        context.add_message("assistant", "炎症是机体对致炎因子的防御性反应。")
        
        summary = context.get_context_summary()
        
        assert "用户" in summary
        assert "助手" in summary
        assert "炎症" in summary
    
    def test_clear(self):
        context = ConversationContext(conversation_id="test_1")
        
        context.add_message("user", "测试")
        context.entities["test"] = "value"
        context.current_topic = "测试"
        
        context.clear()
        
        assert len(context.messages) == 0
        assert len(context.entities) == 0
        assert context.current_topic is None


class TestContextManager:
    """上下文管理器测试"""
    
    def test_get_or_create_context(self, context_manager):
        context1 = context_manager.get_or_create_context("conv_1")
        context2 = context_manager.get_or_create_context("conv_1")
        
        assert context1 is context2
        assert context1.conversation_id == "conv_1"
    
    def test_add_message(self, context_manager):
        context_manager.add_message("conv_1", "user", "测试消息")
        
        context = context_manager.get_context("conv_1")
        assert len(context.messages) == 1
        assert context.messages[0].content == "测试消息"
    
    def test_save_and_load(self, context_manager):
        context_manager.add_message("conv_1", "user", "消息1")
        context_manager.add_message("conv_1", "assistant", "回复1")
        
        new_manager = ContextManager(storage_path=str(context_manager.storage_path))
        context = new_manager.get_context("conv_1")
        
        assert len(context.messages) == 2
        assert context.messages[0].content == "消息1"
        assert context.messages[1].content == "回复1"
    
    def test_clear_context(self, context_manager):
        context_manager.add_message("conv_1", "user", "测试")
        context_manager.clear_context("conv_1")
        
        context = context_manager.get_context("conv_1")
        assert len(context.messages) == 0


class TestDialogueAPI:
    """对话API测试"""
    
    def test_chat_request_validation(self):
        from src.api.routes.dialogue import ChatRequest
        
        request = ChatRequest(message="测试消息")
        assert request.message == "测试消息"
        assert request.conversation_id is None
    
    def test_chat_response_model(self):
        from src.api.routes.dialogue import ChatResponse
        
        response = ChatResponse(
            conversation_id="conv_1",
            response="测试回复",
            suggestions=["建议1", "建议2"]
        )
        assert response.conversation_id == "conv_1"
        assert len(response.suggestions) == 2
    
    def test_feedback_request_validation(self):
        from src.api.routes.dialogue import FeedbackRequest
        
        request = FeedbackRequest(
            conversation_id="conv_1",
            decision_id="decision_1",
            feedback_type="modify",
            content="请修改这个决策"
        )
        assert request.feedback_type == "modify"
    
    def test_history_response_model(self):
        from src.api.routes.dialogue import HistoryResponse
        
        response = HistoryResponse(
            conversation_id="conv_1",
            messages=[
                {"role": "user", "content": "消息1"},
                {"role": "assistant", "content": "回复1"}
            ]
        )
        assert len(response.messages) == 2
