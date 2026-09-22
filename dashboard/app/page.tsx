export default function Home() {
  return (
    <main className="login">
      <section className="login-card">
        <div className="kicker">Aishu Community</div>
        <h1>Aishu Dashboard</h1>
        <p className="muted">
          Private administration panel for the Aishu Discord Community bot.
        </p>
        <div style={{ height: 18 }} />
        <a className="btn" href="/api/auth/login">Continue with Discord</a>
        <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>
          Access is limited by Discord user ID and the configured admin server.
        </p>
      </section>
    </main>
  );
}
