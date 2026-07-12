import { Duration, Stack, StackProps } from "aws-cdk-lib";
import { ITable } from "aws-cdk-lib/aws-dynamodb";
import { Rule, Schedule } from "aws-cdk-lib/aws-events";
import { LambdaFunction } from "aws-cdk-lib/aws-events-targets";
import { DockerImageCode, DockerImageFunction } from "aws-cdk-lib/aws-lambda";
import { Secret } from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";

export interface DealScraperStackProps extends StackProps {
  dealsTable: ITable;
}

export class DealScraperStack extends Stack {
  constructor(scope: Construct, id: string, props: DealScraperStackProps) {
    super(scope, id, props);

    const { dealsTable } = props;

    const hcRefreshToken = new Secret(this, "HiddenClearancesRefreshToken", {
      secretName: "deal-dash/hidden-clearances-refresh-token",
      description: "Supabase refresh token for Hidden Clearances (rotates on every use)",
    });

    const hiddenClearancesScraper = new DockerImageFunction(this, "HiddenClearancesScraper", {
      code: DockerImageCode.fromImageAsset(".", {
        cmd: ["deal_dash.lambdas.scrapers.hidden_clearances.handler"],
      }),
      timeout: Duration.minutes(10),
      memorySize: 1024,
      environment: {
        DEALS_TABLE: dealsTable.tableName,
        HC_REFRESH_TOKEN_SECRET_ID: hcRefreshToken.secretName,
      },
    });

    dealsTable.grantWriteData(hiddenClearancesScraper);
    hcRefreshToken.grantRead(hiddenClearancesScraper);
    hcRefreshToken.grantWrite(hiddenClearancesScraper);

    new Rule(this, "HiddenClearancesScraperSchedule", {
      schedule: Schedule.cron({ minute: "0" }),
      targets: [new LambdaFunction(hiddenClearancesScraper)],
    });

    const rebelSavingsScraperV2 = new DockerImageFunction(this, "RebelSavingsScraperV2", {
      code: DockerImageCode.fromImageAsset(".", {
        cmd: ["deal_dash.lambdas.scrapers.rebel_savings_v2.handler"],
      }),
      timeout: Duration.minutes(10),
      memorySize: 1024,
      environment: {
        DEALS_TABLE: dealsTable.tableName,
      },
    });

    dealsTable.grantWriteData(rebelSavingsScraperV2);

    new Rule(this, "RebelSavingsScraperV2Schedule", {
      schedule: Schedule.cron({ minute: "30" }),
      targets: [new LambdaFunction(rebelSavingsScraperV2)],
    });
  }
}
