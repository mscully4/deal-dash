import { CfnResource, Duration, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import { AttributeType, BillingMode, StreamViewType, Table } from "aws-cdk-lib/aws-dynamodb";
import { Effect, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Code, Function, Runtime, StartingPosition } from "aws-cdk-lib/aws-lambda";
import { DynamoEventSource } from "aws-cdk-lib/aws-lambda-event-sources";
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

    const vectorBucket = new CfnResource(this, "VectorBucket", {
      type: "AWS::S3Vectors::VectorBucket",
      properties: { VectorBucketName: "deal-dash-vectors" },
    });

    const vectorIndex = new CfnResource(this, "VectorIndex", {
      type: "AWS::S3Vectors::VectorIndex",
      properties: {
        VectorBucketName: "deal-dash-vectors",
        VectorIndexName: "deals",
        DataType: "float32",
        Dimension: 256,
        DistanceMetric: "cosine",
      },
    });
    vectorIndex.addDependency(vectorBucket);

    const embedder = new Function(this, "EmbedderLambda", {
      runtime: Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: Code.fromAsset("src/deal_dash/lambdas/embedder"),
      timeout: Duration.seconds(60),
      environment: {
        VECTOR_BUCKET_NAME: "deal-dash-vectors",
        VECTOR_INDEX_NAME: "deals",
      },
    });

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
        actions: ["s3vectors:PutVectors"],
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
  }
}
