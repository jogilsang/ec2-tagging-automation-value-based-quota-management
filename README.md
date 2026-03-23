# EC2 Tagging Automation with Value-Based Quota Management

An automated solution that manages EC2 instance tags by type with value-based quota allocation and provides real-time SNS notifications for tag distribution and instance count monitoring.

## 📋 Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Deployed Resources](#deployed-resources)
- [Key Features](#key-features)
- [Use Cases](#use-cases)
- [Deployment](#deployment)
- [Configuration](#configuration)
- [Monitoring](#monitoring)

## Overview

This solution automatically assigns tags to specific EC2 instance types (e.g., GPU instances) and maintains predefined quotas for each tag value in your AWS environment.

### Core Benefits
- ✅ **Automatic Tagging**: Detects and tags untagged instances automatically
- ✅ **Quota Tracking**: Real-time monitoring of instance counts per tag value
- ✅ **Instant Alerts**: SNS notifications for quota excess/shortage
- ✅ **State Management**: S3-based state storage to prevent duplicate notifications

## Architecture

```
┌─────────────────┐
│  EventBridge    │  (Triggers every 1 minute)
│   Schedule      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│  Lambda         │─────▶│  EC2 API     │ (Query & Tag Instances)
│  Function       │      └──────────────┘
└────────┬────────┘
         │
         ├─────────────▶ ┌──────────────┐
         │               │  S3 Bucket   │ (State Storage)
         │               └──────────────┘
         │
         └─────────────▶ ┌──────────────┐
                         │  SNS Topic   │ (Email Alerts)
                         └──────────────┘
```

## Deployed Resources

### 1. **Lambda Function** (`ec2-monitoring-tagging`)
- **Runtime**: Python 3.9
- **Timeout**: 300 seconds
- **Role**: Query EC2 instances, apply tags, manage state, send notifications

### 2. **EventBridge Rule**
- **Schedule**: Runs every 1 minute (`rate(1 minute)`)
- **Role**: Periodically triggers Lambda function

### 3. **S3 Bucket** (`StateStorageBucket`)
- **Encryption**: AES256
- **Role**: Store previous state for change detection
- **File**: `map_tagging_state.json`

### 4. **SNS Topic** (`ec2-monitoring-alerts`)
- **Role**: Send email notifications
- **Subscribers**: Email addresses specified in environment variables

### 5. **IAM Role** (`EC2MonitoringRole`)
- **Permissions**:
  - EC2: `DescribeInstances`, `CreateTags`
  - SNS: `CreateTopic`, `Subscribe`, `Publish`, `ListSubscriptionsByTopic`
  - S3: `GetObject`, `PutObject`
  - CloudWatch Logs: Write logs

## Key Features

### 1. Instance Count Monitoring
- Checks running instances of specified type
- Compares with expected count and detects excess/shortage

### 2. Automatic Tagging
- Automatically detects untagged instances
- Assigns tags based on value quota limits and priority order
- Corrects instances with invalid tag values

### 3. Tag Quota Management
- Maximum count limit per tag value
- Priority: Array order (first value has priority)
- Example: `[Value1, Value2, Value3]` → Assigns Value2 when Value1 reaches max

### 4. Smart Notifications
- Sends alerts only when state changes (prevents spam)
- Includes detailed status information (table format)
- Clear distinction between normal/abnormal states

## Use Cases

### Scenario 1: Environment-Based Instance Allocation

**Situation**: 3 environments (prd, stg, dev) each using 2 instances, total 6 t3.micro instances

**Configuration**:
```yaml
INSTANCE_TYPE: t3.micro
TOTAL_COUNT: 6
MAP_TAGGING_KEY: env
MAP_TAGGING_VALUES: prd,stg,dev
MAP_TAGGING_VALUES_MAX_COUNT: 2
```

**Behavior**:
1. Checks if 6 instances are in Running state
2. Assigns 2 tags per environment
3. Auto-tags untagged instances when detected
4. Sends SNS alert on count mismatch

**Alert Example**:
```
✅ NORMAL STATUS
Timestamp: 2026-03-23 05:00:00 UTC

📊 Instance Count: 6/6

🏷️  Tag Distribution:
Tag Value                 Count      Status         
--------------------------------------------------
prd                      2          ✅ OK          
stg                      2          ✅ OK          
dev                      2          ✅ OK          
```

### Scenario 2: GPU Instance Project Allocation

**Situation**: 3 projects each using 12 instances, total 36 p5en.48xlarge instances

**Configuration**:
```yaml
INSTANCE_TYPE: p5en.48xlarge
TOTAL_COUNT: 36
MAP_TAGGING_KEY: project-code
MAP_TAGGING_VALUES: PROJECT-A,PROJECT-B,PROJECT-C
MAP_TAGGING_VALUES_MAX_COUNT: 12
```

### Scenario 3: Instance Shortage Detection

**Situation**: 2 out of 6 instances terminated

**Alert**:
```
⚠️ ALERT: Action Required
Timestamp: 2026-03-23 05:05:00 UTC

📊 Instance Count: 4/6
   ⚠️ SHORT by 2 instances

🏷️  Tag Distribution:
Tag Value                 Count      Status         
--------------------------------------------------
prd                      2          ✅ OK          
stg                      1          ⚠️ 1/2         
dev                      1          ⚠️ 1/2         
```

### Scenario 4: Automatic Untagged Instance Handling

**Situation**: 3 new instances started without tags

**Alert**:
```
⚠️ ALERT: Action Required
Timestamp: 2026-03-23 05:10:00 UTC

📊 Instance Count: 6/6

🏷️  Tag Distribution:
Tag Value                 Count      Status         
--------------------------------------------------
prd                      2          ✅ OK          
stg                      2          ✅ OK          
dev                      2          ✅ OK          

✏️  Auto-Tagged 3 instances:
   • i-0abc123def456 → prd
   • i-0abc123def457 → prd
   • i-0abc123def458 → stg
```

## Deployment

### Prerequisites
- AWS CLI installed and configured
- Appropriate IAM permissions (CloudFormation, Lambda, EC2, SNS, S3, IAM)
- Bash shell environment

### 1. Run Deployment Script

```bash
cd deploy
chmod +x deploy.sh
./deploy.sh
```

### 2. CloudFormation Parameters

Configure the following parameters during deployment or use defaults:

| Parameter | Default | Description |
|-----------|---------|-------------|
| AccountId | 123456789012 | AWS Account ID |
| Region | us-east-1 | Target region |
| InstanceType | p5en.48xlarge | Instance type to monitor |
| TotalCount | 36 | Expected total instance count |
| AlertEmails | admin@example.com,ops@example.com | Alert email addresses (comma-separated) |

### 3. Confirm SNS Subscription

After deployment, SNS subscription confirmation emails will be sent to specified addresses.
**You must click "Confirm subscription" link** to activate notifications.

### 4. Verify Deployment

```bash
# Check Lambda function
aws lambda get-function --function-name ec2-monitoring-tagging --region us-east-1

# Check EventBridge rule
aws events describe-rule --name <StackName>-ScheduleRule-<ID> --region us-east-1

# Check S3 bucket
aws s3 ls | grep ec2-tagging-state
```

## Configuration

### Method 1: Update CloudFormation Stack

```bash
aws cloudformation update-stack \
  --stack-name ec2-tagging-automation \
  --use-previous-template \
  --parameters \
    ParameterKey=InstanceType,ParameterValue=t3.medium \
    ParameterKey=TotalCount,ParameterValue=30 \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### Method 2: Update Lambda Environment Variables

```bash
aws lambda update-function-configuration \
  --function-name ec2-monitoring-tagging \
  --environment Variables="{
    ACCOUNT_ID=123456789012,
    REGION=us-east-1,
    INSTANCE_TYPE=t3.medium,
    TOTAL_COUNT=30,
    MAP_TAGGING_KEY=Environment,
    MAP_TAGGING_VALUES=dev,staging,prod,
    MAP_TAGGING_VALUES_MAX_COUNT=10,
    ALERT_EMAILS=admin@example.com,
    STATE_BUCKET=<your-bucket-name>
  }" \
  --region us-east-1
```

### Key Configuration Options

| Environment Variable | Description | Example |
|---------------------|-------------|---------|
| INSTANCE_TYPE | Instance type to monitor | `p5en.48xlarge`, `t3.medium` |
| TOTAL_COUNT | Expected total instance count | `36`, `30` |
| MAP_TAGGING_KEY | Tag key name | `project-code`, `Environment` |
| MAP_TAGGING_VALUES | Tag value list (comma-separated) | `PROJECT-A,PROJECT-B,PROJECT-C` |
| MAP_TAGGING_VALUES_MAX_COUNT | Max count per value | `12`, `10` |
| ALERT_EMAILS | Alert email addresses (comma-separated) | `admin@example.com,ops@example.com` |

## Monitoring

### CloudWatch Logs

```bash
# Tail recent logs
aws logs tail /aws/lambda/ec2-monitoring-tagging --follow --region us-east-1

# Query logs for specific time range
aws logs filter-log-events \
  --log-group-name /aws/lambda/ec2-monitoring-tagging \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --region us-east-1
```

### S3 State File

```bash
# Check current state
aws s3 cp s3://<bucket-name>/map_tagging_state.json - | jq .
```

**State File Example**:
```json
{
  "timestamp": "2026-03-23T04:30:00.123456",
  "instanceCount": 36,
  "taggedInstances": {
    "PROJECT-A": 12,
    "PROJECT-B": 12,
    "PROJECT-C": 12
  }
}
```

### Manual Execution (Testing)

```bash
# Manually invoke Lambda function
aws lambda invoke \
  --function-name ec2-monitoring-tagging \
  --region us-east-1 \
  response.json

# Check result
cat response.json | jq .
```

## Troubleshooting

### Not Receiving Alerts
1. Verify SNS subscription confirmation email was clicked
2. Check email spam folder
3. Review CloudWatch Logs for errors

### Tags Not Applied
1. Verify Lambda IAM Role has `ec2:CreateTags` permission
2. Confirm instances are in Running state
3. Check CloudWatch Logs for error messages

### Duplicate Alerts
1. Verify state file is being saved to S3 bucket
2. Check Lambda IAM Role has S3 permissions

## Cost Estimate

| Service | Usage | Monthly Cost (us-east-1) |
|---------|-------|-------------------------|
| Lambda | 43,200 executions/month (every 1 minute) | ~$0.01 |
| S3 | State file storage | ~$0.01 |
| SNS | Email notifications (on changes only) | ~$0.01 |
| CloudWatch Logs | Log storage | ~$0.50 |
| **Total** | | **~$0.53/month** |

## License

This project is for internal use.

## Support

For questions or issues:
- Email: admin@example.com
- Contact project administrator
