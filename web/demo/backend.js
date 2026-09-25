const SERVER_PATHS = ["/editor/api/", "/admin/", "/api/"];

export const servedByDemo = (url, pageUrl) =>
  url.origin === new URL(pageUrl).origin &&
  SERVER_PATHS.some((prefix) => url.pathname.startsWith(prefix));

export function createDemoFetch(worker, nativeFetch, pageUrl) {
  const pending = new Map();
  let nextId = 0;
  let unreachable = null;

  worker.addEventListener("message", ({ data }) => {
    if (data.type !== "response" || !pending.has(data.id)) return;
    const { resolve, reject } = pending.get(data.id);
    pending.delete(data.id);
    if (data.error) reject(new TypeError(data.error));
    else resolve(new Response(data.body, { status: data.status, headers: data.headers }));
  });

  worker.addEventListener("error", () => {
    unreachable = new TypeError("Serveur de démo indisponible.");
    for (const { reject } of pending.values()) reject(unreachable);
    pending.clear();
  });

  return async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input), pageUrl);
    if (!servedByDemo(url, pageUrl)) return nativeFetch(input, init);
    if (unreachable) throw unreachable;

    const request = new Request(input instanceof Request ? input : url, init);
    const body = ["GET", "HEAD"].includes(request.method) ? "" : await request.text();
    const id = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      worker.postMessage({
        type: "request",
        id,
        request: {
          method: request.method,
          url: url.pathname + url.search,
          headers: [...request.headers],
          body,
        },
      });
    });
  };
}
