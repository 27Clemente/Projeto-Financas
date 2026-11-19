"""Testes do projeto Finanças — só biblioteca padrão, sem servidor rodando.

Uso:  python server/test_financas.py

Cria um SQLite temporário (não toca em data/financas.db), cria dados de
exercício e confere os cálculos de resumo, filtros e paginação.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app  # noqa: E402  (precisa do sys.path acima)
import db  # noqa: E402
import pluggy  # noqa: E402

FALHAS = []


def check(nome, cond, detalhe=""):
    if cond:
        print(f"  ok   {nome}")
    else:
        print(f"  FALHA {nome}  {detalhe}")
        FALHAS.append(nome)


def seed(conn):
    conn.execute(
        "INSERT INTO items (id, connector_id, institution_name, image_url, status,"
            " execution_status, error_message, last_synced_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
        ("item-1", 200, "Banco Teste", None, "UPDATED", "SUCCESS", None, "2026-11-17T10:00:00Z", "2026-11-01T10:00:00Z"),
    )
    for row in [
        ("acc-bank", "BANK", 5000.0, None),
        ("acc-credit", "CREDIT", -1200.0, 3000.0),
    ]:
        conn.execute(
            "INSERT INTO accounts (id, item_id, type, subtype, name, number, balance,"
            " currency, owner, credit_limit, available_credit_limit, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (row[0], "item-1", row[1], None, "Conta", "0001", row[2], "BRL", "Fulano", row[3], None, "2026-11-17T10:00:00Z"),
        )
    txs = [
        ("tx1", "2026-11-15T12:00:00Z", "Mercado", -250.75, "Groceries"),
        ("tx2", "2026-11-14T12:00:00Z", "Salário", 7000.0, "Salary"),
        ("tx3", "2026-11-10T12:00:00Z", "iFood", -89.9, "Restaurant"),
        ("tx4", "2026-11-05T12:00:00Z", "Uber", -32.5, "Transport"),
        ("tx5", "2026-10-28T12:00:00Z", "Farmácia", -45.0, "Pharmacy"),
        ("tx6", "2026-11-01T12:00:00Z", "Sem categoria", -10.0, ""),
    ]
    for tid, date, desc, amount, category in txs:
        conn.execute(
            "INSERT INTO transactions (id, item_id, account_id, date, description, amount,"
                " category, type, status, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tid, "item-1", "acc-bank", date, desc, amount, category, "DEBIT", "POSTED", "2026-11-17T10:00:00Z"),
        )
    for iid, name, typ, balance, original, profit in [
        ("inv1", "CDB", "FIXED_INCOME", 10000.0, 9500.0, None),
        ("inv2", "Fundo", "MUTUAL_FUND", 5000.0, None, 800.0),
        ("inv3", "Ação", "EQUITY", 2000.0, None, None),
    ]:
        conn.execute(
            "INSERT INTO investments (id, item_id, name, code, type, subtype, balance,"
            " amount_original, amount_profit, annual_rate, fixed_annual_rate, rate,"
            " rate_type, issuer, status, ref_date, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iid, "item-1", name, None, typ, None, balance, original, profit, None, None, None, None, None, "ACTIVE", None, "2026-11-17T10:00:00Z"),
        )


def listar(params):
    return app.list_transactions(params, "local")


def test_auth_e_isolamento():
    print("autenticacao e isolamento por usuario")
    h = app.senha_hash("senha-teste")
    check("senha verificada", app.senha_valida("senha-teste", h) is True)
    check("senha errada rejeitada", app.senha_valida("outra", h) is False)
    check("clientUserId local", app.pluggy_user_id("local") == "local-user")
    check("clientUserId por pessoa", app.pluggy_user_id("abc") == "user-abc")

    token = app.sessao_token("u1")
    check("sessao valida", app.sessao_usuario(token) == "u1")
    check("sessao adulterada rejeitada", app.sessao_usuario(token[:-1] + "0") is None)

    with db.db() as conn:
        conn.execute(
            "INSERT INTO items (id, user_id, institution_name, status) VALUES (?,?,?,?)",
            ("alheio", "outro", "Banco Alheio", "UPDATED"),
        )
        conn.execute(
            "INSERT INTO accounts (id, user_id, item_id, type, balance, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            ("conta-alheia", "outro", "alheio", "BANK", 9999.0, "2026-11-17T10:00:00Z"),
        )
    s = app.get_summary("2026-11", "local")
    check("saldo alheio ignorado", s["bankBalance"] == 5000, s["bankBalance"])
    check("itens alheios ignorados", s["items"] == 1, s["items"])
    check("transacoes alheias ignoradas", listar({})["total"] == 6, listar({})["total"])
    with db.db() as conn:
        conn.execute("DELETE FROM items WHERE user_id = 'outro'")
        conn.execute("DELETE FROM accounts WHERE user_id = 'outro'")


def test_sync_item_novo():
    print("item novo so entra com o dono certo")
    origens = (
        pluggy.get_api_key, pluggy.get_item, pluggy.list_accounts,
        pluggy.iter_transactions, pluggy.list_investments,
    )
    pluggy.get_api_key = lambda: "chave-teste"
    pluggy.get_item = lambda iid, key: {
        "id": iid, "clientUserId": "user-abc" if iid == "novo-abc" else "user-xyz",
        "connector": {"id": 1, "name": "Banco Exemplo"},
        "executionStatus": "SUCCESS", "createdAt": "2026-11-01T10:00:00Z",
    }
    pluggy.list_accounts = lambda iid, key: []
    pluggy.iter_transactions = lambda aid, key: iter([])
    pluggy.list_investments = lambda iid, key: []
    try:
        r = app.sync_item("novo-abc", False, "abc")
        check("item novo aceito", r["ok"] is True, r)
        try:
            app.sync_item("novo-xyz", False, "abc")
            check("item de outro dono rejeitado", False)
        except pluggy.PluggyError as e:
            check("item de outro dono rejeitado", e.status == 404, e.status)
    finally:
        (
            pluggy.get_api_key, pluggy.get_item, pluggy.list_accounts,
            pluggy.iter_transactions, pluggy.list_investments,
        ) = origens
    with db.db() as conn:
        conn.execute("DELETE FROM items WHERE id IN ('novo-abc','novo-xyz')")


def test_summary():
    print("resumo do mês")
    s = app.get_summary("2026-11", "local")
    check("saldo bancário", s["bankBalance"] == 5000, s["bankBalance"])
    check("fatura de cartão separada", s["creditBalance"] == -1200, s["creditBalance"])
    check("investido", s["invested"] == 17000, s["invested"])
    check("rendimento", s["profit"] == 1300, s["profit"])
    check("base do rendimento (ignora posição sem base)", s["profitBase"] == 13700, s["profitBase"])
    check("gastos do mês", abs(s["expenses"] - 383.15) < 1e-9, s["expenses"])
    check("entradas do mês", s["income"] == 7000, s["income"])
    check("conta só de novembro", s["transactions"] == 5, s["transactions"])
    check("percentual", s["profitRate"] and abs(s["profitRate"] - 1300 / 13700 * 100) < 1e-9, s["profitRate"])

    out = app.get_summary("2026-10", "local")
    check("mês anterior isolado", abs(out["expenses"] - 45.0) < 1e-9, out["expenses"])
    vazio = app.get_summary("1999-01", "local")
    check("mês sem dados zera", vazio["expenses"] == 0 and vazio["transactions"] == 0, vazio)


def q(**kwargs):
    """Parâmetros no formato devolvido por urllib.parse.parse_qs (listas)."""
    return {k: [str(v)] for k, v in kwargs.items()}


def test_transactions():
    print("filtros e paginação de transações")
    r = listar(q(month="2026-11"))
    check("total do mês", r["total"] == 5, r["total"])
    check("ordem decrescente por data", r["results"][0]["date"] >= r["results"][-1]["date"], r["results"][0])

    r = listar(q(month="2026-11", limit=2))
    check("limit respeitado", len(r["results"]) == 2 and r["limit"] == 2, r["limit"])

    r = listar(q(month="2026-11", limit=50, offset=2))
    check("offset", len(r["results"]) == 3, len(r["results"]))

    r = listar(q(limit=99999))
    check("limit clamp em 500", r["limit"] == 500, r["limit"])
    r = listar(q(limit="abc", offset="xyz"))
    check("parâmetro inválido cai no padrão", r["limit"] == 50 and r["offset"] == 0, r)

    r = listar({"month": ["2026-11"], "type": ["in"]})
    check("tipo entrada", r["total"] == 1, r["total"])
    check("tipo saída", listar({"type": ["out"]})["total"] == 5)
    check("busca por descrição", listar({"q": ["Uber"]})["total"] == 1)
    check("busca por categoria", listar({"q": ["Groceries"]})["total"] == 1)
    check("filtro de categoria", listar({"category": ["Groceries"]})["total"] == 1)
    check("categoria vazia vira 'Sem categoria'", listar({"category": ["Sem categoria"]})["total"] == 1)
    check("filtro de conta", listar({"accountId": ["acc-credit"]})["total"] == 0)
    check("conta com instituição junta", listar({})["results"][0]["institution"] == "Banco Teste")


def test_include_sandbox():
    print("detecção de modo do widget")
    antes = os.environ.pop("PLUGGY_INCLUDE_SANDBOX", None)
    try:
        os.environ["PLUGGY_INCLUDE_SANDBOX"] = "0"
        check("override 0 desliga sandbox", app.include_sandbox() is False)
        os.environ["PLUGGY_INCLUDE_SANDBOX"] = "true"
        check("override true liga sandbox", app.include_sandbox() is True)
        os.environ["PLUGGY_MODE"] = "production"
        os.environ.pop("PLUGGY_INCLUDE_SANDBOX")
        check("modo production esconde sandbox", app.include_sandbox() is False)
        os.environ["PLUGGY_MODE"] = "development"
        check("modo development mostra sandbox", app.include_sandbox() is True)
        check("app_mode lê PLUGGY_MODE", app.app_mode() == "development", app.app_mode())
    finally:
        os.environ.pop("PLUGGY_INCLUDE_SANDBOX", None)
        os.environ.pop("PLUGGY_MODE", None)
        if antes is not None:
            os.environ["PLUGGY_INCLUDE_SANDBOX"] = antes


def test_app_mode_detection():
    print("detecção de produção com 1 conector real")
    original_stats = pluggy.connector_stats
    original_cache = dict(pluggy._connector_stats_cache)
    pluggy._connector_stats_cache.update({"data": None, "expires_at": 0.0})
    pluggy.connector_stats = lambda: {"live": 1, "sandbox": 15}
    antes = os.environ.pop("PLUGGY_MODE", None)
    try:
        check("1 conector real => production", app.app_mode() == "production", app.app_mode())
        check("sandbox escondido em production", app.include_sandbox() is False, app.include_sandbox())
    finally:
        pluggy.connector_stats = original_stats
        pluggy._connector_stats_cache.clear()
        pluggy._connector_stats_cache.update(original_cache)
        os.environ.pop("PLUGGY_MODE", None)
        if antes is not None:
            os.environ["PLUGGY_MODE"] = antes


def test_connect_token_options():
    print("opções do connect token (conectar 2+ bancos)")
    chamadas = []
    original_request = pluggy._request
    original_key = pluggy.get_api_key
    pluggy.get_api_key = lambda: "chave-teste"
    pluggy._request = lambda path, method=None, api_key=None, body=None: (
        chamadas.append((path, body)) or {"accessToken": "tk-teste"}
    )
    antes = os.environ.pop("PLUGGY_AVOID_DUPLICATES", None)
    try:
        retorno = pluggy.create_connect_token()
        check("token devolvido", retorno == "tk-teste", retorno)
        opts = chamadas[-1][1]["options"]
        check("avoidDuplicates desligado por padrão", opts["avoidDuplicates"] is False, opts)
        check("clientUserId padrão", opts["clientUserId"] == "local-user", opts)

        os.environ["PLUGGY_AVOID_DUPLICATES"] = "1"
        pluggy.create_connect_token()
        opts = chamadas[-1][1]["options"]
        check("avoidDuplicates ligável pelo .env", opts["avoidDuplicates"] is True, opts)

        pluggy.create_connect_token(client_user_id="user-2", avoid_duplicates=True)
        opts = chamadas[-1][1]["options"]
        check(
            "parâmetros explícitos vencem o padrão",
            opts["clientUserId"] == "user-2" and opts["avoidDuplicates"] is True,
            opts,
        )
    finally:
        pluggy._request = original_request
        pluggy.get_api_key = original_key
        os.environ.pop("PLUGGY_AVOID_DUPLICATES", None)
        if antes is not None:
            os.environ["PLUGGY_AVOID_DUPLICATES"] = antes


def test_multi_item_isolation():
    print("múltiplos bancos isolados na sincronização")
    with db.db() as conn:
        conn.execute(
            "INSERT INTO items (id, connector_id, institution_name, image_url, status,"
            " execution_status, error_message, last_synced_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            ("item-2", 999, "Banco Dois", None, "UPDATED", "SUCCESS", None,
             "2026-11-17T10:00:00Z", "2026-11-01T10:00:00Z"),
        )
        conn.execute(
            "INSERT INTO accounts (id, item_id, type, subtype, name, number, balance,"
            " currency, owner, credit_limit, available_credit_limit, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("acc-b2", "item-2", "BANK", None, "Conta Dois", "0002", 777.0,
             "BRL", "Fulano", None, None, "2026-11-17T10:00:00Z"),
        )
        conn.execute(
            "INSERT INTO transactions (id, item_id, account_id, date, description, amount,"
                " category, type, status, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("tx-b2", "item-2", "acc-b2", "2026-11-16T12:00:00Z", "Gasto Dois",
             -99.0, "Other", "DEBIT", "POSTED", "2026-11-17T10:00:00Z"),
        )

    # Simula o Pluggy devolvendo dados apenas para o item-1.
    contas = [{"id": "acc-b1", "type": "BANK", "balance": 123.0, "name": "Conta Um"}]
    transacoes = [[{
        "id": "tx-b1", "accountId": "acc-b1", "date": "2026-11-15T12:00:00Z",
        "description": "Gasto Um", "amount": -50.0, "type": "DEBIT", "status": "POSTED",
    }]]
    orig = (pluggy.list_accounts, pluggy.iter_transactions, pluggy.list_investments)
    pluggy.list_accounts = lambda item_id, key: contas if item_id == "item-1" else []
    pluggy.iter_transactions = lambda acc_id, key: iter(transacoes)
    pluggy.list_investments = lambda item_id, key: []
    try:
        app.pull_item_data("item-1", "fake-key", "local")
    finally:
        pluggy.list_accounts, pluggy.iter_transactions, pluggy.list_investments = orig

    with db.db() as conn:
        b2 = conn.execute("SELECT item_id FROM accounts WHERE id = 'acc-b2'").fetchone()
        tx2 = conn.execute("SELECT item_id FROM transactions WHERE id = 'tx-b2'").fetchone()
        b1 = conn.execute("SELECT item_id FROM accounts WHERE id = 'acc-b1'").fetchone()
    check("conta do 2º banco preservada", b2 is not None and b2["item_id"] == "item-2", b2)
    check("transação do 2º banco preservada", tx2 is not None and tx2["item_id"] == "item-2", tx2)
    check("conta do 1º banco importada", b1 is not None and b1["item_id"] == "item-1", b1)


def test_security_helpers():
    print("validações de segurança")
    check("id válido aceito", app._valid_item_id("abc-123_XYZ") is True)
    for ruim in ["../etc", "a/b", "a?b", "a#b", "a b", "%2f", "", "x" * 65, None, 123]:
        check(f"id inválido rejeitado ({ruim!r})", app._valid_item_id(ruim) is False)

    class FakeHandler:
        def __init__(self, headers):
            self.headers = headers

    host = f"127.0.0.1:{app.PORT}"
    check("sem Origin permitido", app._origin_allowed(FakeHandler({})) is True)
    check(
        "Origin local permitido",
        app._origin_allowed(FakeHandler({"Origin": f"http://{host}", "Host": host})) is True,
    )
    check(
        "Origin externo bloqueado",
        app._origin_allowed(FakeHandler({"Origin": "https://evil.example", "Host": host})) is False,
    )

    check("id codificado na URL", pluggy._id("a/b c?") == "a%2Fb%20c%3F", pluggy._id("a/b c?"))

    class FakeResp:
        def __init__(self):
            self.headers = {}

        def send_header(self, key, value):
            self.headers[key] = value

    h = FakeResp()
    app.Handler._security_headers(h)
    check("CSP presente", "Content-Security-Policy" in h.headers, h.headers)
    check("nosniff presente", h.headers.get("X-Content-Type-Options") == "nosniff")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="financas-test-")) / "test.db"
    db.DB_PATH = tmp  # redige as conexões do módulo para o banco temporário
    db.init_db()
    with db.db() as conn:
        seed(conn)
    try:
        test_auth_e_isolamento()
        test_sync_item_novo()
        test_summary()
        test_transactions()
        test_include_sandbox()
        test_app_mode_detection()
        test_connect_token_options()
        test_multi_item_isolation()
        test_security_helpers()
    finally:
        db.DB_PATH = db.DATA_DIR / "financas.db"
        tmp.unlink(missing_ok=True)
        tmp.parent.rmdir()

    print()
    if FALHAS:
        print(f"{len(FALHAS)} teste(s) falharam: {', '.join(FALHAS)}")
        return 1
    print("todos os testes passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
