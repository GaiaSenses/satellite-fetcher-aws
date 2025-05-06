import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
// import * as sqs from 'aws-cdk-lib/aws-sqs';

import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";

export class SatelliteFetcherAwsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // The code that defines your stack goes here

    // example resource
    // const queue = new sqs.Queue(this, 'SatelliteFetcherAwsQueue', {
    //   visibilityTimeout: cdk.Duration.seconds(300)
    // });

    const dockerFunc = new lambda.DockerImageFunction(this, "DockerFunc", {
      code: lambda.DockerImageCode.fromImageAsset("./image"),
      memorySize: 1024,
      timeout: cdk.Duration.seconds(30),
      architecture: lambda.Architecture.ARM_64,
    });

    const functionUrl = dockerFunc.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedMethods: [lambda.HttpMethod.GET],
        allowedHeaders: ["*"],
        allowedOrigins: ["*"],
      },
    });

    new cdk.CfnOutput(this, "FunctionUrl", {
      value: functionUrl.url,
    });

    const api = new apigateway.RestApi(this, "SatelliteFetcherAwsApi", {
      restApiName: "SatelliteFetcherAwsApi",
      description: "Fetch satellite data",
      deployOptions: {
        stageName: "prod",
      },
    });

    const fireDataResource = api.root.addResource("fire");
    fireDataResource.addMethod(
      "GET",
      new apigateway.LambdaIntegration(dockerFunc)
    );

    const lightningDataResource = api.root.addResource("lightning");
    lightningDataResource.addMethod(
      "GET",
      new apigateway.LambdaIntegration(dockerFunc)
    );

    const rainDataResource = api.root.addResource("rain");
    rainDataResource.addMethod(
      "GET",
      new apigateway.LambdaIntegration(dockerFunc)
    );

    new cdk.CfnOutput(this, "ApiGatewayUrl", {
      value: api.url,
    });
  }
}
