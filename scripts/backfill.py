"""
Backfill Script - Populate DynamoDB with historical stock data.

This script fetches the last N days of stock data from Massive API
and populates DynamoDB so the dashboard shows data immediately after
a fresh deployment instead of waiting 7 days for the pipeline to run.

Usage:
    python scripts/backfill.py --days 7 --table stocks-pipeline-movers --region us-east-1
"""

import json
import argparse
import time
import urllib.request
import urllib.error
import boto3
from datetime import datetime, timedelta


WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"]
MAX_RETRIES = 3


def get_api_key_from_ssm(region):
    """Retrieve Massive API key from SSM Parameter Store."""
    ssm = boto3.client("ssm", region_name=region)
    response = ssm.get_parameter(
        Name="/stocks-pipeline/stock-api-key",
        WithDecryption=True
    )
    return response["Parameter"]["Value"]


def get_stock_data_for_date(ticker, date_str, api_key):
    """
    Fetch OHLC data for a specific date using the aggregates endpoint.
    date_str format: YYYY-MM-DD
    """
    url = f"https://api.massive.com/v2/aggs/ticker/{ticker}/range/1/day/{date_str}/{date_str}?apiKey={api_key}&adjusted=true"

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

                if data.get("resultsCount", 0) == 0:
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
            if e.code == 429:
                wait_time = 2 ** attempt
                print(f"  Rate limited. Waiting {wait_time}s...")
                time.sleep(wait_time)
            elif e.code == 401:
                print(f"  Unauthorized - check your API key")
                return None
            else:
                time.sleep(2 ** attempt)

        except Exception as e:
            print(f"  Error fetching {ticker} for {date_str}: {str(e)}")
            time.sleep(2 ** attempt)

    return None


def is_trading_day(date):
    """Check if a date is a weekday (basic check - excludes weekends)."""
    return date.weekday() < 5  # 0=Monday, 4=Friday


def backfill(days, table_name, region):
    """Main backfill function."""
    print(f"Starting backfill for last {days} trading days...")
    print(f"Table: {table_name} | Region: {region}")
    print("-" * 50)

    # Get API key
    print("Retrieving API key from SSM...")
    api_key = get_api_key_from_ssm(region)
    print("API key retrieved successfully")
    print("-" * 50)

    # Connect to DynamoDB
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    # Generate list of trading days to backfill
    trading_days = []
    current_date = datetime.now() - timedelta(days=1)  # Start from yesterday
    while len(trading_days) < days:
        if is_trading_day(current_date):
            trading_days.append(current_date)
        current_date -= timedelta(days=1)

    print(f"Backfilling {len(trading_days)} trading days:")
    for d in trading_days:
        print(f"  {d.strftime('%Y-%m-%d')}")
    print("-" * 50)

    # Process each trading day
    success_count = 0
    skip_count = 0

    for trade_date in trading_days:
        date_str = trade_date.strftime("%Y-%m-%d")
        print(f"\nProcessing {date_str}...")

        # Check if record already exists
        existing = table.get_item(Key={"date": date_str})
        if "Item" in existing:
            print(f"  Record already exists for {date_str} - skipping")
            skip_count += 1
            continue

        # Fetch data for each stock
        results = []
        for ticker in WATCHLIST:
            print(f"  Fetching {ticker}...")
            data = get_stock_data_for_date(ticker, date_str, api_key)
            if data:
                results.append(data)
            time.sleep(0.2)  # Small delay to avoid rate limiting

        if not results:
            print(f"  No data available for {date_str} - skipping")
            skip_count += 1
            continue

        # Find top mover
        top_mover = max(results, key=lambda x: abs(x["pct_change"]))
        print(f"  Top mover: {top_mover['ticker']} | {top_mover['pct_change']}% | ${top_mover['close']}")

        # Calculate TTL (90 days from now)
        ttl_timestamp = int(time.time()) + (90 * 24 * 60 * 60)

        # Save to DynamoDB
        table.put_item(Item={
            "date": date_str,
            "ticker": top_mover["ticker"],
            "pct_change": str(round(top_mover["pct_change"], 4)),
            "close_price": str(round(top_mover["close"], 4)),
            "ttl": ttl_timestamp
        })

        print(f"  Saved successfully!")
        success_count += 1

    print("\n" + "=" * 50)
    print(f"Backfill complete!")
    print(f"  Saved:   {success_count} records")
    print(f"  Skipped: {skip_count} records")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill stock pipeline DynamoDB table")
    parser.add_argument("--days", type=int, default=7, help="Number of trading days to backfill")
    parser.add_argument("--table", type=str, default="stocks-pipeline-movers", help="DynamoDB table name")
    parser.add_argument("--region", type=str, default="us-east-1", help="AWS region")
    args = parser.parse_args()

    backfill(args.days, args.table, args.region)