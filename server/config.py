"""应用配置管理，从环境变量和 .env 文件加载。"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """全局配置单例。"""

    # 服务
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Deepgram (Slice 2 用)
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    DEEPGRAM_MODEL: str = os.getenv("DEEPGRAM_MODEL", "nova-3")
    DEEPGRAM_LANGUAGE: str = os.getenv("DEEPGRAM_LANGUAGE", "en")
    DEEPGRAM_SAMPLE_RATE: int = int(os.getenv("DEEPGRAM_SAMPLE_RATE", "16000"))

    # DeepSeek 详细配置
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_TEMPERATURE: float = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.3"))
    DEEPSEEK_MAX_TOKENS: int = int(os.getenv("DEEPSEEK_MAX_TOKENS", "512"))

    # Embedding 服务 (修正引擎)
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )

    # DeepSeek (Slice 3 用)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
    )

    # OpenAI 备用 (Slice 5 用)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Azure 备用 (Slice 5 用)
    AZURE_SPEECH_KEY: str = os.getenv("AZURE_SPEECH_KEY", "")
    AZURE_SPEECH_REGION: str = os.getenv("AZURE_SPEECH_REGION", "")

    # 修正引擎
    CORRECTION_ENABLED: bool = os.getenv("CORRECTION_ENABLED", "true").lower() == "true"
    MAX_CORRECTION_CALLS: int = int(os.getenv("MAX_CORRECTION_CALLS", "20"))

    # RAG 知识库
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "true").lower() == "true"
    RAG_DATA_DIR: str = os.getenv("RAG_DATA_DIR", "server/data/chroma")


settings = Settings()
