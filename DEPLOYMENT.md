# Deployment Guide (AWS)

Valorant AI Companion runs on AWS as one Docker Compose stack behind CloudFront:

```
Browser ──HTTPS──> CloudFront ──HTTP──> EC2 (t3.small, Amazon Linux 2023)
                   (TLS, CDN,            └─ docker compose
                    *.cloudfront.net         ├─ web: Caddy — serves the React build,
                    or your domain)          │        proxies /api/* -> api:8000
                                             └─ api: FastAPI + ChromaDB
                                                  ├── Anthropic Claude API
                                                  ├── HenrikDev API (match data)
                                                  └── SQLite on a persistent volume
```

Why this shape:

- **One box, one stack.** The same `docker-compose.yml` runs locally and in production, so "works on my machine" *is* the deployment.
- **Persistent state.** Mental profiles and analytics live in SQLite on the instance's EBS volume and survive deploys — the thing the old free-tier Render setup couldn't do.
- **Same-origin API.** The frontend calls `/api/...` on its own origin, so there are no CORS or mixed-content surprises; Caddy strips the prefix before handing requests to FastAPI.
- **Free HTTPS from day one.** CloudFront fronts the box with a `*.cloudfront.net` URL; a custom domain is one script away (below).
- **Push-to-deploy, no stored keys.** GitHub Actions assumes an IAM role through OIDC and runs `infra/deploy.sh` on the box over Systems Manager. No SSH port is open; shell access is `aws ssm start-session`.
- **Secrets in Parameter Store.** The box pulls `/vac/*` (SecureString) into `backend/.env` on every deploy; nothing sensitive is in the repo, the image, or GitHub.

Rough cost in `us-east-1`: t3.small ≈ $15/mo + 20 GB gp3 ≈ $1.60 + public IPv4 ≈ $3.65 ≈ **$20/mo**. CloudFront, Parameter Store, SSM and the ACM certificate are free at this scale. New AWS accounts get free-tier credits that cover this for months.

> AWS App Runner would have been the managed-container option, but it stopped accepting new customers on April 30, 2026.

---

## Prerequisites (once)

- **AWS CLI v2** and **GitHub CLI** on your PATH; a bash shell (Git Bash on Windows).
- An AWS session: `aws login` (opens the browser; sessions last up to 12 h — re-run it when the CLI says the session expired).
- `gh auth login` done for the repo owner.
- `backend/.env` filled in with `ANTHROPIC_API_KEY` and `RIOT_API_KEY` (optionally `DISCORD_WEBHOOK_URL`). These are what get copied into Parameter Store.
- Optional: the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) if you want a shell on the box.

## 1. First deploy — `infra/bootstrap.sh`

```bash
aws login            # if you don't have an active session
infra/bootstrap.sh
```

It's idempotent (safe to re-run) and creates, in order: Parameter Store secrets → EC2 instance role → security group (port 80 from CloudFront's IP ranges only) → the instance, whose first boot installs Docker, clones this repo into `/opt/vac` and runs `infra/deploy.sh` → an Elastic IP → the CloudFront distribution → the GitHub OIDC deploy role → the repo variables the workflow needs. Then it polls until `https://<id>.cloudfront.net/api/` answers (the first build on the box plus CloudFront's rollout take 10–15 minutes) and prints the URL, the instance id, and — on the very first run — a generated `ADMIN_TOKEN` for `GET /api/analytics/summary`. **Save that token; it isn't shown again** (it's retrievable from Parameter Store as `/vac/ADMIN_TOKEN`).

Knobs (env vars): `INSTANCE_TYPE` (default `t3.small`, ≈$15/mo; the API idles around 160 MB, so `t3.micro` at ≈$7.60/mo also works — the 2 GB swap added at first boot covers the on-box image builds, which are the memory-hungry part), `VOLUME_GB`, `AWS_REGION`, `REPO`, `BRANCH`.

## 2. Every deploy after that — `git push`

[.github/workflows/deploy.yml](.github/workflows/deploy.yml) runs on every push to `main` (or manually: `gh workflow run deploy.yml`):

1. assume the `vac-github-deploy` role via OIDC;
2. `aws ssm send-command` → the box runs [infra/deploy.sh](infra/deploy.sh): refresh `backend/.env` from Parameter Store, `git reset --hard origin/main`, `docker compose up -d --build`, wait for `/api/`;
3. invalidate the CloudFront cache;
4. smoke-test `/api/` and `/api/meta/status` through CloudFront.

Expect 3–5 minutes; the backend image rebuild is most of it. There's a few seconds of downtime while the `api` container is replaced.

### Changing a secret

```bash
aws ssm put-parameter --name /vac/RIOT_API_KEY --type SecureString --overwrite --value "HDEV-..."
gh workflow run deploy.yml      # or push anything
```

## 3. Custom domain — `infra/add-domain.sh`

1. Register the domain in **Route 53 → Registered domains → Register domain** (cheapest TLDs there are around $3–5/yr — `.click`, `.link`; `.com` ≈ $15/yr). Registration creates the hosted zone automatically.

   > **Pick a name with no Riot trademark in it.** Riot's fan-content policy
   > ([Legal Jibber Jabber](https://www.riotgames.com/en/legal) §5) says you
   > "may not register domain names … that use Riot Games or any of our
   > trademarks, trade names, character names," so `valorant-companion.gg`
   > would breach it while `tiltcheck.dev` is fine. The TLD is irrelevant —
   > it's the mark inside the label that matters. Using the game's name in the
   > *page title* is fine; putting it in the *domain* is not.
2. ```bash
   infra/add-domain.sh yourdomain.tld
   ```
   Requests a free ACM certificate (DNS-validated, in `us-east-1` as CloudFront requires), adds the domain + `www` to the distribution, creates the alias records, updates the backend's `CORS_ORIGINS`, switches the workflow's `APP_URL`, and triggers a redeploy. Live after the CloudFront update (~5 min) and DNS propagation.

The `*.cloudfront.net` URL keeps working alongside the domain.

## 4. Operating it

| Need | Command |
|---|---|
| Shell on the box | `aws ssm start-session --target <instance-id>` |
| App logs | on the box: `cd /opt/vac && sudo docker compose logs -f api` |
| First-boot log | on the box: `sudo cat /var/log/vac-bootstrap.log` |
| Redeploy manually | on the box: `sudo /opt/vac/infra/deploy.sh` — or `gh workflow run deploy.yml` |
| RAG index status | `curl https://<url>/api/meta/status` |
| Analytics summary | `curl -H "X-Admin-Token: <token>" https://<url>/api/analytics/summary` |
| Back up SQLite | on the box: `sudo docker compose cp api:/app/state/companion.sqlite3 ./backup.sqlite3` |
| Stop paying | `aws ec2 stop-instances --instance-ids <id>` (EBS + Elastic IP still bill a few $/mo); to remove everything, delete in reverse: CloudFront distribution, instance, Elastic IP, security group, IAM roles, `/vac/*` parameters |

### How requests are rate-limited behind the proxy

CloudFront sets `CloudFront-Viewer-Address` (the real client IP) on every request to the origin — it discards any copy a client sends — and the distribution's origin request policy forwards it. `backend/app/limiter.py` keys the per-IP limits on that header, falling back to the socket address locally. Two things keep that header trustworthy: the security group only admits CloudFront's published IP ranges, and Caddy rejects any request that doesn't carry the `X-Origin-Verify` shared secret that only *our* distribution stamps on origin requests (`/vac/ORIGIN_SECRET`, generated by the bootstrap) — so the box can't be reached directly, nor through someone else's CloudFront distribution.

### Things baked into the backend image

`backend/Dockerfile` downloads ChromaDB's ONNX embedding model and builds the knowledge index at **build time**, so a new container is ready for `/api/meta/ask` instantly and the index always matches the knowledge files in that commit. Editing `backend/data/knowledge/*.md` and pushing is all it takes to update the meta Q&A.

## Running the production stack locally

```bash
WEB_PORT=8080 docker compose up --build
# http://localhost:8080        frontend
# http://localhost:8080/api/   backend (docs at /api/docs)
```

Uses your `backend/.env`. State lives in the `state` Docker volume (`docker compose down -v` wipes it).

---

## Legacy: Render + Vercel

`render.yaml` and `frontend/vercel.json` are kept for anyone who wants the free-tier path (Render web service + Vercel static site, joined by `CORS_ORIGINS`). Set `VITE_API_URL` on Vercel to the Render URL and `CORS_ORIGINS` on Render to the Vercel URL; note Render's free disk is ephemeral, so SQLite resets on every deploy or cold start. The git history before the AWS migration has the full walkthrough.
