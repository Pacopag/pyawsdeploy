class AwsDeployException(Exception):
	def __init__(self, message):
		super(AwsDeployException, self).__init__(message)