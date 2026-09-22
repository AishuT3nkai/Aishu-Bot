import crypto from "node:crypto";
import { cookies } from "next/headers";

const SESSION_COOKIE = "aishu_dashboard_session";
const STATE_COOKIE = "aishu_oauth_state";

type Session = {
  id: string;
  username: string;
  avatar?: string | null;
  exp: number;
};

function secret() {
  const value = process.env.DASHBOARD_SESSION_SECRET;
  if (!value || value.length < 32) {
    throw new Error("DASHBOARD_SESSION_SECRET must be at least 32 characters.");
  }
  return value;
}

function encode(value: string) {
  return Buffer.from(value).toString("base64url");
}

function decode(value: string) {
  return Buffer.from(value, "base64url").toString("utf8");
}

function sign(value: string) {
  return crypto.createHmac("sha256", secret()).update(value).digest("base64url");
}

function serialize(session: Session) {
  const payload = encode(JSON.stringify(session));
  return payload + "." + sign(payload);
}

function parse(value: string): Session | null {
  const [payload, signature] = value.split(".");
  if (!payload || !signature) return null;

  const expected = sign(payload);
  const a = Buffer.from(signature);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;

  try {
    const session = JSON.parse(decode(payload)) as Session;
    if (!session.exp || session.exp < Math.floor(Date.now() / 1000)) return null;
    return session;
  } catch {
    return null;
  }
}

export function authorizedAdminIds() {
  return [process.env.ADMIN_USER_ID_1, process.env.ADMIN_USER_ID_2].filter(
    (id): id is string => Boolean(id && /^\d+$/.test(id)),
  );
}

export function clearAuthStateOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    maxAge: 0,
    path: "/",
  };
}

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 24 * 7,
    path: "/",
  };
}

export async function getSession(): Promise<Session | null> {
  const cookieStore = await cookies();
  const value = cookieStore.get(SESSION_COOKIE)?.value;
  return value ? parse(value) : null;
}

export async function startLoginState() {
  const state = crypto.randomBytes(24).toString("base64url");
  const cookieStore = await cookies();
  cookieStore.set(STATE_COOKIE, state, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 600,
    path: "/",
  });
  return state;
}

export async function readLoginState() {
  const cookieStore = await cookies();
  return cookieStore.get(STATE_COOKIE)?.value ?? null;
}

export async function saveSession(session: Session) {
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, serialize(session), sessionCookieOptions());
}

export async function clearSession() {
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, "", clearAuthStateOptions());
  cookieStore.set(STATE_COOKIE, "", clearAuthStateOptions());
}
