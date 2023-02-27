import boto3
import botocore.exceptions as awserr
import re
import asyncio
import paramiko

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

    def get_ecs_instance_public_ip(self):
        try:
            instance_arn = self.ecs_client.list_container_instances(
                cluster=self.cluster,
                maxResults=1
            )['containerInstanceArns'][0]
            ec2_instance_id = self.ecs_client.describe_container_instances(
                cluster=self.cluster,
                containerInstances=[instance_arn]
            )['containerInstances'][0]['ec2InstanceId']
            ec2 = boto3.client('ec2', region_name=self.region)
            ec2_public_ip = ec2.describe_instances(
                InstanceIds=[ec2_instance_id]
            )['Reservations'][0]['Instances'][0]['PublicIpAddress']
            return ec2_public_ip
        except Exception as e:
            return e

    def new_ssh_client(self):
        try:
            ec2_public_ip = self.get_ecs_instance_public_ip()
            key = paramiko.RSAKey.from_private_key_file('valheim-sa.pem')
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            print(f'connecting to instance {ec2_public_ip}')
            client.connect(hostname=ec2_public_ip, username='ec2-user', pkey=key)
            return client 
        except Exception as e:
            return e


    def exec_in_container(self, cmd):
        try:
            client = self.new_ssh_client()
            _, stdout, _ = client.exec_command("printf $(docker ps -aqf 'name=valheim')")
            valheim_container_id = stdout.read().decode()
            describe_valheim_fs_cmd = f"docker exec -it {valheim_container_id} {cmd}"
            print(f'executing command: "{describe_valheim_fs_cmd}"')
            _, stdout, _ = client.exec_command(f"exec {describe_valheim_fs_cmd}", get_pty=True)
            result = stdout.read().decode()
            client.close()
            return result
        except Exception as e:
            print(e)
            client.close()
            return e

    def get_volume_details(self):
        try:
            valheim_container_dfh = self.exec_in_container('df -h --output=pcent,target')
            return valheim_container_dfh
        except Exception as e:
            print(e)
            return e



