import boto3
from botocore.exceptions import ClientError

class S3():
    region = 'us-east-1'
    def __init__(self, bucket):
        self.bucket = bucket
        self.s3_client = boto3.client('s3', region_name=self.region)

    def get(self,key: str):
        try:
            s3obj = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            return s3obj['Body'].read()
        except ClientError as e:
            print(e)

    def put(self,key: str, data: str):
        # Put object in storage
        try:
            response = self.s3_client.put_object(Bucket=self.bucket, Key=key, Body=data)
            return response
        except ClientError as e:
            print(e)