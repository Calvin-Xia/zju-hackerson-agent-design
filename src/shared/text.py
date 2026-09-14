"""文本处理工具。

被分块、知识整合、压缩等模块共用，集中处理中英文混排的分句、
去重、包含关系判断与抽取式摘要。
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

# 句末标点分句：中文标点直接分，英文句点只在后面跟空白时才算句末
# （避免把 3.14、U.S. 之类切开）
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；…])|(?<=[!?;])|(?<=\.)(?=\s)|(?<=\n)")

# 结尾引号/括号紧跟句末标点时，应回粘到上一句
_TRAILING_PUNCT = "”’\"')）]】》"

# 定义型句式标记，摘要时优先保留
_DEFINITION_MARKERS = (
    "是", "指", "称为", "叫做", "定义", "由", "包括", "分为", "属于", "表示", "用于",
)

_WHITESPACE_RE = re.compile(r"[ \t\u3000]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{2,}")


def normalize_text(text: str) -> str:
    """压缩空白、统一换行，用于比较与展示。"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n", text)
    return text.strip()


def split_sentences(text: str) -> List[str]:
    """把文本切成句子（保留顺序，去掉空串）。"""
    if not text or not text.strip():
        return []

    raw = [segment.strip() for segment in _SENTENCE_SPLIT_RE.split(text)]
    sentences: List[str] = []
    for segment in raw:
        if not segment:
            continue
        # 以收尾引号/括号开头的片段回粘到上一句
        if sentences and segment[0] in _TRAILING_PUNCT:
            sentences[-1] = f"{sentences[-1]}{segment}"
        else:
            sentences.append(segment)
    return sentences


def _char_bigrams(text: str) -> set:
    cleaned = re.sub(r"\s+", "", text)
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


def bigram_jaccard(text1: str, text2: str) -> float:
    """字符二元组 Jaccard 相似度，抗语序差异且无需分词。"""
    set1, set2 = _char_bigrams(text1), _char_bigrams(text2)
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union else 0.0


def contains_text(haystack: str, needle: str) -> bool:
    """判断 ``needle`` 是否已被 ``haystack`` 覆盖（归一化后的子串关系）。"""
    normalized_haystack = normalize_text(haystack)
    normalized_needle = normalize_text(needle)
    if not normalized_needle:
        return True
    return normalized_needle in normalized_haystack


def dedup_sentences(sentences: Iterable[str], similarity_threshold: float = 0.85) -> List[str]:
    """按顺序去重语义重复的句子（近似重复也算）。"""
    kept: List[str] = []
    for sentence in sentences:
        candidate = sentence.strip()
        if not candidate:
            continue
        duplicate = False
        for existing in kept:
            if candidate == existing or contains_text(existing, candidate):
                duplicate = True
                break
            if bigram_jaccard(candidate, existing) >= similarity_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


# 句末标记：拼接定义时用于判断是否需要补分隔符
_SENTENCE_END_CHARS = "。！？；…!?;."


def _join_pieces(pieces: Sequence[str]) -> str:
    """拼接句子片段；缺句末标点时补分隔符，避免出现一长串病句。"""
    result = ""
    for piece in pieces:
        if not piece:
            continue
        if result and result[-1] not in _SENTENCE_END_CHARS:
            result += "；" if not result[-1].isascii() else "; "
        result += piece
    return result


def merge_definitions(*definitions: str, similarity_threshold: float = 0.85) -> str:
    """合并多个知识点描述，去除重复表述并保持原有顺序。"""
    sentences: List[str] = []
    for definition in definitions:
        if definition:
            sentences.extend(split_sentences(normalize_text(definition)))
    return _join_pieces(dedup_sentences(sentences, similarity_threshold))


def _sentence_score(sentence: str, index: int, total: int) -> float:
    """抽取式摘要的句子打分：位置 + 长度 + 定义型标记。"""
    position_score = 1.0 / (1.0 + index) if total else 0.0
    length_score = min(len(sentence), 120) / 120.0
    marker_score = 0.4 if any(marker in sentence for marker in _DEFINITION_MARKERS) else 0.0
    digit_bonus = 0.1 if any(ch.isdigit() for ch in sentence) else 0.0
    return 0.5 * position_score + 0.7 * length_score + marker_score + digit_bonus


def _clip_at_boundary(text: str, max_chars: int) -> str:
    """把 ``text`` 裁到 ``max_chars`` 以内，尽量落在子句/句子边界上。"""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    # 优先句末，其次子句标点，最后退回硬截断（省略号也要算进预算内）
    for delimiters in ("。！？；…!?;", "，,、：（("):
        index = max((window.rfind(ch) for ch in delimiters), default=-1)
        if index >= max_chars * 0.5:
            return window[: index + 1].rstrip()
    return text[: max_chars - 1].rstrip() + "…"


def extractive_condense(text: str, max_chars: int) -> str:
    """把文本压缩到 ``max_chars`` 以内。

    采用抽取式策略：始终保留首句（通常是定义句），其余句子按重要度
    贪心选取，最后按原顺序输出，保证可读性与事实不变。
    必须截断时优先落在标点边界上，避免把词句从中间劈开。
    """
    if not text:
        return ""
    normalized = normalize_text(text)
    if max_chars <= 0:
        return ""
    if len(normalized) <= max_chars:
        return normalized

    sentences = split_sentences(normalized)
    if len(sentences) <= 1:
        return _clip_at_boundary(normalized, max_chars)

    scored = sorted(
        ((_sentence_score(s, i, len(sentences)), i, s) for i, s in enumerate(sentences)),
        key=lambda item: item[0],
        reverse=True,
    )

    selected_indices = {0}  # 首句恒保留
    used = len(sentences[0])
    if used > max_chars:
        return _clip_at_boundary(sentences[0], max_chars)

    for score, index, sentence in scored:
        if index == 0:
            continue
        if used + len(sentence) <= max_chars:
            selected_indices.add(index)
            used += len(sentence)

    ordered = [sentences[i] for i in sorted(selected_indices)]
    result = _join_pieces(ordered)
    if len(result) > max_chars:
        result = _clip_at_boundary(result, max_chars)
    return result


def truncate_at_boundary(text: str, max_chars: int) -> str:
    """在句子/字符边界处截断，避免把句子从中间劈开。"""
    if not text or max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text

    sentences = split_sentences(text)
    result = ""
    for sentence in sentences:
        if len(result) + len(sentence) <= max_chars:
            result += sentence
        else:
            break
    if result:
        return result
    # 单句就超长时，退化为在子句标点处裁剪
    return _clip_at_boundary(normalize_text(text), max_chars)


def dedupe_preserving_order(items: Sequence[str]) -> List[str]:
    seen: set = set()
    result: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
