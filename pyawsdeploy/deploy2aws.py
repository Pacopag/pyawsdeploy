from pyawsdeploy.deploy import AwsDeploy
import sys

def main():
	args = sys.argv
	if len(args)==0:
		return usage()
	deployment = args[1]
	build_args = args[2:] if len(args)>2 else []
	if len(build_args) and build_args[0]=="rollback":
		return AwsDeploy().run(deployment, [], rollback=True)
	AwsDeploy().run(deployment, build_args)

def usage():
	print("Usage: deploy2aws <deployment_name> [<build_arg>...]")

if __name__ == "__main__":
	main()