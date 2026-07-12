import { Duration, Stack, StackProps } from "aws-cdk-lib";
import { ITable } from "aws-cdk-lib/aws-dynamodb";
import { DockerImageCode, DockerImageFunction, StartingPosition } from "aws-cdk-lib/aws-lambda";
import { DynamoEventSource } from "aws-cdk-lib/aws-lambda-event-sources";
import { Secret } from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";

export interface DealConsumerStackProps extends StackProps {
  dealsTable: ITable;
}

export class DealConsumerStack extends Stack {
  constructor(scope: Construct, id: string, props: DealConsumerStackProps) {
    super(scope, id, props);

    const { dealsTable } = props;

    // Own copy of the Discord bot token, decoupled from RebelSavingsStack's
    // secret of the same value — lets that stack be torn down independently
    // once fully deprecated. Same physical Discord bot; value must be copied
    // over manually after deploy (CDK generates a random placeholder).
    const discordBotToken = new Secret(this, "DiscordBotToken", {
      secretName: "deal-dash/discord-bot-token-v2",
      description: "Discord bot token for deal-dash (deal-consumer-stack copy)",
    });

    // Notifier: DDB stream -> Discord. No embedding/similarity check yet —
    // that's deferred until the S3 Vectors vs in-DDB decision is settled.
    const notifier = new DockerImageFunction(this, "NotifierLambda", {
      code: DockerImageCode.fromImageAsset(".", {
        cmd: ["deal_dash.lambdas.notifier.handler.handler"],
      }),
      timeout: Duration.seconds(30),
      environment: {
        DEALS_TABLE: dealsTable.tableName,
        DISCORD_BOT_TOKEN_ARN: discordBotToken.secretArn,
        DISCORD_CHANNEL_ID: process.env.DISCORD_CHANNEL_ID ?? "",
      },
    });

    discordBotToken.grantRead(notifier);

    notifier.addEventSource(
      new DynamoEventSource(dealsTable, {
        startingPosition: StartingPosition.TRIM_HORIZON,
        batchSize: 10,
        bisectBatchOnError: true,
      })
    );
  }
}
