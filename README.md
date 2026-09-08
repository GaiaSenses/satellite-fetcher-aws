# satellite-fetcher-aws

> **Satellite data backend for [GaiaSenses](https://github.com/GaiaSenses/Gaiasenses-web).**
> AWS CDK (TypeScript) project that provisions the Lambda + API Gateway serving fire and lightning data to the public site.

⚠️ **This is a production dependency.** The site at <https://gaiasenses-web.vercel.app> calls this API on every visit (server-side, via `SATELLITE_API_URL` / `SATELLITE_API_KEY`). Do not decommission or rename resources without checking the web repo first.

**Region:** `sa-east-1` (pinned in `bin/`, on purpose — see the comment there) · **Releases:** tagged since [`v1.0.0`](https://github.com/GaiaSenses/satellite-fetcher-aws/releases/tag/v1.0.0)

---

## The API

Three routes on a single API Gateway (`prod` stage). **Every route requires an API key** sent as `x-api-key` — without it the Gateway answers `403 Forbidden` before reaching the Lambda.

| Route | Source | Query params |
|---|---|---|
| `GET /fire` | **NASA FIRMS** (VIIRS on NOAA-20, near-real-time) — needs `FIRMS_MAP_KEY` | `lat`, `lon`, `dist` |
| `GET /lightning` | **GOES-19 GLM** (`GLM-L2-LCFA` netCDF, public S3 bucket `noaa-goes19`, read anonymously) | `lat`, `lon`, `dist` |
| `GET /rain` | **GOES-19 RRQPE** (same bucket) — exists, but the site does not call it today | `lat`, `lon` |

Validation (returns `400` with a JSON `error`, never a 5xx, for bad input):

- `lat` ∈ [-90, 90], `lon` ∈ [-180, 180], both required and numeric;
- `dist` in km, optional — default **50**, maximum **1000**.

```bash
curl -H "x-api-key: $SATELLITE_API_KEY" \
  "$SATELLITE_API_URL/fire?lat=-22.85&lon=-47.12&dist=100"
# → {"count": N, ...}
```

If a GOES time slot is missing on S3 (they land with delay sometimes), `/lightning` falls back up to 4 previous slots before giving up — a transient gap does not become an error for the visitor.

## Limits and cost fences (stay inside the free tier)

| Fence | Value | Where |
|---|---|---|
| Throttle | **10 rps**, burst 20 | usage plan + method throttling |
| Quota | **50,000 requests/month** | usage plan |
| Budget | **US$ 5/month** alarm to the project e-mail | `MonthlyBudget` in the stack |
| Lambda | 512 MB, ARM64, 30 s timeout | `DockerFunc` |
| Concurrency | account total (5) — no reservation, the account quota **is** the ceiling (see comment in the stack) | — |
| ECR | lifecycle keeps the **3** most recent images | stack |
| Logs | function + API access logs, **30-day** retention, JSON, no headers | stack |

## Deploy from zero

Prerequisites: Node ≥ 18, Docker, AWS credentials for the project account.

```bash
# 1. Dependencies
npm ci

# 2. Docker must build linux/arm64. On an x86 machine, install the emulator once:
docker run --privileged --rm tonistiigi/binfmt --install arm64

# 3. Credentials. `aws login` opens the browser; the CDK uses the AWS SDK,
#    which does NOT read the session `aws login` writes — bridge it:
aws login
eval "$(aws configure export-credentials --format env)"

# 4. The NASA FIRMS key (free: https://firms.modaps.eosdis.nasa.gov/api/map_key/).
#    Synth fails on purpose without it — /fire is dead without the key.
export FIRMS_MAP_KEY=<your key>

# 5. First deploy in a fresh account only:
npx cdk bootstrap

# 6. Review, then deploy:
npx cdk diff
npx cdk deploy
```

The deploy prints the API base URL. Read the generated API key:

```bash
aws apigateway get-api-keys --query 'items[].{id:id,name:name}' --output table
aws apigateway get-api-key --api-key <id> --include-value --query value --output text
```

Smoke test — the acceptance is a **200 with real data**:

```bash
curl -s -H "x-api-key: <value>" \
  "https://<api-id>.execute-api.sa-east-1.amazonaws.com/prod/fire?lat=-22.85&lon=-47.12&dist=100"
```

Finally, wire the site: set `SATELLITE_API_URL` (base URL, no trailing slash) and `SATELLITE_API_KEY` in the Vercel project of `Gaiasenses-web` and redeploy it.

## Run locally

```bash
cd image/
docker build -t satellite-fetcher-aws .
docker run --env-file ../.env -p 9000:8080 satellite-fetcher-aws

# In another terminal (2015-03-31 is the Lambda runtime API version):
curl "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"rawPath":"/fire","queryStringParameters":{"lat":"-22.85","lon":"-47.12","dist":"100"}}'
```

`../.env` needs `FIRMS_MAP_KEY=...`. The image base is pinned by digest and `image/requirements.txt` is fully frozen — the build is reproducible from a clean clone.

## Tests

```bash
# Python (the Lambda code): regression tests for the /fire bounding box,
# input validation, the GOES slot fallback and the vectorized /lightning filter.
python3 -m pip install numpy pandas shapely netCDF4 boto3
python3 -m unittest discover -s image/tests -v

# TypeScript (the stack):
npm test
```

Both run on every PR in the `verificar-stack` workflow, which is a **required check** on `main` — there is no pushing directly.

## Operations

- **Alarms** (all e-mail the project account through the `AlertasDeSaude` SNS topic): API 5xx ≥ 5 in 5 min (`Alarme5xx`), Lambda errors ≥ 5 (`AlarmeErrosLambda`), p95 duration > 25 s (`AlarmeDuracao`, near the Gateway's 29 s limit). What to do when each fires — and how to test the pipeline deliberately — is in the [runbook](https://github.com/GaiaSenses/gaiasenses-docs/blob/main/runbook-alarmes-e-custos.md).
- **Rotating the API key:** rename the API key construct in `lib/satellite-fetcher-aws-stack.ts` and deploy — CloudFormation creates the new key and deletes the old one in the same run (recipe commented above the construct). Update `SATELLITE_API_KEY` on Vercel afterwards.
- **Rotating `FIRMS_MAP_KEY`:** get a new key from NASA, update the Lambda environment (console or `aws lambda update-function-configuration`), and keep it out of git.

## Useful CDK commands

- `npx cdk diff` — compare deployed stack with current code (always before deploy)
- `npx cdk deploy` — deploy
- `npx cdk synth` — emit the CloudFormation template
- `npm run build` / `npm run watch` — compile TypeScript

## Related

- [`Gaiasenses-web`](https://github.com/GaiaSenses/Gaiasenses-web) — the site that consumes this API (see its README for the consumer side).
- [`gaiasenses-docs`](https://github.com/GaiaSenses/gaiasenses-docs) — architecture dossier, runbook, status reports.
- Live task tracking: [trilha v1](https://github.com/GaiaSenses/Gaiasenses-web/blob/main/docs/trilha-v1.md).

**History:** the fetcher ran on Railway (2023–2025), was migrated to AWS Lambda in March 2025, and weather moved off to Open-Meteo. In August 2026 the whole backend was redeployed into the project's own AWS account — until then it lived in a personal account nobody on the team could access.
