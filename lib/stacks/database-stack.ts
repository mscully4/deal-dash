import { RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import { AttributeType, BillingMode, StreamViewType, Table } from "aws-cdk-lib/aws-dynamodb";
import { Construct } from "constructs";

export class DatabaseStack extends Stack {
  public readonly dealsTable: Table;

  constructor(scope: Construct, id: string, props: StackProps) {
    super(scope, id, props);

    // Multi-source deals table (Rebel Savings + Hidden Clearances). Idle for
    // now — not wired to any Lambda or event source until the code cutover
    // in the multi-source-deals design doc ships.
    this.dealsTable = new Table(this, "DealDashDealsTable", {
      tableName: "deal-dash-deals",
      partitionKey: { name: "product_key", type: AttributeType.STRING },
      sortKey: { name: "store_key", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.RETAIN,
      stream: StreamViewType.NEW_IMAGE,
    });

    this.dealsTable.addGlobalSecondaryIndex({
      indexName: "retailer-category-index",
      partitionKey: { name: "retailer", type: AttributeType.STRING },
      sortKey: { name: "category", type: AttributeType.STRING },
    });
  }
}
