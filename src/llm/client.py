"""LLM 调用封装。

提供统一的 ``call_llm`` / ``call_llm_json`` 接口，特性：

* 按提供商选择默认模型（可用 ``LLM_MODEL`` 覆盖）；
* 指数退避 + 抖动的重试，仅对可重试错误（限流/超时/5xx）重试；
* 全局并发信号量，避免大批量抽取时把服务端打爆；
* 健壮的 JSON 解析，容忍 markdown 代码块与前后噪声。

``LLM_MAX_RETRIES`` 表示**额外重试次数**，因此实际请求次数为
``LLM_MAX_RETRIES + 1``（默认 3 次重试 = 最多 4 次请求）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import threading
from typing import Any, Dict, List, Optional

import httpx

from src.shared.config import settings
from src.shared.utils import ensure_sslkeylogfile_usable

logger = logging.getLogger(__name__)

# 该环境变量指向不存在的目录时会让 ssl 直接抛错，导致所有 API 调用失败
ensure_sslkeylogfile_usable()

PROVIDER_DEFAULT_MODELS: Dict[str, str] = {
    "deepseek": "deepseek-chat",
    "dashscope": "qwen-plus",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
}

# 仅支持 OpenAI 兼容接口的提供商；anthropic 需要官方 SDK，故不在其中
PROVIDER_BASE_URLS: Dict[str, Optional[str]] = {
    "deepseek": "https://api.deepseek.com",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "openai": None,
}

PROVIDER_API_KEY_FIELDS: Dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class LLMError(RuntimeError):
    """LLM 调用失败。"""


class LLMNotConfiguredError(LLMError):
    """缺少 API Key 或提供商不受支持。"""


class _EmptyResponseError(LLMError):
    """提供商返回了空响应（可重试）。"""


_client_cache: Dict[str, Any] = {}
_client_cache_lock = threading.Lock()
_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_loop: Optional[asyncio.AbstractEventLoop] = None


def get_provider() -> str:
    return (settings.LLM_PROVIDER or "dashscope").lower()


def get_api_key(provider: Optional[str] = None) -> str:
    provider = provider or get_provider()
    field = PROVIDER_API_KEY_FIELDS.get(provider)
    if not field:
        raise LLMNotConfiguredError(f"不支持的 LLM 提供商: {provider}")
    return getattr(settings, field, "") or ""


def get_model_name(provider: Optional[str] = None) -> str:
    """返回当前使用的模型名，``LLM_MODEL`` 优先。"""
    if settings.LLM_MODEL:
        return settings.LLM_MODEL
    provider = provider or get_provider()
    return PROVIDER_DEFAULT_MODELS.get(provider, "deepseek-chat")


def get_llm_client() -> Any:
    """获取（并缓存）异步 LLM 客户端。"""
    provider = get_provider()
    with _client_cache_lock:
        cached = _client_cache.get(provider)
    if cached is not None:
        return cached

    if provider == "anthropic":
        raise LLMNotConfiguredError(
            "anthropic 需使用其官方 SDK，当前仅支持 OpenAI 兼容接口的提供商"
        )
    if provider not in PROVIDER_BASE_URLS:
        raise LLMNotConfiguredError(f"不支持的 LLM 提供商: {provider}")

    api_key = get_api_key(provider)
    if not api_key:
        raise LLMNotConfiguredError(
            f"未配置 {PROVIDER_API_KEY_FIELDS[provider]}，请在 .env 中填写后重试"
        )

    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMError("未安装 openai 依赖") from exc

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PROVIDER_BASE_URLS.get(provider),
        timeout=float(settings.LLM_TIMEOUT),
        max_retries=0,  # 重试逻辑由本模块统一下沉处理
    )
    with _client_cache_lock:
        _client_cache.setdefault(provider, client)
        client = _client_cache[provider]
    logger.info("LLM 客户端就绪: provider=%s, model=%s", provider, get_model_name())
    return client


def _get_semaphore() -> asyncio.Semaphore:
    """按事件循环创建并发信号量（避免跨 loop 复用）。"""
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(max(1, int(settings.LLM_CONCURRENCY)))
        _semaphore_loop = loop
    return _semaphore


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, _EmptyResponseError):
        return True

    from openai import APIStatusError, APIConnectionError, APITimeoutError, RateLimitError

    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in (408, 409, 425, 429) or exc.status_code >= 500
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return False


async def call_llm(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_retries: Optional[int] = None,
) -> str:
    """调用 LLM，返回纯文本。失败抛出 :class:`LLMError`。"""
    retries = settings.LLM_MAX_RETRIES if max_retries is None else max_retries
    attempts = max(1, int(retries) + 1)

    client = get_llm_client()
    model = get_model_name()

    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_error: Optional[Exception] = None
    semaphore = _get_semaphore()

    for attempt in range(attempts):
        try:
            logger.debug("调用 LLM（第 %d/%d 次）model=%s", attempt + 1, attempts, model)
            # 信号量只包住单次请求，退避等待期间释放名额，避免拖慢其他并发调用
            async with semaphore:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            choices = getattr(response, "choices", None) or []
            if not choices:
                raise _EmptyResponseError("LLM 返回了空 choices")
            content = (choices[0].message.content or "").strip()
            usage = getattr(response, "usage", None)
            if usage:
                logger.info(
                    "Token 用量 - prompt=%s, completion=%s, total=%s",
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                )
            if not content:
                raise _EmptyResponseError("LLM 返回了空内容")
            return content

        except Exception as exc:  # noqa: BLE001 - 需要按类型决定是否重试
            last_error = exc
            retryable = _is_retryable(exc)
            logger.warning(
                "LLM 调用失败（第 %d/%d 次，%s）: %s",
                attempt + 1,
                attempts,
                "可重试" if retryable else "不可重试",
                exc,
            )
            if not retryable or attempt == attempts - 1:
                break
            delay = min(2 ** attempt, 8) + random.uniform(0, 1)
            await asyncio.sleep(delay)

    raise LLMError(f"LLM 调用失败: {last_error}") from last_error


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """从可能包含 markdown 围栏或额外文本的响应中取出 JSON。"""
    if not text or not text.strip():
        raise ValueError("响应为空，无法解析 JSON")

    candidates: List[str] = []
    stripped = text.strip()
    candidates.append(stripped)
    candidates.extend(match.strip() for match in _JSON_FENCE_RE.findall(text))

    # 截取最外层的 {} 或 []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        end = stripped.rfind(closer)
        if start >= 0 and end > start:
            candidates.append(stripped[start:end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError(f"无法从响应中解析 JSON: {text[:200]}")


async def call_llm_json(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    max_retries: Optional[int] = None,
    retry_on_parse_error: int = 1,
) -> Any:
    """调用 LLM 并解析 JSON 结果。

    解析失败时会追加一次强约束重试，避免首轮格式跑偏导致整段抽取失败。
    """
    attempt_prompt = prompt
    last_error: Optional[Exception] = None

    for parse_attempt in range(retry_on_parse_error + 1):
        raw = await call_llm(
            prompt=attempt_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )
        try:
            return extract_json(raw)
        except ValueError as exc:
            last_error = exc
            logger.warning("JSON 解析失败（第 %d 次）: %s", parse_attempt + 1, exc)
            attempt_prompt = (
                f"{prompt}\n\n注意：你的上一次回复不是合法 JSON。"
                f"请只输出 JSON 本身，不要任何解释、前后缀或 markdown 代码块。"
            )

    raise LLMError(f"LLM 未返回合法 JSON: {last_error}") from last_error
