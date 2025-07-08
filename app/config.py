import configparser, os

cfg = configparser.ConfigParser()
cfg.read(os.path.join(os.path.dirname(__file__), os.pardir, "config.ini"))

db_cfg = cfg["database"]

DB_URI = (
    f"postgresql+psycopg2://{db_cfg['user']}:{db_cfg['password']}"
    f"@{db_cfg['host']}:{db_cfg.get('port','5432')}/{db_cfg['database']}"
)
MATERIALS_TABLE = db_cfg["materials_table"]
MATERIALS_SCHEMA = db_cfg.get("schema") or None