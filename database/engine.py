from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import Engine


from models import TelegramMessage, Location, MediaProcessingJob

def get_engine(db_path: str = "sqlite:///database/database.db") -> Engine:
    """
    Risolve il percorso del database e restituisce l'Engine di SQLAlchemy/SQLModel.
    """
    if db_path == "sqlite:////database/database.db":
        db_path = "sqlite:///database/database.db"

    if db_path.startswith("sqlite:///"):
        raw_path = db_path[len("sqlite:///"):]
        sqlite_file = Path(raw_path)
        if not sqlite_file.is_absolute():
            sqlite_file = (Path.cwd() / sqlite_file).resolve()
        
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)
        db_path = f"sqlite:///{sqlite_file.as_posix()}"

    connect_args = {"check_same_thread": False} if db_path.startswith("sqlite") else {}
    
    return create_engine(db_path, connect_args=connect_args)

def init_db(engine: Engine):
    """
    Crea tutte le tabelle nel database basandosi sui modelli caricati.
    Se le tabelle esistono già, non fa nulla.
    """
    SQLModel.metadata.create_all(engine)