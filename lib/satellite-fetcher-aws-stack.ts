import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";

import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as logs from "aws-cdk-lib/aws-logs";
import * as budgets from "aws-cdk-lib/aws-budgets";

/**
 * Free tier is not a promise the AWS console makes on its own — it is a
 * consequence of every door being counted. The numbers below exist so that the
 * worst case is a 429, never an invoice.
 */

/** Requests per second, and the burst allowed above it. */
const RATE_LIMIT = 10;
const BURST_LIMIT = 20;

/**
 * Monthly ceiling. The site fetches server-side with Next.js caching — two
 * hours for fire, twenty-four for the rest — so real traffic is a small
 * fraction of this. Lambda's always-free tier is 1M requests a month and API
 * Gateway REST gives 1M for the first twelve months; 50k leaves both untouched
 * even if traffic grows tenfold. Raise it deliberately, not by reflex.
 */
const MONTHLY_QUOTA = 50_000;

/** Where the budget alarm goes, and the threshold in US dollars. */
const BUDGET_EMAIL = "gaiasenses.cti@gmail.com";
const MONTHLY_BUDGET_USD = 5;

export class SatelliteFetcherAwsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    /**
     * The NASA FIRMS key. Free, but the /fire endpoint is dead without it, so
     * the stack refuses to synthesize rather than deploying a backend that
     * answers 500 to every fire request.
     *
     * It is read from the deploy environment and never committed. It does end
     * up readable in the Lambda configuration by anyone with access to this
     * account, which is an accepted trade for a free key on a research
     * project. Moving it to SSM Parameter Store — also free — and reading it
     * at runtime is the upgrade when that stops being acceptable.
     */
    const firmsMapKey = process.env.FIRMS_MAP_KEY;
    if (!firmsMapKey) {
      throw new Error(
        "FIRMS_MAP_KEY is not set. Get a free key at " +
          "https://firms.modaps.eosdis.nasa.gov/api/map_key/ and export it " +
          "before running cdk deploy.",
      );
    }

    const dockerFunc = new lambda.DockerImageFunction(this, "DockerFunc", {
      code: lambda.DockerImageCode.fromImageAsset("./image"),
      /**
       * 512 MB, not the 1024 this stack used to ask for. New AWS accounts are
       * capped there until the account matures, and CloudFormation refuses the
       * larger value outright — the first deploy into this account rolled back
       * on exactly that.
       *
       * It is not only a workaround. Lambda's free tier is 400,000 GB-seconds
       * a month, so halving memory doubles the seconds it buys. The cost is
       * CPU, which scales with memory: /lightning downloads GOES imagery and
       * works it with numpy, and it is the one at risk of running long. If it
       * starts timing out, raise the quota with AWS Support and bring this
       * back to 1024 — in that order, or the deploy fails again.
       */
      memorySize: 512,
      // No reservedConcurrentExecutions, measured and on purpose: this
      // account's TOTAL Lambda concurrency limit is 5 (aws lambda
      // get-account-settings, 2026-09-08), and AWS requires >=5 left
      // unreserved — so the maximum reservable here is zero, and both 10 and 5
      // failed deployment with InvalidRequest. The ceiling SEC-01 asked for
      // exists anyway, tighter than planned: the account itself cannot run
      // more than 5 concurrent executions, and this is its only function. If
      // the account quota is ever raised, add a reservation back to keep the
      // ceiling explicit.
      /**
       * API Gateway cuts any integration at 29 seconds, so anything above that
       * only affects direct invocations. Kept at 30 to leave the function a
       * moment to log its own timeout rather than being killed mid-request.
       */
      timeout: cdk.Duration.seconds(30),
      architecture: lambda.Architecture.ARM_64,
      environment: {
        FIRMS_MAP_KEY: firmsMapKey,
      },
      // Log groups default to never expiring, which is a bill that grows
      // quietly forever. A month is plenty to debug what broke yesterday.
      //
      // Declared as its own resource rather than through `logRetention`, which
      // would have CDK deploy a helper Lambda and an IAM role just to call
      // PutRetentionPolicy — three resources and an extra function in the
      // account to express one number.
      logGroup: new logs.LogGroup(this, "DockerFuncLogs", {
        retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // The Function URL that used to live here was removed. It was a second
    // door into the same Lambda — authType NONE, CORS "*" — that nothing used:
    // the site talks to the API Gateway below. An unauthenticated, unmetered
    // endpoint has no ceiling, and a ceiling is the whole point of this file.

    const api = new apigateway.RestApi(this, "SatelliteFetcherAwsApi", {
      restApiName: "SatelliteFetcherAwsApi",
      description: "Fetch satellite data",
      deployOptions: {
        stageName: "prod",
        // Per-method throttling is the second line, under the usage plan.
        throttlingRateLimit: RATE_LIMIT,
        throttlingBurstLimit: BURST_LIMIT,
      },
    });

    const integration = new apigateway.LambdaIntegration(dockerFunc);

    // Every route requires the key. The site calls this server-side, from a
    // Next.js route with SATELLITE_API_URL, so the key never reaches a browser.
    for (const path of ["fire", "lightning", "rain"]) {
      api.root.addResource(path).addMethod("GET", integration, {
        apiKeyRequired: true,
      });
    }

    const apiKey = api.addApiKey("SatelliteFetcherKey", {
      description: "Used by the Gaiasenses web app, server-side only",
    });

    api
      .addUsagePlan("SatelliteFetcherUsagePlan", {
        name: "SatelliteFetcherUsagePlan",
        throttle: { rateLimit: RATE_LIMIT, burstLimit: BURST_LIMIT },
        quota: {
          limit: MONTHLY_QUOTA,
          period: apigateway.Period.MONTH,
        },
        /**
         * Without this the plan exists, the key exists, the key is linked to
         * the plan — and every request still gets 403, because the plan is
         * attached to no stage and so the key is valid nowhere. The first
         * deploy of this file had exactly that, and it fails in the direction
         * that looks like success: `curl` without a key is refused, which is
         * what you check first.
         */
        apiStages: [{ api, stage: api.deploymentStage }],
      })
      .addApiKey(apiKey);

    /**
     * The throttle and the quota bound usage. This bounds everything else —
     * a mistake in another service, a resource left running, a surprise none
     * of us predicted. Two budgets per account are free.
     */
    new budgets.CfnBudget(this, "MonthlyBudget", {
      budget: {
        budgetName: "gaiasenses-monthly",
        budgetType: "COST",
        timeUnit: "MONTHLY",
        budgetLimit: { amount: MONTHLY_BUDGET_USD, unit: "USD" },
      },
      notificationsWithSubscribers: [
        // Forecast first: it warns before the money is spent, not after.
        {
          notification: {
            notificationType: "FORECASTED",
            comparisonOperator: "GREATER_THAN",
            threshold: 100,
            thresholdType: "PERCENTAGE",
          },
          subscribers: [
            { subscriptionType: "EMAIL", address: BUDGET_EMAIL },
          ],
        },
        {
          notification: {
            notificationType: "ACTUAL",
            comparisonOperator: "GREATER_THAN",
            threshold: 80,
            thresholdType: "PERCENTAGE",
          },
          subscribers: [
            { subscriptionType: "EMAIL", address: BUDGET_EMAIL },
          ],
        },
      ],
    });

    new cdk.CfnOutput(this, "ApiGatewayUrl", {
      value: api.url,
      description: "Goes in SATELLITE_API_URL on Vercel",
    });

    new cdk.CfnOutput(this, "ApiKeyId", {
      value: apiKey.keyId,
      description:
        "Read the value with: aws apigateway get-api-key --api-key <this> " +
        "--include-value --query value --output text",
    });
  }
}
