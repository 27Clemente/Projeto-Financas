# Minhas Finanças

Um painel local pra acompanhar saldo, gastos, cartões e investimentos num lugar só. Fiz esse projeto pra organizar minhas contas e praticar Python, banco de dados e integração com APIs.

A conexão com os bancos é feita pelo Pluggy, e os dados ficam salvos em SQLite no computador. Pra atualizar as informações, é só usar a opção de sincronizar.

## Demo ao vivo

[**Acesse a demonstracao no Render**](https://minhas-financas-5dcs.onrender.com)

A versao publicada roda em modo de demonstracao: apenas bancos de teste (sandbox) do Pluggy podem ser conectados, com dados ficticios. Crie uma conta com qualquer e-mail e senha (minimo de 8 caracteres) para explorar.

Para usar com seus proprios dados, rode o projeto localmente (instrucoes abaixo).

## O que dá pra fazer

- Ver o saldo das contas, faturas e investimentos.
- Consultar transações e filtrar por mês, tipo e categoria.
- Conectar, sincronizar e remover bancos.
- Mudar o tema, a fonte e as cores do painel.

Usei Python no servidor, HTML, CSS e JavaScript na interface e SQLite pra guardar os dados.

## Como rodar

Precisa de Python 3.10 ou superior. Não tem dependência Python externa pra instalar.

```bash
git clone https://github.com/27Clemente/Projeto-Financas.git
cd Projeto-Financas
```

Crie uma conta no [Pluggy](https://dashboard.pluggy.ai), pegue o Client ID e o Client Secret da sua aplicação e coloque num arquivo `.env` na raiz do projeto:

Copie o modelo `.env.example` para `.env` e preencha seus dados (o `.env` esta no `.gitignore` e nunca vai para o GitHub):

```bash
copy .env.example .env
```

```env
PLUGGY_CLIENT_ID=seu_client_id
PLUGGY_CLIENT_SECRET=seu_client_secret
APP_SECRET=uma_chave_longa_e_aleatoria
```

A variavel `APP_SECRET` ativa o login e assina os cookies de sessao.

Depois, inicie o servidor:

```bash
python server/app.py
```

No Windows, voce tambem pode dar duplo clique em `iniciar.bat`.

Abra `http://127.0.0.1:3000` no navegador.

## Conectando um banco de teste

Dá pra testar com dados fictícios, sem conectar sua conta bancária.

1. Abra a aba **Conexões**.
2. Se sua aplicação no Pluggy estiver em produção, ative **Mostrar bancos de teste**. No ambiente de desenvolvimento, eles já aparecem.
3. Clique em **Conectar banco** e escolha uma instituição de teste, como **Pluggy Bank** ou **Meu Pluggy**.
4. Use os dados abaixo:

| Campo | Valor |
| --- | --- |
| Usuário | `user-ok` |
| Senha | `password-ok` |
| Código de autenticação, se pedir | `123456` |

Depois de autorizar, o app carrega os dados de exemplo. Na aba **Conexões**, você pode sincronizar ou remover esse banco.

Se aparecer que a conta já está conectada, sincronize a conexão existente.

Pra conectar bancos reais, é necessário habilitar o ambiente de produção no Pluggy.

## Testes

```bash
python server/test_financas.py
```

Os testes conferem os cálculos, filtros, paginação e validações de segurança. Usam um banco temporário, sem mexer nos dados salvos pelo app.

## Sobre os dados

Os dados financeiros ficam em `data/financas.db`. O app roda apenas na própria máquina, mas precisa se comunicar com o Pluggy pra conectar os bancos e buscar as informações.

O `.env` e a pasta `data/` estão no `.gitignore`. A aplicação ainda não tem login e foi pensada pra uso pessoal e local.

---

Feito por Thomas Clemente.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/thomas-clemente/)
[![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/27Clemente)
