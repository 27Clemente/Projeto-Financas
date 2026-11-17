# Minhas Finanças

Um painel local pra ver saldo, gastos e investimentos num lugar só. Os dados chegam
pelos seus bancos via Pluggy (Open Finance) e ficam num SQLite em `data/financas.db`.
Não tem nuvem, não tem login, não tem telemetria. Sua senha bancária é digitada no
widget do Pluggy e nunca passa por aqui.

## Rodando

Só precisa de Python 3.10+. Não tem dependência pra instalar.

```bash
python server/app.py
```

Depois abre `http://127.0.0.1:3000`. O servidor escuta só em `127.0.0.1`, então
ninguém na rede consegue acessar.

## Ligando os bancos

Cria uma conta no [dashboard do Pluggy](https://dashboard.pluggy.ai), vai em
Applications → **Go to production** e copia o Client ID e o Client Secret. Joga num
arquivo `.env` na raiz do projeto:

```
PLUGGY_CLIENT_ID=o_seu_id
PLUGGY_CLIENT_SECRET=o_seu_secret
```

Reinicia o servidor, clica em **Conectar banco**, escolhe a instituição e autoriza.
O app puxa uns 365 dias de transações, saldos e investimentos. Depois é só usar
**Sincronizar tudo** quando quiser atualizar.

Se você criar a aplicação em Development, o widget só mostra os bancos de teste.
O login deles é `user-ok` / `password-ok` / `123456`. O app tenta detectar o modo
sozinho, mas se ele se confundir (acontece quando você habilitou poucos bancos),
coloca `PLUGGY_MODE=production` e `PLUGGY_INCLUDE_SANDBOX=0` no `.env`.

## O que da pra fazer

O Painel traz o consolidado: saldo em conta, fatura de cartão separada, total
investido e o rendimento. Em Gastos dá pra filtrar por mês, tipo, categoria e
buscar pela descrição. Investimentos mostra as posições ativas com lucro e percentual
sobre o aplicado. Em Conexões você sincroniza ou remove cada banco. E em Aparência
você escolhe tema, fonte, cor de destaque e se quer animação — isso fica salvo no
próprio navegador.

## Tests

```bash
python server/test_financas.py
```

Bate os cálculos do resumo, os filtros, a paginação e as validações de segurança.
Usa um SQLite temporário, então não mexe nos seus dados.

## Algumas coisas que vale saber

Dá pra conectar quantos bancos quiser. O connect token vai com `avoidDuplicates`
desligado justamente por causa disso — se você quiser o comportamento antigo, de
recusar duplicata, põe `PLUGGY_AVOID_DUPLICATES=1` no `.env`.

Nem toda instituição informa o lucro de uma posição via Open Finance. Quando falta,
o app calcula `valor atual − aplicado`. Onde o campo oficial vem, ele usa o oficial.

Cartão de crédito aparece separado: o saldo da conta tipo CREDIT é a fatura em
aberto, não dinheiro disponível. As categorias vêm em inglês do Pluggy; as mais
comuns eu traduzi.

O `.env` e a pasta `data/` estão no `.gitignore`. Se quiser apagar tudo, fecha o
app e deleta `data/`.

## Onde está o quê

- `server/app.py` — servidor, rotas e sincronização
- `server/pluggy.py` — cliente da API do Pluggy
- `server/db.py` — esquema do SQLite
- `public/` — interface, estilo e o script da aba de aparência

Ainda quero colocar autenticação e banco por usuário se um dia isso virar algo
pra mais de uma pessoa. Por enquanto é um app de casa, como os meus dados pedem.
