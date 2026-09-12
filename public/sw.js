/* Only cache public shells and static assets. APIs, pairing links and recordings never enter Cache Storage. */
const CACHE = "ihear-shell-v3";
const SHELL = [
  "/app",
  "/app/pair",
  "/pcm-worklet.js",
  "/manifest.webmanifest",
  "/icon.svg",
  "/app-icon.png",
];
async function installShell() {
  const cache = await caches.open(CACHE);
  await cache.addAll(SHELL);
  const assets = new Set();
  for (const route of ["/app", "/app/pair"]) {
    const html = await (await cache.match(route)).text();
    for (const match of html.matchAll(
      /(?:src|href)="([^" ]*\/_next\/static\/[^" ]+)"/g,
    )) {
      const url = new URL(
        match[1].replaceAll("&amp;", "&"),
        self.location.origin,
      );
      if (url.origin === self.location.origin) assets.add(url.href);
    }
  }
  await cache.addAll([...assets]);
  for (const asset of assets) {
    if (!new URL(asset).pathname.endsWith(".css")) continue;
    const css = await (await cache.match(asset)).text();
    const fonts = [];
    for (const match of css.matchAll(/url\(["']?([^"')]+)["']?\)/g)) {
      const url = new URL(match[1], asset);
      if (
        url.origin === self.location.origin &&
        url.pathname.startsWith("/_next/static/")
      )
        fonts.push(url.href);
    }
    await cache.addAll([...new Set(fonts)]);
  }
  await self.skipWaiting();
}
self.addEventListener("install", (event) => {
  event.waitUntil(installShell());
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("ihear-shell-") && k !== CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (
    event.request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/pair/")
  )
    return;
  if (
    !url.pathname.startsWith("/_next/static/") &&
    !SHELL.includes(url.pathname)
  )
    return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          void caches.open(CACHE).then((c) => c.put(event.request, copy));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) return cached;
        if (event.request.mode === "navigate")
          return (await caches.match("/app")) || Response.error();
        return Response.error();
      }),
  );
});
