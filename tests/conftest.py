import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    pos_csv = tmp_path / "empty_pos.csv"
    monkeypatch.setenv("POS_CSV_PATH", str(pos_csv))
    Path(pos_csv).write_text(
        "order_id,order_date,order_time,store_id,product_id,brand_name,total_amount\n",
        encoding="utf-8",
    )

    import api.database as database

    database.engine = create_engine(url, connect_args={"check_same_thread": False})
    database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
    database.init_db()

    import api.main as main_mod

    main_mod.SessionLocal = database.SessionLocal

    from api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
