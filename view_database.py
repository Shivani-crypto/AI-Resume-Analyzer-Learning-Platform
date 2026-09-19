"""
Database Inspection Utility for AI Resume Analyzer & Learning Platform.
Run: python view_database.py
"""
import sqlite3
import os

DB_FILES = ["local_dev.db", "resume.db"]

def inspect_db(db_path):
    if not os.path.exists(db_path):
        print(f"❌ Database file '{db_path}' does not exist yet.")
        return

    print("=" * 80)
    print(f"📦 DATABASE: {db_path}")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [t[0] for t in cursor.fetchall() if not t[0].startswith("sqlite_")]

    for table in tables:
        print(f"\n--- 📋 TABLE: {table.upper()} ---")
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [col[1] for col in cursor.fetchall()]
        print("Columns:", " | ".join(columns))

        cursor.execute(f"SELECT * FROM {table} LIMIT 20;")
        rows = cursor.fetchall()
        if not rows:
            print("  (No records found)")
        else:
            for row in rows:
                print(" ", row)

    conn.close()

if __name__ == "__main__":
    for db in DB_FILES:
        inspect_db(db)
