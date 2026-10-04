/**
 * Auth: HS256 JWT compatible with the Python side, plus password hashing.
 *
 * The token format matches app/core/security.py exactly (sub / type / iat /
 * exp, HS256) so a token minted by either runtime is accepted by the other.
 */

const SECRET = Deno.env.get("SECRET_KEY") ?? "";
const ACCESS_TTL_MINUTES = Number(
  Deno.env.get("ACCESS_TOKEN_TTL_MINUTES") ?? 30,
);
const REFRESH_TTL_DAYS = Number(
  Deno.env.get("REFRESH_TOKEN_TTL_DAYS") ?? 30,
);

function b64url(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlToBytes(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

async function hmacKey(): Promise<CryptoKey> {
  return await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export interface Claims {
  sub: string;
  type: string;
  iat: number;
  exp: number;
}

export async function signToken(
  subject: string,
  type: "access" | "refresh",
): Promise<string> {
  if (!SECRET) throw new Error("SECRET_KEY is not set on the edge function");

  const now = Math.floor(Date.now() / 1000);
  const ttl = type === "access"
    ? ACCESS_TTL_MINUTES * 60
    : REFRESH_TTL_DAYS * 86400;

  const header = b64url(new TextEncoder().encode(JSON.stringify({
    alg: "HS256",
    typ: "JWT",
  })));
  const payload = b64url(new TextEncoder().encode(JSON.stringify({
    sub: subject,
    type,
    iat: now,
    exp: now + ttl,
  })));

  const key = await hmacKey();
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(`${header}.${payload}`),
  );

  return `${header}.${payload}.${b64url(new Uint8Array(signature))}`;
}

export async function verifyToken(token: string): Promise<Claims | null> {
  if (!SECRET) return null;

  const parts = token.split(".");
  if (parts.length !== 3) return null;

  const [header, payload, signature] = parts;
  const key = await hmacKey();
  const valid = await crypto.subtle.verify(
    "HMAC",
    key,
    b64urlToBytes(signature),
    new TextEncoder().encode(`${header}.${payload}`),
  );
  if (!valid) return null;

  try {
    const claims = JSON.parse(
      new TextDecoder().decode(b64urlToBytes(payload)),
    ) as Claims;
    if (typeof claims.exp !== "number" || claims.exp * 1000 < Date.now()) {
      return null;
    }
    return claims;
  } catch {
    return null;
  }
}

/** Extract the bearer token from a request, or null. */
export function bearerFrom(request: Request): string | null {
  const header = request.headers.get("Authorization");
  if (header?.startsWith("Bearer ")) return header.slice(7);
  const cookie = request.headers.get("Cookie") ?? "";
  const match = cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Password hashing.
 *
 * bcrypt lives in the Python service; here we use PBKDF2-HMAC-SHA256 from
 * WebCrypto, which needs no wasm dependency and is deliberately slow.
 */
const PBKDF2_ITERATIONS = 120000;

export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const derived = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt: salt as unknown as BufferSource,
      iterations: PBKDF2_ITERATIONS,
      hash: "SHA-256",
    },
    await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(password),
      "PBKDF2",
      false,
      ["deriveBits"],
    ),
    256,
  );

  return [
    "pbkdf2_sha256",
    PBKDF2_ITERATIONS,
    b64url(salt),
    b64url(new Uint8Array(derived)),
  ].join("$");
}

export async function verifyPassword(
  password: string,
  stored: string,
): Promise<boolean> {
  // Google-only accounts get this placeholder and can never use a password.
  if (stored.startsWith("oauth:")) return false;

  const parts = stored.split("$");
  if (parts.length !== 4 || parts[0] !== "pbkdf2_sha256") return false;

  const iterations = Number(parts[1]);
  const salt = b64urlToBytes(parts[2]);
  const expected = b64urlToBytes(parts[3]);

  const derived = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt: salt as unknown as BufferSource,
      iterations,
      hash: "SHA-256",
    },
    await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(password),
      "PBKDF2",
      false,
      ["deriveBits"],
    ),
    256,
  );

  const actual = new Uint8Array(derived);
  if (actual.length !== expected.length) return false;

  let diff = 0;
  for (let i = 0; i < actual.length; i += 1) diff |= actual[i] ^ expected[i];
  return diff === 0;
}