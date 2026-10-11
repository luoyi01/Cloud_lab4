"""Generate local credentials without printing or committing them."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
env = root / ".env"
if not env.exists():
    env.write_text(f"REDIS_PASSWORD={secrets.token_hex(24)}\nAPP_TITLE=班级云留言板\n", encoding="utf-8")
    env.chmod(0o600)
values = dict(line.split("=", 1) for line in env.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#") and "=" in line)
password = values.get("REDIS_PASSWORD", "")
if len(password) < 24 or password.startswith("replace-"):
    raise SystemExit(".env 的 REDIS_PASSWORD 必须是至少 24 字符的本地随机密码。")
local = root / ".local"
local.mkdir(exist_ok=True)
secret = local / "redis.env"
secret.write_text(f"REDIS_PASSWORD={password}\n", encoding="utf-8")
secret.chmod(0o600)
print("Local configuration is ready; credentials are not displayed.")
