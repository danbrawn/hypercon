import configparser, os
from pathlib import Path

cfg = configparser.ConfigParser()
cfg.read(Path(__file__).parent.parent / "config.ini")

db = cfg["database"]
DB_URI = (
    f"postgresql+psycopg2://{db['user']}:{db['password']}"
    f"@{db['host']}:{db.get('port',5432)}/{db['database']}"
)
