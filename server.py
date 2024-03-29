import boto3
import botocore.exceptions as awserr
import re
import asyncio
import os
import storage.s3 as storage
import container.container as valheim_container
import datetime

class Valheim:
    region = 'sa-east-1'
    ecs_service_name = 'valheim'
    log_group_name = 'valheim-container'
    world_saves_location = '/home/steam/.config/unity3d/IronGate/Valheim/worlds_local'

    def __init__(self, cluster):
        self.cluster = cluster
        self.asg_client = boto3.client("autoscaling", region_name=self.region)
        self.ecs_client = boto3.client("ecs", region_name=self.region)
        self.logs_client = boto3.client("logs", region_name=self.region)
        self.valheim_container = valheim_container.Container(cluster=cluster)
        self.set_status()
    
    def set_service_name(self, service_name):
        self.ecs_service_name = service_name

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
                startFromHead=True
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

    def set_status(self):
        # Possible status: LOADED, LOADING, RUNNING, PENDING, STOPPED
        task = self.task_status()
        if task[0] == 'RUNNING':
            if self.gameserver_status(task[1]) != 'LOADED':
                self.status = 'LOADING'
            else:
                self.status = 'LOADED'
        else:
            self.status = task[0]


    async def start(self):
        self.status = 'STARTING'
        self.asg_client.set_desired_capacity(
            AutoScalingGroupName=self.cluster,
            DesiredCapacity=1
        )
        while not self.cluster_has_infra():
            print(f'[{self.cluster}] scaling asg and associating instance to cluster')
            await asyncio.sleep(2)
        try:
            self.ecs_client.update_service(
                cluster=self.cluster,
                service=self.ecs_service_name,
                desiredCount=1
            )
        except Exception as e:
            print(e)

    def remove_infra(self):
        self.ecs_client.update_service(
            cluster=self.cluster,
            service=self.ecs_service_name,
            desiredCount=0
        )
        self.asg_client.set_desired_capacity(
            AutoScalingGroupName=self.cluster,
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

    def get_storage_details(self):
        try:
            valheim_container_dfh = self.valheim_container.exec_in_container('df -h --output=pcent,target')
            return valheim_container_dfh
        except Exception as e:
            print(e)
            return e

    def stop_valheim_process(self):
        self.valheim_container.exec_in_container(cmd='odin stop &', path='/home/steam/valheim')

    def make_valheim_bkp(self):
        now = datetime.datetime.now()
        datetime_str = now.strftime("%Y%m%d%H%M%S")
        world_name = self.cluster
        bkp_file_name = f'bkp_{world_name}_{datetime_str}.tar.gz'
        print(f'[{self.cluster}] Generating backup named {bkp_file_name}')
        self.valheim_container.compress_files(bkp_file_name)
        print(f'[{self.cluster}] Copying from container')
        self.valheim_container.copy_bkp_from_container_to_ecs_agent(bkp_file_name)
        print(f'[{self.cluster}] Copying from ecs agent')
        self.valheim_container.copy_bkp_from_ecs_agent(from_path=f'/home/ec2-user/{bkp_file_name}', to_path=bkp_file_name)
        print(os.listdir())
        s3_storage = storage.S3(bucket='valheim-backup-rda')
        with open(bkp_file_name, 'rb') as f:
            file_contents = f.read()
        # Put the file in the S3 bucket
        response = s3_storage.put(key=f"{self.cluster}/{bkp_file_name}", data=file_contents)
        print(response)

    def cleanup_old_days(self, num_days_to_keep):
        num_files_to_keep = num_days_to_keep*2+4
        print(f'[{self.cluster}] keeping {num_files_to_keep} files')
        self.valheim_container.delete_saves(num_files_to_keep)
