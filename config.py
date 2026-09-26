import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    token: str
    guild_id: int | None
    king_role_name: str
    database_path: str

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is missing. Put it in .env.")
        raw_guild = os.getenv("GUILD_ID", "").strip()
        guild_id = int(raw_guild) if raw_guild else None
        return cls(
            token=token,
            guild_id=guild_id,
            king_role_name=os.getenv("KING_ROLE_NAME", "King").strip() or "King",
            database_path=os.getenv("DATABASE_PATH", "data/inventory.db").strip() or "data/inventory.db",
        )
