import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Expects something like: postgresql://postgres:password@db.supabase.co:5432/postgres
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_dev.db")

# Fix legacy postgres:// URL format for SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        # Test connection immediately
        with engine.connect() as conn:
            pass
    except Exception as db_err:
        print(f"[NOTICE] Remote PostgreSQL unavailable ({db_err}). Falling back to local SQLite: sqlite:///./local_dev.db")
        DATABASE_URL = "sqlite:///./local_dev.db"
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
