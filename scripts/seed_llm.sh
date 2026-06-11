#!/usr/bin/env bash
# Seed LLM config (models + routes + budgets) cho môi trường dev/test.
# CHẠY THỦ CÔNG — không tự động trong app. Idempotent.
# Production: cấu hình qua trang superadmin Models.
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://smart:smart@localhost:5433/smart_bot}"

echo "→ Seeding LLM config (models, routes, budgets) …"

PGPASSWORD=smart psql "$DB_URL" -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;

-- Models: smart = gpt-4o (kèm vision), fast = groq llama (nhanh + rẻ)
INSERT INTO models (name, provider, endpoint_kind, base_url, tier, ctx_max,
                    capabilities, cost_per_1m_input_usd, cost_per_1m_output_usd,
                    is_platform_default, notes)
SELECT 'gpt-4o', 'openai', 'openai_compat', NULL, 'smart', 128000,
       '["text","vision","tools"]'::jsonb, 2.50, 10.00, TRUE, 'seed_llm.sh'
WHERE NOT EXISTS (SELECT 1 FROM models WHERE name='gpt-4o' AND provider='openai');

INSERT INTO models (name, provider, endpoint_kind, base_url, tier, ctx_max,
                    capabilities, cost_per_1m_input_usd, cost_per_1m_output_usd,
                    is_platform_default, notes)
SELECT 'llama-3.3-70b-versatile', 'groq', 'openai_compat',
       'https://api.groq.com/openai/v1', 'fast', 128000,
       '["text","tools"]'::jsonb, 0.59, 0.79, TRUE, 'seed_llm.sh'
WHERE NOT EXISTS (SELECT 1 FROM models WHERE name='llama-3.3-70b-versatile' AND provider='groq');

-- Routes: feature → tier (fallback chain)
INSERT INTO llm_routes (feature, target_tier, fallback_chain, weight, notes)
SELECT v.feature, v.tier, v.fb::jsonb, 100, 'seed_llm.sh'
FROM (VALUES
  ('dm_general',     'smart', '["fast"]'),
  ('note_update',    'fast',  '["smart"]'),
  ('qa_with_search', 'smart', '["fast"]')
) AS v(feature, tier, fb)
WHERE NOT EXISTS (SELECT 1 FROM llm_routes r WHERE r.feature = v.feature);

-- Budgets per feature
INSERT INTO feature_budgets (feature, max_input_tokens, max_output_tokens, trim_policy_json)
SELECT v.feature, v.tin, v.tout, '{}'::jsonb
FROM (VALUES
  ('dm_general',     12000, 1000),
  ('note_update',    16000, 2000),
  ('qa_with_search', 16000, 1500)
) AS v(feature, tin, tout)
ON CONFLICT (feature) DO NOTHING;

COMMIT;
SQL

echo "✓ LLM config seeded:"
PGPASSWORD=smart psql "$DB_URL" -c "SELECT name, provider, tier, is_platform_default FROM models" \
  -c "SELECT feature, target_tier, fallback_chain FROM llm_routes" \
  -c "SELECT feature, max_input_tokens, max_output_tokens FROM feature_budgets"
