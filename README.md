# DirecioZAP

Bot de WhatsApp para coleta de cadastros de fornecedores. Conduz conversas automatizadas, coleta e valida respostas campo a campo, salva os dados no banco de dados (Neon) e exporta para Excel.

---

## Visao Geral

```
Usuario WhatsApp  →  Twilio/Meta  →  ngrok (tunel)  →  Bot FastAPI (local)
                                                            ↓
                                                       Neon/Postgres (sessoes, cadastros)
                                                         ↓
                                                       Excel gerado sob demanda (/exportar)
```

O administrador usa o **DirecioZAP Manager** (aplicativo desktop) para:
- Gerenciar as perguntas do formulario
- Monitorar conversas e cadastros
- Baixar o Excel com os dados coletados
- Configurar credenciais (Twilio ou Meta, ngrok, banco de dados (Neon))

---

## Guia Rapido — Para Quem Vai So Usar o Aplicativo (.exe)

Se voce recebeu a pasta `DirecioZAP_Manager` pronta (nao vai mexer no codigo), e so isso que precisa saber:

1. **Nao precisa instalar nada.** Python, ngrok e todas as dependencias ja vem dentro da pasta. Basta extrair o .zip em qualquer lugar (Area de Trabalho, Documentos etc.).
2. **Nao precisa ser administrador do Windows.** O aplicativo roda com uma conta comum.
3. Na primeira vez que abrir o `DirecioZAP_Manager.exe`, o Windows pode mostrar uma tela azul **"O Windows protegeu o seu PC"**. Isso e normal para programas novos sem assinatura digital paga — clique em **"Mais informacoes"** e depois em **"Executar assim mesmo"**.
4. Ao clicar em **"Iniciar Bot"** pela primeira vez, o Firewall do Windows pode perguntar se permite acesso a rede. Pode clicar em **"Cancelar"** sem problema — o aplicativo continua funcionando normalmente (a conexao publica passa pelo ngrok, que nao depende dessa permissao).
5. Va na aba **Configuracoes**, preencha as credenciais (Twilio ou Meta, banco de dados (Neon), ngrok) e clique em **"Salvar Configuracoes"**.
6. Volte para a barra lateral e clique em **"Iniciar Bot"**. A URL publica aparece embaixo do botao — cole essa URL no painel do Twilio/Meta.
7. Duvidas sobre onde conseguir cada credencial? A aba **Tutorial**, dentro do proprio aplicativo, tem o passo a passo completo.

---

## Requisitos

| Software | Versao | Obs |
|---|---|---|
| Python | 3.11+ | Apenas para rodar/buildar a partir do codigo-fonte |
| ngrok | qualquer | So precisa instalar manualmente se rodar `python manager_app.py` direto; o .exe ja vem com o ngrok embutido |
| Git | qualquer | Para clonar o repositorio |
| Conta Neon | gratuita | neon.tech |
| Conta Twilio | gratuita (sandbox) | twilio.com |

---

## Estrutura do Projeto

```
DirecioZAP/
├── manager_app.py          # Aplicativo desktop (CustomTkinter)
├── main.py                 # Backend FastAPI do bot
├── config.py               # Configuracoes via .env (pydantic-settings)
├── conversation.py         # Motor de conversa dinamico
├── whatsapp.py             # Envio de mensagens via Twilio
├── db.py                   # Acesso ao banco Postgres/Neon (sessoes, perguntas, cadastros)
├── excel_writer.py         # Gera o .xlsx a partir dos cadastros do banco de dados (Neon)
├── validators.py           # Validacao de CNPJ, telefone, e-mail, estados
├── requirements.txt        # Dependencias do bot
├── requirements_manager.txt # Dependencias do aplicativo desktop
├── build.ps1               # Script de build do executavel (.exe)
├── .env.example            # Modelo de configuracao
├── data/                   # Excel gerado automaticamente
└── tests/                  # Suite de testes automatizados
    ├── conftest.py
    ├── test_conversation.py
    ├── test_validators.py
    └── test_excel_writer.py
```

---

## Configuracao Inicial

### 1. Clonar o repositorio

```bash
git clone <url-do-repositorio>
cd DirecioZAP
```

### 2. Criar ambiente virtual e instalar dependencias

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
pip install -r requirements_manager.txt
```

### 3. Configurar o .env

Copie `.env.example` para `.env` e preencha os valores:

```env
# Provedor: Twilio ou Meta
WHATSAPP_PROVIDER=Twilio

# Twilio (sandbox para testes)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=+14155238886

# Meta WhatsApp Cloud API (para producao)
META_PHONE_NUMBER_ID=coloque_aqui
META_TOKEN=coloque_aqui
META_VERIFY_TOKEN=coloque_aqui

# ngrok
NGROK_AUTH_TOKEN=coloque_aqui
NGROK_DOMAIN=                    # opcional: dominio estatico ngrok

# Banco de dados (Neon)
DATABASE_URL=postgresql://usuario:senha@ep-xxxx.neon.tech/neondb?sslmode=require

# Seguranca
VERIFY_TOKEN=gere_um_token_seguro
```

---

## Configurando o banco de dados (Neon)

1. Acesse [neon.tech](https://neon.tech) e crie uma conta gratuita.
2. Crie um projeto (regiao AWS Sao Paulo, se disponivel).
3. No painel do projeto, clique em **Connect** e copie a connection string (`postgresql://...?sslmode=require`).
4. No Manager, aba **Configuracoes**, cole em **Banco de dados (Neon)** e clique em **Testar Conexao**.
   O teste cria as tabelas (`perguntas`, `cadastros`, `sessions`) e as perguntas padrao, se ainda nao existirem —
   nao e preciso rodar SQL manualmente. O esquema completo esta em `db.py` (`SCHEMA_SQL`).

> O plano gratuito do Neon suspende o banco apos alguns minutos sem uso; a primeira mensagem depois disso
> demora um pouco mais (o banco "acorda" sozinho). Nao e preciso fazer nada.

---

## Configurando o Twilio (Sandbox)

O sandbox permite testar sem custo e sem aprovacao da Meta. Restricao: cada usuario precisa fazer o "join" uma vez.

1. Acesse [twilio.com](https://twilio.com) e crie uma conta gratuita.
2. No console, va em **Messaging > Try it out > Send a WhatsApp message**.
3. Copie **Account SID** e **Auth Token** da pagina inicial.
4. O numero do sandbox e `+1 415 523 8886`.
5. Em **Sandbox Settings**, configure o campo **"When a message comes in"** com:
   ```
   https://SEU_DOMINIO.ngrok-free.app/webhook
   ```
6. Para cada usuario que quiser usar o bot, ele deve enviar no WhatsApp:
   ```
   join [palavra-do-sandbox]
   ```
   A palavra aparece no painel Twilio (ex: `join yellow-tiger`).
7. Apos 72h de inatividade, o usuario precisa fazer o join novamente.

---

## Configurando o ngrok

O ngrok cria um tunel HTTPS publico para o bot rodando localmente, permitindo que o Twilio/Meta entregue os webhooks.

> **No executavel (.exe) o ngrok ja vem embutido** — o `build.ps1` copia o `ngrok.exe` para dentro da pasta `dist\DirecioZAP_Manager\` automaticamente. Quem so vai usar o app pronto pode pular os passos 1 e 2 abaixo.

1. (Somente para rodar a partir do codigo-fonte) Acesse [ngrok.com/download](https://ngrok.com/download) e baixe o executavel.
2. (Somente para rodar a partir do codigo-fonte) Coloque o `ngrok.exe` em uma pasta incluida no PATH ou junto de `manager_app.py`.
3. Crie uma conta gratuita em [ngrok.com](https://ngrok.com) — recomendado mesmo com o ngrok embutido, pois libera Auth Token e dominio estatico.
4. No painel, copie o **Auth Token** e cole em `.env` como `NGROK_AUTH_TOKEN`.
5. Opcionalmente, crie um **Dominio Estatico** (Domains no painel ngrok) e cole em `NGROK_DOMAIN`.
   Com dominio estatico, a URL nao muda a cada reinicio — ideal para nao precisar atualizar o Twilio toda vez.
6. O Manager inicia o ngrok automaticamente ao clicar em "Iniciar Bot".

Para iniciar manualmente:
```bash
ngrok http 3000
# ou com dominio estatico:
ngrok http 3000 --domain=abc.ngrok-free.app
```

---

## Usando o Aplicativo Desktop (Manager)

### Iniciando

```bash
python manager_app.py
```

### Abas

#### Perguntas
Gerencia o formulario de cadastro. As perguntas sao armazenadas no banco de dados (Neon) e lidas pelo bot em tempo real.

- **Adicionar**: cria uma nova pergunta
- **Editar**: modifica uma pergunta existente
- **Excluir**: remove permanentemente
- **Mover Acima / Mover Abaixo**: reordena as perguntas
- **Atualizar**: recarrega da base de dados

**Campos de cada pergunta:**

| Campo | Descricao |
|---|---|
| Ordem | Sequencia de apresentacao |
| Campo | Identificador interno (snake_case, sem espacos) |
| Label | Nome exibido no resumo final |
| Pergunta | Texto que o bot envia |
| Tipo | Regra de validacao |
| Mensagem de Erro | Texto enviado quando a resposta e invalida |
| Ativo | Se False, a pergunta e ignorada |

**Tipos de validacao:**

| Tipo | Aceita |
|---|---|
| texto | Qualquer texto nao vazio |
| cnpj | CNPJ com digitos verificadores validos |
| email | Formato de e-mail valido |
| telefone | Numero de telefone brasileiro |
| contato | Telefone ou e-mail |
| estados | Siglas de estados brasileiros (MG, SP, RJ...) |

#### Mensagens
Monitora as conversas em andamento e os cadastros concluidos.

- **Sessoes Ativas**: usuarios em conversa que ainda nao finalizaram
- **Cadastros Concluidos**: formularios confirmados e salvos
- **Baixar Excel**: exporta todos os cadastros para .xlsx (o bot precisa estar rodando)

#### Configuracoes
Configura credenciais de todos os servicos.

- Selecione o provedor (Twilio ou Meta)
- Preencha os campos correspondentes
- Configure ngrok e banco de dados (Neon)
- Defina o Verify Token (qualquer string segura; protege o endpoint `/exportar`)
- Clique em "Salvar Configuracoes"

#### Tutorial
Documentacao completa embutida no aplicativo.

### Iniciando o Bot pelo Manager

1. Configure as credenciais na aba Configuracoes e salve.
2. Clique em **"Iniciar Bot"** na barra lateral.
3. Aguarde — o bot e o ngrok sobem automaticamente.
4. A URL publica aparece abaixo do botao.
5. Cole essa URL no campo de webhook do Twilio ou Meta.

---

## Bot na Nuvem (Render) — modo recomendado

A rede da empresa bloqueia a API da Meta, entao o bot roda no Render e o PC so envia os avisos
por e-mail (tarefa "DirecioZAP Avisos"). Passo a passo em [guides/04_deploy_render.md](guides/04_deploy_render.md).

## Rodando em Segundo Plano no PC (bot local)

Para o bot responder sem precisar deixar o Manager aberto, registre a tarefa agendada:

```powershell
powershell -ExecutionPolicy Bypass -File register_task.ps1          # registra e inicia
powershell -ExecutionPolicy Bypass -File register_task.ps1 -Remove  # remove
```

A tarefa "DirecioZAP Bot" roda `run_bot.py` com `pythonw` (sem janela) a cada logon do Windows:
sobe o bot na porta 3000, abre o túnel ngrok (ou reaproveita um já aberto) e o reabre se cair; se o
bot parar, a tarefa o reinicia em 1 minuto. Se o Manager já estiver rodando o bot, ela espera a porta
liberar, e o Manager mostra "Em segundo plano" enquanto a tarefa estiver ativa.

Só funciona com o PC ligado e o usuário logado (o aviso por e-mail usa o Outlook da sessão). Evite
que o PC entre em suspensão: em Configurações > Energia, deixe "Suspender" como "Nunca" quando
conectado à energia. Logs em `logs/direciozap.log`; problemas do túnel em `logs/ngrok.log`.

## Rodando o Bot Manualmente (para desenvolvimento)

```bash
# Terminal 1 — Bot
.venv\Scripts\activate
uvicorn main:app --host 127.0.0.1 --port 3000 --reload

# Terminal 2 — ngrok
ngrok http 3000
```

---

## Como o Bot Funciona

1. O usuario envia qualquer mensagem para o numero do bot.
2. O bot responde com a saudacao e a primeira pergunta configurada.
3. O usuario responde cada pergunta em sequencia.
4. Se a resposta for invalida, o bot rejeita e repete a pergunta (ate 3 tentativas).
5. Apos a ultima pergunta, o bot exibe um resumo e pede confirmacao (S/N).
6. Ao confirmar:
   - Dados salvos no banco de dados (Neon) (tabela `cadastros`)
   - Sessao encerrada
7. Sessions expiram apos 24 horas sem interacao.

---

## API Endpoints

| Metodo | Rota | Descricao |
|---|---|---|
| GET | `/` | Health check |
| POST | `/webhook` | Recebe mensagens do Twilio |
| GET | `/exportar?token=SEU_TOKEN` | Baixa o Excel de cadastros |

---

## Gerando o Executavel (.exe)

O script `build.ps1` empacota o Manager, o bot e o **ngrok** em um diretorio distribuivel — o usuario final nao instala nada.

```powershell
# Construir (mantendo dist\ anterior)
.\build.ps1

# Construir do zero (apaga dist\ e build\)
.\build.ps1 -Clean
```

O resultado estara em `dist\DirecioZAP_Manager\`.

**O que o build faz automaticamente:**
1. Roda o PyInstaller e gera `DirecioZAP_Manager.exe`.
2. Copia `.env.example` para `.env` (se ainda nao existir na pasta de destino).
3. Cria a pasta `data\`.
4. Procura um `ngrok.exe` na maquina de build (via PATH); se nao encontrar, instala via `winget install --id Ngrok.Ngrok` automaticamente. Em seguida copia o `ngrok.exe` para dentro de `dist\DirecioZAP_Manager\`, junto do executavel.
   - Se a maquina de build nao tiver `winget` nem `ngrok` disponiveis, o build continua normalmente mas avisa no console que o ngrok nao foi embutido — nesse caso o usuario final precisaria instala-lo manualmente (ver secao "Configurando o ngrok").

**Para distribuir:**
1. Compacte a pasta `dist\DirecioZAP_Manager\` inteira (incluindo o `ngrok.exe`) em um .zip.
2. Entregue ao usuario final.
3. O usuario descompacta e edita o arquivo `.env` (ou preenche pela aba Configuracoes) com suas credenciais.
4. Duplo clique em `DirecioZAP_Manager.exe`.

**Requisitos na maquina do usuario final:**
- Windows 10/11 (64-bit)
- **Nao precisa de conta de administrador** — o app roda e grava tudo dentro da propria pasta
- **Nao precisa instalar ngrok** — ja vem embutido no pacote
- Na primeira execucao, o SmartScreen do Windows pode pedir uma confirmacao ("Executar assim mesmo") por o executavel nao ser assinado digitalmente — isso nao exige senha de administrador
- O aviso de Firewall ao iniciar o bot pode ser ignorado (Cancelar) sem afetar o funcionamento, ja que o ngrok se conecta por `localhost`
- Credenciais Twilio/Meta e banco de dados (Neon) proprias

---

## Testes

```bash
pytest -v
```

Cobertura:
- `test_conversation.py` — fluxo feliz e erros (18 cenarios)
- `test_excel_writer.py` — geracao da planilha, colunas quando o formulario muda, datas
- `test_validators.py` — CNPJ, telefone, e-mail, estados

---

## Configurando o Meta WhatsApp Cloud API (Producao)

> Atencao: O sandbox Meta **nao envia mensagens para numeros brasileiros (+55)**. Para producao com Brasil, e necessario verificar o negocio na Meta.

1. Acesse [developers.facebook.com](https://developers.facebook.com) e crie uma conta.
2. Crie um novo app do tipo **Business**.
3. Adicione o produto **WhatsApp** ao app.
4. Em **API Setup**, copie o **Phone Number ID** e gere o **Access Token**.
5. Em **Configuration > Webhook**, adicione:
   - URL: `https://SEU_DOMINIO.ngrok-free.app/webhook`
   - Verify Token: o mesmo valor de `VERIFY_TOKEN` no .env
6. Assine o campo **messages** no webhook.
7. No .env, defina `WHATSAPP_PROVIDER=Meta` e preencha `META_PHONE_NUMBER_ID`, `META_TOKEN`, `META_VERIFY_TOKEN`.

---

## Variaveis de Ambiente — Referencia Completa

| Variavel | Obrigatoria | Descricao |
|---|---|---|
| `WHATSAPP_PROVIDER` | Sim | `Twilio` ou `Meta` |
| `TWILIO_ACCOUNT_SID` | Se Twilio | Account SID do console Twilio |
| `TWILIO_AUTH_TOKEN` | Se Twilio | Auth Token do console Twilio |
| `TWILIO_WHATSAPP_FROM` | Se Twilio | Numero do sandbox (ex: +14155238886) |
| `META_PHONE_NUMBER_ID` | Se Meta | ID do numero no Meta |
| `META_TOKEN` | Se Meta | Access Token da API Meta |
| `META_VERIFY_TOKEN` | Se Meta | Token de verificacao do webhook |
| `META_APP_SECRET` | Se Meta | App Secret (valida a assinatura dos webhooks) |
| `META_WABA_ID` | Nao | ID da conta do WhatsApp Business (usado pelo Diagnostico) |
| `NGROK_AUTH_TOKEN` | Recomendado | Token de autenticacao do ngrok |
| `NGROK_DOMAIN` | Nao | Dominio estatico ngrok |
| `DATABASE_URL` | Sim | Connection string do Postgres (Neon) |
| `VERIFY_TOKEN` | Sim | Token para proteger `/exportar` |
| `NOTIFY_EMAIL` | Nao | E-mail(s) avisados pelo Outlook a cada cadastro concluido |

---

## Branches

| Branch | Descricao |
|---|---|
| `main` | Producao (Twilio + fluxo dinamico) |
| `META` | Versao com Meta Cloud API |
| `twilio` | Branch de desenvolvimento atual |

---

## Licenca

Projeto privado. Todos os direitos reservados.

---

*Dias*
