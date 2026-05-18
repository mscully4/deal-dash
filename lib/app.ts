#!/usr/bin/env node
import { App } from "aws-cdk-lib";
import { RebelSavingsStack } from "./stacks/rebel-savings-stack";
import { ACCOUNT_NO, REGION } from "./constants";

const app = new App();
const APP_NAME = "DealDash";

new RebelSavingsStack(app, `${APP_NAME}-RebelSavingsStack-${ACCOUNT_NO}-${REGION}`, {
  env: {
    region: REGION,
    account: ACCOUNT_NO,
  },
});

app.synth();
