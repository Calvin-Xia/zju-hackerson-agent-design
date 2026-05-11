import logging
from typing import Optional

from openai import AsyncOpenAI

from src.shared.config import settings

logger = logging.getLogger(__name__)

_client_cache: dict[str, AsyncOpenAI] = {}


def get_llm_client() -> AsyncOpenAI:
    """获取LLM客户端实例（带缓存）"""
    provider = settings.LLM_PROVIDER.lower()

    if provider in _client_cache:
        return _client_cache[provider]

    if provider == "deepseek":
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
    elif provider == "openai":
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    elif provider == "dashscope":
        client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    _client_cache[provider] = client
    return client


def get_model_name() -> str:
    """获取模型名称"""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "deepseek":
        return "deepseek-v4-pro"
    elif provider == "openai":
        return "gpt-4o-mini"
    elif provider == "dashscope":
        return "qwen-plus"
    else:
        return "deepseek-v4-pro"


async def call_llm(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_retries: int = 3,
) -> str:
    """调用LLM API，返回文本响应"""
    client = get_llm_client()
    model = get_model_name()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(max_retries):
        try:
            logger.info(f"Calling LLM (attempt {attempt + 1}/{max_retries}), model: {model}")

            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = response.choices[0].message.content
            usage = response.usage

            if usage:
                logger.info(f"Token usage - prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")

            return content.strip()

        except Exception as e:
            logger.error(f"LLM call failed (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                raise

    raise Exception("LLM call failed after all retries")
