"""
对话API端点模块

提供多轮对话的REST API：
- POST /chat - 发送消息
- POST /feedback - 提交反馈
- GET /history - 获取对话历史
"""

import logging
import uuid
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.dialogue.context import get_context_manager, Message
from src.llm.client import call_llm

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    suggestions: List[str]


class FeedbackRequest(BaseModel):
    conversation_id: str
    decision_id: str
    feedback_type: str
    content: str


class FeedbackResponse(BaseModel):
    success: bool
    message: str


class HistoryResponse(BaseModel):
    conversation_id: str
    messages: List[Dict[str, Any]]


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """发送消息"""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    conversation_id = request.conversation_id or f"conv_{uuid.uuid4().hex[:8]}"

    context_manager = get_context_manager()
    context = context_manager.get_context(conversation_id)

    # 先取历史再落库，否则最新一条用户消息会在历史里出现一次、
    # 又在下面的「用户最新消息」里重复一次，模型会看到两遍同样的问题。
    conversation_history = "\n".join(
        f"{'用户' if msg.role == 'user' else '助手'}: {msg.content}"
        for msg in context.get_recent_messages(10)
    )

    prompt = f"""你是一个教育知识整合助手，帮助教师理解和优化知识整合方案。

对话历史：
{conversation_history or '（无）'}

用户最新消息：{request.message}

请根据对话历史和用户消息，提供有帮助的回复。如果用户询问整合决策，请解释决策理由。如果用户要求修改决策，请确认修改内容。

回复要求：
1. 准确理解用户意图
2. 引用相关数据和决策
3. 提供具体建议
4. 语气友好专业"""

    try:
        response = await call_llm(
            prompt=prompt,
            system_prompt="你是一个教育知识整合专家，擅长解释整合决策和处理用户反馈。",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("对话生成失败: %s", exc)
        # 失败时不落库，避免留下一条永远得不到回复的用户消息
        raise HTTPException(status_code=502, detail="生成回复失败，请稍后重试") from exc

    context_manager.add_message(conversation_id, "user", request.message)
    context_manager.add_message(conversation_id, "assistant", response)

    return ChatResponse(
        conversation_id=conversation_id,
        response=response,
        suggestions=_generate_suggestions(request.message, response),
    )


def _generate_suggestions(user_message: str, assistant_response: str) -> List[str]:
    """根据用户消息与回复内容生成后续操作建议。"""
    combined = f"{user_message}\n{assistant_response}"
    suggestions: List[str] = []

    if "决策" in combined or "整合" in combined:
        suggestions.append("查看所有整合决策")
        suggestions.append("这个决策的依据是什么？")
    if "知识点" in combined:
        suggestions.append("查看知识点详情")
        suggestions.append("还有哪些相关知识点？")
    if "精简" in combined or "压缩" in combined or "字数" in combined:
        suggestions.append("压缩比是多少？")
    if "引用" in combined or "来源" in combined or "出处" in combined:
        suggestions.append("这些内容来自哪本教材？")

    for fallback in ("查看整合统计", "开始新的整合"):
        if len(suggestions) >= 3:
            break
        if fallback not in suggestions:
            suggestions.append(fallback)

    return suggestions[:3]


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    """提交反馈"""
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="反馈内容不能为空")

    context_manager = get_context_manager()
    context_manager.add_message(
        request.conversation_id,
        "user",
        f"[反馈] {request.content}",
        metadata={
            "type": "feedback",
            "decision_id": request.decision_id,
            "feedback_type": request.feedback_type,
        },
    )

    logger.info("收到反馈: %s（决策 %s）", request.feedback_type, request.decision_id)

    return FeedbackResponse(
        success=True,
        message="反馈已收到，系统将根据反馈调整整合方案",
    )


@router.get("/history/{conversation_id}", response_model=HistoryResponse)
async def get_history(conversation_id: str, limit: int = 200):
    """获取对话历史（默认最多返回最近 200 条）。"""
    context_manager = get_context_manager()
    context = context_manager.get_context(conversation_id)

    messages = [msg.to_dict() for msg in context.messages]
    if limit > 0:
        messages = messages[-limit:]

    return HistoryResponse(conversation_id=conversation_id, messages=messages)


@router.delete("/history/{conversation_id}")
async def clear_history(conversation_id: str):
    """清空对话历史"""
    context_manager = get_context_manager()
    context_manager.clear_context(conversation_id)
    
    return {"message": "对话历史已清空"}
