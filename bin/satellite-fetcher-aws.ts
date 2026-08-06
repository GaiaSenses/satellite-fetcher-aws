#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { SatelliteFetcherAwsStack } from '../lib/satellite-fetcher-aws-stack';

const app = new cdk.App();

/**
 * The stack was environment-agnostic, which reads as flexible and behaves as a
 * trap: `cdk deploy` went wherever the CLI happened to point. Someone with a
 * different default region would not update this stack — they would create a
 * second one, and end up with two Lambdas, two API Gateways, two bills, and a
 * site wired to only one of them.
 *
 * The account comes from the CLI, so no account id is hardcoded into a public
 * repository. The region is pinned, because it is a decision and not an
 * accident: sa-east-1 keeps the backend near its audience and matches the
 * Supabase project.
 *
 * Worth revisiting once /lightning is measured: it pulls GOES imagery from the
 * `noaa-goes19` bucket, which lives in us-east-1. Running there would put the
 * function next to the data it downloads — closer to the data, further from
 * the people. Measure before moving.
 */
new SatelliteFetcherAwsStack(app, 'SatelliteFetcherAwsStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'sa-east-1',
  },
});