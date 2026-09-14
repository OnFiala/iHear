export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError("Couldn’t connect. Check your connection or reload this page, then try again.", 0);
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("Couldn’t read the response. Reload this page to reconnect, then try again.", response.ok ? 502 : response.status);
  }
  if (!response.ok)
    throw new ApiError(
      typeof body?.error === "string" ? body.error : "Something went wrong. Please try again.",
      response.status,
    );
  return body as T;
}
export function dateLabel(value: string) {
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(value.length === 10 ? value + "T12:00:00" : value));
}
