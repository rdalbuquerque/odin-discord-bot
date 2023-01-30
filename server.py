import boto3
import botocore.exceptions as awserr
import re
import asyncio

class Valheim:
    region = 'sa-east-1'
    asg_name = 'valheim-ec2-cluster'
    ecs_service_name = 'valheim'
    log_group_name = 'valheim-container'

    def __init__(self, cluster):
        self.cluster = cluster
        self.asg_client = boto3.client("autoscaling", region_name=self.region)
        self.ecs_client = boto3.client("ecs", region_name=self.region)
        self.logs_client = boto3.client("logs", region_name=self.region)

    def task_status(self):
        tasks = self.ecs_client.list_tasks(cluster=self.cluster)
        if len(tasks["taskArns"]) != 0:
            task = self.ecs_client.describe_tasks(cluster=self.cluster,tasks=tasks["taskArns"])
            return task["tasks"][0]["lastStatus"], task["tasks"][0]["taskArn"].split("/")[-1]
        else:
            return 'STOPPED', None
    
    def gameserver_status(self, task_name):
        # Define the log group and stream name
        log_stream_name = f'valheim/valheim-latest/{task_name}'

        # Get the log events
        try: 
            response = self.logs_client.get_log_events(
                logGroupName=self.log_group_name,
                logStreamName=log_stream_name,
            )
        except awserr.ClientError as err:
            if err.response['Error']['Code'] == 'ResourceNotFoundException':
                return 'TASK LOGS NOT FOUND'

        status = 'NOT LOADED'
        for event in response['events']:
            if re.search("^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}: Game server connected$", event['message']):
                status = 'LOADED'
                break
        return status

    def status(self):
        # Possible status: LOADED, LOADING, RUNNING, PENDING, STOPPED
        task = self.task_status()
        if task[0] == 'RUNNING':
            if self.gameserver_status(task[1]) != 'LOADED':
                return 'LOADING'
            else:
                return 'LOADED'
        else:
            return task[0]


    async def start(self):
        self.asg_client.set_desired_capacity(
            AutoScalingGroupName=self.asg_name,
            DesiredCapacity=1
        )
        while not self.cluster_has_infra():
            print('scaling asg and associating instance to cluster')
            await asyncio.sleep(2)
        self.ecs_client.update_service(
            cluster=self.cluster,
            service=self.ecs_service_name,
            desiredCount=1
        )

    def stop(self):
        self.ecs_client.update_service(
            cluster=self.cluster,
            service=self.ecs_service_name,
            desiredCount=0
        )
        self.asg_client.set_desired_capacity(
            AutoScalingGroupName=self.asg_name,
            DesiredCapacity=0
        )

    def cluster_has_infra(self):
        container_instance_count = self.ecs_client.describe_clusters(
            clusters=[self.cluster]
        )['clusters'][0]['registeredContainerInstancesCount']
        if container_instance_count == 1:
            return True
        else:
            return False

