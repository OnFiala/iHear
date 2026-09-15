-- Add accent-insensitive search without rewriting profiles, event snapshots or revisions.
-- Existing search vectors remain intact so an older application can be restored.
create extension if not exists unaccent with schema extensions;
create text search configuration ihear.patient_search (copy = pg_catalog.simple);
alter text search configuration ihear.patient_search
  alter mapping for hword, hword_part, word
  with extensions.unaccent, pg_catalog.simple;

create index patients_directory_search_idx on ihear.patients using gin (
  to_tsvector('ihear.patient_search', coalesce(display_name, '') || ' ' || coalesce(note, ''))
);
create index events_directory_search_idx on ihear.events using gin (
  to_tsvector('ihear.patient_search', coalesce(kind, '') || ' ' || coalesce(difficulty, '') || ' ' ||
    coalesce(environment, '') || ' ' || coalesce(capture ->> 'sourceLabel', ''))
);

-- Preserve the existing private, SECURITY INVOKER function signature and grants.
create or replace function ihear.search_patients(
  p_workspace_id uuid,
  p_query text default null,
  p_status text default null,
  p_difficulty text default null,
  p_follow_up text default null
)
returns table (
  id uuid, workspace_id uuid, display_name text, audiogram jsonb, aids jsonb,
  follow_up_date date, note text, timezone text, profile_version integer,
  report_revision bigint, created_at timestamptz, updated_at timestamptz,
  event_count bigint, latest_status text
)
language sql
stable
set search_path = ''
as $$
  with input as (
    select case
      -- Explicit phrases, OR and exclusions retain web-search semantics.
      when p_query ~* '"|(^|[[:space:]])or([[:space:]]|$)|(^|[[:space:]])-[^[:space:]]'
        then websearch_to_tsquery('ihear.patient_search', p_query)
      -- Tokenize before quoting: punctuation can never become a query operator.
      else to_tsquery('ihear.patient_search', coalesce((
        select string_agg(quote_literal(token) || ':*', ' & ')
        from unnest(tsvector_to_array(to_tsvector('ihear.patient_search', p_query))) as token
      ), ''))
    end as terms
  )
  select p.id, p.workspace_id, p.display_name, p.audiogram, p.aids,
    p.follow_up_date, p.note, p.timezone, p.profile_version, p.report_revision,
    p.created_at, p.updated_at,
    count(e.id) as event_count,
    (array_agg(e.status order by e.captured_at desc) filter (where e.id is not null))[1] as latest_status
  from ihear.patients p
  cross join input
  left join ihear.events e on e.patient_id = p.id and e.workspace_id = p.workspace_id
  where p.workspace_id = p_workspace_id
    and (
      nullif(btrim(coalesce(p_query, '')), '') is null
      or to_tsvector('ihear.patient_search', coalesce(p.display_name, '') || ' ' || coalesce(p.note, '')) @@ input.terms
      or exists (
        select 1 from ihear.events se
        where se.patient_id = p.id and se.workspace_id = p.workspace_id
          and to_tsvector('ihear.patient_search', coalesce(se.kind, '') || ' ' || coalesce(se.difficulty, '') || ' ' ||
            coalesce(se.environment, '') || ' ' || coalesce(se.capture ->> 'sourceLabel', '')) @@ input.terms
      )
    )
    and (p_status is null or exists (
      select 1 from ihear.events fs where fs.patient_id = p.id and fs.workspace_id = p.workspace_id and fs.status = p_status
    ))
    and (p_difficulty is null or exists (
      select 1 from ihear.events fd where fd.patient_id = p.id and fd.workspace_id = p.workspace_id and fd.difficulty = p_difficulty
    ))
    and case
      when p_follow_up is null then true
      when p_follow_up = 'overdue' then p.follow_up_date < current_date
      when p_follow_up = 'today' then p.follow_up_date = current_date
      when p_follow_up = 'upcoming' then p.follow_up_date > current_date
      when p_follow_up ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then p.follow_up_date = p_follow_up::date
      else false
    end
  group by p.id
  order by p.updated_at desc, p.id;
$$;
