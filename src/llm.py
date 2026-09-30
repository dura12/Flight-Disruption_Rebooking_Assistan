from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    kwargs = {"model": model, "temperature": temperature}
    if api_key:
        kwargs["google_api_key"] = api_key
    return ChatGoogleGenerativeAI(**kwargs)
