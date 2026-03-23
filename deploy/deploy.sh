#!/bin/bash

# EC2 Monitoring and Tagging Automation Deployment Script

STACK_NAME="ec2-monitoring-tagging-stack"
FUNCTION_NAME="ec2-monitoring-tagging"
REGION="us-east-1"

echo "🚀 Starting deployment..."

# Create deployment package
echo "📦 Creating deployment package..."
zip -r lambda-deployment.zip lambda_function.py

# Deploy CloudFormation stack
echo "☁️ Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name $STACK_NAME \
    --capabilities CAPABILITY_IAM \
    --region $REGION

# Update Lambda function code
echo "🔄 Updating Lambda function code..."
aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb://lambda-deployment.zip \
    --region $REGION

# Clean up
rm lambda-deployment.zip

echo "✅ Deployment completed!"
echo "📊 Monitor the function logs with:"
echo "aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION"