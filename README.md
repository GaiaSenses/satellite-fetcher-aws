# Welcome to your CDK TypeScript project

This is a blank project for CDK development with TypeScript.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

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
