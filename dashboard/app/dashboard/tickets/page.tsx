import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";

export default async function TicketsPage() {
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
      </aside>
      <main className="main">
        <div className="kicker">Private admin panel</div>
        <h1>Tickets</h1>
        <section className="card" style={{ marginTop: 24 }}>
          <h2>Tickets controls</h2>
          <p className="muted">
            The secure dashboard page is ready. Bot API wiring will connect these controls to the live Discord configuration.
          </p>
        </section>
      </main>
    </div>
  );
}
