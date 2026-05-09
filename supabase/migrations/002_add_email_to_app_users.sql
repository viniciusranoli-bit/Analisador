-- Adiciona e-mail único para autenticação.
ALTER TABLE public.app_users
ADD COLUMN IF NOT EXISTS email text;

UPDATE public.app_users
SET email = lower(username) || '@sem-email.local'
WHERE email IS NULL OR btrim(email) = '';

ALTER TABLE public.app_users
ALTER COLUMN email SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'app_users_email_key'
      AND conrelid = 'public.app_users'::regclass
  ) THEN
    ALTER TABLE public.app_users
    ADD CONSTRAINT app_users_email_key UNIQUE (email);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_app_users_email_lower ON public.app_users (lower(email));
