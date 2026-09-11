alter table ihear.budget_accounts
  add column frozen_at timestamptz,
  add column freeze_reason text,
  add constraint budget_freeze_pair_check check (
    (frozen_at is null and freeze_reason is null)
    or (frozen_at is not null and nullif(btrim(freeze_reason), '') is not null)
  );

create or replace function ihear.reserve_api_budget(
  p_workspace_id uuid,
  p_patient_id uuid,
  p_event_id uuid,
  p_job_id uuid,
  p_kind text,
  p_model text,
  p_maximum_cost_usd numeric,
  p_idempotency_key text,
  p_ambiguous boolean default false,
  p_now timestamptz default now()
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_account ihear.budget_accounts%rowtype;
  v_existing ihear.api_usage%rowtype;
  v_usage_id uuid;
  v_timezone text;
  v_usage_day date;
  v_patient_day date;
  v_total numeric := 0;
  v_daily numeric := 0;
  v_event_count integer := 0;
begin
  if p_ambiguous then return jsonb_build_object('status', 'held_ambiguity'); end if;
  if p_maximum_cost_usd <= 0 then raise exception 'invalid_budget_reservation' using errcode = '22023'; end if;
  if p_kind = 'event_interpretation' and not exists (
    select 1 from ihear.events where id = p_event_id and workspace_id = p_workspace_id and patient_id = p_patient_id
  ) then raise exception 'event_not_found' using errcode = 'P0002'; end if;

  select * into v_account from ihear.budget_accounts
  where account_key = 'astra-global' for update;
  if not found then raise exception 'budget_account_not_found' using errcode = 'P0002'; end if;
  if v_account.frozen_at is not null then return jsonb_build_object('status', 'held_budget_frozen'); end if;
  select timezone into v_timezone from ihear.patients
  where id = p_patient_id and workspace_id = p_workspace_id;
  if not found then raise exception 'patient_not_found' using errcode = 'P0002'; end if;

  select * into v_existing from ihear.api_usage
  where workspace_id = p_workspace_id and idempotency_key = p_idempotency_key;
  if found then
    return jsonb_build_object('status', 'existing', 'usageId', v_existing.id, 'state', v_existing.state);
  end if;

  v_usage_day := (p_now at time zone v_account.budget_timezone)::date;
  v_patient_day := (p_now at time zone v_timezone)::date;
  select coalesce(sum(case when state = 'settled' then actual_usd else reserved_usd end), 0)
    into v_total from ihear.api_usage where state in ('reserved', 'settled');
  select coalesce(sum(case when state = 'settled' then actual_usd else reserved_usd end), 0)
    into v_daily from ihear.api_usage
    where usage_day = v_usage_day and state in ('reserved', 'settled');

  if v_total + p_maximum_cost_usd > v_account.total_limit_usd
    or v_daily + p_maximum_cost_usd > v_account.daily_limit_usd then
    return jsonb_build_object('status', 'held_budget');
  end if;

  if p_kind = 'event_interpretation' then
    select count(distinct event_id) into v_event_count from ihear.api_usage
    where patient_id = p_patient_id and patient_day = v_patient_day
      and kind = 'event_interpretation' and state in ('reserved', 'settled');
    if v_event_count >= 5 then return jsonb_build_object('status', 'held_event_limit'); end if;
  end if;

  insert into ihear.api_usage (
    workspace_id, patient_id, event_id, job_id, kind, usage_day, patient_day, state,
    reserved_usd, model, idempotency_key
  ) values (
    p_workspace_id, p_patient_id, p_event_id, p_job_id, p_kind, v_usage_day, v_patient_day,
    'reserved', p_maximum_cost_usd, p_model, p_idempotency_key
  ) returning id into v_usage_id;
  return jsonb_build_object('status', 'reserved', 'usageId', v_usage_id);
end;
$$;

create function ihear.settle_api_budget_overage(
  p_usage_id uuid,
  p_actual_cost_usd numeric,
  p_provider_request_id text,
  p_reason text
)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_usage ihear.api_usage%rowtype;
begin
  if nullif(btrim(p_reason), '') is null or char_length(p_reason) > 500 then
    raise exception 'invalid_budget_freeze_reason' using errcode = '22023';
  end if;
  select u.* into v_usage from ihear.api_usage u
  cross join ihear.budget_accounts b
  where u.id = p_usage_id and b.account_key = 'astra-global'
  for update of b, u;
  if not found then raise exception 'budget_reservation_not_found' using errcode = 'P0002'; end if;
  if v_usage.state = 'settled' and v_usage.actual_usd = p_actual_cost_usd then return; end if;
  if v_usage.state <> 'reserved' or p_actual_cost_usd <= v_usage.reserved_usd then
    raise exception 'invalid_budget_overage' using errcode = 'P0001';
  end if;
  update ihear.api_usage
  set state = 'settled', actual_usd = p_actual_cost_usd,
      provider_request_id = p_provider_request_id, settled_at = now()
  where id = p_usage_id;
  update ihear.budget_accounts
  set frozen_at = coalesce(frozen_at, now()),
      freeze_reason = coalesce(freeze_reason, p_reason)
  where account_key = 'astra-global';
end;
$$;

revoke all on function ihear.settle_api_budget_overage(uuid, numeric, text, text) from public, anon, authenticated;
grant execute on function ihear.settle_api_budget_overage(uuid, numeric, text, text) to service_role;
