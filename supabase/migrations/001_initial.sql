-- Execute no SQL Editor do Supabase (Dashboard → SQL → New query).
-- Projeto: https://pcriebnzkaowvettrkzn.supabase.co
--
-- No servidor Python (.env), defina:
--   SUPABASE_URL=https://pcriebnzkaowvettrkzn.supabase.co
--   SUPABASE_SERVICE_ROLE_KEY=<chave service_role do painel API — nunca no frontend>

-- Usuários da aplicação (login próprio; não confundir com auth.users)
CREATE TABLE IF NOT EXISTS public.app_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text NOT NULL UNIQUE,
  salt text NOT NULL,
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_users_username_lower ON public.app_users (lower(username));

-- Histórico de análises (payload completo em JSON)
CREATE TABLE IF NOT EXISTS public.historico_analises (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario text NOT NULL,
  dados jsonb NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_historico_usuario_criado
  ON public.historico_analises (lower(usuario), criado_em DESC);

-- Feedback de artigos (um registro por usuário + análise + nome do artigo)
CREATE TABLE IF NOT EXISTS public.artigos_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario text NOT NULL,
  analise_data text NOT NULL DEFAULT '',
  artigo_nome text NOT NULL,
  artigo_link text NOT NULL DEFAULT '',
  gostou boolean NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_artigos_feedback_user_analise_titulo
  ON public.artigos_feedback (lower(usuario), analise_data, lower(artigo_nome));

-- Sugestões de funcionalidades
CREATE TABLE IF NOT EXISTS public.sugestoes_funcionalidades (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario text NOT NULL,
  sugestao text NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sugestoes_criado ON public.sugestoes_funcionalidades (criado_em DESC);

-- RLS: o backend usa SERVICE_ROLE_KEY e ignora RLS. Opcional: habilitar RLS + policies se no futuro
-- o cliente acessar o PostgREST diretamente.

COMMENT ON TABLE public.app_users IS 'Contas criadas no app (login/senha próprios).';
COMMENT ON TABLE public.historico_analises IS 'Análises salvas; campo dados = JSON da análise.';
COMMENT ON TABLE public.artigos_feedback IS 'Feedback gostou/não gostou por artigo recomendado.';
COMMENT ON TABLE public.sugestoes_funcionalidades IS 'Sugestões enviadas pelos usuários.';

-- Carga a partir dos JSON/pasta Historico (na máquina do projeto):
--   python scripts/migrate_json_to_supabase.py --dry-run
--   python scripts/migrate_json_to_supabase.py --reset
