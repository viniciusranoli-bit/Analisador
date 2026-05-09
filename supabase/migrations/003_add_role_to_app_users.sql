-- Adiciona tipo de utilizador: 'admin' | 'user' (padrão 'user').
ALTER TABLE public.app_users
ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'user';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'app_users_role_check'
      AND conrelid = 'public.app_users'::regclass
  ) THEN
    ALTER TABLE public.app_users
    ADD CONSTRAINT app_users_role_check CHECK (role IN ('admin', 'user'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_app_users_role ON public.app_users (role);
