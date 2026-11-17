"""Servidor local do projeto Finanças — Python puro, sem dependências externas.

Uso:  python server/app.py   →  http://127.0.0.1:3000
"""

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import db as database
import pluggy

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"


def load_env(path):
    """Carrega um .env simples (KEY=VALUE) sem dependências."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    except FileNotFoundError:
        pass


load_env(ROOT / ".env")

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "3000"))

APP_SECRET = os.environ.get("APP_SECRET", "").strip()
AUTH_ATIVO = bool(APP_SECRET)
COOKIE = "financas_sessao"
SESSION_MAX = 30 * 24 * 3600


class NaoAutorizado(Exception):
    pass


def senha_hash(senha, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 120_000).hex()
    return f"{salt}${digest}"


def senha_valida(senha, guardado):
    try:
        salt, esperado = guardado.split("$", 1)
        atual = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 120_000).hex()
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(atual, esperado)


def sessao_token(user_id):
    payload = f"{user_id}|{int(time.time()) + SESSION_MAX}"
    assinatura = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{assinatura}"


def sessao_usuario(token):
    try:
        uid, exp, assinatura = token.split("|", 2)
        payload = f"{uid}|{exp}"
        esperado = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(assinatura, esperado) or int(exp) < time.time():
            return None
        return uid
    except (ValueError, AttributeError):
        return None


def cookie_valor(handler, nome):
    for parte in (handler.headers.get("Cookie") or "").split(";"):
        chave, _, valor = parte.strip().partition("=")
        if chave == nome:
            return valor
    return None


def definir_cookie(handler, valor, max_age=SESSION_MAX):
    seguro = " Secure" if (handler.headers.get("X-Forwarded-Proto") or "").lower() == "https" else ""
    handler._cookie = (
        f"{COOKIE}={valor}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{seguro}"
    )


def usuario_atual(handler):
    if not AUTH_ATIVO:
        return "local"
    uid = sessao_usuario(cookie_valor(handler, COOKIE) or "")
    if not uid:
        raise NaoAutorizado()
    with database.db() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
            raise NaoAutorizado()
    return uid


def pluggy_user_id(user_id):
    return "local-user" if user_id == "local" else f"user-{user_id}"

# Development não tem conector Live; 1 já basta para Produção.
PRODUCTION_CONNECTOR_THRESHOLD = 1


def app_mode():
    """Detecta se as credenciais são de aplicação Development ou Production.

    Aplicação criada em Development (dashboard → Applications) só enxerga os
    conectores sandbox; para bancos reais é precisa criar uma aplicação em
    Production ("Go to production") e usar as chaves dela.
    """
    env = os.environ.get("PLUGGY_MODE", "").strip().lower()
    if env in ("production", "development"):
        return env
    try:
        stats = pluggy.connector_stats()
    except pluggy.PluggyError:
        return None  # sem rede/credenciais: não opina
    return "production" if stats["live"] >= PRODUCTION_CONNECTOR_THRESHOLD else "development"


def include_sandbox():
    """Se o widget deve listar os conectores de teste (sandbox)."""
    override = os.environ.get("PLUGGY_INCLUDE_SANDBOX", "").strip().lower()
    if override in ("1", "true", "yes", "on"):
        return True
    if override in ("0", "false", "no", "off"):
        return False
    mode = app_mode()
    return mode != "production"  # em Development, só há sandbox para mostrar


def iso(dt=None):
    dt = dt or datetime.now(timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def current_month():
    d = datetime.now().strftime("%Y-%m")
    return d


# ---------------------------------------------------------------------------
# Sincronização: baixa os dados do Pluggy e grava no SQLite local
# ---------------------------------------------------------------------------

def upsert_item(conn, item, user_id):
    connector = item.get("connector") or {}
    conn.execute(
        """INSERT INTO items (id, user_id, connector_id, institution_name, image_url,
                              status, execution_status, error_message, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             connector_id = excluded.connector_id,
             institution_name = excluded.institution_name,
             image_url = excluded.image_url,
             status = excluded.status,
             execution_status = excluded.execution_status,
             error_message = excluded.error_message""",
        (
            item.get("id"),
            user_id,
            connector.get("id"),
            connector.get("name"),
            connector.get("imageUrl"),
            item.get("status"),
            item.get("executionStatus"),
            (item.get("error") or {}).get("message"),
            item.get("createdAt") or iso(),
        ),
    )


def pull_item_data(item_id, api_key, user_id):
    """Baixa contas, transações e investimentos; grava tudo em uma única transação."""
    started_at = iso(datetime.now(timezone.utc) - timedelta(seconds=5))
    now = iso()

    accounts = pluggy.list_accounts(item_id, api_key)
    transactions_batches = [
        list(pluggy.iter_transactions(acc["id"], api_key)) for acc in accounts
    ]
    investments = pluggy.list_investments(item_id, api_key)

    with database.db() as conn:
        # --- Contas ---
        for acc in accounts:
            credit = acc.get("creditData") or {}
            conn.execute(
                """INSERT INTO accounts (id, user_id, item_id, type, subtype, name, number, balance,
                                         currency, owner, credit_limit,
                                         available_credit_limit, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     item_id = excluded.item_id, type = excluded.type,
                     subtype = excluded.subtype, name = excluded.name,
                     number = excluded.number, balance = excluded.balance,
                     currency = excluded.currency, owner = excluded.owner,
                     credit_limit = excluded.credit_limit,
                     available_credit_limit = excluded.available_credit_limit,
                     updated_at = excluded.updated_at""",
                (
                    acc.get("id"),
                    user_id,
                    item_id,
                    acc.get("type"),
                    acc.get("subtype"),
                    acc.get("name"),
                    acc.get("number"),
                    acc.get("balance") or 0,
                    acc.get("currencyCode"),
                    acc.get("owner"),
                    credit.get("creditLimit"),
                    credit.get("availableCreditLimit"),
                    now,
                ),
            )

        # --- Transações (cursor /v2) ---
        for account_id, batches in zip([a["id"] for a in accounts], transactions_batches):
            for batch in batches:
                for tx in batch:
                    conn.execute(
                        """INSERT INTO transactions (id, user_id, item_id, account_id, date, description,
                                                     amount, category, type, status, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET
                             account_id = excluded.account_id, date = excluded.date,
                             description = excluded.description, amount = excluded.amount,
                             category = excluded.category, type = excluded.type,
                             status = excluded.status, updated_at = excluded.updated_at""",
                        (
                            tx.get("id"),
                            user_id,
                            item_id,
                            tx.get("accountId") or account_id,
                            tx.get("date"),
                            tx.get("description") or tx.get("descriptionRaw"),
                            tx.get("amount") or 0,
                            tx.get("category"),
                            tx.get("type"),
                            tx.get("status"),
                            now,
                        ),
                    )

        # --- Investimentos ---
        for inv in investments:
            conn.execute(
                """INSERT INTO investments (id, user_id, item_id, name, code, type, subtype, balance,
                                            amount_original, amount_profit, annual_rate,
                                            fixed_annual_rate, rate, rate_type, issuer, status,
                                            ref_date, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name = excluded.name, code = excluded.code, type = excluded.type,
                     subtype = excluded.subtype, balance = excluded.balance,
                     amount_original = excluded.amount_original,
                     amount_profit = excluded.amount_profit,
                     annual_rate = excluded.annual_rate,
                     fixed_annual_rate = excluded.fixed_annual_rate,
                     rate = excluded.rate, rate_type = excluded.rate_type,
                     issuer = excluded.issuer, status = excluded.status,
                     ref_date = excluded.ref_date, updated_at = excluded.updated_at""",
                (
                    inv.get("id"),
                    user_id,
                    item_id,
                    inv.get("name"),
                    inv.get("code"),
                    inv.get("type"),
                    inv.get("subtype"),
                    inv.get("balance") or 0,
                    inv.get("amountOriginal"),
                    inv.get("amountProfit"),
                    inv.get("annualRate"),
                    inv.get("fixedAnnualRate"),
                    inv.get("rate"),
                    inv.get("rateType"),
                    inv.get("issuer"),
                    inv.get("status"),
                    inv.get("date"),
                    now,
                ),
            )

        # Resposta vazia pode ser falha do provedor: não apaga nada.
        if not accounts and not any(transactions_batches) and not investments:
            print(f"[aviso] item {item_id}: resposta vazia do Pluggy; dados locais mantidos.")
            return

        # Contas recebem updated_at = now no upsert acima; as que a
        # instituição deixou de reportar mantêm updated_at antigo e saem
        # aqui — mesmo padrão de transações/investimentos, sem SQL dinâmico.
        conn.execute(
            "DELETE FROM accounts WHERE user_id = ? AND item_id = ? "
            "AND (updated_at IS NULL OR updated_at < ?)",
            (user_id, item_id, started_at),
        )
        conn.execute(
            "DELETE FROM transactions WHERE user_id = ? AND item_id = ? AND updated_at < ?",
            (user_id, item_id, started_at),
        )
        conn.execute(
            "DELETE FROM investments WHERE user_id = ? AND item_id = ? AND updated_at < ?",
            (user_id, item_id, started_at),
        )


def sync_item(item_id, trigger, user_id):
    with database.db() as conn:
        dono = conn.execute("SELECT user_id FROM items WHERE id = ?", (item_id,)).fetchone()
    if dono and dono["user_id"] != user_id:
        raise pluggy.PluggyError("Conexão não encontrada.", "NOT_FOUND", 404)

    api_key = pluggy.get_api_key()
    if trigger:
        try:
            pluggy.trigger_sync(item_id, api_key)
        except pluggy.PluggyError as exc:
            # Itens do Meu Pluggy atualizam sozinhos a cada 24h e não aceitam
            # update manual — segue para a leitura dos dados mesmo assim.
            print(f"[aviso] update manual ignorado ({item_id}): {exc}")

    # Aguarda a execução terminar (conexões novas coletam ~365 dias de dados).
    item = None
    timed_out = True
    for _ in range(45):
        item = pluggy.get_item(item_id, api_key)
        execution_status = (item or {}).get("executionStatus")
        if execution_status and execution_status != "RUNNING":
            timed_out = False
            break
        time.sleep(2)

    if not item:
        raise pluggy.PluggyError("Conexão não encontrada no Pluggy.", "NOT_FOUND")

    # Item novo (ainda não salvo aqui) precisa vir do connect token desta pessoa.
    # Algumas respostas do Pluggy não trazem clientUserId; nesse caso seguimos.
    if not dono:
        item_uid = item.get("clientUserId")
        if item_uid and item_uid != pluggy_user_id(user_id):
            raise pluggy.PluggyError("Conexão não encontrada.", "NOT_FOUND", 404)

    with database.db() as conn:
        upsert_item(conn, item, user_id)

    if timed_out:
        return {
            "ok": False,
            "status": "TIMEOUT",
            "message": "A sincronização demorou mais que o esperado. Tente de novo em instantes.",
        }

    execution_status = item.get("executionStatus")
    if execution_status and execution_status not in ("SUCCESS", "PARTIAL_SUCCESS"):
        return {
            "ok": False,
            "status": execution_status,
            "message": (item.get("error") or {}).get("message")
            or "A sincronização com o banco falhou.",
        }

    pull_item_data(item_id, api_key, user_id)
    with database.db() as conn:
        conn.execute(
            "UPDATE items SET last_synced_at = ?, error_message = NULL "
            "WHERE id = ? AND user_id = ?",
            (iso(), item_id, user_id),
        )
    return {"ok": True, "status": execution_status or "SUCCESS"}


# ---------------------------------------------------------------------------
# Consultas de leitura
# ---------------------------------------------------------------------------

def get_summary(month, user_id):
    with database.db() as conn:
        accounts = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN type = 'BANK' THEN balance END), 0) AS bank_balance,
                      COALESCE(SUM(CASE WHEN type = 'CREDIT' THEN balance END), 0) AS credit_balance,
                      COUNT(*) AS accounts
               FROM accounts WHERE user_id = ?""",
            (user_id,),
        ).fetchone()

        # Open Finance não traz amountProfit; nesse caso usamos balance - amountOriginal.
        investments = conn.execute(
            """SELECT COALESCE(SUM(balance), 0) AS invested,
                      COALESCE(SUM(CASE
                        WHEN amount_profit IS NOT NULL THEN amount_profit
                        WHEN amount_original IS NOT NULL THEN balance - amount_original
                      END), 0) AS profit,
                      COALESCE(SUM(CASE
                        WHEN amount_profit IS NOT NULL THEN balance - amount_profit
                        WHEN amount_original IS NOT NULL THEN amount_original
                      END), 0) AS profit_base,
                      COUNT(*) AS investments
               FROM investments
               WHERE user_id = ? AND (status IS NULL OR status = 'ACTIVE')""",
            (user_id,),
        ).fetchone()

        transactions = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount END), 0) AS expenses,
                      COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS income,
                      COUNT(*) AS transactions
               FROM transactions WHERE user_id = ? AND date LIKE ?""",
            (user_id, month + "%"),
        ).fetchone()

        items = conn.execute(
            "SELECT COUNT(*) AS n FROM items WHERE user_id = ?", (user_id,)
        ).fetchone()

    profit_base = investments["profit_base"]
    return {
        "month": month,
        "bankBalance": accounts["bank_balance"],
        "creditBalance": accounts["credit_balance"],
        "accounts": accounts["accounts"],
        "invested": investments["invested"],
        "profit": investments["profit"],
        "profitBase": profit_base,
        "profitRate": (investments["profit"] / profit_base * 100) if profit_base > 0 else None,
        "investments": investments["investments"],
        "expenses": transactions["expenses"],
        "income": transactions["income"],
        "transactions": transactions["transactions"],
        "items": items["n"],
    }


def _p(params, name, default=""):
    """Lê um parâmetro vindo de parse_qs (lista) ou de um dict simples."""
    values = params.get(name)
    if not values:
        return default
    return values[0] if isinstance(values, (list, tuple)) else values


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _valid_item_id(value):
    """IDs vindo da URL precisam ser simples (sem '/', '?', '#', '%' ou espaços)."""
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None


def _origin_allowed(handler):
    """Bloqueia requisições de outros sites (CSRF) quando o header Origin existe.

    Clientes locais (curl, testes) não enviam Origin e continuam funcionando.
    """
    origin = handler.headers.get("Origin")
    if not origin:
        return True
    host = handler.headers.get("Host") or f"127.0.0.1:{PORT}"
    return origin in (f"http://{host}", f"https://{host}")


def list_transactions(params, user_id):
    month = _p(params, "month")
    type_filter = _p(params, "type")
    category = _p(params, "category")
    account_id = _p(params, "accountId")
    q = _p(params, "q").strip()
    limit = min(max(_int(_p(params, "limit"), 50), 1), 500)
    offset = max(_int(_p(params, "offset"), 0), 0)

    where = ["t.user_id = ?"]
    args = [user_id]
    if month:
        where.append("t.date LIKE ?")
        args.append(month + "%")
    if type_filter == "out":
        where.append("t.amount < 0")
    if type_filter == "in":
        where.append("t.amount > 0")
    if category:
        where.append("COALESCE(NULLIF(t.category, ''), 'Sem categoria') = ?")
        args.append(category)
    if account_id:
        where.append("t.account_id = ?")
        args.append(account_id)
    if q:
        where.append("(t.description LIKE ? OR t.category LIKE ?)")
        args.extend([f"%{q}%", f"%{q}%"])
    where_sql = " ".join(["WHERE", " AND ".join(where)]) if where else ""

    with database.db() as conn:
        # Fragmentos são literais fixos; valores entram por placeholder.
        count_sql = " ".join(["SELECT COUNT(*) AS n FROM transactions t", where_sql])
        total = conn.execute(count_sql, args).fetchone()["n"]
        rows_sql = " ".join(
            [
                """SELECT t.id, t.date, t.description, t.amount, t.category, t.type,
                          t.account_id,
                          COALESCE(a.name, '') AS account_name,
                          COALESCE(i.institution_name, '') AS institution
                   FROM transactions t
                   LEFT JOIN accounts a ON a.id = t.account_id
                   LEFT JOIN items i ON i.id = t.item_id""",
                where_sql,
                "ORDER BY t.date DESC, t.id LIMIT ? OFFSET ?",
            ]
        )
        rows = conn.execute(rows_sql, args + [limit, offset]).fetchall()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# Servidor HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "Financas/0.1"

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_PATCH(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if getattr(self, "_cookie", None):
            self.send_header("Set-Cookie", self._cookie)
            self._cookie = None
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":  # HEAD responde só com os cabeçalhos
            self.wfile.write(body)

    def _text(self, status, text, content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' https://cdn.pluggy.ai; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.pluggy.ai; "
            "frame-src https:; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "object-src 'none'; base-uri 'none'",
        )

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        if length > 1024 * 1024:
            raise pluggy.PluggyError("Corpo da requisição muito grande.", "PAYLOAD_TOO_LARGE", 413)
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except ValueError:
            raise pluggy.PluggyError("JSON inválido.", "BAD_JSON")

    def _dispatch(self):
        self._cookie = None
        try:
            parts = urlsplit(self.path)
            if parts.path.startswith("/api/"):
                self._api(parts)
            elif self.command in ("GET", "HEAD"):
                self._static(parts.path)
            else:
                self._json(405, {"error": "Método não permitido."})
        except Exception as exc:  # noqa: BLE001 - vira resposta JSON
            print(f"[erro] {exc!r}")
            try:
                if isinstance(exc, pluggy.PluggyError):
                    status = exc.status if isinstance(exc.status, int) and 400 <= exc.status < 600 else 500
                    payload = {"error": str(exc) or "Erro interno."}
                    if exc.code:
                        payload["code"] = exc.code  # código estável p/ o frontend traduzir
                else:
                    # Não devolve mensagens internas (paths, exceções) ao cliente.
                    status, payload = 500, {"error": "Erro interno no servidor."}
                self._json(status, payload)
            except Exception as resp_exc:  # noqa: BLE001 - falha ao responder
                print(f"[erro] falha ao responder: {resp_exc!r}")

    # ---------------- rotas da API ----------------

    # Rotas de leitura: usadas para responder 405 (em vez de 404) quando o
    # método não combina com a rota.
    READ_ROUTES = {
        "/api/status", "/api/summary", "/api/accounts", "/api/months",
        "/api/categories", "/api/transactions", "/api/investments", "/api/items",
    }

    def _registrar(self):
        body = self._body()
        email = str(body.get("email") or "").strip().lower()
        senha = str(body.get("senha") or "")
        if "@" not in email or len(email) > 254 or len(senha) < 8:
            return self._json(400, {"error": "E-mail inválido ou senha com menos de 8 caracteres."})
        uid = secrets.token_hex(16)
        try:
            with database.db() as conn:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (uid, email, senha_hash(senha), iso()),
                )
        except sqlite3.IntegrityError:
            return self._json(409, {"error": "Esse e-mail já está cadastrado."})
        definir_cookie(self, sessao_token(uid))
        return self._json(200, {"ok": True, "email": email})

    def _entrar(self):
        body = self._body()
        email = str(body.get("email") or "").strip().lower()
        senha = str(body.get("senha") or "")
        with database.db() as conn:
            row = conn.execute(
                "SELECT id, password_hash FROM users WHERE email = ?", (email,)
            ).fetchone()
        if not row or not senha_valida(senha, row["password_hash"]):
            return self._json(401, {"error": "E-mail ou senha incorretos."})
        definir_cookie(self, sessao_token(row["id"]))
        return self._json(200, {"ok": True, "email": email})

    def _api(self, parts):
        # HEAD responde como GET, só sem corpo (regra do HTTP).
        method = "GET" if self.command == "HEAD" else self.command
        path = parts.path
        params = parse_qs(parts.query)

        if method == "POST" and path == "/api/register":
            return self._registrar()
        if method == "POST" and path == "/api/login":
            return self._entrar()
        if method == "POST" and path == "/api/logout":
            definir_cookie(self, "", 0)
            return self._json(200, {"ok": True})
        if method == "GET" and path == "/api/me":
            if not AUTH_ATIVO:
                return self._json(200, {"autenticado": True, "modo": "local", "email": None})
            uid = sessao_usuario(cookie_valor(self, COOKIE) or "")
            email = None
            if uid:
                with database.db() as conn:
                    row = conn.execute("SELECT email FROM users WHERE id = ?", (uid,)).fetchone()
                    email = row["email"] if row else None
            return self._json(200, {"autenticado": bool(email), "modo": "publico", "email": email})

        if method not in ("GET", "POST", "DELETE"):
            return self._json(405, {"error": "Método não permitido."})
        if method in ("POST", "DELETE") and not _origin_allowed(self):
            return self._json(403, {"error": "Origem não permitida."})

        try:
            uid = usuario_atual(self)
        except NaoAutorizado:
            return self._json(401, {"error": "Faça login para continuar.", "code": "UNAUTHORIZED"})

        if method == "GET" and path == "/api/status":
            with database.db() as conn:
                items = conn.execute(
                    "SELECT COUNT(*) AS n FROM items WHERE user_id = ?", (uid,)
                ).fetchone()["n"]
            payload = {
                "configured": pluggy.has_credentials(),
                "items": items,
                "mode": None,
                "includeSandbox": True,
                "liveConnectors": None,
            }
            if payload["configured"]:
                payload["mode"] = app_mode()
                payload["includeSandbox"] = include_sandbox()
                try:
                    payload["liveConnectors"] = pluggy.connector_stats()["live"]
                except pluggy.PluggyError as exc:
                    payload["connectorsError"] = str(exc)
            return self._json(200, payload)

        if method == "POST" and path == "/api/connect-token":
            token = pluggy.create_connect_token(client_user_id=pluggy_user_id(uid))
            return self._json(200, {"accessToken": token})

        if method == "GET" and path == "/api/summary":
            month = _p(params, "month") or current_month()
            return self._json(200, get_summary(month, uid))

        if method == "GET" and path == "/api/accounts":
            with database.db() as conn:
                rows = conn.execute(
                    """SELECT a.*, COALESCE(i.institution_name, '') AS institution,
                              i.image_url AS image_url
                       FROM accounts a LEFT JOIN items i ON i.id = a.item_id
                       WHERE a.user_id = ? ORDER BY a.type, a.name""",
                (uid,),
                ).fetchall()
            return self._json(200, {"results": [dict(r) for r in rows]})

        if method == "GET" and path == "/api/months":
            with database.db() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT substr(date, 1, 7) AS month FROM transactions "
                    "WHERE user_id = ? ORDER BY month DESC LIMIT 36",
                    (uid,),
                ).fetchall()
            return self._json(200, {"results": [r["month"] for r in rows]})

        if method == "GET" and path == "/api/categories":
            month = _p(params, "month")
            sql = (
                """SELECT COALESCE(NULLIF(category, ''), 'Sem categoria') AS category,
                          SUM(-amount) AS total
                   FROM transactions
                   WHERE user_id = ? AND amount < 0 """
            )
            args = [uid]
            if month:
                sql += "AND date LIKE ? "
                args.append(month + "%")
            sql += "GROUP BY 1 ORDER BY total DESC LIMIT 50"
            with database.db() as conn:
                rows = conn.execute(sql, args).fetchall()
            return self._json(200, {"results": [dict(r) for r in rows]})

        if method == "GET" and path == "/api/transactions":
            return self._json(200, list_transactions(params, uid))

        if method == "GET" and path == "/api/investments":
            with database.db() as conn:
                rows = conn.execute(
                    """SELECT inv.*, COALESCE(i.institution_name, '') AS institution
                       FROM investments inv LEFT JOIN items i ON i.id = inv.item_id
                       WHERE inv.user_id = ? AND (inv.status IS NULL OR inv.status = 'ACTIVE')
                       ORDER BY inv.balance DESC""",
                (uid,),
                ).fetchall()
            return self._json(200, {"results": [dict(r) for r in rows]})

        if method == "GET" and path == "/api/items":
            with database.db() as conn:
                rows = conn.execute(
                    "SELECT * FROM items WHERE user_id = ? ORDER BY created_at", (uid,)
                ).fetchall()
            return self._json(200, {"results": [dict(r) for r in rows]})

        match = re.fullmatch(r"/api/items/([^/]+)/sync", path)
        if method == "POST" and match:
            item_id = unquote(match.group(1))
            if not _valid_item_id(item_id):
                return self._json(400, {"error": "ID de conexão inválido."})
            body = self._body()
            trigger = body.get("trigger", True) is not False
            return self._json(200, sync_item(item_id, trigger, uid))

        match = re.fullmatch(r"/api/items/([^/]+)", path)
        if method == "DELETE" and match:
            item_id = unquote(match.group(1))
            if not _valid_item_id(item_id):
                return self._json(400, {"error": "ID de conexão inválido."})
            with database.db() as conn:
                if not conn.execute(
                    "SELECT 1 FROM items WHERE id = ? AND user_id = ?", (item_id, uid)
                ).fetchone():
                    return self._json(404, {"error": "Conexão não encontrada."})
            try:
                api_key = pluggy.get_api_key()
                pluggy.delete_remote_item(item_id, api_key)
            except Exception as exc:
                print(f"[aviso] falha ao remover item remoto ({item_id}): {exc}")
            with database.db() as conn:
                if not conn.execute(
                    "SELECT 1 FROM items WHERE id = ? AND user_id = ?", (item_id, uid)
                ).fetchone():
                    return self._json(404, {"error": "Conexão não encontrada."})
                conn.execute(
                    "DELETE FROM transactions WHERE user_id = ? AND item_id = ?", (uid, item_id)
                )
                conn.execute(
                    "DELETE FROM investments WHERE user_id = ? AND item_id = ?", (uid, item_id)
                )
                conn.execute(
                    "DELETE FROM accounts WHERE user_id = ? AND item_id = ?", (uid, item_id)
                )
                conn.execute("DELETE FROM items WHERE id = ? AND user_id = ?", (item_id, uid))
            return self._json(200, {"ok": True})

        if path in self.READ_ROUTES:
            return self._json(405, {"error": "Método não permitido."})
        return self._json(404, {"error": "Rota não encontrada."})

    # ---------------- arquivos estáticos ----------------

    def _static(self, path):
        rel = "index.html" if path == "/" else unquote(path.lstrip("/"))
        target = (PUBLIC_DIR / rel).resolve()
        if not target.is_relative_to(PUBLIC_DIR.resolve()) or not target.is_file():
            return self._text(404, "Não encontrado")

        content_type, _ = mimetypes.guess_type(target.name)
        if content_type and content_type.startswith("text/"):
            content_type += "; charset=utf-8"
        if target.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"

        size = target.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-cache")
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(target.read_bytes())


def main():
    # Console Windows (cp1252) não aceita emoji/caracteres fora da tabela;
    # troca por "?" em vez de quebrar o servidor.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")

    database.init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"Minhas Finanças rodando em http://{HOST}:{PORT}")
    if not pluggy.has_credentials():
        print("Sem credenciais do Pluggy: crie um .env com PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando…")


if __name__ == "__main__":
    main()
