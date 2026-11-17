# 💰 Minhas Finanças

Painel financeiro para acompanhar saldos, gastos, cartões e investimentos em um só lugar, com integração bancária pelo **Pluggy**.

A aplicação roda localmente e armazena os dados em **SQLite**. A sincronização é iniciada pelo usuário e depende das informações disponibilizadas por cada instituição.

> 🚧 Projeto pessoal em desenvolvimento.

## ✨ Funcionalidades

- Resumo de saldos, faturas e investimentos.
- Consulta de transações com filtros e busca.
- Conexão, sincronização e remoção de bancos.
- Personalização de tema, fontes e cores.

## 🛠️ Tecnologias

**Python • JavaScript • HTML • CSS • SQL (SQLite) • API Pluggy**

## 🚀 Como executar

Requer **Python 3.10+**, sem dependências Python externas.

```bash
git clone https://github.com/27Clemente/Projeto-Financas.git
cd Projeto-Financas
```

Para conectar bancos, obtenha suas credenciais no [Pluggy](https://dashboard.pluggy.ai) e crie um arquivo `.env` na raiz:

```env
PLUGGY_CLIENT_ID=seu_client_id
PLUGGY_CLIENT_SECRET=seu_client_secret
```

Inicie o servidor:

```bash
python server/app.py
```

Acesse **http://127.0.0.1:3000** e clique em **Conectar banco**.

O ambiente de desenvolvimento utiliza instituições de teste. Para conectar bancos reais, é necessário habilitar o ambiente de produção no Pluggy.

## 🏦 Como conectar um banco de teste

Não precisa ter conta bancária nem dinheiro real. O Pluggy oferece instituições sandbox só para testar a integração.

1. Abra o app em **http://127.0.0.1:3000** e vá na aba **Conexões**.
2. Se a sua aplicação no Pluggy for de **produção**, ligue o interruptor **Mostrar bancos de teste**. Se for de desenvolvimento, os conectores sandbox já aparecem e você pode pular este passo.
3. Clique em **Conectar banco**.
4. Escolha um conector de teste, como **Pluggy Bank** ou **Meu Pluggy**.
5. Na tela de login do banco, use:

   | Campo | Valor |
   | --- | --- |
   | Usuário | `user-ok` |
   | Senha | `password-ok` |
   | Token MFA (quando pedir) | `123456` |

6. Autorize a conexão. O app puxa os dados automaticamente e já abre o Painel com saldos, transações e investimentos de exemplo.
7. Em **Conexões** você pode usar **Sincronizar** para atualizar ou **Remover** para apagar o banco de teste.

> Se aparecer `Essa conta já está conectada`, é porque o Pluggy ainda tem a conexão antiga. Vá em **Conexões** e clique em **Sincronizar** nela, sem criar outra.

> 🧪 O interruptor fica salvo no navegador, então na próxima vez você não precisa ligar de novo.

## 🧪 Testes

```bash
python server/test_financas.py
```

Verificam cálculos, filtros, paginação e validações de segurança usando um banco temporário.

## 🔒 Privacidade

Os dados ficam em `data/financas.db`, e o servidor aceita acesso apenas pela própria máquina. A conexão bancária utiliza o widget do Pluggy.

O `.env` e a pasta `data/` estão no `.gitignore`. A aplicação ainda não possui autenticação e foi desenvolvida para uso pessoal e local.

## 👨‍💻 Autor

Desenvolvido por **Thomas Clemente**, estudante de Cibersegurança na FIAP.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/thomas-clemente/)
[![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/27Clemente)
