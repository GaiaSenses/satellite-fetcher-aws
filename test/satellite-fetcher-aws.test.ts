import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { SatelliteFetcherAwsStack } from "../lib/satellite-fetcher-aws-stack";

/**
 * What this file asserts is not arbitrary: every case is a property that was
 * missing or wrong in production, and that nothing would have noticed.
 *
 * The file it replaces was the CDK scaffold — a test named "SQS Queue Created",
 * with its entire body commented out, against a stack that has no queue. It
 * passed, because an empty test always passes. A green check that asserts
 * nothing is worse than no check: it makes CI look like it is watching.
 *
 * The stack refuses to synthesise without FIRMS_MAP_KEY, deliberately, so that
 * a backend answering 500 to every /fire cannot be deployed. Tests supply a
 * throwaway value rather than relaxing the guard.
 */
function template(): Template {
  process.env.FIRMS_MAP_KEY = "chave-de-teste";
  const app = new cdk.App();
  const stack = new SatelliteFetcherAwsStack(app, "TestStack", {
    env: { account: "123456789012", region: "sa-east-1" },
  });
  return Template.fromStack(stack);
}

describe("portas de entrada", () => {
  /**
   * There used to be a Function URL with authType NONE and CORS "*" — a second,
   * unauthenticated way into the same Lambda that nothing used. An open,
   * unmetered endpoint has no ceiling, which is what made "inside the free
   * tier" a hope rather than a property.
   */
  test("não existe Function URL", () => {
    template().resourceCountIs("AWS::Lambda::Url", 0);
  });

  test("as três rotas existem e todas exigem chave", () => {
    const t = template();
    t.resourceCountIs("AWS::ApiGateway::Method", 3);
    t.allResourcesProperties("AWS::ApiGateway::Method", {
      ApiKeyRequired: true,
    });
  });
});

describe("teto de uso", () => {
  /**
   * The one that cost a deploy cycle. The plan existed, the key existed, the key
   * was linked to the plan — and every request answered 403, because a key is
   * only valid on the stages its plan covers and this plan covered none.
   *
   * It fails in the direction that looks like success: a request without a key
   * is refused, which is the first thing anyone checks, and it passes for the
   * wrong reason.
   */
  test("todos os planos de uso estão ligados a um stage", () => {
    // Read the resource and assert on it directly, instead of going through
    // hasResourceProperties. `Match.arrayWith` does not fail when the property
    // is absent altogether, which is exactly the case being guarded against —
    // the first version of this test passed with `apiStages` deleted from the
    // stack. A test that cannot see the bug it was written for is the vacuous
    // scaffold all over again, in a more convincing costume.
    const planos = Object.values(
      template().findResources("AWS::ApiGateway::UsagePlan"),
    );

    expect(planos).toHaveLength(2);

    for (const plano of planos) {
      const estagios = plano.Properties?.ApiStages;
      expect(Array.isArray(estagios)).toBe(true);
      expect(estagios.length).toBeGreaterThan(0);
      expect(estagios[0].Stage).toBeDefined();
    }
  });

  test("há cota mensal e throttle", () => {
    template().hasResourceProperties("AWS::ApiGateway::UsagePlan", {
      Quota: Match.objectLike({ Period: "MONTH" }),
      Throttle: Match.objectLike({
        RateLimit: Match.anyValue(),
        BurstLimit: Match.anyValue(),
      }),
    });
  });

  /**
   * The throttle bounds this backend. The budget bounds everything else,
   * including mistakes nobody predicted — which is the only reason it is here
   * rather than in a console someone has to remember to open.
   */
  test("existe um budget com aviso por e-mail", () => {
    template().hasResourceProperties("AWS::Budgets::Budget", {
      Budget: Match.objectLike({ BudgetType: "COST", TimeUnit: "MONTHLY" }),
      NotificationsWithSubscribers: Match.arrayWith([
        Match.objectLike({
          Subscribers: Match.arrayWith([
            Match.objectLike({ SubscriptionType: "EMAIL" }),
          ]),
        }),
      ]),
    });
  });
});

describe("o plano público", () => {
  /**
   * A API pública do Gaiasenses-web usa uma chave própria num plano próprio,
   * para que abuso do tráfego público esgote a cota PÚBLICA — e vire 429 —
   * sem nunca dividir os 50k/mês e 10 rps que mantêm o mapa do site vivo.
   * É a lição do HIG-03: a rota antiga era uma porta gratuita para um backend
   * sem medidor; a porta nova tem medidor separado.
   */
  test("existem duas chaves, cada uma ligada a um plano", () => {
    const t = template();
    t.resourceCountIs("AWS::ApiGateway::ApiKey", 2);
    t.resourceCountIs("AWS::ApiGateway::UsagePlanKey", 2);
  });

  test("o plano público tem throttle 2/5 e cota de 20 mil por mês", () => {
    template().hasResourceProperties("AWS::ApiGateway::UsagePlan", {
      UsagePlanName: "SatelliteFetcherPublicUsagePlan",
      Quota: Match.objectLike({ Limit: 20_000, Period: "MONTH" }),
      Throttle: Match.objectLike({ RateLimit: 2, BurstLimit: 5 }),
    });
  });

  /** O plano do site permanece intocado: mesma cota, mesmo throttle. */
  test("o plano do site continua com 50 mil por mês e 10 rps", () => {
    template().hasResourceProperties("AWS::ApiGateway::UsagePlan", {
      UsagePlanName: "SatelliteFetcherUsagePlan",
      Quota: Match.objectLike({ Limit: 50_000, Period: "MONTH" }),
      Throttle: Match.objectLike({ RateLimit: 10, BurstLimit: 20 }),
    });
  });
});

describe("a função", () => {
  /**
   * New AWS accounts cap Lambda at 512 MB and CloudFormation rejects more, so
   * raising this fails the deploy rather than the review. It also suits the free
   * tier, measured in GB-seconds: half the memory buys twice the seconds.
   * Measured peak in production is 221 MB.
   */
  test("pede 512 MB, o que a conta permite", () => {
    template().hasResourceProperties("AWS::Lambda::Function", {
      MemorySize: 512,
    });
  });

  test("recebe a FIRMS_MAP_KEY", () => {
    template().hasResourceProperties("AWS::Lambda::Function", {
      Environment: Match.objectLike({
        Variables: Match.objectLike({ FIRMS_MAP_KEY: Match.anyValue() }),
      }),
    });
  });

  /** Log groups default to never expiring, which is a bill that grows quietly. */
  test("o log expira", () => {
    template().hasResourceProperties("AWS::Logs::LogGroup", {
      RetentionInDays: Match.anyValue(),
    });
  });
});

describe("o guard da chave", () => {
  /**
   * Without the key the /fire endpoint is dead, so the stack refuses to
   * synthesise rather than deploying a backend that answers 500 to everything.
   */
  test("sem FIRMS_MAP_KEY a stack recusa sintetizar", () => {
    const anterior = process.env.FIRMS_MAP_KEY;
    delete process.env.FIRMS_MAP_KEY;

    try {
      expect(
        () => new SatelliteFetcherAwsStack(new cdk.App(), "SemChave"),
      ).toThrow(/FIRMS_MAP_KEY/);
    } finally {
      if (anterior !== undefined) process.env.FIRMS_MAP_KEY = anterior;
    }
  });
});
