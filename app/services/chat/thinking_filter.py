import re
from typing import Generator, List


def strip_thinking(text: str) -> str:
    """Loại bỏ hoàn toàn các block và header suy nghĩ nội tâm khỏi text."""
    if not text:
        return ""

    cleaned = text
    # 1. Loại bỏ các thẻ thinking/thought/reasoning hoàn chỉnh
    cleaned = re.sub(r"<(?:thinking|thought|reasoning)>[\s\S]*?<\/(?:thinking|thought|reasoning)>", "", cleaned, flags=re.IGNORECASE)

    # 2. Loại bỏ các thẻ thinking chưa đóng (kết thúc ở cuối chuỗi)
    cleaned = re.sub(r"<(?:thinking|thought|reasoning)>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)

    # 3. Loại bỏ các header suy nghĩ dạng markdown heading hoặc bold kèm nội dung tới 2 dấu xuống dòng
    cleaned = re.sub(
        r"^(?:#*\s*|\*\*)(?:Suy nghĩ(?:\s*\([^)]*\))?|Thinking|Thought|Reasoning)(?:\*\*|:)?[\s\S]*?\n\n",
        "",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # 4. Loại bỏ các dòng header đứng riêng lẻ
    cleaned = re.sub(
        r"^(?:Suy nghĩ(?:\s*\([^)]*\))?|Thinking:|Thought:).*$\n?",
        "",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    return cleaned.strip()


class ThinkingStreamFilter:
    """Filter cho SSE streaming chunks để nuốt sạch thẻ và nội dung <thinking>."""

    def __init__(self):
        self.buffer = ""
        self.in_thinking = False

    def process_chunk(self, chunk: str) -> List[str]:
        if not chunk:
            return []

        self.buffer += chunk
        emitted: List[str] = []

        while self.buffer:
            if not self.in_thinking:
                # Kiểm tra xem có thẻ mở <thinking... không
                match_open = re.search(r"<(?:thinking|thought|reasoning)\b[^>]*>", self.buffer, flags=re.IGNORECASE)
                if match_open:
                    # Xuất text phía trước thẻ mở
                    before = self.buffer[: match_open.start()]
                    if before:
                        emitted.append(before)
                    # Chuyển sang trạng thái nuốt thinking
                    self.in_thinking = True
                    self.buffer = self.buffer[match_open.end() :]
                    continue

                # Kiểm tra xem cuối buffer có thể là phần mở đầu của thẻ mở dở dang không (e.g. "<", "<th", "<think")
                partial_match = re.search(r"<[a-zA-Z]*$", self.buffer)
                if partial_match and len(self.buffer) - partial_match.start() < 15:
                    before = self.buffer[: partial_match.start()]
                    if before:
                        emitted.append(before)
                    self.buffer = self.buffer[partial_match.start() :]
                    break

                # Kiểm tra header text đầu dòng như "Suy nghĩ..." hoặc "Thinking..."
                header_match = re.search(
                    r"^(?:#*\s*|\*\*)(?:Suy nghĩ(?:\s*\([^)]*\))?|Thinking|Thought|Reasoning)(?:\*\*|:)?[\s\S]*?\n\n",
                    self.buffer,
                    flags=re.IGNORECASE,
                )
                if header_match:
                    self.buffer = self.buffer[header_match.end() :]
                    continue

                # Không có gì khả nghi, xuất toàn bộ buffer
                emitted.append(self.buffer)
                self.buffer = ""
            else:
                # Đang trong thinking block, tìm thẻ đóng </thinking...>
                match_close = re.search(r"<\/(?:thinking|thought|reasoning)>", self.buffer, flags=re.IGNORECASE)
                if match_close:
                    self.in_thinking = False
                    self.buffer = self.buffer[match_close.end() :]
                else:
                    # Giữ tối đa 15 ký tự cuối phòng trường hợp thẻ đóng </thinking> bị cắt ngang giữa 2 chunks
                    if len(self.buffer) > 15:
                        self.buffer = self.buffer[-15:]
                    break

        return emitted

    def flush(self) -> List[str]:
        """Xả buffer khi kết thúc stream."""
        emitted = []
        if not self.in_thinking and self.buffer:
            emitted.append(self.buffer)
        self.buffer = ""
        self.in_thinking = False
        return emitted
