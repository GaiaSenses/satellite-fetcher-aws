# Welcome to your CDK TypeScript project

This is a blank project for CDK development with TypeScript.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

> ℹ️ This README is still the CDK boilerplate — the full rewrite is tracked in [#19](https://github.com/GaiaSenses/satellite-fetcher-aws/issues/19). Until then, the notes below cover what the boilerplate does not: tests, alarms and key rotation. Releases are tagged since [`v1.0.0`](https://github.com/GaiaSenses/satellite-fetcher-aws/releases/tag/v1.0.0).

## Python tests

The Lambda code under `image/src/` has unit tests in `image/tests/` (regression tests for the `/fire` bounding box, input validation, the GOES slot fallback and the vectorized `/lightning` filter). CI runs them on every PR (`verificar-stack` workflow); locally:

```bash
python3 -m pip install numpy pandas shapely netCDF4 boto3
python3 -m unittest discover -s image/tests -v
```

## Operations

- **Alarms:** the stack creates three CloudWatch alarms (API 5xx, Lambda errors, p95 duration) that e-mail the project account through the `AlertasDeSaude` SNS topic, plus a JSON access log on the API Gateway (30-day retention, no headers). What to do when each one fires — and how to test the pipeline deliberately — is written in the [runbook](https://github.com/GaiaSenses/gaiasenses-docs/blob/main/runbook-alarmes-e-custos.md).
- **API key rotation:** rename the API key construct in `lib/satellite-fetcher-aws-stack.ts` and deploy — CloudFormation creates the new key and deletes the old one in the same run. The recipe is commented right above the construct.
- **Cost:** everything fits the free tier (API key + 10 rps throttle + 50k/month quota + ECR lifecycle keeping 3 images); a US$ 5 AWS Budget is the fence.

## Useful commands

- `npm run build` compile typescript to js
- `npm run watch` watch for changes and compile
- `npm run test` perform the jest unit tests
- `npx cdk deploy` deploy this stack to your default AWS account/region
- `npx cdk diff` compare deployed stack with current state
- `npx cdk synth` emits the synthesized CloudFormation template

## To run the docker image and test our application locally.

- `cd image/` enter the docker image folder
- `docker build -t docker-image/satellite-fetcher-aws .` build the docker image with the name `satellite-fetcher-aws` with the `.` Dockerfile
- `docker run --env-file ../.env -p 9000:8080 docker-image/satellite-fetcher-aws` run the docker image you just built
- `curl "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"rawPath":"/fire","queryStringParameters": {"lat":-22.851692221661406, "lon":47.1276886499418, "dist":100}}'` to hit the function. `2015-03-31` is the AWS Lambda Version
