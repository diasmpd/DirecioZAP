# Guia 04 — Bot na nuvem (Render)

> Tempo estimado: 20 minutos
> Pré-requisitos: conta gratuita no [render.com](https://render.com) (entre com o GitHub) e o
> repositório `diasmpd/DirecioZAP` no GitHub

## Por que na nuvem

A rede corporativa (FortiGate) bloqueia `graph.facebook.com`: com o bot no PC da empresa, as
mensagens chegam, mas as respostas não saem. No Render o bot não depende da rede da empresa,
do PC ligado nem do ngrok.

O que continua no PC: os **avisos por e-mail** (o Outlook só existe no PC). A tarefa
"DirecioZAP Avisos" roda a cada 5 minutos, envia os avisos pendentes e mantém o bot do Render
acordado — o plano gratuito adormece após 15 min sem requisições, e a primeira resposta
levaria 30–60 s. Com o PC desligado, o bot continua respondendo (talvez com essa demora na
primeira mensagem) e os avisos saem quando o PC voltar.

## Passo 1 — Criar o serviço

1. Em [dashboard.render.com](https://dashboard.render.com), clique em **New → Blueprint**.
2. Conecte o GitHub e escolha o repositório **diasmpd/DirecioZAP**. O Render lê o `render.yaml`.
3. Ele pede os valores secretos. Copie cada um do `.env` deste PC:
   `META_PHONE_NUMBER_ID`, `META_TOKEN`, `META_APP_SECRET`, `META_VERIFY_TOKEN`,
   `DATABASE_URL`, `VERIFY_TOKEN`.
4. Clique em **Apply**. O primeiro deploy leva uns 3–5 minutos.
5. Copie a URL do serviço (ex: `https://direciozap-bot.onrender.com`). Abra no navegador:
   deve aparecer `{"status":"ok"}`.

## Passo 2 — Apontar o webhook da Meta para o Render

`developers.facebook.com` é bloqueado na rede da empresa: faça este passo pelo celular
(4G) ou com o PC no roteador do celular.

1. developers.facebook.com → app **DirecioZAP** → **WhatsApp → Configuração** → Webhook → **Editar**.
2. **URL de callback:** `https://<sua-url>.onrender.com/webhook`
3. **Token de verificação:** o mesmo `META_VERIFY_TOKEN` do `.env`.
4. **Verificar e salvar**. Confira que o campo **messages** continua assinado.

## Passo 3 — Ligar os avisos no PC

1. No Manager, aba **Configurações → Bot na nuvem (Render)**, cole a URL do Render e salve.
2. Rode, na pasta do projeto:

   ```powershell
   powershell -ExecutionPolicy Bypass -File register_task.ps1
   ```

   Isso remove a tarefa do bot local ("DirecioZAP Bot", com o ngrok) e registra
   "DirecioZAP Avisos".
3. Mande "oi" para o número do bot e conclua um cadastro de teste: a resposta vem do Render
   e o e-mail chega em até 5 minutos.

## Atualizações

Cada `git push` na branch `main` do fork faz o Render publicar a nova versão sozinho.

## Problemas

- **Bot não responde:** painel do Render → serviço → **Logs**. O Diagnóstico do Manager confere
  a URL do Render, o banco e os avisos (as checagens da Meta só funcionam fora da rede da empresa).
- **E-mails não chegam:** `logs\direciozap.log` neste PC e o status da tarefa no Agendador de
  Tarefas do Windows.
