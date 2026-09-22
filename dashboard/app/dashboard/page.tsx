import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";

const sections = [
  ["Welcome", "Welcome channel, message and join cards"],
  ["Goodbye", "Leave messages and departure handling"],
  ["Verification", "Account-age rules, roles and verification panel"],
  ["Moderation", "Logs, moderation defaults and safety settings"],
  ["Tickets", "Ticket category, support role and panel settings"],
  ["Auto Role", "Role assignment for new members"],
  ["Birthday", "Birthday announcement channel and settings"],
  ["Suggestions", "Suggestion channel and review workflow"],
  ["Reports", "Private report destination and moderation flow"],
];

export default async function DashboardPage() {
  const session = await getSession();
  if (!session) redirect("/");

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">AISHU BOT</div>
        <nav className="nav">
          <a href="/dashboard">Overview</a>
          <a href="/dashboard/verification">Verification</a>
          <a href="/dashboard/moderation">Moderation</a>
          <a href="/dashboard/community">Community</a>
          <a href="/dashboard/tickets">Tickets</a>
          <a href="/dashboard/settings">Settings</a>
        </nav>
        <div style={{ position: "absolute", bottom: 22, left: 16, right: 16 }}>
          <form action="/api/auth/logout" method="post">
            <button className="btn secondary" style={{ width: "100%" }} type="submit">
              Sign out
            </button>
          </form>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div>
            <div className="kicker">Private admin panel</div>
            <h1>Overview</h1>
          </div>
          <div className="muted">{session.username}</div>
        </div>

        <div className="grid">
          {sections.map(([title, description]) => (
            <section className="card" key={title}>
              <h2>{title}</h2>
              <p className="muted">{description}</p>
              <div className="row" style={{ marginTop: 18 }}>
                <span className="stat">—</span>
                <span className="muted">Awaiting bot bridge</span>
              </div>
            </section>
          ))}
        </div>

        <section className="card" style={{ marginTop: 16 }}>
          <h2>Access control</h2>
          <p className="muted">
            This dashboard accepts only the two Discord user IDs configured in the server environment,
            and also requires the user to belong to the configured admin server.
          </p>
        </section>
      </main>
    </div>
  );
}
