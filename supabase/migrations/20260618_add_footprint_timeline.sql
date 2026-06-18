-- Resonance footprint timeline prototype schema.
-- Run manually in Supabase SQL Editor when you are ready to move footprints
-- from local SQLite prototype data to Supabase. Do not use service_role keys
-- in the Streamlit app.

create table if not exists public.places (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    category text not null default '其他',
    city text not null default '',
    district text not null default '',
    address text not null default '',
    latitude double precision not null,
    longitude double precision not null,
    osm_type text,
    osm_id text,
    source text not null default 'manual',
    created_at timestamptz not null default now(),
    constraint places_valid_latitude check (latitude between -90 and 90),
    constraint places_valid_longitude check (longitude between -180 and 180)
);

create unique index if not exists places_osm_unique_idx
on public.places(osm_type, osm_id)
where osm_type is not null and osm_id is not null;

alter table public.checkins
    add column if not exists place_id uuid references public.places(id) on delete set null,
    add column if not exists visited_at timestamptz,
    add column if not exists ended_at timestamptz,
    add column if not exists duration_minutes integer,
    add column if not exists mood text not null default '',
    add column if not exists tags text[] not null default '{}',
    add column if not exists source text not null default 'manual',
    add column if not exists timezone text not null default 'Asia/Shanghai',
    add column if not exists notes text not null default '',
    add column if not exists feed_public boolean not null default false;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'checkins_duration_non_negative'
    ) then
        alter table public.checkins
            add constraint checkins_duration_non_negative
            check (duration_minutes is null or duration_minutes >= 0);
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'checkins_ended_after_visited'
    ) then
        alter table public.checkins
            add constraint checkins_ended_after_visited
            check (ended_at is null or visited_at is null or ended_at >= visited_at);
    end if;
end $$;

update public.checkins
set visited_at = coalesce(visited_at, created_at)
where visited_at is null;

alter table public.places enable row level security;
alter table public.checkins enable row level security;

drop policy if exists "Authenticated users can read places" on public.places;
create policy "Authenticated users can read places"
on public.places
for select
to authenticated
using (true);

drop policy if exists "Authenticated users can insert places" on public.places;
create policy "Authenticated users can insert places"
on public.places
for insert
to authenticated
with check (true);

drop policy if exists "Users can read own checkins" on public.checkins;
create policy "Users can read own checkins"
on public.checkins
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users can insert own checkins" on public.checkins;
create policy "Users can insert own checkins"
on public.checkins
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users can update own checkins" on public.checkins;
create policy "Users can update own checkins"
on public.checkins
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can delete own checkins" on public.checkins;
create policy "Users can delete own checkins"
on public.checkins
for delete
to authenticated
using (auth.uid() = user_id);
