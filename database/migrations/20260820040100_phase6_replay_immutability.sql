begin;

update vigia.replay_cases set frozen = true where not frozen;
alter table vigia.replay_cases alter column frozen set default true;

create or replace function vigia.prevent_frozen_replay_case_update()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.frozen and (to_jsonb(new) - 'updated_at') is distinct from
    (to_jsonb(old) - 'updated_at') then
    raise exception 'ReplayCase congelado: el manifest y sus campos no pueden cambiar';
  end if;
  return new;
end;
$$;

drop trigger if exists replay_cases_immutable_when_frozen on vigia.replay_cases;
create trigger replay_cases_immutable_when_frozen
before update on vigia.replay_cases
for each row execute function vigia.prevent_frozen_replay_case_update();

revoke all on function vigia.prevent_frozen_replay_case_update()
from public, anon, authenticated;

commit;
