import 'server-only';
import { Pool, type PoolClient, type QueryResultRow } from 'pg';

let pool: Pool | undefined;

function databaseUrl(): string {
  const value = process.env.DATABASE_URL;
  if (!value) throw new Error('DATABASE_URL is not configured.');
  return value;
}

function poolMaximum(): number {
  const value = Number(process.env.DATABASE_POOL_MAX ?? '3');
  if (!Number.isSafeInteger(value) || value < 1 || value > 10) throw new Error('DATABASE_POOL_MAX must be an integer from 1 to 10.');
  return value;
}

export function db(): Pool {
  pool ??= new Pool({
    connectionString: databaseUrl(),
    max: poolMaximum(),
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 10_000,
  });
  return pool;
}

export async function query<T extends QueryResultRow>(text: string, values: unknown[] = []): Promise<T[]> {
  return (await db().query<T>(text, values)).rows;
}

export async function transaction<T>(run: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await db().connect();
  try {
    await client.query('begin');
    const result = await run(client);
    await client.query('commit');
    return result;
  } catch (error) {
    await client.query('rollback');
    throw error;
  } finally {
    client.release();
  }
}
