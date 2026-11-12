# Contrato JSON e Protocolo: Segunda Opinião por Agente (Fase Só Consulta)

> **Contrato em vigor:** [26-second-opinion.md](../26-second-opinion.md). Este documento é o desenho do caso do
> Bike Anjo; no serviço, `case_facts`, `context` e `allowed_actions` são do projeto, e `point_to_buttons`
> chama-se `point_to_ui`.

Contrato canônico entre o canal de atendimento (`zapzap`/`sistemaBA`), a fila de orquestração do `ai2tcs` e os agentes professores (`Cursor Agent` ou `Antigravity` no `mini62`).

| | |
|---|---|
| Escopo | Fase 0 e 1: **Estritamente Leitura / Consulta** (sem execução de mutação no banco e sem envio ativo de WhatsApp) |
| Arquivo de schema | `second-opinion.schema.json` |
| Wrapper de chamada | `second-opinion.sh` (executado no `mini62`) |
| Consumo | Treinamento da LLM local via `/ratings` e exemplos aprovados |

---

## 1. O Pacote Enviado ao Professor (`SecondOpinionPayload`)

O pacote gerado pelo `zapzap`/`sistemaBA` só é despachado após a **janela de debounce** (ex.: 2 minutos). Ele agrega os fatos da ocorrência e sanitiza dados pessoais sensíveis.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SecondOpinionPayload",
  "type": "object",
  "required": [
    "source_ref",
    "project_id",
    "timestamp",
    "incoming_text",
    "local_hypothesis",
    "case_facts"
  ],
  "properties": {
    "source_ref": {
      "type": "string",
      "description": "Identificador único do caso/mensagem para rastreamento e deduplicação (ex: 'zap:msg:AAJA9-1731410000')"
    },
    "project_id": {
      "type": "string",
      "description": "Slug do projeto cliente (ex: 'bikeanjoall_2026')"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "Timestamp ISO UTC do recebimento"
    },
    "incoming_text": {
      "type": "string",
      "description": "Texto inbound consolidado do usuário após a janela de debounce"
    },
    "campaign_context": {
      "type": "object",
      "properties": {
        "active_campaign": { "type": "boolean" },
        "campaign_kind": { "type": "string", "enum": ["event_confirmation", "onboarding_followup", "survey", "other"] },
        "buttons_offered": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Rótulos dos botões apresentados na mensagem anterior (ex: ['Confirmar Presença', 'Liberar Vaga'])"
        }
      }
    },
    "local_hypothesis": {
      "type": "object",
      "required": ["suggested_route", "confidence"],
      "properties": {
        "suggested_route": { "type": "string" },
        "action": { "type": "string", "enum": ["answer_now", "escalate"] },
        "answer": { "type": "string" },
        "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "obs": { "type": "string" }
      }
    },
    "case_facts": {
      "type": "object",
      "required": ["slot_status", "button_already_used", "identity_ok_for_slot"],
      "properties": {
        "slot_status": {
          "type": "string",
          "enum": ["registered", "confirmed", "waiting", "released", "not_found", "unknown"],
          "description": "Situação real da vaga/inscrição da conta após o término da janela"
        },
        "button_already_used": {
          "type": "boolean",
          "description": "True se a pessoa já clicou no botão de liberar ou confirmar antes da avaliação da segunda opinião"
        },
        "identity_ok_for_slot": {
          "type": "boolean",
          "description": "True se o remetente tem autoridade verificada pelo backend para gerenciar a vaga (o agente NUNCA calcula acesso)"
        },
        "hours_until_event": {
          "type": "number",
          "description": "Horas restantes para o evento em questão (se aplicável)"
        }
      }
    }
  }
}
```

---

## 2. A Resposta do Agente Professor (`SecondOpinionResponse`)

O agente professor (`Cursor Agent` ou `Antigravity`) é instruído a responder **estritamente este JSON** (sem markdown envolvente):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SecondOpinionResponse",
  "type": "object",
  "required": [
    "source_ref",
    "agent",
    "local_answer_rating",
    "local_answer_path",
    "path_note",
    "intent",
    "reply_kind",
    "suggested_reply",
    "checked"
  ],
  "properties": {
    "source_ref": {
      "type": "string"
    },
    "agent": {
      "type": "string",
      "enum": ["cursor-agent", "antigravity", "gemini-fallback"]
    },
    "local_answer_rating": {
      "type": "string",
      "enum": ["good", "bad", "neutral"],
      "description": "Avaliação objetiva da hipótese da LLM local"
    },
    "local_answer_path": {
      "type": "string",
      "enum": ["right", "wrong"],
      "description": "Indica se a LLM local acertou a categoria/intenção do fluxo"
    },
    "path_note": {
      "type": "string",
      "description": "Diagnóstico pedagógico sucinto (ex: 'era ação de liberar vaga já executada via botão, não dúvida genérica de inscrição')"
    },
    "intent": {
      "type": "string",
      "enum": ["action", "question", "chitchat", "refusal"]
    },
    "reply_kind": {
      "type": "string",
      "enum": ["acknowledge_done", "point_to_buttons", "direct_answer", "silence", "escalate_human"]
    },
    "suggested_action": {
      "type": "object",
      "properties": {
        "type": { "type": "string", "enum": ["none", "release_slot", "confirm_slot", "manual_review"] },
        "already_applied": { "type": "boolean" },
        "why": { "type": "string" }
      }
    },
    "suggested_reply": {
      "type": "string",
      "description": "Resposta modelo em tom natural, curto e humanizado para ser aproveitada como exemplo gold"
    },
    "checked": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Lista de fatos verificados no pacote (ex: ['slot_status=released', 'button_already_used=true'])"
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0
    }
  }
}
```

---

## 3. Exemplos Canônicos de Treino

### Exemplo 1: Caso AAJA9 — Botão Já Utilizado na Janela

#### Entrada (Pacote do Zap):
```json
{
  "source_ref": "zap:msg:AAJA9-20261112",
  "project_id": "bikeanjoall_2026",
  "timestamp": "2026-11-12T11:00:00Z",
  "incoming_text": "Bom dia ! Vou precisar libertar a vaga . Larissa não vai conseguir comparecer 😢",
  "campaign_context": {
    "active_campaign": true,
    "campaign_kind": "event_confirmation",
    "buttons_offered": ["Confirmar Presença", "Liberar Vaga"]
  },
  "local_hypothesis": {
    "suggested_route": "ask",
    "action": "answer_now",
    "answer": "Há registro de interesse na EBA Lagoa. Ainda não confirmamos sua inscrição, aguarde novidades.",
    "confidence": 0.65,
    "obs": "identificou eba lagoa via RAG"
  },
  "case_facts": {
    "slot_status": "released",
    "button_already_used": true,
    "identity_ok_for_slot": true,
    "hours_until_event": 42.5
  }
}
```

#### Saída do Professor:
```json
{
  "source_ref": "zap:msg:AAJA9-20261112",
  "agent": "cursor-agent",
  "local_answer_rating": "bad",
  "local_answer_path": "wrong",
  "path_note": "A pessoa informou liberação de vaga e já clicou no botão na janela. A hipótese local tratou como dúvida genérica de interesse e ignorou a ação consumada.",
  "intent": "action",
  "reply_kind": "acknowledge_done",
  "suggested_action": {
    "type": "release_slot",
    "already_applied": true,
    "why": "Vaga já foi liberada via clique no botão registrado em case_facts."
  },
  "suggested_reply": "Bom dia! Tudo bem, a vaga da Larissa já foi liberada com sucesso. Obrigado por avisar!",
  "checked": ["slot_status=released", "button_already_used=true", "identity_ok_for_slot=true"],
  "confidence": 0.98
}
```

---

### Exemplo 2: Pessoa Enviou Texto mas NÃO Clicou no Botão

#### Entrada:
```json
{
  "source_ref": "zap:msg:BB77-20261112",
  "project_id": "bikeanjoall_2026",
  "timestamp": "2026-11-12T11:15:00Z",
  "incoming_text": "Não vou conseguir ir no domingo, podem passar pra outro",
  "campaign_context": {
    "active_campaign": true,
    "campaign_kind": "event_confirmation",
    "buttons_offered": ["Confirmar Presença", "Liberar Vaga"]
  },
  "local_hypothesis": {
    "suggested_route": "ask",
    "action": "answer_now",
    "answer": "Você pode verificar os próximos eventos no site.",
    "confidence": 0.40,
    "obs": "confiança baixa"
  },
  "case_facts": {
    "slot_status": "confirmed",
    "button_already_used": false,
    "identity_ok_for_slot": true,
    "hours_until_event": 48.0
  }
}
```

#### Saída do Professor:
```json
{
  "source_ref": "zap:msg:BB77-20261112",
  "agent": "cursor-agent",
  "local_answer_rating": "bad",
  "local_answer_path": "wrong",
  "path_note": "A intenção é desistência/liberação de vaga confirmada, mas o botão oficial ainda não foi clicado. Orientar o botão para atualizar a vaga no sistema.",
  "intent": "action",
  "reply_kind": "point_to_buttons",
  "suggested_action": {
    "type": "release_slot",
    "already_applied": false,
    "why": "A pessoa deseja liberar a vaga mas ainda não clicou no botão correspondente."
  },
  "suggested_reply": "Para confirmar a liberação da sua vaga e chamar quem está na fila de espera, por favor clique no botão 'Liberar Vaga' na mensagem acima.",
  "checked": ["slot_status=confirmed", "button_already_used=false", "identity_ok_for_slot=true"],
  "confidence": 0.95
}
```
