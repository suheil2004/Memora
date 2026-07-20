"""Message-aware conversation chunking with bounded overlap."""

from dataclasses import dataclass

from backend.interfaces import ImportedConversation
from backend.models import ConversationChunk, Message, new_id


@dataclass(frozen=True, slots=True)
class ConversationChunker:
    max_tokens: int = 120
    overlap_tokens: int = 30

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not 0 <= self.overlap_tokens < self.max_tokens:
            raise ValueError("overlap_tokens must be non-negative and less than max_tokens")

    def chunk(self, imported: ImportedConversation) -> tuple[ConversationChunk, ...]:
        units = [_format_message(message) for message in imported.messages]
        chunks: list[ConversationChunk] = []
        start = 0
        while start < len(units):
            end = start
            used = 0
            while end < len(units):
                cost = _token_count(units[end])
                if end > start and used + cost > self.max_tokens:
                    break
                used += cost
                end += 1
                if used >= self.max_tokens:
                    break

            selected_messages = imported.messages[start:end]
            source_timestamp = max(
                (message.created_at for message in selected_messages if message.created_at),
                default=(
                    imported.conversation.updated_at
                    or imported.conversation.created_at
                    or imported.conversation.imported_at
                ),
            )
            chunks.append(
                ConversationChunk(
                    id=new_id(),
                    conversation_id=imported.conversation.id,
                    user_id=imported.conversation.user_id,
                    content="\n".join(units[start:end]),
                    ordinal=len(chunks),
                    message_ids=tuple(message.id for message in selected_messages),
                    created_at=source_timestamp,
                )
            )
            if end >= len(units):
                break

            overlap_start = end
            overlap_used = 0
            while overlap_start > start:
                previous_cost = _token_count(units[overlap_start - 1])
                if overlap_used + previous_cost > self.overlap_tokens:
                    break
                overlap_start -= 1
                overlap_used += previous_cost
            # Always advance at least one message, even when all selected messages
            # fit inside the overlap budget and the next message is oversized.
            start = max(start + 1, overlap_start) if overlap_start < end else end
        return tuple(chunks)


def _format_message(message: Message) -> str:
    return f"{message.role.value.title()}: {message.content.strip()}"


def _token_count(text: str) -> int:
    return max(1, len(text.split()))
