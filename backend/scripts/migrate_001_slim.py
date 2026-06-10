"""
migrate_001_slim.py — slim-v3 数据库迁移脚本

执行契约：停服务 → python scripts/migrate_001_slim.py → 启服务

操作清单：
  1. 备份 data/boss_autoapply.db → data/boss_autoapply.db.bak-<ts>
  2. job 表新增 9 列（可重复执行：已存在的列自动跳过）
  3. 重建 run_log（旧 vlm_*/backend_*/paused_reason 列已删，旧日志可弃）
  4. 重建 quota（迁 date+apply_count+updated_at，删 vlm_count）
  5. 清掉 B1 产生的空 rules Config 行

注意：本脚本使用裸 sqlite3，不 import SQLModel / app.models，
      以避免启动期 create_all 与脚本之间的版本依赖。
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径解析：脚本在 backend/scripts/，DB 在 backend/data/
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DB_PATH = BACKEND_DIR / "data" / "boss_autoapply.db"


def main() -> None:
    if not DB_PATH.exists():
        print(f"[migrate] DB 不存在：{DB_PATH}，跳过迁移（新库由 init_db 创建）。")
        return

    # ------------------------------------------------------------------
    # 1. 备份
    # ------------------------------------------------------------------
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    bak_path = DB_PATH.with_suffix(f".db.bak-{ts}")
    shutil.copy2(DB_PATH, bak_path)
    print(f"[migrate] 备份 → {bak_path}")

    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    # ------------------------------------------------------------------
    # 2. job 表新增 9 列（幂等：PRAGMA table_info 跳过已存在列）
    # ------------------------------------------------------------------
    cur.execute("PRAGMA table_info(job)")
    existing_cols = {row[1] for row in cur.fetchall()}

    new_job_cols = [
        ("salary_min_k",    "REAL"),
        ("salary_max_k",    "REAL"),
        ("degree",          "TEXT DEFAULT ''"),
        ("experience",      "TEXT DEFAULT ''"),
        ("company_scale",   "TEXT DEFAULT ''"),
        ("finance_stage",   "TEXT DEFAULT ''"),
        ("hr_active",       "TEXT DEFAULT ''"),
        ("hr_name",         "TEXT DEFAULT ''"),
        ("detail_fetched_at", "DATETIME"),
    ]

    added = 0
    for col_name, col_type in new_job_cols:
        if col_name not in existing_cols:
            cur.execute(f"ALTER TABLE job ADD COLUMN {col_name} {col_type}")
            print(f"[migrate] job.{col_name} 已添加")
            added += 1
        else:
            print(f"[migrate] job.{col_name} 已存在，跳过")
    con.commit()
    print(f"[migrate] job 表：新增 {added} 列，跳过 {len(new_job_cols) - added} 列")

    # ------------------------------------------------------------------
    # 3a. 重建 run_log（新结构，旧日志可弃）
    # ------------------------------------------------------------------
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='run_log'")
    if cur.fetchone():
        cur.execute("DROP TABLE run_log")
        print("[migrate] run_log 旧表已删除")

    cur.execute("""
        CREATE TABLE run_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ts             DATETIME NOT NULL DEFAULT (datetime('now')),
            level          TEXT NOT NULL DEFAULT 'INFO',
            event          TEXT NOT NULL DEFAULT '',
            message        TEXT NOT NULL DEFAULT '',
            application_id INTEGER,
            job_id         INTEGER
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_run_log_ts ON run_log(ts)")
    con.commit()
    print("[migrate] run_log 新表已创建")

    # ------------------------------------------------------------------
    # 3b. 重建 quota（迁 date+apply_count+updated_at，删 vlm_count）
    # ------------------------------------------------------------------
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quota'")
    if cur.fetchone():
        # 检查旧表是否有需要迁移的数据
        cur.execute("PRAGMA table_info(quota)")
        quota_cols = {row[1] for row in cur.fetchall()}

        cur.execute("CREATE TABLE quota_new (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, apply_count INTEGER NOT NULL DEFAULT 0, updated_at DATETIME NOT NULL DEFAULT (datetime('now')))")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_quota_new_date ON quota_new(date)")

        if "date" in quota_cols and "apply_count" in quota_cols:
            if "updated_at" in quota_cols:
                cur.execute("INSERT INTO quota_new (date, apply_count, updated_at) SELECT date, apply_count, updated_at FROM quota")
            else:
                cur.execute("INSERT INTO quota_new (date, apply_count) SELECT date, apply_count FROM quota")
            cur.execute("SELECT COUNT(*) FROM quota_new")
            migrated = cur.fetchone()[0]
            print(f"[migrate] quota 迁移了 {migrated} 行")
        else:
            print("[migrate] quota 旧表结构不含预期列，跳过数据迁移")

        cur.execute("DROP TABLE quota")
        cur.execute("ALTER TABLE quota_new RENAME TO quota")
        con.commit()
        print("[migrate] quota 重建完成")
    else:
        # 旧表不存在，直接建新表
        cur.execute("""
            CREATE TABLE quota (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                apply_count INTEGER NOT NULL DEFAULT 0,
                updated_at  DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_quota_date ON quota(date)")
        con.commit()
        print("[migrate] quota 新表已创建（原不存在）")

    # ------------------------------------------------------------------
    # 4. 清掉 B1 产生的空 rules Config 行
    # ------------------------------------------------------------------
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
    if cur.fetchone():
        cur.execute("DELETE FROM config WHERE key='rules' AND (value='' OR value IS NULL)")
        deleted = cur.rowcount
        con.commit()
        print(f"[migrate] 清除空 rules Config 行：{deleted} 行")
    else:
        print("[migrate] config 表不存在，跳过清理")

    con.close()

    # ------------------------------------------------------------------
    # 摘要
    # ------------------------------------------------------------------
    print()
    print("=" * 50)
    print("[migrate] migrate_001_slim 完成")
    print(f"  DB   : {DB_PATH}")
    print(f"  备份 : {bak_path}")
    print("  变更 :")
    print("    job     → +9 列（salary_min/max_k, degree, experience,")
    print("               company_scale, finance_stage, hr_active, hr_name,")
    print("               detail_fetched_at）")
    print("    run_log → 重建（删 vlm_calls/backend_switches/backend_used/paused_reason）")
    print("    quota   → 重建（删 vlm_count）")
    print("    config  → 清除空 rules 行")
    print("=" * 50)


if __name__ == "__main__":
    main()
