-- Tightens the policies from the original schema. Run in the Supabase SQL Editor.
-- Nothing in the app reads other users' profiles or activity logs, so these
-- don't break any feature.

-- profiles: emails were readable by anyone holding the public anon key.
DROP POLICY IF EXISTS "Public profiles are viewable by everyone" ON public.profiles;
DROP POLICY IF EXISTS "Users can view own profile" ON public.profiles;
CREATE POLICY "Users can view own profile" ON public.profiles
    FOR SELECT TO authenticated USING (auth.uid() = id);

-- profiles: anyone could insert arbitrary rows. The signup trigger runs as the
-- table owner (SECURITY DEFINER), which bypasses RLS, so it needs no policy.
DROP POLICY IF EXISTS "Allow system insert into profiles" ON public.profiles;

-- Pin search_path on the SECURITY DEFINER trigger function (Supabase linter 0011).
ALTER FUNCTION public.handle_new_user() SET search_path = public;

-- user_activity_logs: every user's email, IP and activity were publicly readable.
-- Users may now read only their own logs. Inserts stay open, because the
-- server-side logger uses the anon key.
DROP POLICY IF EXISTS "Allow select" ON public.user_activity_logs;
DROP POLICY IF EXISTS "Users read own activity" ON public.user_activity_logs;
CREATE POLICY "Users read own activity" ON public.user_activity_logs
    FOR SELECT TO authenticated USING (auth.uid()::text = user_id);
