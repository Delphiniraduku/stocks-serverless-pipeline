import json
import os
import boto3
import urllib.request
from datetime import datetime, timedelta

# Constants
WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"]
SSM_API_KEY = os.environ.get("SSM_API_KEY")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE")
AWS_REGION_NAME = os.environ.get("AWS_REGION_NAME", "us-east-1")


def get_api_key():
    """Retrieve API key from SSM Parameter Store."""
    ssm = boto3.client("ssm", region_name=AWS_REGION_NAME)
    response = ssm.get_parameter(Name=SSM_API_KEY, WithDecryption=True)
    return response["Parameter"]["Value"]


def get_stock_data(ticker, api_key):
    """Fetch previous day OHLC data for a single ticker from Massive."""
    url = f"https://api.massive.com/v2/aggs/ticker/{ticker}/prev?apiKey={api_key}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

            if data.get("resultsCount", 0) == 0:
                print(f"No data returned for {ticker}")
                return None

            result = data["results"][0]
            open_price = result["o"]
            close_price = result["c"]
            pct_change = ((close_price - open_price) / open_price) * 100

            return {
                "ticker": ticker,
                "open": open_price,
                "close": close_price,
                "pct_change": round(pct_change, 4)
            }

    except Exception as e:
        print(f"Error fetching data for {ticker}: {str(e)}")
        return None

    except Exception as e:
        print(f"Error fetching data for {ticker}: {str(e)}")
        return None


def save_to_dynamodb(date, ticker, pct_change, close_price):
    """Save the top mover to DynamoDB."""
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION_NAME)
    table = dynamodb.Table(DYNAMODB_TABLE)

    table.put_item(Item={
        "date": date,
        "ticker": ticker,
        "pct_change": str(round(pct_change, 4)),
        "close_price": str(round(close_price, 4))
    })

    print(f"Saved to DynamoDB: {date} | {ticker} | {pct_change}% | ${close_price}")


def lambda_handler(event, context):
    """Main Lambda handler."""
    print("Starting ingestion Lambda...")

    # Step 1: Get API key from SSM
    try:
        api_key = get_api_key()
        print("Successfully retrieved API key from SSM")
    except Exception as e:
        print(f"Failed to retrieve API key: {str(e)}")
        return {"statusCode": 500, "body": "Failed to retrieve API key"}

    # Step 2: Fetch data for each stock
    results = []
    for ticker in WATCHLIST:
        print(f"Fetching data for {ticker}...")
        data = get_stock_data(ticker, api_key)
        if data:
            results.append(data)

    if not results:
        print("No stock data retrieved for any ticker")
        return {"statusCode": 500, "body": "No stock data retrieved"}

    # Step 3: Find the top mover by absolute % change
    top_mover = max(results, key=lambda x: abs(x["pct_change"]))
    print(f"Top mover: {top_mover['ticker']} with {top_mover['pct_change']}% change")

    # Step 4: Save to DynamoDB
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        save_to_dynamodb(
            date=today,
            ticker=top_mover["ticker"],
            pct_change=top_mover["pct_change"],
            close_price=top_mover["close"]
        )
    except Exception as e:
        print(f"Failed to save to DynamoDB: {str(e)}")
        return {"statusCode": 500, "body": "Failed to save to DynamoDB"}

    print("Ingestion complete!")
    return {
        "statusCode": 200,
        "body": json.dumps({
            "date": today,
            "top_mover": top_mover["ticker"],
            "pct_change": top_mover["pct_change"],
            "close_price": top_mover["close"]
        })
    }