# 🧠 Analisador CV IA — v1.0.0

Sistema local para análise executiva de perfis LinkedIn usando OpenAI GPT.

---

## ⚙️ Instalação

```bash
cd C:\Projetos\AnalisadorCV
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🔑 Configuração da API

Copie o arquivo `.env.example` para `.env` e insira sua chave OpenAI:

```bash
copy .env.example .env
```

Edite o `.env`:
```
OPENAI_API_KEY=sk-...sua-chave...
OPENAI_MODEL=gpt-4.1-mini
```

---

## ▶️ Execução

```bash
cd C:\Projetos\AnalisadorCV
.venv\Scripts\activate
python -m uvicorn app:app --reload
```

Acesse: **http://localhost:8000**

---

## 📁 Estrutura

```
AnalisadorCV/
├── app.py              # Backend FastAPI
├── index.html          # Frontend
├── requirements.txt    # Dependências
├── .env.example        # Exemplo de variáveis de ambiente
├── .env                # Sua chave API (NÃO commitar)
├── README.md
└── Historico/          # Análises salvas (criada automaticamente)
```

---

## 📤 Exportando dados do LinkedIn

1. Acesse LinkedIn → **Configurações**
2. Vá em **Privacidade dos dados**
3. Clique em **Obter uma cópia dos seus dados**
4. Selecione todos os dados e solicite o arquivo
5. Faça o download do `.zip` e envie no sistema

---

## 🚀 Funcionalidades

- Upload do ZIP oficial do LinkedIn
- Análise executiva com OpenAI GPT
- Score geral (0–100)
- Veredito, Diagnóstico, Ações Prioritárias
- Pontos Fortes e Riscos identificados
- Palavras-chave recomendadas
- Headline e seção "Sobre" otimizadas
- Checklist de perfil
- Artigos recomendados
- Histórico de análises salvas

---

## 📌 Notas

- O sistema **não avalia** dados sensíveis (idade, gênero, raça, foto, religião)
- Análises salvas ficam em `Historico/` no formato `.json`
- Compatível com Windows 10/11

---

**v1.0.0** — Desenvolvido com FastAPI + OpenAI + HTML/CSS/JS puro
