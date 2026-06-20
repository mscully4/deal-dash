import { Duration, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import { LambdaIntegration, RestApi } from "aws-cdk-lib/aws-apigateway";
import { AttributeType, BillingMode, StreamViewType, Table } from "aws-cdk-lib/aws-dynamodb";
import { Rule, Schedule } from "aws-cdk-lib/aws-events";
import { LambdaFunction } from "aws-cdk-lib/aws-events-targets";
import { Effect, PolicyStatement } from "aws-cdk-lib/aws-iam";
import {
  DockerImageCode,
  DockerImageFunction,
  FunctionUrl,
  FunctionUrlAuthType,
  StartingPosition,
} from "aws-cdk-lib/aws-lambda";
import { DynamoEventSource } from "aws-cdk-lib/aws-lambda-event-sources";
import { CfnIndex, CfnVectorBucket } from "aws-cdk-lib/aws-s3vectors";
import { Secret } from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";

export class RebelSavingsStack extends Stack {
  public readonly dealsTable: Table;

  constructor(scope: Construct, id: string, props: StackProps) {
    super(scope, id, props);

    this.dealsTable = new Table(this, "DealsTable", {
      tableName: "rebel-savings-deals",
      partitionKey: { name: "retailer", type: AttributeType.STRING },
      sortKey: { name: "item_id", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.RETAIN,
      stream: StreamViewType.NEW_IMAGE,
    });

    const vectorBucket = new CfnVectorBucket(this, "VectorBucket", {
      vectorBucketName: "deal-dash-vectors",
    });

    const vectorIndex = new CfnIndex(this, "VectorIndex", {
      vectorBucketName: "deal-dash-vectors",
      indexName: "deals",
      dataType: "float32",
      dimension: 256,
      distanceMetric: "cosine",
    });
    vectorIndex.addDependency(vectorBucket);

    const discordBotToken = new Secret(this, "DiscordBotToken", {
      secretName: "deal-dash/discord-bot-token",
      description: "Discord bot token for deal-dash",
    });

    const embedder = new DockerImageFunction(this, "EmbedderLambda", {
      code: DockerImageCode.fromImageAsset(".", {
        cmd: ["deal_dash.lambdas.embedder.handler.handler"],
      }),
      timeout: Duration.seconds(60),
      environment: {
        VECTOR_BUCKET: "deal-dash-vectors",
        VECTOR_INDEX: "deals",
        DISCORD_BOT_TOKEN_ARN: discordBotToken.secretArn,
        DISCORD_CHANNEL_ID: process.env.DISCORD_CHANNEL_ID ?? "",
      },
    });

    discordBotToken.grantRead(embedder);

    embedder.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["bedrock:InvokeModel"],
        resources: [
          `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        ],
      })
    );

    embedder.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["s3vectors:GetVectors", "s3vectors:PutVectors", "s3vectors:QueryVectors"],
        resources: [
          `arn:aws:s3vectors:${this.region}:${this.account}:bucket/deal-dash-vectors/index/deals`,
        ],
      })
    );

    embedder.addEventSource(
      new DynamoEventSource(this.dealsTable, {
        startingPosition: StartingPosition.TRIM_HORIZON,
        batchSize: 10,
        bisectBatchOnError: true,
      })
    );

    const discordHandler = new DockerImageFunction(this, "DiscordHandlerLambda", {
      code: DockerImageCode.fromImageAsset(".", {
        cmd: ["deal_dash.lambdas.discord_handler.handler.handler"],
      }),
      timeout: Duration.seconds(10),
      environment: {
        DISCORD_PUBLIC_KEY: process.env.DISCORD_PUBLIC_KEY ?? "",
        VECTOR_BUCKET: "deal-dash-vectors",
        VECTOR_INDEX: "deals",
      },
    });

    new FunctionUrl(this, "DiscordHandlerUrl", {
      function: discordHandler,
      authType: FunctionUrlAuthType.NONE,
    });

    const api = new RestApi(this, "DiscordApi", {
      restApiName: "deal-dash-discord",
    });
    api.root.addResource("interactions").addMethod("POST", new LambdaIntegration(discordHandler));

    discordHandler.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["s3vectors:GetVectors", "s3vectors:PutVectors"],
        resources: [
          `arn:aws:s3vectors:${this.region}:${this.account}:bucket/deal-dash-vectors/index/deals`,
        ],
      })
    );

    const scraper = new DockerImageFunction(this, "ScraperLambda", {
      code: DockerImageCode.fromImageAsset("."),
      timeout: Duration.minutes(10),
      memorySize: 1024,
      environment: {
        DEALS_TABLE: this.dealsTable.tableName,
      },
    });

    this.dealsTable.grantWriteData(scraper);

    new Rule(this, "ScraperSchedule", {
      schedule: Schedule.rate(Duration.hours(1)),
      targets: [new LambdaFunction(scraper)],
    });
  }
}
