"""Cliente da API do Pluggy (https://docs.pluggy.ai) — agregador de Open Finance.

O Client ID/Secret fica só no servidor; o frontend recebe apenas Connect Tokens
de curta duração (30 min) com escopo reduzido. Apenas biblioteca padrão.
"""

import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

BASE = "https://api.pluggy.ai"


class PluggyError(Exception):
    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


def has_credentials():
    return bool(os.environ.get("PLUGGY_CLIENT_ID") and os.environ.get("PLUGGY_CLIENT_SECRET"))


# API Key do /auth vale 2 horas; guardamos por ~1h55 para reutilizar.
_api_key_cache = {"key": None, "expires_at": 0.0}


def _request(path, method="GET", api_key=None, body=None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-KEY"] = api_key
    data = json.dumps(body).encode("utf-8") if body is not None else None
    url = BASE + path
    parsed = urlsplit(url)
    # Só HTTPS para api.pluggy.ai.
    if parsed.scheme != "https" or parsed.hostname != "api.pluggy.ai":
        raise PluggyError("Destino de URL inválido.", "BAD_URL")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310 -- URL validada acima
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        payload = {}
        try:
            payload = json.loads(text) if text else {}
        except ValueError:
            pass
        raise PluggyError(
            payload.get("message") or f"Erro {exc.code} na API do Pluggy",
            payload.get("codeDescription") or f"HTTP_{exc.code}",
            exc.code,
        ) from None
    except urllib.error.URLError as exc:
        raise PluggyError(f"Sem conexão com a API do Pluggy: {exc.reason}", "NETWORK") from None

    if not text:
        return None
    return json.loads(text)


def get_api_key():
    if not has_credentials():
        raise PluggyError(
            "Credenciais do Pluggy não configuradas. Preencha o arquivo .env.",
            "NOT_CONFIGURED",
        )
    now = time.time()
    if _api_key_cache["key"] and now < _api_key_cache["expires_at"]:
        return _api_key_cache["key"]
    data = _request(
        "/auth",
        method="POST",
        body={
            "clientId": os.environ["PLUGGY_CLIENT_ID"],
            "clientSecret": os.environ["PLUGGY_CLIENT_SECRET"],
        },
    )
    _api_key_cache["key"] = data["apiKey"]
    _api_key_cache["expires_at"] = now + 115 * 60  # 1h55
    return _api_key_cache["key"]


def _env_bool(name, default):
    """Lê um booleano simples do .env (1/true/yes/on ou 0/false/no/off)."""
    value = os.environ.get(name, "").strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return default


def create_connect_token(client_user_id=None, avoid_duplicates=None):
    """Cria o connect token usado pelo widget.

    Por padrão `avoidDuplicates` é **False**: cada conexão vira um item novo, o
    que permite conectar 2 ou mais bancos mesmo quando as instituições usam
    credenciais parecidas. Com True, o Pluggy recusa a criação com
    ITEM_USER_ALREADY_EXISTS (útil apenas para quem quer um único item por
    usuário). Use PLUGGY_AVOID_DUPLICATES=1 no .env para ligar.
    """
    api_key = get_api_key()
    if avoid_duplicates is None:
        avoid_duplicates = _env_bool("PLUGGY_AVOID_DUPLICATES", False)
    if client_user_id is None:
        client_user_id = os.environ.get("PLUGGY_CLIENT_USER_ID", "local-user")
    data = _request(
        "/connect_token",
        method="POST",
        api_key=api_key,
        body={
            "options": {
                "clientUserId": client_user_id,
                "avoidDuplicates": avoid_duplicates,
            }
        },
    )
    return data["accessToken"]


# Cache de 10 min para diferenciar Development (sandbox) de Production.
_connector_stats_cache = {"data": None, "expires_at": 0.0}


def connector_stats():
    """Totais de conectores Live e Sandbox disponíveis para esta aplicação."""
    now = time.time()
    if _connector_stats_cache["data"] and now < _connector_stats_cache["expires_at"]:
        return _connector_stats_cache["data"]

    api_key = get_api_key()
    live = (_request("/connectors?sandbox=false&pageSize=1", api_key=api_key) or {}).get("total") or 0
    sandbox = (_request("/connectors?sandbox=true&pageSize=1", api_key=api_key) or {}).get("total") or 0

    data = {"live": live, "sandbox": sandbox}
    _connector_stats_cache["data"] = data
    _connector_stats_cache["expires_at"] = now + 600
    return data


def _id(value):
    """Codifica um id para uso seguro em path/query da URL da API."""
    return quote(str(value), safe="")


def get_item(item_id, api_key):
    return _request(f"/items/{_id(item_id)}", api_key=api_key)


def trigger_sync(item_id, api_key):
    """Dispara uma nova sincronização com a instituição usando as credenciais salvas."""
    return _request(f"/items/{_id(item_id)}", method="PATCH", api_key=api_key, body={})


def delete_remote_item(item_id, api_key):
    return _request(f"/items/{_id(item_id)}", method="DELETE", api_key=api_key)


def list_accounts(item_id, api_key):
    data = _request(f"/accounts?itemId={_id(item_id)}", api_key=api_key)
    return (data or {}).get("results") or []


def iter_transactions(account_id, api_key):
    """GET /v2/transactions — paginação por cursor: seguir `next` até None."""
    qs = f"?accountId={account_id}"
    while qs:
        page = _request(f"/v2/transactions{qs}", api_key=api_key) or {}
        yield page.get("results") or []
        qs = page.get("next")


def list_investments(item_id, api_key):
    """GET /investments — paginação por número de página (pageSize máx. 500)."""
    results = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        data = _request(
            f"/investments?itemId={_id(item_id)}&page={page}&pageSize=500",
            api_key=api_key,
        ) or {}
        results.extend(data.get("results") or [])
        total_pages = data.get("totalPages") or 1
        page += 1
    return results
