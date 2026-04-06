-- 创建 contracts 表
CREATE TABLE IF NOT EXISTS contracts (
    id SERIAL PRIMARY KEY,
    award_id TEXT UNIQUE NOT NULL,
    recipient_name TEXT,
    award_amount NUMERIC,
    action_date DATE,
    start_date DATE,
    internal_id TEXT,
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_action_date ON contracts(action_date);
CREATE INDEX IF NOT EXISTS idx_start_date ON contracts(start_date);
CREATE INDEX IF NOT EXISTS idx_recipient ON contracts(recipient_name);
CREATE INDEX IF NOT EXISTS idx_award_amount ON contracts(award_amount);