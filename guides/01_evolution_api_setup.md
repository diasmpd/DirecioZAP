# Guia 01 — Setup da Evolution API

> Tempo estimado: 20–30 minutos  
> Pré-requisitos: Docker instalado

---

## O que é a Evolution API?

A Evolution API é uma solução open-source que emula o protocolo WhatsApp Web e expõe uma REST API. Isso significa que você não precisa de aprovação da Meta para usar o WhatsApp — basta ter um número de celular comum.

**Repositório oficial:** https://github.com/EvolutionAPI/evolution-api

---

## Passo 1 — Subir a Evolution API com Docker Compose

O projeto já inclui um `docker-compose.yml` configurado. Para subir:

```bash
# No diretório raiz do projeto
docker-compose up -d evolution-api
```

Isso vai:
- Baixar a imagem `atendai/evolution-api:latest`
- Subir o servidor na porta `8080`
- Criar volumes Docker para persistir instâncias e armazenamento

Verifique se está rodando:
```bash
docker ps
# Deve mostrar: evolution-api ... 0.0.0.0:8080->8080/tcp
```

---

## Passo 2 — Acessar o Painel da Evolution API

Abra no navegador:
```
http://localhost:8080/manager
```

Na tela de login, use a mesma `EVOLUTION_API_KEY` que você definiu no `.env`.

---

## Passo 3 — Criar uma Instância

Uma "instância" representa uma conexão com um número de WhatsApp.

### Via Painel Web:
1. Clique em **"New Instance"**
2. Preencha:
   - **Instance Name:** `direciozap` (deve ser igual ao `EVOLUTION_INSTANCE` no `.env`)
   - **Integration:** WhatsApp
3. Clique em **"Create"**

### Via API (alternativa):
```bash
curl -X POST http://localhost:8080/instance/create \
  -H "apikey: SUA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "instanceName": "direciozap",
    "integration": "WHATSAPP-BAILEYS"
  }'
```

---

## Passo 4 — Conectar o Número de WhatsApp

Após criar a instância, você precisa conectá-la a um número real.

### Opção A: QR Code
1. No painel, clique na instância `direciozap`
2. Clique em **"Connect"** → escolha **"QR Code"**
3. Escaneie o QR Code com o WhatsApp do número que você quer usar como bot
4. Aguarde a mensagem "Connected"

### Opção B: Pairing Code (sem precisar escanear)
```bash
curl -X POST http://localhost:8080/instance/connect/direciozap \
  -H "apikey: SUA_API_KEY"
```
A API retorna um código de 8 dígitos. No WhatsApp → Configurações → Aparelhos Conectados → Conectar com número de telefone → insira o código.

> **Dica:** Use um número secundário ou chip de teste. O número conectado ficará como "WhatsApp Web ativo" no aparelho.

---

## Passo 5 — Configurar o Webhook

O webhook é a URL que a Evolution API vai chamar quando uma mensagem chegar.

### Via API:
```bash
curl -X POST http://localhost:8080/webhook/set/direciozap \
  -H "apikey: SUA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://SEU-APP.onrender.com/webhook",
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

### Para desenvolvimento local (com ngrok):
```bash
# Terminal 1: rodar o bot
uvicorn main:app --reload --port 3000

# Terminal 2: expor via ngrok
ngrok http 3000
# Copia a URL gerada (ex: https://abc123.ngrok.io)

# Configura o webhook com a URL do ngrok
curl -X POST http://localhost:8080/webhook/set/direciozap \
  -H "apikey: SUA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://abc123.ngrok.io/webhook",
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

---

## Passo 6 — Testar o envio de mensagem

```bash
curl -X POST http://localhost:8080/message/sendText/direciozap \
  -H "apikey: SUA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "number": "5531999990000",
    "text": "Teste do DirecioZap Bot!"
  }'
```

Substitua `5531999990000` pelo seu número (com DDI + DDD + número, sem +).

---

## Passo 7 — Verificar o recebimento de webhook

Envie uma mensagem **para** o número do bot pelo WhatsApp. O log do backend deve mostrar:

```
INFO:     127.0.0.1 - "POST /webhook HTTP/1.1" 200 OK
```

Se não aparecer, verifique:
1. Se o ngrok/URL está correto no webhook
2. Se a instância está com status "connected"
3. Se o evento `MESSAGES_UPSERT` está habilitado

---

## Estrutura do Payload recebido

```json
{
  "event": "messages.upsert",
  "instance": "direciozap",
  "data": {
    "key": {
      "remoteJid": "5531999990000@s.whatsapp.net",
      "fromMe": false,
      "id": "MSGID123"
    },
    "pushName": "Nome do Contato",
    "message": {
      "conversation": "texto que o usuário digitou"
    },
    "messageType": "conversation",
    "messageTimestamp": 1687536000
  }
}
```

---

## Próximo passo

Após confirmar que a Evolution API está funcional, siga o  
[Guia 02 — Setup do Supabase](./02_supabase_setup.md)
