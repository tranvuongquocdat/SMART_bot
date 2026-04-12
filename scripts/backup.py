"""Daily backup script cho SQLite. Chay bang cron hoac APScheduler."""
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = "data/history.db"
BACKUP_DIR = Path("data/backups")
MAX_BACKUPS = 7


def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"history_{timestamp}.db"
    shutil.copy2(DB_PATH, dest)
    print(f"Backup: {dest}")

    # Xoa backup cu
    backups = sorted(BACKUP_DIR.glob("history_*.db"))
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        oldest.unlink()
        print(f"Deleted old backup: {oldest}")


if __name__ == "__main__":
    backup()
