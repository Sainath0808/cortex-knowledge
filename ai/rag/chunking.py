"""Token-aware recursive chunking.

Splits documents along semantic boundaries (paragraphs, then sentences)
while keeping each chunk under a token budget, with overlap between
consecutive chunks so context isn't lost at boundaries.
"""

import re
from dataclasses import dataclass
from math import sqrt

import tiktoken

_encoding = tiktoken.get_encoding("cl100k_base")
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+\S.*$")


def count_tokens(text: str) -> int:
    return len(_encoding.encode(text))


@dataclass
class Chunk:
    chunk_index: int
    content: str
    token_count: int


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """Last resort: split by raw tokens for pathological inputs (no punctuation)."""
    tokens = _encoding.encode(text)
    return [_encoding.decode(tokens[i : i + max_tokens]) for i in range(0, len(tokens), max_tokens)]


def _validate_chunk_sizes(max_tokens: int, overlap_tokens: int) -> None:
    if max_tokens < 1:
        raise ValueError("max_tokens must be greater than zero")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be between zero and max_tokens - 1")


def chunk_text(text: str, *, max_tokens: int = 512, overlap_tokens: int = 64) -> list[Chunk]:
    """Recursive splitting: paragraphs -> sentences -> raw tokens.

    Greedily packs units into chunks up to max_tokens, carrying overlap_tokens
    of trailing content into the next chunk.
    """
    _validate_chunk_sizes(max_tokens, overlap_tokens)
    units: list[str] = []
    for para in _split_paragraphs(text):
        if count_tokens(para) <= max_tokens:
            units.append(para)
            continue
        for sent in _split_sentences(para):
            if count_tokens(sent) <= max_tokens:
                units.append(sent)
            else:
                units.extend(_hard_split(sent, max_tokens))

    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0

    def flush():
        nonlocal current, current_tokens
        if not current:
            return
        content = "\n\n".join(current)
        chunks.append(
            Chunk(chunk_index=len(chunks), content=content, token_count=count_tokens(content))
        )
        # Carry overlap: keep trailing units up to overlap_tokens.
        kept: list[str] = []
        kept_tokens = 0
        for unit in reversed(current):
            t = count_tokens(unit)
            if kept_tokens + t > overlap_tokens:
                break
            kept.insert(0, unit)
            kept_tokens += t
        current = kept
        current_tokens = kept_tokens

    for unit in units:
        t = count_tokens(unit)
        if current_tokens + t > max_tokens and current:
            flush()
        current.append(unit)
        current_tokens += t
    if current:
        content = "\n\n".join(current)
        # Avoid emitting an overlap-only tail chunk that duplicates the previous one.
        if not chunks or content not in chunks[-1].content:
            chunks.append(
                Chunk(chunk_index=len(chunks), content=content, token_count=count_tokens(content))
            )
    return chunks


def chunk_fixed(text: str, *, max_tokens: int = 512, overlap_tokens: int = 64) -> list[Chunk]:
    """Split at exact token windows, independent of sentence or paragraph boundaries."""
    _validate_chunk_sizes(max_tokens, overlap_tokens)
    tokens = _encoding.encode(text)
    stride = max_tokens - overlap_tokens
    return [
        Chunk(
            index,
            _encoding.decode(tokens[start : start + max_tokens]),
            len(tokens[start : start + max_tokens]),
        )
        for index, start in enumerate(range(0, len(tokens), stride))
    ]


def chunk_structure_aware(
    text: str, *, max_tokens: int = 512, overlap_tokens: int = 64
) -> list[Chunk]:
    """Split Markdown by headings and repeat each section heading in its chunks."""
    _validate_chunk_sizes(max_tokens, overlap_tokens)
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _MARKDOWN_HEADING.match(stripped):
            if heading or body:
                sections.append((heading, "\n".join(body).strip()))
            heading, body = stripped, []
        else:
            body.append(line)
    if heading or body:
        sections.append((heading, "\n".join(body).strip()))
    if not any(section_heading for section_heading, _ in sections):
        return chunk_text(text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)

    chunks: list[Chunk] = []
    for section_heading, section_body in sections:
        prefix = f"{section_heading}\n\n" if section_heading else ""
        remaining_budget = max_tokens - count_tokens(prefix)
        if remaining_budget < 1 or not section_body:
            section_chunks = chunk_text(
                f"{prefix}{section_body}",
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
        else:
            section_chunks = chunk_text(
                section_body,
                max_tokens=remaining_budget,
                overlap_tokens=min(overlap_tokens, remaining_budget - 1),
            )
            for chunk in section_chunks:
                chunk.content = f"{prefix}{chunk.content}"
                chunk.token_count = count_tokens(chunk.content)
        for chunk in section_chunks:
            chunks.append(Chunk(len(chunks), chunk.content, chunk.token_count))
    return chunks


async def chunk_semantic(
    text: str,
    *,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
    similarity_threshold: float = 0.72,
) -> list[Chunk]:
    """Group adjacent sentences by embedding similarity, then enforce token limits."""
    _validate_chunk_sizes(max_tokens, overlap_tokens)
    if not 0 <= similarity_threshold <= 1:
        raise ValueError("similarity_threshold must be between zero and one")

    sentences = [
        sentence
        for paragraph in _split_paragraphs(text)
        for sentence in _split_sentences(paragraph)
    ]
    if not sentences:
        return []

    from ai.rag.embeddings import embed_texts

    vectors = await embed_texts(sentences)
    if len(vectors) != len(sentences):
        raise ValueError("Embedding provider returned an unexpected number of vectors")

    groups: list[list[str]] = [[sentences[0]]]
    for index in range(len(sentences) - 1):
        left, right = vectors[index], vectors[index + 1]
        if len(left) != len(right):
            raise ValueError("Embedding vectors have inconsistent dimensions")
        denominator = sqrt(sum(value * value for value in left)) * sqrt(
            sum(value * value for value in right)
        )
        similarity = (
            sum(a * b for a, b in zip(left, right, strict=True)) / denominator
            if denominator
            else 0.0
        )
        if similarity < similarity_threshold:
            groups.append([])
        groups[-1].append(sentences[index + 1])

    chunks: list[Chunk] = []
    for group in groups:
        for chunk in chunk_text(
            "\n\n".join(group), max_tokens=max_tokens, overlap_tokens=overlap_tokens
        ):
            chunks.append(Chunk(len(chunks), chunk.content, chunk.token_count))
    return chunks


async def chunk_document(
    text: str,
    *,
    strategy: str = "recursive",
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    if strategy == "fixed":
        return chunk_fixed(text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    if strategy == "recursive":
        return chunk_text(text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    if strategy == "structure_aware":
        return chunk_structure_aware(text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    if strategy == "semantic":
        return await chunk_semantic(text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    raise ValueError(f"Unknown chunking strategy: {strategy}")
