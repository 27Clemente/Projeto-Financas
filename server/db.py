"""Banco de dados local (SQLite) do projeto Finanças.

Sem dependências externas: apenas a biblioteca padrão do Python.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "financas.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  connector_id INTEGER,
  institution_name TEXT,
  image_url TEXT,
  status TEXT,
  execution_status TEXT,
  error_message TEXT,
  last_synced_at TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  type TEXT,
  subtype TEXT,
  name TEXT,
  number TEXT,
  balance REAL DEFAULT 0,
  currency TEXT,
  owner TEXT,
  credit_limit REAL,
  available_credit_limit REAL,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  account_id TEXT,
  date TEXT,
  description TEXT,
  amount REAL DEFAULT 0,
  category TEXT,
  type TEXT,
  status TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS investments (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  name TEXT,
  code TEXT,
  type TEXT,
  subtype TEXT,
  balance REAL DEFAULT 0,
  amount_original REAL,
  amount_profit REAL,
  annual_rate REAL,
  fixed_annual_rate REAL,
  rate REAL,
  rate_type TEXT,
  issuer TEXT,
  status TEXT,
  ref_date TEXT,
  updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_tx_item ON transactions(item_id);
CREATE INDEX IF NOT EXISTS idx_accounts_item ON accounts(item_id);
CREATE INDEX IF NOT EXISTS idx_investments_item ON investments(item_id);
"""


def init_db():
    # with db() fecha a conexão; with connect() travaria o arquivo no Windows.
    with db() as conn:
        conn.executescript(SCHEMA)


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    """Conexão com commit automático no sucesso e rollback em erro.

    Cada operação usa a própria conexão (o servidor atende em várias threads).
    """
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
