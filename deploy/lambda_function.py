import boto3
import json
import os
from typing import Dict, List, Tuple, Optional

def lambda_handler(event, context):
    # Environment variables
    ACCOUNT_ID = os.environ['ACCOUNT_ID']
    REGION = os.environ['REGION']
    INSTANCE_TYPE = os.environ['INSTANCE_TYPE']
    TOTAL_COUNT = int(os.environ['TOTAL_COUNT'])
    MAP_TAGGING_KEY = os.environ['MAP_TAGGING_KEY']
    MAP_TAGGING_VALUES = os.environ['MAP_TAGGING_VALUES'].split(',')
    MAP_TAGGING_VALUES_MAX_COUNT = int(os.environ['MAP_TAGGING_VALUES_MAX_COUNT'])
    ALERT_EMAILS = os.environ['ALERT_EMAILS'].split(',')
    STATE_BUCKET = os.environ.get('STATE_BUCKET', 'ec2-tagging-state-bucket')
    STATE_KEY = 'map_tagging_state.json'
    
    # Initialize AWS clients
    ec2 = boto3.client('ec2', region_name=REGION)
    sns = boto3.client('sns', region_name=REGION)
    s3 = boto3.client('s3', region_name=REGION)
    
    try:
        # Load previous state
        previous_state = load_previous_state(s3, STATE_BUCKET, STATE_KEY)
        
        # Get all instances of specified type
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'instance-type', 'Values': [INSTANCE_TYPE]},
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )
        
        instances = []
        for reservation in response['Reservations']:
            instances.extend(reservation['Instances'])
        
        running_count = len(instances)
        alerts = []
        
        # Check if running count matches total count
        if running_count != TOTAL_COUNT:
            alerts.append(f"Instance count mismatch: Expected {TOTAL_COUNT}, Found {running_count} running instances")
        
        # Check and apply tagging
        tag_distribution = {value: [] for value in MAP_TAGGING_VALUES}
        untagged_instances = []
        incorrectly_tagged_instances = []
        
        for instance in instances:
            instance_id = instance['InstanceId']
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
            
            if MAP_TAGGING_KEY in tags:
                tag_value = tags[MAP_TAGGING_KEY]
                if tag_value in tag_distribution:
                    # Valid tag value
                    tag_distribution[tag_value].append(instance_id)
                else:
                    # Invalid tag value (like 'aaa'), treat as untagged
                    incorrectly_tagged_instances.append(f"{instance_id} (current: {tag_value})")
                    untagged_instances.append(instance_id)
            else:
                # No tag at all
                untagged_instances.append(instance_id)
        
        # Apply tags to untagged instances
        tagged_instances = []
        for instance_id in untagged_instances:
            # Find the tag value with lowest count (priority by index)
            target_value = None
            for value in MAP_TAGGING_VALUES:
                if len(tag_distribution[value]) < MAP_TAGGING_VALUES_MAX_COUNT:
                    target_value = value
                    break
            
            if target_value:
                ec2.create_tags(
                    Resources=[instance_id],
                    Tags=[{'Key': MAP_TAGGING_KEY, 'Value': target_value}]
                )
                tag_distribution[target_value].append(instance_id)
                tagged_instances.append(f"{instance_id} -> {target_value}")
        
        # Check final tag distribution
        total_tagged = sum(len(v) for v in tag_distribution.values())
        if total_tagged != TOTAL_COUNT:
            alerts.append(f"Tag distribution issue: Total tagged {total_tagged}, Expected {TOTAL_COUNT}")
        
        # Create current state
        current_state = {
            "timestamp": context.aws_request_id + "_" + str(int(context.get_remaining_time_in_millis())),
            "instanceCount": running_count,
            "taggedInstances": {k: len(v) for k, v in tag_distribution.items()}
        }
        
        # Compare states and send notification only if there are changes
        should_notify = states_are_different(previous_state, current_state)
        
        if should_notify and (alerts or tagged_instances or previous_state is None):
            message_parts = []
            
            if not alerts and tagged_instances:
                message_parts.append("✅ NORMAL: All instances running and properly tagged")
            elif not alerts and not tagged_instances:
                message_parts.append("✅ NORMAL: System status unchanged")
            else:
                message_parts.append("⚠️ ALERT: Issues detected")
                message_parts.extend(alerts)
            
            message_parts.append(f"\nCurrent Status:")
            message_parts.append(f"- Running instances: {running_count}/{TOTAL_COUNT}")
            tag_dist_str = ', '.join([f"'{k}': {len(v)}" for k, v in tag_distribution.items()])
            message_parts.append(f"- Tag distribution: {{{tag_dist_str}}}")
            
            # Show all tagged instances with their values
            message_parts.append(f"\nTagged instances:")
            for value in MAP_TAGGING_VALUES:
                for instance_id in tag_distribution[value]:
                    message_parts.append(f"{instance_id} -> {value}")
            
            # Show untagged instances if any
            if untagged_instances:
                message_parts.append(f"\n⚠️ Untagged instances ({len(untagged_instances)}):")
                for instance_id in untagged_instances:
                    message_parts.append(f"{instance_id}")
            
            if incorrectly_tagged_instances:
                message_parts.append(f"\nCorrected incorrectly tagged instances:")
                message_parts.extend(incorrectly_tagged_instances)
            
            alert_message = "\n".join(message_parts)
            
            # Send SNS notification
            send_alert(sns, alert_message, ALERT_EMAILS)
        else:
            print("No significant changes detected, skipping notification")
        
        # Save current state
        save_current_state(s3, STATE_BUCKET, STATE_KEY, current_state)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'running_count': running_count,
                'tag_distribution': {k: len(v) for k, v in tag_distribution.items()},
                'tagged_instances': len(tagged_instances)
            })
        }
        
    except Exception as e:
        error_message = f"Error in EC2 monitoring: {str(e)}"
        send_alert(sns, error_message, ALERT_EMAILS)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': error_message})
        }

def load_previous_state(s3_client, bucket: str, key: str) -> Optional[Dict]:
    """Load previous state from S3"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except s3_client.exceptions.NoSuchKey:
        print("No previous state found, treating as first run")
        return None
    except Exception as e:
        print(f"Error loading previous state: {str(e)}")
        return None

def save_current_state(s3_client, bucket: str, key: str, state: Dict):
    """Save current state to S3"""
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(state, indent=2),
            ContentType='application/json'
        )
        print("State saved successfully")
    except Exception as e:
        print(f"Error saving state: {str(e)}")

def states_are_different(previous: Optional[Dict], current: Dict) -> bool:
    """Compare states to determine if notification is needed"""
    if previous is None:
        return True  # First run, send notification
    
    # Check if instance count changed
    if previous.get('instanceCount') != current.get('instanceCount'):
        return True
    
    # Check if tag distribution changed
    prev_tags = previous.get('taggedInstances', {})
    curr_tags = current.get('taggedInstances', {})
    
    if prev_tags != curr_tags:
        return True
    
    return False

def check_subscription_exists(sns_client, topic_arn: str, email: str) -> bool:
    """Check if email subscription already exists"""
    try:
        response = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)
        for subscription in response['Subscriptions']:
            if subscription['Protocol'] == 'email' and subscription['Endpoint'] == email:
                return True
        return False
    except Exception as e:
        print(f"Error checking subscription: {str(e)}")
        return False

def send_alert(sns_client, message: str, emails: List[str]):
    """Send alert via SNS"""
    try:
        # Create SNS topic if not exists
        topic_response = sns_client.create_topic(Name='ec2-monitoring-alerts')
        topic_arn = topic_response['TopicArn']
        
        # Subscribe emails to topic (only if not already subscribed)
        for email in emails:
            if not check_subscription_exists(sns_client, topic_arn, email):
                print(f"Creating new subscription for {email}")
                sns_client.subscribe(
                    TopicArn=topic_arn,
                    Protocol='email',
                    Endpoint=email
                )
            else:
                print(f"Subscription already exists for {email}")
        
        # Publish message
        sns_client.publish(
            TopicArn=topic_arn,
            Subject='EC2 Instance Tagging Monitoring Alert',
            Message=message
        )
    except Exception as e:
        print(f"Failed to send alert: {str(e)}")