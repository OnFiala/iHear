import test from "node:test";
import assert from "node:assert/strict";
import pg from "pg";
import { createClient } from "@supabase/supabase-js";
import { execFileSync } from "node:child_process";

const enabled = process.env.RUN_LIVE_SUPABASE_SECURITY === "1";

test(
  "live anon role is denied private database and Storage access",
  { skip: !enabled },
  async (context) => {
    let local: Record<string, string> = {};
    try {
      const output = execFileSync(
        "pnpm",
        ["exec", "supabase", "status", "-o", "env"],
        {
          encoding: "utf8",
          env: process.env,
          stdio: ["ignore", "pipe", "ignore"],
        },
      );
      local = Object.fromEntries(
        output.split("\n").flatMap((line) => {
          const match = line.match(/^([A-Z0-9_]+)="(.*)"$/);
          return match ? [[match[1], match[2]]] : [];
        }),
      );
    } catch {
      throw new Error("Local Supabase status is unavailable.");
    }
    const url =
      process.env.SUPABASE_URL ??
      process.env.NEXT_PUBLIC_SUPABASE_URL ??
      local.API_URL;
    const anonKey =
      process.env.SUPABASE_ANON_KEY ??
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ??
      process.env.SUPABASE_PUBLISHABLE_KEY ??
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
      local.ANON_KEY ??
      local.PUBLISHABLE_KEY;
    const databaseUrl =
      process.env.DATABASE_URL ??
      local.DB_URL ??
      "postgresql://postgres:postgres@127.0.0.1:54322/postgres";
    if (!url || !anonKey || !databaseUrl)
      throw new Error(
        "Live Supabase security test configuration is incomplete.",
      );
    const supabase = createClient(url, anonKey, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const existingObject = async () => {
      const database = new pg.Client({ connectionString: databaseUrl });
      await database.connect();
      try {
        return (
          (
            await database.query<{ bucket_id: string; name: string }>(`
        select bucket_id, name from storage.objects
        where bucket_id in ('ihear-audio', 'ihear-reports')
        order by created_at desc limit 1
      `)
          ).rows[0] ?? null
        );
      } finally {
        await database.end();
      }
    };

    await context.test(
      "anon cannot select the private ihear schema",
      async () => {
        const { data, error } = await supabase
          .schema("ihear")
          .from("patients")
          .select("id")
          .limit(1);
        assert.ok(
          error && data === null,
          "Unexpected anonymous database read access.",
        );
      },
    );

    await context.test(
      "anon cannot insert into the private ihear schema",
      async () => {
        const { data, error } = await supabase
          .schema("ihear")
          .from("workspaces")
          .insert({})
          .select("id");
        assert.ok(
          error && data === null,
          "Unexpected anonymous database write access.",
        );
      },
    );

    await context.test(
      "anon cannot list an existing private object",
      async (storageContext) => {
        const object = await existingObject();
        if (!object)
          return storageContext.skip(
            "No existing private object was available.",
          );
        const segments = object.name.split("/");
        const objectName = segments.pop();
        const { data, error } = await supabase.storage
          .from(object.bucket_id)
          .list(segments.join("/"), { limit: 100 });
        assert.ok(
          error || !data?.some((entry) => entry.name === objectName),
          "Unexpected anonymous Storage list access.",
        );
      },
    );

    await context.test("anon cannot upload to a private bucket", async () => {
      const { data, error } = await supabase.storage
        .from("ihear-audio")
        .upload("_security_probe/deny.wav", new Uint8Array([0]), {
          contentType: "audio/wav",
          upsert: false,
        });
      assert.ok(
        error && data === null,
        "Unexpected anonymous Storage upload access.",
      );
    });

    await context.test(
      "anon cannot download an existing private object",
      async (storageContext) => {
        const object = await existingObject();
        if (!object)
          return storageContext.skip(
            "No existing private object was available.",
          );
        const { data, error } = await supabase.storage
          .from(object.bucket_id)
          .download(object.name);
        assert.ok(
          error && data === null,
          "Unexpected anonymous Storage download access.",
        );
      },
    );
  },
);
