from pyawscli.client import AwsClient
from .exceptions import AwsDeployException
from subprocess import Popen, PIPE
import json, sys, datetime, os, time

def error_handler(err, args):
	print(err.decode('utf-8'))
	print(args)

class AwsDeploy:

	def __init__(self, config=None, config_path=None, results_dir=None):
		if config_path is None:
			config_path = os.path.expanduser('~')+"/.awsdeploy/deployments.json"

		with open(config_path, 'r') as f:
			self.deployments_config = json.loads(f.read())

		if results_dir is None:
			results_dir = os.path.expanduser('~')+"/.awsdeploy/results/"
		elif not results_dir.endswith('/'):
			results_dir+='/'

		self.results_dir = results_dir

		if config is not None:
			self.deployments_config = config

	def run(self, name, build_args, rollback=False):
		self.name = name
		self.build_args = build_args

		if name not in self.deployments_config:
			raise AwsDeployException("Configuration not found for deployment "+self.quote_name)

		self.start_time = datetime.datetime.utcnow()
		self.results_fname = self.start_time.isoformat().replace(':','_')
		with open(self.results_dir+self.results_fname, 'w') as f:
			try:
				self.results = f

				print("Reading configuration...")
				self.read_config()

				if not rollback:
					print("Building...")
					self.build()
					print("Deploying...")
					self.deploy()
				else:
					print("Rollback...")
					self.rollback()
				
			except Exception as exception:
				self.results.write('Status:\tFailed'+"\n")
				self.results.write('Reason:\t'+str(exception)+"\n")
				self.results.write("Time:\t"+str((datetime.datetime.utcnow()-self.start_time).total_seconds())+"\n")
				raise exception

	def read_config(self):
		self.deployment_config = self.deployments_config[self.name]
		#self.results.write("Config:\t"+str(self.deployment_config)+"\n")
		self.build_cmd = self.get_build_cmd()
		self.profile = self.get_profile()
		self.results.write("Profile:\t"+str(self.profile)+"\n")
		self.region = self.get_region()
		self.results.write("Region:\t"+str(self.region)+"\n")

		self.aws = AwsClient(
			profile = self.profile,
			region = self.region,
			error_handler = error_handler
		)

		self.retention = self.get_retention()
		self.results.write("Retention:\t"+str(self.retention)+"\n")
		self.instance = self.get_instance()
		self.results.write("Instance:\t"+str(self.instance)+"\n")
		self.launch_config_config = self.get_launch_config()
		self.instance_type = self.get_instance_type()
		self.results.write("Instance type:\t"+str(self.instance_type)+"\n")
		self.key_name = self.get_key_name()
		self.results.write("Key name:\t"+str(self.key_name)+"\n")
		self.security_groups = self.get_security_groups()
		self.security_group_ids = self.get_security_group_ids()
		self.results.write("Security groups:\t"+str(self.security_group_ids)+"\n")
		self.scaling_group = self.get_scaling_group()
		self.elb = self.get_elb()
		self.results.write("Scaling group:\t"+str(self.scaling_group)+"\n")

	def get_build_cmd(self):
		if 'build_cmd' not in self.deployment_config:
			print("WARNING: No build_cmd specified for deployment "+self.quote_name)
			return None
		return self.deployment_config['build_cmd']

	def get_profile(self):
		if 'profile' not in self.deployment_config:
			raise AwsDeployException("No profile specified for deployment "+self.quote_name)
		return self.deployment_config['profile']

	def get_region(self):
		if 'region' not in self.deployment_config:
			raise AwsDeployException("No region specified for deployment "+self.quote_name)
		return self.deployment_config['region']

	def get_retention(self):
		if 'retention' not in self.deployment_config:
			return 3
		retention = self.deployment_config['retention']
		try:
			return max(1, int(retention))
		except:
			raise AwsDeployException("Improperly configured retention for deployment "+self.quote_name)

	def get_instance(self):
		if 'instance' not in self.deployment_config:
			raise AwsDeployException("No instance specified for deployment "+self.quote_name)
		instance_config = self.deployment_config['instance']
		if 'instance_id' in instance_config:
			instance = self.aws.ec2.instance_by_id(instance_config['id'])
		elif 'name' in instance_config:
			instances = self.aws.ec2.instances_by_name(instance_config['name'])
			instance = instances[0] if len(instances)>0 else None
		else:
			raise AwsDeployException("Improperly configured instance for deployment "+self.quote_name)
		if instance is None:
			raise AwsDeployException("Cannot find ec2 instance for deployment "+self.quote_name)
		return instance

	def get_launch_config(self):
		if 'launch_config' not in self.deployment_config:
			raise AwsDeployException("No launch_config specified for deployment "+self.quote_name) 
		return self.deployment_config['launch_config']

	def get_instance_type(self):
		if 'type' not in self.launch_config_config:
			raise AwsDeployException("No instance type specified in launch_config for deployment "+self.quote_name)
		return self.launch_config_config['type']

	def get_key_name(self):
		if 'key_name' not in self.launch_config_config:
			raise AwsDeployException("No key_name specified in launch_config for deployment "+self.quote_name)
		return self.launch_config_config['key_name']

	def get_security_groups(self):
		if 'security_groups' not in self.launch_config_config or len(self.launch_config_config['security_groups'])==0:
			raise AwsDeployException("No security groups specified in launch_config for deployment "+self.quote_name)
		return self.launch_config_config['security_groups']

	def get_security_group_ids(self):
		ids = []
		for i,sg in enumerate(self.security_groups):
			if 'id' in sg:
				security_group = self.aws.ec2.security_group_by_id(sg['id'])
				if security_group is None:
					raise AwsDeployException("Could not find security group with id "+sg['id'])
				ids.append(sg['id'])
			elif 'name' in sg:
				security_groups = self.aws.ec2.security_groups_by_name(sg['name'])
				if len(security_groups)==0:
					raise AwsDeployException("Could not find security group with name "+sg['name'])
				ids.append(security_groups[0]['GroupId'])
			else:
				raise AwsDeployException("Improperly configured security group at position "+i+" in launch_config for deployment "+self.quote_name)
		return ids

	def get_scaling_group(self):
		if 'scaling_group' in self.deployment_config:
			if 'arn' in self.deployment_config['scaling_group']:
				scaling_group_id = self.deployment_config['scaling_group']['arn']
				key = 'AutoScalingGroupARN'
			elif 'name' in self.deployment_config['scaling_group']:
				scaling_group_id = self.deployment_config['scaling_group']['name']
				key = 'AutoScalingGroupName'
			else:
				raise AwsDeployException("Improperly configured scaling_group for deployment "+self.quote_name)
		else:
			scaling_group_id = self.name
			key = 'AutoScalingGroupName'
		try:
			return self.aws.autoscaling.scaling_groups_by(key, scaling_group_id)[0]
		except IndexError:
			raise AwsDeployException("No scaling group found for "+scaling_group_id)

	def get_elb(self):
		if 'elb' in self.deployment_config:
			if 'name' in self.deployment_config['elb']:
				elb_id = self.deployment_config['elb']['name']
				key = 'LoadBalancerName'
			elif 'dns_name' in self.deployment_config['elb']:
				elb_id = self.deployment_config['elb']['dns_name']
				key = 'DNSName'
		else:
			if len(self.scaling_group['LoadBalancerNames']):
				elb_id = self.scaling_group['LoadBalancerNames'][0]
				key = 'LoadBalancerName'
			else:
				raise AwsDeployException("Improperly configured elb for deployment "+self.quote_name+". Check that the auto scaling group "+self.scaling_group['AutoScalingGroupName']+" has a load balancer assigned to it")
		try:
			return self.aws.elb.balancers_by(key, elb_id)[0]
		except IndexError:
			raise AwsDeployException("No load balancer found for "+elb_id)


	def build(self):
		if self.build_cmd is None:
			return
		build_file = self.results_dir+self.results_fname+".build"
		with open(build_file, 'w') as writer, open(build_file, 'r') as reader:
			p = Popen(self.build_cmd.split(' ')+self.build_args, stdin=PIPE, stdout=writer, stderr=writer)
			while p.poll() is None:
				line = reader.read()
				sys.stdout.write(line)
				time.sleep(0.5)
			sys.stdout.write(reader.read())
			if p.returncode!=0:
				pass
				#raise AwsDeployException("Build failed with code "+str(p.returncode))

	def deploy(self):
		print("Creating image...")
		self.ami = self.create_ami()
		self.results.write("AMI:\t"+str(self.ami)+"\n")
		print("Creating launch config...")
		self.launch_config = self.create_launch_config()
		self.results.write("Launch config:\t"+str(self.launch_config)+"\n")
		self.replace_nodes()

	def replace_nodes(self):
		print("Registering template to the elb...")
		self.register_instance()
		print("Configuring scaling group...")
		res = self.update_scaling_group()
		print("Terminating existing nodes...")
		res = self.terminate_old_nodes()
		self.results.write("Terminated:\t"+str(res)+"\n")
		print("Waiting for new nodes...")
		self.new_instances = self.wait_for_new_nodes()
		self.results.write("New instances:\t"+str(self.new_instances)+"\n")
		self.wait_for_service()
		self.deregister_instance()
		print("Cleaning up...")
		self.cleanup()
		self.results.write("Status:\tDone"+"\n")
		self.results.write("Time:\t"+str((datetime.datetime.utcnow()-self.start_time).total_seconds())+"\n")

	def create_ami(self):
		ami = self.aws.ec2.create_ami(self.instance, name_prefix=self.name, no_reboot=True, wait_for_state=True)
		if 'State' in ami and ami['State']=='available':
			return ami
		else:
			raise AwsDeployException("Failed to create ami for deployment "+self.quote_name)

	def create_launch_config(self):
		name = self.aws.autoscaling.create_launch_configuration(self.ami, self.instance_type, self.key_name, self.security_group_ids)
		return self.aws.autoscaling.launch_configuration_by_name(name)

	def register_instance(self):
		return self.aws.elb.register_instances(self.elb['LoadBalancerName'], self.instance, wait_for_service=True)

	def deregister_instance(self):
		return self.aws.elb.deregister_instances(self.elb['LoadBalancerName'], self.instance)

	def update_scaling_group(self):
		return self.aws.autoscaling.update_scaling_group_launch_config(self.scaling_group, self.launch_config)

	def terminate_old_nodes(self):
		instances = self.aws.ec2.instances_in_scaling_group(self.scaling_group)
		return self.aws.ec2.terminate_instances(instances)

	def wait_for_new_nodes(self):
		then = time.time()
		done = False
		while not done:
			now = time.time()
			scaling_group = self.get_scaling_group()
			capacity = scaling_group['DesiredCapacity']
			timeout = 300*capacity # Let's wait five minutes per member
			instances = scaling_group['Instances']
			new_instances = [i for i in instances if i['LaunchConfigurationName']==self.launch_config['LaunchConfigurationName']]
			num_new_instances = len(new_instances)
			if num_new_instances==capacity:
				done = True
			elif now-then > timeout:
				print("WARNING: Timeout while waiting for scaling group to reach capacity")
				if num_new_instances==0:
					raise AwsDeployException("AWS failed to spin up new instances into the scaling group.")
				else:
					break
			time.sleep(5)
		return new_instances

	def wait_for_service(self):
		then = time.time()
		new_instance_ids = [i['InstanceId'] for i in self.new_instances]
		done = False
		while not done:
			now = time.time()
			instances = self.aws.elb.health(self.elb['LoadBalancerName'])
			instances_in_service = [i for i in instances if i['State']=='InService' and i['InstanceId'] in new_instance_ids]
			if len(instances_in_service)>0:
				done = True
			elif now-then > 600:
				raise AwsDeployException("Timeout while waiting for new instances to come into service")
			time.sleep(5)

	def cleanup(self):
		filenames = []
		for _dirpath, _dirnames, _filenames in os.walk(self.results_dir):
			filenames = _filenames
			break
		
		launch_configs = self.aws.autoscaling.launch_configurations()
		launch_configs = [l for l in launch_configs if l['LaunchConfigurationName'].startswith(self.name)]
		launch_configs = sorted(launch_configs, key=lambda k: k['CreatedTime'])[:-self.retention]
		for l in launch_configs:
			self.aws.autoscaling.delete_launch_configuration(l['LaunchConfigurationName'])
		self.results.write("Deleted Launch Configs:\t"+str(launch_configs)+"\n")
		ami_ids = [l['ImageId'] for l in launch_configs]
		self.aws.ec2.deregister_amis(ami_ids)
		self.results.write("Deregistered AMIs:\t"+str(ami_ids)+"\n")
		self.aws.ec2.cleanup_snapshots_from_amis()

	def rollback(self):
		print("Finding launch configurations...")
		launch_configs = self.aws.autoscaling.launch_configurations()
		launch_configs = [l for l in launch_configs if l['LaunchConfigurationName'].startswith(self.name)]
		launch_configs = sorted(launch_configs, key=lambda k: k['CreatedTime'], reverse=True)
		print("Choose a launch configuration:")
		for i,l in enumerate(launch_configs):
			print(str(i)+')','|', l['LaunchConfigurationName'], '|', "AMI: "+l['ImageId'], '|', "Created: "+l['CreatedTime'])
		try:
			index = int(input('Default (1):').strip())
		except ValueError:
			index = 1
		self.launch_config = launch_configs[index]
		self.replace_nodes()


	@property
	def quote_name(self):
		return '"'+self.name+'"'