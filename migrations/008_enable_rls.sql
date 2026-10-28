-- Migration 008: Enable Row Level Security (RLS) on remaining public tables
-- Ensures compliance with Supabase Security Advisor linter
ALTER TABLE IF EXISTS schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pr_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS fix_attempts ENABLE ROW LEVEL SECURITY;
