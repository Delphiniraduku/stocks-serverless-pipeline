import json
import os
import boto3
from datetime import datetime, timedelta
from decimal import Decimal

# Constants
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE")
AWS_REGION_NAME = os.environ.get("AWS_REGION_NAME", "us-east-1")


class DecimalEncoder(json.JSONEncoder):
    """Handle DynamoDB Decimal types for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def get_last_7_trading_days():
    """Generate a list of the last 7 trading days, skipping weekends."""
    trading_days = []
    current_date = datetime.now()

    while len(trading_days) < 7:
        current_date -= timedelta(days=1)
        # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        if current_date.weekday() < 5:
            trading_days.append(current_date.strftime("%Y-%m-%d"))

    return trading_days


def lambda_handler(event, context):
    """Main Lambda handler - returns last 7 trading days of top movers."""
    print("Starting API Lambda...")

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION_NAME)
    table = dynamodb.Table(DYNAMODB_TABLE)

    # Get last 7 trading days (skipping weekends)
    dates = get_last_7_trading_days()
    results = []

    for date in dates:
        try:
            response = table.get_item(Key={"date": date})
            if "Item" in response:
                item = response["Item"]
                # Remove TTL field from response - frontend doesn't need it
                item.pop("ttl", None)
                results.append(item)
        except Exception as e:
            print(f"Error fetching data for {date}: {str(e)}")

    # Sort by date descending (most recent first)
    results.sort(key=lambda x: x["date"], reverse=True)

    print(f"Returning {len(results)} records")

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        },
        "body": json.dumps(results, cls=DecimalEncoder)
    }