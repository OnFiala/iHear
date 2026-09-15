import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import pg from "pg";

test("directory search finds partial and accent-free words with exact filters and tenant isolation", async () => {
  const connectionString = process.env.DATABASE_URL ?? "postgresql://postgres:postgres@127.0.0.1:54322/postgres";
  assert.ok(["127.0.0.1", "localhost"].includes(new URL(connectionString).hostname), "Run only against the local test database.");
  const client = new pg.Client({ connectionString });
  await client.connect();
  await client.query("begin");
  try {
    const workspace = randomUUID(), otherWorkspace = randomUUID();
    await client.query("insert into ihear.workspaces(id) values ($1), ($2)", [workspace, otherWorkspace]);
    const profile = { frequencies: [500], left: [20], right: [25] };
    const aids = { side: "bilateral", left: { model: "Example", tier: "110" }, right: { model: "Example", tier: "110" } };
    const insert = async (owner: string, name: string, note: string) => (await client.query(
      "insert into ihear.patients(workspace_id, display_name, audiogram, aids, follow_up_date, note) values ($1, $2, $3, $4, '2026-09-20', $5) returning id",
      [owner, name, profile, aids, note],
    )).rows[0].id as string;
    const jana = await insert(workspace, "Jana Nováková", "Synthetic café conversation");
    const robert = await insert(workspace, "Robert McDough", "Synthetic garden visit");
    const foreign = await insert(otherWorkspace, "Jana Nováková", "Synthetic café conversation");
    await client.query(`insert into ihear.events(id, workspace_id, patient_id, kind, difficulty, environment, captured_at, capture, profile_snapshot, profile_version, audio_object_path, audio_sha256, request_fingerprint, audio_bytes, duration_seconds, pipeline_version, status)
      values ($1, $2, $3, 'difficult', 'Several people talking', 'Music or TV', now(), '{"sourceLabel":"Phone microphone"}', $4, 1, $5, $6, $7, 32044, 1, 1, 'ready')`,
      [randomUUID(), workspace, robert, { displayName: "Robert McDough", audiogram: profile, aids }, `explicit-test/${randomUUID()}.wav`, Buffer.alloc(32, 2), Buffer.alloc(32, 3)]);
    const search = async (q: string, owner = workspace, status: string | null = null, difficulty: string | null = null, date: string | null = null) => (await client.query(
      "select id, event_count from ihear.search_patients($1,$2,$3,$4,$5)", [owner, q, status, difficulty, date],
    )).rows;
    for (const q of ["jan nov", "NOVAK", "Jana Nováková", "cafe", "café", "caf"]) {
      assert.deepEqual((await search(q)).map((p) => p.id), [jana], q);
    }
    for (const q of ["Rob", "mcdo", "gard", "MUS", "sever peop", "micro", "Robert: McDough"]) {
      assert.deepEqual((await search(q)).map((p) => p.id), [robert], q);
    }
    assert.equal((await search("mus"))[0].event_count, "1");
    assert.equal((await search("jan", otherWorkspace))[0].id, foreign);
    assert.equal((await search("rob", otherWorkspace)).length, 0);
    assert.equal((await search("gar", workspace, "ready", "Several people talking", "2026-09-20")).length, 1);
    assert.equal((await search("gar", workspace, "failed")).length, 0);
    assert.equal((await search("gar", workspace, null, "Following one person")).length, 0);
    assert.equal((await search("gar", workspace, null, null, "2026-09-21")).length, 0);
    const today = (await client.query("select current_date::text as value")).rows[0].value;
    await client.query("update ihear.patients set follow_up_date = current_date where id = $1", [jana]);
    assert.equal((await search("jan", workspace, null, null, "today")).length, 1);
    assert.equal((await search("jan", workspace, null, null, today)).length, 1);
    assert.equal((await search("jan", workspace, null, null, "overdue")).length, 0);
    assert.equal((await search("jan", workspace, null, null, "upcoming")).length, 0);
    assert.equal((await search('"café conversation"')).length, 1);
    assert.equal((await search('"conversation café"')).length, 0);
    assert.equal((await search("Jana OR Robert")).length, 2);
    assert.equal((await search("Jana -cafe")).length, 0);
    for (const q of ["missingword", "!!!", "' ; DROP TABLE ihear.patients; --"]) assert.equal((await search(q)).length, 0, q);
    assert.equal((await search(" ")).length, 2);
    for (const role of ["anon", "authenticated"]) {
      await client.query("savepoint role_denial");
      await client.query(`set local role ${role}`);
      await assert.rejects(search("jan"), /permission denied/);
      await client.query("rollback to savepoint role_denial");
    }
  } finally {
    await client.query("rollback");
    await client.end();
  }
});
