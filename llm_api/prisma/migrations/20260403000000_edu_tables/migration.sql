-- Vocabulário educacional
CREATE TABLE edu_vocabulary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    language VARCHAR(10) NOT NULL DEFAULT 'zh-CN',
    hanzi TEXT NOT NULL,
    pinyin TEXT NOT NULL,
    translation TEXT NOT NULL,
    level VARCHAR(10) NOT NULL,         -- HSK1..HSK6 ou custom
    category VARCHAR(50),               -- noun, verb, adjective, etc.
    example_sentence TEXT,
    example_pinyin TEXT,
    example_translation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON edu_vocabulary (language, level);

-- Pontos gramaticais
CREATE TABLE edu_grammar (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    language VARCHAR(10) NOT NULL DEFAULT 'zh-CN',
    pattern TEXT NOT NULL,
    explanation TEXT NOT NULL,
    level VARCHAR(10) NOT NULL,
    examples JSONB NOT NULL DEFAULT '[]',  -- [{hanzi, pinyin, translation}]
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON edu_grammar (language, level);

-- Progresso do usuário por palavra
CREATE TABLE edu_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    vocab_id UUID NOT NULL REFERENCES edu_vocabulary(id) ON DELETE CASCADE,
    seen_count INT NOT NULL DEFAULT 1,
    correct_count INT NOT NULL DEFAULT 0,
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mastered BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(user_id, vocab_id)
);
CREATE INDEX ON edu_progress (user_id);
