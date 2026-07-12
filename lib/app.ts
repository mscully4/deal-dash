#!/usr/bin/env node
import { App } from "aws-cdk-lib";
import { DatabaseStack } from "./stacks/database-stack";
import { DealConsumerStack } from "./stacks/deal-consumer-stack";
import { DealScraperStack } from "./stacks/deal-scraper-stack";
import { RebelSavingsStack } from "./stacks/rebel-savings-stack";
import { ACCOUNT_NO, REGION } from "./constants";

const app = new App();
const APP_NAME = "DealDash";

const databaseStack = new DatabaseStack(app, `${APP_NAME}-DatabaseStack-${ACCOUNT_NO}-${REGION}`, {
  env: {
    region: REGION,
    account: ACCOUNT_NO,
  },
});

new DealScraperStack(app, `${APP_NAME}-DealScraperStack-${ACCOUNT_NO}-${REGION}`, {
  env: {
    region: REGION,
    account: ACCOUNT_NO,
  },
  dealsTable: databaseStack.dealsTable,
});

new RebelSavingsStack(app, `${APP_NAME}-RebelSavingsStack-${ACCOUNT_NO}-${REGION}`, {
  env: {
    region: REGION,
    account: ACCOUNT_NO,
  },
});

new DealConsumerStack(app, `${APP_NAME}-DealConsumerStack-${ACCOUNT_NO}-${REGION}`, {
  env: {
    region: REGION,
    account: ACCOUNT_NO,
  },
  dealsTable: databaseStack.dealsTable,
});

app.synth();
