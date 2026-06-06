"""WebSocket 消息协议定义。使用 Pydantic 模型确保类型安全。"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ─── 客户端 → 服务端 ───────────────────────────────────

class ClientMessageType(str, Enum):
    """客户端发送的消息类型。"""
    CONFIG = "config"
    PING = "ping"


class ConfigMessage(BaseModel):
    """配置消息：设置语言、服务商偏好等。"""
    type: str = ClientMessageType.CONFIG
    source_lang: str = "en"
    target_lang: str = "zh"
    asr_provider: str = "deepgram"
    translation_provider: str = "deepseek"


class PingMessage(BaseModel):
    """心跳消息。"""
    type: str = ClientMessageType.PING


# ─── 服务端 → 客户端 ───────────────────────────────────

class ServerMessageType(str, Enum):
    """服务端发送的消息类型。"""
    SUBTITLE = "subtitle"
    STATUS = "status"
    PONG = "pong"
    ECHO = "echo"  # Slice 1 专用：连通性验证回显


class SubtitleMessage(BaseModel):
    """字幕消息：包含 ASR 识别或翻译结果。"""
    type: str = ServerMessageType.SUBTITLE
    segment_id: str = Field(description="句段唯一标识")
    text: str
    is_final: bool = False
    source: str = "asr"  # "asr" | "translation"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: float = Field(default=0.0)
    replace: bool = Field(default=False, description="前端是否替换同 segment_id 旧条目")
    sequence: int = Field(default=0, description="同 segment 内递增序号")


class StatusMessage(BaseModel):
    """状态消息：当前服务商和延迟信息。"""
    type: str = ServerMessageType.STATUS
    asr_status: str = "idle"  # "idle" | "connected" | "error"
    translation_status: str = "idle"  # "idle" | "connected" | "error"
    latency_ms: int = 0


class PongMessage(BaseModel):
    """心跳响应。"""
    type: str = ServerMessageType.PONG


class EchoMessage(BaseModel):
    """连通性验证回显 (Slice 1 专用)。"""
    type: str = ServerMessageType.ECHO
    original_size: int = 0
    message: str = "audio frame received"
