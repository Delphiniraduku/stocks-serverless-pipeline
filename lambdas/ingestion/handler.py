import json
import os
import boto3
import urllib.request
import urllib.error
import time
from datetime import datetime

# Constants
WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"]
SSM_API_KEY = os.environ.get("SSM_API_KEY")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE")
AWS_REGION_NAME = os.environ.get("AWS_REGION_NAME", "us-east-1")
MAX_RETRIES = 3


def get_api_key():
    """Retrieve API key from SSM Parameter Store."""
    ssm = boto3.client("ssm", region_name=AWS_REGION_NAME)
    response = ssm.get_parameter(Name=SSM_API_KEY, WithDecryption=True)
    return response["Parameter"]["Value"]


def get_stock_data(ticker, api_key):
    """
    Fetch previous day OHLC data for a single ticker from Massive.
    Implements exponential backoff retry logic to handle API failures
    and rate limiting gracefully.
    """
    url = f"https://api.massive.com/v2/aggs/ticker/{ticker}/prev?apiKey={api_key}"

    for attempt in range(MAX_RETRIES):
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

        except urllib.error.HTTPError as e:
            # Handle rate limiting specifically
            if e.code == 429:
                wait_time = 2 ** attempt
                print(f"Rate limited on {ticker}. Attempt {attempt + 1}/{MAX_RETRIES}. Waiting {wait_time}s...")
                time.sleep(wait_time)
            # Handle unauthorized separately - no point retrying
            elif e.code == 401:
                print(f"Unauthorized for {ticker}. Check your API key.")
                return None
            else:
                wait_time = 2 ** attempt
                print(f"HTTP {e.code} error for {ticker}. Attempt {attempt + 1}/{MAX_RETRIES}. Waiting {wait_time}s...")
                time.sleep(wait_time)

        except urllib.error.URLError as e:
            # Handle network errors
            wait_time = 2 ** attempt
            print(f"Network error for {ticker}: {e.reason}. Attempt {attempt + 1}/{MAX_RETRIES}. Waiting {wait_time}s...")
            time.sleep(wait_time)

        except Exception as e:
            # Handle any other unexpected errors
            print(f"Unexpected error for {ticker}: {str(e)}. Attempt {attempt + 1}/{MAX_RETRIES}.")
            time.sleep(2 ** attempt)

    print(f"All {MAX_RETRIES} attempts failed for {ticker}. Skipping.")
    return None


def save_to_dynamodb(date, ticker, pct_change, close_price):
    """Save the top mover to DynamoDB with TTL of 90 days."""
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION_NAME)
    table = dynamodb.Table(DYNAMODB_TABLE)

    # Calculate TTL as Unix timestamp 90 days from now
    ttl_timestamp = int(time.time()) + (90 * 24 * 60 * 60)

    table.put_item(Item={
        "date": date,
        "ticker": ticker,
        "pct_change": str(round(pct_change, 4)),
        "close_price": str(round(close_price, 4)),
        "ttl": ttl_timestamp
    })

    print(f"Saved to DynamoDB: {date} | {ticker} | {pct_change}% | ${close_price} | TTL: 90 days")

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

    # Step 2: Fetch data for each stock with retry logic
    results = []
    failed_tickers = []

    for ticker in WATCHLIST:
        print(f"Fetching data for {ticker}...")
        data = get_stock_data(ticker, api_key)
        if data:
            results.append(data)
        else:
            failed_tickers.append(ticker)

    # Log which tickers failed
    if failed_tickers:
        print(f"Warning: Failed to retrieve data for: {', '.join(failed_tickers)}")

    # If every single ticker failed, abort
    if not results:
        print("No stock data retrieved for any ticker - aborting")
        return {"statusCode": 500, "body": "No stock data retrieved"}

    # Step 3: Find the top mover by absolute % change
    top_mover = max(results, key=lambda x: abs(x["pct_change"]))
    print(f"Top mover: {top_mover['ticker']} with {top_mover['pct_change']}% change")
    print(f"Calculated from {len(results)}/{len(WATCHLIST)} stocks successfully fetched")

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
            "close_price": top_mover["close"],
            "stocks_fetched": len(results),
            "stocks_failed": len(failed_tickers),
            "failed_tickers": failed_tickers
        })
    }