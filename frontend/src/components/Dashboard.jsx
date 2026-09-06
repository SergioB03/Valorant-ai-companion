import { useEffect, useRef, useState } from "react";
import { getAccount, getMatches, isDemoMode } from "../api.js";
import { relativeDate } from "../utils.js";
import { ErrorBanner, EmptyState, Skeleton, CopyLinkButton } from "./common.jsx";
import AnimatedNumber from "./AnimatedNumber.jsx";
import { useGSAP, revealStagger, revealIn } from "../anim.js";
import { track } from "../analytics.js";

function computeStats(matches) {
  if (!matches || matches.length === 0) return null;
  const wins = matches.filter((m) => m.won).length;
  const sum = (key) => matches.reduce((acc, m) => acc + (m[key] || 0), 0);
  const kills = sum("kills");
  const deaths = sum("deaths");
  const assists = sum("assists");
  const hs =
    matches.reduce((acc, m) => acc + (m.headshot_percent || 0), 0) /
    matches.length;
  return {
    winRate: Math.round((wins / matches.length) * 100),
    kda: ((kills + assists) / Math.max(1, deaths)).toFixed(2),
    hs: hs.toFixed(1),
    count: matches.length,
    wins,
  };
}

function StatTile({ label, value, suffix }) {
  // Entrance is a GSAP stagger driven by the parent grid; the value counts up
  // via <AnimatedNumber>. Both no-op under prefers-reduced-motion.
  return (
    <div className="stat-tile">
      <span className="stat-value">
        <AnimatedNumber value={value} />
        {suffix ? <small>{suffix}</small> : null}
      </span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

function MatchRow({ m }) {
  return (
    <li className={`match-row ${m.won ? "win" : "loss"}`}>
      <span className={`wl ${m.won ? "win" : "loss"}`}>
        {m.won ? "W" : "L"}
      </span>
      <div className="match-main">
        <span className="match-agent">{m.agent || "Unknown"}</span>
        <span className="match-map">
          {m.map || "?"} · {m.mode || "?"}
        </span>
      </div>
      <span className="match-kda" title="Kills / Deaths / Assists">
        {m.kills}/{m.deaths}/{m.assists}
      </span>
      <span className="match-hs">{m.headshot_percent}% HS</span>
      <span className="match-date">{relativeDate(m.started_at)}</span>
    </li>
  );
}

function DashboardSkeleton() {
  return (
    <div className="stack">
      <section className="panel">
        <div className="account-body">
          <Skeleton width={64} height={64} />
          <div className="stack-sm" style={{ flex: 1 }}>
            <Skeleton width="40%" height={22} />
            <Skeleton width="60%" height={14} />
          </div>
        </div>
      </section>
      <div className="stat-grid">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="stat-tile">
            <Skeleton width="50%" height={28} />
            <Skeleton width="70%" height={12} />
          </div>
        ))}
      </div>
      <section className="panel">
        <div className="stack-sm">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} height={40} />
          ))}
        </div>
      </section>
    </div>
  );
}

export default function Dashboard({ player }) {
  const [state, setState] = useState({
    loading: false,
    error: null,
    account: null,
    matches: null,
  });
  const [reloadKey, setReloadKey] = useState(0);
  // Dashboard remounts per player (keyed wrapper in App), so this fires
  // player_search once per searched player — retries don't re-count.
  const searchTracked = useRef(false);
  const scope = useRef(null);

  // Entrance choreography: the account card leads, then the stat tiles and
  // match rows cascade. Re-runs whenever a load finishes (loading -> data).
  // Declared before the early returns below so hook order stays stable.
  useGSAP(
    () => {
      revealIn(scope.current?.querySelector(".account-card"));
      revealStagger(scope.current, ".stat-tile", { delay: 0.08 });
      revealStagger(scope.current, ".match-row", { delay: 0.16, y: 10 });
    },
    { scope, dependencies: [state.loading, state.account, state.matches] },
  );

  useEffect(() => {
    if (!player) return;
    let alive = true;
    // Abort on unmount/player switch — no point finishing a fetch whose
    // results will be thrown away (and it frees the backend's rate budget).
    const controller = new AbortController();
    setState({ loading: true, error: null, account: null, matches: null });
    Promise.allSettled([
      getAccount(player.name, player.tag, { signal: controller.signal }),
      getMatches(player.name, player.tag, player.region, 10, {
        signal: controller.signal,
      }),
    ]).then(([accountRes, matchesRes]) => {
      if (!alive) return;
      if (!searchTracked.current) {
        searchTracked.current = true;
        // Demo fires demo_started (in App) and nothing else — the sample
        // player must never look like a real search in the funnel.
        if (!isDemoMode()) {
          track("player_search", {
            region: player.region,
            found: accountRes.status === "fulfilled",
          });
        }
      }
      const account =
        accountRes.status === "fulfilled" ? accountRes.value : null;
      const matches =
        matchesRes.status === "fulfilled" ? matchesRes.value : null;
      const failed = [];
      if (accountRes.status === "rejected") failed.push("the account profile");
      if (matchesRes.status === "rejected") failed.push("recent matches");
      let error = null;
      if (failed.length > 0) {
        const reason =
          accountRes.status === "rejected"
            ? accountRes.reason
            : matchesRes.reason;
        error = `Could not load ${failed.join(" or ")}: ${
          (reason && reason.message) || "unknown error"
        }`;
      }
      setState({ loading: false, error, account, matches });
    });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [player, reloadKey]);

  if (!player) {
    return (
      <EmptyState
        title="No player selected"
        body="Search a Riot ID (name + tag) above to load their profile and recent matches."
      />
    );
  }

  if (state.loading) return <DashboardSkeleton />;

  if (state.error && !state.account && !state.matches) {
    return (
      <ErrorBanner
        message={state.error}
        onRetry={() => setReloadKey((k) => k + 1)}
      />
    );
  }

  const data = (state.account && state.account.data) || {};
  const matches = state.matches || [];
  const stats = computeStats(matches);
  const rank =
    (matches.find((m) => m.tier) || {}).tier || "Unranked";
  const card = data.card || {};

  return (
    <div className="stack" ref={scope}>
      {state.error ? (
        <ErrorBanner
          message={state.error}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : null}

      {state.account ? (
        <section className="panel account-card">
          {card.wide ? (
            <div
              className="account-banner"
              style={{ backgroundImage: `url(${card.wide})` }}
              aria-hidden="true"
            />
          ) : null}
          <div className="account-body">
            {card.small ? (
              <img className="account-avatar" src={card.small} alt="" />
            ) : null}
            <div>
              <h2 className="account-name">
                {data.name || player.name}
                <span className="tag">#{data.tag || player.tag}</span>
              </h2>
              <div className="chips">
                <span className="chip">Level {data.account_level ?? "?"}</span>
                <span className="chip accent-chip">{rank}</span>
                <span className="chip">
                  {(data.region || player.region || "").toUpperCase()}
                </span>
                {/* Deep links shipped with zero UI affordance — this is it.
                    Hidden in demo (a Demo#VAC link would just 404). */}
                {!isDemoMode() ? (
                  <CopyLinkButton player={player} tab="dashboard" />
                ) : null}
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {state.matches ? (
        <>
          {stats ? (
            <div className="stat-grid">
              <StatTile label="Win rate" value={stats.winRate} suffix="%" />
              <StatTile label="Avg KDA" value={stats.kda} />
              <StatTile label="Avg headshot" value={stats.hs} suffix="%" />
              <StatTile label="Matches analyzed" value={stats.count} />
            </div>
          ) : null}

          <section className="panel">
            <h3 className="panel-title">Recent matches</h3>
            {matches.length === 0 ? (
              <EmptyState
                title="No recent matches"
                body="No competitive history came back for this player. Try another region or play a few games."
              />
            ) : (
              <ul className="match-list">
                {matches.map((m, i) => (
                  <MatchRow key={m.match_id || i} m={m} />
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
