-- AItranscriber schema for Neon (Postgres)
-- Run this once against your Neon database, e.g.:
--   psql "$DATABASE_URL" -f app/db/schema.sql

create extension if not exists pgcrypto;

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email text unique not null,
    password_hash text not null,
    created_at timestamptz not null default now()
);

create table if not exists user_preferences (
    user_id uuid primary key,
    summary_frequency integer not null default 7
);

create table if not exists notes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    urdu_text text,
    urdu_text_corrected text,
    urdu_text_roman text,
    english_text text,
    title text,
    tags text[],
    audio_url text,
    embedding double precision[],
    created_at timestamptz not null default now()
);

create index if not exists idx_notes_user_id on notes (user_id);

create table if not exists memories (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    text text not null,
    kind text not null check (kind in ('short', 'long')),
    embedding double precision[],
    expires_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists idx_memories_user_id on memories (user_id);
