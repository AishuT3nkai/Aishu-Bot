import { NextResponse } from "next/server";
import { readLoginState, clearSession, authorizedAdminIds, saveSession } from "@/lib/auth";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const expectedState = await readLoginState();

  if (!code || !state || !expectedState || state !== expectedState) {
    return NextResponse.json({ error: "Invalid OAuth state." }, { status: 400 });
  }

  const clientId = process.env.DISCORD_CLIENT_ID;
  const clientSecret = process.env.DISCORD_CLIENT_SECRET;
  const redirectUri = process.env.DISCORD_REDIRECT_URI;
  const adminGuildId = process.env.ADMIN_GUILD_ID;

  if (!clientId || !clientSecret || !redirectUri || !adminGuildId) {
    return NextResponse.json({ error: "Dashboard OAuth is not fully configured." }, { status: 500 });
  }

  const tokenResponse = await fetch("https://discord.com/api/v10/oauth2/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri,
    }),
    cache: "no-store",
  });

  if (!tokenResponse.ok) {
    return NextResponse.json({ error: "Discord OAuth token exchange failed." }, { status: 401 });
  }

  const token = (await tokenResponse.json()) as { access_token?: string };
  if (!token.access_token) {
    return NextResponse.json({ error: "Discord did not return an access token." }, { status: 401 });
  }

  const headers = { Authorization: "Bearer " + token.access_token };

  const [userResponse, guildsResponse] = await Promise.all([
    fetch("https://discord.com/api/v10/users/@me", { headers, cache: "no-store" }),
    fetch("https://discord.com/api/v10/users/@me/guilds", { headers, cache: "no-store" }),
  ]);

  if (!userResponse.ok || !guildsResponse.ok) {
    return NextResponse.json({ error: "Could not read Discord account information." }, { status: 401 });
  }

  const user = (await userResponse.json()) as {
    id: string;
    username: string;
    avatar?: string | null;
  };
  const guilds = (await guildsResponse.json()) as Array<{ id: string }>;

  const admins = authorizedAdminIds();
  const isAdmin = admins.includes(user.id);
  const inAdminGuild = guilds.some((guild) => guild.id === adminGuildId);

  if (!isAdmin || !inAdminGuild) {
    await clearSession();
    return new NextResponse(
      "<!doctype html><html><body style='font-family:sans-serif;padding:40px'><h1>Access denied</h1><p>This dashboard is restricted to the authorized Aishu administrators.</p></body></html>",
      { status: 403, headers: { "Content-Type": "text/html; charset=utf-8" } },
    );
  }

  await saveSession({
    id: user.id,
    username: user.username,
    avatar: user.avatar,
    exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7,
  });

  const response = NextResponse.redirect(new URL("/dashboard", request.url));
  response.headers.append("Set-Cookie", "aishu_oauth_state=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax");
  return response;
}
