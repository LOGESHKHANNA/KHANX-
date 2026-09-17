-- Migration: Auto-create profile trigger on Supabase Auth signup
-- Resolves user/profile race condition and chat_sessions_user_id_fkey foreign key constraint errors.

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
DECLARE
  meta_username TEXT;
  user_email TEXT;
BEGIN
  user_email := COALESCE(new.email, new.id::text || '@user.com');
  meta_username := COALESCE(
    new.raw_user_meta_data->>'username',
    new.raw_user_meta_data->>'name',
    new.raw_user_meta_data->>'full_name',
    split_part(user_email, '@', 1)
  );

  INSERT INTO public.profiles (id, email, username)
  VALUES (new.id, user_email, meta_username)
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    username = COALESCE(profiles.username, EXCLUDED.username);
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
