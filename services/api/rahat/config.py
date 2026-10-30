import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("RAHAT_MODEL", "claude-opus-5-5")
LLM_ENABLED = os.getenv("RAHAT_LLM", "on").lower() != "off"
USER_AGENT = os.getenv("RAHAT_USER_AGENT", "RAHAT/0.1 (Forge buildathon prototype)")
CORS_ORIGINS = [o.strip() for o in os.getenv("RAHAT_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
