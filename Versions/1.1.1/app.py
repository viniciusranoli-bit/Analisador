import csv
import io
import os
import zipfile
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader

load_dotenv()

APP_VERSION = "v0.1.1"
MAX_CHARS = 45_000
MAX_FILE_BYTES = 15 * 1024 * 1024

app = FastAPI(title="AnalisadorCV IA", version=APP_VERSION)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class LinkedInAnalysis(BaseModel):
    app_version: str = APP_VERSION
    score_geral: int = Field(ge=0, le=100)
    diagnostico: str
    pontos_fortes: List[str]
    pontos_de_risco: List[str]
    palavras_chave_recomendadas: List[str]
    headline_sugerida: str
    sobre_sugerido: str
    acoes_prioritarias: List[str]
    checklist: List[str]


@app.get("/")
def home():
    return FileResponse("index.html")


@app.get("/version")
def version():
    return {"app_name": "AnalisadorCV IA", "version": APP_VERSION}


def clean_value(value: Optional[str]) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split()).strip()


def csv_from_zip(zipped_file: zipfile.ZipFile, csv_name: str) -> List[dict]:
    try:
        raw = zipped_file.read(csv_name)
    except KeyError:
        return []

    text = raw.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def rows_to_section(title: str, rows: List[dict], allowed_columns: List[str], max_rows: int = 50) -> str:
    if not rows:
        return ""

    lines = [f"\n## {title}"]
    for idx, row in enumerate(rows[:max_rows], start=1):
        parts = []
        for col in allowed_columns:
            value = clean_value(row.get(col))
            if value:
                parts.append(f"{col}: {value}")
        if parts:
            lines.append(f"{idx}. " + " | ".join(parts))
    return "\n".join(lines)


def extract_text_from_linkedin_zip(file_bytes: bytes) -> str:
    try:
        zipped_file = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="ZIP inválido. Envie o arquivo original exportado do LinkedIn.")

    available_files = set(zipped_file.namelist())
    sections = ["# Dados profissionais extraídos do LinkedIn"]

    profile_rows = csv_from_zip(zipped_file, "Profile.csv")
    if profile_rows:
        section = rows_to_section(
            "Perfil",
            profile_rows,
            ["First Name", "Last Name", "Headline", "Summary", "Industry", "Geo Location", "Websites"],
            max_rows=1,
        )
        if section:
            sections.append(section)

    extraction_plan = [
        ("Experiências", "Positions.csv", ["Company Name", "Title", "Description", "Location", "Started On", "Finished On"], 30),
        ("Competências", "Skills.csv", ["Name"], 120),
        ("Formação", "Education.csv", ["School Name", "Start Date", "End Date", "Degree Name", "Activities", "Notes"], 30),
        ("Certificações", "Certifications.csv", ["Name", "Authority", "Started On", "Finished On", "License Number"], 30),
        ("Recomendações recebidas", "Recommendations_Received.csv", ["First Name", "Last Name", "Company", "Job Title", "Text", "Creation Date"], 20),
        ("Cursos / Aprendizado", "Learning.csv", ["Content Name", "Content Provider", "Completed At"], 50),
        ("Projetos / mídias", "Rich_Media.csv", ["Title", "Description", "Url"], 30),
    ]

    for title, file_name, columns, max_rows in extraction_plan:
        rows = csv_from_zip(zipped_file, file_name)
        section = rows_to_section(title, rows, columns, max_rows=max_rows)
        if section:
            sections.append(section)

    extracted = "\n".join(section for section in sections if section).strip()

    if len(extracted) < 300:
        found = ", ".join(sorted(available_files)[:20])
        raise HTTPException(
            status_code=400,
            detail=f"O ZIP foi lido, mas não encontrei dados profissionais suficientes. Arquivos encontrados: {found}",
        )

    return extracted[:MAX_CHARS]


def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages).strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler o PDF: {exc}")


def extract_text_from_txt_bytes(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8", errors="ignore").strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler o TXT: {exc}")


def build_prompt(
    profile_text: str,
    specialty: str,
    seniority: str,
    objective: str,
    target_role: Optional[str],
    extra_context: Optional[str],
) -> str:
    return f"""
Você é um especialista sênior em desenvolvimento de carreira, LinkedIn, recrutamento e marca profissional.

Analise o perfil abaixo com foco em melhores práticas de LinkedIn, posicionamento profissional e aderência ao objetivo informado.

Versão do sistema: {APP_VERSION}

Contexto informado pelo candidato:
- Especialidade: {specialty}
- Senioridade: {seniority}
- Objetivo profissional: {objective}
- Cargo ou vaga-alvo: {target_role or "Não informado"}
- Contexto adicional: {extra_context or "Não informado"}

Regras importantes:
- Não avalie foto, idade, gênero, raça, religião, estado civil, endereço, telefone, e-mail ou qualquer atributo pessoal sensível.
- Avalie apenas conteúdo profissional.
- Seja direto, prático e específico.
- Aponte riscos de percepção profissional.
- Não invente experiências que não aparecem no perfil.
- Se faltarem informações, diga o que falta e como corrigir.
- A headline sugerida deve ser objetiva e otimizada para busca.
- O "Sobre sugerido" deve ter tom profissional, humano e orientado a resultados.
- A senioridade informada deve ser considerada na régua de avaliação.

Conteúdo extraído do perfil:
\"\"\"
{profile_text[:MAX_CHARS]}
\"\"\"
""".strip()


@app.post("/analyze", response_model=LinkedInAnalysis)
async def analyze_profile(
    linkedin_file: UploadFile = File(...),
    specialty: str = Form(...),
    seniority: str = Form(...),
    objective: str = Form(...),
    target_role: Optional[str] = Form(None),
    extra_context: Optional[str] = Form(None),
):
    filename = linkedin_file.filename or ""
    lower_filename = filename.lower()
    content = await linkedin_file.read()

    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Limite: 15MB.")

    if lower_filename.endswith(".zip") or lower_filename.endswith(".zip.zip"):
        profile_text = extract_text_from_linkedin_zip(content)
    elif lower_filename.endswith(".pdf"):
        profile_text = extract_text_from_pdf_bytes(content)
    elif lower_filename.endswith(".txt"):
        profile_text = extract_text_from_txt_bytes(content)
    else:
        raise HTTPException(status_code=400, detail="Envie um arquivo ZIP, PDF ou TXT.")

    if len(profile_text) < 300:
        raise HTTPException(
            status_code=400,
            detail="O arquivo tem pouco texto. Envie o ZIP oficial do LinkedIn ou um arquivo com o conteúdo completo do perfil.",
        )

    prompt = build_prompt(
        profile_text=profile_text,
        specialty=specialty,
        seniority=seniority,
        objective=objective,
        target_role=target_role,
        extra_context=extra_context,
    )

    try:
        response = client.responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-5.2"),
            input=[
                {"role": "system", "content": "Você responde exclusivamente em JSON válido conforme o schema solicitado."},
                {"role": "user", "content": prompt},
            ],
            text_format=LinkedInAnalysis,
        )

        parsed = response.output_parsed
        parsed.app_version = APP_VERSION
        return parsed

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao chamar a IA: {exc}")
