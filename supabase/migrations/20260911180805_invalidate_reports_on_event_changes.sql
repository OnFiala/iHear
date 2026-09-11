create trigger event_report_revision_insert_delete_trigger
after insert or delete on ihear.events
for each row execute function ihear.bump_report_revision();

create trigger event_report_revision_update_trigger
after update of kind, difficulty, environment, captured_at, capture, profile_snapshot, status, error on ihear.events
for each row when (
  old.kind is distinct from new.kind
  or old.difficulty is distinct from new.difficulty
  or old.environment is distinct from new.environment
  or old.captured_at is distinct from new.captured_at
  or old.capture is distinct from new.capture
  or old.profile_snapshot is distinct from new.profile_snapshot
  or old.status is distinct from new.status
  or old.error is distinct from new.error
)
execute function ihear.bump_report_revision();
