# AnalisadorCV IA v0.1.1

Correção da v0.1.

## Correções

- Corrigido erro de `unterminated triple-quoted string literal`
- `README.md` separado corretamente do `app.py`
- Mantida leitura do ZIP oficial do LinkedIn
- Versão exibida no site: `v0.1.1`

## Como atualizar

Substitua na pasta:

```text
C:\Projetos\AnalisadorCV
```

os arquivos:

```text
app.py
index.html
requirements.txt
README.md
```

Depois rode:

```bash
cd C:\Projetos\AnalisadorCV
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Abra:

```text
http://127.0.0.1:8000
```
