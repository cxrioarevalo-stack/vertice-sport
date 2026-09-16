-- VÉRTICE SPORT V0.3.1 schema
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  url TEXT,
  reliability TEXT DEFAULT 'unknown',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sport_key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS competitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sport_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  country TEXT,
  external_urn TEXT,
  UNIQUE(sport_id, name)
);
CREATE TABLE IF NOT EXISTS teams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sport_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  short_name TEXT,
  external_urn TEXT,
  UNIQUE(sport_id, name)
);
CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  team_id INTEGER,
  sport_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  external_urn TEXT
);
CREATE TABLE IF NOT EXISTS matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sport_id INTEGER NOT NULL,
  sport_key TEXT NOT NULL DEFAULT 'football',
  competition_id INTEGER,
  home_team_id INTEGER,
  away_team_id INTEGER,
  source_code TEXT,
  external_id TEXT,
  external_urn TEXT,
  kickoff_utc TEXT,
  venue TEXT,
  status TEXT,
  minute TEXT,
  home_score TEXT,
  away_score TEXT,
  data_quality TEXT,
  integrity_level TEXT,
  integrity_note TEXT,
  presence TEXT,
  last_seen_scan_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(source_code, external_id)
);
CREATE TABLE IF NOT EXISTS match_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL,
  scan_id INTEGER,
  source_id INTEGER NOT NULL,
  field_name TEXT NOT NULL,
  field_value TEXT,
  data_status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS statistics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER,
  team_id INTEGER,
  player_id INTEGER,
  stat_key TEXT NOT NULL,
  stat_value TEXT,
  source_id INTEGER,
  data_status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS injuries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER,
  team_id INTEGER,
  match_id INTEGER,
  description TEXT,
  source_id INTEGER,
  data_status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suspensions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER,
  team_id INTEGER,
  match_id INTEGER,
  description TEXT,
  source_id INTEGER,
  data_status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lineups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL,
  team_id INTEGER,
  player_id INTEGER,
  role TEXT,
  source_id INTEGER,
  data_status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER,
  team_id INTEGER,
  player_id INTEGER,
  title TEXT,
  summary TEXT,
  url TEXT,
  published_at TEXT,
  source_id INTEGER,
  data_status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS markets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  sport_key TEXT NOT NULL,
  group_name TEXT
);
CREATE TABLE IF NOT EXISTS odds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL,
  market_id INTEGER NOT NULL,
  selection TEXT NOT NULL,
  bookmaker TEXT,
  price REAL,
  source_id INTEGER,
  data_status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS integrity_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL,
  signal_type TEXT NOT NULL,
  description TEXT,
  source_id INTEGER,
  data_status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL,
  market_id INTEGER,
  selection TEXT,
  estimated_probability REAL,
  odds_id INTEGER,
  confidence_level TEXT,
  variables_json TEXT,
  created_at TEXT NOT NULL,
  withdrawn INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS prediction_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prediction_id INTEGER NOT NULL,
  actual_result TEXT,
  win_loss TEXT,
  settled_at TEXT
);
CREATE TABLE IF NOT EXISTS scan_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  date_local TEXT,
  timezone TEXT,
  sport_key TEXT DEFAULT 'football',
  status TEXT,
  matches_found INTEGER,
  sources_ok TEXT,
  sources_fail TEXT,
  persist_ok INTEGER,
  persist_error TEXT,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);
INSERT OR IGNORE INTO sports (id, sport_key, name) VALUES
  (1, 'football', 'Football'),
  (2, 'tennis', 'Tennis'),
  (3, 'basketball', 'Basketball'),
  (4, 'baseball', 'Baseball');
INSERT OR IGNORE INTO sources (code, name, url, reliability, created_at) VALUES
  ('bbc', 'BBC Sport', 'https://www.bbc.co.uk/sport/football', 'high', datetime('now')),
  ('betano', 'Betano', 'https://lat.betano.com', 'blocked', datetime('now')),
  ('manual_public', 'Public web reports', NULL, 'variable', datetime('now'));
INSERT OR IGNORE INTO markets (code, name, sport_key, group_name) VALUES
  ('1x2', 'Match result 1X2', 'football', 'result'),
  ('double_chance', 'Double chance', 'football', 'result'),
  ('dnb', 'Draw no bet', 'football', 'result'),
  ('handicap', 'Handicap', 'football', 'result'),
  ('ah', 'Asian handicap', 'football', 'result'),
  ('ou', 'Over/Under', 'football', 'goals'),
  ('btts', 'Both teams to score', 'football', 'goals'),
  ('team_goals', 'Team goals', 'football', 'goals'),
  ('fh', 'First half', 'football', 'period'),
  ('sh', 'Second half', 'football', 'period'),
  ('time', 'Time-based markets', 'football', 'time'),
  ('live', 'Live markets', 'football', 'live');

CREATE TABLE IF NOT EXISTS odds_provider_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_code TEXT NOT NULL,
  provider_event_id TEXT NOT NULL,
  sport_key TEXT NOT NULL DEFAULT 'football',
  home_team TEXT,
  away_team TEXT,
  competition TEXT,
  kickoff_utc TEXT,
  raw_status TEXT,
  fetched_at TEXT NOT NULL,
  UNIQUE(provider_code, provider_event_id)
);

CREATE TABLE IF NOT EXISTS odds_event_map (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL,
  provider_code TEXT NOT NULL,
  provider_event_id TEXT NOT NULL,
  confidence REAL,
  method TEXT,
  reason TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(provider_code, provider_event_id)
);

CREATE TABLE IF NOT EXISTS odds_unmatched (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_code TEXT NOT NULL,
  provider_event_id TEXT,
  home_team TEXT,
  away_team TEXT,
  kickoff_utc TEXT,
  reason TEXT,
  observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id INTEGER,
  match_id INTEGER,
  provider_code TEXT NOT NULL,
  provider_event_id TEXT,
  bookmaker TEXT NOT NULL,
  market_code TEXT NOT NULL,
  market_name TEXT,
  selection TEXT NOT NULL,
  line REAL,
  decimal_odds REAL NOT NULL,
  raw_odds TEXT,
  phase TEXT NOT NULL,
  data_status TEXT NOT NULL DEFAULT 'REAL',
  source_updated_at TEXT,
  observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_request_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_code TEXT NOT NULL,
  endpoint TEXT,
  http_status INTEGER,
  ok INTEGER,
  error TEXT,
  observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_market_catalog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_code TEXT NOT NULL,
  sport_key TEXT NOT NULL DEFAULT 'football',
  sport_id INTEGER,
  market_id TEXT NOT NULL,
  market_name TEXT,
  market_type TEXT,
  period TEXT,
  player_prop INTEGER,
  catalog_handicap REAL,
  fetched_at TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'oddspapi',
  UNIQUE(provider_code, sport_key, market_id)
);

CREATE TABLE IF NOT EXISTS odds_market_outcomes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_code TEXT NOT NULL,
  sport_key TEXT NOT NULL DEFAULT 'football',
  market_id TEXT NOT NULL,
  outcome_id TEXT NOT NULL,
  outcome_name TEXT,
  UNIQUE(provider_code, sport_key, market_id, outcome_id)
);

CREATE TABLE IF NOT EXISTS odds_catalog_meta (
  provider_code TEXT NOT NULL,
  sport_key TEXT NOT NULL,
  sport_id INTEGER NOT NULL,
  fetched_at TEXT NOT NULL,
  market_count INTEGER,
  PRIMARY KEY (provider_code, sport_key, sport_id)
);

CREATE TABLE IF NOT EXISTS odds_mapped_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id INTEGER,
  scan_id INTEGER,
  match_id INTEGER,
  sport_key TEXT NOT NULL DEFAULT 'football',
  provider_code TEXT NOT NULL,
  provider_event_id TEXT,
  bookmaker TEXT NOT NULL,
  market_id TEXT NOT NULL,
  market_name_official TEXT,
  market_type TEXT,
  period_official TEXT,
  outcome_id TEXT,
  outcome_name_official TEXT,
  fixture_line REAL,
  catalog_handicap REAL,
  decimal_odds REAL NOT NULL,
  phase TEXT,
  data_status TEXT NOT NULL DEFAULT 'REAL',
  mapped INTEGER NOT NULL DEFAULT 1,
  source_updated_at TEXT,
  observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_unmapped_markets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id INTEGER,
  scan_id INTEGER,
  match_id INTEGER,
  sport_key TEXT NOT NULL DEFAULT 'football',
  provider_code TEXT NOT NULL,
  provider_event_id TEXT,
  bookmaker TEXT,
  raw_market_id TEXT,
  raw_outcome_id TEXT,
  fixture_line REAL,
  decimal_odds REAL,
  phase TEXT,
  reason TEXT,
  observed_at TEXT NOT NULL
);

-- DEV/DEBUG only. Disable with VERTICE_CAPTURE_RAW_ODDS=0. Not production market data.
CREATE TABLE IF NOT EXISTS odds_raw_captures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id INTEGER,
  provider_code TEXT NOT NULL,
  provider_event_id TEXT,
  bookmaker TEXT,
  captured_at TEXT NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'debug_raw_odds',
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_normalized_v043 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id INTEGER,
  scan_id INTEGER,
  match_id INTEGER,
  sport_key TEXT NOT NULL DEFAULT 'football',
  provider_code TEXT NOT NULL,
  provider_event_id TEXT,
  bookmaker TEXT NOT NULL,
  market_id TEXT NOT NULL,
  bookmaker_market_id TEXT,
  market_name_official TEXT,
  market_type TEXT,
  period_official TEXT,
  outcome_id TEXT,
  bookmaker_outcome_id TEXT,
  outcome_name_official TEXT,
  player_id TEXT,
  player_name TEXT,
  fixture_line REAL,
  catalog_handicap REAL,
  decimal_odds REAL NOT NULL,
  phase TEXT,
  mapped INTEGER NOT NULL DEFAULT 0,
  data_status TEXT NOT NULL DEFAULT 'REAL',
  source_updated_at TEXT,
  observed_at TEXT NOT NULL
);
