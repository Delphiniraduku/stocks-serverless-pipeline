# Stocks Serverless Pipeline

A fully automated serverless data pipeline that tracks daily top stock movers across a watchlist of tech stocks. The system wakes up daily, fetches stock data, records the biggest mover, and displays the history on a public website.

## Live Demo

- **Frontend:** http://stocks-pipeline-frontend-ebf685ce.s3-website-us-east-1.amazonaws.com
- **API Endpoint:** https://kczb47v9bb.execute-api.us-east-1.amazonaws.com/prod/movers

## Architecture
```
EventBridge (Cron) → Ingestion Lambda → DynamoDB
                                              ↑
Frontend (S3) → API Gateway → API Lambda ────┘
```

## Watchlist

AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA

## Tech Stack

- **IaC:** Terraform
- **Compute:** AWS Lambda (Python 3.11)
- **Scheduler:** Amazon EventBridge
- **Database:** Amazon DynamoDB
- **API:** Amazon API Gateway (REST)
- **Frontend:** AWS S3 Static Website Hosting
- **Stock Data:** Massive API
- **Secrets:** AWS SSM Parameter Store

## Prerequisites

- AWS CLI installed and configured
- Terraform v1.0+ installed
- Python 3.11+
- A free Massive API account and key

## Deployment Instructions

### 1. Clone the repository
```bash
git clone https://github.com/Delphiniraduku/stocks-serverless-pipeline.git
cd stocks-serverless-pipeline
```

### 2. Store your Massive API key in AWS SSM
```bash
aws ssm put-parameter \
  --name "/stocks-pipeline/stock-api-key" \
  --value "YOUR_MASSIVE_API_KEY" \
  --type "SecureString" \
  --region us-east-1
```

### 3. Deploy infrastructure with Terraform
```bash
cd infra
terraform init
terraform apply
```

Note the outputs — you will need the `api_endpoint` and `frontend_url` values.

### 4. Update the frontend API URL

In `frontend/index.html`, replace the `API_URL` value with your `api_endpoint` output from Terraform.

### 5. Upload the frontend to S3
```bash
aws s3 cp frontend/index.html s3://YOUR_BUCKET_NAME/index.html --region us-east-1
```

Replace `YOUR_BUCKET_NAME` with the bucket name from Terraform outputs.

## How It Works

1. **EventBridge** triggers the ingestion Lambda every day at 9PM UTC (after market close)
2. **Ingestion Lambda** fetches the previous day OHLC data for each stock in the watchlist from the Massive API
3. It calculates the % change using `((Close - Open) / Open) * 100` and finds the stock with the highest absolute % change
4. The winner is saved to **DynamoDB** with the date, ticker, % change, and close price
5. The **API Lambda** is triggered by API Gateway when the frontend calls `GET /movers`
6. It retrieves the last 7 days of winners from DynamoDB and returns them as JSON
7. The **Frontend** fetches the data and displays it in a table with green/red color coding

## Security

- API keys are stored in AWS SSM Parameter Store, never in code
- `.gitignore` excludes all sensitive files
- IAM roles follow least privilege — Lambda only has the exact permissions it needs

## Trade-offs & Challenges

- **Terraform local state** — used local state for simplicity. In production, state should be stored in S3 with DynamoDB locking for team collaboration
- **DynamoDB key design** — using date as the partition key means only one winner per day can be stored, which is exactly what the project requires
- **Previous day data** — the Massive API `/prev` endpoint is used instead of same-day data to ensure complete market data is always available after close
- **SSM vs Secrets Manager** — SSM Parameter Store (SecureString) was chosen over Secrets Manager because it is free tier, while Secrets Manager costs $0.40/month per secret