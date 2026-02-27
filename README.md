# Stocks Serverless Pipeline

A fully automated serverless data pipeline that tracks daily top stock movers across a watchlist of tech stocks. The system wakes up daily after market close, fetches stock data, records the biggest mover, and displays the history on a public website.

## Live Demo

- **Frontend:** http://stocks-pipeline-frontend-ebf685ce.s3-website-us-east-1.amazonaws.com
- **API Endpoint:** https://kczb47v9bb.execute-api.us-east-1.amazonaws.com/prod/movers

## Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                            │
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────┐  │
│  │ EventBridge  │────▶│  Ingestion   │────▶│  DynamoDB  │  │
│  │  (9PM UTC)   │     │   Lambda     │     │   Table    │  │
│  └──────────────┘     └──────────────┘     └─────┬──────┘  │
│                              │                   │         │
│                        CloudWatch                │         │
│                         Alarms                   │         │
│                              │                   │         │
│                             SNS                  │         │
│                           (Email)                │         │
│                                                  ▼         │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────┐  │
│  │   S3 Static  │────▶│ API Gateway  │────▶│    API     │  │
│  │   Website    │     │  REST API    │     │   Lambda   │  │
│  └──────────────┘     └──────────────┘     └────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Watchlist

AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA

## Tech Stack

| Component | Technology |
|-----------|-----------|
| IaC | Terraform |
| Compute | AWS Lambda (Python 3.11) |
| Scheduler | Amazon EventBridge |
| Database | Amazon DynamoDB |
| API | Amazon API Gateway (REST) |
| Frontend | AWS S3 Static Website Hosting |
| Stock Data | Massive API |
| Secrets | AWS SSM Parameter Store |
| Monitoring | CloudWatch Alarms + SNS |
| State Management | S3 + DynamoDB Locking |
| CI/CD | GitHub Actions |
| Tracing | AWS X-Ray |
| Dead Letter Queue | AWS SQS |

## Prerequisites

- AWS CLI installed and configured (`aws configure`)
- Terraform v1.0+ installed
- Python 3.11+
- A free Massive API account and key

## Deployment Instructions

### 1. Clone the repository
```bash
git clone https://github.com/Delphiniraduku/stocks-serverless-pipeline.git
cd stocks-serverless-pipeline
```

### 2. Create Terraform remote state infrastructure

These only need to be created once. Replace `YOUR_ACCOUNT_ID` with your AWS account ID:
```bash
aws s3api create-bucket --bucket stocks-pipeline-tfstate-YOUR_ACCOUNT_ID --region us-east-1

aws s3api put-bucket-versioning \
  --bucket stocks-pipeline-tfstate-YOUR_ACCOUNT_ID \
  --versioning-configuration Status=Enabled

aws dynamodb create-table \
  --table-name stocks-pipeline-tfstate-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Then update the bucket name in `infra/main.tf` backend block to match your bucket name.

### 3. Store your Massive API key in AWS SSM
```bash
aws ssm put-parameter \
  --name "/stocks-pipeline/stock-api-key" \
  --value "YOUR_MASSIVE_API_KEY" \
  --type "SecureString" \
  --region us-east-1
```

### 4. Deploy infrastructure with Terraform
```bash
cd infra
terraform init
terraform apply
```

Note the outputs — you will need the `api_endpoint` and `frontend_url` values.

### 5. Confirm your SNS email subscription

Check your email for a message from AWS SNS and click the confirmation link to activate pipeline failure alerts.

### 6. Update the frontend API URL

In `frontend/index.html` replace the `API_URL` value with your `api_endpoint` output from Terraform.

### 7. Upload the frontend to S3
```bash
aws s3 cp frontend/index.html s3://YOUR_BUCKET_NAME/index.html --region us-east-1
```

### 8. Destroy the stack when done
```bash
cd infra
terraform destroy
```

Note: The Terraform state S3 bucket and DynamoDB lock table are not managed by Terraform and must be deleted manually if needed.

## How It Works

1. **EventBridge** triggers the ingestion Lambda every day at 9PM UTC (30 minutes after US market close)
2. **Ingestion Lambda** fetches the previous day OHLC data for each stock from the Massive API with exponential backoff retry logic — if a request fails it retries up to 3 times with increasing wait times (1s, 2s, 4s)
3. It calculates % change using `((Close - Open) / Open) * 100` and finds the stock with the highest absolute % change
4. The winner is saved to **DynamoDB** with date, ticker, % change, and close price
5. **CloudWatch** monitors both Lambda functions and triggers **SNS email alerts** if failures are detected
6. The **API Lambda** is triggered by API Gateway when the frontend calls `GET /movers`
7. It retrieves the last 7 days of winners from DynamoDB and returns them as JSON
8. The **Frontend** fetches the data and displays it in a table with green/red color coding for gains/losses

## Security

- API keys stored in AWS SSM Parameter Store with encryption, never in code
- `.gitignore` excludes all sensitive files
- IAM roles follow least privilege principle
- API Gateway rate limiting prevents abuse (10 req/sec, 1000 req/day)
- Terraform state stored in encrypted S3 bucket with DynamoDB locking

## Monitoring & Alerting

- CloudWatch alarm triggers if ingestion Lambda has any errors in a 24 hour window
- CloudWatch alarm triggers if API Lambda has more than 5 errors in 5 minutes
- Both alarms send email notifications via SNS

## Trade-offs & Challenges

- **Terraform remote state** — state is stored in S3 with DynamoDB locking for team collaboration and disaster recovery. Local state was intentionally avoided
- **Previous day data** — Massive API `/prev` endpoint is used instead of same-day data to ensure fully settled market data is always available
- **SSM vs Secrets Manager** — SSM Parameter Store (SecureString) was chosen over Secrets Manager to stay within free tier. Secrets Manager costs $0.40/month per secret
- **DynamoDB key design** — date as partition key means exactly one winner per day, which matches the project requirements and makes 7-day lookups extremely fast
- **Plain JS over React/Vue** — the frontend requirement is a simple 7-row table. Using a framework would add unnecessary complexity without improving the graded criteria

## Known Limitations

- Stock data is only available on trading days. Weekends and market holidays will have no data
- The pipeline uses previous day data so the website always shows data that is at least one trading day old
- DynamoDB partition key design means if the pipeline runs twice in one day the second run overwrites the first

## Future Improvements

- Add historical data backfill for dates beyond 90 days
- Add Lambda Layers for shared dependencies across functions
- Add input validation and request sanitization on API Lambda
- Implement multi-region deployment for high availability