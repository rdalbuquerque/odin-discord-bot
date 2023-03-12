import boto3
from botocore.exceptions import ClientError

class S3():
    region = 'us-east-1'
    def __init__(self, bucket):
        self.bucket = bucket
        self.s3_client = boto3.client('s3', region_name=self.region)

    def list(self):
        try:
            contents = self.s3_client.list_objects_v2(Bucket=self.bucket)['contents']
            return [obj['Key'] for obj in contents] if contents else []
        except ClientError as e:
            print(e)

    def put(self,key: str, data: str):
        # Put object in storage
        try:
            response = self.s3_client.put_object(Bucket=self.bucket, Key=key, Body=data)
            return response
        except ClientError as e:
            print(e)