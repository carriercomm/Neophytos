'''
	This can be run once, or run on interval. When run it will check all targets on all accounts
	to see if any are due to be run. If any are found due they will be pushed and their last run
	time reset on success. 
	
	It will try to service all users on the system if it can access their user path.
	
	service.py --service
	service.py --runonce
	
	You must provide one of the options or it will refuse to run. This is to ensure it
	is running in the desired mode. In service mode it will run continually and by default
	check every 5 minutes.
	
	Need way for status GUI to communicate with service about what it is currently doing
	in respect to current job it is executing.
'''

def main():
	return