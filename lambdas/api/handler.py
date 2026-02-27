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


def get_last_7_days():
    """Generate a list of the last 7 days as strings."""
    dates = []
    for i in range(7):
        date = datetime.now() - timedelta(days=i)
        dates.append(date.strftime("%Y-%m-%d"))
    return dates


def lambda_handler(event, context):
    """Main Lambda handler - returns last 7 days of top movers."""
    print("Starting API Lambda...")

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION_NAME)
    table = dynamodb.Table(DYNAMODB_TABLE)

    # Get last 7 days of dates
    dates = get_last_7_days()
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